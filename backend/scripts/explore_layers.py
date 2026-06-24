"""
Explore sub-industries and company counts per AI chain layer.

Uses ONLY the canonical patterns from /a-stock-data skill:
- em_get() helper with rate limiting (mandatory for EastMoney)
- clist endpoint with fs=m:90+t:1 (concepts) and fs=m:90+t:2 (industries)
- f104 (up_count) + f105 (down_count) = total members per board

Output: structured layer → sub-industry → company count table.
"""

import json
import time
import random
import requests
from pathlib import Path

# ── a-stock-data skill: 共用 helper (verbatim from §Prerequisites) ──────────
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
EM_SESSION = requests.Session()
EM_SESSION.headers.update({"User-Agent": UA})
EM_MIN_INTERVAL = 1.0
_em_last_call = [0.0]


def em_get(url: str, params: dict | None = None, headers: dict | None = None,
           timeout: int = 15, **kwargs):
    """东财统一请求入口：自动节流 + 复用 session + 默认 UA。"""
    wait = EM_MIN_INTERVAL - (time.time() - _em_last_call[0])
    if wait > 0:
        time.sleep(wait + random.uniform(0.1, 0.5))
    try:
        return EM_SESSION.get(url, params=params, headers=headers, timeout=timeout, **kwargs)
    finally:
        _em_last_call[0] = time.time()


# ── a-stock-data skill: clist board listing (adapted from §3.7) ─────────────
def list_boards(board_type: int, page_size: int = 200) -> list[dict]:
    """
    List all boards of a given type via EastMoney clist endpoint.
    board_type: 1=concept, 2=industry, 3=region
    Returns: [{name, code, change_pct, up_count, down_count, total, leader}, ...]
    """
    url = "https://push2.eastmoney.com/api/qt/clist/get"
    params = {
        "pn": "1", "pz": str(page_size), "po": "1", "np": "1",
        "fltt": "2", "invt": "2",
        "fs": f"m:90+t:{board_type}",
        "fields": "f2,f3,f4,f12,f13,f14,f104,f105,f128,f136,f140,f141,f207",
    }
    headers = {"User-Agent": UA}
    r = em_get(url, params=params, headers=headers, timeout=15)
    d = r.json()
    items = d.get("data", {}).get("diff", []) or []
    rows = []
    for item in items:
        up = item.get("f104", 0) or 0
        down = item.get("f105", 0) or 0
        rows.append({
            "name":         item.get("f14", ""),
            "code":         item.get("f12", ""),
            "change_pct":   item.get("f3", 0),
            "up_count":     up,
            "down_count":   down,
            "total":        up + down,
            "leader":       item.get("f140", ""),
            "leader_change": item.get("f136", 0),
        })
    return rows


# ── AI keyword map for the 5 seed layers (ADR-0002) ─────────────────────────
LAYER_KEYWORDS = {
    "能源 (Energy)": [
        "电力", "电源", "核电", "风电", "光伏", "储能", "电网", "特高压",
        "充电桩", "氢能", "锂电", "电池", "煤炭", "石油", "天然气",
        "数据中心", "算力基建", "IDC",
    ],
    "芯片 (Chips)": [
        "半导体", "芯片", "集成电路", "光刻", "刻蚀", "薄膜", "清洗",
        "封测", "封装", "测试", "EDA", "IP", "硅片", "衬底", "外延",
        "GPU", "CPU", "FPGA", "ASIC", "存储", "DRAM", "NAND",
        "模拟", "射频", "功率", "IGBT", "SiC", "GaN", "氮化镓", "碳化硅",
        "光模块", "光通信", "CPO", "光电", "HBM",
    ],
    "AI基础设施 (AI Infrastructure)": [
        "服务器", "算力", "IDC", "数据中心", "云计算", "云服务",
        "交换机", "路由器", "光模块", "光通信", "液冷", "散热",
        "存储", "边缘计算", "CDN", "网络", "通信",
        "pcb", "PCB", "覆铜板", "连接器",
    ],
    "AI基础模型 (Foundation Models)": [
        "大模型", "AIGC", "生成式", "NLP", "自然语言",
        "多模态", "视觉", "语音", "知识图谱",
        "OpenAI", "GPT", "DeepSeek", "智谱", "百度", "科大讯飞",
        "昆仑万维", "金山办公",
    ],
    "AI应用 (AI Applications)": [
        "机器人", "人形", "工业机器人", "服务机器人",
        "自动驾驶", "无人驾驶", "智能驾驶", "激光雷达",
        "AI医疗", "智慧医疗", "AI制药",
        "AI教育", "智慧教育",
        "AI金融", "智慧金融",
        "AI安防", "智慧城市",
        "智能穿戴", "AR", "VR", "MR", "AI眼镜",
        "无人机", "工业软件", "CAD", "CAE",
        "智慧", "智能", "AI",
    ],
}


