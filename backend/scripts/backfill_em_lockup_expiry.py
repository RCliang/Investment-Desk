"""
Backfill lockup expiry (限售解禁) for all CN-listed companies in the seed.

Input:  backend/data/aichainmap_seed.json
Output: backend/data/backfill_em_lockup_expiry.json

Uses East Money datacenter API (a-stock-data skill §3.6). Returns:
  - history:  past lockup expiry events (unlimited lookback, capped at 15)
  - upcoming: next-90-day lockup expiry events (forward risk signal)

This is the single most important "structural risk signal" for v1:
  - Every company has either data or explicit "no upcoming expiry"
  - Field shape is simple (date, type, shares, ratio)
  - East Money datacenter-web is on the safe list (skill priority 3,
    low IP-block risk)

Rate limiting: em_get() enforces ≥1s + jitter. Single call per ticker for
history, single call for upcoming = 2 calls × 1.3s × 234 ≈ 10 min total.
"""

import json
import random
import time
from datetime import datetime, timedelta
from pathlib import Path

import requests

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
SEED_PATH = DATA_DIR / "aichainmap_seed.json"
OUT_PATH = DATA_DIR / "backfill_em_lockup_expiry.json"

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
EM_SESSION = requests.Session()
EM_SESSION.headers.update({"User-Agent": UA})
EM_MIN_INTERVAL = 1.0  # seconds; skill §防封铁律
_em_last = [0.0]

DATACENTER_URL = "https://datacenter-web.eastmoney.com/api/data/v1/get"
FORWARD_DAYS = 90  # look-forward window for upcoming expiries


def em_get(url: str, params: dict | None = None, headers: dict | None = None,
           timeout: int = 15, **kwargs):
    """East Money unified request entry — auto-throttle + session reuse.

    Verbatim from a-stock-data skill §Prerequisites.
    """
    wait = EM_MIN_INTERVAL - (time.time() - _em_last[0])
    if wait > 0:
        time.sleep(wait + random.uniform(0.1, 0.5))
    try:
        return EM_SESSION.get(url, params=params, headers=headers,
                              timeout=timeout, **kwargs)
    finally:
        _em_last[0] = time.time()


def eastmoney_datacenter(report_name: str, filter_str: str = "",
                         page_size: int = 50,
                         sort_columns: str = "",
                         sort_types: str = "-1") -> list[dict]:
    """East Money datacenter unified query. Verbatim from skill §Prerequisites."""
    params = {
        "reportName": report_name, "columns": "ALL",
        "filter": filter_str, "pageNumber": "1", "pageSize": str(page_size),
        "sortColumns": sort_columns, "sortTypes": sort_types,
        "source": "WEB", "client": "WEB",
    }
    r = em_get(DATACENTER_URL, params=params, timeout=15)
    if r.status_code != 200:
        raise RuntimeError(f"HTTP {r.status_code}: {r.text[:200]}")
    d = r.json()
    if d.get("result") and d["result"].get("data"):
        return d["result"]["data"]
    return []


def normalize_ticker(raw: str) -> str:
    return raw.split(".")[0]


def fetch_lockup_for(code: str, asof_date: str) -> dict:
    """Fetch all lockup expiry events for one ticker, then split by date.

    Single API call (filter only on SECURITY_CODE), client-side partition
    into history (date < asof) vs upcoming (asof ≤ date ≤ asof+90d).

    Field names per actual EM datacenter response (audited 2026-06-24):
      FREE_SHARES_TYPE  解禁股本类型 (e.g. "定向增发机构配售股份")
      FREE_SHARES       解禁股数 (万股)
      FREE_RATIO        占解禁前流通股本比例 (0-1 decimal → ×100 for %)
      LIFT_MARKET_CAP   解禁市值 (万元)
      TOTALSHARES_RATIO 占总股本比例 (0-1 decimal → ×100 for %)

    Note: skill §3.6 documents LIMITED_STOCK_TYPE / FREE_SHARES_NUM, which
    don't match the actual API response. Using real field names here.
    """
    end_date = (
        datetime.strptime(asof_date, "%Y-%m-%d") + timedelta(days=FORWARD_DAYS)
    ).strftime("%Y-%m-%d")

    all_data = eastmoney_datacenter(
        "RPT_LIFT_STAGE",
        filter_str=f'(SECURITY_CODE="{code}")',
        page_size=50,
        sort_columns="FREE_DATE", sort_types="-1",
    )

    history = []
    upcoming = []
    for row in all_data:
        date_str = str(row.get("FREE_DATE", ""))[:10]
        if not date_str:
            continue
        event = {
            "date": date_str,
            "type": row.get("FREE_SHARES_TYPE", "") or "",
            "shares_wan": row.get("FREE_SHARES", 0),              # 万股
            "ratio_pct": round(
                float(row.get("FREE_RATIO") or 0) * 100, 4),      # 0.27 → 27.37%
            "mcap_wan": row.get("LIFT_MARKET_CAP", 0),            # 万元
            "total_shares_ratio_pct": round(
                float(row.get("TOTALSHARES_RATIO") or 0) * 100, 4),
        }
        if date_str < asof_date:
            history.append(event)
        elif asof_date <= date_str <= end_date:
            upcoming.append(event)

    return {
        "history_count": len(history),
        "upcoming_count": len(upcoming),
        "history": history,
        "upcoming": upcoming,
    }


