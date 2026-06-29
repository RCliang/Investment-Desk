# InvestLens 投资研究工作台 · 使用者指南

> 个人 A 股投资研究工作台 — 用 AI 产业链图谱把"看赛道、选个股、写复盘、管计划"串成一条线。

---

## 一、项目是什么

**InvestLens（Investment-Desk）** 是一个面向个人投资者的 A 股研究工作台。它把投资研究中最耗时的几件事打包成了一站式工具：

- **看赛道** — 不再只是看研报列表，而是用一张"五层产业链地图"把能源→材料→制造→交通→消费串起来，每个细分行业都挂载着真实 A 股公司。
- **选个股** — 同一只股票可以从行情、财务、研报、资金流、概念板块、解禁、股东户数、融资融券等多个维度交叉看，不用切多个 App。
- **写复盘** — 一键让 AI 把产业链分析结果写成结构化报告（核心判断 / 机会排序 / 风险矩阵 / 标的推荐），并流式输出。
- **管计划** — 买卖理由、仓位、目标价、止损价、状态全部入库，方便事后复盘。

技术栈：后端 Python/FastAPI + SQLite，前端 React/TypeScript/Vite + Ant Design（深色主题），可选 Docker Compose 一键部署。

---

## 二、四大核心功能

### 1. 产业链知识库（主推功能）

一张五层结构的产业链大图：

```
I  · 能源与电力      (Energy)
II · 原材料          (Materials)
III· 制造业          (Manufacturing)
IV · 交通与物流      (Transport)
V  · 消费与服务      (Consumption)
     │
     └─ 48 个细分行业
          └─ 234 家 A 股公司 + 30+ 港/美参考公司（NVIDIA、TSMC 等）
```

前端三个页面标签：
- **00 · 总览** — 五层结构树，可一层层钻取到细分行业
- **01 · 产业链层级** — 选定细分行业后看它的公司列表、上中下游分类、关键细分领域
- **03 · 财务拆解** — 单家公司的画像（行情 + 财务 + 概念标签 + 研报）

支持公司名称/代码搜索，并支持页面间钻取（点公司直接跳到财务拆解）。

### 2. 产业链 AI 分析（v0 兼容功能）

输入一个产业名（如"新能源汽车"），AI 返回结构化的上中下游机会评级：

- 产业规模、增长率、综合评级
- 每个环节的关键细分领域
- 每个领域的投资评级（high / mid / low）+ 一句话逻辑

> 与"产业链知识库"的区别：知识库是**结构化挂载的真实公司**，AI 分析是**LLM 对单个产业的动态解读**。两者可互相印证。

### 3. 报告生成

基于产业链分析结果，AI 生成结构化研究报告，章节固定为：

1. 核心判断
2. 机会优先级排序
3. 风险矩阵（高风险因素 vs 正向催化剂）
4. 关键标的推荐（3-5 只 A 股）

**SSE 流式输出**，前端边生成边渲染，不需要等几十秒才看到内容。

### 4. 投资计划

简单的 CRUD，但字段覆盖了真实复盘需要的信息：

| 字段 | 含义 |
|---|---|
| `direction` | buy / sell |
| `position_ratio` | 仓位比例 0-100 |
| `target_price` | 目标价 |
| `stop_loss_price` | 止损价 |
| `reason` | 买卖理由（最重要） |
| `status` | pending / executing / closed / stopped |

---

## 三、数据来源（重点）

 InvestLens 不自己造数据，而是把多个公开/半公开数据源**整合到统一接口**，并按各自特点设置缓存与刷新策略。

### 3.1 数据源全景

| 数据源 | 用途 | 是否需要 Token | 备注 |
|---|---|---|---|
| **DeepSeek API** | 产业链 AI 分析、报告生成 | 需要 `DEEPSEEK_API_KEY` | OpenAI 兼容协议；不配 key 时回退到 mock 数据 |
| **AkShare** | A 股行情、财务、行业成分股、资金流 | **无需** | 开源 Python 库，抓东财/新浪/同花顺等公开页面 |
| **Tushare Pro** | 专业财务指标（PE/PB/ROE/毛利率等） | 需要 `TUSHARE_TOKEN` | 积分制，部分接口需要积分门槛 |
| **腾讯财经** | 实时行情（PE/PB/市值） | **无需** | 速度快、不封 IP，作为行情主源 |
| **东方财富** | 研报、概念板块、资金流分钟级、解禁、股东户数、融资融券 | **无需** | 通过 AkShare / 自封装接口访问 |
| **通达信 (mootdx)** | 财务三表、F10 | **无需** | 财务数据主源，稳定 |
| **iWencai** | 研报搜索（可选） | 可选 `IWENCAI_API_KEY` | 不配也能用东财源 |

