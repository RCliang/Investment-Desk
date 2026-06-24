"""
Consolidate layer exploration data into final 5-layer summary.

Data sources (canonical a-stock-data skill methods):
- Layers 1-3: EastMoney clist m:90+t:2 (skill §3.7) — 100 industry boards
- Layers 4-5: iwencai query2data (skill §2.3) — 20 AI themes

EastMoney push2 endpoint is IP-blocked (skill #18), so concept boards
(m:90+t:3) are not available this session. iwencai covers AI themes
comprehensively, so Layers 4-5 are well-populated.
"""

import json
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def load_industry_data() -> dict:
    """Load Layers 1-3 from layer_exploration.json"""
    p = DATA_DIR / "layer_exploration.json"
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


def load_iwencai_data() -> dict:
    """Load Layers 4-5 from layer_4_5_iwencai.json"""
    p = DATA_DIR / "layer_4_5_iwencai.json"
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


def main():
    ind = load_industry_data()
    iw = load_iwencai_data()

    print("=" * 90)
    print("InvestLens v1 — Final Layer Exploration Summary")
    print("=" * 90)
    print()
    print("Data sources (canonical /a-stock-data skill):")
    print("  Layers 1-3: EastMoney clist m:90+t:2 (§3.7 industry_comparison)")
    print("  Layers 4-5: iwencai query2data (§2.3) — 20 AI themes")
    print("  Note: EM concept boards (m:90+t:3) unavailable — IP blocked (skill #18)")
    print()

    grand_total_companies = 0
    grand_total_subindustries = 0

    # === Layers 1-3 (industries) ===
    if ind:
        for layer in ind.get("layers", []):
            name = layer["name"]
            if name in ("AI基础模型 (Foundation Models)", "AI应用 (AI Applications)"):
                continue  # These use iwencai data
            subs = layer["sub_industries"]
            if not subs:
                print(f"\n{name}: (no sub-industries from this source)")
                continue
            total = sum(s["member_count"] for s in subs)
            grand_total_companies += total
            grand_total_subindustries += len(subs)
            print(f"## {name}")
            print(f"   {len(subs)} sub-industries  |  ~{total} member stocks")
            print("-" * 90)
            print(f"   {'Sub-industry':<24} {'Members':>8}  {'Leader':<14}")
            print("-" * 90)
            for s in subs:
                leader = (s.get("leader") or "")[:12]
                print(f"   {s['name'][:22]:<24} {s['member_count']:>8}  {leader:<14}")
            print()

    # === Layers 4-5 (iwencai) ===
    if iw:
        for layer_name, data in iw.items():
            themes = data.get("themes", [])
            total_unique = data.get("total_unique_companies", 0)
            multi = data.get("multi_theme_companies", 0)
            grand_total_companies += total_unique
            grand_total_subindustries += len(themes)
            print(f"## {layer_name}")
            print(f"   {len(themes)} sub-industries (concepts)  |  {total_unique} unique companies")
            print(f"   ({multi} companies appear in multiple concepts = core to layer)")
            print("-" * 90)
            print(f"   {'Concept':<28} {'iwencai matches':>16}")
            print("-" * 90)
            for t in themes:
                print(f"   {t['query'][:26]:<28} {t['row_count']:>16}")
            print()
            print(f"   Top 8 companies (by concept coverage):")
            for c in data.get("top_companies", [])[:8]:
                themes_str = f"{c['theme_count']}/{len(themes)}"
                print(f"     {c['name'][:12]:<14} {c['ticker']:<11} {c['industry'][:10]:<12} in {themes_str} concepts")
            print()

    print("=" * 90)
    print(f"GRAND TOTALS")
    print(f"  Sub-industries explored: {grand_total_subindustries}")
    print(f"  Company memberships:     ~{grand_total_companies}")
    print(f"  (Memberships overlap across concepts/industries; unique companies < sum)")
    print("=" * 90)


if __name__ == "__main__":
    main()
