"""
Backfill concept/sector/region tags for all CN-listed companies in the seed.

Input:  backend/data/aichainmap_seed.json
Output: backend/data/backfill_em_concept_blocks.json

Uses East Money slist (a-stock-data skill §3.3) — push2.eastmoney.com with
spt=3 returns all boards (industry + concept + region mixed) for one stock
in a single call. Chosen because:
  - Single endpoint returns full concept attribution per ticker.
  - East Money mixes industry/concept/region in one list — the board name
    itself is self-explanatory ("食品饮料"=industry, "贵州板块"=region,
    "酿酒概念"=concept).
  - Provides BK code, intraday change%, and lead stock per board.

Rate limiting: em_get() enforces ≥1s + jitter between calls. At 234 tickers
this is ~5 minutes. push2 subdomain is on the IP-block-risk list (skill #18),
so we keep EM_MIN_INTERVAL at 1.0 (default) — do not tighten. If residential
IP blocking appears (HTTP 000 / empty), retry after a few minutes or switch
network.

Note: BJ (北交所) tickers (8/4 prefix) may not be supported by this endpoint.
We use market_code=0 fallback for them; failures are logged but don't abort.
"""

import json
import random
import time
from collections import Counter
from pathlib import Path

import requests

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
SEED_PATH = DATA_DIR / "aichainmap_seed.json"
OUT_PATH = DATA_DIR / "backfill_em_concept_blocks.json"

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
EM_SESSION = requests.Session()
EM_SESSION.headers.update({"User-Agent": UA})
EM_MIN_INTERVAL = 1.0  # seconds; skill §防封铁律
_em_last = [0.0]

SLIST_API = "https://push2.eastmoney.com/api/qt/slist/get"


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


def market_code_for(code: str) -> int:
    """East Money secid market prefix. 1=SH, 0=SZ/BJ. (skill §3.3)"""
    if code.startswith("6"):
        return 1
    return 0  # SZ or BJ; BJ may fail, logged in errors


def fetch_concept_blocks(code: str) -> dict:
    """Fetch industry/concept/region boards for one ticker.

    Pattern verbatim from a-stock-data skill §3.3 (eastmoney_concept_blocks).
    Returns {total, boards: [...], concept_tags: [...]}.
    """
    params = {
        "fltt": "2", "invt": "2",
        "secid": f"{market_code_for(code)}.{code}",
        "spt": "3", "pi": "0", "pz": "200", "po": "1",
        "fields": "f12,f14,f3,f128",
    }
    headers = {"Referer": "https://quote.eastmoney.com/"}
    r = em_get(SLIST_API, params=params, headers=headers, timeout=15)
    if r.status_code != 200:
        raise RuntimeError(f"HTTP {r.status_code}: {r.text[:200]}")
    d = r.json()
    diff = (d.get("data") or {}).get("diff") or {}
    items = diff.values() if isinstance(diff, dict) else diff

    boards = []
    for it in items:
        boards.append({
            "name": it.get("f14", ""),
            "code": it.get("f12", ""),
            "change_pct": it.get("f3", ""),
            "lead_stock": it.get("f128", ""),
        })
    return {
        "total": len(boards),
        "boards": boards,
        "concept_tags": [b["name"] for b in boards if b["name"]],
    }


