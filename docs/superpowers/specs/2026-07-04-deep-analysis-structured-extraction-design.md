# Deep Analysis Structured Extraction Design

**Date:** 2026-07-04
**Status:** Pending Review
**Builds on:** `2026-06-30-deep-analysis-pipeline-design.md`
**Scope:** B = 6 模板路由 + 结构化 JSON 输出 + 前端 Tab 化展示

## Overview

将当前 deep-analysis 流水线的"AI 解析大脑"从 1 个通用 markdown prompt 升级为**按企业类型路由的 6 模板分桶结构化提取**,产出 `{value, evidence, quote}` 三件套字段,前端按桶 Tab 展示。

骨架(搜索→下载→MinerU 解析→SSE 分析)不动,改造集中在 `analyze_stream` 服务 + 前端 `AnalysisResultStep` 组件。

方法论来源:项目根 `research-report-data-extraction.md`。

## Core Decisions

| 决策点 | 选定值 |
|---|---|
| 范围 | B(6 模板 + 结构化输出 + 前端结构化展示) |
| 企业类型入口 | 向导 Step 1 顶部单选 5 档:设备/材料/封测/IP/综合,默认"综合" |
| 后端执行 | 桶独立串行调用,每桶完成推送 1 个 SSE 事件 |
| 模板路由 | 设备=1+2+4+5+6 / 材料=1+3+4+5+6 / 封测=IP=综合=1+4+5+6 |
| 字段 schema | `{value, evidence, quote}` 三件套 |
| 前端展示 | Tab 切换(每桶一 Tab),证据色绿/黄/灰 |
| DB 兼容 | 新增 `analysis_struct_json` + `analysis_version` + `company_type` 字段,旧记录 v1 向后兼容 |
| 模板存储 | 单文件 `deep_analysis/templates.py`,6 个 Python 字符串常量 + ROUTING_TABLE dict |
| 后端组织 | 子包分解:`services/deep_analysis/` 含 7 个模块 |

## Architecture

### 后端子包结构

```
backend/app/services/deep_analysis/
├── __init__.py          # 公共接口 re-export
├── templates.py         # 6 个 prompt 模板字符串 + ROUTING_TABLE
├── schemas.py           # Pydantic: FieldValue / BucketResult / AnalysisDoc
├── analyzer.py          # run_single_bucket():单桶 LLM 调用 + JSON 严格解析 + 重试 1 次
├── runner.py            # orchestrate():按 company_type 路由 → 串行调 analyzer → 拼装 AnalysisDoc
├── streaming.py         # SSE 事件格式化:start/bucket_start/bucket_done/bucket_error/error/done/cached
└── storage.py           # DB CRUD:save_structured()/load_cached()/load_history()
```

原 `backend/app/services/deep_analysis_service.py` 保留做向后兼容 re-export,内部调用全部委托给新子包。

### 模块职责

| 模块 | 输入 | 输出 | 依赖 |
|---|---|---|---|
| `templates.py` | — | `DICT[str, str]` 模板 + `DICT[str, list[str]]` 路由 | 纯常量 |
| `schemas.py` | — | Pydantic 类 | 仅 pydantic |
| `analyzer.py` | `(bucket_id, markdown_text)` | `BucketResult` 或 `AnalyzerError` | templates + schemas + llm_service.client |
| `runner.py` | `(code, oss_keys, company_type, db)` | `AsyncIterator[ServerSentEvent]` | templates.ROUTING_TABLE + analyzer + storage + streaming |
| `streaming.py` | BucketResult / 状态对象 | SSE 字符串 | 纯格式化 |
| `storage.py` | DB session + 业务参数 | ORM 对象 | models + schemas |

### Router 改动

`backend/app/routers/deep_analysis.py` 现有 5 个端点结构不动:
- `POST /parse`、`GET /parse-status`、`GET /history`、`GET /records/{id}` 完全不动
- `GET /analyze` 仅做两件事:
  1. 新增 query 参数 `company_type`(默认 `"general"`)
  2. 实现内部从调 `deep_analysis_service.analyze_stream` 改为调 `services.deep_analysis.runner.orchestrate`

### 前端组织

`frontend/src/components/deep-analysis/`:
- `AnalysisResultStep.tsx` 重写
- 新增 `CompanyTypeSelector.tsx`(放 ReportSearchStep 顶部)
- 新增 `BucketTabs.tsx`(Tab 容器)
- 新增 `BucketFieldCard.tsx`(单字段卡片)

