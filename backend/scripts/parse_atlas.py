"""
Parse aichainmap.com atlas dump into a structured seed JSON.

Input:  backend/data/atlas_raw.txt
Output: backend/data/aichainmap_seed.json

The atlas dump format (saved from https://aichainmap.com/atlas?L=1):
  - Layer markers:   LAYER I — 能源与电力 (Energy & Power)
  - Stream markers:  [上游 / Upstream] — 1 个
  - Group IDs:       ## I-U-1   (Layer I, Upstream, group 1)
  - Company+ticker:  东方电气600875  (A股 6-digit)
                     阿里巴巴9988     (港股 4-digit)
                     Bloom EnergyBEE (US letter ticker, concatenated)
                     比亚迪002594.SZ / 1211   (A+H dual-listing)
  - Hidden counts:   + 16

Sub-industry NAMES are not in the public dump — only company clusters.
This script hardcodes inferred names based on the visible company set.
See docs/adr/0007-aichainmap-canonical-layers.md for the naming policy.

Ticker extraction is greedy on a whitespace-separated token stream:
  1. Strip trailing ` / N` dual-listing suffixes.
  2. Match the longest trailing ticker: A股 (.SH/.SZ), 港股 (.HK), or 美股 (letters).
"""

import json
import re
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
RAW_PATH = DATA_DIR / "atlas_raw.txt"
OUT_PATH = DATA_DIR / "aichainmap_seed.json"


# Layer headers (roman numeral → canonical layer)
LAYER_HEADERS = [
    ("I",   "能源与电力",   "Energy"),
    ("II",  "芯片系统",    "Chip Systems"),
    ("III", "AI基础设施",  "AI Infrastructure"),
    ("IV",  "AI基础模型",  "Foundation Models"),
    ("V",   "AI应用",      "AI Applications"),
]

STREAM_MAP = {
    "上游": ("U", "Upstream"),
    "中游": ("M", "Midstream"),
    "下游": ("D", "Downstream"),
}

# Sub-industry NAMES — inferred from company clusters in the dump.
# Keyed by group_id (e.g., "II-U-1"). Names are zh (canonical).
# See docs/adr/0007 for the inference policy.
SUBINDUSTRY_NAMES = {
    # Layer I — 能源与电力
    "I-U-1":  "发电设备与新能源",
    "I-M-1":  "能源工业基础材料",
    "I-M-2":  "电网与能源数字化",
    "I-D-1":  "热管理与液冷",
    "I-D-2":  "UPS·储能·电源管理",
    # Layer II — 芯片系统
    "II-U-1": "半导体设备",
    "II-U-2": "封装测试与PCB",
    "II-U-3": "铜箔与覆铜板",
    "II-U-4": "EDA工具",
    "II-U-5": "半导体IP授权",
    "II-M-1": "算力芯片设计与制造",
    "II-M-2": "存储芯片",
    "II-M-3": "FPGA",
    "II-M-4": "模拟与电源管理IC",
    "II-D-1": "服务器整机",
    "II-D-2": "光通信与光模块",
    "II-D-3": "网络设备与芯片",
    # Layer III — AI基础设施
    "III-U-1": "数据中心热管理",
    "III-U-2": "IDC与数据中心地产",
    "III-M-1": "数据中心机电系统",
    "III-M-2": "存储与内存接口",
    "III-M-3": "连接器与线缆",
    "III-M-4": "CDN与边缘计算",
    "III-M-5": "网络安全",
    "III-D-1": "云服务与基础算力",
    "III-D-2": "智算中心与算力租赁",
    "III-D-3": "云原生与可观测性",
    # Layer IV — AI基础模型
    "IV-U-1": "数据标注与训练数据",
    "IV-M-1": "AI大模型平台",
    "IV-M-2": "云厂商AI平台",
    "IV-D-1": "AI引擎与中间件",
    # Layer V — AI应用 (flat, no stream markers in dump)
    "V-1":  "智能驾驶",
    "V-2":  "人形机器人核心零部件",
    "V-3":  "AI营销与AIGC",
    "V-4":  "AI医疗",
    "V-5":  "AI安防与智慧城市",
    "V-6":  "企业服务SaaS",
    "V-7":  "AI金融",
    "V-8":  "AI教育",
    "V-9":  "金融科技与量化",
    "V-10": "AI法律与合规",
    "V-11": "智能客服与CRM",
    "V-12": "机器视觉与AOI检测",
    "V-13": "AI游戏",
    "V-14": "AI安全",
    "V-15": "AI药物发现",
    "V-16": "智慧物流与出行",
    "V-17": "垂直行业AI应用",
}


