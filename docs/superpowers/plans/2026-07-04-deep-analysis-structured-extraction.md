# Implementation Plan: Deep Analysis Structured Extraction

**Spec:** `docs/superpowers/specs/2026-07-04-deep-analysis-structured-extraction-design.md`
**Date:** 2026-07-04
**Scope:** B = 6 模板路由 + 结构化 JSON 输出 + 前端 Tab 化展示

## Goal

把 `analyze_stream` 的「单一 markdown prompt」升级为「按企业类型路由的 6 模板分桶结构化提取」,产出 `{value, evidence, quote}` 三件套,前端按桶 Tab 展示,每桶完成即推送 SSE 事件。

## Architecture

```
backend/app/services/deep_analysis/         # 新子包
├── __init__.py          # 公共接口 re-export
├── templates.py         # 6 prompt 模板 + ROUTING_TABLE + BUCKET_FIELD_DEFS
├── schemas.py           # FieldValue / BucketResult / AnalysisDoc (Pydantic v2)
├── analyzer.py          # run_single_bucket + parse_bucket_result + AnalyzerError
├── runner.py            # orchestrate + build_analysis_doc
├── streaming.py         # 7 SSE 事件格式化
└── storage.py           # load_markdown / make_cache_key / load_cached / save_structured / load_history

backend/app/services/deep_analysis_service.py   # 改造为薄 facade,re-export 子包公共 API
backend/app/routers/deep_analysis.py            # /analyze 端点改为调 runner.orchestrate
backend/app/models/models.py                    # DeepAnalysis 加 3 字段
backend/app/main.py                             # startup 加 ensure_deep_analysis_columns

backend/tests/
├── conftest.py                          # 新:共享 test_db / client fixture
├── test_deep_analysis_templates.py      # 新
├── test_deep_analysis_schemas.py        # 新
├── test_deep_analysis_streaming.py      # 新
├── test_deep_analysis_storage.py        # 新
├── test_deep_analysis_analyzer.py       # 新
├── test_deep_analysis_runner.py         # 新
├── test_deep_analysis.py                # 改:更新 SSE 事件名 + cache_key 算法
└── test_analyze_smoke.py                # 新:标记 @pytest.mark.smoke

frontend/src/
├── types/deepAnalysis.ts                # 加 FieldValue/BucketResult/AnalysisDoc/CompanyType 类型
├── services/api.ts                      # streamAnalyze 加 company_type + 新事件回调
├── components/deep-analysis/
│   ├── CompanyTypeSelector.tsx          # 新
│   ├── BucketTabs.tsx                   # 新
│   ├── BucketFieldCard.tsx              # 新
│   └── AnalysisResultStep.tsx           # 重写
├── pages/DeepAnalysisPage.tsx           # 加 companyType state
└── pages/deep-analysis.css              # 加 Tab/卡片样式
```

## Tech Stack

- **Backend:** FastAPI · SQLAlchemy 2.0 (async engine + sync session) · Pydantic v2 · sse-starlette · OpenAI SDK (sync `OpenAI` client — 用 `asyncio.to_thread` 包装)
- **Frontend:** React + TypeScript · fetch + ReadableStream (NOT EventSource) · Vite
- **Test:** pytest 9 + pytest-mock (用 `asyncio.run` 测 async 函数,不引入 pytest-asyncio)
- **DB:** SQLite,启动时 `PRAGMA table_info` + 条件 `ALTER TABLE ADD COLUMN`(不引入 Alembic)

## Global Constraints

1. **Sync OpenAI client 包装**:`llm_service.client` 是 SYNC `OpenAI(...)`,在 async 上下文必须用 `await asyncio.to_thread(...)` 调用,避免阻塞事件循环。
2. **前端 SSE 解析沿用 fetch+ReadableStream**:不引入 `EventSource`,扩展 `api.ts:streamAnalyze` 的 line parser 即可。
3. **`analysis_text` 列在老 DB 是 nullable=False**:v2 记录写 `analysis_text=""`(空串),不要写 NULL。新 DB 由 model 决定(去掉 nullable=False)。
4. **Cache key 升级**:新算法包含 `company_type`,16 字符;老算法 64 字符 → 不会碰撞。老记录不动。
5. **Pydantic v2 语法**:`model_dump()` / `model_validate()`,不写 v1 的 `.dict()` / `.parse_obj()`。
6. **不引入新依赖**:pytest-asyncio、Alembic、前端 vitest 都不开。
7. **TDD 节奏**:每个任务先写测试,看红,再写实现,看绿。每个任务结束 commit 一次。

---

## Task 1: DB Schema + Migration Helper

**Goal:** 给 `DeepAnalysis` 模型加 3 个字段,启动时自动 ALTER TABLE 补列。

**Files:**
- Modify: `backend/app/models/models.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_deep_analysis.py::test_history_format`(已有,只需保证不回归)

**Interface:**
- Consumes: 现有 `Base` / `async_engine`
- Produces: `DeepAnalysis.analysis_struct_json` / `analysis_version` / `company_type` 三列;`ensure_deep_analysis_columns()` 启动执行

### Steps

- [ ] 修改 `backend/app/models/models.py` 的 `DeepAnalysis` 类:

```python
class DeepAnalysis(Base):
    __tablename__ = "deep_analyses"
    id = Column(Integer, primary_key=True)
    stock_code = Column(String, nullable=False, index=True)
    oss_keys_json = Column(String, nullable=False)
    cache_key = Column(String, nullable=False, unique=True, index=True)
    analysis_text = Column(Text)                       # 改:去掉 nullable=False
    analysis_struct_json = Column(Text)                # 新
    analysis_version = Column(String, default="v1")    # 新
    company_type = Column(String)                      # 新
    model_name = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)
```

- [ ] 在 `backend/app/main.py` 加迁移函数,并在 `startup()` 里调用:

```python
def _run_migrations(conn):
    """SQLite-friendly: create_all 后,补齐 deep_analyses 的新列(老库)。"""
    from sqlalchemy import text
    Base.metadata.create_all(conn)
    cols = [r[1] for r in conn.exec_driver_sql("PRAGMA table_info(deep_analyses)")]
    if "analysis_struct_json" not in cols:
        conn.exec_driver_sql("ALTER TABLE deep_analyses ADD COLUMN analysis_struct_json TEXT")
    if "analysis_version" not in cols:
        conn.exec_driver_sql(
            "ALTER TABLE deep_analyses ADD COLUMN analysis_version VARCHAR DEFAULT 'v1'"
        )
    if "company_type" not in cols:
        conn.exec_driver_sql("ALTER TABLE deep_analyses ADD COLUMN company_type VARCHAR")


@app.on_event("startup")
async def startup():
    from app.db import async_engine, Base
    from app.models.models import (
        ChainAnalysis, DataCache, Report, InvestmentPlan,
        ReportContent, DeepAnalysis,
    )
    from app.models import chain_models  # noqa: F401
    async with async_engine.begin() as conn:
        await conn.run_sync(_run_migrations)
```

- [ ] 删除已有 SQLite 文件测试一遍:`cd backend && python -c "from app.main import app"` 应不报错。
- [ ] 跑 `pytest backend/tests/test_deep_analysis.py::test_history_format`(应仍绿,因为新列对老逻辑透明)。
- [ ] Commit:`feat(deep-analysis): add 3 columns to DeepAnalysis for v2 structured extraction`

---

## Task 2: schemas.py

**Goal:** 定义 FieldValue / BucketResult / AnalysisDoc 三个 Pydantic 模型。

**Files:**
- Create: `backend/app/services/deep_analysis/__init__.py`(空文件占位)
- Create: `backend/app/services/deep_analysis/schemas.py`
- Test: `backend/tests/test_deep_analysis_schemas.py`

**Interface:**
- Consumes: `pydantic>=2.0.0`
- Produces: `FieldValue`, `BucketResult`, `AnalysisDoc`

### Steps

- [ ] 写测试 `backend/tests/test_deep_analysis_schemas.py`:

```python
"""FieldValue / BucketResult / AnalysisDoc 单元测试。"""
import pytest
from pydantic import ValidationError

from app.services.deep_analysis.schemas import FieldValue, BucketResult, AnalysisDoc


def test_field_value_accepts_string():
    fv = FieldValue(value="约15%", evidence="medium", quote="...")
    assert fv.value == "约15%"
    assert fv.evidence == "medium"


def test_field_value_accepts_list():
    fv = FieldValue(value=["北方华创", "中微公司"], evidence="strong")
    assert isinstance(fv.value, list)


def test_field_value_accepts_null_defaults():
    fv = FieldValue()
    assert fv.value is None
    assert fv.evidence == "unknown"
    assert fv.quote is None


def test_field_value_rejects_bad_evidence():
    with pytest.raises(ValidationError):
        FieldValue(value="x", evidence="bogus")


def test_bucket_result_accepts_dict_fields():
    br = BucketResult(bucket_id="industry_chain", fields={
        "domestic_share": FieldValue(value="15%", evidence="medium"),
    })
    assert br.bucket_id == "industry_chain"
    assert "domestic_share" in br.fields


def test_analysis_doc_stats_default():
    doc = AnalysisDoc(
        company_type="equipment", stock_code="688120",
        buckets=[], analyzed_at="2026-07-04T10:00:00Z",
    )
    assert doc.version == "v2"
    assert doc.stats == {"ok": 0, "error": 0, "total": 0}
```

- [ ] 跑测试,确认全部失败(`ModuleNotFoundError`)。
- [ ] 创建 `backend/app/services/deep_analysis/__init__.py`(空)。
- [ ] 创建 `backend/app/services/deep_analysis/schemas.py`:

```python
"""Structured extraction schemas (Pydantic v2)."""
from __future__ import annotations

from typing import Literal, Union
from pydantic import BaseModel, Field


FieldValueT = Union[str, int, float, list[str], None]


class FieldValue(BaseModel):
    """单字段三件套。找不到的字段统一填 {value:null, evidence:"unknown", quote:null}。"""
    value: FieldValueT = None
    evidence: Literal["strong", "medium", "weak", "unknown"] = "unknown"
    quote: str | None = None


class BucketResult(BaseModel):
    """单桶结果。fields 是 dict 而非固定字段,允许不同 bucket 有不同字段集。"""
    bucket_id: str
    fields: dict[str, FieldValue] = Field(default_factory=dict)


class AnalysisDoc(BaseModel):
    """完整结构化分析文档(持久化到 analysis_struct_json)。"""
    version: Literal["v2"] = "v2"
    company_type: str
    stock_code: str
    buckets: list[BucketResult]
    analyzed_at: str  # ISO 8601 UTC
    model_name: str = ""
    stats: dict[str, int] = Field(
        default_factory=lambda: {"ok": 0, "error": 0, "total": 0}
    )
```

- [ ] 跑测试,应全绿。
- [ ] Commit:`feat(deep-analysis): add schemas for structured extraction`

---

## Task 3: templates.py

**Goal:** 写 6 个 bucket prompt 模板、ROUTING_TABLE、BUCKET_FIELD_DEFS。

**Files:**
- Create: `backend/app/services/deep_analysis/templates.py`
- Test: `backend/tests/test_deep_analysis_templates.py`

**Interface:**
- Consumes: 无(纯常量)
- Produces: `BUCKET_TEMPLATES: dict[str, str]`、`ROUTING_TABLE: dict[str, list[str]]`、`BUCKET_FIELD_DEFS: dict[str, list[str]]`、`BUCKET_DISPLAY_NAMES: dict[str, str]`、`COMPANY_TYPES: list[str]`、`COMPANY_TYPE_LABELS: dict[str, str]`

### Steps

- [ ] 写测试 `backend/tests/test_deep_analysis_templates.py`:

```python
"""templates.py: 6 模板 + 路由表 + 字段定义的约束校验。"""
import pytest

from app.services.deep_analysis.templates import (
    BUCKET_TEMPLATES, ROUTING_TABLE, BUCKET_FIELD_DEFS,
    BUCKET_DISPLAY_NAMES, COMPANY_TYPES, COMPANY_TYPE_LABELS,
)


def test_six_buckets_exist():
    expected = {"industry_chain", "equipment", "material", "financial", "risk", "catalyst"}
    assert set(BUCKET_TEMPLATES.keys()) == expected
    assert set(BUCKET_FIELD_DEFS.keys()) == expected
    assert set(BUCKET_DISPLAY_NAMES.keys()) == expected


@pytest.mark.parametrize("bid", list(BUCKET_TEMPLATES.keys()))
def test_template_has_markdown_placeholder(bid):
    assert "{markdown}" in BUCKET_TEMPLATES[bid], f"{bid} 模板缺 {{markdown}} 占位符"


@pytest.mark.parametrize("bid", list(BUCKET_TEMPLATES.keys()))
def test_template_has_json_keyword(bid):
    """DeepSeek JSON 模式要求 prompt 含 'json' 关键字。"""
    assert "json" in BUCKET_TEMPLATES[bid].lower(), f"{bid} 模板缺 'json' 关键字"


@pytest.mark.parametrize("bid", list(BUCKET_TEMPLATES.keys()))
def test_template_lists_all_declared_fields(bid):
    """模板必须提及 BUCKET_FIELD_DEFS[bid] 中所有字段名。"""
    tpl = BUCKET_TEMPLATES[bid]
    for field in BUCKET_FIELD_DEFS[bid]:
        assert field in tpl, f"{bid} 模板未提及字段 {field}"


def test_routing_table_has_5_company_types():
    expected = {"equipment", "material", "packaging", "ip", "general"}
    assert set(ROUTING_TABLE.keys()) == expected


def test_routing_values_subset_of_buckets():
    for cid, buckets in ROUTING_TABLE.items():
        for b in buckets:
            assert b in BUCKET_TEMPLATES, f"{cid} 路由到未知 bucket {b}"


def test_company_types_match_routing():
    assert set(COMPANY_TYPES) == set(ROUTING_TABLE.keys())
    assert set(COMPANY_TYPE_LABELS.keys()) == set(ROUTING_TABLE.keys())
    assert COMPANY_TYPE_LABELS["general"] == "综合"


def test_general_route_excludes_equipment_and_material():
    """综合模式不跑 equipment/material 专属桶。"""
    assert "equipment" not in ROUTING_TABLE["general"]
    assert "material" not in ROUTING_TABLE["general"]


def test_equipment_route_includes_equipment_bucket():
    assert "equipment" in ROUTING_TABLE["equipment"]
    assert "material" not in ROUTING_TABLE["equipment"]


def test_material_route_includes_material_bucket():
    assert "material" in ROUTING_TABLE["material"]
    assert "equipment" not in ROUTING_TABLE["material"]
```

- [ ] 跑测试,确认全红。
- [ ] 创建 `backend/app/services/deep_analysis/templates.py`:

```python
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
```

- [ ] 跑测试,应全绿。
- [ ] Commit:`feat(deep-analysis): add 6 prompt templates + routing table`

---

## Task 4: streaming.py

**Goal:** 7 种 SSE 事件的格式化函数,产出 `{event, data}` dict 供 `EventSourceResponse` 直接 yield。

**Files:**
- Create: `backend/app/services/deep_analysis/streaming.py`
- Test: `backend/tests/test_deep_analysis_streaming.py`

**Interface:**
- Consumes: `schemas.BucketResult`, `schemas.AnalysisDoc`
- Produces: `format_start / format_bucket_start / format_bucket_done / format_bucket_error / format_cached / format_error / format_done`

### Steps

- [ ] 写测试 `backend/tests/test_deep_analysis_streaming.py`:

```python
"""streaming.py: 7 种 SSE 事件格式化。"""
import json

from app.services.deep_analysis.schemas import BucketResult, FieldValue, AnalysisDoc
from app.services.deep_analysis.streaming import (
    format_start, format_bucket_start, format_bucket_done,
    format_bucket_error, format_cached, format_error, format_done,
)


def test_start_emits_bucket_list():
    evt = format_start(company_type="equipment", bucket_ids=["industry_chain", "equipment"])
    assert evt["event"] == "start"
    payload = json.loads(evt["data"])
    assert payload["version"] == "v2"
    assert payload["company_type"] == "equipment"
    assert payload["buckets"] == ["industry_chain", "equipment"]


def test_bucket_start():
    assert format_bucket_start("industry_chain") == {
        "event": "bucket_start",
        "data": json.dumps({"bucket_id": "industry_chain"}, ensure_ascii=False),
    }


def test_bucket_done_includes_serialized_result():
    br = BucketResult(bucket_id="financial", fields={"x": FieldValue(value="1", evidence="strong")})
    evt = format_bucket_done(br)
    assert evt["event"] == "bucket_done"
    payload = json.loads(evt["data"])
    assert payload["bucket_id"] == "financial"
    assert payload["result"]["fields"]["x"]["value"] == "1"


def test_bucket_error():
    evt = format_bucket_error("financial", "JSON parse failed after 1 retry")
    assert evt["event"] == "bucket_error"
    payload = json.loads(evt["data"])
    assert payload["bucket_id"] == "financial"
    assert "JSON parse" in payload["error"]


def test_cached_serializes_full_doc():
    doc = AnalysisDoc(
        company_type="general", stock_code="301095",
        buckets=[], analyzed_at="2026-07-04T10:00:00Z",
    )
    evt = format_cached(doc)
    assert evt["event"] == "cached"
    payload = json.loads(evt["data"])
    assert payload["stock_code"] == "301095"


def test_error_short_circuit():
    evt = format_error(reason="markdown_too_short", extra={"len": 42})
    payload = json.loads(evt["data"])
    assert payload["reason"] == "markdown_too_short"
    assert payload["len"] == 42


def test_done_has_counts():
    evt = format_done(analysis_id=42, ok_count=4, error_count=1, total=5)
    payload = json.loads(evt["data"])
    assert payload == {"version": "v2", "analysis_id": 42, "ok_count": 4, "error_count": 1, "total": 5}


def test_chinese_quote_not_mangled():
    """UTF-8 中文不乱码。"""
    br = BucketResult(bucket_id="industry_chain",
                      fields={"x": FieldValue(value="国产化率约15%", evidence="medium", quote="原文片段")})
    evt = format_bucket_done(br)
    assert "国产化率" in evt["data"]
    assert "原文片段" in evt["data"]
```

- [ ] 跑测试,确认全红。
- [ ] 创建 `backend/app/services/deep_analysis/streaming.py`:

```python
"""SSE event formatters: 产出 {event, data} dict 供 EventSourceResponse yield。"""
from __future__ import annotations

import json
from typing import Any

from app.services.deep_analysis.schemas import AnalysisDoc, BucketResult


def _emit(event: str, payload: dict[str, Any]) -> dict[str, str]:
    return {"event": event, "data": json.dumps(payload, ensure_ascii=False)}


def format_start(company_type: str, bucket_ids: list[str]) -> dict[str, str]:
    return _emit("start", {
        "version": "v2",
        "company_type": company_type,
        "buckets": bucket_ids,
    })


def format_bucket_start(bucket_id: str) -> dict[str, str]:
    return _emit("bucket_start", {"bucket_id": bucket_id})


def format_bucket_done(result: BucketResult) -> dict[str, str]:
    return _emit("bucket_done", {
        "bucket_id": result.bucket_id,
        "result": result.model_dump(),
    })


def format_bucket_error(bucket_id: str, error: str) -> dict[str, str]:
    return _emit("bucket_error", {"bucket_id": bucket_id, "error": error})


def format_cached(doc: AnalysisDoc) -> dict[str, str]:
    return _emit("cached", doc.model_dump())


def format_error(reason: str, extra: dict[str, Any] | None = None) -> dict[str, str]:
    payload = {"reason": reason}
    if extra:
        payload.update(extra)
    return _emit("error", payload)


def format_done(analysis_id: int, ok_count: int, error_count: int, total: int) -> dict[str, str]:
    return _emit("done", {
        "version": "v2",
        "analysis_id": analysis_id,
        "ok_count": ok_count,
        "error_count": error_count,
        "total": total,
    })
```

- [ ] 跑测试,应全绿。
- [ ] Commit:`feat(deep-analysis): add SSE event formatters`

---

## Task 5: storage.py + conftest.py

**Goal:** DB CRUD:加载 markdown / 算 cache_key / 读写 AnalysisDoc / 历史。同时建共享 conftest。

**Files:**
- Create: `backend/tests/conftest.py`
- Create: `backend/app/services/deep_analysis/storage.py`
- Test: `backend/tests/test_deep_analysis_storage.py`

**Interface:**
- Consumes: `models.ReportContent`, `models.DeepAnalysis`, `schemas.AnalysisDoc`
- Produces:
  - `load_markdown(db, code, oss_keys) -> str | None`
  - `make_cache_key(code, oss_keys, company_type) -> str`(16 字符)
  - `load_cached(db, code, oss_keys, company_type) -> AnalysisDoc | None`
  - `save_structured(db, code, oss_keys, company_type, doc) -> int`(返回 analysis_id)
  - `load_history(db, code, limit=20) -> list[dict]`

### Steps

- [ ] 创建 `backend/tests/conftest.py`(供后续测试共享):

```python
"""Shared fixtures for deep-analysis tests."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base, get_db
from app.main import app


@pytest.fixture(scope="function")
def test_db():
    """每测试独立 in-memory SQLite。"""
    engine = create_engine(
        "sqlite:///:memory:",
        echo=False,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = Session()
    yield db
    db.close()
    engine.dispose()


@pytest.fixture(scope="function")
def client(test_db):
    """TestClient with injected DB."""
    def override_get_db():
        try:
            yield test_db
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
```

- [ ] 写测试 `backend/tests/test_deep_analysis_storage.py`:

```python
"""storage.py: markdown 加载、cache_key、AnalysisDoc 持久化。"""
import json
from datetime import datetime

import pytest

from app.models.models import ReportContent, DeepAnalysis
from app.services.deep_analysis import storage
from app.services.deep_analysis.schemas import (
    AnalysisDoc, BucketResult, FieldValue,
)


# ── load_markdown ────────────────────────────────────────────────────

def test_load_markdown_concatenates_multiple_reports(test_db):
    test_db.add(ReportContent(
        oss_key="a.pdf", stock_code="301095", title="R1",
        markdown_text="AAA", token_count=1, parsed_at=datetime.now(),
    ))
    test_db.add(ReportContent(
        oss_key="b.pdf", stock_code="301095", title="R2",
        markdown_text="BBB", token_count=1, parsed_at=datetime.now(),
    ))
    test_db.commit()
    md = storage.load_markdown(test_db, "301095", ["a.pdf", "b.pdf"])
    assert "AAA" in md
    assert "BBB" in md
    assert "---" in md  # 分隔符


def test_load_markdown_returns_none_if_any_missing(test_db):
    test_db.add(ReportContent(
        oss_key="a.pdf", stock_code="301095", title="R1",
        markdown_text="AAA", token_count=1, parsed_at=datetime.now(),
    ))
    test_db.commit()
    # b.pdf 不存在
    assert storage.load_markdown(test_db, "301095", ["a.pdf", "b.pdf"]) is None


def test_load_markdown_empty_keys_returns_none(test_db):
    assert storage.load_markdown(test_db, "301095", []) is None


# ── make_cache_key ───────────────────────────────────────────────────

def test_cache_key_is_16_chars():
    key = storage.make_cache_key("301095", ["a.pdf"], "equipment")
    assert len(key) == 16


def test_cache_key_differs_by_company_type():
    k1 = storage.make_cache_key("301095", ["a.pdf"], "equipment")
    k2 = storage.make_cache_key("301095", ["a.pdf"], "material")
    assert k1 != k2


def test_cache_key_independent_of_order():
    k1 = storage.make_cache_key("301095", ["a.pdf", "b.pdf"], "general")
    k2 = storage.make_cache_key("301095", ["b.pdf", "a.pdf"], "general")
    assert k1 == k2


# ── save_structured + load_cached ───────────────────────────────────

def _make_doc(company_type="equipment", stock_code="301095"):
    return AnalysisDoc(
        company_type=company_type, stock_code=stock_code,
        buckets=[BucketResult(bucket_id="industry_chain",
                              fields={"x": FieldValue(value="15%", evidence="medium")})],
        analyzed_at="2026-07-04T10:00:00Z",
        model_name="deepseek-chat",
        stats={"ok": 1, "error": 0, "total": 1},
    )


def test_save_and_load_roundtrip(test_db):
    doc = _make_doc()
    aid = storage.save_structured(
        test_db, "301095", ["a.pdf"], "equipment", doc,
    )
    assert isinstance(aid, int)

    loaded = storage.load_cached(test_db, "301095", ["a.pdf"], "equipment")
    assert loaded is not None
    assert loaded.company_type == "equipment"
    assert loaded.buckets[0].bucket_id == "industry_chain"
    assert loaded.buckets[0].fields["x"].value == "15%"


def test_load_cached_returns_none_for_v1_records(test_db):
    """老 v1 记录(无 analysis_struct_json)load_cached 应返回 None。"""
    test_db.add(DeepAnalysis(
        stock_code="301095",
        oss_keys_json=json.dumps(["a.pdf"]),
        cache_key="k" * 16,
        analysis_text="# 老的 markdown",
        analysis_version="v1",
        model_name="deepseek-chat",
        created_at=datetime.now(),
    ))
    test_db.commit()
    # 即使 cache_key 算法不同,这里也直接验 v1 不被 v2 视为 cached
    assert storage.load_cached(test_db, "301095", ["a.pdf"], "equipment") is None


def test_save_structured_writes_empty_analysis_text(test_db):
    """v2 记录 analysis_text 必须写空串(列在老 DB 是 nullable=False)。"""
    doc = _make_doc()
    aid = storage.save_structured(
        test_db, "301095", ["a.pdf"], "equipment", doc,
    )
    rec = test_db.query(DeepAnalysis).filter(DeepAnalysis.id == aid).one()
    assert rec.analysis_text == ""
    assert rec.analysis_version == "v2"
    assert rec.company_type == "equipment"


def test_save_structured_overwrites_same_cache_key(test_db):
    doc1 = _make_doc()
    aid1 = storage.save_structured(test_db, "301095", ["a.pdf"], "equipment", doc1)
    doc2 = AnalysisDoc(
        company_type="equipment", stock_code="301095",
        buckets=[], analyzed_at="2026-07-04T11:00:00Z",
        stats={"ok": 0, "error": 0, "total": 0},
    )
    aid2 = storage.save_structured(test_db, "301095", ["a.pdf"], "equipment", doc2)
    assert aid1 == aid2  # 覆盖,不新增
    assert test_db.query(DeepAnalysis).count() == 1


# ── load_history ────────────────────────────────────────────────────

def test_load_history_returns_v2_records_with_metadata(test_db):
    doc = _make_doc()
    storage.save_structured(test_db, "301095", ["a.pdf"], "equipment", doc)
    history = storage.load_history(test_db, "301095")
    assert len(history) == 1
    item = history[0]
    assert item["analysis_version"] == "v2"
    assert item["company_type"] == "equipment"
    assert item["id"] > 0
```

- [ ] 跑测试,确认全红。
- [ ] 创建 `backend/app/services/deep_analysis/storage.py`:

```python
"""DB CRUD for structured analysis."""
from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime

from sqlalchemy.orm import Session

from app.models.models import ReportContent, DeepAnalysis
from app.services.deep_analysis.schemas import AnalysisDoc

logger = logging.getLogger(__name__)

_MARKDOWN_SEPARATOR = "\n\n---\n\n"


def load_markdown(db: Session, code: str, oss_keys: list[str]) -> str | None:
    """按 oss_keys 顺序取多份 markdown,用分隔符拼接。任一缺失 → 返回 None。"""
    if not oss_keys:
        return None
    records = (
        db.query(ReportContent)
        .filter(
            ReportContent.stock_code == code,
            ReportContent.oss_key.in_(oss_keys),
        )
        .all()
    )
    by_key = {r.oss_key: r for r in records}
    parts: list[str] = []
    for k in oss_keys:
        rec = by_key.get(k)
        if rec is None or not rec.markdown_text:
            return None
        parts.append(rec.markdown_text)
    return _MARKDOWN_SEPARATOR.join(parts)


def make_cache_key(code: str, oss_keys: list[str], company_type: str) -> str:
    """sha256(code|sorted_keys|company_type)[:16] — 16 字符,与老 64 字符算法不冲突。"""
    sorted_keys = sorted(oss_keys)
    raw = f"{code}|{','.join(sorted_keys)}|{company_type}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def load_cached(
    db: Session, code: str, oss_keys: list[str], company_type: str,
) -> AnalysisDoc | None:
    """命中 v2 缓存返回 AnalysisDoc,否则 None。v1 记录不算命中。"""
    cache_key = make_cache_key(code, oss_keys, company_type)
    rec = db.query(DeepAnalysis).filter(DeepAnalysis.cache_key == cache_key).first()
    if rec is None or rec.analysis_version != "v2" or not rec.analysis_struct_json:
        return None
    return AnalysisDoc.model_validate(json.loads(rec.analysis_struct_json))


def save_structured(
    db: Session, code: str, oss_keys: list[str],
    company_type: str, doc: AnalysisDoc,
) -> int:
    """持久化 v2 AnalysisDoc,返回 analysis_id。同 cache_key 覆盖。"""
    cache_key = make_cache_key(code, oss_keys, company_type)
    payload = doc.model_dump_json(ensure_ascii=False)
    existing = db.query(DeepAnalysis).filter(DeepAnalysis.cache_key == cache_key).first()
    if existing:
        existing.analysis_struct_json = payload
        existing.analysis_version = "v2"
        existing.company_type = company_type
        existing.analysis_text = ""  # 列在老 DB 是 nullable=False
        existing.model_name = doc.model_name or existing.model_name
        existing.created_at = datetime.now()
        db.commit()
        return existing.id
    rec = DeepAnalysis(
        stock_code=code,
        oss_keys_json=json.dumps(oss_keys, ensure_ascii=False),
        cache_key=cache_key,
        analysis_text="",
        analysis_struct_json=payload,
        analysis_version="v2",
        company_type=company_type,
        model_name=doc.model_name or "",
        created_at=datetime.now(),
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)
    return rec.id


def load_history(db: Session, code: str, limit: int = 20) -> list[dict]:
    """该股票历史分析列表,最新优先。"""
    records = (
        db.query(DeepAnalysis)
        .filter(DeepAnalysis.stock_code == code)
        .order_by(DeepAnalysis.created_at.desc())
        .limit(limit)
        .all()
    )
    out: list[dict] = []
    for r in records:
        preview = ""
        if r.analysis_version == "v2" and r.analysis_struct_json:
            try:
                doc = AnalysisDoc.model_validate(json.loads(r.analysis_struct_json))
                preview = f"[v2] {doc.company_type} · {doc.stats.get('ok', 0)}/{doc.stats.get('total', 0)} 桶"
            except Exception:
                preview = "[v2 解析失败]"
        else:
            preview = (r.analysis_text or "")[:120]
        out.append({
            "id": r.id,
            "created_at": r.created_at.isoformat() if r.created_at else "",
            "model_name": r.model_name or "",
            "report_count": len(json.loads(r.oss_keys_json or "[]")),
            "preview": preview,
            "analysis_version": r.analysis_version or "v1",
            "company_type": r.company_type or "",
        })
    return out
```

- [ ] 跑测试,应全绿。
- [ ] Commit:`feat(deep-analysis): add storage layer with v2 schema support`

---

## Task 6: analyzer.py

**Goal:** 单桶 LLM 调用 + JSON 严格解析 + 重试 1 次 + 缺字段自动补 unknown。

**Files:**
- Create: `backend/app/services/deep_analysis/analyzer.py`
- Test: `backend/tests/test_deep_analysis_analyzer.py`

**Interface:**
- Consumes: `templates.BUCKET_TEMPLATES`, `templates.BUCKET_FIELD_DEFS`, `schemas.BucketResult` / `FieldValue`, `llm_service.client`, `app.config.MODEL_NAME`
- Produces: `AnalyzerError`(异常)、`run_single_bucket(bucket_id, markdown_text) -> BucketResult`(async)、`parse_bucket_result(bucket_id, raw_str) -> BucketResult`(sync helper)

### Steps

- [ ] 写测试 `backend/tests/test_deep_analysis_analyzer.py`:

```python
"""analyzer.py: 单桶 LLM 调用 + 重试 + schema 补全。"""
import asyncio
import json
from unittest.mock import MagicMock, patch

import pytest

from app.services.deep_analysis.analyzer import (
    AnalyzerError, parse_bucket_result, run_single_bucket,
)
from app.services.deep_analysis.schemas import BucketResult


def _mock_resp(content: str, finish_reason: str = "stop"):
    m = MagicMock()
    m.choices = [MagicMock()]
    m.choices[0].message.content = content
    m.choices[0].finish_reason = finish_reason
    return m


# ── parse_bucket_result ─────────────────────────────────────────────

def test_parse_happy_path():
    raw = json.dumps({
        "bucket_id": "industry_chain",
        "fields": {
            "domestic_share": {"value": "15%", "evidence": "medium", "quote": "..."},
        },
    })
    br = parse_bucket_result("industry_chain", raw)
    assert isinstance(br, BucketResult)
    assert br.fields["domestic_share"].value == "15%"


def test_parse_missing_field_auto_filled():
    """模板声明的字段缺失,自动补 unknown,不抛错。"""
    raw = json.dumps({
        "bucket_id": "industry_chain",
        "fields": {"domestic_share": {"value": "15%"}},
    })
    br = parse_bucket_result("industry_chain", raw)
    # industry_chain 在 BUCKET_FIELD_DEFS 声明 5 个字段
    assert len(br.fields) == 5
    assert br.fields["competitors"].evidence == "unknown"
    assert br.fields["competitors"].value is None


def test_parse_extra_field_ignored():
    raw = json.dumps({
        "bucket_id": "industry_chain",
        "fields": {
            "domestic_share": {"value": "x"},
            "unknown_field": {"value": "y"},
        },
    })
    br = parse_bucket_result("industry_chain", raw)
    assert "unknown_field" not in br.fields


def test_parse_invalid_json_raises_value_error():
    with pytest.raises(ValueError):
        parse_bucket_result("industry_chain", "not a json")


# ── run_single_bucket ───────────────────────────────────────────────

def test_happy_path_single_call(mocker):
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = _mock_resp(json.dumps({
        "bucket_id": "industry_chain",
        "fields": {"domestic_share": {"value": "15%", "evidence": "medium"}},
    }))
    mocker.patch("app.services.deep_analysis.analyzer.llm_client", mock_client)

    result = asyncio.run(run_single_bucket("industry_chain", "...markdown..."))
    assert isinstance(result, BucketResult)
    assert mock_client.chat.completions.create.call_count == 1


def test_retry_on_invalid_json_then_success(mocker):
    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = [
        _mock_resp("not a json"),
        _mock_resp(json.dumps({
            "bucket_id": "industry_chain",
            "fields": {"domestic_share": {"value": "15%"}},
        })),
    ]
    mocker.patch("app.services.deep_analysis.analyzer.llm_client", mock_client)

    result = asyncio.run(run_single_bucket("industry_chain", "...md..."))
    assert isinstance(result, BucketResult)
    assert mock_client.chat.completions.create.call_count == 2


def test_give_up_after_two_bad_jsons(mocker):
    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = [
        _mock_resp("bad1"),
        _mock_resp("bad2"),
    ]
    mocker.patch("app.services.deep_analysis.analyzer.llm_client", mock_client)

    with pytest.raises(AnalyzerError, match="JSON parse failed after retry"):
        asyncio.run(run_single_bucket("industry_chain", "...md..."))


def test_missing_field_does_not_retry(mocker):
    """缺字段 → 直接补 unknown,不重试。"""
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = _mock_resp(json.dumps({
        "bucket_id": "industry_chain",
        "fields": {"domestic_share": {"value": "x"}},  # 只给 1 个,缺 4 个
    }))
    mocker.patch("app.services.deep_analysis.analyzer.llm_client", mock_client)

    result = asyncio.run(run_single_bucket("industry_chain", "...md..."))
    assert len(result.fields) == 5  # 5 个字段都被填充
    assert mock_client.chat.completions.create.call_count == 1


def test_finish_reason_length_triggers_retry(mocker):
    """LLM 输出截断(finish_reason=length)视为 JSON 失败,触发重试。"""
    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = [
        _mock_resp('{"bucket_id":"industry_chain","fields":', finish_reason="length"),
        _mock_resp(json.dumps({
            "bucket_id": "industry_chain",
            "fields": {"domestic_share": {"value": "15%"}},
        })),
    ]
    mocker.patch("app.services.deep_analysis.analyzer.llm_client", mock_client)

    result = asyncio.run(run_single_bucket("industry_chain", "...md..."))
    assert isinstance(result, BucketResult)
    assert mock_client.chat.completions.create.call_count == 2


def test_llm_call_exception_raises_analyzer_error(mocker):
    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = RuntimeError("network timeout")
    mocker.patch("app.services.deep_analysis.analyzer.llm_client", mock_client)

    with pytest.raises(AnalyzerError, match="LLM call failed"):
        asyncio.run(run_single_bucket("industry_chain", "...md..."))
```