`frontend/src/pages/DeepAnalysisPage.tsx` 加 `companyType` 顶层 state。

## Data Contracts

### FieldValue(单字段)

```python
{
  "value": "约15%",                       # str | number | list[str] | null
  "evidence": "medium",                   # "strong" | "medium" | "weak" | "unknown"
  "quote": "XX环节国产化率约15%..."        # str | null
}
```

未提及 = `value=null` + `evidence="unknown"` + `quote=null`。

### BucketResult(单桶)

```python
{
  "bucket_id": "industry_chain",
  "fields": {
    "domestic_share":      { "value": "约15%", "evidence": "medium", "quote": "..." },
    "competitors":         { "value": ["北方华创","中微公司"], "evidence": "medium", "quote": "..." },
    "certification_stage": { "value": null, "evidence": "unknown", "quote": null }
  }
}
```

### bucket_id 枚举与来源模板

| bucket_id | 中文显示 | 来源 |
|---|---|---|
| `industry_chain` | 产业链与竞争格局 | research-report-data-extraction.md §模板 1 |
| `equipment` | 设备层指标 | §模板 2 |
| `material` | 材料层指标 | §模板 3 |
| `financial` | 分业务财务 | §模板 4 |
| `risk` | 风险与反证 | §模板 5 |
| `catalyst` | 催化剂与监控 | §模板 6 |

### AnalysisDoc(完整文档)

```python
{
  "version": "v2",
  "company_type": "equipment",
  "stock_code": "688120",
  "buckets": [BucketResult, ...],
  "analyzed_at": "2026-07-04T11:30:00Z",
  "model_name": "deepseek-chat",
  "stats": { "ok": 4, "error": 1, "total": 5 }
}
```

### ROUTING_TABLE

```python
ROUTING_TABLE = {
    "equipment": ["industry_chain", "equipment", "financial", "risk", "catalyst"],
    "material":  ["industry_chain", "material",  "financial", "risk", "catalyst"],
    "packaging": ["industry_chain",              "financial", "risk", "catalyst"],
    "ip":        ["industry_chain",              "financial", "risk", "catalyst"],
    "general":   ["industry_chain",              "financial", "risk", "catalyst"],
}
```

封测/IP 走综合(无专属模板),后续 P2 迭代时补"封测/IP 专属桶"只需新增模板 + 路由表加一项。

### SSE 事件协议

后端 `sse-starlette` 用具名事件,前端 `EventSource.addEventListener(name, ...)` 监听:

```
event: start
data: {"version":"v2","company_type":"equipment","buckets":["industry_chain","equipment","financial","risk","catalyst"]}

event: bucket_start
data: {"bucket_id":"industry_chain"}

event: bucket_done
data: {"bucket_id":"industry_chain","result":{ /* BucketResult */ }}

event: bucket_error
data: {"bucket_id":"financial","error":"JSON parse failed after 1 retry"}

event: cached
data: { /* 完整 AnalysisDoc,缓存命中时单事件 */ }

event: error
data: {"reason":"markdown_too_short","len":42}

event: done
data: {"version":"v2","analysis_id":123,"ok_count":4,"error_count":1,"total":5}
```

### company_type 传递

`GET /analyze` 是 GET(SSE 要求),走 query 参数:

```
GET /api/deep-analysis/analyze?code=688120&oss_keys=a,b&company_type=equipment
```

## Data Flow

### 前端状态流

`DeepAnalysisPage.tsx` 顶层:

```tsx
type CompanyType = 'equipment' | 'material' | 'packaging' | 'ip' | 'general';
const [companyType, setCompanyType] = useState<CompanyType>('general');
```

`ReportSearchStep` 顶部新增 `<CompanyTypeSelector value onChange />`,Step 2/3 透传不用,Step 4 作为 `streamAnalyze` 第三个参数。

### 后端 orchestrate 生命周期