### 3.2 后端数据服务对应关系

```
app/services/
  llm_service.py        ← DeepSeek (产业链 AI 分析、报告生成)
  akshare_service.py    ← AkShare  (行情/财务/行业/资金流通用接口)
  tushare_service.py    ← Tushare  (专业财务指标)
  astock_service.py     ← 腾讯 + 东财 (实时行情/研报/分钟资金流/概念板块)
```

产业链知识库的市场数据**不走上面的通用接口**，而是通过专门的 backfill 脚本定时抓取后入库，查询时直接读数据库 — 这也是为什么知识库页面的加载速度比通用数据接口快。

### 3.3 数据缓存策略

通用数据查询走 `data_cache` 表，按类型设置 TTL：

| 类型 | TTL | 说明 |
|---|---|---|
| 行情数据 | 5 分钟 | 平衡实时性与 API 调用频次 |
| 财务数据 | 1 天 | 财务数据日级更新足够 |
| 产业链 AI 分析 | 7 天 | 避免 LLM 重复消耗 |

缓存键 = `{source}:{action}:{params}` 的 MD5。命中缓存时直接返回，未命中才调外部接口。

---

## 四、产业链是怎么关联的（重点）

这是项目最值得讲清楚的地方。产业链不是"AI 凭空生成"，也不是"手工录入"，而是**结构化种子数据 + 多源市场数据**的双层组合。

### 4.1 第一层：种子结构（静态）

来源文件：`backend/data/aichainmap_seed.json`（基于公开网站 aichainmap.com 整理）

包含：
- **5 个层级**（I-V，对应能源/材料/制造/交通/消费）
- **48 个细分行业**，每个细分行业标注了"上中下游"归属和 3-6 个关键细分领域
- **234 家 A 股公司** + **30+ 港/美参考公司**，公司与细分行业是多对多关系（一家公司可同时出现在多个细分行业）

通过 `backend/scripts/load_seed_to_db.py` 一次性导入到 7 张关联表：

```
chain_layers                  5 个层级
chain_sub_industries          48 个细分行业
chain_companies               公司主表（A 股 + 参考公司）
chain_concepts                概念标签字典
chain_sub_industry_companies  公司 ↔ 细分行业
chain_company_concepts        公司 ↔ 概念标签
```

> 关键点：**层级 → 细分行业 → 公司**这条骨架是结构化的、可钻取的、可枚举的。前端"00·总览"页面的整棵树就来自这里。

### 4.2 第二层：市场数据（动态挂载）

骨架确定后，每家公司再挂载 7 类动态数据，分别由独立的 backfill 脚本抓取入库：

| 数据类型 | 入库表 | 数据源 | 抓取脚本 |
|---|---|---|---|
| 实时行情快照 | `chain_quotes` | 腾讯财经 | `backfill_tencent_quotes.py` |
| 财务三表 | `chain_finance_snapshots` | 通达信 mootdx | `backfill_mootdx_finance.py` |
| 研究报告 | `chain_research_reports` | 东方财富 | `backfill_em_reports.py` |
| 概念板块 | `chain_concepts`（关联表） | 东方财富 | `backfill_em_concept_blocks.py` |
| 解禁事件 | `chain_lockup_events` | 东方财富 | `backfill_em_lockup_expiry.py` |
| 股东户数 | `chain_holder_periods` | 东方财富 | `backfill_em_holder_num.py` |
| 融资融券 | `chain_margin_daily` | 东方财富 | `backfill_em_margin_trading.py` |

> 关键点：用户在前端看到的"03·财务拆解"页面，是把 **第一层的结构 + 第二层的市场数据** 拼装出来的公司画像。

### 4.3 第三层：AI 分析（按需触发）

当用户想看某个产业的**投资逻辑**而不仅是公司列表时，AI 上场：

- 输入：产业名（或选定的细分行业）
- 调 DeepSeek API，用结构化 prompt 约束输出为 JSON
- 输出：上中下游各环节的机会评级 + 逻辑

这一层**不会写入产业链骨架**，而是单独存在 `chain_analyses` 表，缓存 7 天。

### 4.4 三层如何配合