def main():
    if not SEED_PATH.exists():
        raise SystemExit(f"seed not found: {SEED_PATH}")

    seed = json.loads(SEED_PATH.read_text(encoding="utf-8"))
    cn_tickers: dict[str, str] = {}
    ticker_subindustries: dict[str, list[str]] = {}
    for L in seed["layers"]:
        for s in L["sub_industries"]:
            for c in s["visible_companies"]:
                if c["market"] == "CN":
                    norm = normalize_ticker(c["ticker"])
                    cn_tickers.setdefault(norm, c["name"])
                    ticker_subindustries.setdefault(norm, []).append(s["group_id"])

    codes = sorted(cn_tickers)
    asof = time.strftime("%Y-%m-%d")
    print(f"Fetching lockup expiry for {len(codes)} CN tickers via EM datacenter...")
    print(f"  as-of date: {asof}  forward window: {FORWARD_DAYS} days")
    print(f"  (rate-limited at {EM_MIN_INTERVAL}s/call, 1 call/ticker "
          f"→ ETA ~{len(codes)*EM_MIN_INTERVAL/60:.1f} min)")
    print()

    per_ticker: dict[str, dict] = {}
    errors: list[dict] = []
    fetched_at = time.strftime("%Y-%m-%d %H:%M:%S")
    t0 = time.time()

    for i, code in enumerate(codes, 1):
        try:
            data = fetch_lockup_for(code, asof)
            per_ticker[code] = {
                "ticker": code,
                "seed_name": cn_tickers[code],
                "subindustries": ticker_subindustries[code],
                **data,
            }
        except Exception as e:
            errors.append({"ticker": code, "name": cn_tickers[code],
                           "error": f"{type(e).__name__}: {str(e)[:200]}"})

        if i % 20 == 0 or i == len(codes):
            elapsed = time.time() - t0
            eta = (len(codes) - i) * EM_MIN_INTERVAL
            total_up = sum(v["upcoming_count"] for v in per_ticker.values())
            print(f"  [{i:>3}/{len(codes)}] ok={len(per_ticker)} "
                  f"err={len(errors)} upcoming_events={total_up} "
                  f"elapsed={elapsed:>5.1f}s eta={eta:>5.1f}s")

    # ── Aggregate stats ─────────────────────────────────────────────────────
    tickers_with_upcoming = [
        v for v in per_ticker.values() if v["upcoming_count"] > 0
    ]
    total_upcoming_events = sum(v["upcoming_count"] for v in tickers_with_upcoming)
    total_upcoming_shares = sum(
        sum(u["shares"] for u in v["upcoming"])
        for v in tickers_with_upcoming
    )

    # Heaviest upcoming dilution (by ratio %)
    all_upcoming_flattened = [
        (v["ticker"], v["seed_name"], u)
        for v in tickers_with_upcoming for u in v["upcoming"]
    ]
    heaviest_dilution = sorted(
        all_upcoming_flattened,
        key=lambda x: -(float(x[2].get("ratio_pct") or 0))
    )[:10]

    # History distribution
    hist_counts = [v["history_count"] for v in per_ticker.values()]
    coverage_buckets = {"0": 0, "1-3": 0, "4-10": 0, "10+": 0}
    for n in hist_counts:
        if n == 0:
            coverage_buckets["0"] += 1
        elif n <= 3:
            coverage_buckets["1-3"] += 1
        elif n <= 10:
            coverage_buckets["4-10"] += 1
        else:
            coverage_buckets["10+"] += 1

    output = {
        "source": "https://datacenter-web.eastmoney.com/api/data/v1/get",
        "fetched_at": fetched_at,
        "asof_date": asof,
        "forward_days": FORWARD_DAYS,
        "source_method": "a-stock-data skill §3.6 (lockup_expiry)",
        "ticker_count": len(per_ticker),
        "error_count": len(errors),
        "tickers_with_upcoming": len(tickers_with_upcoming),
        "total_upcoming_events": total_upcoming_events,
        "rate_limit_seconds": EM_MIN_INTERVAL,
        "coverage_distribution": coverage_buckets,
        "errors": errors[:20],
        "heaviest_upcoming_dilution_top10": [
            {
                "ticker": t,
                "name": name,
                "date": u["date"],
                "type": u["type"],
                "shares": u["shares"],
                "ratio_pct": u["ratio_pct"],
            }
            for t, name, u in heaviest_dilution
        ],
        "tickers": per_ticker,
    }

    OUT_PATH.write_text(
        json.dumps(output, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # ── Summary ─────────────────────────────────────────────────────────────
    print()
    print("=" * 80)
    print("EM lockup expiry backfill complete")
    print("=" * 80)
    print(f"  Total tickers attempted:   {len(codes)}")
    print(f"  Successfully fetched:      {len(per_ticker)}")
    print(f"  Errors:                    {len(errors)}")
    if errors:
        print(f"    samples: {[(e['ticker'], e['error'][:50]) for e in errors[:3]]}")
    print()
    print(f"  Tickers with upcoming expiry (next {FORWARD_DAYS}d): "
          f"{len(tickers_with_upcoming)} "
          f"({len(tickers_with_upcoming)/max(len(per_ticker),1)*100:.1f}%)")
    print(f"  Total upcoming events:     {total_upcoming_events}")

    print()
    print("  History coverage distribution:")
    for bucket, n in coverage_buckets.items():
        pct = n / len(per_ticker) * 100 if per_ticker else 0
        print(f"    {bucket:>4} past events: {n:>4} tickers ({pct:>5.1f}%)")

    if heaviest_dilution:
        print()
        print(f"  Top 10 heaviest upcoming dilutions (by ratio %):")
        for t, name, u in heaviest_dilution[:10]:
            ratio = float(u.get("ratio_pct") or 0)
            print(f"    {t} {name:<10}  {u['date']}  "
                  f"ratio={ratio:>5.2f}%  type={u['type'][:24]}")

    print()
    print(f"Wrote: {OUT_PATH}")


if __name__ == "__main__":
    main()
