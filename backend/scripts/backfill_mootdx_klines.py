"""
Backfill daily OHLCV bars for all CN-listed companies in the seed.

Input:  backend/data/aichainmap_seed.json
Output: backend/data/backfill_mootdx_klines.json

Uses the mootdx (通达信) TCP binary protocol (a-stock-data skill §1.1).
Chosen because:
  - TCP protocol does NOT share East Money's IP-blocking behavior (skill
    priority table ranks mootdx #1 for "封IP风险: 极低").
  - Returns full OHLCV per bar in one payload — exactly the shape needed
    for the quant backtester and signal scanner.
  - Already a project dependency (existing backfill_mootdx_finance.py uses it).

mootdx API (v0.11+):
    client.bars(symbol, frequency=9, start=0, offset=800)
        frequency=9 → daily bars (旧名 category=4, 0.11 renamed to frequency)
        start   → pagination offset (0 = most recent)
        offset  → bars per request (max 800)
    Two pages (start=0 + start=800) cover ~6.6 years (1600 bars). We merge
    by datetime and drop duplicates.

Ticker normalization:
    The seed stores a few tickers with exchange suffixes (e.g. 002594.SZ for
    比亚迪). mootdx wants the bare 6-digit code, so we strip the suffix here.
    Market is derived from the first digit (6/9→SH, 8→BJ, else→SZ), matching
    scripts/load_seed_to_db.py:_derive_cn_market.

Usage:
    python scripts/backfill_mootdx_klines.py            # full 5y backfill
    python scripts/backfill_mootdx_klines.py --incremental  # only today's bar
"""

from __future__ import annotations

import argparse
import json
import time
from datetime import datetime
from pathlib import Path

import pandas as pd
from mootdx.quotes import Quotes

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
SEED_PATH = DATA_DIR / "aichainmap_seed.json"
OUT_PATH = DATA_DIR / "backfill_mootdx_klines.json"

# frequency=9 is daily bars in mootdx 0.11+ (renamed from category=4).
# See mootdx docs / existing backfill_mootdx_finance.py.
FREQUENCY_DAILY = 9
# mootdx caps each request at 800 bars.
PAGE_SIZE = 800
# 5 years ≈ 1220 trading days; two pages (1600 bars) comfortably cover it.
PAGES_FOR_FULL = 2

_client = None


def get_client():
    """Lazy-init a single mootdx client (TCP connection reuse)."""
    global _client
    if _client is None:
        _client = Quotes.factory(market="std")
    return _client


def normalize_ticker(raw: str) -> str:
    """Strip exchange suffixes (.SH/.SZ/.BJ). Seed stores a few verbatim
    (e.g. 002594.SZ). mootdx wants the bare 6-digit code."""
    return str(raw).split(".")[0]


def market_code_for(code: str) -> int:
    """6-digit code → mootdx market id (0=深圳, 1=上海).

    mootdx's `bars()` auto-detects market from the code prefix, so this
    helper is only needed for explicit APIs. Kept for parity with other
    scripts and future IPO edge cases.
    """
    return 1 if code.startswith(("6", "9")) else 0


def fetch_history(code: str, pages: int = PAGES_FOR_FULL) -> pd.DataFrame:
    """Fetch `pages * PAGE_SIZE` daily bars for one ticker, merged & deduped.

    Returns DataFrame indexed by datetime with columns:
        open, close, high, low, vol, amount, datetime, volume
    Sorted ascending by date. Empty DataFrame on failure.
    """
    client = get_client()
    frames: list[pd.DataFrame] = []
    for page in range(pages):
        start = page * PAGE_SIZE
        try:
            df = client.bars(
                symbol=code, frequency=FREQUENCY_DAILY,
                start=start, offset=PAGE_SIZE,
            )
        except Exception as e:  # network blip / connection reset
            print(f"  [WARN] {code} page {page} failed: {e}; retry once")
            time.sleep(1.5)
            try:
                df = client.bars(
                    symbol=code, frequency=FREQUENCY_DAILY,
                    start=start, offset=PAGE_SIZE,
                )
            except Exception as e2:
                print(f"  [ERR]  {code} page {page} gave up: {e2}")
                continue
        if df is None or df.empty:
            # No more history past this page; stop early.
            break
        frames.append(df)
        # mootdx returns fewer than PAGE_SIZE when history runs out.
        if len(df) < PAGE_SIZE:
            break
        # Polite pause between pages for the same ticker.
        time.sleep(0.15)

    if not frames:
        return pd.DataFrame()

    merged = pd.concat(frames, ignore_index=True)
    # Dedup by datetime (pages overlap by 0–1 bar at the boundary).
    merged = merged.drop_duplicates(subset="datetime").sort_values("datetime")
    return merged.reset_index(drop=True)


def fetch_today(code: str) -> pd.DataFrame:
    """Fetch only the latest bar (for incremental daily refresh)."""
    return fetch_history(code, pages=1).tail(1).reset_index(drop=True)


def collect_cn_tickers(seed: dict) -> dict[str, str]:
    """Return {normalized_ticker: seed_name} for CN-listed companies only.

    Mirrors load_seed_to_db.py's CN filter (market == "CN"). Reference
    HK/US peers are excluded — they have no mootdx daily bars.
    """
    out: dict[str, str] = {}
    for layer in seed["layers"]:
        for sub in layer["sub_industries"]:
            for comp in sub["visible_companies"]:
                if comp.get("market") != "CN":
                    continue
                norm = normalize_ticker(comp["ticker"])
                # setdefault: keep first occurrence (dedup across sub-industries)
                out.setdefault(norm, comp.get("name", ""))
    return out