```
GET /api/deep-analysis/analyze?code=X&oss_keys=a,b&company_type=equipment
  │
  ├─ Router 校验 company_type 合法性(非法 → 422,不进 SSE)
  │
  ├─ storage.load_cached(code, oss_keys, company_type)
  │     │
  │     ├─ 命中 → yield SSE cached { 完整 AnalysisDoc }; return
  │     │
  │     └─ 未命中 → 进 runner.orchestrate()
  │
  └─ runner.orchestrate():
       1. markdown_text = storage.load_markdown(code, oss_keys)  // 多份拼接
       2. 校验 markdown_text 非空且 ≥ 200 字,否则短路 yield error + done
       3. bucket_ids = templates.ROUTING_TABLE[company_type]
       4. yield SSE start { version, company_type, buckets: bucket_ids }
       5. accumulator = []
       6. for bid in bucket_ids:
            yield SSE bucket_start { bucket_id: bid }
            try:
              result = await analyzer.run_single_bucket(bid, markdown_text)
              yield SSE bucket_done { bucket_id: bid, result }
              accumulator.append(result)
            except AnalyzerError as e:
              yield SSE bucket_error { bucket_id: bid, error: str(e) }
              // 不 break,继续下一桶
       7. doc = build_analysis_doc(company_type, code, accumulator, stats)
       8. analysis_id = storage.save_structured(code, oss_keys, company_type, doc)
       9. yield SSE done { analysis_id, ok_count, error_count, total }
```

### 前端 EventSource 监听

```tsx
type Phase = 'idle' | 'running' | 'cached' | 'done' | 'error';
const [phase, setPhase] = useState<Phase>('idle');
const [bucketOrder, setBucketOrder] = useState<BucketId[]>([]);
const [bucketState, setBucketState] = useState<Record<BucketId, 'pending'|'running'|'done'|'error'>>({});
const [analysisDoc, setAnalysisDoc] = useState<AnalysisDoc | null>(null);

const es = new EventSource(url);
es.addEventListener('start',        e => { const d = JSON.parse(e.data); setBucketOrder(d.buckets); ... });
es.addEventListener('bucket_start', e => setBucketState(s => ({...s, [d.bucket_id]: 'running'})));
es.addEventListener('bucket_done',  e => appendToAnalysisDoc(JSON.parse(e.data)));
es.addEventListener('bucket_error', e => setBucketState(s => ({...s, [d.bucket_id]: 'error'})));
es.addEventListener('cached',       e => { setAnalysisDoc(JSON.parse(e.data)); setPhase('cached'); });
es.addEventListener('done',         e => setPhase('done'));
es.addEventListener('error',        e => { /* SSE 'error' event 名 */ setPhase('error'); });
es.onerror = () => setPhase('error');  // 连接级错误
```

注意:浏览器 `EventSource` 的 `error` 事件名与我们业务 SSE 的 `event: error` 冲突。前端用 `addEventListener('error', ...)` 监听业务事件,用 `es.onerror` 监听连接级错误,两者要区分处理。

### 典型时间线(综合模式 4 桶)

```
t=0s     用户点"开始分析" → GET /analyze?...&company_type=general
t=0.5s   收到 start 事件 → Tab 出现 4 个灰色标题
t=0.6s   bucket_start: industry_chain → Tab1 转圈
t=12s    bucket_done: industry_chain → Tab1 绿✓ + 字段卡片可看;Tab2 转圈
t=24s    bucket_done: financial → Tab2 绿✓
t=36s    bucket_done: risk → Tab3 绿✓
t=48s    bucket_done: catalyst → Tab4 绿✓
t=48.5s  done 事件 → phase=done,显示"分析完成,4/4 成功"
```

第一桶 12 秒用户就能看到内容,不必等全部跑完。

## Error Handling

### 失败模式与处理

| # | 失败类型 | 触发条件 | 处理 |
|---|---|---|---|
| 1 | LLM 返回非法 JSON | `json.loads` 抛错 | **重试 1 次**(temperature 降到 0.0),仍失败 → `bucket_error`,继续下一桶 |
| 2 | LLM 返回 JSON 但 schema 不符 | Pydantic ValidationError | 缺失字段填 `{value:null, evidence:"unknown", quote:null}`;多余字段忽略;**不重试** |
| 3 | LLM 调用超时 | 60s 无响应 | 抛 `AnalyzerError` → `bucket_error` 事件 |
| 4 | LLM 输出截断 | `finish_reason="length"` | 视为 JSON 解析失败,走 #1 重试路径 |
| 5 | 单桶失败 | 任何 AnalyzerError | **不中断流**;`done` 事件里 `error_count>0` |
| 6 | markdown_text 太短(<200 字) | OCR 失败/占位 | 整条 orchestrate 短路:1 个 `error` 事件 + `done`,不跑桶 |
| 7 | ReportContent 找不到 | 用户跳过 Step 3 | HTTP 422,**不进 SSE** |
| 8 | 前端连接断 | network / `es.onerror` | 保留已收到 Tab;**不自动重连**(避免重复跑已完成的桶) |
| 9 | 缓存命中但是 v1 markdown | 老记录 | 前端按 version 渲染回退 |

