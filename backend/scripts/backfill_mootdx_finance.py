"""
Backfill quarterly financial snapshots for all CN-listed companies in the seed.

Input:  backend/data/aichainmap_seed.json
Output: backend/data/backfill_mootdx_finance.json

Uses mootdx TCP quote API (a-stock-data skill §6.1) — connects to TDX server
on port 7709, returns 37 financial fields per symbol. Chosen because:
  - TCP protocol; no HTTP IP-blocking risk (skill priority table).
  - Single round-trip per symbol; ~0.3-0.8s each.
  - Covers balance sheet + income statement + cash flow + share structure
    in one call.

mootdx does not return EPS or ROE directly — we derive them from net income,
total shares, and net assets. The returned values are the latest quarterly
snapshot (updated_date field shows which report period).
"""

import json
import time
from pathlib import Path

from mootdx.quotes import Quotes

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
SEED_PATH = DATA_DIR / "aichainmap_seed.json"
OUT_PATH = DATA_DIR / "backfill_mootdx_finance.json"


def normalize_ticker(raw: str) -> str:
    """Strip .SH/.SZ/.BJ suffixes if present in the seed ticker."""
    return raw.split(".")[0]


def extract_finance_row(fin, ticker: str) -> dict | None:
    """Convert mootdx DataFrame (single row) into a flat dict.

    Returns None if no data. Monetary values are kept in yuan (raw); we add
    *_yi derived fields for human readability.
    """
    if fin is None or len(fin) == 0:
        return None
    row = fin.iloc[0]

    zongguben = float(row.get("zongguben") or 0)        # 总股本(股)
    liutongguben = float(row.get("liutongguben") or 0)  # 流通股本(股)
    jinglirun = float(row.get("jinglirun") or 0)         # 净利润(元)
    zhuyingshouru = float(row.get("zhuyingshouru") or 0)  # 主营收入(元)
    yingyelirun = float(row.get("yingyelirun") or 0)     # 营业利润(元)
    jingzichan = float(row.get("jingzichan") or 0)       # 净资产(元)
    meigujingzichan = float(row.get("meigujingzichan") or 0)  # 每股净资产
    zongzichan = float(row.get("zongzichan") or 0)       # 总资产(元)

    # Derived metrics
    eps = jinglirun / zongguben if zongguben > 0 else 0.0
    roe_pct = (jinglirun / jingzichan * 100) if jingzichan > 0 else 0.0
    net_margin_pct = (jinglirun / zhuyingshouru * 100) if zhuyingshouru > 0 else 0.0
    debt_ratio_pct = (
        (1 - jingzichan / zongzichan) * 100
    ) if zongzichan > 0 else 0.0

    return {
        "ticker": ticker,
        "updated_date": str(row.get("updated_date") or ""),
        "ipo_date": str(row.get("ipo_date") or ""),
        # Share structure
        "total_shares": zongguben,
        "float_shares": liutongguben,
        # Balance sheet (yuan)
        "total_assets": zongzichan,
        "net_assets": jingzichan,
        "current_assets": float(row.get("liudongzichan") or 0),
        "fixed_assets": float(row.get("gudingzichan") or 0),
        "current_liab": float(row.get("liudongfuzhai") or 0),
        "long_term_liab": float(row.get("changqifuzhai") or 0),
        "inventory": float(row.get("cunhuo") or 0),
        "accounts_recv": float(row.get("yinghouzhangkuan") or 0),
        # Income statement (yuan)
        "revenue": zhuyingshouru,
        "operating_profit": yingyelirun,
        "total_profit": float(row.get("lirunzonghe") or 0),
        "net_profit_after_tax": float(row.get("shuihoulirun") or 0),
        "net_profit": jinglirun,
        "undistributed_profit": float(row.get("weifenpeilirun") or 0),
        # Cash flow (yuan)
        "op_cash_flow": float(row.get("jingyingxianjinliu") or 0),
        "total_cash_flow": float(row.get("zongxianjinliu") or 0),
        # Per-share
        "bvps": meigujingzichan,  # 每股净资产
        # Shareholder count
        "holder_num": float(row.get("gudongrenshu") or 0),
        # Derived (human-friendly)
        "eps": round(eps, 4),
        "roe_pct": round(roe_pct, 2),
        "net_margin_pct": round(net_margin_pct, 2),
        "debt_ratio_pct": round(debt_ratio_pct, 2),
        # Derived (亿 yuan, for quick reading)
        "revenue_yi": round(zhuyingshouru / 1e8, 2),
        "net_profit_yi": round(jinglirun / 1e8, 2),
        "net_assets_yi": round(jingzichan / 1e8, 2),
        "total_assets_yi": round(zongzichan / 1e8, 2),
    }


