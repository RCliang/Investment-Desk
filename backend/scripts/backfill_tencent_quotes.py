"""
Backfill real-time market quotes for all CN-listed companies in the seed.

Input:  backend/data/aichainmap_seed.json
Output: backend/data/backfill_tencent_quotes.json

Uses the Tencent Finance batch quote API (a-stock-data skill §1.2). Chosen
because:
  - One HTTP request covers all 234 tickers (Tencent accepts comma-joined
    sh/sz/bj-prefixed codes, no documented ceiling, tested up to ~500).
  - Does not share East Money's IP-blocking behavior (skill priority table).
  - Returns PE_TTM, PE_static, PB, market cap, turnover, limit prices in
    a single payload — exactly the v1 investable data shape.

The Tencent response is GBK-encoded and `~`-separated (88 fields per code).
Field indices are calibrated to the a-stock-data skill's 2026-05-03 audit.
"""

import json
import time
import urllib.request
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
SEED_PATH = DATA_DIR / "aichainmap_seed.json"
OUT_PATH = DATA_DIR / "backfill_tencent_quotes.json"

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"


def normalize_ticker(raw: str) -> str:
    """Strip exchange suffixes (.SH/.SZ/.BJ) — seed stores them verbatim from
    aichainmap dump (e.g., 002594.SZ). Tencent wants the bare 6-digit code."""
    return raw.split(".")[0]


def prefix_for(code: str) -> str:
    """6位代码 → 腾讯市场前缀 (a-stock-data skill §Prerequisites)."""
    if code.startswith(("6", "9")):
        return "sh"
    if code.startswith(("8", "4")):
        return "bj"
    return "sz"


def tencent_quote(codes: list[str]) -> dict[str, dict]:
    """
    Batch quote via Tencent Finance.  Verbatim pattern from skill §1.2.
    Returns {code: {name, price, pe_ttm, pe_static, pb, mcap_yi, ...}}.
    """
    prefixed = [f"{prefix_for(c)}{c}" for c in codes]
    # Tencent allows long comma-joined queries; split into chunks of 100
    # to stay under any URL-length ceiling and keep responses manageable.
    result: dict[str, dict] = {}
    for i in range(0, len(prefixed), 100):
        chunk = prefixed[i : i + 100]
        url = "https://qt.gtimg.cn/q=" + ",".join(chunk)
        req = urllib.request.Request(url)
        req.add_header("User-Agent", UA)
        resp = urllib.request.urlopen(req, timeout=15)
        data = resp.read().decode("gbk")

        for line in data.strip().split(";"):
            line = line.strip()
            if not line or "=" not in line or '"' not in line:
                continue
            key = line.split("=")[0].split("_")[-1]
            vals = line.split('"')[1].split("~")
            if len(vals) < 53:
                continue
            code = key[2:]  # strip sh/sz/bj prefix
            result[code] = _parse_tencent_row(code, vals)
        # polite pause between chunks (not strictly required)
        if i + 100 < len(prefixed):
            time.sleep(0.3)
    return result


def _parse_tencent_row(code: str, vals: list[str]) -> dict:
    """Convert one Tencent `~`-separated row into a structured dict.

    Indices per a-stock-data skill §1.2 (audited 2026-05-03).
    """
    def _f(idx: int) -> float:
        try:
            v = vals[idx]
            return float(v) if v else 0.0
        except (IndexError, ValueError):
            return 0.0

    return {
        "ticker": code,
        "name": vals[1],
        "price": _f(3),
        "last_close": _f(4),
        "open": _f(5),
        "change_amt": _f(31),
        "change_pct": _f(32),
        "high": _f(33),
        "low": _f(34),
        "amount_wan": _f(37),       # 成交额(万)
        "turnover_pct": _f(38),
        "pe_ttm": _f(39),
        "amplitude_pct": _f(43),
        "mcap_yi": _f(44),          # 总市值(亿)
        "float_mcap_yi": _f(45),    # 流通市值(亿)
        "pb": _f(46),
        "limit_up": _f(47),
        "limit_down": _f(48),
        "vol_ratio": _f(49),
        "pe_static": _f(52),
    }


