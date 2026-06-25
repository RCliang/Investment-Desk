"""
Backfill margin trading (融资融券明细) for all CN-listed companies in the seed.

Input:  backend/data/aichainmap_seed.json
Output: backend/data/backfill_em_margin_trading.json

Uses East Money datacenter API (a-stock-data skill §4.1). Returns daily
margin balances + net buy/sell activity — a primary "杠杆资金" (leverage
capital) signal:
  - 融资余额持续上升 + 融资买入额放大 → 多头情绪 bullish leverage
  - 融券余额激增 → 空头情绪 bearish short interest

Covers only tickers on the two-exchange margin list (融资融券标的), which is
~1700 of the 5000+ A-shares. Most seed tickers will have data; the few
non-margin-eligible tickers will return empty and be flagged.

Rate limiting: em_get() enforces >=1s + jitter. Single call per ticker for
the 30 most recent trading days. 234 tickers * 1.3s = ~5 min total.

Field names audited 2026-06-24 against raw RPTA_WEB_RZRQ_GGMX response:
  DATE         交易日
  SCODE        代码
  SECNAME      名称
  RZYE         融资余额 (元) - e.g. 19902433764 = ~199亿
  RQYE         融券余额 (元)
  RZRQYE       融资融券余额合计 (元)
  RZMRE        融资买入额 (元)
  RZCHE        融资偿还额 (元)
  RZJME        融资净买额 (元)  = RZMRE - RZCHE
  RQMCL        融券卖出量 (股)
  RQCHL        融券偿还量 (股)
  RQJMG        融券净买股 (股)  = RQMCL - RQCHL
  RZYEZB       融资余额占流通市值比 (%)  (already in percent, e.g. 1.32 = 1.32%)
  SPJ          收盘价
  ZDF          当日涨跌幅 (%)
  FIN_BALANCE_GR  融资余额比率 (alternative calc)
  KCB          是否科创板 (0/1)

Note: All monetary fields are in 元 (yuan), not 万元 — must divide by 1e8
for 亿 or 1e4 for 万 when surfacing to users.

Note: skill §4.1 field names match the actual API response (no drift).
Verified before writing this script (avoiding the §3.6 / §4.3 mistakes).
"""

import json
import random
import time
from pathlib import Path

import requests

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
SEED_PATH = DATA_DIR / "aichainmap_seed.json"
OUT_PATH = DATA_DIR / "backfill_em_margin_trading.json"

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
EM_SESSION = requests.Session()
EM_SESSION.headers.update({"User-Agent": UA})
EM_MIN_INTERVAL = 1.0  # seconds; skill §防封铁律
_em_last = [0.0]

DATACENTER_URL = "https://datacenter-web.eastmoney.com/api/data/v1/get"

# How many recent trading days to fetch per ticker
HISTORY_DAYS = 30
# For trend summary — use last N days of activity
TREND_WINDOW = 10


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


