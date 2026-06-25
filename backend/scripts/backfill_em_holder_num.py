"""
Backfill shareholder-count change (股东户数变化) for all CN-listed companies.

Input:  backend/data/aichainmap_seed.json
Output: backend/data/backfill_em_holder_num.json

Uses East Money datacenter API (a-stock-data skill §4.3). Returns quarterly
holder count snapshots with sequential change — a primary "chip concentration"
signal:
  - Holder num DECREASING → chips concentrating → institutional accumulation
  - Holder num INCREASING → chips dispersing → retail distribution

This is the most actionable "筹码面" (chip structure) signal in v1 because:
  - Every listed company has at least 1 record (since 2022 disclosure rules)
  - Field shape is simple (date, holder_num, change_num, change_ratio)
  - East Money datacenter-web is on the safe list (skill priority 3)

Rate limiting: em_get() enforces >=1s + jitter. Single call per ticker for
the 20 most recent disclosure dates. 234 tickers * 1.3s = ~5 min total.

Report endpoint audit (2026-06-24):
  RPT_HOLDERNUMLATEST  - Only LATEST + previous period in 1 row (PRE_* fields).
                         Useful for current snapshot, no history.
  RPT_F10_EH_HOLDERNUM - Full history (up to 20 periods). THIS is what we use.

Field names per actual RPT_F10_EH_HOLDERNUM response (audited 2026-06-24):
  HOLDER_TOTAL_NUM     股东户数 (current period) - equivalent to skill's HOLDER_NUM
  TOTAL_NUM_RATIO      环比% (already in percent, e.g. -4.9759 = -4.98%)
  AVG_FREE_SHARES      户均流通股 (matches skill §4.3 doc, NOT in LATEST)
  AVG_HOLD_AMT         户均持股金额 (元)
  PRICE                收盘价
  CHANGEWITHLAST       较上期变化数
  END_DATE             报告期 YYYY-MM-DD (e.g. "2026-03-31")
  NOTICE_DATE          披露日 YYYY-MM-DD
  HOLD_FOCUS           筹码集中度 (sometimes populated)
  TOTAL_SHAREHOLD_NUM  总持股数

Note on skill §4.3 field-name drift:
  - skill documents `HOLDER_NUM` and `AVG_FREE_SHARES`.
  - The LATEST endpoint has HOLDER_NUM but NOT AVG_FREE_SHARES (has AVG_HOLD_NUM).
  - The HISTORY endpoint has both (HOLDER_TOTAL_NUM ~= HOLDER_NUM, AVG_FREE_SHARES).
  - Using the HISTORY endpoint here because it matches skill field names
    more closely AND gives multi-period data.
"""

import json
import random
import time
from pathlib import Path

import requests

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
SEED_PATH = DATA_DIR / "aichainmap_seed.json"
OUT_PATH = DATA_DIR / "backfill_em_holder_num.json"

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
EM_SESSION = requests.Session()
EM_SESSION.headers.update({"User-Agent": UA})
EM_MIN_INTERVAL = 1.0  # seconds; skill §防封铁律
_em_last = [0.0]

DATACENTER_URL = "https://datacenter-web.eastmoney.com/api/data/v1/get"


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


