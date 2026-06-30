# Deep Analysis Pipeline — Implementation Plan

**Date:** 2026-06-30
**Spec:** `docs/superpowers/specs/2026-06-30-deep-analysis-pipeline-design.md`
**Approach:** C — Composable Endpoints + 服务端缓存

## 实际代码勘误（与 spec 对齐）

Spec 中关于前端的描述需要按现状修正：
- ❌ Spec 假设 "Ant Design `Steps` 组件 + react-router"
- ✅ **现状**：`frontend/` 未安装 `antd` 也未安装 `react-router-dom`，是手写 sketch/paper 主题（`chainkb.css`），`App.tsx` 单页直接渲染 `ChainPage`
- 因此「新页面」的实现方式调整为：**在 `App.tsx` 增加一个顶层 view switcher**（不引入 react-router，保持轻量），DeepAnalysisPage 用纯 React state 管理四步向导，沿用 sketch 主题风格

后端部分 spec 描述与现状一致，无需修正。

---

## 任务列表

### Phase 1 — 后端基础设施（DB + Config）

#### Task 1.1: 新增两张表的 SQLAlchemy 模型
**文件:** `backend/app/models/models.py`（追加）
- 新增 `ReportContent` 模型：`id, oss_key(unique+index), stock_code(index), title, markdown_text, parsed_at, token_count`
- 新增 `DeepAnalysis` 模型：`id, stock_code(index), oss_keys_json, analysis_text, model_name, created_at`
- 字段类型严格按 spec
**验证:** 启动 backend，sqlite 自动建表无报错；表结构用 `sqlite3 backend/data/investlens.db ".schema report_contents"` 核对

#### Task 1.2: 在 startup() 中导入新模型
**文件:** `backend/app/main.py`
- 在 `startup()` 函数的 import 行追加 `ReportContent, DeepAnalysis`
- 验证 `Base.metadata.create_all` 能感知新表
**验证:** 启动后日志无报错，DB 文件出现两张新表

#### Task 1.3: 新增 MinerU 配置项
**文件:** `backend/app/config.py`（追加）+ `backend/.env.example`（追加）
- 新增 `MINERU_API_URL`（默认 `https://mineru.dottore.com/api/v1`）
- 新增 `MINERU_API_KEY`（默认空）
- `.env.example` 增加对应模板
**验证:** 启动时 config 能加载

---

### Phase 2 — MinerU 解析服务

#### Task 2.1: 创建 `mineru_service.py`
**文件:** `backend/app/services/mineru_service.py`（新建）
- `is_configured() -> bool`：检查 `MINERU_API_KEY` 非空
- `submit_parse(pdf_url: str) -> str`：POST 到 MinerU 提交解析任务，返回 `task_id`
- `poll_result(task_id: str) -> dict | None`：GET 任务状态，完成返回 `{"markdown": "...", "token_count": N}`，未完成返回 `None`
- `estimate_tokens(text: str) -> int`：粗略估算（中文按 1.5 字/token，英文按 0.25 word/token）
- 失败时抛 `RuntimeError(detail)`，由 router 转 HTTP 状态码
- **Mock 模式**：`MINERU_API_KEY` 为空时，返回简短 mock markdown（与 llm_service 一致的行为）
**验证:** 单元测试覆盖 submit/poll/estimate_tokens，mock 模式可用

#### Task 2.2: MinerU 集成 smoke test
**文件:** `backend/tests/test_mineru_smoke.py`（新建）
- 仅当 `MINERU_API_KEY` 已配置时运行真实调用
- 提交一个已知小 PDF（用 fixtures/sample.pdf 或从 OSS 取一个）
- poll 直到 done，验证返回 markdown 非空
- 未配置 key 时 skip
**验证:** `pytest -k mineru` 通过

---

### Phase 3 — Deep Analysis 服务 + Router

#### Task 3.1: 创建 `deep_analysis_service.py`（解析编排）
**文件:** `backend/app/services/deep_analysis_service.py`（新建）
- `parse_reports(code: str, oss_keys: list[str], db: Session) -> dict`
  - 查 `report_contents` 表，已有缓存的标记 `cached`
  - 未缓存的：从 `oss_service.get_public_url(oss_key)` 取 URL（注：私有 bucket 需要 signed URL 或直接用 SDK stream）→ 调 `mineru_service.submit_parse` → 记录到内存任务表（暂用进程内 dict，task_id → oss_key）
  - 返回 spec 中 `parse` 端点的 response 结构
- `parse_status(code: str, db: Session) -> dict`
  - 从进程内任务表 poll 所有未完成的 task_id
  - 完成的写入 `report_contents` 表，清理任务表
  - 返回 spec 中 `parse-status` 的 response 结构
- `get_cached_markdown(oss_keys: list[str], db: Session) -> list[dict]`
  - 查 `report_contents` 表，返回 `[{oss_key, title, markdown_text, token_count}]`
**设计决策:** 进程内任务表是 MVP 选择（单实例部署够用）。后续如要多 worker，可换成 DB 表 `parse_tasks`。
**验证:** 单元测试 mock mineru_service，验证 cached/submitted/done 三种状态流转