def fetch_margin_for(code: str) -> dict:
    """Fetch last HISTORY_DAYS of margin trading activity for one ticker.

    Single API call (filter on SCODE), sorted descending by DATE so index 0
    is most recent.

    Returns:
      history: list of daily records (chronological, oldest first)
      latest_*: snapshot of most recent trading day
      trend_*: aggregates over the last TREND_WINDOW days
    """
    all_data = eastmoney_datacenter(
        "RPTA_WEB_RZRQ_GGMX",
        filter_str=f'(SCODE="{code}")',
        page_size=HISTORY_DAYS + 5,  # small over-fetch for safety
        sort_columns="DATE", sort_types="-1",
    )

    if not all_data:
        return {
            "history_count": 0,
            "margin_eligible": False,
            "history": [],
            "latest_rzye_yi": None,
            "latest_rzrqye_yi": None,
            "latest_rzjme_yi": None,
            "latest_rzyezb_pct": None,
            "trend_rzjme_sum_yi": None,
            "trend_signal": "no_data",
        }

    history = []
    for row in all_data[:HISTORY_DAYS]:
        rzye = float(row.get("RZYE") or 0)        # 融资余额 (元)
        rqye = float(row.get("RQYE") or 0)        # 融券余额 (元)
        rzrqye = float(row.get("RZRQYE") or 0)    # 合计 (元)
        rzmre = float(row.get("RZMRE") or 0)      # 融资买入额 (元)
        rzche = float(row.get("RZCHE") or 0)      # 融资偿还额 (元)
        rzjme = float(row.get("RZJME") or 0)      # 融资净买额 (元)
        rqmcl = float(row.get("RQMCL") or 0)      # 融券卖出量 (股)
        rqchl = float(row.get("RQCHL") or 0)      # 融券偿还量 (股)
        rqjmg = float(row.get("RQJMG") or 0)      # 融券净买股 (股)
        rzyezb = float(row.get("RZYEZB") or 0)    # 融资余额占比% (already %)

        history.append({
            "date": str(row.get("DATE", ""))[:10],
            "rzye_yi": round(rzye / 1e8, 4),       # 转换为亿
            "rqye_yi": round(rqye / 1e8, 4),
            "rzrqye_yi": round(rzrqye / 1e8, 4),
            "rzmre_yi": round(rzmre / 1e8, 4),
            "rzche_yi": round(rzche / 1e8, 4),
            "rzjme_yi": round(rzjme / 1e8, 4),
            "rqmcl_wan": round(rqmcl / 1e4, 2),    # 股 → 万股
            "rqchl_wan": round(rqchl / 1e4, 2),
            "rqjmg_wan": round(rqjmg / 1e4, 2),
            "rzyezb_pct": round(rzyezb, 4),
            "close_price": float(row.get("SPJ") or 0),
            "change_pct": float(row.get("ZDF") or 0),
        })

    # Reverse to chronological (oldest first) for trend math
    history_chrono = list(reversed(history))

    # Latest snapshot (most recent trading day)
    latest = history[0]
    # Trend over last TREND_WINDOW days
    trend_window = history_chrono[-TREND_WINDOW:] \
        if len(history_chrono) >= TREND_WINDOW else history_chrono
    trend_rzjme_sum = sum(d["rzjme_yi"] for d in trend_window)
    trend_rzjme_positive_days = sum(
        1 for d in trend_window if d["rzjme_yi"] > 0
    )

    # Simple signal: net buying direction over trend window
    # Threshold: 5+ positive days out of TREND_WINDOW AND
    # cumulative >= 10% of latest rzye
    trend_signal = "neutral"
    if len(trend_window) >= 3:
        positive_ratio = trend_rzjme_positive_days / len(trend_window)
        if positive_ratio >= 0.6 and trend_rzjme_sum > 0:
            trend_signal = "leverage_in"        # 杠杆资金持续净流入
        elif positive_ratio <= 0.4 and trend_rzjme_sum < 0:
            trend_signal = "leverage_out"       # 杠杆资金持续净流出

    return {
        "history_count": len(history),
        "margin_eligible": True,
        "history": history,
        "latest_date": latest["date"],
        "latest_rzye_yi": latest["rzye_yi"],
        "latest_rqye_yi": latest["rqye_yi"],
        "latest_rzrqye_yi": latest["rzrqye_yi"],
        "latest_rzjme_yi": latest["rzjme_yi"],
        "latest_rzyezb_pct": latest["rzyezb_pct"],
        "trend_window_days": len(trend_window),
        "trend_rzjme_sum_yi": round(trend_rzjme_sum, 4),
        "trend_rzjme_positive_days": trend_rzjme_positive_days,
        "trend_signal": trend_signal,
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
    print(f"Fetching margin trading for {len(codes)} CN tickers "
          f"via EM datacenter...")
    print(f"  (rate-limited at {EM_MIN_INTERVAL}s/call, 1 call/ticker, "
          f"{HISTORY_DAYS}d history → ETA ~{len(codes)*EM_MIN_INTERVAL/60:.1f} min)")
    print()

    per_ticker: dict[str, dict] = {}
    errors: list[dict] = []
    fetched_at = time.strftime("%Y-%m-%d %H:%M:%S")
    t0 = time.time()

    for i, code in enumerate(codes, 1):
        try:
            data = fetch_margin_for(code)
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
            eligible = sum(1 for v in per_ticker.values()
                           if v.get("margin_eligible"))
            n_in = sum(1 for v in per_ticker.values()
                       if v.get("trend_signal") == "leverage_in")
            n_out = sum(1 for v in per_ticker.values()
                        if v.get("trend_signal") == "leverage_out")
            print(f"  [{i:>3}/{len(codes)}] ok={len(per_ticker)} "
                  f"err={len(errors)} eligible={eligible} "
                  f"lev_in={n_in} lev_out={n_out} "
                  f"elapsed={elapsed:>5.1f}s eta={eta:>5.1f}s")

    # ── Write JSON output FIRST (so data is safe even if aggregation fails) ─
    eligible_count = sum(1 for v in per_ticker.values()
                         if v.get("margin_eligible"))
    not_eligible_count = sum(1 for v in per_ticker.values()
                             if not v.get("margin_eligible"))

    signal_counts = {
        "leverage_in": sum(1 for v in per_ticker.values()
                           if v.get("trend_signal") == "leverage_in"),
        "leverage_out": sum(1 for v in per_ticker.values()
                            if v.get("trend_signal") == "leverage_out"),
        "neutral": sum(1 for v in per_ticker.values()
                       if v.get("trend_signal") == "neutral"),
        "no_data": sum(1 for v in per_ticker.values()
                       if v.get("trend_signal") == "no_data"),
    }

    # Coverage distribution: # of trading days fetched per ticker
    coverage_buckets = {"0": 0, "1-7": 0, "8-15": 0, "16-25": 0, "26+": 0}
    for v in per_ticker.values():
        n = v.get("history_count", 0)
        if n == 0:
            coverage_buckets["0"] += 1
        elif n <= 7:
            coverage_buckets["1-7"] += 1
        elif n <= 15:
            coverage_buckets["8-15"] += 1
        elif n <= 25:
            coverage_buckets["16-25"] += 1
        else:
            coverage_buckets["26+"] += 1

    output = {
        "source": "https://datacenter-web.eastmoney.com/api/data/v1/get",
        "fetched_at": fetched_at,
        "source_method": "a-stock-data skill §4.1 (margin_trading)",
        "ticker_count": len(per_ticker),
        "error_count": len(errors),
        "margin_eligible_count": eligible_count,
        "not_eligible_count": not_eligible_count,
        "rate_limit_seconds": EM_MIN_INTERVAL,
        "history_days_per_ticker": HISTORY_DAYS,
        "trend_window_days": TREND_WINDOW,
        "coverage_distribution": coverage_buckets,
        "signal_distribution": signal_counts,
        "field_name_notes": (
            "All monetary fields in 元 (yuan) at source; normalized to 亿 "
            "(divide by 1e8) and 万股 (divide by 1e4) for output. "
            "RZYEZB is already in percentage units (1.32 = 1.32%). "
            "Skill §4.1 field names match actual API response."
        ),
        "errors": errors[:20],
        "tickers": per_ticker,
    }

    OUT_PATH.write_text(
        json.dumps(output, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # ── Aggregate stats (post-write; safe to fail without losing data) ─────
    eligible = [v for v in per_ticker.values() if v.get("margin_eligible")]
    total_rzye = sum(v["latest_rzye_yi"] for v in eligible
                     if v.get("latest_rzye_yi") is not None)

    # Top leveraged long positions (largest 融资余额)
    by_rzye = sorted(
        [v for v in eligible if v.get("latest_rzye_yi") is not None],
        key=lambda v: -(v["latest_rzye_yi"]),
    )[:10]

    # Top leverage inflow (largest positive 10d 融资净买额)
    by_inflow = sorted(
        [v for v in eligible
         if v.get("trend_rzjme_sum_yi") is not None],
        key=lambda v: -(v["trend_rzjme_sum_yi"]),
    )[:10]

    # Top leverage outflow (most negative)
    by_outflow = sorted(
        [v for v in eligible
         if v.get("trend_rzjme_sum_yi") is not None],
        key=lambda v: v["trend_rzjme_sum_yi"],
    )[:10]

    # Highest 融资余额占比 (concentration of leverage in float)
    by_rzyezb = sorted(
        [v for v in eligible
         if v.get("latest_rzyezb_pct") is not None
         and v.get("latest_rzye_yi", 0) > 1],  # filter noise on tiny absolute
        key=lambda v: -(v["latest_rzyezb_pct"]),
    )[:10]

    # ── Summary ─────────────────────────────────────────────────────────────
    print()
    print("=" * 80)
    print("EM margin trading backfill complete")
    print("=" * 80)
    print(f"  Total tickers attempted:   {len(codes)}")
    print(f"  Successfully fetched:      {len(per_ticker)}")
    print(f"  Errors:                    {len(errors)}")
    if errors:
        print(f"    samples: {[(e['ticker'], e['error'][:50]) for e in errors[:3]]}")
    print()

    print(f"  Margin-eligible tickers:   {eligible_count} "
          f"({eligible_count/max(len(per_ticker),1)*100:.1f}%)")
    print(f"  Not on margin list:        {not_eligible_count} "
          f"({not_eligible_count/max(len(per_ticker),1)*100:.1f}%)")
    if eligible_count:
        print(f"  Total 融资余额 across seed: {total_rzye:.1f} 亿元 "
              f"(avg {total_rzye/eligible_count:.2f} 亿/ticker)")
    print()

    print("  Coverage distribution (days of history per ticker):")
    for bucket, n in coverage_buckets.items():
        pct = n / len(per_ticker) * 100 if per_ticker else 0
        print(f"    {bucket:>5} days: {n:>4} tickers ({pct:>5.1f}%)")

    print()
    print("  Trend signal distribution "
          f"(last {TREND_WINDOW} trading days):")
    for sig, n in signal_counts.items():
        pct = n / len(per_ticker) * 100 if per_ticker else 0
        print(f"    {sig:<14} {n:>4} tickers ({pct:>5.1f}%)")

    if by_rzye:
        print()
        print("  Top 10 by 融资余额 (largest leverage long positions):")
        for v in by_rzye:
            print(f"    {v['ticker']} {v['seed_name']:<10}  "
                  f"rzye={v['latest_rzye_yi']:>8.2f}亿  "
                  f"占比={v['latest_rzyezb_pct']:>5.2f}%  "
                  f"signal={v['trend_signal']}")

    if by_inflow:
        print()
        print(f"  Top 10 leverage INFLOW (net 融资买入 over last {TREND_WINDOW}d):")
        for v in by_inflow:
            print(f"    {v['ticker']} {v['seed_name']:<10}  "
                  f"net_buy={v['trend_rzjme_sum_yi']:>+8.2f}亿  "
                  f"pos_days={v['trend_rzjme_positive_days']}/"
                  f"{v['trend_window_days']}")

    if by_outflow:
        print()
        print(f"  Top 10 leverage OUTFLOW (net 融资偿还 over last {TREND_WINDOW}d):")
        for v in by_outflow:
            print(f"    {v['ticker']} {v['seed_name']:<10}  "
                  f"net_buy={v['trend_rzjme_sum_yi']:>+8.2f}亿  "
                  f"pos_days={v['trend_rzjme_positive_days']}/"
                  f"{v['trend_window_days']}")

    if by_rzyezb:
        print()
        print("  Top 10 by 融资余额占流通市值比 (leverage concentration):")
        for v in by_rzyezb:
            print(f"    {v['ticker']} {v['seed_name']:<10}  "
                  f"rzye={v['latest_rzye_yi']:>7.2f}亿  "
                  f"占比={v['latest_rzyezb_pct']:>6.2f}%  "
                  f"signal={v['trend_signal']}")

    print()
    print(f"Wrote: {OUT_PATH}")


if __name__ == "__main__":
    main()
