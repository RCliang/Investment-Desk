"""
Backfill sell-side research reports for all CN-listed companies in the seed.

Input:  backend/data/aichainmap_seed.json
Output: backend/data/backfill_em_reports.json

Uses East Money reportapi (a-stock-data skill §2.1). Chosen because:
  - Per-symbol analyst coverage with predicted EPS for 3 years.
  - reportapi.eastmoney.com is A-level public JSON (no key, no IP block in
    our tests — distinct from push2.eastmoney.com which has the #18 issue).
  - Returns rating (买入/增持/中性), target broker, publishDate.

Rate limiting: em_get() enforces ≥1s + jitter between calls (skill §防封铁律).
At 234 tickers this takes ~5 minutes. Batched runs should keep
EM_MIN_INTERVAL at 1.0 (default); tighten only if the connection is dropped.

We keep the top 5 most recent reports per ticker — enough to surface the
analyst consensus without bloating the v1 seed.
"""

import json
import random
import time
from pathlib import Path

import requests

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
SEED_PATH = DATA_DIR / "aichainmap_seed.json"
OUT_PATH = DATA_DIR / "backfill_em_reports.json"

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
EM_SESSION = requests.Session()
EM_SESSION.headers.update({"User-Agent": UA})
EM_MIN_INTERVAL = 1.0  # seconds; skill §防封铁律
_em_last = [0.0]

REPORT_API = "https://reportapi.eastmoney.com/report/list"
REPORTS_PER_TICKER = 5  # how many recent reports to keep per ticker


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


def normalize_ticker(raw: str) -> str:
    return raw.split(".")[0]