def bars_to_records(code: str, df: pd.DataFrame) -> list[dict]:
    """Convert mootdx DataFrame rows into JSON-serializable bar dicts.

    mootdx returns `vol` in 手 (lots; 1 lot = 100 shares) and `amount` in 元.
    We convert vol → shares (×100). Verified against the price-band sanity
    check: 002202 on 2026-07-15 has vol=849600, amount=1.62e9 → avg price
    = amount / (vol*100) = 19.04, which falls inside [18.82, 19.38]. ✓
    """
    records = []
    for _, row in df.iterrows():
        # mootdx datetime is a string like "2026-07-17 15:00"
        dt_str = str(row["datetime"]).strip()
        date_str = dt_str.split(" ")[0]  # YYYY-MM-DD
        # mootdx `vol` is in 手 (lots); ×100 → shares. (`volume` column is
        # identical to `vol`, not pre-converted.)
        vol_lots = float(row["vol"])
        records.append({
            "ticker": code,
            "date": date_str,
            "open": float(row["open"]),
            "high": float(row["high"]),
            "low": float(row["low"]),
            "close": float(row["close"]),
            "volume": vol_lots * 100,            # shares
            "amount": float(row["amount"]),      # 元
        })
    return records


def main():
    ap = argparse.ArgumentParser(description="Backfill CN daily bars via mootdx")
    ap.add_argument("--incremental", action="store_true",
                    help="Only fetch the latest bar per ticker (daily refresh)")
    ap.add_argument("--limit", type=int, default=None,
                    help="Cap number of tickers (for smoke testing)")
    ap.add_argument("--pool", action="store_true",
                    help="Use the sector-rotation pool (data/sector_pool.json) "
                         "instead of the aichainmap seed")
    args = ap.parse_args()

    if args.pool:
        # Sector-rotation universe (hard-constrained pool). Lives inside
        # the quant package (tracked config), not in gitignored data/.
        pool_path = Path(__file__).resolve().parent.parent / "app" / "services" / "quant" / "sector_pool.json"
        pool = json.loads(pool_path.read_text(encoding="utf-8"))
        tickers: dict[str, str] = {}
        for cfg in pool.values():
            for t, name in cfg["stocks"]:
                tickers.setdefault(t, name)
    else:
        if not SEED_PATH.exists():
            raise SystemExit(f"seed not found: {SEED_PATH}")
        seed = json.loads(SEED_PATH.read_text(encoding="utf-8"))
        tickers = collect_cn_tickers(seed)
    if args.limit:
        # Deterministic slice for reproducible smoke tests.
        items = list(tickers.items())[: args.limit]
        tickers = dict(items)

    codes = sorted(tickers)
    print(f"Backfilling {'latest bar' if args.incremental else '5y history'} "
          f"for {len(codes)} CN tickers via mootdx TCP ...")

    all_bars: dict[str, list[dict]] = {}
    missing: list[str] = []
    total_bars = 0
    started = time.time()

    for i, code in enumerate(codes, 1):
        try:
            if args.incremental:
                df = fetch_today(code)
            else:
                df = fetch_history(code)
        except Exception as e:
            print(f"  [ERR] {code} ({tickers[code]}): {e}")
            missing.append(code)
            continue

        if df is None or df.empty:
            print(f"  [WARN] {code} ({tickers[code]}): empty — delisted/suspended?")
            missing.append(code)
            continue

        records = bars_to_records(code, df)
        all_bars[code] = records
        total_bars += len(records)

        # Progress every 20 tickers.
        if i % 20 == 0 or i == len(codes):
            elapsed = time.time() - started
            rate = i / elapsed if elapsed > 0 else 0
            print(f"  [{i}/{len(codes)}] {code} {tickers[code]}: "
                  f"{len(records)} bars | {rate:.1f} tickers/s")

        # mootdx is TCP/non-blocking but stay polite between tickers.
        time.sleep(0.1)

    output = {
        "source": "mootdx TCP (通达信 日线 frequency=9)",
        "fetched_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "source_method": "a-stock-data skill §1.1 (mootdx)",
        "mode": "incremental" if args.incremental else "full",
        "ticker_count": len(all_bars),
        "missing_count": len(missing),
        "missing_samples": missing[:10],
        "total_bars": total_bars,
        "bars": all_bars,
    }
    OUT_PATH.write_text(
        json.dumps(output, ensure_ascii=False),
        encoding="utf-8",
    )

    print("=" * 80)
    print("mootdx daily-bar backfill complete")
    print("=" * 80)
    print(f"  Tickers in seed:     {len(codes)}")
    print(f"  Successfully fetched:{ len(all_bars)}")
    print(f"  Missing:             {len(missing)}")
    print(f"  Total bars stored:   {total_bars:,}")
    print(f"  Avg bars/ticker:     {total_bars // max(len(all_bars), 1):,}")
    print(f"  Elapsed:             {time.time() - started:.0f}s")
    print(f"  Output:              {OUT_PATH}")
    if missing:
        print(f"  Missing samples:     {missing[:5]}")


if __name__ == "__main__":
    main()
