"""Backfill daily OHLCV bars for the ETF rotation pool (dividend-adjusted).

Input:  backend/app/services/quant/etf_pool.json
Output: backend/data/backfill_etf_klines.json

Source choice (a-stock-data SKILL.md priority rules):
  - mootdx ranks #1 (TCP, no IP ban) but returns UNADJUSTED prices, and
    several pool ETFs pay dividends (510300 / 512800 / 511010...) whose
    ex-dividend gaps would corrupt momentum. Adjusted klines are the
    capability only EM carries among the no-akshare sources.
  - So: EM push2his `stock/kline/get` with fqt=2 (后复权), direct HTTP —
    zero third-party wrappers — under the SKILL's em_get() throttle
    discipline (serial, ≥1s + jitter, Keep-Alive session, browser UA).
    Pool volume is ~17 ETFs × 1 request: far below every block threshold.
  - Fallback if EM blocks the IP: scripts/backfill_mootdx_klines.py works
    on ETF codes too (unadjusted; flag any momentum caveats).

Money-ETF note: 511990's 场内价格 is pinned near 100 — the hfq series
carries the accrued yield (收益结转), which is exactly what the engine's
absolute-momentum hurdle wants. If EM ever returns it flat, the gate
degrades gracefully to "> 0".

Usage:
    python scripts/backfill_etf_klines.py               # full history
    python scripts/backfill_etf_klines.py --incremental # last ~30 bars only
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import time
from datetime import datetime
from pathlib import Path

import requests

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

DATA_DIR = BACKEND_DIR / "data"
POOL_PATH = BACKEND_DIR / "app" / "services" / "quant" / "etf_pool.json"
OUT_PATH = DATA_DIR / "backfill_etf_klines.json"

KLINE_URL = "https://push2his.eastmoney.com/api/qt/stock/kline/get"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
EM_HEADERS = {
    "User-Agent": UA,
    "Referer": "https://quote.eastmoney.com/",
    "Origin": "https://quote.eastmoney.com",
}
RETRIES = 3

# EM throttle discipline (SKILL.md §东财防封 + #18): serial + ≥1.5s interval
# with jitter + one Keep-Alive session + browser headers. push2his is
# touchier than datacenter, matching backfill_em_fund_flow's 1.5s.
EM_MIN_INTERVAL = 1.5
_session = requests.Session()
_session.headers.update({"User-Agent": UA})
_last_call = [0.0]

# Circuit breaker: push2his IP blocks are all-or-nothing (skill #18) —
# after this many consecutive failures stop hammering and fail loudly.
_EM_FAIL_STREAK_LIMIT = 3
_em_fail_streak = [0]


def em_get(url: str, params: dict, timeout: int = 20) -> dict:
    """Throttled GET returning parsed JSON (raises through on errors)."""
    wait = EM_MIN_INTERVAL - (time.time() - _last_call[0])
    if wait > 0:
        time.sleep(wait + random.uniform(0.1, 0.5))
    try:
        r = _session.get(url, params=params, headers=EM_HEADERS, timeout=timeout)
        r.raise_for_status()
        return r.json()
    finally:
        _last_call[0] = time.time()


def market_code_for(code: str) -> int:
    """ETF code prefix → EM market id (1=上海, 0=深圳).

    SH ETFs: 51x/56x/58x (all start with 5); SZ ETFs: 15x/16x. Stock
    prefixes (6/9→SH, 8→BJ) kept for parity with the other scripts.
    """
    return 1 if code.startswith(("5", "6", "9")) else 0


def fetch_klines(code: str, incremental: bool = False) -> list[dict]:
    """One ETF's daily hfq bars, listing→today in ONE request.

    incremental keeps the same proven beg/end form (the lmt-only variant
    was never verified against EM and saves nothing — it is still one
    request per ticker; the upsert is idempotent either way).
    """
    params = {
        "secid": f"{market_code_for(code)}.{code}",
        "klt": "101",            # daily
        "fqt": "2",              # 后复权 (dividend-adjusted)
        "beg": "0", "end": "20500101",
        "fields1": "f1,f2,f3,f4,f5,f6",
        "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
    }

    if _em_fail_streak[0] >= _EM_FAIL_STREAK_LIMIT:
        raise RuntimeError("EM circuit open (consecutive failures) — "
                           "likely the intermittent push2his IP block "
                           "(skill #18); retry later or switch network")

    last_err: Exception | None = None
    for attempt in range(RETRIES):
        try:
            d = em_get(KLINE_URL, params)
            _em_fail_streak[0] = 0
            break
        except Exception as e:  # transport/parse error → backoff and retry
            last_err = e
            time.sleep(2 ** attempt + random.uniform(0.5, 1.5))
    else:
        _em_fail_streak[0] += 1
        raise RuntimeError(f"failed after {RETRIES} attempts: {last_err}")

    klines = ((d.get("data") or {}).get("klines")) or []
    bars = []
    for line in klines:
        parts = line.split(",")
        if len(parts) < 7:
            continue
        # EM field order: date, open, close, high, low, volume(手), amount(元)
        try:
            bars.append({
                "ticker": code,
                "date": parts[0],
                "open": float(parts[1]),
                "high": float(parts[3]),
                "low": float(parts[4]),
                "close": float(parts[2]),
                "volume": float(parts[5]) * 100,   # 手 → 份
                "amount": float(parts[6]),
            })
        except ValueError:
            continue  # "-" placeholders on suspended days
    return bars


def main():
    ap = argparse.ArgumentParser(description="Backfill ETF pool daily bars (EM hfq)")
    ap.add_argument("--incremental", action="store_true",
                    help="Only fetch the last ~30 bars per ETF (daily refresh)")
    ap.add_argument("--limit", type=int, default=None,
                    help="Cap number of ETFs (for smoke testing)")
    args = ap.parse_args()

    pool = json.loads(POOL_PATH.read_text(encoding="utf-8"))
    tickers = [e["ticker"] for e in pool["etfs"]]
    if args.limit:
        tickers = tickers[: args.limit]

    # Stale-first ordering: the #18 block tends to cut the connection
    # after a burst of requests, stranding the pool's tail. Re-runs start
    # from the STALEST tickers (oldest last-bar first — pure-missing have
    # no bars at all so they sort first) so each window of availability
    # makes maximal progress (merge semantics below keep the old bars for
    # whoever fails again).
    if OUT_PATH.exists():
        try:
            prev_bars = json.loads(
                OUT_PATH.read_text(encoding="utf-8")).get("bars", {})
        except (ValueError, OSError):
            prev_bars = {}
        if prev_bars:
            def _last_date(t: str) -> str:
                b = prev_bars.get(t)
                return b[-1]["date"] if b else ""
            tickers = sorted(set(tickers), key=_last_date)

    print(f"Backfilling {'recent' if args.incremental else 'full history'} "
          f"hfq bars for {len(tickers)} ETFs via EM push2his (throttled) ...")

    all_bars: dict[str, list[dict]] = {}
    missing: list[str] = []
    total_bars = 0
    started = time.time()

    for i, code in enumerate(tickers, 1):
        try:
            bars = fetch_klines(code, incremental=args.incremental)
        except Exception as e:
            print(f"  [ERR]  {code}: {e}")
            missing.append(code)
            continue
        if not bars:
            print(f"  [WARN] {code}: empty — delisted/suspended?")
            missing.append(code)
            continue
        all_bars[code] = bars
        total_bars += len(bars)
        if i % 5 == 0 or i == len(tickers):
            elapsed = time.time() - started
            print(f"  [{i}/{len(tickers)}] {code}: {len(bars)} bars "
                  f"| {elapsed:.0f}s elapsed")

    if not all_bars:
        # Total failure (e.g. the #18 intermittent push2his IP block):
        # DON'T overwrite the last good output file — exit non-zero so the
        # refresh log records 'failed' instead of a misleading 'succeeded'.
        print("  [FATAL] no bars fetched — keeping the previous output file")
        sys.exit(1)

    # Merge semantics: a partial run (the IP block flaps mid-run) keeps the
    # previous file's bars for tickers that failed NOW, so re-runs are
    # strictly additive until the whole pool is fresh. Stale members are
    # listed in the output metadata for honesty.
    prev_bars: dict = {}
    if OUT_PATH.exists():
        try:
            prev_bars = json.loads(
                OUT_PATH.read_text(encoding="utf-8")).get("bars", {})
        except (ValueError, OSError):
            prev_bars = {}
    stale = sorted(t for t in prev_bars if t not in all_bars)
    for t in stale:
        all_bars[t] = prev_bars[t]
    missing = [t for t in tickers if t not in all_bars]
    total_bars = sum(len(b) for b in all_bars.values())

    output = {
        "source": "eastmoney push2his kline fqt=2 (后复权)",
        "fetched_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "source_method": "a-stock-data SKILL.md 东财防封纪律 (em_get 节流)",
        "mode": "incremental" if args.incremental else "full",
        "ticker_count": len(all_bars),
        "stale_tickers": stale,
        "missing_count": len(missing),
        "missing_samples": missing[:10],
        "total_bars": total_bars,
        "bars": all_bars,
    }
    OUT_PATH.write_text(json.dumps(output, ensure_ascii=False), encoding="utf-8")

    print("=" * 80)
    print("ETF kline backfill complete")
    print("=" * 80)
    print(f"  ETFs in pool:        {len(tickers)}")
    print(f"  With bars:           {len(all_bars)}")
    print(f"  Stale (kept old):    {len(stale)} {stale[:5]}")
    print(f"  Missing:             {len(missing)}")
    print(f"  Total bars stored:   {total_bars:,}")
    print(f"  Elapsed:             {time.time() - started:.0f}s")
    print(f"  Output:              {OUT_PATH}")
    if missing:
        print(f"  Missing samples:     {missing[:5]}")
        sys.exit(1)  # refresh log must record 'failed' while pool incomplete


if __name__ == "__main__":
    main()