```
用户打开"00·总览"
   │
   ├── 看到：层级 → 细分行业 → 公司         ← 第一层（静态结构）
   │
   ├── 点公司看"03·财务拆解"
   │     └─ 看到：行情/财务/研报/概念/解禁… ← 第二层（动态市场数据）
   │
   └── 想看产业投资逻辑？ → 点"AI 分析"     ← 第三层（LLM 动态生成）
         │
         └─ 满意？→ 点"生成报告" → SSE 流式输出研究报告
```

---

## 五、使用方法

### 5.1 启动

#### 方式 A：本地开发（推荐试用）

```bash
# 1) 后端
cd backend
pip install -r requirements.txt
copy .env.example .env       # 编辑 .env，至少填 ADMIN_REFRESH_TOKEN
uvicorn app.main:app --reload --port 8000

# 2) 前端（另开终端）
cd frontend
npm install
npm run dev                  # 打开 http://localhost:5173
```

#### 方式 B：Docker 一键起

```bash
docker-compose up --build
# 后端 :8000，前端 :3000（nginx 代理 /api/* 到后端）
```

### 5.2 环境变量

| 变量 | 是否必填 | 作用 |
|---|---|---|
| `ADMIN_REFRESH_TOKEN` | **必填** | 数据刷新接口鉴权；不填则刷新接口返回 503 |
| `DEEPSEEK_API_KEY` | 推荐 | 产业链 AI 分析与报告生成；不填则回退 mock 数据 |
| `MODEL_NAME` | 可选 | `deepseek-chat`（默认）或 `deepseek-reasoner`（R1 推理） |
| `TUSHARE_TOKEN` | 可选 | 专业财务指标；不填则跳过 tushare 源 |
| `IWENCAI_API_KEY` | 可选 | 同花顺研报搜索；不填则用东财源 |

`.env` 已 gitignore，模板见 `.env.example`。

### 5.3 首次初始化数据

新装的数据库是空的，需要跑一次全量 backfill：

```bash
cd backend
python -m app.services.refresh_cli all
```

这一步会执行 7 类抓取脚本，约几分钟到十几分钟（取决于网络）。

### 5.4 日常使用

| 想做的事 | 在哪做 |
|---|---|
| 浏览产业链大图 | 首页 "00·总览" |
| 钻取到细分行业的公司列表 | 点某个细分行业 → "01·产业链层级" |
| 看单家公司全维度画像 | 点公司 → "03·财务拆解" |
| 让 AI 分析某个产业 | "AI 产业链分析"页 |
| 生成研究报告 | "报告"页 → 选产业 → SSE 流式渲染 |
| 记录买卖计划 | "计划"页 → 新建/编辑 |

---

## 六、数据刷新与新鲜度

### 6.1 三种触发方式

| 方式 | 是否需要 Token | 适用场景 |
|---|---|---|
| **CLI**（`python -m app.services.refresh_cli <type>`） | 否 | 本地运维、首次初始化 |
| **HTTP API**（`POST /api/chainkb/refresh/{type}`） | 是（`X-Admin-Token`） | 生产环境远程触发 |
| **自动调度器**（APScheduler，进程内） | 否 | 后端启动即自动运行，零干预 |

### 6.2 默认调度表（时区 Asia/Shanghai）

| 类型 | 默认 cron | 说明 |
|---|---|---|
| `quotes` 行情 | 周一至五 9:00-14:59 / 5min，15:00-15:30 / 5min | 交易时段高频 |
| `finance` 财务 | 周日 03:00 | 周末低频 |
| `reports` 研报 | 周日 04:00 | 周末低频 |
| `concepts` 概念 | 每月 1 号 04:00 | 月频足够 |
| `lockup` 解禁 | 周日 05:00 | 周末低频 |
| `holders` 股东户数 | 每月 1 号 03:00 | 月频 |
| `margin` 融资融券 | 周一至五 15:30 | 收盘后一次 |

### 6.3 新鲜度可见

前端右上角有数据新鲜度条，60 秒轮询一次 `/api/chainkb/freshness`，显示如：

```
现价 3分钟前 · 财务 2天前 · 研报 更新中… · 概念 5天前
```

如果某类数据从未抓取成功过，会显示"从未"，提示用户手动跑一次 backfill。

### 6.4 CLI 命令一览

```bash
python -m app.services.refresh_cli quotes       # 仅行情
python -m app.services.refresh_cli finance      # 仅财务
python -m app.services.refresh_cli all          # 全部 7 类
python -m app.services.refresh_cli --list       # 查看历史执行记录
```