### analyzer 重试伪码

```python
BUCKET_SYSTEM_PROMPT = """
你是研报结构化解析器。必须输出严格 JSON,不要 markdown 代码块。
所有字段必须出现;找不到的字段填 {"value":null,"evidence":"unknown","quote":null}。
"""

async def run_single_bucket(bucket_id: str, markdown_text: str) -> BucketResult:
    template = templates.BUCKET_TEMPLATES[bucket_id]
    last_err = None
    for attempt, temp in [(0, 0.1), (1, 0.0)]:  # 原始 + 1 次重试
        try:
            resp = await llm_service.client.chat.completions.create(
                model=settings.MODEL_NAME,
                messages=[
                    {"role": "system", "content": BUCKET_SYSTEM_PROMPT},
                    {"role": "user",   "content": template.format(markdown=markdown_text)},
                ],
                response_format={"type": "json_object"},  # DeepSeek JSON 模式
                max_tokens=2000,
                temperature=temp,
                timeout=60,
            )
            return parse_bucket_result(bucket_id, resp.choices[0].message.content)
        except (json.JSONDecodeError, ValidationError) as e:
            last_err = e
            continue
        except Exception as e:
            raise AnalyzerError(f"LLM call failed: {type(e).__name__}: {e}")
    raise AnalyzerError(f"JSON parse failed after retry: {last_err}")
```

### 三个关键实现细节

1. **`response_format={"type":"json_object"}` 是 DeepSeek JSON 模式开关**,能极大提高解析率。官方要求 prompt 含 "json" 关键字才生效——`BUCKET_SYSTEM_PROMPT` 已包含。
2. **Schema 缺字段不重试**:LLM 找不到信息重试还是找不到。直接填 unknown,既快又准。
3. **多研报拼接冲突**:Step 1 选多份研报时,`markdown_text` 是多份用 `\n\n---\n\n` 拼接。`quote` 只标原文,不强求来源研报(拼接后丢失边界)。

### Implementation Hints(辅助函数语义)

伪码中引用的几个辅助函数,语义固定如下,实现者无需自行决定:

| 函数 | 所在模块 | 语义 |
|---|---|---|
| `parse_bucket_result(bucket_id, raw_str)` | `analyzer.py` | `json.loads` → 用 BucketResult Pydantic 校验 → 模板里声明的字段缺失时自动填 `{value:null, evidence:"unknown", quote:null}` → 多余字段忽略 → 返回 `BucketResult` |
| `build_analysis_doc(company_type, code, accumulator, model_name)` | `runner.py` | 把 accumulator(list[BucketResult])+ metadata 拼成 `AnalysisDoc`,自动算 `stats.ok/error/total` 和 `analyzed_at=utcnow()` |
| `storage.load_markdown(db, code, oss_keys)` | `storage.py` | 按 oss_keys 顺序从 `ReportContent` 表取多份 `markdown_text`,用 `\n\n---\n\n` 拼接;任一 oss_key 缺失 → 返回 None |
| `storage.make_cache_key(code, oss_keys, company_type)` | `storage.py` | `hashlib.sha256("|".join([code, ",".join(sorted(oss_keys)), company_type]).encode()).hexdigest()[:16]` |
| `templates.BUCKET_TEMPLATES` | `templates.py` | `dict[bucket_id, str]`,6 个 prompt 模板,每个含 `{markdown}` 唯一占位符 |
| `templates.ROUTING_TABLE` | `templates.py` | `dict[company_type, list[bucket_id]]`,5 个 key(见 §ROUTING_TABLE) |

### 前端 Tab 错误视觉

| bucketState | Tab 标题 | Tab 内容 |
|---|---|---|
| pending | 灰色文字 | 空白,提示"等待中" |
| running | spinner + 文字 | 骨架屏 |
| done | 绿色 ✓ + 字段数 | 字段卡片网格 |
| error | 红色 ✗ | "该模块解析失败:[error]。重试单桶功能在 P2 提供" |

## Database Migration

### Schema diff(`backend/app/models/models.py` 的 DeepAnalysis 类)