#### Task 3.2: 实现 LLM 多维度分析（含 token 管理）
**文件:** `backend/app/services/deep_analysis_service.py`（继续追加）
- `analyze_stream(code: str, oss_keys: list[str], db: Session) -> Iterator[str]`
  - 读 `report_contents` markdown
  - Token 管理：累加 token_count，超 60K 时按 `parsed_at` 倒序截断（保留最新）
  - 构建四维度 prompt（见 spec）
  - 调 DeepSeek streaming（与 `llm_service.generate_report_stream` 同模式）
  - yield 每个 chunk
  - 流结束后：拼接完整 markdown → 写入 `deep_analyses` 表
- `_build_prompt(code: str, reports: list[dict]) -> str`
- `_truncate_reports(reports: list[dict], max_tokens: int = 60000) -> list[dict]`
- `_compute_cache_key(code: str, oss_keys: list[str]) -> str`
  - 排序 + `|` join + hash，用于缓存命中判断
- `get_cached_analysis(code: str, oss_keys: list[str], db: Session) -> dict | None`
  - 命中返回 `{analysis_text, created_at}`，避免重复消耗 token
**验证:** 单元测试 mock LLM client，验证 prompt 构建、截断逻辑、缓存写入

#### Task 3.3: 创建 `deep_analysis.py` router
**文件:** `backend/app/routers/deep_analysis.py`（新建）
- `POST /api/deep-analysis/parse` — `ParseRequest{code, oss_keys}`，调 `parse_reports`
- `GET /api/deep-analysis/parse-status?code=` — 调 `parse_status`
- `GET /api/deep-analysis/analyze?code=&oss_keys=` — SSE，先查缓存，未命中则 `EventSourceResponse(analyze_stream(...))`
  - 事件格式：`event: chunk` / `event: done` / `event: error`
- `GET /api/deep-analysis/history?code=` — 查 `deep_analyses` 表，返回 spec 中 history response
- 错误处理：MinerU 未配置 → 503；OSS key 不存在 → 422
**验证:** 启动 backend，用 curl 测每个端点

#### Task 3.4: 注册 router
**文件:** `backend/app/main.py`
- 在 `from app.routers import ...` 行追加 `deep_analysis`
- 在 `app.include_router(...)` 后追加 `app.include_router(deep_analysis.router)`
**验证:** `/docs` Swagger 显示 4 个新端点

#### Task 3.5: 后端集成测试
**文件:** `backend/tests/test_deep_analysis.py`（新建）
- 使用 FastAPI TestClient + 临时 DB
- 测试 `parse` 已有缓存路径（预填 `report_contents` → 全 cached）
- 测试 `analyze` 缓存命中路径（预填 `deep_analyses` → 直接返回，不调 LLM）
- 测试 `history` 端点返回格式
- LLM/MinerU 全部 mock
**验证:** `pytest backend/tests/test_deep_analysis.py` 全过

---

### Phase 4 — 前端页面

#### Task 4.1: 顶层 view switcher
**文件:** `frontend/src/App.tsx`（重写）
- 用 `useState<'chain' | 'deep'>` 切换两个顶层页面
- 顶部加一个极简的 nav bar（两个文字 tab，sketch 风格），不影响 ChainKbPage 已有 `.chainkb-root` 主题
- 默认 `'chain'` 保持现有行为
**验证:** `npm run dev` 默认显示 ChainKbPage，点击 nav 切换到 DeepAnalysisPage 不报错

#### Task 4.2: 新增 API 客户端函数
**文件:** `frontend/src/services/api.ts`（追加）+ 新建 `frontend/src/types/deepAnalysis.ts`
- 新增类型：`ReportItem, ParseResponse, ParseStatusResponse, AnalysisHistoryItem`
- `searchReports(code)` / `downloadReports(code, reports)` 复用已有 `/api/research/*` 端点
- `parseReports(code, ossKeys)` → POST
- `getParseStatus(code)` → GET，轮询用
- `streamAnalyze(code, ossKeys, callbacks)` → 用 `fetch` + ReadableStream（不用 EventSource，因为要支持 query params 且 GET）
- `getAnalysisHistory(code)` → GET
**验证:** TS 编译无错（`npm run build` 的 tsc 阶段通过）

#### Task 4.3: DeepAnalysisPage 主页面（向导容器）
**文件:** `frontend/src/pages/DeepAnalysisPage.tsx`（新建）+ `deep-analysis.css`
- 用 `useState<1|2|3|4>` 管理当前 step
- 顶部 sketch 风格的 step indicator（手绘风的 ①②③④ 文字 + 连接线）
- 持有跨 step 的 state：
  - `code: string`
  - `selectedReports: ReportItem[]`
  - `downloadResults: DownloadResult[]`
  - `ossKeys: string[]`（解析阶段使用）
  - `analysisText: string`