# Ticker extraction patterns — applied in priority order.
# Each pattern matches the trailing portion of a token.
_TICKER_A   = r"\d{6}(?:\.S[ZH])?"              # A股: 600519 / 600519.SH
_TICKER_HK  = r"\d{4,5}(?:\.HK)?"               # 港股: 9988 / 0981.HK
_TICKER_US  = r"[A-Z][A-Z.\-]{1,6}[A-Z]"        # 美股: NVDA / APH / BEE
_TICKER_DUAL = r"(?: / \d{4,5})?"               # A+H 双重上市后缀

TICKER_RE = re.compile(
    r"^(?P<name>.+?)"
    r"(?P<ticker>"
    + _TICKER_A + r"|" + _TICKER_HK + r"|" + _TICKER_US
    + r")"
    + _TICKER_DUAL
    + r"$"
)


def classify_ticker(ticker: str) -> str:
    """Return listing market tag for a parsed ticker string."""
    if re.fullmatch(r"\d{6}(?:\.S[ZH])?", ticker) or re.fullmatch(r"\d{6}", ticker):
        return "CN"
    if re.fullmatch(r"\d{4,5}(?:\.HK)?", ticker):
        return "HK"
    return "US"


def parse_company_token(token: str) -> tuple[str, str, str] | None:
    """
    Parse a single whitespace-separated token into (name, ticker, market).

    Returns None if no ticker is found (token is a bare English word or fragment).
    """
    if not token or token.startswith("#") or token.startswith("="):
        return None
    m = TICKER_RE.match(token)
    if not m:
        return None
    name = m.group("name").strip()
    ticker = m.group("ticker").strip()
    if not name or not ticker:
        return None
    # Filter false positives where "ticker" is really part of the name
    # (e.g., a bare English fragment matched the US-letter branch).
    # Require: at least one CJK char in name OR at least one space-separated
    # English word longer than 2 chars before the ticker.
    has_cjk = any("\u4e00" <= ch <= "\u9fff" for ch in name)
    if not has_cjk and len(name) < 3:
        return None
    return name, ticker, classify_ticker(ticker)


# Lines that should be skipped (not company data).
_SKIP_PREFIXES = ("#", "=", "LAYER", "[", "##")