def main():
    if not SEED_PATH.exists():
        raise SystemExit(f"seed not found: {SEED_PATH}")

    seed = json.loads(SEED_PATH.read_text(encoding="utf-8"))

    # Build ticker → seed-name map (CN only)
    cn_tickers: dict[str, str] = {}
    ticker_subindustries: dict[str, list[str]] = {}
    for L in seed["layers"]:
        for s in L["sub_industries"]:
            for c in s["visible_companies"]:
                if c["market"] == "CN":
                    norm = normalize_ticker(c["ticker"])
                    cn_tickers.setdefault(norm, c["name"])
                    ticker_subindustries.setdefault(norm, []).append(
                        s["group_id"]
                    )

    codes = sorted(cn_tickers)
    print(f"Fetching quotes for {len(codes)} CN tickers via Tencent batch API...")
    quotes = tencent_quote(codes)

    # Enrich and assemble records
    fetched_at = time.strftime("%Y-%m-%d %H:%M:%S")
    records = []
    missing = []
    for code in codes:
        if code not in quotes:
            missing.append(code)
            continue
        q = quotes[code]
        q["seed_name"] = cn_tickers[code]
        q["subindustries"] = ticker_subindustries[code]
        records.append(q)

    output = {
        "source": "https://qt.gtimg.cn/q=",
        "fetched_at": fetched_at,
        "source_method": "a-stock-data skill §1.2 (Tencent batch quote)",
        "count": len(records),
        "missing_count": len(missing),
        "missing_samples": missing[:10],
        "quotes": records,
    }

    OUT_PATH.write_text(
        json.dumps(output, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # Summary
    print("=" * 80)
    print("Tencent quote backfill complete")
    print("=" * 80)
    print(f"  Total CN tickers in seed: {len(codes)}")
    print(f"  Successfully fetched:     {len(records)}")
    print(f"  Missing (delisted / suspended?): {len(missing)}")
    if missing:
        print(f"    samples: {missing[:5]}")
    print()

    # Aggregate stats on the fetched set
    pe_ttm = [q["pe_ttm"] for q in records if q["pe_ttm"] > 0]
    pb = [q["pb"] for q in records if q["pb"] > 0]
    mcap = [q["mcap_yi"] for q in records if q["mcap_yi"] > 0]
    if pe_ttm:
        print(f"  PE_TTM range:  {min(pe_ttm):.1f} ~ {max(pe_ttm):.1f}  "
              f"(median ~{sorted(pe_ttm)[len(pe_ttm)//2]:.1f})")
    if pb:
        print(f"  PB range:      {min(pb):.1f} ~ {max(pb):.1f}  "
              f"(median ~{sorted(pb)[len(pb)//2]:.1f})")
    if mcap:
        print(f"  Market cap:    {min(mcap):.0f}亿 ~ {max(mcap):.0f}亿  "
              f"(total {sum(mcap):.0f}亿)")

    # Top 5 by market cap
    by_mcap = sorted(records, key=lambda q: -q["mcap_yi"])[:5]
    print()
    print("  Top 5 by market cap:")
    for q in by_mcap:
        print(f"    {q['ticker']}  {q['name']:<10}  "
              f"市值 {q['mcap_yi']:>6.0f}亿  PE {q['pe_ttm']:>6.1f}  PB {q['pb']:>5.1f}")

    # Smallest 5
    by_mcap_asc = sorted([q for q in records if q["mcap_yi"] > 0],
                          key=lambda q: q["mcap_yi"])[:5]
    print()
    print("  Smallest 5 by market cap:")
    for q in by_mcap_asc:
        print(f"    {q['ticker']}  {q['name']:<10}  "
              f"市值 {q['mcap_yi']:>6.0f}亿  PE {q['pe_ttm']:>6.1f}  PB {q['pb']:>5.1f}")

    print()
    print(f"Wrote: {OUT_PATH}")


if __name__ == "__main__":
    main()
