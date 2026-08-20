"""
Backfill per-ticker daily fund flow (个股资金流, 主力/超大单/大单/中单/小单)
for the sector-rotation strategy pool.

Input:  backend/data/sector_pool.json (8 sectors, ~70 tickers)
Output: backend/data/backfill_em_fund_flow.json

Primary source: East Money push2his fflow/daykline API (a-stock-data
skill §4.5), ~120 trading days per call.
Fallback source: Sina MoneyFlow history (vip.stock.finance.sina.com.cn,
~200 trading days, num≤200/page). push2his has connection-level risk
control on some mainland residential IPs (skill issue #18, observed:
instant RST / HTTP 000 while datacenter-web works); when EM refuses,
the fetcher falls back to Sina per ticker and records the source.

Units: all monetary fields are 元 (yuan) at source — stored raw to stay
consistent with chain_daily_bars.amount.

Mapping (both sources → same row schema):
  EM klines CSV:  date, main, small, mid, large, super (f51-f56)
  Sina fields:    r0_net(超大), r1_net(大), r2_net(中), r3_net(小);
                  main = r0_net + r1_net (东财"主力"定义)
Sina's order-size cutpoints differ slightly from EM's; the rotation
factors use ratios/persistence/acceleration, robust to the difference.
A per-ticker `source` field travels through to chain_fund_flow_daily.source
so mixed-source history is visible (avoid mixing within an analysis
window where possible).

Rate limiting: 1.5s + jitter between calls. 70 tickers ≈ 2 min.
Failures retry 3× with exponential backoff; tickers still failing are
logged to .errors and skipped (next day's incremental heals the gap).

Field audit (skill §4.5, klines CSV order):
  parts[0] date, parts[1] main_net, parts[2] small_net, parts[3] mid_net,
  parts[4] large_net, parts[5] super_net
"""

import argparse
import json
import random
import time
from pathlib import Path

import requests

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
POOL_PATH = Path(__file__).resolve().parent.parent / "app" / "services" / "quant" / "sector_pool.json"
OUT_PATH = DATA_DIR / "backfill_em_fund_flow.json"

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
EM_SESSION = requests.Session()
EM_SESSION.headers.update({"User-Agent": UA})
EM_MIN_INTERVAL = 1.5  # seconds; push2his is touchier than datacenter (skill #18)
_em_last = [0.0]

FFLOW_URL = "https://push2his.eastmoney.com/api/qt/stock/fflow/daykline/get"
FIELDS2 = "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61,f62,f63,f64,f65"

SINA_URL = ("https://vip.stock.finance.sina.com.cn/quotes_service/api/"
            "json_v2.php/MoneyFlow.ssl_qsfx_lscjfb")
SINA_PAGE = 200  # rows per call (API cap; 200 verified working)

RETRIES = 3

# Circuit breaker: push2his IP blocks are all-or-nothing — after this many
# consecutive EM failures, skip EM for the rest of the process and go
# straight to Sina (saves ~8s of retry backoff per ticker).
_EM_FAIL_STREAK_LIMIT = 3
_em_fail_streak = [0]


def _em_available() -> bool:
    return _em_fail_streak[0] < _EM_FAIL_STREAK_LIMIT


def reset_em_circuit() -> None:
    """Re-enable EM for this process (e.g. at the start of a new run)."""
    _em_fail_streak[0] = 0


def em_get(url: str, params: dict | None = None, headers: dict | None = None,
           timeout: int = 15, **kwargs):
    """East Money unified request entry — auto-throttle + session reuse."""
    wait = EM_MIN_INTERVAL - (time.time() - _em_last[0])
    if wait > 0:
        time.sleep(wait + random.uniform(0.1, 0.4))
    try:
        return EM_SESSION.get(url, params=params, headers=headers,
                              timeout=timeout, **kwargs)
    finally:
        _em_last[0] = time.time()


def market_prefix(code: str) -> int:
    """push2his secid market: 1 = SH (6xxxxx incl. 688 STAR), 0 = SZ (everything else)."""
    return 1 if code.startswith("6") else 0


def sina_symbol(code: str) -> str:
    return ("sh" if code.startswith("6") else "sz") + code