def parse_atlas(text: str) -> dict:
    """
    Parse the atlas dump text into a structured dict.

    Output schema:
      {
        "source": "https://aichainmap.com/atlas?L=1",
        "fetched_at": "2026-06-24",
        "site_update_claimed": "2026·06·17",
        "layers": [
          {
            "layer_order": 1,
            "name_zh": "能源与电力",
            "name_en": "Energy",
            "sub_industries": [
              {
                "group_id": "I-U-1",
                "stream": "Upstream",
                "name_zh": "发电设备与新能源",
                "visible_companies": [{"name": ..., "ticker": ..., "market": ...}, ...],
                "hidden_count": 16,
                "estimated_total": 28   # len(visible) + hidden_count
              },
              ...
            ]
          },
          ...
        ],
        "totals": {"sub_industries": 48, "visible_companies": N, "estimated_total": N}
      }
    """
    lines = text.splitlines()

    # Parser state
    layers_out = []
    current_layer_roman: str | None = None
    current_layer_zh: str | None = None
    current_layer_en: str | None = None
    current_stream_en: str | None = None
    current_group_id: str | None = None
    current_group_companies: list[dict] = []
    pending_hidden_count: int | None = None
    subindustries_buffer: list[dict] = []

    def _flush_group():
        nonlocal current_group_id, current_group_companies, pending_hidden_count
        if current_group_id is None:
            return
        visible = list(current_group_companies)
        hidden = pending_hidden_count or 0
        entry = {
            "group_id": current_group_id,
            "stream": current_stream_en,
            "name_zh": SUBINDUSTRY_NAMES.get(current_group_id, "(未命名)"),
            "visible_companies": visible,
            "hidden_count": hidden,
            "estimated_total": len(visible) + hidden,
        }
        subindustries_buffer.append(entry)
        current_group_id = None
        current_group_companies = []
        pending_hidden_count = None

    def _flush_layer():
        nonlocal current_layer_roman, current_layer_zh, current_layer_en
        nonlocal current_stream_en, subindustries_buffer
        _flush_group()
        if current_layer_roman is not None and subindustries_buffer:
            order = ["I", "II", "III", "IV", "V"].index(current_layer_roman) + 1
            layers_out.append({
                "layer_order": order,
                "name_zh": current_layer_zh,
                "name_en": current_layer_en,
                "sub_industries": list(subindustries_buffer),
            })
        current_layer_roman = None
        current_layer_zh = None
        current_layer_en = None
        current_stream_en = None
        subindustries_buffer = []

    for raw_line in lines:
        line = raw_line.rstrip()
        stripped = line.strip()
        if not stripped:
            continue

        # Layer header
        for roman, zh, en in LAYER_HEADERS:
            if stripped.startswith(f"LAYER {roman} —"):
                _flush_layer()
                current_layer_roman = roman
                current_layer_zh = zh
                current_layer_en = en
                break
        else:
            # Stream header:  [上游 / Upstream] — 1 个
            if stripped.startswith("[") and " / " in stripped and "]" in stripped:
                _flush_group()
                # extract zh marker
                inside = stripped[stripped.index("[") + 1 : stripped.index("]")]
                zh_marker = inside.split(" / ")[0].strip()
                if zh_marker in STREAM_MAP:
                    current_stream_en = STREAM_MAP[zh_marker][1]
                continue

            # Group header
            if stripped.startswith("## "):
                _flush_group()
                current_group_id = stripped[3:].strip()
                continue

            # Hidden-count marker:  "+ 16"
            hidden_m = re.fullmatch(r"\+\s*(\d+)", stripped)
            if hidden_m and current_group_id is not None:
                pending_hidden_count = int(hidden_m.group(1))
                continue

            # Company line — split on whitespace and attempt ticker extraction.
            # Skip obvious non-data lines.
            if any(stripped.startswith(p) for p in _SKIP_PREFIXES):
                continue

            # Tokenize and parse companies
            tokens = stripped.split()
            for token in tokens:
                parsed = parse_company_token(token)
                if parsed is None:
                    continue
                name, ticker, market = parsed
                current_group_companies.append({
                    "name": name,
                    "ticker": ticker,
                    "market": market,
                })

    _flush_layer()

    # Totals
    total_sub = sum(len(L["sub_industries"]) for L in layers_out)
    total_visible = sum(
        len(s["visible_companies"])
        for L in layers_out for s in L["sub_industries"]
    )
    total_estimated = sum(
        s["estimated_total"]
        for L in layers_out for s in L["sub_industries"]
    )

    return {
        "source": "https://aichainmap.com/atlas?L=1",
        "fetched_at": "2026-06-24",
        "site_update_claimed": "2026·06·17",
        "note": (
            "Visible companies are those rendered server-side in the atlas "
            "page text. hidden_count is the site's own '+ N' ellipsis. "
            "Sub-industry names are inferred (not present in the public dump); "
            "see docs/adr/0007-aichainmap-canonical-layers.md."
        ),
        "layers": layers_out,
        "totals": {
            "sub_industries": total_sub,
            "visible_companies": total_visible,
            "estimated_total_companies": total_estimated,
        },
    }


def main():
    if not RAW_PATH.exists():
        raise SystemExit(f"atlas dump not found: {RAW_PATH}")

    text = RAW_PATH.read_text(encoding="utf-8")
    data = parse_atlas(text)

    OUT_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # Console summary
    print("=" * 80)
    print("InvestLens v1 — aichainmap.com Seed Parse")
    print("=" * 80)
    for layer in data["layers"]:
        n_sub = len(layer["sub_industries"])
        n_vis = sum(len(s["visible_companies"]) for s in layer["sub_industries"])
        n_est = sum(s["estimated_total"] for s in layer["sub_industries"])
        print(
            f"  L{layer['layer_order']} {layer['name_zh']:<10} "
            f"({layer['name_en']:<20})  "
            f"{n_sub:>2} sub-ind  {n_vis:>4} visible  ~{n_est:>4} est"
        )
    t = data["totals"]
    print("-" * 80)
    print(
        f"  TOTALS: {t['sub_industries']} sub-industries  "
        f"{t['visible_companies']} visible companies  "
        f"~{t['estimated_total_companies']} estimated (visible + hidden)"
    )
    print("=" * 80)
    print(f"Wrote: {OUT_PATH}")


if __name__ == "__main__":
    main()