新增 3 个字段:

```python
class DeepAnalysis(Base):
    __tablename__ = "deep_analyses"
    id = Column(Integer, primary_key=True)
    stock_code = Column(String, nullable=False, index=True)
    oss_keys_json = Column(String, nullable=False)
    cache_key = Column(String, nullable=False, unique=True, index=True)
    analysis_text = Column(Text)                       # v1 markdown,保留
    analysis_struct_json = Column(Text)                 # 🆕 v2+ 结构化 JSON
    analysis_version = Column(String, default="v1")     # 🆕 "v1" | "v2"
    company_type = Column(String)                       # 🆕 冗余,便于过滤
    model_name = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)
```

### 迁移策略:启动时 runtime 检查

不引入 Alembic(与 `CLAUDE.md` "SQLite auto-creates on startup" 惯例一致)。`backend/app/main.py` 的 `startup()` 函数加一个轻量升级:

```python
def ensure_deep_analysis_columns():
    """SQLite-friendly: add new columns to existing tables if missing."""
    with engine.connect() as conn:
        cols = [r[1] for r in conn.exec_driver_sql("PRAGMA table_info(deep_analyses)")]
        if "analysis_struct_json" not in cols:
            conn.exec_driver_sql(
                "ALTER TABLE deep_analyses ADD COLUMN analysis_struct_json TEXT"
            )
        if "analysis_version" not in cols:
            conn.exec_driver_sql(
                "ALTER TABLE deep_analyses ADD COLUMN analysis_version VARCHAR DEFAULT 'v1'"
            )
        if "company_type" not in cols:
            conn.exec_driver_sql(
                "ALTER TABLE deep_analyses ADD COLUMN company_type VARCHAR"
            )
        conn.commit()

@app.on_event("startup")
def startup():
    Base.metadata.create_all(bind=engine)
    ensure_deep_analysis_columns()   # ← 新增 1 行
```

### 老数据兼容

| 字段 | 老记录值 | 行为 |
|---|---|---|
| `analysis_text` | 原 markdown | 保留,前端 v1 视图渲染 |
| `analysis_struct_json` | `NULL` | 前端识别为 v1,走 markdown 渲染 |
| `analysis_version` | `'v1'` (DEFAULT 生效) | 自动填充 |
| `company_type` | `NULL` | 历史列表显示"旧版"标签 |

### Cache key 升级

- **老算法**:`hash(code + sorted(oss_keys))`
- **新算法**:`hash(code + sorted(oss_keys) + company_type)`
- 老记录 `cache_key` 值**不动**(算法不同,新算法算出的 key 不会撞到老记录)
- 用户对老股票重跑直接产生 v2 新记录,不冲突

### 历史 API 改动

`GET /api/deep-analysis/history?code=X` 每条记录多返回 2 字段:`company_type`、`analysis_version`。前端按 version 分流渲染。

## Testing

### 测试金字塔

```
Smoke(真实 LLM,标记 slow)        test_analyze_smoke.py
        ↑
Integration(真实 DB,mock LLM)    test_runner.py / test_api.py
        ↑
Unit(mock 一切)                  test_templates/schemas/analyzer/streaming/storage.py
```

### 单元测试矩阵

| 模块 | 测试文件 | 关键用例 |
|---|---|---|
| templates | `test_templates.py` | ROUTING_TABLE 5 个 key 全覆盖;每模板含 `{markdown}` 占位符;每模板含 "json" 关键字(DeepSeek JSON 模式触发条件) |
| schemas | `test_schemas.py` | FieldValue 类型校验(str/number/list/null);缺字段时 evidence="unknown" 自动补;多余字段忽略 |
| analyzer | `test_analyzer.py` | happy path;非法 JSON 第一次→重试→成功;非法 JSON 两次→AnalyzerError;缺字段→填 unknown 不重试;LLM 超时;`finish_reason="length"` |
| streaming | `test_streaming.py` | 7 种 SSE 事件格式化正确(start/bucket_start/bucket_done/bucket_error/cached/error/done);data 里 JSON 转义无误;UTF-8 中文不乱码 |
| storage | `test_storage.py` | save→load 来回一致;v1 老记录 load 返回 None;不同 company_type 的 cache_key 不碰撞 |

### Analyzer mock 模式