- [ ] 跑测试,确认全红。
- [ ] 创建 `backend/app/services/deep_analysis/analyzer.py`:

```python
"""Single-bucket LLM call with retry and schema completion."""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from pydantic import ValidationError

from app.config import MODEL_NAME
from app.services import llm_service
from app.services.deep_analysis.schemas import BucketResult, FieldValue
from app.services.deep_analysis.templates import (
    BUCKET_FIELD_DEFS, BUCKET_TEMPLATES,
)

logger = logging.getLogger(__name__)

BUCKET_SYSTEM_PROMPT = """你是研报结构化解析器。必须输出严格 JSON,不要 markdown 代码块。
所有声明的字段必须出现;找不到的字段填 {"value":null,"evidence":"unknown","quote":null}。"""

MAX_TOKENS = 2000
TIMEOUT_SECONDS = 60


class AnalyzerError(Exception):
    """单桶解析失败的统一异常。"""


def parse_bucket_result(bucket_id: str, raw_str: str) -> BucketResult:
    """json.loads → 补缺字段 → 忽略多余字段。非法 JSON 抛 ValueError(触发重试)。"""
    data = json.loads(raw_str)  # 可能抛 JSONDecodeError(是 ValueError 的子类)
    if not isinstance(data, dict):
        raise ValueError(f"top-level not dict: {type(data).__name__}")

    fields_in = data.get("fields", {}) if isinstance(data.get("fields"), dict) else {}
    expected = BUCKET_FIELD_DEFS.get(bucket_id, [])
    fields_out: dict[str, FieldValue] = {}
    for name in expected:
        raw = fields_in.get(name)
        if raw is None:
            fields_out[name] = FieldValue()
        else:
            try:
                fields_out[name] = FieldValue.model_validate(raw)
            except ValidationError:
                fields_out[name] = FieldValue()
    return BucketResult(bucket_id=bucket_id, fields=fields_out)


async def run_single_bucket(bucket_id: str, markdown_text: str) -> BucketResult:
    """调用 LLM,重试 1 次。返回 BucketResult 或抛 AnalyzerError。"""
    template = BUCKET_TEMPLATES[bucket_id]
    user_prompt = template.replace("{markdown}", markdown_text)

    llm_client = llm_service.client
    if llm_client is None:
        raise AnalyzerError("LLM client not configured (DEEPSEEK_API_KEY missing)")

    last_err: Exception | None = None
    for attempt, temp in [(0, 0.1), (1, 0.0)]:
        try:
            resp = await asyncio.to_thread(
                llm_client.chat.completions.create,
                model=MODEL_NAME,
                messages=[
                    {"role": "system", "content": BUCKET_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                response_format={"type": "json_object"},
                max_tokens=MAX_TOKENS,
                temperature=temp,
                timeout=TIMEOUT_SECONDS,
            )
            finish_reason = resp.choices[0].finish_reason
            content = resp.choices[0].message.content or ""
            if finish_reason == "length":
                # 视为 JSON 解析失败,触发重试
                raise ValueError(f"finish_reason=length (truncated output)")
            return parse_bucket_result(bucket_id, content)
        except ValueError as e:
            last_err = e
            logger.warning("bucket %s attempt %d failed: %s", bucket_id, attempt, e)
            continue
        except Exception as e:
            raise AnalyzerError(f"LLM call failed: {type(e).__name__}: {e}") from e

    raise AnalyzerError(f"JSON parse failed after retry: {last_err}")
```

- [ ] 跑测试,应全绿。
- [ ] Commit:`feat(deep-analysis): add single-bucket analyzer with retry`

---

## Task 7: runner.py

**Goal:** `orchestrate` async generator + `build_analysis_doc` helper。

**Files:**
- Create: `backend/app/services/deep_analysis/runner.py`
- Test: `backend/tests/test_deep_analysis_runner.py`

**Interface:**
- Consumes: `templates.ROUTING_TABLE`, `analyzer.run_single_bucket`, `storage.*`, `streaming.*`, `schemas.AnalysisDoc`
- Produces:
  - `build_analysis_doc(company_type, code, accumulator, model_name, error_count) -> AnalysisDoc`
  - `async def orchestrate(db, code, oss_keys, company_type, force_refresh) -> AsyncIterator[dict]`

### Steps

- [ ] 写测试 `backend/tests/test_deep_analysis_runner.py`:

```python
"""runner.py: orchestrate async generator + build_analysis_doc."""
import asyncio
import json
from datetime import datetime
from unittest.mock import MagicMock

import pytest

from app.models.models import ReportContent
from app.services.deep_analysis import runner, storage
from app.services.deep_analysis.analyzer import AnalyzerError
from app.services.deep_analysis.schemas import BucketResult, FieldValue


def _seed_markdown(test_db, code="301095", keys=("a.pdf",), text=None):
    for k in keys:
        test_db.add(ReportContent(
            oss_key=k, stock_code=code, title=f"R-{k}",
            markdown_text=text or ("研报正文 " * 50),
            token_count=10, parsed_at=datetime.now(),
        ))
    test_db.commit()


def _collect_events(gen):
    """同步收集 async generator 产出的所有事件。"""
    out = []
    async def drain():
        async for evt in gen:
            out.append(evt)
    asyncio.run(drain())
    return out


# ── build_analysis_doc ──────────────────────────────────────────────

def test_build_analysis_doc_computes_stats():
    buckets = [
        BucketResult(bucket_id="industry_chain", fields={"x": FieldValue(value="1")}),
        BucketResult(bucket_id="financial",      fields={"y": FieldValue(value="2")}),
    ]
    doc = runner.build_analysis_doc(
        company_type="general", code="301095",
        accumulator=buckets, model_name="deepseek-chat", error_count=1,
    )
    assert doc.version == "v2"
    assert doc.company_type == "general"
    assert doc.stock_code == "301095"
    assert doc.model_name == "deepseek-chat"
    assert doc.stats == {"ok": 2, "error": 1, "total": 3}
    assert len(doc.buckets) == 2
    assert doc.analyzed_at  # 非空 ISO 字符串


# ── orchestrate: happy path ─────────────────────────────────────────

def test_orchestrate_emits_correct_event_sequence(test_db, mocker):
    _seed_markdown(test_db)
    # mock analyzer: 不调真实 LLM,直接返回 BucketResult
    async def fake_run(bucket_id, md):
        return BucketResult(
            bucket_id=bucket_id,
            fields={"x": FieldValue(value="ok", evidence="strong")},
        )
    mocker.patch("app.services.deep_analysis.runner.run_single_bucket", fake_run)

    events = _collect_events(runner.orchestrate(
        test_db, "301095", ["a.pdf"], "general", force_refresh=False,
    ))

    event_types = [e["event"] for e in events]
    assert event_types[0] == "start"
    assert event_types[-1] == "done"
    # general 路由 4 个桶
    assert event_types.count("bucket_start") == 4
    assert event_types.count("bucket_done") == 4
    assert "bucket_error" not in event_types

    # start 事件包含桶列表
    start_payload = json.loads(events[0]["data"])
    assert start_payload["company_type"] == "general"
    assert start_payload["buckets"] == ["industry_chain", "financial", "risk", "catalyst"]


def test_orchestrate_cached_returns_single_cached_event(test_db):
    """命中缓存:只发 cached 事件,不发 start/bucket_*/done。"""
    _seed_markdown(test_db)
    # 预存 v2 记录
    from app.services.deep_analysis.schemas import AnalysisDoc
    doc = AnalysisDoc(
        company_type="general", stock_code="301095",
        buckets=[], analyzed_at="2026-07-04T10:00:00Z",
    )
    storage.save_structured(test_db, "301095", ["a.pdf"], "general", doc)

    events = _collect_events(runner.orchestrate(
        test_db, "301095", ["a.pdf"], "general", force_refresh=False,
    ))

    assert len(events) == 1
    assert events[0]["event"] == "cached"


# ── orchestrate: error paths ────────────────────────────────────────

def test_orchestrate_short_markdown_short_circuits(test_db, mocker):
    _seed_markdown(test_db, text="短")  # < 200 字
    events = _collect_events(runner.orchestrate(
        test_db, "301095", ["a.pdf"], "general", force_refresh=False,
    ))
    event_types = [e["event"] for e in events]
    # 短路:error + done,没有 start / bucket_*
    assert "start" not in event_types
    assert "bucket_start" not in event_types
    assert "error" in event_types
    assert event_types[-1] == "done"


def test_orchestrate_missing_markdown_short_circuits(test_db, mocker):
    """load_markdown 返回 None 时也短路。"""
    events = _collect_events(runner.orchestrate(
        test_db, "301095", ["nonexistent.pdf"], "general", force_refresh=False,
    ))
    event_types = [e["event"] for e in events]
    assert "error" in event_types
    assert "start" not in event_types


def test_orchestrate_continues_after_bucket_failure(test_db, mocker):
    _seed_markdown(test_db)
    call_count = {"n": 0}

    async def fake_run(bucket_id, md):
        call_count["n"] += 1
        if bucket_id == "financial":
            raise AnalyzerError("simulated failure")
        return BucketResult(bucket_id=bucket_id, fields={})

    mocker.patch("app.services.deep_analysis.runner.run_single_bucket", fake_run)

    events = _collect_events(runner.orchestrate(
        test_db, "301095", ["a.pdf"], "general", force_refresh=False,
    ))

    event_types = [e["event"] for e in events]
    assert event_types.count("bucket_start") == 4
    assert event_types.count("bucket_done") == 3
    assert event_types.count("bucket_error") == 1
    assert event_types[-1] == "done"
    # done 事件含 error_count=1
    done_payload = json.loads(events[-1]["data"])
    assert done_payload["error_count"] == 1
    assert done_payload["ok_count"] == 3
    assert call_count["n"] == 4  # 4 个桶都调了,没中断


def test_orchestrate_force_refresh_bypasses_cache(test_db, mocker):
    _seed_markdown(test_db)
    from app.services.deep_analysis.schemas import AnalysisDoc
    doc = AnalysisDoc(
        company_type="general", stock_code="301095",
        buckets=[], analyzed_at="2026-07-04T10:00:00Z",
    )
    storage.save_structured(test_db, "301095", ["a.pdf"], "general", doc)

    async def fake_run(bucket_id, md):
        return BucketResult(bucket_id=bucket_id, fields={})
    mocker.patch("app.services.deep_analysis.runner.run_single_bucket", fake_run)

    events = _collect_events(runner.orchestrate(
        test_db, "301095", ["a.pdf"], "general", force_refresh=True,
    ))
    event_types = [e["event"] for e in events]
    assert "cached" not in event_types
    assert event_types[0] == "start"
```

