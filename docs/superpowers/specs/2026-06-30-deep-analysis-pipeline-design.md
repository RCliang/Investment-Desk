# Deep Analysis Pipeline Design

**Date:** 2026-06-30
**Status:** Approved
**Approach:** C — Composable Endpoints + 服务端缓存

## Overview

构建完整 pipeline：搜索研报 → 下载到 OSS → MinerU 解析 PDF → AI 多维分析 → 前端流式展示。

用户通过四步向导交互，每步可回退，中间结果持久化。

## Architecture

```
Frontend (4-step wizard)
  │
  ├─ Step1: GET /api/research/reports (existing)
  ├─ Step2: POST /api/research/download (existing)
  ├─ Step3: POST /api/deep-analysis/parse
  │         GET  /api/deep-analysis/parse-status
  └─ Step4: GET  /api/deep-analysis/analyze (SSE)
             GET  /api/deep-analysis/history
```

## Database Schema

### `report_contents` — MinerU 解析结果缓存

| Column | Type | Description |
|--------|------|-------------|
| id | Integer PK | 自增主键 |
| oss_key | String UNIQUE INDEX | OSS 对象路径，如 `reports/301095/xxx.pdf` |
| stock_code | String(6) INDEX | 股票代码 |
| title | String | 研报标题 |
| markdown_text | Text | MinerU 解析的 markdown 全文 |
| parsed_at | DateTime | 解析完成时间 |
| token_count | Integer | 预估 token 数，用于 LLM 上下文管理 |

### `deep_analyses` — AI 分析结果持久化

| Column | Type | Description |
|--------|------|-------------|
| id | Integer PK | 自增主键 |
| stock_code | String(6) INDEX | 股票代码 |
| oss_keys_json | Text | JSON list，记录用了哪些研报 |
| analysis_text | Text | 完整 markdown 分析结果 |
| model_name | String | 使用的模型名 |
| created_at | DateTime | 创建时间 |

## API Design

### POST /api/deep-analysis/parse

提交 PDF 给 MinerU 解析。已有缓存的自动跳过。

**Request:**
```json
{
    "code": "301095",
    "oss_keys": ["reports/301095/xxx.pdf", "reports/301095/yyy.pdf"]
}
```

**Response:**
```json
{
    "total": 5,
    "parsed": 3,
    "submitted": 2,
    "results": [
        {"oss_key": "...", "status": "cached"},
        {"oss_key": "...", "status": "submitted", "task_id": "mineru_xxx"},
        {"oss_key": "...", "status": "failed", "error": "..."}
    ]
}
```

### GET /api/deep-analysis/parse-status?code=301095

轮询解析进度。

**Response:**
```json
{
    "code": "301095",
    "total": 5,
    "done": 4,
    "pending": 1,
    "details": [
        {"oss_key": "...", "status": "done", "token_count": 3200},
        {"oss_key": "...", "status": "parsing"}
    ]
}
```

### GET /api/deep-analysis/analyze?code=301095&oss_keys=key1,key2

SSE 流式 AI 分析。从 DB 读取已解析 markdown，调用 DeepSeek LLM。

**SSE Events:**
```
event: chunk
data: {"content": "## 一、核心观点提取\n\n根据..."}

event: done
data: {"token_usage": {"prompt": 12000, "completion": 3500}}
```

**分析完成后自动存入 `deep_analyses` 表。**

### GET /api/deep-analysis/history?code=301095

返回历史分析列表。

**Response:**
```json
{
    "code": "301095",
    "analyses": [
        {
            "id": 1,
            "created_at": "2026-06-30T10:00:00",
            "model_name": "deepseek-chat",
            "report_count": 5,
            "preview": "核心观点：华泰证券认为..."
        }
    ]
}
```

## MinerU Integration

**新 service:** `app/services/mineru_service.py`

```python
async def submit_parse(pdf_url: str) -> str:
    """提交 PDF 给 MinerU 云端 API，返回 task_id"""

async def poll_result(task_id: str) -> dict | None:
    """轮询解析结果，完成返回 {"markdown": "..."}, 未完成返回 None"""
```

**配置项（.env）：**
```
MINERU_API_URL=https://mineru.dottore.com/api/v1
MINERU_API_KEY=
```

**流程：**
1. 收到 parse 请求 → 检查 `report_contents` 表
2. 已有缓存 → 返回 `status: "cached"`
3. 未解析 → 构建 OSS public URL → 提交 MinerU → 返回 task_id
4. 前端轮询 `parse-status` → 后端 poll MinerU → 完成时写入 DB

## AI Analysis

**Prompt 结构：**
```
你是一位专业的证券分析师。以下是关于{stock_name}({code})的{n}篇研究报告内容。
请从以下四个维度进行深度分析：

## 一、核心观点提取
提取每篇报告的核心投资观点、评级、目标价。

## 二、估值与盈利预测汇总
汇总各机构的营收/净利润预测、PE/PB估值，做对比表格。

## 三、多报告一致性分析
分析各报告观点的一致与分歧，哪些是共识，哪些有争议。

## 四、行业与竞争格局
提取行业趋势判断、竞争对手对比、公司核心壁垒。

---
【研报1】{title_1} ({org_1}, {date_1})
{markdown_1}

【研报2】{title_2} ({org_2}, {date_2})
{markdown_2}
...
```

**Token 管理策略：**
- 累加各研报 `token_count`，超过 60K input 时截断
- 优先保留最新研报，截断最早的
- 单篇超长时截取前 N 字符

**缓存策略：**
- 相同 `code` + 相同 `oss_keys` 组合（排序后 hash）命中缓存
- 缓存命中时直接返回历史结果（非 SSE）

## Frontend

**路由：** `/deep-analysis`

**页面：** `src/pages/DeepAnalysisPage.tsx`

**组件：**
```
src/components/deep-analysis/
  ├── ReportSearchStep.tsx      — Step1: 搜索+勾选
  ├── ReportDownloadStep.tsx    — Step2: 下载进度
  ├── ReportParseStep.tsx       — Step3: 解析进度+轮询
  └── AnalysisResultStep.tsx    — Step4: SSE流式展示
```

**交互要点：**
- Ant Design `Steps` 组件做顶部进度
- 每步可回退
- Step4 复用 `MarkdownRenderer.tsx`
- 页面顶部"查看历史"可切换历史列表
- 导航：左侧菜单新增"个股深度分析"，图标 `FileSearchOutlined`

## Backend File Structure (new/modified)

```
app/
├── models/models.py              (MODIFY: add ReportContent, DeepAnalysis)
├── config.py                     (MODIFY: add MINERU_API_URL, MINERU_API_KEY)
├── main.py                       (MODIFY: register deep_analysis router)
├── services/
│   ├── mineru_service.py         (NEW: MinerU cloud API client)
│   └── deep_analysis_service.py  (NEW: parse orchestration + LLM analysis)
└── routers/
    └── deep_analysis.py          (NEW: 4 endpoints)
```

## Error Handling

| Scenario | Behavior |
|----------|----------|
| MinerU API 不可用 | parse 返回 `status: "failed"`，前端显示错误可重试 |
| MinerU 解析超时 | parse-status 持续返回 `"parsing"`，前端显示等待 |
| OSS key 不存在 | parse 返回 `status: "failed", error: "oss_key_not_found"` |
| LLM 调用失败 | SSE 发送 `event: error`，前端显示错误 |
| Token 超限 | 自动截断最早研报，SSE 正常进行 |
| MINERU_API_KEY 未配置 | parse 接口返回 503 |