def fetch_holder_num_for(code: str) -> dict:
    """Fetch the 10 most recent holder-num disclosures for one ticker.

    Uses RPT_F10_EH_HOLDERNUM (history endpoint, up to 20 periods).
    Returns chronological list with change vs prior period.

    Field names per actual RPT_F10_EH_HOLDERNUM response (audited 2026-06-24):
      HOLDER_TOTAL_NUM     股东户数
      TOTAL_NUM_RATIO      环比% (already in percent, e.g. -4.9759 = -4.98%)
      AVG_FREE_SHARES      户均流通股
      AVG_HOLD_AMT         户均持股金额 (元)
      CHANGEWITHLAST       较上期变化数
      PRICE                收盘价
      END_DATE             报告期 YYYY-MM-DD
      NOTICE_DATE          披露日 YYYY-MM-DD
    """
    all_data = eastmoney_datacenter(
        "RPT_F10_EH_HOLDERNUM",
        filter_str=f'(SECURITY_CODE="{code}")',
        page_size=20,  # full history endpoint, take top 10
        sort_columns="END_DATE", sort_types="-1",
    )

    # Deduplicate on END_DATE (keep earliest notice per period)
    seen_periods: dict[str, dict] = {}
    for row in all_data:
        end_date = str(row.get("END_DATE", ""))[:10]
        if not end_date:
            continue
        if end_date not in seen_periods:
            seen_periods[end_date] = row

    history = []
    for end_date, row in sorted(seen_periods.items(), reverse=True)[:10]:
        holder_num = int(row.get("HOLDER_TOTAL_NUM") or 0)
        change_num_raw = row.get("CHANGEWITHLAST")
        # CHANGEWITHLAST may be None or a string like "+(-12733)"
        try:
            change_num = int(float(change_num_raw)) if change_num_raw else 0
        except (TypeError, ValueError):
            change_num = 0
        ratio_pct = float(row.get("TOTAL_NUM_RATIO") or 0)
        avg_free_shares = float(row.get("AVG_FREE_SHARES") or 0)
        avg_hold_amt = float(row.get("AVG_HOLD_AMT") or 0)
        history.append({
            "end_date": end_date,
            "notice_date": str(row.get("NOTICE_DATE", ""))[:10],
            "holder_num": holder_num,
            "change_num": change_num,
            "change_ratio_pct": round(ratio_pct, 4),
            "avg_free_shares": round(avg_free_shares, 2),
            "avg_hold_amt_yi": round(avg_hold_amt / 1e8, 4) if avg_hold_amt else 0,
            "close_price": float(row.get("PRICE") or 0),
        })

    # Derived signals
    latest = history[0] if history else None
    prior = history[1] if len(history) >= 2 else None
    trend_3p = None
    if len(history) >= 3:
        # Net ratio change over the 3 most recent periods
        trend_3p = round(
            history[0]["change_ratio_pct"]
            + history[1]["change_ratio_pct"]
            + history[2]["change_ratio_pct"],
            4,
        )

    signal = "neutral"
    if latest and prior:
        if latest["change_ratio_pct"] <= -3 and trend_3p is not None \
                and trend_3p <= -5:
            signal = "concentrating"   # 主力吸筹 chip concentration
        elif latest["change_ratio_pct"] >= 3 and trend_3p is not None \
                and trend_3p >= 5:
            signal = "dispersing"      # 筹码分散 chip dispersion

    return {
        "history_count": len(history),
        "latest_holder_num": latest["holder_num"] if latest else None,
        "latest_change_ratio_pct": latest["change_ratio_pct"] if latest else None,
        "trend_3p_sum_ratio_pct": trend_3p,
        "signal": signal,
        "history": history,
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
    print(f"Fetching holder-num change for {len(codes)} CN tickers "
          f"via EM datacenter...")
    print(f"  (rate-limited at {EM_MIN_INTERVAL}s/call, 1 call/ticker "
          f"→ ETA ~{len(codes)*EM_MIN_INTERVAL/60:.1f} min)")
    print()

    per_ticker: dict[str, dict] = {}
    errors: list[dict] = []
    fetched_at = time.strftime("%Y-%m-%d %H:%M:%S")
    t0 = time.time()

    for i, code in enumerate(codes, 1):
        try:
            data = fetch_holder_num_for(code)
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
            n_conc = sum(1 for v in per_ticker.values()
                         if v["signal"] == "concentrating")
            n_disp = sum(1 for v in per_ticker.values()
                         if v["signal"] == "dispersing")
            print(f"  [{i:>3}/{len(codes)}] ok={len(per_ticker)} "
                  f"err={len(errors)} concentrating={n_conc} "
                  f"dispersing={n_disp} elapsed={elapsed:>5.1f}s "
                  f"eta={eta:>5.1f}s")

    # ── Write JSON output FIRST (so data is safe even if aggregation fails) ─
    coverage_buckets = {"0": 0, "1-2": 0, "3-5": 0, "6-10": 0, "10+": 0}
    for v in per_ticker.values():
        n = v["history_count"]
        if n == 0:
            coverage_buckets["0"] += 1
        elif n <= 2:
            coverage_buckets["1-2"] += 1
        elif n <= 5:
            coverage_buckets["3-5"] += 1
        elif n <= 10:
            coverage_buckets["6-10"] += 1
        else:
            coverage_buckets["10+"] += 1

    signal_counts = {
        "concentrating": sum(1 for v in per_ticker.values()
                             if v["signal"] == "concentrating"),
        "dispersing": sum(1 for v in per_ticker.values()
                          if v["signal"] == "dispersing"),
        "neutral": sum(1 for v in per_ticker.values()
                       if v["signal"] == "neutral"),
    }

    output = {
        "source": "https://datacenter-web.eastmoney.com/api/data/v1/get",
        "fetched_at": fetched_at,
        "source_method": "a-stock-data skill §4.3 (holder_num_change)",
        "ticker_count": len(per_ticker),
        "error_count": len(errors),
        "rate_limit_seconds": EM_MIN_INTERVAL,
        "coverage_distribution": coverage_buckets,
        "signal_distribution": signal_counts,
        "field_name_notes": (
            "AVG_HOLD_NUM is the actual API field name (skill §4.3 "
            "incorrectly documents it as AVG_FREE_SHARES). "
            "HOLDER_NUM_RATIO is already in percentage units (e.g. -4.98 = -4.98%)."
        ),
        "errors": errors[:20],
        "tickers": per_ticker,
    }

    OUT_PATH.write_text(
        json.dumps(output, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # ── Aggregate stats (post-write; safe to fail without losing data) ─────
    # Strongest concentration / dispersion signals
    candidates_conc = [
        v for v in per_ticker.values()
        if v["latest_change_ratio_pct"] is not None
        and v["history_count"] >= 2
    ]
    top_concentrating = sorted(
        candidates_conc,
        key=lambda v: v["latest_change_ratio_pct"],
    )[:10]
    top_dispersing = sorted(
        candidates_conc,
        key=lambda v: -(v["latest_change_ratio_pct"]),
    )[:10]

    # ── Summary ─────────────────────────────────────────────────────────────
    print()
    print("=" * 80)
    print("EM holder-num change backfill complete")
    print("=" * 80)
    print(f"  Total tickers attempted:   {len(codes)}")
    print(f"  Successfully fetched:      {len(per_ticker)}")
    print(f"  Errors:                    {len(errors)}")
    if errors:
        print(f"    samples: {[(e['ticker'], e['error'][:50]) for e in errors[:3]]}")
    print()

    print("  History coverage distribution:")
    for bucket, n in coverage_buckets.items():
        pct = n / len(per_ticker) * 100 if per_ticker else 0
        print(f"    {bucket:>5} periods: {n:>4} tickers ({pct:>5.1f}%)")

    print()
    print("  Signal distribution (3-period trend):")
    for sig, n in signal_counts.items():
        pct = n / len(per_ticker) * 100 if per_ticker else 0
        print(f"    {sig:<14} {n:>4} tickers ({pct:>5.1f}%)")

    if top_concentrating:
        print()
        print("  Top 10 chip-concentration candidates (latest ratio most negative):")
        for v in top_concentrating:
            r = v["latest_change_ratio_pct"]
            n = v["latest_holder_num"]
            print(f"    {v['ticker']} {v['seed_name']:<10} "
                  f"holders={n:>7}  ratio={r:>6.2f}%  "
                  f"trend3p={v['trend_3p_sum_ratio_pct']}")

    if top_dispersing:
        print()
        print("  Top 10 chip-dispersion candidates (latest ratio most positive):")
        for v in top_dispersing:
            r = v["latest_change_ratio_pct"]
            n = v["latest_holder_num"]
            print(f"    {v['ticker']} {v['seed_name']:<10} "
                  f"holders={n:>7}  ratio={r:>6.2f}%  "
                  f"trend3p={v['trend_3p_sum_ratio_pct']}")

    print()
    print(f"Wrote: {OUT_PATH}")


if __name__ == "__main__":
    main()