- [ ] 跑测试,确认全红。
- [ ] 创建 `backend/app/services/deep_analysis/runner.py`:

```python
"""orchestrate: 按 company_type 路由 → 串行调 analyzer → 拼装 AnalysisDoc。"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import AsyncIterator

from sqlalchemy.orm import Session

from app.config import MODEL_NAME
from app.services.deep_analysis import storage, streaming
from app.services.deep_analysis.analyzer import AnalyzerError, run_single_bucket
from app.services.deep_analysis.schemas import AnalysisDoc, BucketResult
from app.services.deep_analysis.templates import ROUTING_TABLE

logger = logging.getLogger(__name__)

MIN_MARKDOWN_LEN = 200


def build_analysis_doc(
    company_type: str,
    code: str,
    accumulator: list[BucketResult],
    model_name: str,
    error_count: int,
) -> AnalysisDoc:
    """把 accumulator 拼成 AnalysisDoc,自动算 stats。"""
    ok = len(accumulator)
    total = ok + error_count
    return AnalysisDoc(
        company_type=company_type,
        stock_code=code,
        buckets=list(accumulator),
        analyzed_at=datetime.now(timezone.utc).isoformat(),
        model_name=model_name,
        stats={"ok": ok, "error": error_count, "total": total},
    )


async def orchestrate(
    db: Session,
    code: str,
    oss_keys: list[str],
    company_type: str,
    force_refresh: bool,
) -> AsyncIterator[dict]:
    """主流程 async generator。yield SSE {event, data} dict。"""
    # 1. 缓存命中检查
    if not force_refresh:
        cached = storage.load_cached(db, code, oss_keys, company_type)
        if cached is not None:
            yield streaming.format_cached(cached)
            return

    # 2. 加载 markdown
    markdown_text = storage.load_markdown(db, code, oss_keys)
    if markdown_text is None:
        yield streaming.format_error("markdown_not_found", {"oss_keys": oss_keys})
        yield streaming.format_done(analysis_id=0, ok_count=0, error_count=0, total=0)
        return
    if len(markdown_text) < MIN_MARKDOWN_LEN:
        yield streaming.format_error(
            "markdown_too_short", {"len": len(markdown_text), "min": MIN_MARKDOWN_LEN},
        )
        yield streaming.format_done(analysis_id=0, ok_count=0, error_count=0, total=0)
        return

    # 3. 路由
    bucket_ids = ROUTING_TABLE[company_type]
    yield streaming.format_start(company_type, bucket_ids)

    # 4. 串行调 analyzer
    accumulator: list[BucketResult] = []
    error_count = 0
    for bid in bucket_ids:
        yield streaming.format_bucket_start(bid)
        try:
            result = await run_single_bucket(bid, markdown_text)
            yield streaming.format_bucket_done(result)
            accumulator.append(result)
        except AnalyzerError as e:
            logger.warning("bucket %s failed: %s", bid, e)
            yield streaming.format_bucket_error(bid, str(e))
            error_count += 1
            continue

    # 5. 持久化 + done
    doc = build_analysis_doc(
        company_type=company_type, code=code,
        accumulator=accumulator, model_name=MODEL_NAME,
        error_count=error_count,
    )
    try:
        analysis_id = storage.save_structured(db, code, oss_keys, company_type, doc)
    except Exception as e:
        logger.exception("save_structured failed: %s", e)
        analysis_id = 0

    yield streaming.format_done(
        analysis_id=analysis_id,
        ok_count=len(accumulator),
        error_count=error_count,
        total=len(bucket_ids),
    )
```

- [ ] 跑测试,应全绿。
- [ ] Commit:`feat(deep-analysis): add orchestrate runner with bucket streaming`

---

## Task 8: Sub-package __init__.py + facade refactor

**Goal:** 把 `deep_analysis_service.py` 改成薄 facade,所有内部调用迁移到子包。

**Files:**
- Modify: `backend/app/services/deep_analysis/__init__.py`
- Modify: `backend/app/services/deep_analysis_service.py`

**Interface:**
- Sub-package `__init__.py` re-exports: `orchestrate`, `load_history`, `load_cached`
- `deep_analysis_service.py` 保留:`parse_reports`、`parse_status`、`get_cached_markdown`(这些不涉及结构化分析,保持原样);新增:`orchestrate`、`load_history_v2`、`load_cached_v2` 的 re-export(供老调用方迁移)

### Steps

- [ ] 修改 `backend/app/services/deep_analysis/__init__.py`:

```python
"""Deep analysis structured extraction subpackage.

Public API:
- orchestrate: SSE async generator(替代老 analyze_stream)
- load_history: 历史列表(支持 v1/v2 混合)
- load_cached: 命中 v2 缓存
"""
from app.services.deep_analysis.runner import orchestrate, build_analysis_doc
from app.services.deep_analysis.storage import (
    load_markdown, load_cached, load_history, save_structured, make_cache_key,
)
from app.services.deep_analysis.analyzer import run_single_bucket, AnalyzerError
from app.services.deep_analysis.schemas import (
    FieldValue, BucketResult, AnalysisDoc,
)
from app.services.deep_analysis.templates import (
    BUCKET_TEMPLATES, ROUTING_TABLE, BUCKET_FIELD_DEFS,
    BUCKET_DISPLAY_NAMES, COMPANY_TYPES, COMPANY_TYPE_LABELS,
)

__all__ = [
    "orchestrate", "build_analysis_doc",
    "load_markdown", "load_cached", "load_history", "save_structured", "make_cache_key",
    "run_single_bucket", "AnalyzerError",
    "FieldValue", "BucketResult", "AnalysisDoc",
    "BUCKET_TEMPLATES", "ROUTING_TABLE", "BUCKET_FIELD_DEFS",
    "BUCKET_DISPLAY_NAMES", "COMPANY_TYPES", "COMPANY_TYPE_LABELS",
]
```

- [ ] 修改 `backend/app/services/deep_analysis_service.py`:在文件顶部 imports 后加 re-export,在文件底部删除 `analyze_stream`、`_persist_analysis`、`get_cached_analysis`、`compute_cache_key`、`_truncate_reports`、`_build_prompt`、`ANALYSIS_PROMPT_TEMPLATE`、`_mock_analysis`(这些都迁移完毕)。

最终文件应只保留 `parse_reports` / `parse_status` / `get_cached_markdown` / `list_history` / `get_analysis_by_id`(这些是 Step 1/2/3 的服务,不涉及结构化分析)+ 子包 re-export:

```python
"""
Deep analysis service — facade.

历史职责:
- Step 1/2 PDF 解析编排(parse_reports / parse_status / get_cached_markdown)→ 保留
- Step 4 结构化分析(orchestrate / load_history / load_cached)→ 委托给 deep_analysis 子包
"""
from __future__ import annotations

# Step 1/2 PDF 解析(保留原样)
from app.services.mineru_service import estimate_tokens as _estimate_tokens  # noqa: F401

# 从老 _persist 等迁移走的逻辑(导入子包以保持向后兼容)
from app.services.deep_analysis import (
    orchestrate,
    load_history as _load_history_v2,
    load_cached as _load_cached_v2,
)

# === 保留的 PDF 解析函数(从原文件裁剪后保留)===
# parse_reports / parse_status / get_cached_markdown 函数体保持原样
# (它们不涉及结构化分析,无需改动)

# === 历史/缓存统一入口(委托给子包)===
def list_history(code: str, db, limit: int = 20) -> dict:
    """历史列表(支持 v1/v2 混合)。返回子包的 dict 列表 + 包装。"""
    items = _load_history_v2(db, code, limit)
    return {"code": code, "analyses": items}


def get_analysis_by_id(analysis_id: int, db) -> dict | None:
    """按 id 拉单条。"""
    from app.models.models import DeepAnalysis
    import json
    r = db.query(DeepAnalysis).filter(DeepAnalysis.id == analysis_id).first()
    if not r:
        return None
    return {
        "id": r.id,
        "stock_code": r.stock_code,
        "oss_keys": json.loads(r.oss_keys_json or "[]"),
        "analysis_text": r.analysis_text or "",
        "analysis_struct": json.loads(r.analysis_struct_json) if r.analysis_struct_json else None,
        "analysis_version": r.analysis_version or "v1",
        "company_type": r.company_type or "",
        "created_at": r.created_at.isoformat() if r.created_at else "",
        "model_name": r.model_name or "",
    }
```

注意:`parse_reports` / `parse_status` / `get_cached_markdown` 的函数体保持原样不动,只需把它们留在这个文件里。把 `ANALYSIS_PROMPT_TEMPLATE`、`analyze_stream`、`_persist_analysis`、`get_cached_analysis`、`compute_cache_key`、`_truncate_reports`、`_build_prompt`、`_mock_analysis`、`MAX_INPUT_TOKENS` 全部删除。

- [ ] 跑全部已有测试:`pytest backend/tests/test_deep_analysis*.py` 应全绿(router 还没改,但子包 + 老 service 都独立可测)。
- [ ] Commit:`refactor(deep-analysis): migrate to subpackage, slim down facade`

---

## Task 9: Router migration + test_deep_analysis.py updates

**Goal:** `GET /analyze` 端点改造为调 `orchestrate`,加 `company_type` query 参数;更新 `test_deep_analysis.py` 中两个会破裂的测试。

**Files:**
- Modify: `backend/app/routers/deep_analysis.py`
- Modify: `backend/tests/test_deep_analysis.py`

**Interface:**
- `GET /analyze?code=X&oss_keys=a,b&company_type=equipment&force_refresh=false`
- 非法 `company_type` → 422

### Steps

- [ ] 改 `backend/app/routers/deep_analysis.py` 的 `analyze` 端点:

```python
from app.services import deep_analysis_service as svc
from app.services.deep_analysis import orchestrate as _orchestrate
from app.services.deep_analysis.templates import COMPANY_TYPES


@router.get("/analyze")
async def analyze(
    code: str = Query(..., min_length=6, max_length=6, pattern=r"^\d{6}$"),
    oss_keys: str = Query(..., description="逗号分隔的 oss_key 列表"),
    company_type: str = Query("general", description="企业类型"),
    force_refresh: bool = Query(False, description="为 true 时跳过缓存"),
    db: Session = Depends(get_db),
):
    """SSE 流式结构化分析。"""
    keys = [k.strip() for k in oss_keys.split(",") if k.strip()]
    if not keys:
        raise HTTPException(422, "oss_keys 不能为空")
    if company_type not in COMPANY_TYPES:
        raise HTTPException(422, f"invalid company_type: {company_type}")

    async def event_stream():
        try:
            async for evt in _orchestrate(db, code, keys, company_type, force_refresh):
                yield evt
        except Exception as e:
            yield {"event": "error", "data": json.dumps({"error": f"unexpected: {e}"}, ensure_ascii=False)}

    return EventSourceResponse(event_stream())
```

- [ ] 更新 `test_deep_analysis.py`:

  - 删除 `test_analyze_cache_hit`(它预填 v1 markdown 记录期望命中,但新逻辑只命中 v2;改写为 v2 测试)
  - 删除 `test_analyze_force_refresh_skips_cache`(它 mock `analyze_stream` 期望 `chunk` 事件,新事件名是 `bucket_done`)
  - 改写为:

```python
def test_analyze_invalid_company_type_returns_422(client):
    r = client.get(
        "/api/deep-analysis/analyze",
        params={"code": "301095", "oss_keys": "a.pdf", "company_type": "bogus"},
    )
    assert r.status_code == 422


def test_analyze_cache_hit_v2(client, test_db):
    """预填 v2 结构化记录 → /analyze 返回 cached 事件。"""
    from app.services.deep_analysis.schemas import AnalysisDoc
    from app.services.deep_analysis import storage

    oss_keys = ["reports/301095/a.pdf"]
    doc = AnalysisDoc(
        company_type="general", stock_code="301095",
        buckets=[], analyzed_at="2026-07-04T10:00:00Z",
        model_name="deepseek-chat",
    )
    storage.save_structured(test_db, "301095", oss_keys, "general", doc)

    with client.stream(
        "GET", "/api/deep-analysis/analyze",
        params={"code": "301095", "oss_keys": ",".join(oss_keys), "company_type": "general"},
    ) as resp:
        assert resp.status_code == 200
        events = _collect_sse_events(resp)

    event_types = [e["event"] for e in events]
    assert "cached" in event_types
    # cached 单事件,不应有 start/bucket_*
    assert "start" not in event_types
    assert "bucket_done" not in event_types


def test_analyze_force_refresh_emits_start_and_done(client, test_db, monkeypatch):
    """force_refresh=true 时跳过缓存,进入 orchestrate。
    Mock run_single_bucket,验证 start + bucket_done + done 事件序列。"""
    import asyncio
    oss_keys = ["reports/301095/a.pdf"]

    # 预填 v2 缓存(应被绕开)
    from app.services.deep_analysis.schemas import AnalysisDoc
    from app.services.deep_analysis import storage
    doc = AnalysisDoc(
        company_type="general", stock_code="301095",
        buckets=[], analyzed_at="2026-07-04T10:00:00Z",
    )
    storage.save_structured(test_db, "301095", oss_keys, "general", doc)

    # 预填 markdown(orchestrate 需要至少 200 字)
    from app.models.models import ReportContent
    from datetime import datetime
    test_db.add(ReportContent(
        oss_key=oss_keys[0], stock_code="301095", title="R",
        markdown_text="研报正文内容 " * 50,
        token_count=10, parsed_at=datetime.now(),
    ))
    test_db.commit()

    # Mock LLM:每个桶直接返回空 BucketResult
    from app.services.deep_analysis.schemas import BucketResult
    async def fake_run(bucket_id, md):
        return BucketResult(bucket_id=bucket_id, fields={})
    monkeypatch.setattr(
        "app.services.deep_analysis.runner.run_single_bucket", fake_run,
    )

    with client.stream(
        "GET", "/api/deep-analysis/analyze",
        params={
            "code": "301095",
            "oss_keys": ",".join(oss_keys),
            "company_type": "general",
            "force_refresh": "true",
        },
    ) as resp:
        assert resp.status_code == 200
        events = _collect_sse_events(resp)

    event_types = [e["event"] for e in events]
    assert "cached" not in event_types
    assert event_types[0] == "start"
    assert "bucket_done" in event_types
    assert event_types[-1] == "done"
```

- [ ] 删除 `test_deep_analysis.py` 中的 `_compute_key_for_test` helper(不再需要)。
- [ ] 跑全部测试,应全绿。
- [ ] Commit:`feat(deep-analysis): migrate /analyze endpoint to orchestrate + update tests`

---

## Task 10: test_analyze_smoke.py

**Goal:** 真实 LLM smoke 测试,标记 `@pytest.mark.smoke`,默认 CI 跳过。

**Files:**
- Create: `backend/tests/test_analyze_smoke.py`
- Modify: `backend/requirements.txt`(加 `pytest-mock>=3.10` 显式声明,虽然已装)
- Modify: `backend/pytest.ini`(新文件,marker 声明)+ 在 `backend/Dockerfile` 或现有配置不需要改动

### Steps

- [ ] 创建 `backend/pytest.ini`:

```ini
[pytest]
markers =
    smoke: end-to-end tests requiring real API keys (skipped by default)
addopts = -m "not smoke"
testpaths = tests
```

- [ ] 添加 `pytest-mock>=3.10` 到 `backend/requirements.txt` 末尾。
- [ ] 创建 `backend/tests/test_analyze_smoke.py`:

```python
"""
Deep analysis smoke test — 真实 LLM 端到端验证。

默认跳过(标记 @pytest.mark.smoke)。带 DEEPSEEK_API_KEY 时显式运行:
    DEEPSEEK_API_KEY=xxx pytest backend/tests -m smoke
"""
import asyncio
import json
from datetime import datetime

import pytest

from app.config import DEEPSEEK_API_KEY
from app.db import SessionLocal
from app.models.models import Base, ReportContent, DeepAnalysis
from app.services.deep_analysis import orchestrate, storage
from app.services.deep_analysis.schemas import AnalysisDoc
from app.services import llm_service
from app.db import sync_engine


@pytest.mark.smoke
@pytest.mark.skipif(not DEEPSEEK_API_KEY, reason="DEEPSEEK_API_KEY not configured")
def test_smoke_equipment_full_pipeline():
    """真实 LLM,4 个桶(equipment 模式 5 个桶),至少 3 个 bucket_done。"""
    # 准备一份真 markdown(1500 字模拟研报)
    markdown = """
    北方华创(002371)是国内领先的半导体设备厂商,主要产品包括刻蚀机、PVD、CVD、清洗设备等。
    国产化率方面,目前我国半导体设备国产化率约 15%-20%,部分细分领域如刻蚀机已突破 30%。
    主要竞争对手包括中微公司、拓荆科技、芯源微等。客户端认证方面,公司产品已进入中芯国际、
    长江存储、华虹半导体等主流晶圆厂的供应链体系。在产业链环节上,公司位于半导体设备制造中游,
    上游零部件仍有较高进口依赖,下游客户为晶圆代工厂和 IDM 厂商。
    """ * 10  # 重复 10 次凑到 >200 字

    # 用真 DB(测试用 in-memory 避免污染生产)
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()

    try:
        # 灌入 markdown
        db.add(ReportContent(
            oss_key="smoke.pdf", stock_code="002371", title="北方华创深度",
            markdown_text=markdown, token_count=1000, parsed_at=datetime.now(),
        ))
        db.commit()

        # 验证 LLM client 可用
        assert llm_service.client is not None, "DEEPSEEK_API_KEY 未生效"

        # 跑 orchestrate(equipment 模式 5 个桶)
        events = []
        async def collect():
            async for evt in orchestrate(db, "002371", ["smoke.pdf"], "equipment", force_refresh=True):
                events.append(evt)
        asyncio.run(collect())

        event_types = [e["event"] for e in events]
        assert event_types[0] == "start"
        assert event_types[-1] == "done"

        done_bucket_count = event_types.count("bucket_done")
        error_bucket_count = event_types.count("bucket_error")
        # 5 个桶,允许部分失败,但至少 3 个成功
        assert done_bucket_count >= 3, f"只有 {done_bucket_count} 个桶成功(失败 {error_bucket_count})"

        # 验证持久化
        cached = storage.load_cached(db, "002371", ["smoke.pdf"], "equipment")
        assert cached is not None
        assert cached.company_type == "equipment"
        assert len(cached.buckets) >= 3

        # 验证字段提取出了真信息(至少一个非 unknown 字段)
        non_unknown_count = 0
        for bucket in cached.buckets:
            for fv in bucket.fields.values():
                if fv.evidence != "unknown":
                    non_unknown_count += 1
        assert non_unknown_count >= 5, f"提取的非 unknown 字段太少({non_unknown_count} 个)"
    finally:
        db.close()
        engine.dispose()
```

- [ ] 跑 `pytest backend/tests/test_analyze_smoke.py -m smoke`(无 key 时 SKIP)。
- [ ] 跑 `pytest backend/tests/`(无 -m smoke)应全绿且 smoke 测试被跳过。
- [ ] Commit:`test(deep-analysis): add smoke test for real LLM end-to-end`

---

## Task 11: Frontend types + api.ts

**Goal:** 加 FieldValue/BucketResult/AnalysisDoc/CompanyType 类型;扩展 streamAnalyze 支持新事件 + company_type。

**Files:**
- Modify: `frontend/src/types/deepAnalysis.ts`
- Modify: `frontend/src/services/api.ts`

### Steps

- [ ] 在 `frontend/src/types/deepAnalysis.ts` 末尾加:

```typescript
// ── 结构化分析(v2) ─────────────────────────────────────────────

export type CompanyType = 'equipment' | 'material' | 'packaging' | 'ip' | 'general';

export type BucketId = 'industry_chain' | 'equipment' | 'material' | 'financial' | 'risk' | 'catalyst';

export type Evidence = 'strong' | 'medium' | 'weak' | 'unknown';

export interface FieldValue {
  value: string | number | string[] | null;
  evidence: Evidence;
  quote: string | null;
}

export interface BucketResult {
  bucket_id: BucketId;
  fields: Record<string, FieldValue>;
}

export interface AnalysisStats {
  ok: number;
  error: number;
  total: number;
}

export interface AnalysisDoc {
  version: 'v2';
  company_type: CompanyType;
  stock_code: string;
  buckets: BucketResult[];
  analyzed_at: string;
  model_name: string;
  stats: AnalysisStats;
}

export const COMPANY_TYPE_LABELS: Record<CompanyType, string> = {
  equipment: '设备',
  material:  '材料',
  packaging: '封测',
  ip:        'IP',
  general:   '综合',
};

export const BUCKET_DISPLAY_NAMES: Record<BucketId, string> = {
  industry_chain: '产业链与竞争格局',
  equipment:      '设备层指标',
  material:       '材料层指标',
  financial:      '分业务财务',
  risk:           '风险与反证',
  catalyst:       '催化剂与监控',
};
```

- [ ] 更新 `frontend/src/services/api.ts` 的 `AnalyzeStreamCallbacks` 接口和 `streamAnalyze` 函数:

```typescript
import type {
  // ... 原有 ...
  CompanyType,
  BucketId,
  BucketResult,
  AnalysisDoc,
} from '../types/deepAnalysis';
export type {
  // ... 原有 ...
  CompanyType,
  BucketId,
  BucketResult,
  AnalysisDoc,
};

/** SSE 流式分析的回调接口(v2 结构化版本) */
export interface AnalyzeStreamCallbacks {
  onStart?: (payload: { version: 'v2'; company_type: CompanyType; buckets: BucketId[] }) => void;
  onBucketStart?: (bucketId: BucketId) => void;
  onBucketDone?: (bucketId: BucketId, result: BucketResult) => void;
  onBucketError?: (bucketId: BucketId, error: string) => void;
  onCached?: (doc: AnalysisDoc) => void;
  onDone?: (info: { version: 'v2'; analysis_id: number; ok_count: number; error_count: number; total: number }) => void;
  onError?: (err: string) => void;
}

export async function streamAnalyze(
  code: string,
  ossKeys: string[],
  companyType: CompanyType,
  callbacks: AnalyzeStreamCallbacks,
  options: { forceRefresh?: boolean } = {},
): Promise<void> {
  const isDev = import.meta.env.DEV;
  const base = isDev ? 'http://localhost:8000' : '';
  const params = new URLSearchParams({
    code,
    oss_keys: ossKeys.join(','),
    company_type: companyType,
  });
  if (options.forceRefresh) params.append('force_refresh', 'true');

  const resp = await fetch(
    `${base}/api/deep-analysis/analyze?${params.toString()}`,
    { headers: { Accept: 'text/event-stream' } },
  );
  if (!resp.ok || !resp.body) {
    throw new Error(`HTTP ${resp.status}`);
  }

  const reader = resp.body.getReader();
  const decoder = new TextDecoder('utf-8');
  let buffer = '';
  let currentEvent = 'message';

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    const lines = buffer.split('\n');
    buffer = lines.pop() || '';

    for (const line of lines) {
      if (!line.trim()) {
        currentEvent = 'message';
        continue;
      }
      if (line.startsWith('event:')) {
        currentEvent = line.slice(6).trim();
      } else if (line.startsWith('data:')) {
        const payload = line.slice(5).trim();
        try {
          const parsed = JSON.parse(payload);
          switch (currentEvent) {
            case 'start':         callbacks.onStart?.(parsed); break;
            case 'bucket_start':  callbacks.onBucketStart?.(parsed.bucket_id); break;
            case 'bucket_done':   callbacks.onBucketDone?.(parsed.bucket_id, parsed.result); break;
            case 'bucket_error':  callbacks.onBucketError?.(parsed.bucket_id, parsed.error); break;
            case 'cached':        callbacks.onCached?.(parsed); break;
            case 'done':          callbacks.onDone?.(parsed); break;
            case 'error':         callbacks.onError?.(parsed.error || parsed.reason || 'unknown'); break;
          }
        } catch {
          // 忽略解析失败的非 JSON 数据行
        }
        currentEvent = 'message';
      }
    }
  }
}
```