def fetch_reports_for(code: str, page_size: int = 10) -> list[dict]:
    """Fetch the most recent reports for a single ticker.

    Returns up to page_size records. Each record is trimmed to the fields
    we actually use in v1.
    """
    params = {
        "industryCode": "*", "pageSize": str(page_size), "industry": "*",
        "rating": "*", "ratingChange": "*",
        "beginTime": "2000-01-01", "endTime": "2030-01-01",
        "pageNo": "1", "fields": "", "qType": "0",
        "orgCode": "", "code": code, "rcode": "",
        "p": "1", "pageNum": "1", "pageNumber": "1",
    }
    headers = {"Referer": "https://data.eastmoney.com/"}
    r = em_get(REPORT_API, params=params, headers=headers, timeout=20)
    if r.status_code != 200:
        raise RuntimeError(f"HTTP {r.status_code}: {r.text[:200]}")
    d = r.json()
    rows = d.get("data") or []
    out = []
    for rec in rows:
        out.append({
            "publish_date": (rec.get("publishDate") or "")[:10],
            "broker": rec.get("orgSName") or "",
            "rating": rec.get("emRatingName") or "",
            "rating_change": rec.get("emRatingChangeName") or "",
            "title": rec.get("title") or "",
            "info_code": rec.get("infoCode") or "",
            "predict_this_year_eps": rec.get("predictThisYearEps"),
            "predict_next_year_eps": rec.get("predictNextYearEps"),
            "predict_next_two_year_eps": rec.get("predictNextTwoYearEps"),
            "industry": rec.get("indvInduName") or "",
        })
    return out


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
    print(f"Fetching research reports for {len(codes)} CN tickers via EM reportapi...")
    print(f"  (rate-limited at {EM_MIN_INTERVAL}s/call → ETA ~{len(codes)*EM_MIN_INTERVAL/60:.1f} min)")
    print()

    per_ticker: dict[str, dict] = {}
    errors: list[dict] = []
    fetched_at = time.strftime("%Y-%m-%d %H:%M:%S")
    t0 = time.time()

    for i, code in enumerate(codes, 1):
        try:
            reports = fetch_reports_for(code, page_size=REPORTS_PER_TICKER + 5)
            per_ticker[code] = {
                "ticker": code,
                "seed_name": cn_tickers[code],
                "subindustries": ticker_subindustries[code],
                "report_count_total": len(reports),
                "reports": reports[:REPORTS_PER_TICKER],
            }
        except Exception as e:
            errors.append({"ticker": code, "name": cn_tickers[code],
                           "error": f"{type(e).__name__}: {str(e)[:200]}"})

        if i % 20 == 0 or i == len(codes):
            elapsed = time.time() - t0
            eta = (len(codes) - i) * EM_MIN_INTERVAL
            total_reports = sum(v["report_count_total"] for v in per_ticker.values())
            print(f"  [{i:>3}/{len(codes)}] tickers_ok={len(per_ticker)} "
                  f"errs={len(errors)} reports_seen={total_reports} "
                  f"elapsed={elapsed:>5.1f}s eta={eta:>5.1f}s")

    # Aggregate stats
    all_reports = [r for v in per_ticker.values() for r in v["reports"]]
    rated = [r for r in all_reports if r["rating"]]
    with_eps = [r for r in all_reports if r["predict_this_year_eps"]]

    # Coverage distribution
    coverage_buckets = {"0": 0, "1-3": 0, "4-5": 0, "5+": 0}
    for v in per_ticker.values():
        n = v["report_count_total"]
        if n == 0: coverage_buckets["0"] += 1
        elif n <= 3: coverage_buckets["1-3"] += 1
        elif n <= 5: coverage_buckets["4-5"] += 1
        else: coverage_buckets["5+"] += 1

    output = {
        "source": "https://reportapi.eastmoney.com/report/list",
        "fetched_at": fetched_at,
        "source_method": "a-stock-data skill §2.1 (eastmoney_reports)",
        "ticker_count": len(per_ticker),
        "error_count": len(errors),
        "total_reports_kept": sum(len(v["reports"]) for v in per_ticker.values()),
        "rate_limit_seconds": EM_MIN_INTERVAL,
        "reports_per_ticker_cap": REPORTS_PER_TICKER,
        "coverage_distribution": coverage_buckets,
        "errors": errors[:20],
        "tickers": per_ticker,
    }

    OUT_PATH.write_text(
        json.dumps(output, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # Summary
    print()
    print("=" * 80)
    print("EM reportapi backfill complete")
    print("=" * 80)
    print(f"  Total tickers attempted: {len(codes)}")
    print(f"  Successfully fetched:    {len(per_ticker)}")
    print(f"  Errors:                  {len(errors)}")
    if errors:
        print(f"    samples: {[(e['ticker'], e['error'][:50]) for e in errors[:3]]}")
    print()
    print(f"  Reports kept (top {REPORTS_PER_TICKER}/ticker):  "
          f"{sum(len(v['reports']) for v in per_ticker.values())}")
    print(f"  Reports with rating:     {len(rated)}")
    print(f"  Reports with pred EPS:   {len(with_eps)}")
    print()
    print("  Coverage distribution:")
    for bucket, n in coverage_buckets.items():
        pct = n / len(per_ticker) * 100 if per_ticker else 0
        print(f"    {bucket:>4} reports: {n:>4} tickers ({pct:>5.1f}%)")

    # Rating distribution
    from collections import Counter
    rating_cnt = Counter(r["rating"] for r in rated)
    print()
    print("  Rating distribution (top 8):")
    for rating, n in rating_cnt.most_common(8):
        print(f"    {rating:<12} {n:>4}")

    # Sample: most-covered ticker
    if per_ticker:
        most_covered = max(per_ticker.values(), key=lambda v: v["report_count_total"])
        print()
        print(f"  Most-covered ticker: {most_covered['ticker']} {most_covered['seed_name']}"
              f"  ({most_covered['report_count_total']} reports)")
        for r in most_covered["reports"][:3]:
            print(f"    {r['publish_date']} | {r['broker']:<12} | {r['rating']:<8} | "
                  f"predEPS={r['predict_this_year_eps']} | {r['title'][:50]}")

    print()
    print(f"Wrote: {OUT_PATH}")


if __name__ == "__main__":
    main()