def assign_layer(name: str) -> str | None:
    """Return the layer name if the board matches any layer's keywords. Top-down priority."""
    for layer, keywords in LAYER_KEYWORDS.items():
        for kw in keywords:
            if kw.lower() in name.lower():
                return layer
    return None


def explore():
    """Fetch concept + industry boards, classify into 5 layers, output structured table."""
    print("=" * 80)
    print("InvestLens v1 — AI Chain Layer Exploration")
    print("=" * 80)
    print()

    # Fetch both lists
    print("[1/3] Fetching concept boards (m:90+t:1)...")
    concepts = list_boards(board_type=1, page_size=500)
    print(f"      Got {len(concepts)} concept boards")

    print("[2/3] Fetching industry boards (m:90+t:2)...")
    industries = list_boards(board_type=2, page_size=200)
    print(f"      Got {len(industries)} industry boards")
    print()

    # Combine and classify
    all_boards = []
    for b in concepts:
        b["source"] = "concept"
        all_boards.append(b)
    for b in industries:
        b["source"] = "industry"
        all_boards.append(b)

    for b in all_boards:
        b["layer"] = assign_layer(b["name"])

    # Group by layer
    by_layer: dict[str, list[dict]] = {}
    unclassified = []
    for b in all_boards:
        layer = b["layer"]
        if layer:
            by_layer.setdefault(layer, []).append(b)
        else:
            unclassified.append(b)

    # Print per-layer table
    print("[3/3] Layer → Sub-industry → Company count")
    print("=" * 80)
    layer_order = list(LAYER_KEYWORDS.keys())
    total_companies = 0
    total_subindustries = 0

    for layer in layer_order:
        boards = by_layer.get(layer, [])
        # Deduplicate by name (same board may appear in concept + industry)
        seen = set()
        unique = []
        for b in sorted(boards, key=lambda x: -x["total"]):
            if b["name"] not in seen:
                seen.add(b["name"])
                unique.append(b)

        layer_companies = sum(b["total"] for b in unique)
        total_companies += layer_companies
        total_subindustries += len(unique)

        print(f"\n## {layer}  ({len(unique)} sub-industries, ~{layer_companies} member stocks)")
        print("-" * 80)
        print(f"{'Sub-industry':<28} {'Type':<10} {'Members':>8} {'Leader':<16} {'Chg%':>7}")
        print("-" * 80)
        for b in unique:
            chg = b["change_pct"] if isinstance(b["change_pct"], (int, float)) else 0
            chg_str = f"{chg:+.2f}" if chg else "-"
            print(f"{b['name'][:26]:<28} {b['source']:<10} {b['total']:>8} "
                  f"{(b['leader'] or '')[:14]:<16} {chg_str:>7}")

    print()
    print("=" * 80)
    print(f"TOTALS: {total_subindustries} sub-industries across 5 layers, "
          f"~{total_companies} stock memberships (with duplicates across boards)")
    print(f"Unclassified boards: {len(unclassified)} (out of {len(all_boards)})")
    print("=" * 80)

    # Persist as JSON for next step (seed YAML generation)
    out_dir = Path(__file__).resolve().parent.parent / "data"
    out_dir.mkdir(exist_ok=True)
    out_path = out_dir / "layer_exploration.json"
    payload = {
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "layers": [
            {
                "name": layer,
                "sub_industries": [
                    {
                        "name": b["name"],
                        "source": b["source"],
                        "code": b["code"],
                        "member_count": b["total"],
                        "leader": b["leader"],
                        "change_pct": b["change_pct"],
                    }
                    for b in sorted(by_layer.get(layer, []), key=lambda x: -x["total"])
                ],
            }
            for layer in layer_order
        ],
        "unclassified_count": len(unclassified),
        "raw_concept_count": len(concepts),
        "raw_industry_count": len(industries),
    }
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nRaw data persisted to: {out_path}")


if __name__ == "__main__":
    explore()