- 每步渲染对应子组件，通过 props 传递 state + setter
- 支持回退（点 step indicator 回到任意已完成步骤）
**验证:** 手动渲染每个 step，确认布局无错位

#### Task 4.4: Step 1 — ReportSearchStep
**文件:** `frontend/src/components/deep-analysis/ReportSearchStep.tsx`（新建）
- 输入框 + 搜索按钮 → 调 `searchReports(code)` → 列表展示
- 列表带 checkbox 多选（标题、机构、日期、评级）
- 「下一步」按钮 disabled 直到至少选 1 个
- 「下一步」点击后调用 `downloadReports(code, selected)` → 进入 Step 2
**验证:** 实测能搜出 301095 的研报并勾选

#### Task 4.5: Step 2 — ReportDownloadStep
**文件:** `frontend/src/components/deep-analysis/ReportDownloadStep.tsx`（新建）
- 接收 Step 1 触发的下载结果，逐行展示：`✓ ok / ✓ exists / ✗ failed`
- 失败项可点击「重试」
- 全部成功后允许「下一步」（部分失败也允许，但提示数量）
- 进入 Step 3 时把成功的 `oss_key` 列表（从 download 结果反推）传过去
- **注意：** `downloadReports` 返回的字段是 `info_code/filename/oss_url/status`，没有直接 oss_key，需要前端用 `reports/{code}/{filename}` 拼接
**验证:** Step1 → Step2 流转正常

#### Task 4.6: Step 3 — ReportParseStep
**文件:** `frontend/src/components/deep-analysis/ReportParseStep.tsx`（新建）
- 进入时立刻调 `parseReports(code, ossKeys)`
- 启动 `setInterval` 每 3s 调 `getParseStatus(code)` 直到 `done === total`
- 渲染每个 oss_key 的状态：`✓ done (3200 tokens) / ⏳ parsing / ✗ failed`
- 全部 done 后允许「下一步」
- 失败项提供「跳过」按钮（继续用已成功的部分）
**验证:** 实测能解析 1-2 个小 PDF

#### Task 4.7: Step 4 — AnalysisResultStep
**文件:** `frontend/src/components/deep-analysis/AnalysisResultStep.tsx`（新建）
- 进入时调 `streamAnalyze(code, ossKeys, { onChunk, onDone, onError })`
- 用本地 state 累加 chunk → 传给复用的 `MarkdownRenderer.tsx`
- 流式期间显示一个简单的 streaming 指示（如末尾光标 ▊）
- 「重新分析」按钮：清空 state 重新调
- 顶部「查看历史」按钮：弹出一个抽屉/模态框列出 `getAnalysisHistory(code)` 的历史记录，点击可加载
**验证:** 端到端实测，能看到 markdown 流式渲染

---

### Phase 5 — 集成 & 收尾

#### Task 5.1: 端到端走通
- 用 301095 走完四步：搜索 → 下载 → 解析 → 分析
- 确认 `report_contents` 和 `deep_analyses` 表都有数据
- 重启 backend 后再分析同一股票 → 应秒返回（缓存命中）
**验证:** 全流程无报错，缓存命中

#### Task 5.2: 错误路径覆盖
- 测试 MINERU_API_KEY 未配置：parse 端点返回 503
- 测试 oss_key 不存在：analyze 端点返回明确错误
- 测试 LLM 失败：SSE 发 `event: error`，前端显示错误而不卡死
**验证:** 每条错误路径手动触发确认

#### Task 5.3: 前端 lint + build
**验证:** `npm run lint` + `npm run build` 全过

#### Task 5.4: 提交 commits（按 phase 拆分）
- Phase 1+2: `feat(backend): add MinerU parse service + report_contents schema`
- Phase 3: `feat(backend): add /api/deep-analysis endpoints for AI multi-report analysis`
- Phase 4: `feat(frontend): add Deep Analysis wizard page with 4-step pipeline`
- Phase 5: `test: add integration tests for deep analysis pipeline`

---

## 不在本计划范围内的事项（明确推迟）

1. **MinerU 异步任务持久化**：MVP 用进程内 dict，单实例够用；多 worker 部署时再换 DB 表
2. **OSS signed URL**：MinerU 需要能下载 PDF，当前 bucket 是私有的；MVP 用 SDK `sign_url` 方法生成 1 小时有效的 GET URL
3. **历史分析的 diff 视图**：MVP 历史只做"加载查看"，不做对比
4. **批量任务并行化**：parse 端点对 N 个 PDF 串行提交（MinerU 限速未知），并发优化留到后续
5. **路由真正接入 react-router**：当前两个顶层页面用 state 切换够用，后续多页面再引入 router

---

## 依赖关系

```
Phase 1 (DB + Config)
   ↓
Phase 2 (MinerU service)  ←── 依赖 1.3 配置
   ↓
Phase 3 (Analysis service + Router)  ←── 依赖 1.1/1.2 表 + 2.1 service
   ↓
Phase 4 (Frontend)  ←── 依赖 3.3/3.4 端点可用
   ↓
Phase 5 (Integration)
```

每个 task 都可独立验证、独立提交。