### 6.5 HTTP API 调用示例

```bash
# 同步类型（quotes，立即返回结果）
curl -X POST http://localhost:8000/api/chainkb/refresh/quotes \
  -H "X-Admin-Token: $ADMIN_REFRESH_TOKEN"

# 异步类型（reports 等，返回任务 ID）
curl -X POST http://localhost:8000/api/chainkb/refresh/reports \
  -H "X-Admin-Token: $ADMIN_REFRESH_TOKEN"

# 查任务状态
curl http://localhost:8000/api/chainkb/refresh/status/42 \
  -H "X-Admin-Token: $ADMIN_REFRESH_TOKEN"
```

---

## 七、主要 API 接口速查

### 产业链知识库
| 方法 | 路径 | 作用 |
|---|---|---|
| GET | `/api/chainkb/tree` | 完整五层结构树 |
| GET | `/api/chainkb/sub_industries/{group_id}` | 细分行业详情及公司列表 |
| GET | `/api/chainkb/companies/{ticker}` | 公司画像（结构化+行情+财务+概念） |
| GET | `/api/chainkb/companies/{ticker}/timeseries` | 公司时序数据 |
| GET | `/api/chainkb/search?q=` | 公司搜索 |
| GET | `/api/chainkb/freshness` | 数据新鲜度（公开） |

### 产业链 AI 分析
| 方法 | 路径 | 作用 |
|---|---|---|
| POST | `/api/chain/analyze` | 触发 AI 分析 |
| GET | `/api/chain/history` | 历史分析列表 |
| GET | `/api/chain/{id}` | 某次分析详情 |

### 数据查询
| 方法 | 路径 | 作用 |
|---|---|---|
| POST | `/api/data/query` | 统一查询（指定 source/action/params） |
| GET | `/api/data/stock/{code}` | 实时行情 |
| GET | `/api/data/stock/{code}/hist` | 历史行情 |
| GET | `/api/data/stock/{code}/financial` | 财务指标 |
| GET | `/api/data/stock/{code}/fund-flow` | 资金流向 |
| GET | `/api/data/stock/{code}/reports` | 研报 |
| GET | `/api/data/stock/{code}/blocks` | 概念板块 |

### 报告生成
| 方法 | 路径 | 作用 |
|---|---|---|
| POST | `/api/report/generate` | 触发报告（SSE 流式） |
| GET | `/api/report/list` | 报告列表 |
| GET | `/api/report/{id}` | 报告详情 |

### 投资计划
| 方法 | 路径 | 作用 |
|---|---|---|
| POST | `/api/plan/create` | 创建计划 |
| GET | `/api/plan/list` | 计划列表 |
| PUT | `/api/plan/{id}` | 更新计划 |
| DELETE | `/api/plan/{id}` | 删除计划 |

---

## 八、常见问题

**Q：前端显示"从未"是怎么回事？**
A：数据库还没跑过 backfill。执行 `python -m app.services.refresh_cli all` 即可。

**Q：不配 `DEEPSEEK_API_KEY` 能用吗？**
A：能用。产业链知识库浏览、数据查询、投资计划都不依赖 LLM；只有 AI 分析和报告生成会回退到 mock 数据。

**Q：调度器不工作？**
A：检查 uvicorn 是否单 worker 启动（多 worker 会跑多份调度器）；看启动日志里有没有 scheduler 就绪信息；时区确认是 `Asia/Shanghai`。

**Q：报告生成失败？**
A：先确认 `DEEPSEEK_API_KEY` 有效，再看后端日志的网络/超时信息。生产环境建议反向代理超时 ≥ 600s。

**Q：Tushare 接口 403 / 权限不足？**
A：Tushare Pro 是积分制，部分接口需要积分门槛。可以暂时不配 `TUSHARE_TOKEN`，退化为只用 AkShare + 通达信源。

---

## 九、设计文档索引

更深入的设计与实现细节可参考 `docs/superpowers/`：

- `specs/2026-06-21-investment-desk-design.md` — 系统整体设计、API 契约、数据 schema
- `specs/2026-06-26-data-freshness-design.md` — 数据刷新与新鲜度系统设计
- `specs/2026-06-26-frontend-slim-down-design.md` — 前端精简方案
- `docs/data-refresh-guide.md` — 数据刷新运维手册

产业链种子数据：`backend/data/aichainmap_seed.json`
数据抓取脚本：`backend/scripts/backfill_*.py`
