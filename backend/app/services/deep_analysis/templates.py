"""6 模板 + 路由表 + 字段定义。

模板内容来源:research-report-data-extraction.md(半导体产业链 6 模板方法论)。
每个模板要求 LLM 输出严格 JSON,缺字段填 {value:null, evidence:"unknown", quote:null}。
"""

# ═══════════════════════════════════════════════════════════════════
# 桶显示名
# ═══════════════════════════════════════════════════════════════════

BUCKET_DISPLAY_NAMES = {
    "industry_chain": "产业链与竞争格局",
    "equipment":      "设备层指标",
    "material":       "材料层指标",
    "financial":      "分业务财务",
    "risk":           "风险与反证",
    "catalyst":       "催化剂与监控",
}

# ═══════════════════════════════════════════════════════════════════
# 企业类型
# ═══════════════════════════════════════════════════════════════════

COMPANY_TYPES = ["equipment", "material", "packaging", "ip", "general"]

COMPANY_TYPE_LABELS = {
    "equipment": "设备",
    "material":  "材料",
    "packaging": "封测",
    "ip":        "IP",
    "general":   "综合",
}

# ═══════════════════════════════════════════════════════════════════
# 路由表
# ═══════════════════════════════════════════════════════════════════

ROUTING_TABLE = {
    "equipment": ["industry_chain", "equipment", "financial", "risk", "catalyst"],
    "material":  ["industry_chain", "material",  "financial", "risk", "catalyst"],
    "packaging": ["industry_chain",              "financial", "risk", "catalyst"],
    "ip":        ["industry_chain",              "financial", "risk", "catalyst"],
    "general":   ["industry_chain",              "financial", "risk", "catalyst"],
}

# ═══════════════════════════════════════════════════════════════════
# 字段定义(每桶 LLM 应输出的字段集;缺失时由 analyzer 自动补 unknown)
# ═══════════════════════════════════════════════════════════════════

BUCKET_FIELD_DEFS = {
    "industry_chain": [
        "domestic_share",          # 国产化率
        "competitors",             # 主要竞争对手(list)
        "certification_stage",     # 客户认证阶段
        "industry_position",       # 行业地位描述
        "value_chain_link",        # 所处产业链环节
    ],
    "equipment": [
        "keyEquipmentModels",      # 核心设备型号
        "targetProcessNode",       # 目标制程节点
        "throughput",              # 设备产能/吞吐
        "yield_rate",              # 良率
        "customer_validation",     # 客户验证进度
    ],
    "material": [
        "key_materials",           # 核心材料(list)
        "purity_grade",            # 纯度等级
        "domestic_suppliers",      # 国产供应商(list)
        "import_dependency",       # 进口依赖度
        "certification_progress",  # 认证进度
    ],
    "financial": [
        "revenue_forecast",        # 营收预测(分业务)
        "gross_margin",            # 毛利率
        "net_profit_forecast",     # 净利润预测
        "pe_band",                 # PE 估值区间
        "growth_drivers",          # 增长驱动(list)
    ],
    "risk": [
        "tech_risk",               # 技术风险
        "market_risk",             # 市场风险
        "policy_risk",             # 政策/贸易战风险
        "supply_chain_risk",       # 供应链风险
        "counter_evidence",        # 反证(看空理由)
    ],
    "catalyst": [
        "short_term_catalyst",     # 短期催化剂
        "long_term_catalyst",      # 长期催化剂
        "monitoring_metrics",      # 监控指标(list)
        "inflection_point",        # 拐点信号
    ],
}

# ═══════════════════════════════════════════════════════════════════
# Prompt 模板(每模板含 {markdown} 占位符 + 'json' 关键字)
# ═══════════════════════════════════════════════════════════════════

_TPL_HEADER = """你是半导体/半导体设备/材料行业研报结构化解析器。
基于以下研报 markdown,提取本桶字段。必须输出严格 JSON,不要 markdown 代码块。

要求的 JSON schema:
{{
  "bucket_id": "{bucket_id}",
  "fields": {{
    "<field_name>": {{ "value": <str|number|list[str]|null>, "evidence": "strong|medium|weak|unknown", "quote": <原文引用|null> }}
  }}
}}

约束:
1. 必须出现以下全部字段:{required_fields}
2. 找不到信息的字段,填 {{"value": null, "evidence": "unknown", "quote": null}}
3. evidence 分级:strong=研报明确给出数字/机构名;medium=研报含糊描述;weak=推断/猜测;unknown=未提及
4. quote 必须是研报原文片段(<= 80 字),找不到则填 null
5. value 如果是 list[str],每项必须是字符串

以下是研报 markdown:

{markdown}
"""

BUCKET_TEMPLATES = {
    "industry_chain": _TPL_HEADER.format(
        bucket_id="industry_chain",
        required_fields=", ".join(BUCKET_FIELD_DEFS["industry_chain"]),
        markdown="{markdown}",
    ),
    "equipment": _TPL_HEADER.format(
        bucket_id="equipment",
        required_fields=", ".join(BUCKET_FIELD_DEFS["equipment"]),
        markdown="{markdown}",
    ),
    "material": _TPL_HEADER.format(
        bucket_id="material",
        required_fields=", ".join(BUCKET_FIELD_DEFS["material"]),
        markdown="{markdown}",
    ),
    "financial": _TPL_HEADER.format(
        bucket_id="financial",
        required_fields=", ".join(BUCKET_FIELD_DEFS["financial"]),
        markdown="{markdown}",
    ),
    "risk": _TPL_HEADER.format(
        bucket_id="risk",
        required_fields=", ".join(BUCKET_FIELD_DEFS["risk"]),
        markdown="{markdown}",
    ),
    "catalyst": _TPL_HEADER.format(
        bucket_id="catalyst",
        required_fields=", ".join(BUCKET_FIELD_DEFS["catalyst"]),
        markdown="{markdown}",
    ),
}
