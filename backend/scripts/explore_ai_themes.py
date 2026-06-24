"""
Explore AI-themed companies for Layers 4-5 via iwencai query2data.

Context: EastMoney push2 endpoint (clist) is IP-blocked (skill #18).
For Layers 4-5 (Foundation Models + Applications), AI themes live in
concept boards, so we use iwencai's query2data (skill §2.3) which
returns structured stock listings.

Output: structured table of AI themes → company counts per layer.
"""

import os
import json
import secrets
import requests
from pathlib import Path

# Load env vars
env_path = Path(__file__).resolve().parent.parent / ".env"
if env_path.exists():
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip())

IWENCAI_BASE = os.environ.get("IWENCAI_BASE_URL", "https://openapi.iwencai.com")
IWENCAI_KEY = os.environ.get("IWENCAI_API_KEY", "")


def _claw_headers() -> dict:
    """SkillHub 2.0 X-Claw headers (verbatim from §2.3)"""
    return {
        "X-Claw-Call-Type": "normal",
        "X-Claw-Skill-Id": "report-search",
        "X-Claw-Skill-Version": "2.0.0",
        "X-Claw-Plugin-Id": "none",
        "X-Claw-Plugin-Version": "none",
        "X-Claw-Trace-Id": secrets.token_hex(32),
    }


def iwencai_query(query: str, page: int = 1, limit: int = 100) -> dict:
    """iwencai query2data — structured stock listings (canonical §2.3)"""
    headers = {
        "Authorization": f"Bearer {IWENCAI_KEY}",
        "Content-Type": "application/json",
        **_claw_headers(),
    }
    payload = {
        "query": query,
        "page": str(page),
        "limit": str(limit),
        "is_cache": "1",
        "expand_index": "true",
    }
    r = requests.post(
        f"{IWENCAI_BASE}/v1/query2data",
        json=payload, headers=headers, timeout=30,
    )
    if r.status_code != 200:
        raise RuntimeError(f"iwencai HTTP {r.status_code}: {r.text[:200]}")
    d = r.json()
    if d.get("status_code", 0) != 0:
        raise RuntimeError(f"iwencai error: {d.get('status_msg', '')}")
    return {
        "row_count": d.get("row_count", 0),
        "code_count": d.get("code_count", 0),
        "datas": d.get("datas") or [],
    }


# AI theme queries per layer — these map to concept boards in the A-share market
LAYER_THEMES = {
    "AI基础模型 (Foundation Models)": [
        "大模型 概念股",
        "AIGC概念股",
        "生成式AI概念股",
        "多模态AI概念股",
        "DeepSeek概念股",
        "AI智能体概念股",
    ],
    "AI应用 (AI Applications)": [
        "人形机器人概念股",
        "自动驾驶概念股",
        "智能驾驶概念股",
        "AI眼镜概念股",
        "AI智能穿戴概念股",
        "AI医疗概念股",
        "AI教育概念股",
        "AI安防概念股",
        "智慧城市概念股",
        "工业软件概念股",
        "CAD概念股",
        "无人机概念股",
        "算力概念股",
        "东数西算概念股",
    ],
}


def explore_theme(query: str) -> dict:
    """Run a single iwencai query2data and extract company info."""
    result = iwencai_query(query, limit=200)
    datas = result["datas"]
    # datas is a list of lists (each inner list = one row dict-like)
    # Actually it's a list of dicts based on our test
    companies = []
    if datas and isinstance(datas[0], list):
        # Unexpected shape, take first inner list
        datas = datas[0] if datas[0] else []
    for row in datas:
        if not isinstance(row, dict):
            continue
        companies.append({
            "ticker": str(row.get("股票代码", "")),
            "name": row.get("股票简称", ""),
            "industry": (row.get("所属同花顺行业") or [""])[0]
                        if isinstance(row.get("所属同花顺行业"), list)
                        else str(row.get("所属同花顺行业", "")),
            "concepts": row.get("所属概念", []) if isinstance(row.get("所属概念"), list) else [],
        })
    return {
        "query": query,
        "row_count": result["row_count"],
        "returned": len(companies),
        "companies": companies,
    }


def explore_layer(layer_name: str, themes: list[str]) -> dict:
    """Run all themes for a layer, collect unique companies."""
    print(f"\n## {layer_name}")
    print("-" * 80)
    theme_results = []
    layer_companies: dict[str, dict] = {}  # name -> company info + theme set

    for query in themes:
        try:
            r = explore_theme(query)
        except Exception as e:
            print(f"  [ERR] {query!r}: {e}")
            theme_results.append({"query": query, "row_count": 0, "returned": 0, "error": str(e)})
            continue
        theme_results.append({
            "query": query,
            "row_count": r["row_count"],
            "returned": r["returned"],
        })
        print(f"  {query:<28}  iwencai matches: {r['row_count']:>4}  returned: {r['returned']:>3}")

        # Merge into layer company set
        for c in r["companies"]:
            name = c["name"]
            if not name:
                continue
            if name not in layer_companies:
                layer_companies[name] = {
                    "ticker": c["ticker"],
                    "name": name,
                    "industry": c["industry"],
                    "themes": set(),
                }
            layer_companies[name]["themes"].add(query)

    # Build summary
    total_unique = len(layer_companies)
    multi_theme = sum(1 for c in layer_companies.values() if len(c["themes"]) >= 2)
    print(f"  → Unique companies in layer: {total_unique}  (multi-theme: {multi_theme})")

    # Top by theme coverage
    sorted_companies = sorted(
        layer_companies.values(),
        key=lambda x: (-len(x["themes"]), x["name"]),
    )
    return {
        "name": layer_name,
        "themes": theme_results,
        "total_unique_companies": total_unique,
        "multi_theme_companies": multi_theme,
        "top_companies": [
            {
                "name": c["name"],
                "ticker": c["ticker"],
                "industry": c["industry"],
                "theme_count": len(c["themes"]),
                "themes": sorted(list(c["themes"])),
            }
            for c in sorted_companies[:20]
        ],
    }


def main():
    print("=" * 80)
    print("InvestLens v1 — Layers 4-5 AI Theme Exploration")
    print("via iwencai query2data (skill §2.3 canonical)")
    print("=" * 80)
    if not IWENCAI_KEY:
        print("ERROR: IWENCAI_API_KEY not set")
        return

    results = {}
    for layer_name, themes in LAYER_THEMES.items():
        results[layer_name] = explore_layer(layer_name, themes)

    # Summary
    print()
    print("=" * 80)
    print("SUMMARY")
    print("=" * 80)
    for layer_name, data in results.items():
        total_themes = len(LAYER_THEMES[layer_name])
        print(f"\n{layer_name}:")
        print(f"  Themes explored: {total_themes}")
        print(f"  Unique companies: {data['total_unique_companies']}")
        print(f"  Multi-theme companies (core): {data['multi_theme_companies']}")
        print(f"  Top 10 (by theme coverage):")
        for c in data["top_companies"][:10]:
            print(f"    {c['name'][:14]:<16} {c['ticker']:<11} "
                  f"{c['industry'][:12]:<14} in {c['theme_count']}/{total_themes} themes")

    # Persist
    out_dir = Path(__file__).resolve().parent.parent / "data"
    out_dir.mkdir(exist_ok=True)
    out_path = out_dir / "layer_4_5_iwencai.json"
    out_path.write_text(
        json.dumps(results, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"\nRaw data persisted to: {out_path}")


if __name__ == "__main__":
    main()