def _parse_kline(line: str) -> dict | None:
    """One CSV kline row → dict. Fields per skill §4.5 audit."""
    parts = line.split(",")
    if len(parts) < 6:
        return None

    def _f(v: str) -> float:
        return float(v) if v not in ("-", "") else 0.0

    return {
        "date": parts[0],
        "main_net": _f(parts[1]),      # 主力净流入 (元)
        "small_net": _f(parts[2]),     # 小单净流入 (元)
        "mid_net": _f(parts[3]),       # 中单净流入 (元)
        "large_net": _f(parts[4]),     # 大单净流入 (元)
        "super_net": _f(parts[5]),     # 超大单净流入 (元)
    }


def _fetch_em(code: str, lmt: int) -> list[dict]:
    """EM push2his: last `lmt` days, chronological. Raises on failure."""
    if not _em_available():
        raise RuntimeError("EM circuit open (consecutive failures)")
    params = {
        "secid": f"{market_prefix(code)}.{code}",
        "fields1": "f1,f2,f3,f7",
        "fields2": FIELDS2,
        "lmt": str(lmt),
    }
    headers = {
        "User-Agent": UA,
        "Referer": "https://quote.eastmoney.com/",
        "Origin": "https://quote.eastmoney.com",
    }

    last_err: Exception | None = None
    for attempt in range(RETRIES):
        try:
            r = em_get(FFLOW_URL, params=params, headers=headers, timeout=15)
            if r.status_code != 200:
                raise RuntimeError(f"HTTP {r.status_code}")
            klines = r.json().get("data", {}).get("klines", [])
            rows = [p for p in (_parse_kline(line) for line in klines) if p]
            _em_fail_streak[0] = 0
            return rows
        except Exception as e:  # noqa: BLE001 — retry any transport/parse error
            last_err = e
            time.sleep(2 ** attempt + random.uniform(0.5, 1.5))
    _em_fail_streak[0] += 1
    raise RuntimeError(f"failed after {RETRIES} attempts: {last_err}")


