import json
from openai import OpenAI
from app.config import DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, MODEL_NAME, LLM_MAX_TOKENS

client = OpenAI(
    api_key=DEEPSEEK_API_KEY,
    base_url=DEEPSEEK_BASE_URL,
) if DEEPSEEK_API_KEY else None

CHAIN_ANALYSIS_PROMPT = """你是一个资深的产业分析师。请对「{industry}」产业进行产业链分析。

要求：
1. 识别上游（原材料/零部件）、中游（制造/集成）、下游（应用/服务）各环节
2. 每个环节列出 3-6 个关键细分领域
3. 对每个细分领域标注投资机会评级（高/中/低）
4. 对每个细分领域写一句话说明机会逻辑

请严格按以下 JSON 格式输出，不要输出其他内容：
{{
  "summary": {{
    "market_size": "产业规模描述",
    "growth_rate": "同比增长率描述",
    "overall_rating": "综合评级（如 A/B+/B/C）",
    "opportunity_count": 0,
    "high_confidence_count": 0
  }},
  "upstream": [
    {{"name": "细分领域名称", "opp_level": "high/mid/low", "summary": "一句话说明"}}
  ],
  "midstream": [
    {{"name": "细分领域名称", "opp_level": "high/mid/low", "summary": "一句话说明"}}
  ],
  "downstream": [
    {{"name": "细分领域名称", "opp_level": "high/mid/low", "summary": "一句话说明"}}
  ]
}}"""

REPORT_GENERATION_PROMPT = """你是一个资深投资研究员。请基于以下产业链分析数据，为「{industry}」产业撰写投资研究报告。

产业链数据：
{chain_data}

请输出以下章节：
1. **核心判断**：一两段话概括产业投资逻辑
2. **机会优先级排序**：按确信度从高到低列出 3-5 个关键机会，每个包含：环节名称、机会类型、时间窗口、确信度百分比
3. **风险矩阵**：
   - 高风险因素（3个）
   - 正向催化剂（3个）
4. **关键标的推荐**：推荐 3-5 个 A 股标的，包含股票代码、推荐理由

使用 Markdown 格式输出。"""


def analyze_chain(industry: str) -> dict:
    if not client:
        return _mock_chain_analysis(industry)
    response = client.chat.completions.create(
        model=MODEL_NAME,
        max_tokens=LLM_MAX_TOKENS,
        messages=[{"role": "user", "content": CHAIN_ANALYSIS_PROMPT.format(industry=industry)}],
    )
    text = response.choices[0].message.content
    if "```json" in text:
        text = text.split("```json")[1].split("```")[0]
    elif "```" in text:
        text = text.split("```")[1].split("```")[0]
    return json.loads(text.strip())


def generate_report_stream(industry: str, chain_data: str):
    if not client:
        yield _mock_report(industry)
        return
    prompt = REPORT_GENERATION_PROMPT.format(industry=industry, chain_data=chain_data)
    stream = client.chat.completions.create(
        model=MODEL_NAME,
        max_tokens=LLM_MAX_TOKENS * 2,
        messages=[{"role": "user", "content": prompt}],
        stream=True,
    )
    for chunk in stream:
        delta = chunk.choices[0].delta.content
        if delta:
            yield delta


def _mock_chain_analysis(industry: str) -> dict:
    return {
        "summary": {"market_size": "¥1.2T (2024)", "growth_rate": "+18.3%", "overall_rating": "B+", "opportunity_count": 14, "high_confidence_count": 3},
        "upstream": [
            {"name": "锂矿资源", "opp_level": "high", "summary": "供需缺口扩大，价格有望企稳反弹"},
            {"name": "正极材料", "opp_level": "high", "summary": "产能出清加速，龙头集中度提升"},
            {"name": "负极材料", "opp_level": "mid", "summary": "硅碳负极渗透率提升带来结构性机会"},
        ],
        "midstream": [
            {"name": "动力电池", "opp_level": "high", "summary": "宁德时代以外二线厂商份额提升"},
            {"name": "智能座舱", "opp_level": "high", "summary": "渗透率快速提升，芯片国产替代"},
            {"name": "电机电控", "opp_level": "mid", "summary": "国产替代持续推进"},
        ],
        "downstream": [
            {"name": "充换电桩", "opp_level": "high", "summary": "政策驱动，保有量快速增长"},
            {"name": "V2G储能", "opp_level": "high", "summary": "商业化拐点临近"},
            {"name": "整车品牌", "opp_level": "mid", "summary": "竞争格局分化加剧"},
        ],
    }


def _mock_report(industry: str) -> str:
    return f"""# 投资研究报告 — {industry}产业链

## 核心判断

中游分化加剧，动力电池及智能化零部件具备阶段性配置价值。上游锂矿短期价格压力仍存，建议等待企稳信号后再介入。

## 机会优先级排序

1. **正极材料** — 供需缺口，确信度 87%，时间窗口 6-12 个月
2. **充换电基础设施** — 政策驱动，确信度 79%，时间窗口 12-24 个月
3. **智能座舱芯片** — 技术渗透，确信度 62%，时间窗口 18-36 个月

## 风险矩阵

### 高风险因素
- 国内价格战持续压缩毛利率
- 欧美关税壁垒上升
- 原材料价格剧烈波动

### 正向催化剂
- 以旧换新政策持续发力
- 固态电池量产时间表清晰
- 出海东南亚市场加速

## 关键标的推荐

1. **宁德时代 (300750)** — 动力电池龙头，技术壁垒高
2. **比亚迪 (002594)** — 垂直整合优势明显
3. **亿纬锂能 (300014)** — 二线电池厂弹性最大
"""