- [ ] `cd frontend && npx tsc --noEmit` 应通过(此时 AnalysisResultStep 还在用旧 callbacks,会报错;先记下,Task 13 修复)。
- [ ] Commit:`feat(frontend): add structured analysis types and streamAnalyze v2`

---

## Task 12: Frontend new components

**Goal:** 新增 CompanyTypeSelector / BucketFieldCard / BucketTabs 三个组件。

**Files:**
- Create: `frontend/src/components/deep-analysis/CompanyTypeSelector.tsx`
- Create: `frontend/src/components/deep-analysis/BucketFieldCard.tsx`
- Create: `frontend/src/components/deep-analysis/BucketTabs.tsx`

### Steps

- [ ] 创建 `CompanyTypeSelector.tsx`:

```tsx
import type { CompanyType } from '../../types/deepAnalysis';
import { COMPANY_TYPE_LABELS } from '../../types/deepAnalysis';

interface Props {
  value: CompanyType;
  onChange: (v: CompanyType) => void;
  disabled?: boolean;
}

const ORDER: CompanyType[] = ['equipment', 'material', 'packaging', 'ip', 'general'];

/**
 * 企业类型 5 档单选(Step 1 顶部)。
 */
export default function CompanyTypeSelector({ value, onChange, disabled }: Props) {
  return (
    <div className="da-company-type-row">
      <span className="da-company-type-label">企业类型</span>
      <div className="da-company-type-options">
        {ORDER.map((ct) => (
          <button
            key={ct}
            type="button"
            className={`da-chip ${value === ct ? 'active' : ''}`}
            onClick={() => onChange(ct)}
            disabled={disabled}
          >
            {COMPANY_TYPE_LABELS[ct]}
          </button>
        ))}
      </div>
    </div>
  );
}
```

- [ ] 创建 `BucketFieldCard.tsx`:

```tsx
import type { FieldValue, Evidence } from '../../types/deepAnalysis';

interface Props {
  name: string;
  field: FieldValue;
}

const EVIDENCE_LABEL: Record<Evidence, string> = {
  strong:  '强证据',
  medium:  '中等证据',
  weak:    '弱证据',
  unknown: '未提及',
};

const EVIDENCE_CLASS: Record<Evidence, string> = {
  strong:  'ev-strong',
  medium:  'ev-medium',
  weak:    'ev-weak',
  unknown: 'ev-unknown',
};

function formatValue(v: FieldValue['value']): string {
  if (v === null || v === undefined) return '—';
  if (Array.isArray(v)) return v.length ? v.join('、') : '—';
  return String(v);
}

/**
 * 单字段卡片:字段名 + value + evidence 色块 + quote 原文。
 */
export default function BucketFieldCard({ name, field }: Props) {
  const evClass = EVIDENCE_CLASS[field.evidence];
  return (
    <div className={`da-field-card ${evClass}`}>
      <div className="da-field-name">{name}</div>
      <div className="da-field-value">{formatValue(field.value)}</div>
      <div className={`da-field-evidence ${evClass}`}>
        {EVIDENCE_LABEL[field.evidence]}
      </div>
      {field.quote && (
        <blockquote className="da-field-quote">"{field.quote}"</blockquote>
      )}
    </div>
  );
}
```

- [ ] 创建 `BucketTabs.tsx`:

```tsx
import { useState } from 'react';
import type { BucketId, BucketResult } from '../../types/deepAnalysis';
import { BUCKET_DISPLAY_NAMES } from '../../types/deepAnalysis';
import BucketFieldCard from './BucketFieldCard';

export type BucketState = 'pending' | 'running' | 'done' | 'error';

interface Props {
  bucketOrder: BucketId[];
  bucketState: Record<BucketId, BucketState>;
  bucketResults: Partial<Record<BucketId, BucketResult>>;
  bucketErrors: Partial<Record<BucketId, string>>;
}

/**
 * Tab 容器:每桶一 Tab,Tab 标题显示状态(灰/spinner/绿✓/红✗)。
 */
export default function BucketTabs({
  bucketOrder, bucketState, bucketResults, bucketErrors,
}: Props) {
  const [active, setActive] = useState<BucketId | null>(null);

  // 默认选第一个 done 的 Tab,否则选第一个
  const defaultActive: BucketId | null =
    active ?? bucketOrder.find((b) => bucketState[b] === 'done') ?? bucketOrder[0] ?? null;

  return (
    <div className="da-bucket-tabs">
      <div className="da-tab-header">
        {bucketOrder.map((bid) => {
          const st = bucketState[bid] || 'pending';
          const isActive = defaultActive === bid;
          return (
            <button
              key={bid}
              type="button"
              className={`da-tab ${isActive ? 'active' : ''} st-${st}`}
              onClick={() => setActive(bid)}
            >
              <span className="da-tab-status">
                {st === 'done' && '✓'}
                {st === 'error' && '✗'}
                {st === 'running' && <span className="da-spinner" />}
                {st === 'pending' && '·'}
              </span>
              <span className="da-tab-label">{BUCKET_DISPLAY_NAMES[bid]}</span>
            </button>
          );
        })}
      </div>

      <div className="da-tab-body">
        {defaultActive && bucketState[defaultActive] === 'done' && bucketResults[defaultActive] && (
          <div className="da-field-grid">
            {Object.entries(bucketResults[defaultActive]!.fields).map(([name, field]) => (
              <BucketFieldCard key={name} name={name} field={field} />
            ))}
          </div>
        )}
        {defaultActive && bucketState[defaultActive] === 'running' && (
          <div className="da-tab-skeleton">解析中...</div>
        )}
        {defaultActive && bucketState[defaultActive] === 'pending' && (
          <div className="da-tab-empty">等待中</div>
        )}
        {defaultActive && bucketState[defaultActive] === 'error' && (
          <div className="da-tab-error">
            该模块解析失败:{bucketErrors[defaultActive] || '未知错误'}
          </div>
        )}
      </div>
    </div>
  );
}
```

- [ ] `cd frontend && npx tsc --noEmit` 应通过。
- [ ] Commit:`feat(frontend): add CompanyTypeSelector / BucketFieldCard / BucketTabs`

---

## Task 13: AnalysisResultStep rewrite + DeepAnalysisPage wiring + CSS

**Goal:** 重写 AnalysisResultStep 用 BucketTabs;DeepAnalysisPage 加 companyType 顶层 state;加 Tab/卡片样式。

**Files:**
- Modify: `frontend/src/components/deep-analysis/AnalysisResultStep.tsx`
- Modify: `frontend/src/components/deep-analysis/ReportSearchStep.tsx`(加 CompanyTypeSelector)
- Modify: `frontend/src/pages/DeepAnalysisPage.tsx`
- Modify: `frontend/src/pages/deep-analysis.css`

### Steps

- [ ] 重写 `AnalysisResultStep.tsx`:

```tsx
import { useEffect, useRef, useState } from 'react';
import { getAnalysisHistory, streamAnalyze } from '../../services/api';
import type {
  CompanyType, BucketId, BucketResult, AnalysisDoc, HistoryItem,
} from '../../types/deepAnalysis';
import BucketTabs, { type BucketState } from './BucketTabs';

interface Props {
  code: string;
  ossKeys: string[];
  companyType: CompanyType;
  onCompanyTypeChange: (v: CompanyType) => void;
  analysisDoc: AnalysisDoc | null;
  onAnalysisDocChange: (doc: AnalysisDoc | null) => void;
  onBack: () => void;
}

type Phase = 'idle' | 'running' | 'cached' | 'done' | 'error';

/**
 * Step 4: 调 SSE 流式结构化分析,按桶 Tab 展示。
 */
export default function AnalysisResultStep({
  code, ossKeys, companyType, onCompanyTypeChange,
  analysisDoc, onAnalysisDocChange, onBack,
}: Props) {
  const [phase, setPhase] = useState<Phase>('idle');
  const [error, setError] = useState('');
  const [showHistory, setShowHistory] = useState(false);
  const [history, setHistory] = useState<HistoryItem[]>([]);
  const [bucketOrder, setBucketOrder] = useState<BucketId[]>([]);
  const [bucketState, setBucketState] = useState<Record<BucketId, BucketState>>({} as Record<BucketId, BucketState>);
  const [bucketResults, setBucketResults] = useState<Partial<Record<BucketId, BucketResult>>>({});
  const [bucketErrors, setBucketErrors] = useState<Partial<Record<BucketId, string>>>({});
  const startedRef = useRef(false);

  useEffect(() => {
    if (startedRef.current) return;
    if (ossKeys.length === 0) return;
    startedRef.current = true;
    runAnalyze(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [code, ossKeys.join(','), companyType]);

  const resetBuckets = () => {
    setBucketOrder([]);
    setBucketState({} as Record<BucketId, BucketState>);
    setBucketResults({});
    setBucketErrors({});
    onAnalysisDocChange(null);
  };

  const runAnalyze = async (forceRefresh: boolean) => {
    if (phase === 'running') return;
    setPhase('running');
    setError('');
    resetBuckets();

    try {
      await streamAnalyze(code, ossKeys, companyType, {
        onStart: (payload) => {
          setBucketOrder(payload.buckets);
          const init: Record<BucketId, BucketState> = {} as Record<BucketId, BucketState>;
          payload.buckets.forEach((b) => { init[b] = 'pending'; });
          setBucketState(init);
        },
        onBucketStart: (bid) => {
          setBucketState((s) => ({ ...s, [bid]: 'running' }));
        },
        onBucketDone: (bid, result) => {
          setBucketState((s) => ({ ...s, [bid]: 'done' }));
          setBucketResults((r) => ({ ...r, [bid]: result }));
        },
        onBucketError: (bid, err) => {
          setBucketState((s) => ({ ...s, [bid]: 'error' }));
          setBucketErrors((e) => ({ ...e, [bid]: err }));
        },
        onCached: (doc) => {
          onAnalysisDocChange(doc);
          setBucketOrder(doc.buckets.map((b) => b.bucket_id));
          const init: Record<BucketId, BucketState> = {} as Record<BucketId, BucketState>;
          doc.buckets.forEach((b) => { init[b.bucket_id] = 'done'; });
          setBucketState(init);
          const rs: Partial<Record<BucketId, BucketResult>> = {};
          doc.buckets.forEach((b) => { rs[b.bucket_id] = b; });
          setBucketResults(rs);
          setPhase('cached');
        },
        onDone: () => {
          setPhase('done');
        },
        onError: (err) => {
          setError(err);
          setPhase('error');
        },
      }, { forceRefresh });
    } catch (e) {
      setError(`分析失败: ${e instanceof Error ? e.message : String(e)}`);
      setPhase('error');
    }
  };

  const toggleHistory = async () => {
    if (!showHistory) {
      try {
        const resp = await getAnalysisHistory(code);
        setHistory(resp.analyses || []);
      } catch (e) {
        console.warn('load history failed', e);
      }
    }
    setShowHistory(!showHistory);
  };

  const okCount = Object.values(bucketState).filter((s) => s === 'done').length;
  const errCount = Object.values(bucketState).filter((s) => s === 'error').length;

  return (
    <div>
      <div className="da-row-between">
        <div>
          <div style={{ fontSize: 18, color: 'var(--ink)', fontFamily: "'Caveat', cursive", fontWeight: 700 }}>
            AI 结构化分析
            {phase === 'cached' && (
              <span className="da-status-meta" style={{ marginLeft: 10, color: 'var(--marker-green)', borderColor: 'var(--marker-green)' }}>
                ✓ 缓存命中
              </span>
            )}
            {phase === 'running' && (
              <span className="da-status-meta" style={{ marginLeft: 6 }}>
                ● 流式中 ({okCount}/{bucketOrder.length})
              </span>
            )}
            {phase === 'done' && (
              <span className="da-status-meta" style={{ marginLeft: 10, color: 'var(--marker-green)', borderColor: 'var(--marker-green)' }}>
                ✓ 完成 {okCount} 桶成功{errCount > 0 && ` / ${errCount} 桶失败`}
              </span>
            )}
          </div>
          <div className="da-meta-cell" style={{ marginTop: 4 }}>
            基于 {ossKeys.length} 篇研报 · 股票代码 {code} · 类型 {companyType}
          </div>
        </div>
        <div className="da-row">
          <button className="da-btn da-btn-ghost" onClick={onBack} disabled={phase === 'running'}>
            ← 返回
          </button>
          <button className="da-btn da-btn-ghost" onClick={toggleHistory}>
            {showHistory ? '隐藏历史' : '🕔 历史'}
          </button>
          <button
            className="da-btn da-btn-primary"
            onClick={() => runAnalyze(true)}
            disabled={phase === 'running' || ossKeys.length === 0}
          >
            {phase === 'running' ? '分析中...' : '↻ 重新分析'}
          </button>
        </div>
      </div>

      {error && <div className="da-error">{error}</div>}

      {showHistory && (
        <div className="da-history-list">
          <div className="da-meta-cell" style={{ marginBottom: 8 }}>
            历史分析({history.length} 条)
          </div>
          {history.length === 0 ? (
            <div className="da-empty">暂无历史</div>
          ) : (
            history.map((h) => (
              <div key={h.id} className="da-history-item">
                <span>#{h.id} · {h.created_at.slice(0, 16).replace('T', ' ')}</span>
                <span style={{ color: 'var(--pencil)' }}>
                  {(h as any).analysis_version === 'v2' ? '[v2] ' : '[v1] '}
                  {(h as any).company_type && `${(h as any).company_type} · `}
                  {h.report_count} 篇 · {(h.preview || '').slice(0, 50)}
                </span>
              </div>
            ))
          )}
        </div>
      )}

      <div style={{ marginTop: 16 }}>
        {bucketOrder.length > 0 ? (
          <BucketTabs
            bucketOrder={bucketOrder}
            bucketState={bucketState}
            bucketResults={bucketResults}
            bucketErrors={bucketErrors}
          />
        ) : (
          <div className="da-empty">
            {phase === 'running' ? '正在初始化...' : '点击「重新分析」开始'}
          </div>
        )}
      </div>
    </div>
  );
}
```

