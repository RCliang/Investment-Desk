# InvestLens AI 投资研究工作台 — 设计文档

## 概述

个人使用的 Web 应用，用于研究特定产业（如新能源汽车），分析上下游机会，查询 A 股上市公司数据，生成投资研究报告，制定投资计划。

## 技术选型

- **前端：** Vite + React + TypeScript + Ant Design（深色主题）
- **后端：** FastAPI + Python 3.11+
- **数据源：** akshare、tushare-pro、a-stock-data（已有的 skill）
- **AI：** Claude API（Anthropic SDK）/ GPT（OpenAI SDK），通过 LangChain 或直接 SDK 调用
- **数据库：** SQLite（轻量持久化）
- **部署：** Docker Compose（前端 + 后端）

## 系统架构

```
┌──────────────────────────────────────────────────┐
│  React SPA (Vite + TS + Ant Design)              │
│  ┌─────────┬──────────┬──────────┬─────────┐    │
│  │产业链图谱│ 数据查询  │ 投资报告  │投资计划  │    │
│  └────┬─────┴────┬────┴────┬─────┴────┬────┘    │
│       └──────────┴────────┴──────────┘          │
│                  │ REST API                       │
└──────────────────┼───────────────────────────────┘
                   │
┌──────────────────┼───────────────────────────────┐
│  FastAPI 后端 (Python)                            │
│  ┌─────────┬──────────┬──────────┬─────────┐    │
│  │产业链分析│ 数据查询  │ 报告生成  │投资计划  │    │
│  └────┬────┴────┬─────┴────┬─────┴────┬────┘    │
│       │         │          │          │          │
│  ┌────▼───┐ ┌──▼────┐ ┌──▼────┐ ┌───▼───┐    │
│  │  LLM   │ │AkShare│ │Tushare│ │a-stock│    │
│  │(Claude)│ │       │ │       │ │ data  │    │
│  └────────┘ └───────┘ └───────┘ └───────┘    │
└──────────────────────────────────────────────────┘
```

## 模块 1：产业链分析

### 用户流程
输入产业名称 → 点击"启动 AI 分析" → LLM 生成产业链结构 → 展示上中下游图谱 + 机会标签

### API

- `POST /api/chain/analyze` — 接收 `{industry: string}`，调用 LLM 生成产业链
  - LLM 使用 JSON mode 返回结构化数据
  - 返回 `{upstream: [{name, opp_level, summary}], midstream: [...], downstream: [...]}`
- `GET /api/chain/history` — 获取历史分析列表
- `GET /api/chain/{id}` — 获取某次分析详情

### LLM Prompt 设计
- 输入产业名称，要求 LLM 输出上中下游各环节
- 每个环节标注机会评级（高/中/低）和一句话说明
- 使用 structured output 确保格式稳定

### 前端展示
- 顶部 4 个 KPI 卡片（产业规模、机会数、综合评级、数据更新时间）
- 三列布局：上游 → 中游 → 下游，箭头连接
- 每个环节可点击，跳转到数据查询或触发深度分析
- 机会优先级排序表格

### 数据缓存
产业链分析结果缓存 7 天到 SQLite。

## 模块 2：数据查询

### API

- `POST /api/data/query` — 统一查询入口
  - body: `{source: "akshare"|"tushare"|"astock", action: string, params: object}`
- `GET /api/data/stock/{code}` — 查单只股票行情
- `GET /api/data/industry/{name}` — 按行业批量查询
- `GET /api/data/financial/{code}` — 查财务指标

### 支持的查询类型
- 实时行情：日K/周K/月K 线
- 财务指标：PE、PB、ROE、毛利率、负债率
- 资金流向：北向资金、主力净流入
- 行业对比：多公司估值横向对比

### 数据源封装
每个数据源封装为独立的 Python service class：
- `AkShareService` — 参考 `.claude/skills/akshare/` 文档
- `TushareService` — 参考 `.claude/skills/tushare-api/` 文档
- `AStockService` — 参考 `.claude/skills/a-stock-data/` 文档

### 缓存策略
- 行情数据：缓存 5 分钟
- 财务数据：缓存 1 天
- 查询结果存 `data_cache` 表

### 前端展示
- Skill 选择卡片（Wind、研报、财务分析）
- 查询结果表格（支持排序和筛选）
- 历史查询记录

## 模块 3：报告生成

### API