def main():
    if not SEED_PATH.exists():
        raise SystemExit(f"seed not found: {SEED_PATH}")

    seed = json.loads(SEED_PATH.read_text(encoding="utf-8"))
    cn_tickers: dict[str, str] = {}
    for L in seed["layers"]:
        for s in L["sub_industries"]:
            for c in s["visible_companies"]:
                if c["market"] == "CN":
                    cn_tickers.setdefault(normalize_ticker(c["ticker"]), c["name"])

    codes = sorted(cn_tickers)
    print(f"Connecting to TDX TCP quote server (port 7709)...")
    client = Quotes.factory(market="std")
    print(f"Fetching finance snapshots for {len(codes)} CN tickers...")
    print()

    records: list[dict] = []
    errors: list[dict] = []
    fetched_at = time.strftime("%Y-%m-%d %H:%M:%S")
    t0 = time.time()

    for i, code in enumerate(codes, 1):
        try:
            fin = client.finance(symbol=code)
            parsed = extract_finance_row(fin, code)
            if parsed is None:
                errors.append({"ticker": code, "name": cn_tickers[code],
                               "error": "empty result"})
            else:
                parsed["seed_name"] = cn_tickers[code]
                records.append(parsed)
        except Exception as e:
            errors.append({"ticker": code, "name": cn_tickers[code],
                           "error": f"{type(e).__name__}: {e}"})

        # Progress every 25 tickers
        if i % 25 == 0 or i == len(codes):
            elapsed = time.time() - t0
            rate = i / elapsed if elapsed > 0 else 0
            eta = (len(codes) - i) / rate if rate > 0 else 0
            print(f"  [{i:>3}/{len(codes)}] ok={len(records)} err={len(errors)} "
                  f"elapsed={elapsed:>5.1f}s rate={rate:.1f}/s eta={eta:>5.1f}s")

    output = {
        "source": "mootdx TCP quote (port 7709)",
        "fetched_at": fetched_at,
        "source_method": "a-stock-data skill §6.1 (mootdx finance)",
        "count": len(records),
        "error_count": len(errors),
        "errors": errors[:20],
        "snapshots": records,
    }

    OUT_PATH.write_text(
        json.dumps(output, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # Summary
    print()
    print("=" * 80)
    print("mootdx finance backfill complete")
    print("=" * 80)
    print(f"  Total tickers attempted: {len(codes)}")
    print(f"  Successfully fetched:    {len(records)}")
    print(f"  Errors:                  {len(errors)}")
    if errors:
        print(f"    samples: {[(e['ticker'], e['name']) for e in errors[:5]]}")
    print()

    # Aggregate stats
    eps_vals = [r["eps"] for r in records if r["eps"] > 0]
    roe_vals = [r["roe_pct"] for r in records if r["roe_pct"] > 0]
    rev_vals = [r["revenue_yi"] for r in records if r["revenue_yi"] > 0]
    profit_vals = [r["net_profit_yi"] for r in records if r["net_profit_yi"] > 0]
    if eps_vals:
        eps_sorted = sorted(eps_vals)
        print(f"  EPS range:     {eps_sorted[0]:.3f} ~ {eps_sorted[-1]:.3f}  "
              f"(median {eps_sorted[len(eps_sorted)//2]:.3f})")
    if roe_vals:
        roe_sorted = sorted(roe_vals)
        print(f"  ROE% range:    {roe_sorted[0]:.2f}% ~ {roe_sorted[-1]:.2f}%  "
              f"(median {roe_sorted[len(roe_sorted)//2]:.2f}%)")
    if rev_vals:
        print(f"  Revenue range: {min(rev_vals):.0f}亿 ~ {max(rev_vals):.0f}亿")
    if profit_vals:
        print(f"  Net profit:    {min(profit_vals):.0f}亿 ~ {max(profit_vals):.0f}亿")

    # Top 5 most profitable
    by_profit = sorted(records, key=lambda r: -r["net_profit_yi"])[:5]
    print()
    print("  Top 5 by net profit:")
    for r in by_profit:
        print(f"    {r['ticker']}  {r['seed_name']:<10}  "
              f"净利润 {r['net_profit_yi']:>7.0f}亿  "
              f"营收 {r['revenue_yi']:>7.0f}亿  "
              f"ROE {r['roe_pct']:>5.1f}%  EPS {r['eps']:>5.2f}")

    print()
    print(f"Wrote: {OUT_PATH}")


if __name__ == "__main__":
    main()