- [ ] 修改 `frontend/src/components/deep-analysis/ReportSearchStep.tsx`:在搜索区域顶部插入 `<CompanyTypeSelector>`。具体修改方式:
  - 加 props `companyType: CompanyType`、`onCompanyTypeChange: (v: CompanyType) => void`
  - 在 component 顶部 JSX 渲染 `<CompanyTypeSelector value={companyType} onChange={onCompanyTypeChange} />`
  - import `CompanyTypeSelector` 和 `CompanyType` 类型

- [ ] 修改 `frontend/src/pages/DeepAnalysisPage.tsx`:

```tsx
import CompanyTypeSelector from '../components/deep-analysis/CompanyTypeSelector';
import type { CompanyType, AnalysisDoc } from '../types/deepAnalysis';
// ... 既有 import

export default function DeepAnalysisPage() {
  // ... 既有 state
  const [companyType, setCompanyType] = useState<CompanyType>('general');
  const [analysisDoc, setAnalysisDoc] = useState<AnalysisDoc | null>(null);

  // ... 既有 handlers,加:
  const handleAnalysisDocChange = useCallback((doc: AnalysisDoc | null) => {
    setAnalysisDoc(doc);
  }, []);

  // ... 渲染时:
  // Step 1 (ReportSearchStep) 加 props:companyType + onCompanyTypeChange
  // Step 4 (AnalysisResultStep) 改 props:
  //   code, ossKeys, companyType, onCompanyTypeChange,
  //   analysisDoc, onAnalysisDocChange, onBack
  // 删除老 props:analysisText, onAnalysisUpdate

  // goToStep 重置时不再清空 analysisText;改为清空 analysisDoc
}
```

- [ ] 在 `frontend/src/pages/deep-analysis.css` 末尾加 Tab/卡片样式:

```css
/* ── v2 结构化分析:Tab + 字段卡片 ── */
.da-company-type-row {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
  padding: 10px 14px;
  background: var(--paper-highlight, rgba(255, 240, 180, 0.4));
  border: 1px dashed var(--ink-light, #999);
  border-radius: 6px;
}
.da-company-type-label {
  font-family: 'Caveat', cursive;
  font-size: 18px;
  color: var(--ink);
  font-weight: 700;
}
.da-company-type-options { display: flex; gap: 8px; flex-wrap: wrap; }
.da-chip {
  padding: 4px 12px;
  background: transparent;
  border: 1px solid var(--ink-light, #aaa);
  border-radius: 14px;
  font-family: 'Caveat', cursive;
  font-size: 16px;
  color: var(--ink);
  cursor: pointer;
  transition: all 0.15s;
}
.da-chip:hover:not(:disabled) { background: rgba(255, 235, 130, 0.5); }
.da-chip.active {
  background: var(--marker-green, #6ec96e);
  border-color: var(--marker-green, #6ec96e);
  color: white;
  font-weight: 600;
}
.da-chip:disabled { opacity: 0.5; cursor: not-allowed; }

/* Bucket Tabs */
.da-bucket-tabs { margin-top: 8px; }
.da-tab-header {
  display: flex;
  gap: 4px;
  border-bottom: 2px solid var(--ink-light, #ccc);
  margin-bottom: 12px;
  flex-wrap: wrap;
}
.da-tab {
  padding: 6px 14px;
  background: transparent;
  border: none;
  border-bottom: 3px solid transparent;
  font-family: 'Caveat', cursive;
  font-size: 17px;
  color: var(--pencil, #888);
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 6px;
}
.da-tab.st-pending { color: var(--pencil, #aaa); }
.da-tab.st-running { color: var(--ink); }
.da-tab.st-done { color: var(--marker-green, #4a8a4a); }
.da-tab.st-error { color: #c0392b; }
.da-tab.active {
  border-bottom-color: var(--ink);
  font-weight: 700;
  background: rgba(255, 235, 130, 0.3);
}
.da-tab-status {
  display: inline-block;
  min-width: 14px;
  font-weight: 700;
}
.da-spinner {
  display: inline-block;
  width: 10px; height: 10px;
  border: 2px solid currentColor;
  border-top-color: transparent;
  border-radius: 50%;
  animation: da-spin 0.8s linear infinite;
}
@keyframes da-spin { to { transform: rotate(360deg); } }

.da-tab-body { min-height: 100px; }
.da-tab-skeleton, .da-tab-empty, .da-tab-error {
  padding: 20px;
  text-align: center;
  font-family: 'Caveat', cursive;
  font-size: 18px;
  color: var(--pencil);
}
.da-tab-error { color: #c0392b; }

/* Field grid */
.da-field-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap: 12px;
}
.da-field-card {
  padding: 10px 12px;
  background: var(--paper, #fffef5);
  border: 1px solid var(--ink-light, #ddd);
  border-radius: 4px;
  border-left: 4px solid var(--pencil, #aaa);
  box-shadow: 1px 1px 0 rgba(0,0,0,0.05);
  transform: rotate(-0.3deg);
  transition: transform 0.15s;
}
.da-field-card:hover { transform: rotate(0); }
.da-field-card.ev-strong  { border-left-color: var(--marker-green, #4a8a4a); }
.da-field-card.ev-medium  { border-left-color: #d4a72c; }
.da-field-card.ev-weak    { border-left-color: #b8783a; }
.da-field-card.ev-unknown { border-left-color: var(--pencil, #aaa); opacity: 0.7; }

.da-field-name {
  font-family: 'Caveat', cursive;
  font-size: 17px;
  color: var(--pencil);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}
.da-field-value {
  font-size: 16px;
  color: var(--ink);
  font-weight: 600;
  margin: 2px 0;
  word-break: break-word;
}
.da-field-evidence {
  display: inline-block;
  font-size: 12px;
  padding: 1px 6px;
  border-radius: 3px;
  font-family: 'Caveat', cursive;
}
.da-field-evidence.ev-strong  { background: rgba(74,138,74,0.2); color: #2a6a2a; }
.da-field-evidence.ev-medium  { background: rgba(212,167,44,0.2); color: #8a6a14; }
.da-field-evidence.ev-weak    { background: rgba(184,120,58,0.2); color: #6a4a14; }
.da-field-evidence.ev-unknown { background: rgba(170,170,170,0.2); color: #666; }
.da-field-quote {
  margin: 6px 0 0;
  padding: 4px 8px;
  border-left: 2px solid var(--pencil, #aaa);
  font-size: 13px;
  color: var(--pencil);
  font-style: italic;
  background: rgba(0,0,0,0.02);
}
```

- [ ] `cd frontend && npx tsc --noEmit` 应通过。
- [ ] `cd frontend && npm run build` 应通过。
- [ ] 手测:启动 backend + frontend,跑一遍完整流程(搜索 → 下载 → 解析 → 分析),验证:
  - Step 1 顶部出现企业类型 5 chip
  - Step 4 出现 Tab,每桶逐个变绿
  - 第一桶 ~12s 完成,显示字段卡片
- [ ] Commit:`feat(frontend): rewrite AnalysisResultStep with bucket tabs + structured display`

---

## Self-Review Checklist

完成全部 13 任务后,跑一遍自检:

- [ ] **Spec 覆盖**:对照 `2026-07-04-deep-analysis-structured-extraction-design.md` 的 7 个核心决策,逐项验证实现:
  - [ ] 6 模板 + 路由 ✓(Task 3)
  - [ ] Step 1 顶部 5 档单选 ✓(Task 12 + 13)
  - [ ] 桶独立串行 + 每桶 SSE 事件 ✓(Task 7)
  - [ ] 字段 `{value, evidence, quote}` ✓(Task 2)
  - [ ] Tab 切换 + 证据色 ✓(Task 12)
  - [ ] DB 3 字段 + 老记录兼容 ✓(Task 1 + 5)
  - [ ] 子包分解 ✓(Task 8)
- [ ] **占位符扫描**:`grep -rn "TODO\|FIXME\|XXX\|<placeholder>" backend/app/services/deep_analysis/ frontend/src/components/deep-analysis/` 应空。
- [ ] **类型一致性**:前端 `BucketResult.fields` 是 `Record<string, FieldValue>`(字段名是 string),后端 Pydantic `BucketResult.fields` 是 `dict[str, FieldValue]`,一致。
- [ ] **测试金字塔**:`pytest backend/tests/` 全绿,smoke 默认跳过。
- [ ] **手动验证**:跑一遍 688120(设备)/ 综合 模式,验证 Tab + 卡片 + 缓存命中路径。

---

## Execution Handoff

本计划共 13 个任务,每个任务对应一个独立 commit。执行方式二选一:

### 方式 A:Subagent-Driven(推荐)
每个任务派一个 subagent 完成:TDD 节奏(先写测试看红 → 写实现看绿 → commit)。父 agent 仅负责派发 + 验收。

### 方式 B:Inline Execution
父 agent 顺序执行所有任务,每个任务内自己跑 TDD 循环。

**选择方式 A 还是 B?**(默认 A)