def _fetch_sina(code: str, lmt: int) -> list[dict]:
    """Sina MoneyFlow history: last `lmt` days, chronological.

    Rows come newest-first, num≤200 per page. Raises on failure.
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "https://finance.sina.com.cn/",
    }
    collected: list[dict] = []
    page = 1
    while len(collected) < lmt:
        wait = EM_MIN_INTERVAL - (time.time() - _em_last[0])
        if wait > 0:
            time.sleep(wait)
        try:
            r = EM_SESSION.get(
                SINA_URL,
                params={"page": page, "num": SINA_PAGE, "sort": "opendate",
                        "asc": 0, "daima": sina_symbol(code)},
                headers=headers, timeout=15)
            _em_last[0] = time.time()
            if r.status_code != 200:
                raise RuntimeError(f"HTTP {r.status_code}")
            rows = r.json()
        except json.JSONDecodeError:
            # Empty symbol / no history → empty list, not an error.
            rows = []
        if not rows:
            break
        for row in rows:
            try:
                super_net = float(row["r0_net"])
                large_net = float(row["r1_net"])
                mid_net = float(row["r2_net"])
                small_net = float(row["r3_net"])
            except (KeyError, TypeError, ValueError):
                continue
            collected.append({
                "date": str(row.get("opendate", ""))[:10],
                "main_net": super_net + large_net,
                "super_net": super_net,
                "large_net": large_net,
                "mid_net": mid_net,
                "small_net": small_net,
            })
        if len(rows) < SINA_PAGE:
            break
        page += 1
    collected.reverse()  # → chronological
    # Dedup on date (page overlap safety).
    seen: set[str] = set()
    out = []
    for r in collected:
        if r["date"] and r["date"] not in seen:
            seen.add(r["date"])
            out.append(r)
    return out


def fetch_fund_flow(code: str, lmt: int = 120) -> tuple[list[dict], str]:
    """Fetch fund flow with source fallback: EM first, Sina on EM failure.

    Returns (rows_chronological, source_name). Raises only when BOTH
    sources fail.
    """
    try:
        return _fetch_em(code, lmt), "eastmoney"
    except Exception as em_err:  # noqa: BLE001 — fall back to Sina
        try:
            return _fetch_sina(code, lmt), "sina"
        except Exception as sina_err:  # noqa: BLE001
            raise RuntimeError(
                f"EM failed ({em_err}); Sina failed ({sina_err})") from None


def main():
    ap = argparse.ArgumentParser(description="Backfill EM per-ticker fund flow")
    ap.add_argument("--incremental", action="store_true",
                    help="fetch only the last 5 days (daily refresh mode)")
    ap.add_argument("--tickers", nargs="*", default=None,
                    help="explicit tickers (default: full sector pool)")
    args = ap.parse_args()

    pool = json.loads(POOL_PATH.read_text(encoding="utf-8"))
    names: dict[str, str] = {}
    sectors: dict[str, list[str]] = {}
    for sector, cfg in pool.items():
        sectors[sector] = [t for t, _n in cfg["stocks"]]
        for t, n in cfg["stocks"]:
            names.setdefault(t, n)

    codes = sorted(set(args.tickers) if args.tickers else names.keys())
    lmt = 5 if args.incremental else 120

    print(f"Fetching fund flow (lmt={lmt}d) for {len(codes)} tickers "
          f"from {FFLOW_URL}")
    print(f"  rate-limited at {EM_MIN_INTERVAL}s/call → "
          f"ETA ~{len(codes) * EM_MIN_INTERVAL / 60:.1f} min")
    print()

    per_ticker: dict[str, dict] = {}
    errors: list[dict] = []
    fetched_at = time.strftime("%Y-%m-%d %H:%M:%S")
    t0 = time.time()
    reset_em_circuit()

    for i, code in enumerate(codes, 1):
        try:
            history, source = fetch_fund_flow(code, lmt=lmt)
            per_ticker[code] = {
                "ticker": code,
                "name": names.get(code, ""),
                "sectors": [s for s, ts in sectors.items() if code in ts],
                "source": source,
                "history_count": len(history),
                "history": history,
            }
        except Exception as e:  # noqa: BLE001 — log and continue with next ticker
            errors.append({"ticker": code, "name": names.get(code, ""),
                           "error": f"{type(e).__name__}: {str(e)[:200]}"})

        if i % 10 == 0 or i == len(codes):
            elapsed = time.time() - t0
            eta = (len(codes) - i) * EM_MIN_INTERVAL
            total_rows = sum(v["history_count"] for v in per_ticker.values())
            print(f"  [{i:>3}/{len(codes)}] ok={len(per_ticker)} err={len(errors)} "
                  f"rows={total_rows} elapsed={elapsed:>5.1f}s eta={eta:>5.1f}s")

    src_counts: dict[str, int] = {}
    for v in per_ticker.values():
        src_counts[v["source"]] = src_counts.get(v["source"], 0) + 1

    output = {
        "source": FFLOW_URL,
        "fetched_at": fetched_at,
        "source_method": "a-stock-data skill §4.5 (EM) + Sina MoneyFlow fallback",
        "mode": "incremental" if args.incremental else "full",
        "ticker_count": len(per_ticker),
        "error_count": len(errors),
        "rows_total": sum(v["history_count"] for v in per_ticker.values()),
        "source_distribution": src_counts,
        "rate_limit_seconds": EM_MIN_INTERVAL,
        "field_name_notes": (
            "EM klines CSV order: date, main_net, small_net, mid_net, "
            "large_net, super_net. Sina: main = r0_net(超大) + r1_net(大). "
            "All monetary fields in 元. Per-ticker source recorded."
        ),
        "errors": errors[:20],
        "tickers": per_ticker,
    }

    OUT_PATH.write_text(
        json.dumps(output, ensure_ascii=False),
        encoding="utf-8",
    )

    print()
    print("=" * 80)
    print("EM fund flow backfill complete")
    print("=" * 80)
    print(f"  Tickers fetched:  {len(per_ticker)}/{len(codes)}")
    print(f"  Errors:           {len(errors)}")
    if errors:
        for e in errors[:5]:
            print(f"    {e['ticker']} {e['name']}: {e['error'][:80]}")
    print(f"  Rows total:       {output['rows_total']}")
    print(f"  Wrote: {OUT_PATH}")


if __name__ == "__main__":
    main()