def classify_tag(tag: str) -> str:
    """Heuristic: classify a board name as industry/concept/region/index.

    East Money mixes all types in one list. Classification is by name pattern:
    - Region: ends with "板块" (e.g., "贵州板块", "深圳板块")
    - Concept: contains "概念" (e.g., "酿酒概念", "AI概念")
    - Index: starts with "HS"/"CSI"/"中证" or contains "_" (e.g., "HS300_")
    - Industry: everything else (e.g., "食品饮料", "半导体")
    """
    if not tag:
        return "other"
    if tag.endswith("板块"):
        return "region"
    if "概念" in tag:
        return "concept"
    if (tag.startswith("HS") or tag.startswith("CSI")
            or tag.startswith("中证") or "_" in tag):
        return "index"
    return "industry"


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
    print(f"Fetching concept blocks for {len(codes)} CN tickers via EM slist...")
    print(f"  (rate-limited at {EM_MIN_INTERVAL}s/call → "
          f"ETA ~{len(codes)*EM_MIN_INTERVAL/60:.1f} min)")
    print()

    per_ticker: dict[str, dict] = {}
    errors: list[dict] = []
    fetched_at = time.strftime("%Y-%m-%d %H:%M:%S")
    t0 = time.time()

    for i, code in enumerate(codes, 1):
        try:
            data = fetch_concept_blocks(code)
            per_ticker[code] = {
                "ticker": code,
                "seed_name": cn_tickers[code],
                "subindustries": ticker_subindustries[code],
                "total_boards": data["total"],
                "boards": data["boards"],
                "concept_tags": data["concept_tags"],
            }
        except Exception as e:
            errors.append({"ticker": code, "name": cn_tickers[code],
                           "error": f"{type(e).__name__}: {str(e)[:200]}"})

        if i % 20 == 0 or i == len(codes):
            elapsed = time.time() - t0
            eta = (len(codes) - i) * EM_MIN_INTERVAL
            total_tags = sum(v["total_boards"] for v in per_ticker.values())
            print(f"  [{i:>3}/{len(codes)}] ok={len(per_ticker)} "
                  f"err={len(errors)} tags_seen={total_tags} "
                  f"elapsed={elapsed:>5.1f}s eta={eta:>5.1f}s")

    # Aggregate stats
    all_tags = [t for v in per_ticker.values() for t in v["concept_tags"]]
    tag_counter = Counter(all_tags)

    # Classify each tag
    tag_type_counter = Counter()
    for tag in all_tags:
        tag_type_counter[classify_tag(tag)] += 1

    # Per-ticker tag-type counts (for coverage analysis)
    for v in per_ticker.values():
        v["tag_type_counts"] = {
            t: sum(1 for tag in v["concept_tags"] if classify_tag(tag) == t)
            for t in ("industry", "concept", "region", "index", "other")
        }

    # Coverage distribution
    coverage_buckets = {"0": 0, "1-5": 0, "6-10": 0, "11-20": 0, "20+": 0}
    for v in per_ticker.values():
        n = v["total_boards"]
        if n == 0:
            coverage_buckets["0"] += 1
        elif n <= 5:
            coverage_buckets["1-5"] += 1
        elif n <= 10:
            coverage_buckets["6-10"] += 1
        elif n <= 20:
            coverage_buckets["11-20"] += 1
        else:
            coverage_buckets["20+"] += 1

    # Top tags per category
    top_by_type: dict[str, list] = {}
    for t in ("industry", "concept", "region"):
        top_by_type[t] = [
            {"tag": tag, "count": n}
            for tag, n in tag_counter.most_common(200)
            if classify_tag(tag) == t
        ][:15]

    output = {
        "source": "https://push2.eastmoney.com/api/qt/slist/get (spt=3)",
        "fetched_at": fetched_at,
        "source_method": "a-stock-data skill §3.3 (eastmoney_concept_blocks)",
        "ticker_count": len(per_ticker),
        "error_count": len(errors),
        "total_tag_instances": len(all_tags),
        "unique_tags": len(tag_counter),
        "avg_tags_per_ticker": (
            round(len(all_tags) / len(per_ticker), 1) if per_ticker else 0
        ),
        "tag_type_distribution": dict(tag_type_counter),
        "coverage_distribution": coverage_buckets,
        "rate_limit_seconds": EM_MIN_INTERVAL,
        "errors": errors[:20],
        "top_tags_overall": [
            {"tag": t, "count": n} for t, n in tag_counter.most_common(30)
        ],
        "top_tags_by_type": top_by_type,
        "tickers": per_ticker,
    }

    OUT_PATH.write_text(
        json.dumps(output, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # Summary
    print()
    print("=" * 80)
    print("EM slist concept attribution complete")
    print("=" * 80)
    print(f"  Total tickers attempted: {len(codes)}")
    print(f"  Successfully fetched:    {len(per_ticker)}")
    print(f"  Errors:                  {len(errors)}")
    if errors:
        print(f"    samples: "
              f"{[(e['ticker'], e['error'][:50]) for e in errors[:3]]}")
    print()
    print(f"  Total tag instances:     {len(all_tags)}")
    print(f"  Unique tags:             {len(tag_counter)}")
    if per_ticker:
        print(f"  Avg tags / ticker:       "
              f"{len(all_tags)/len(per_ticker):.1f}")
    print()
    print("  Tag type distribution:")
    for t, n in tag_type_counter.most_common():
        print(f"    {t:<10} {n:>5}")

    print()
    print("  Coverage distribution (boards per ticker):")
    for bucket, n in coverage_buckets.items():
        pct = n / len(per_ticker) * 100 if per_ticker else 0
        print(f"    {bucket:>5} boards: {n:>4} tickers ({pct:>5.1f}%)")

    print()
    print("  Top 10 industry tags:")
    for item in top_by_type["industry"][:10]:
        print(f"    {item['tag']:<20} {item['count']:>4} tickers")
    print()
    print("  Top 10 concept tags:")
    for item in top_by_type["concept"][:10]:
        print(f"    {item['tag']:<24} {item['count']:>4} tickers")
    print()
    print("  Top 8 region tags:")
    for item in top_by_type["region"][:8]:
        print(f"    {item['tag']:<12} {item['count']:>4} tickers")

    # Sample: ticker with most boards
    if per_ticker:
        most_tagged = max(per_ticker.values(), key=lambda v: v["total_boards"])
        print()
        print(f"  Most-tagged ticker: "
              f"{most_tagged['ticker']} {most_tagged['seed_name']}"
              f"  ({most_tagged['total_boards']} boards)")
        for b in most_tagged["boards"][:10]:
            ttype = classify_tag(b["name"])
            print(f"    [{ttype:<8}] {b['name']}"
                  f"  (lead: {b['lead_stock']})")

    print()
    print(f"Wrote: {OUT_PATH}")


if __name__ == "__main__":
    main()
