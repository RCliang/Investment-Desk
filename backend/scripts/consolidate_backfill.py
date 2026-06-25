"""
Consolidated view of all v1 backfills — quotes + finance + reports + concepts
+ lockup + holder_num + margin.

Read-only reporting script: joins the seven backfill JSON files by ticker and
prints coverage stats, concept leaders, and per-layer enrichment summaries.

Usage:
    python scripts/consolidate_backfill.py
"""

import json
from collections import Counter
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def load(name):
    return json.loads((DATA_DIR / name).read_text(encoding="utf-8"))


def main():
    seed = load("aichainmap_seed.json")
    quotes = {q["ticker"]: q for q in load("backfill_tencent_quotes.json")["quotes"]}
    finance = {f["ticker"]: f for f in load("backfill_mootdx_finance.json")["snapshots"]}
    reports = load("backfill_em_reports.json")["tickers"]
    blocks = load("backfill_em_concept_blocks.json")["tickers"]
    lockups = load("backfill_em_lockup_expiry.json")["tickers"]
    holders = load("backfill_em_holder_num.json")["tickers"]
    margins = load("backfill_em_margin_trading.json")["tickers"]

    # CN tickers from seed
    cn_in_seed: set[str] = set()
    for L in seed["layers"]:
        for s in L["sub_industries"]:
            for c in s["visible_companies"]:
                if c["market"] == "CN":
                    cn_in_seed.add(c["ticker"].split(".")[0])

    # Coverage matrix
    have_q = sum(1 for t in cn_in_seed if t in quotes)
    have_f = sum(1 for t in cn_in_seed if t in finance)
    have_r = sum(1 for t in cn_in_seed if t in reports and reports[t]["report_count_total"] > 0)
    have_b = sum(1 for t in cn_in_seed if t in blocks and blocks[t]["total_boards"] > 0)
    have_l = sum(1 for t in cn_in_seed if t in lockups and lockups[t]["history_count"] > 0)
    have_h = sum(1 for t in cn_in_seed if t in holders and holders[t]["history_count"] > 0)
    have_m = sum(1 for t in cn_in_seed if t in margins and margins[t].get("margin_eligible"))
    have_all7 = sum(1 for t in cn_in_seed if (
        t in quotes and t in finance and t in reports
        and reports[t]["report_count_total"] > 0 and t in blocks
        and blocks[t]["total_boards"] > 0
        and t in lockups and lockups[t]["history_count"] > 0
        and t in holders and holders[t]["history_count"] > 0
        and t in margins and margins[t].get("margin_eligible")
    ))

    print("=" * 78)
    print("InvestLens v1 — Consolidated backfill coverage")
    print("=" * 78)
    print(f"  CN tickers in seed:           {len(cn_in_seed):>4}")
    print(f"  With Tencent quotes:          {have_q:>4}  ({have_q/len(cn_in_seed)*100:.1f}%)")
    print(f"  With mootdx finance:          {have_f:>4}  ({have_f/len(cn_in_seed)*100:.1f}%)")
    print(f"  With EM research reports:     {have_r:>4}  ({have_r/len(cn_in_seed)*100:.1f}%)")
    print(f"  With EM concept blocks:       {have_b:>4}  ({have_b/len(cn_in_seed)*100:.1f}%)")
    print(f"  With EM lockup expiry:        {have_l:>4}  ({have_l/len(cn_in_seed)*100:.1f}%)")
    print(f"  With EM holder num:           {have_h:>4}  ({have_h/len(cn_in_seed)*100:.1f}%)")
    print(f"  With EM margin trading:       {have_m:>4}  ({have_m/len(cn_in_seed)*100:.1f}%)")
    print(f"  FULL enrichment (all 7):      {have_all7:>4}  ({have_all7/len(cn_in_seed)*100:.1f}%)")
    print()

    # ── Top AI/tech concept tags across the seed ────────────────────────────
    META_TAGS = {
        "融资融券", "深股通", "沪股通", "富时罗素", "MSCI中国", "标准普尔",
        "深成500", "大盘股", "中证500", "沪深300", "上证180", "上证50",
        "央视50_", "HS300_", "上证50_", "上证180_", "沪深300_",
        "融资融券标的", "转融券标的", "科创板做市商", "注册制次新股",
        "机构重仓", "券商场", "创业板", "科创板",
    }

    concept_counts = Counter()
    for v in blocks.values():
        if v["total_boards"] == 0:
            continue
        for tag in v["concept_tags"]:
            if tag in META_TAGS:
                continue
            if tag.endswith("板块"):
                continue
            if "概念" not in tag:
                continue
            concept_counts[tag] += 1

    print("Top 12 AI/tech CONCEPT tags across seed companies:")
    for tag, n in concept_counts.most_common(12):
        print(f"  {tag:<24} {n:>4} tickers")
    print()

    # ── Per-layer concept depth ─────────────────────────────────────────────
    print("Per-layer concept depth (top concept per sub-industry):")
    print()
    for L in seed["layers"]:
        print(f"  Layer {L['layer_order']}: {L['name_zh']} ({L['name_en']})")
        for s in L["sub_industries"]:
            cn_tickers = [
                c["ticker"].split(".")[0]
                for c in s["visible_companies"] if c["market"] == "CN"
            ]
            sub_concepts = Counter()
            for t in cn_tickers:
                if t in blocks and blocks[t]["total_boards"] > 0:
                    for tag in blocks[t]["concept_tags"]:
                        if tag in META_TAGS:
                            continue
                        if "概念" in tag and not tag.endswith("板块"):
                            sub_concepts[tag] += 1
            top3 = ", ".join(
                f"{tg}({n})" for tg, n in sub_concepts.most_common(3) if n >= 2
            )
            n_with_data = sum(1 for t in cn_tickers if t in blocks and blocks[t]["total_boards"]>0)
            print(f"    {s['group_id']:<7} {s['name_zh']:<26} "
                  f"({n_with_data}/{len(cn_tickers)} tagged)")
            if top3:
                print(f"           → {top3}")
        print()

    # ── Sample joined record: 寒武纪 (real seed ticker) ─────────────────────
    print("=" * 78)
    print("Sample joined record — 688256 寒武纪")
    print("=" * 78)
    t = "688256"
    q = quotes.get(t, {})
    f = finance.get(t, {})
    r = reports.get(t, {})
    b = blocks.get(t, {})
    lk = lockups.get(t, {})
    hd = holders.get(t, {})
    mg = margins.get(t, {})
    print(f"  Quote:    price={q.get('price')}  PE_TTM={q.get('pe_ttm')}  "
          f"PB={q.get('pb')}  mcap={q.get('mcap_yi')}亿")
    print(f"  Finance:  EPS={f.get('eps')}  ROE={f.get('roe_pct')}%  "
          f"net_margin={f.get('net_margin_pct')}%  "
          f"revenue={f.get('revenue_yi')}亿  debt={f.get('debt_ratio_pct')}%")
    if r.get("reports"):
        latest = r["reports"][0]
        print(f"  Latest report: [{latest['publish_date']}] "
              f"{latest['broker']} — {latest['rating']}")
        print(f"              pred EPS: "
              f"thisyr={latest['predict_this_year_eps']} "
              f"nextyr={latest['predict_next_year_eps']}")
    print(f"  Concepts: {b.get('total_boards')} boards — "
          f"{', '.join(b.get('concept_tags', [])[:6])}")
    print(f"  Lockup:   hist={lk.get('history_count')}  "
          f"upcoming={lk.get('upcoming_count')}  "
          f"(next 90d: {sum(u['shares_wan'] for u in lk.get('upcoming', [])):.0f}万股)")
    print(f"  Holders:  latest={hd.get('latest_holder_num')}  "
          f"ratio={hd.get('latest_change_ratio_pct')}%  "
          f"trend3p={hd.get('trend_3p_sum_ratio_pct')}  "
          f"signal={hd.get('signal')}")
    print(f"  Margin:   rzye={mg.get('latest_rzye_yi')}亿  "
          f"占比={mg.get('latest_rzyezb_pct')}%  "
          f"10d_net={mg.get('trend_rzjme_sum_yi')}亿  "
          f"signal={mg.get('trend_signal')}")


if __name__ == "__main__":
    main()