- `POST /api/report/generate` — 触发报告生成
  - body: `{industry: string, chain_analysis_id?: string}`
  - 使用 SSE 流式返回
- `GET /api/report/list` — 获取报告列表
- `GET /api/report/{id}` — 获取报告详情
- `GET /api/report/{id}/export?format=pdf|md` — 导出报告

### 报告生成流程
1. 获取产业链分析结果（已有缓存则直接用，否则重新分析）
2. 抓取关键数据点（龙头公司估值、行业增速等）
3. 将结构化数据注入 LLM prompt
4. LLM 生成报告各章节：
   - 核心判断
   - 机会优先级排序
   - 风险矩阵（高风险因素 vs 正向催化剂）
   - 关键标的推荐
5. 流式返回内容

### 前端展示
- Markdown 渲染报告
- 风险矩阵红/绿双栏
- 数据源标签
- 导出按钮（PDF / Markdown）

## 模块 4：投资计划

### API

- `POST /api/plan/create` — 创建投资计划
- `GET /api/plan/list` — 查看所有计划
- `PUT /api/plan/{id}` — 更新计划（修改仓位/价格/状态）
- `DELETE /api/plan/{id}` — 删除计划

### 投资计划数据结构
```python
{
    "id": int,
    "stock_code": str,       # 股票代码
    "stock_name": str,       # 股票名称
    "direction": "buy" | "sell",
    "position_ratio": float, # 仓位比例 0-100
    "target_price": float,    # 目标价
    "stop_loss_price": float, # 止损价
    "reason": str,            # 买入/卖出理由
    "status": "pending" | "executing" | "closed" | "stopped",
    "created_at": datetime,
    "updated_at": datetime
}
```

### 前端展示
- 计划列表（卡片布局）
- 状态标签（待执行/执行中/已平仓/已止损）
- 新建/编辑计划表单（模态框）
- 与报告关联显示

## 数据层

### SQLite Schema

```sql
CREATE TABLE chain_analyses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    industry TEXT NOT NULL,
    result_json TEXT NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE data_cache (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cache_key TEXT UNIQUE NOT NULL,
    result_json TEXT NOT NULL,
    expires_at DATETIME NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    industry TEXT NOT NULL,
    chain_analysis_id INTEGER,
    content_md TEXT NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE plans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    stock_code TEXT NOT NULL,
    stock_name TEXT NOT NULL,
    direction TEXT NOT NULL,
    position_ratio REAL NOT NULL,
    target_price REAL,
    stop_loss_price REAL,
    reason TEXT,
    status TEXT DEFAULT 'pending',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

### 项目结构

```
Investment-Desk/
├── frontend/           # React SPA
│   ├── src/
│   │   ├── components/  # 通用组件
│   │   ├── pages/       # 四个页面
│   │   │   ├── ChainPage/
│   │   │   ├── DataPage/
│   │   │   ├── ReportPage/
│   │   │   └── PlanPage/
│   │   ├── services/    # API 调用封装
│   │   ├── hooks/       # 自定义 hooks
│   │   └── App.tsx
│   ├── package.json
│   └── vite.config.ts
├── backend/             # FastAPI
│   ├── app/
│   │   ├── main.py      # FastAPI 入口
│   │   ├── models/      # SQLAlchemy/Pydantic 模型
│   │   ├── routers/     # 四个路由模块
│   │   │   ├── chain.py
│   │   │   ├── data.py
│   │   │   ├── report.py
│   │   │   └── plan.py
│   │   ├── services/    # 业务逻辑
│   │   │   ├── llm_service.py
│   │   │   ├── akshare_service.py
│   │   │   ├── tushare_service.py
│   │   │   └── astock_service.py
│   │   └── db.py        # SQLite 连接
│   ├── requirements.txt
│   └── Dockerfile
├── docker-compose.yml
└── README.md
```

## 关键设计决策

1. **单体应用**：个人使用，四个模块紧耦合，不需要微服务
2. **SQLite**：轻量无需额外服务，适合单用户场景
3. **SSE 流式返回**：报告生成和产业链分析可能耗时，流式输出提升体验
4. **缓存策略**：减少对外部 API 的重复调用，控制请求频率
5. **LLM structured output**：产业链分析用 JSON mode，确保前端可解析

## 不在第一版范围内的功能

- 用户认证（个人使用不需要）
- 实时行情推送（WebSocket）
- 回测引擎
- 多语言支持