```python
@pytest.fixture
def mock_llm():
    with patch("app.services.deep_analysis.analyzer.llm_service.client") as m:
        m.chat.completions.create = AsyncMock()
        yield m

async def test_retry_on_invalid_json(mock_llm):
    mock_llm.chat.completions.create.side_effect = [
        MockResponse(content="not a json"),
        MockResponse(content='{"bucket_id":"industry_chain","fields":{...}}'),
    ]
    result = await run_single_bucket("industry_chain", "...markdown...")
    assert isinstance(result, BucketResult)
    assert mock_llm.chat.completions.create.call_count == 2

async def test_give_up_after_retry(mock_llm):
    mock_llm.chat.completions.create.side_effect = [
        MockResponse(content="bad1"),
        MockResponse(content="bad2"),
    ]
    with pytest.raises(AnalyzerError, match="JSON parse failed after retry"):
        await run_single_bucket("industry_chain", "...")

async def test_missing_field_not_retry(mock_llm):
    mock_llm.chat.completions.create.return_value = MockResponse(
        content='{"bucket_id":"industry_chain","fields":{"only_one":{...}}}'
    )
    result = await run_single_bucket("industry_chain", "...")
    assert len(result.fields) > 1  # 自动补 unknown
    assert mock_llm.chat.completions.create.call_count == 1  # 没重试
```

### Integration 测试

`test_runner.py` 用真实 SQLite (`sqlite:///:memory:`),验证事件序列:

- `test_orchestrate_emits_correct_event_sequence`:断言 start → ... → done 顺序
- `test_orchestrate_short_markdown_short_circuits`:markdown < 200 字直接 error + done
- `test_orchestrate_continues_after_bucket_failure`:单桶挂仍发 done,error_count>=1

`test_api.py`:
- `test_invalid_company_type_returns_422`
- `test_analyze_returns_sse_stream`
- `test_analyze_cached_returns_single_cached_event`

### Smoke 测试

`backend/tests/test_analyze_smoke.py`(对应已有 `test_mineru_smoke.py` 模式):
- 标记 `@pytest.mark.smoke`,默认 CI 跳过
- 需要 `DEEPSEEK_API_KEY`,跑真实 LLM
- 用 Step 3 已缓存的真 markdown 跑一次 equipment 模式
- 断言至少 3 个 `bucket_done`(允许部分桶失败)
- 不强求全绿,只验证流程通

运行:
```bash
pytest backend/tests/                    # 默认跑 unit + integration
pytest backend/tests/ -m smoke           # 仅 smoke
DEEPSEEK_API_KEY=xxx pytest -m smoke     # 带 key 跑 smoke
```

### Fixtures 目录

```
backend/tests/
├── conftest.py                          # 共享 fixtures
├── fixtures/
│   ├── sample_markdown_equipment.txt    # 1500 字设备类 mock 研报
│   ├── sample_llm_industry_chain.json   # happy path LLM 返回样例
│   ├── sample_llm_invalid.txt           # 非法 JSON
│   └── sample_llm_partial.json          # 缺字段 LLM 返回
└── test_templates/schemas/analyzer/streaming/storage/runner/api/test_analyze_smoke.py
```

### 前端测试

**本次 spec 不包含**。理由:项目当前无 vitest / jsdom 配置,引入测试栈是另一个独立工作。如果要做,优先级:`BucketFieldCard.test.tsx`(证据色) → `AnalysisResultStep.test.tsx`(SSE 事件 → state)。

### 覆盖率目标

子包覆盖率 **>80%**,主要漏掉 LLM client 初始化、DB engine 这些外部依赖。不强求 100%。

## Out of Scope(明确不做)

| 项 | 原因 | 后续 |
|---|---|---|
| 封测/IP 专属桶(对应文档 §4 §5 指标清单) | 文档无现成 prompt,封测/IP 走综合已够用 | P2:加模板 + 路由表一行 |
| 企业类型自动识别(LLM 分类器) | 多一次 LLM 调用,用户手选更准 | 不做(用户输入时已知道) |
| 单桶失败"重试本桶"功能 | 需新增 `/analyze-bucket` 端点 | P2:UI 已预留 |
| Token 级流式(边吐边解析) | 结构化 JSON 边吐边解析很脆弱 | 不做 |
| 前端单元测试 | 项目无 vitest 配置 | 独立 spec |
| Alembic 迁移工具 | 与项目惯例不符 | 不做 |

## Open Questions

无。所有 7 个核心决策点已在 brainstorming 阶段逐一确认。
