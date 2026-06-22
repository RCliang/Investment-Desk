# InvestLens AI 投资研究工作台 — 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 构建个人使用的 Web 应用，支持产业产业链分析、A 股数据查询、投资报告生成和投资计划管理。

**Architecture:** FastAPI 单体后端 + React SPA 前端，SQLite 持久化。后端封装 akshare/tushare/a-stock-data 三个数据源服务，LLM 通过 Anthropic SDK 调用 Claude 生成产业链分析和报告。前后端通过 REST API + SSE 通信。

**Tech Stack:** Python 3.11+ / FastAPI / SQLAlchemy / Anthropic SDK / akshare / tushare / React / Vite / TypeScript / Ant Design

---

### Task 1: 项目脚手架搭建

**Files:**
- Create: `backend/requirements.txt`
- Create: `backend/app/__init__.py`
- Create: `backend/app/main.py`
- Create: `backend/app/config.py`
- Create: `frontend/` (via Vite scaffold)

- [ ] **Step 1: 创建后端项目结构**

```bash
mkdir -p backend/app/{routers,services,models}
touch backend/app/__init__.py
touch backend/app/routers/__init__.py
touch backend/app/services/__init__.py
touch backend/app/models/__init__.py
```

- [ ] **Step 2: 创建 backend/requirements.txt**

```txt
fastapi>=0.115.0
uvicorn[standard]>=0.30.0
sqlalchemy>=2.0.0
aiosqlite>=0.20.0
pydantic>=2.0.0
anthropic>=0.40.0
akshare>=1.14.0
tushare>=1.4.0
httpx>=0.27.0
python-dotenv>=1.0.0
sse-starlette>=2.0.0
```

- [ ] **Step 3: 创建 backend/app/config.py**

```python
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "data" / "investlens.db"

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
TUSHARE_TOKEN = os.getenv("TUSHARE_TOKEN", "")

LLM_MODEL = "claude-sonnet-4-20250514"
LLM_MAX_TOKENS = 4096

CACHE_TTL_MARKET = 300       # 行情缓存 5 分钟
CACHE_TTL_FINANCIAL = 86400  # 财务缓存 1 天
CACHE_TTL_CHAIN = 604800     # 产业链缓存 7 天
```

- [ ] **Step 4: 创建 backend/app/main.py — FastAPI 入口**

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="InvestLens API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/api/health")
async def health():
    return {"status": "ok"}
```

- [ ] **Step 5: 安装后端依赖**

Run: `cd backend && pip install -r requirements.txt`

- [ ] **Step 6: 验证后端启动**

Run: `cd backend && uvicorn app.main:app --reload --port 8000`
Expected: `Uvicorn running on http://127.0.0.1:8000`, `GET /api/health` returns `{"status": "ok"}`

- [ ] **Step 7: 创建前端项目**

Run: `npm create vite@latest frontend -- --template react-ts`

- [ ] **Step 8: 安装前端依赖**

Run:
```bash
cd frontend
npm install antd @ant-design/icons react-router-dom axios
npm install -D @types/node
```

- [ ] **Step 9: 创建前端基础布局**

Create `frontend/src/App.tsx`:

```tsx
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { ConfigProvider, theme } from 'antd';
import Layout from './components/Layout';
import ChainPage from './pages/ChainPage';
import DataPage from './pages/DataPage';
import ReportPage from './pages/ReportPage';
import PlanPage from './pages/PlanPage';

const API_BASE = 'http://localhost:8000';

export default function App() {
  return (
    <ConfigProvider
      theme={{
        algorithm: theme.darkAlgorithm,
        token: {
          colorPrimary: '#1f6feb',
          colorBgContainer: '#161b22',
          colorBgElevated: '#1c2330',
          colorBorder: 'rgba(48,54,61,0.9)',
          colorText: '#e6edf3',
          colorTextSecondary: '#8b949e',
          borderRadius: 6,
        },
      }}
    >
      <BrowserRouter>
        <Routes>
          <Route element={<Layout />}>
            <Route path="/" element={<Navigate to="/chain" replace />} />
            <Route path="/chain" element={<ChainPage />} />
            <Route path="/data" element={<DataPage />} />
            <Route path="/report" element={<ReportPage />} />
            <Route path="/plan" element={<PlanPage />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </ConfigProvider>
  );
}
```

- [ ] **Step 10: 创建 Layout 组件**

Create `frontend/src/components/Layout.tsx`:

```tsx
import { Outlet, useNavigate, useLocation } from 'react-router-dom';
import { Layout, Menu, Typography, Space, Badge } from 'antd';
import {
  ApartmentOutlined,
  DatabaseOutlined,
  FileTextOutlined,
  ScheduleOutlined,
} from '@ant-design/icons';

const { Header, Sider, Content } = Layout;

const menuItems = [
  { key: '/chain', icon: <ApartmentOutlined />, label: '产业链图谱' },
  { key: '/data', icon: <DatabaseOutlined />, label: '数据查询' },
  { key: '/report', icon: <FileTextOutlined />, label: '投资报告' },
  { key: '/plan', icon: <ScheduleOutlined />, label: '投资计划' },
];

export default function AppLayout() {
  const navigate = useNavigate();
  const location = useLocation();

  return (
    <Layout style={{ minHeight: '100vh', background: '#0d1117' }}>
      <Header style={{ background: '#161b22', borderBottom: '1px solid rgba(48,54,61,0.9)', display: 'flex', alignItems: 'center', padding: '0 16px' }}>
        <Typography.Text strong style={{ color: '#388bfd', fontSize: 13, letterSpacing: '0.08em', textTransform: 'uppercase' }}>
          InvestLens
        </Typography.Text>
        <Typography.Text style={{ color: '#6e7681', fontSize: 11, marginLeft: 8 }}>
          v0.1
        </Typography.Text>
      </Header>
      <Layout>
        <Sider width={200} style={{ background: '#161b22', borderRight: '1px solid rgba(48,54,61,0.9)' }}>
          <Menu
            mode="inline"
            selectedKeys={[location.pathname]}
            items={menuItems}
            onClick={({ key }) => navigate(key)}
            style={{ background: 'transparent', border: 'none' }}
          />
        </Sider>
        <Content style={{ padding: 16, overflow: 'auto' }}>
          <Outlet />
        </Content>
      </Layout>
    </Layout>
  );
}
```

- [ ] **Step 11: 创建四个页面占位文件**

Create `frontend/src/pages/ChainPage.tsx`:
```tsx
export default function ChainPage() {
  return <div>产业链图谱 - 开发中</div>;
}
```

Create `frontend/src/pages/DataPage.tsx`:
```tsx
export default function DataPage() {
  return <div>数据查询 - 开发中</div>;
}
```

Create `frontend/src/pages/ReportPage.tsx`:
```tsx
export default function ReportPage() {
  return <div>投资报告 - 开发中</div>;
}
```

Create `frontend/src/pages/PlanPage.tsx`:
```tsx
export default function PlanPage() {
  return <div>投资计划 - 开发中</div>;
}
```

- [ ] **Step 12: 验证前端启动**

Run: `cd frontend && npm run dev`
Expected: 访问 `http://localhost:5173`，可以看到侧边栏导航和深色主题布局，点击菜单可切换页面

- [ ] **Step 13: 提交脚手架**

```bash
git init
git add backend/ frontend/
git commit -m "feat: scaffold project with FastAPI backend and React frontend"
```

---

### Task 2: 数据库层

**Files:**
- Create: `backend/app/db.py`
- Create: `backend/app/models/models.py`

- [ ] **Step 1: 创建 backend/app/db.py**

```python
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from app.config import DB_PATH, BASE_DIR
import os

DB_PATH.parent.mkdir(parents=True, exist_ok=True)

engine = create_engine(f"sqlite+aiosqlite:///{DB_PATH}", echo=False)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

- [ ] **Step 2: 创建 backend/app/models/models.py**

```python
from sqlalchemy import Column, Integer, String, Float, Text, DateTime
from sqlalchemy.sql import func
from app.db import Base


class ChainAnalysis(Base):
    __tablename__ = "chain_analyses"

    id = Column(Integer, primary_key=True, autoincrement=True)
    industry = Column(String(100), nullable=False, index=True)
    result_json = Column(Text, nullable=False)
    created_at = Column(DateTime, server_default=func.now())


class DataCache(Base):
    __tablename__ = "data_cache"

    id = Column(Integer, primary_key=True, autoincrement=True)
    cache_key = Column(String(500), unique=True, nullable=False, index=True)
    result_json = Column(Text, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, server_default=func.now())


class Report(Base):
    __tablename__ = "reports"

    id = Column(Integer, primary_key=True, autoincrement=True)
    industry = Column(String(100), nullable=False, index=True)
    chain_analysis_id = Column(Integer, nullable=True)
    content_md = Column(Text, nullable=False)
    created_at = Column(DateTime, server_default=func.now())


class InvestmentPlan(Base):
    __tablename__ = "plans"

    id = Column(Integer, primary_key=True, autoincrement=True)
    stock_code = Column(String(10), nullable=False)
    stock_name = Column(String(50), nullable=False)
    direction = Column(String(10), nullable=False)  # buy / sell
    position_ratio = Column(Float, nullable=False)
    target_price = Column(Float, nullable=True)
    stop_loss_price = Column(Float, nullable=True)
    reason = Column(Text, nullable=True)
    status = Column(String(20), nullable=False, default="pending")  # pending / executing / closed / stopped
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
```

- [ ] **Step 3: 在 main.py 中注册数据库初始化**

Add to `backend/app/main.py`:

```python
from app.db import engine, Base
from app.models.models import ChainAnalysis, DataCache, Report, InvestmentPlan

@app.on_event("startup")
async def startup():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
```

Also update imports — change `create_engine` to async version:
```python
from sqlalchemy.ext.asyncio import create_async_engine
```

And in `db.py`, change engine to:
```python
engine = create_async_engine(f"sqlite+aiosqlite:///{DB_PATH}", echo=False)
```

- [ ] **Step 4: 验证数据库初始化**

Run: `cd backend && uvicorn app.main:app --reload`
Expected: 启动后 `data/investlens.db` 文件自动创建，包含 4 张表

- [ ] **Step 5: 提交**

```bash
git add backend/app/db.py backend/app/models/ backend/app/main.py
git commit -m "feat: add SQLite database layer with 4 tables"
```

---

### Task 3: 数据源服务 — AkShare

**Files:**
- Create: `backend/app/services/akshare_service.py`

- [ ] **Step 1: 创建 AkShare 服务**

```python
import akshare as ak
import pandas as pd
from datetime import datetime, timedelta


class AkShareService:
    """AkShare 数据源服务，覆盖行情、财务、资金流向。"""

    def get_stock_hist(self, code: str, period: str = "daily",
                       start_date: str = "", end_date: str = "") -> list[dict]:
        """获取股票历史K线。code 为 6 位代码如 000001。"""
        if not end_date:
            end_date = datetime.now().strftime("%Y%m%d")
        if not start_date:
            start_date = (datetime.now() - timedelta(days=365)).strftime("%Y%m%d")
        df = ak.stock_zh_a_hist(
            symbol=code, period=period,
            start_date=start_date, end_date=end_date
        )
        if df.empty:
            return []
        df.columns = [c.lower() for c in df.columns]
        return df.to_dict(orient="records")

    def get_stock_realtime(self) -> list[dict]:
        """获取全 A 股实时行情快照。"""
        df = ak.stock_zh_a_spot_em()
        if df.empty:
            return []
        df.columns = [c.lower() for c in df.columns]
        return df.to_dict(orient="records")

    def get_stock_financial(self, code: str) -> list[dict]:
        """获取个股财务指标摘要。"""
        df = ak.stock_financial_abstract(symbol=code)
        if df.empty:
            return []
        df.columns = [c.lower() for c in df.columns]
        return df.to_dict(orient="records")

    def get_industry_stocks(self, industry: str) -> list[dict]:
        """获取某行业的成分股列表。"""
        df = ak.stock_board_industry_cons_em(symbol=industry)
        if df.empty:
            return []
        df.columns = [c.lower() for c in df.columns]
        return df.to_dict(orient="records")

    def get_fund_flow(self, code: str) -> list[dict]:
        """获取个股资金流向。"""
        df = ak.stock_individual_fund_flow(stock=code, market="sh" if code.startswith("6") else "sz")
        if df.empty:
            return []
        df.columns = [c.lower() for c in df.columns]
        return df.to_dict(orient="records")

    def get_pe_pb_comparison(self, codes: list[str]) -> list[dict]:
        """多股票 PE/PB 估值对比。"""
        df_all = []
        for code in codes:
            df = ak.stock_zh_a_hist(
                symbol=code, period="daily",
                start_date=(datetime.now() - timedelta(days=5)).strftime("%Y%m%d"),
                end_date=datetime.now().strftime("%Y%m%d"),
            )
            if not df.empty:
                latest = df.iloc[-1]
                df_all.append({
                    "code": code,
                    "close": float(latest["收盘"]),
                    "date": str(latest.get("日期", "")),
                })
        return df_all


akshare_service = AkShareService()
```

- [ ] **Step 2: 手动验证数据可获取**

```python
from app.services.akshare_service import akshare_service
data = akshare_service.get_stock_hist("000001", period="daily", start_date="20260601", end_date="20260621")
print(len(data), data[0] if data else "empty")
```

Run: `cd backend && python -c "..."` (paste above)
Expected: 返回最近 21 天的交易数据

- [ ] **Step 3: 提交**

```bash
git add backend/app/services/akshare_service.py
git commit -m "feat: add AkShare data service for market/financial/fund flow queries"
```

---

### Task 4: 数据源服务 — Tushare

**Files:**
- Create: `backend/app/services/tushare_service.py`

- [ ] **Step 1: 创建 Tushare 服务**

```python
import tushare as ts
from app.config import TUSHARE_TOKEN
from datetime import datetime


class TushareService:
    """Tushare Pro 数据源服务，覆盖行情、财务指标、宏观。"""

    def __init__(self):
        if TUSHARE_TOKEN:
            ts.set_token(TUSHARE_TOKEN)
        self.pro = ts.pro_api() if TUSHARE_TOKEN else None

    def get_daily(self, ts_code: str, start_date: str = "", end_date: str = "") -> list[dict]:
        """获取日线行情。ts_code 格式如 000001.SZ。"""
        if not self.pro:
            return []
        df = self.pro.daily(
            ts_code=ts_code,
            start_date=start_date or "20260101",
            end_date=end_date or datetime.now().strftime("%Y%m%d"),
        )
        return df.to_dict(orient="records") if not df.empty else []

    def get_daily_basic(self, ts_code: str, trade_date: str = "") -> list[dict]:
        """获取每日基本面指标（PE/PB/市值）。"""
        if not self.pro:
            return []
        df = self.pro.daily_basic(
            ts_code=ts_code,
            trade_date=trade_date or datetime.now().strftime("%Y%m%d"),
            fields="ts_code,trade_date,close,turnover_rate,pe,pb,ps,total_mv,circ_mv",
        )
        return df.to_dict(orient="records") if not df.empty else []

    def get_financial_indicator(self, ts_code: str) -> list[dict]:
        """获取财务指标（ROE、毛利率等）。"""
        if not self.pro:
            return []
        df = self.pro.fina_indicator(ts_code=ts_code, fields="ts_code,end_date,roe,roa,netprofit_margin,grossprofit_margin")
        return df.to_dict(orient="records") if not df.empty else []

    def get_stock_basic(self) -> list[dict]:
        """获取全部 A 股基础信息列表。"""
        if not self.pro:
            return []
        df = self.pro.stock_basic(exchange="", list_status="L", fields="ts_code,symbol,name,area,industry,list_date")
        return df.to_dict(orient="records") if not df.empty else []


tushare_service = TushareService()
```

- [ ] **Step 2: 提交**

```bash
git add backend/app/services/tushare_service.py
git commit -m "feat: add Tushare Pro data service"
```

---

### Task 5: 数据源服务 — A-Stock-Data

**Files:**
- Create: `backend/app/services/astock_service.py`

- [ ] **Step 1: 创建 A-Stock-Data 服务**

参考 `.claude/skills/a-stock-data/SKILL.md` 中的接口封装关键功能：

```python
import httpx
import json
from datetime import datetime, timedelta
from typing import Optional

AK_TOOL_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
}


def _em_get(url: str, params: dict = None) -> dict:
    """东财统一请求入口，内置限流。"""
    import time, random
    time.sleep(1 + random.random())
    with httpx.Client(timeout=10) as client:
        r = client.get(url, params=params, headers=AK_TOOL_HEADERS)
        r.raise_for_status()
        return r.json()


class AStockService:
    """A-Stock-Data 数据源服务，覆盖行情、研报、资金面。"""

    def get_stock_quote_tx(self, code: str) -> Optional[dict]:
        """腾讯接口获取个股实时报价（PE/PB/市值/涨跌停）。"""
        market_prefix = "sh" if code.startswith("6") else "sz"
        url = f"http://qt.gtimg.cn/q={market_prefix}{code}"
        with httpx.Client(timeout=5) as client:
            r = client.get(url, headers=AK_TOOL_HEADERS)
            if not r.text.startswith("v_"):
                return None
            parts = r.text.split("~")
            if len(parts) < 50:
                return None
            return {
                "code": code,
                "name": parts[1],
                "price": float(parts[3]),
                "last_close": float(parts[4]),
                "change_pct": float(parts[32]) if parts[32] else 0,
                "pe": float(parts[39]) if parts[39] else 0,
                "pb": float(parts[46]) if parts[46] else 0,
                "total_mv": float(parts[44]) if parts[44] else 0,
            }

    def get_stock_concept_blocks(self, code: str) -> list[dict]:
        """获取个股所属概念板块（东财 slist）。"""
        market = "0" if code.startswith("6") else "1"
        secid = f"{market}.{code}"
        url = "https://push2.eastmoney.com/api/qt/slist/get"
        params = {"spt": 3, "fltt": 2, "invt": 2, "secid": secid, "fields": "f12,f14,f3,f62"}
        data = _em_get(url, params)
        return data.get("data", {}).get("diff", []) if data.get("data") else []

    def get_research_reports(self, code: str, page: int = 1, size: int = 10) -> list[dict]:
        """获取个股研报列表（东财 reportapi）。"""
        url = "https://reportapi.eastmoney.com/report/list"
        params = {
            "industryCode": "*", "pageSize": size, "industry": "",
            "rating": "", "ratingChange": "", "companyType": "",
            "reportType": "0", "pageNum": page,
            "qType": "1", "beginTime": "", "endTime": "",
            "code": code,
        }
        data = _em_get(url, params)
        return data.get("data", []) if data else []

    def get_fund_flow_minute(self, code: str) -> list[dict]:
        """个股分钟级资金流向（东财 push2）。"""
        market = "1" if code.startswith("0") else "0" if code.startswith("6") else "0"
        secid = f"{market}.{code}"
        url = "https://push2.eastmoney.com/api/qt/stock/fflow/daykline/get"
        params = {
            "secid": secid, "fields1": "f1,f2,f3,f7",
            "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61,f62,f63,f64,f65",
            "lmt": 0, "klt": 101, "secid2": "",
        }
        data = _em_get(url, params)
        klines = data.get("data", {}).get("klines", [])
        result = []
        for line in klines:
            parts = line.split(",")
            result.append({
                "time": parts[0],
                "main_net_inflow": float(parts[1]) if len(parts) > 1 else 0,
            })
        return result


astock_service = AStockService()
```

- [ ] **Step 2: 提交**

```bash
git add backend/app/services/astock_service.py
git commit -m "feat: add A-Stock-Data service for quotes, research reports, fund flow"
```

---

### Task 6: LLM 服务

**Files:**
- Create: `backend/app/services/llm_service.py`

- [ ] **Step 1: 创建 LLM 服务**

```python
import json
from anthropic import Anthropic
from app.config import ANTHROPIC_API_KEY, LLM_MODEL, LLM_MAX_TOKENS

client = Anthropic(api_key=ANTHROPIC_API_KEY) if ANTHROPIC_API_KEY else None

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
    """调用 LLM 生成产业链分析结果。"""
    if not client:
        return _mock_chain_analysis(industry)

    response = client.messages.create(
        model=LLM_MODEL,
        max_tokens=LLM_MAX_TOKENS,
        messages=[{"role": "user", "content": CHAIN_ANALYSIS_PROMPT.format(industry=industry)}],
    )

    text = response.content[0].text
    # 提取 JSON（可能被 markdown 代码块包裹）
    if "```json" in text:
        text = text.split("```json")[1].split("```")[0]
    elif "```" in text:
        text = text.split("```")[1].split("```")[0]

    return json.loads(text.strip())


def generate_report_stream(industry: str, chain_data: str):
    """流式生成投资报告。"""
    if not client:
        yield _mock_report(industry)
        return

    prompt = REPORT_GENERATION_PROMPT.format(industry=industry, chain_data=chain_data)

    with client.messages.stream(
        model=LLM_MODEL,
        max_tokens=LLM_MAX_TOKENS * 2,
        messages=[{"role": "user", "content": prompt}],
    ) as stream:
        for text in stream.text_stream:
            yield text


def _mock_chain_analysis(industry: str) -> dict:
    """Mock 数据，用于无 API Key 时开发调试。"""
    return {
        "summary": {
            "market_size": "¥1.2T (2024)",
            "growth_rate": "+18.3%",
            "overall_rating": "B+",
            "opportunity_count": 14,
            "high_confidence_count": 3,
        },
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
    """Mock 报告，用于无 API Key 时开发调试。"""
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
```

- [ ] **Step 2: 提交**

```bash
git add backend/app/services/llm_service.py
git commit -m "feat: add LLM service for chain analysis and report generation"
```

---

### Task 7: 后端 API — 产业链分析路由

**Files:**
- Create: `backend/app/routers/chain.py`
- Modify: `backend/app/main.py`

- [ ] **Step 1: 创建 backend/app/routers/chain.py**

```python
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.db import get_db
from app.models.models import ChainAnalysis
from app.services.llm_service import analyze_chain
from datetime import datetime, timedelta
import json

router = APIRouter(prefix="/api/chain", tags=["chain"])


class AnalyzeRequest(BaseModel):
    industry: str


@router.post("/analyze")
async def analyze(req: AnalyzeRequest, db: Session = Depends(get_db)):
    # 检查缓存
    cutoff = datetime.now() - timedelta(days=7)
    cached = db.query(ChainAnalysis).filter(
        ChainAnalysis.industry == req.industry,
        ChainAnalysis.created_at >= cutoff,
    ).order_by(ChainAnalysis.created_at.desc()).first()

    if cached:
        return json.loads(cached.result_json)

    result = analyze_chain(req.industry)

    record = ChainAnalysis(
        industry=req.industry,
        result_json=json.dumps(result, ensure_ascii=False),
    )
    db.add(record)
    db.commit()
    db.refresh(record)

    return result


@router.get("/history")
async def history(db: Session = Depends(get_db)):
    records = db.query(ChainAnalysis).order_by(ChainAnalysis.created_at.desc()).limit(20).all()
    return [{"id": r.id, "industry": r.industry, "created_at": r.created_at.isoformat()} for r in records]


@router.get("/{analysis_id}")
async def get_analysis(analysis_id: int, db: Session = Depends(get_db)):
    record = db.query(ChainAnalysis).filter(ChainAnalysis.id == analysis_id).first()
    if not record:
        raise HTTPException(404, "Analysis not found")
    return {"id": record.id, "industry": record.industry, "result": json.loads(record.result_json), "created_at": record.created_at.isoformat()}
```

- [ ] **Step 2: 注册路由到 main.py**

Add to `backend/app/main.py`:
```python
from app.routers import chain
app.include_router(chain.router)
```

- [ ] **Step 3: 测试 API**

Run: `curl -X POST http://localhost:8000/api/chain/analyze -H "Content-Type: application/json" -d '{"industry":"新能源汽车"}'`
Expected: 返回 JSON 包含 upstream/midstream/downstream

- [ ] **Step 4: 提交**

```bash
git add backend/app/routers/chain.py backend/app/main.py
git commit -m "feat: add chain analysis API endpoint with caching"
```

---

### Task 8: 后端 API — 数据查询路由

**Files:**
- Create: `backend/app/routers/data.py`
- Modify: `backend/app/main.py`

- [ ] **Step 1: 创建 backend/app/routers/data.py**

```python
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.db import get_db
from app.models.models import DataCache
from app.services.akshare_service import akshare_service
from app.services.tushare_service import tushare_service
from app.services.astock_service import astock_service
from datetime import datetime
import hashlib
import json

router = APIRouter(prefix="/api/data", tags=["data"])


def _cache_get(db: Session, key: str):
    cached = db.query(DataCache).filter(DataCache.cache_key == key).first()
    if cached and cached.expires_at > datetime.now():
        return json.loads(cached.result_json)
    return None


def _cache_set(db: Session, key: str, data: dict, ttl: int):
    from datetime import timedelta
    db.query(DataCache).filter(DataCache.cache_key == key).delete()
    record = DataCache(
        cache_key=key,
        result_json=json.dumps(data, ensure_ascii=False, default=str),
        expires_at=datetime.now() + timedelta(seconds=ttl),
    )
    db.add(record)
    db.commit()


class QueryRequest(BaseModel):
    source: str  # akshare / tushare / astock
    action: str
    params: dict = {}


@router.post("/query")
async def query(req: QueryRequest, db: Session = Depends(get_db)):
    cache_key = hashlib.md5(f"{req.source}:{req.action}:{json.dumps(req.params, sort_keys=True)}".encode()).hexdigest()

    cached = _cache_get(db, cache_key)
    if cached:
        return cached

    if req.source == "akshare":
        svc = akshare_service
    elif req.source == "tushare":
        svc = tushare_service
    elif req.source == "astock":
        svc = astock_service
    else:
        raise HTTPException(400, f"Unknown source: {req.source}")

    handler = getattr(svc, req.action, None)
    if not handler:
        raise HTTPException(400, f"Unknown action: {req.action}")

    result = handler(**req.params)
    ttl = 300 if "hist" in req.action or "realtime" in req.action else 86400
    _cache_set(db, cache_key, result, ttl)

    return result


@router.get("/stock/{code}")
async def stock_quote(code: str):
    quote = astock_service.get_stock_quote_tx(code)
    if not quote:
        raise HTTPException(404, f"Stock {code} not found")
    return quote


@router.get("/stock/{code}/hist")
async def stock_hist(code: str, period: str = "daily"):
    return akshare_service.get_stock_hist(code, period=period)


@router.get("/stock/{code}/financial")
async def stock_financial(code: str):
    return akshare_service.get_stock_financial(code)


@router.get("/stock/{code}/fund-flow")
async def stock_fund_flow(code: str):
    return akshare_service.get_fund_flow(code)


@router.get("/stock/{code}/reports")
async def stock_reports(code: str, page: int = 1, size: int = 10):
    return astock_service.get_research_reports(code, page=page, size=size)


@router.get("/stock/{code}/blocks")
async def stock_blocks(code: str):
    return astock_service.get_stock_concept_blocks(code)
```

- [ ] **Step 2: 注册路由到 main.py**

```python
from app.routers import data
app.include_router(data.router)
```

- [ ] **Step 3: 测试 API**

Run: `curl http://localhost:8000/api/data/stock/000001`
Expected: 返回个股实时报价 JSON

- [ ] **Step 4: 提交**

```bash
git add backend/app/routers/data.py backend/app/main.py
git commit -m "feat: add data query API with caching and multi-source support"
```

---

### Task 9: 后端 API — 报告生成路由

**Files:**
- Create: `backend/app/routers/report.py`
- Modify: `backend/app/main.py`

- [ ] **Step 1: 创建 backend/app/routers/report.py**

```python
import json
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.db import get_db
from app.models.models import Report, ChainAnalysis
from app.services.llm_service import generate_report_stream, analyze_chain
from sse_starlette.sse import EventSourceResponse
from datetime import datetime

router = APIRouter(prefix="/api/report", tags=["report"])


class GenerateRequest(BaseModel):
    industry: str
    chain_analysis_id: int | None = None


@router.post("/generate")
async def generate(req: GenerateRequest, db: Session = Depends(get_db)):
    # 获取或生成产业链分析数据
    chain_data = ""
    if req.chain_analysis_id:
        record = db.query(ChainAnalysis).filter(ChainAnalysis.id == req.chain_analysis_id).first()
        if record:
            chain_data = record.result_json

    if not chain_data:
        chain_result = analyze_chain(req.industry)
        chain_data = json.dumps(chain_result, ensure_ascii=False, default=str)

    async def event_stream():
        full_content = ""
        for chunk in generate_report_stream(req.industry, chain_data):
            full_content += chunk
            yield {"data": chunk}

        # 保存完整报告
        report = Report(
            industry=req.industry,
            content_md=full_content,
        )
        db.add(report)
        db.commit()

    return EventSourceResponse(event_stream())


@router.get("/list")
async def list_reports(db: Session = Depends(get_db)):
    records = db.query(Report).order_by(Report.created_at.desc()).limit(20).all()
    return [{"id": r.id, "industry": r.industry, "created_at": r.created_at.isoformat()} for r in records]


@router.get("/{report_id}")
async def get_report(report_id: int, db: Session = Depends(get_db)):
    record = db.query(Report).filter(Report.id == report_id).first()
    if not record:
        raise HTTPException(404, "Report not found")
    return {"id": record.id, "industry": record.industry, "content": record.content_md, "created_at": record.created_at.isoformat()}
```

- [ ] **Step 2: 注册路由到 main.py**

```python
from app.routers import report
app.include_router(report.router)
```

- [ ] **Step 3: 提交**

```bash
git add backend/app/routers/report.py backend/app/main.py
git commit -m "feat: add report generation API with SSE streaming"
```

---

### Task 10: 后端 API — 投资计划路由

**Files:**
- Create: `backend/app/routers/plan.py`
- Modify: `backend/app/main.py`

- [ ] **Step 1: 创建 backend/app/routers/plan.py**

```python
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.db import get_db
from app.models.models import InvestmentPlan

router = APIRouter(prefix="/api/plan", tags=["plan"])


class PlanCreate(BaseModel):
    stock_code: str
    stock_name: str
    direction: str  # buy / sell
    position_ratio: float
    target_price: float | None = None
    stop_loss_price: float | None = None
    reason: str | None = None


class PlanUpdate(BaseModel):
    position_ratio: float | None = None
    target_price: float | None = None
    stop_loss_price: float | None = None
    status: str | None = None
    reason: str | None = None


@router.post("/create")
async def create_plan(req: PlanCreate, db: Session = Depends(get_db)):
    if req.direction not in ("buy", "sell"):
        raise HTTPException(400, "direction must be 'buy' or 'sell'")
    if not 0 < req.position_ratio <= 100:
        raise HTTPException(400, "position_ratio must be between 0 and 100")

    plan = InvestmentPlan(**req.model_dump())
    db.add(plan)
    db.commit()
    db.refresh(plan)
    return _plan_to_dict(plan)


@router.get("/list")
async def list_plans(db: Session = Depends(get_db)):
    plans = db.query(InvestmentPlan).order_by(InvestmentPlan.created_at.desc()).all()
    return [_plan_to_dict(p) for p in plans]


@router.put("/{plan_id}")
async def update_plan(plan_id: int, req: PlanUpdate, db: Session = Depends(get_db)):
    plan = db.query(InvestmentPlan).filter(InvestmentPlan.id == plan_id).first()
    if not plan:
        raise HTTPException(404, "Plan not found")

    updates = req.model_dump(exclude_unset=True)
    if "status" in updates and updates["status"] not in ("pending", "executing", "closed", "stopped"):
        raise HTTPException(400, f"Invalid status: {updates['status']}")

    for key, val in updates.items():
        setattr(plan, key, val)
    plan.updated_at = datetime.now()
    db.commit()
    db.refresh(plan)
    return _plan_to_dict(plan)


@router.delete("/{plan_id}")
async def delete_plan(plan_id: int, db: Session = Depends(get_db)):
    plan = db.query(InvestmentPlan).filter(InvestmentPlan.id == plan_id).first()
    if not plan:
        raise HTTPException(404, "Plan not found")
    db.delete(plan)
    db.commit()
    return {"ok": True}


def _plan_to_dict(plan: InvestmentPlan) -> dict:
    return {
        "id": plan.id,
        "stock_code": plan.stock_code,
        "stock_name": plan.stock_name,
        "direction": plan.direction,
        "position_ratio": plan.position_ratio,
        "target_price": plan.target_price,
        "stop_loss_price": plan.stop_loss_price,
        "reason": plan.reason,
        "status": plan.status,
        "created_at": plan.created_at.isoformat(),
        "updated_at": plan.updated_at.isoformat(),
    }
```

- [ ] **Step 2: 注册路由到 main.py**

```python
from app.routers import plan
app.include_router(plan.router)
```

- [ ] **Step 3: 测试 CRUD**

```bash
curl -X POST http://localhost:8000/api/plan/create -H "Content-Type: application/json" -d '{"stock_code":"300750","stock_name":"宁德时代","direction":"buy","position_ratio":15,"target_price":280,"stop_loss_price":220,"reason":"动力电池龙头"}'
curl http://localhost:8000/api/plan/list
curl -X PUT http://localhost:8000/api/plan/1 -H "Content-Type: application/json" -d '{"status":"executing"}'
curl -X DELETE http://localhost:8000/api/plan/1
```

- [ ] **Step 4: 提交**

```bash
git add backend/app/routers/plan.py backend/app/main.py
git commit -m "feat: add investment plan CRUD API"
```

---

### Task 11: 前端 — API 服务层和类型定义

**Files:**
- Create: `frontend/src/services/api.ts`

- [ ] **Step 1: 创建 API 封装**

```typescript
import axios from 'axios';

const api = axios.create({ baseURL: 'http://localhost:8000' });

// --- 产业链 ---
export async function analyzeChain(industry: string) {
  const { data } = await api.post('/api/chain/analyze', { industry });
  return data;
}

export async function getChainHistory() {
  const { data } = await api.get('/api/chain/history');
  return data;
}

// --- 数据查询 ---
export async function queryData(source: string, action: string, params: Record<string, unknown> = {}) {
  const { data } = await api.post('/api/data/query', { source, action, params });
  return data;
}

export async function getStockQuote(code: string) {
  const { data } = await api.get(`/api/data/stock/${code}`);
  return data;
}

export async function getStockHist(code: string, period = 'daily') {
  const { data } = await api.get(`/api/data/stock/${code}/hist`, { params: { period } });
  return data;
}

export async function getStockFinancial(code: string) {
  const { data } = await api.get(`/api/data/stock/${code}/financial`);
  return data;
}

export async function getStockReports(code: string, page = 1) {
  const { data } = await api.get(`/api/data/stock/${code}/reports`, { params: { page } });
  return data;
}

export async function getStockBlocks(code: string) {
  const { data } = await api.get(`/api/data/stock/${code}/blocks`);
  return data;
}

export async function getStockFundFlow(code: string) {
  const { data } = await api.get(`/api/data/stock/${code}/fund-flow`);
  return data;
}

// --- 报告 ---
export async function generateReport(industry: string, onChunk: (text: string) => void) {
  const resp = await fetch(`http://localhost:8000/api/report/generate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ industry }),
  });

  const reader = resp.body?.getReader();
  if (!reader) return;

  const decoder = new TextDecoder();
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    const text = decoder.decode(value);
    // Parse SSE: "data: {content}\n\n"
    for (const line of text.split('\n')) {
      if (line.startsWith('data: ')) {
        onChunk(line.slice(6));
      }
    }
  }
}

export async function listReports() {
  const { data } = await api.get('/api/report/list');
  return data;
}

export async function getReport(id: number) {
  const { data } = await api.get(`/api/report/${id}`);
  return data;
}

// --- 投资计划 ---
export async function createPlan(plan: {
  stock_code: string; stock_name: string; direction: string;
  position_ratio: number; target_price?: number; stop_loss_price?: number; reason?: string;
}) {
  const { data } = await api.post('/api/plan/create', plan);
  return data;
}

export async function listPlans() {
  const { data } = await api.get('/api/plan/list');
  return data;
}

export async function updatePlan(id: number, updates: Record<string, unknown>) {
  const { data } = await api.put(`/api/plan/${id}`, updates);
  return data;
}

export async function deletePlan(id: number) {
  const { data } = await api.delete(`/api/plan/${id}`);
  return data;
}
```

- [ ] **Step 2: 提交**

```bash
git add frontend/src/services/api.ts
git commit -m "feat: add frontend API service layer"
```

---

### Task 12: 前端 — 产业链图谱页面

**Files:**
- Modify: `frontend/src/pages/ChainPage.tsx`

- [ ] **Step 1: 实现 ChainPage**

```tsx
import { useState } from 'react';
import { Input, Button, Card, Row, Col, Tag, Table, Space, Spin, Typography, message } from 'antd';
import { ApartmentOutlined, ThunderboltOutlined, RightOutlined, SearchOutlined } from '@ant-design/icons';
import { analyzeChain } from '../services/api';

const { Text } = Typography;

const oppColors: Record<string, string> = {
  high: 'green',
  mid: 'orange',
  low: 'default',
};

const oppLabels: Record<string, string> = {
  high: '高',
  mid: '中',
  low: '低',
};

const colColors: Record<string, string> = {
  upstream: '#a371f7',
  midstream: '#388bfd',
  downstream: '#3fb950',
};

const colTitles: Record<string, string> = {
  upstream: '上游原材料',
  midstream: '中游制造',
  downstream: '下游应用',
};

interface ChainItem {
  name: string;
  opp_level: string;
  summary: string;
}

interface ChainResult {
  summary: {
    market_size: string;
    growth_rate: string;
    overall_rating: string;
    opportunity_count: number;
    high_confidence_count: number;
  };
  upstream: ChainItem[];
  midstream: ChainItem[];
  downstream: ChainItem[];
}

export default function ChainPage() {
  const [industry, setIndustry] = useState('新能源汽车');
  const [loading, setLoading] = useState(false);
  const [data, setData] = useState<ChainResult | null>(null);

  const handleAnalyze = async () => {
    if (!industry.trim()) return;
    setLoading(true);
    try {
      const result = await analyzeChain(industry.trim());
      setData(result);
    } catch {
      message.error('分析失败，请检查 API Key 或网络');
    } finally {
      setLoading(false);
    }
  };

  const allItems = [
    ...(data?.upstream || []).map(i => ({ ...i, stage: 'upstream' })),
    ...(data?.midstream || []).map(i => ({ ...i, stage: 'midstream' })),
    ...(data?.downstream || []).map(i => ({ ...i, stage: 'downstream' })),
  ].sort((a, b) => {
    const order = { high: 0, mid: 1, low: 2 };
    return (order[a.opp_level] || 2) - (order[b.opp_level] || 2);
  });

  return (
    <div>
      <Space style={{ marginBottom: 16 }}>
        <Input
          value={industry}
          onChange={e => setIndustry(e.target.value)}
          placeholder="输入产业名称…"
          style={{ width: 280 }}
          onPressEnter={handleAnalyze}
        />
        <Button type="primary" icon={<ThunderboltOutlined />} onClick={handleAnalyze} loading={loading}>
          启动 AI 分析
        </Button>
      </Space>

      <Spin spinning={loading}>
        {data && (
          <>
            <Row gutter={8} style={{ marginBottom: 16 }}>
              <Col span={6}>
                <Card size="small"><Text type="secondary" style={{ fontSize: 11 }}>产业规模</Text><br />
                <Text strong style={{ fontSize: 20, color: '#388bfd' }}>{data.summary.market_size}</Text><br />
                <Text type="secondary" style={{ fontSize: 11 }}>同比 {data.summary.growth_rate}</Text></Card>
              </Col>
              <Col span={6}>
                <Card size="small"><Text type="secondary" style={{ fontSize: 11 }}>识别机会数</Text><br />
                <Text strong style={{ fontSize: 20, color: '#3fb950' }}>{data.summary.opportunity_count}</Text><br />
                <Text type="secondary" style={{ fontSize: 11 }}>高确信度 {data.summary.high_confidence_count} 个</Text></Card>
              </Col>
              <Col span={6}>
                <Card size="small"><Text type="secondary" style={{ fontSize: 11 }}>综合评级</Text><br />
                <Text strong style={{ fontSize: 20, color: '#d29922' }}>{data.summary.overall_rating}</Text></Card>
              </Col>
              <Col span={6}>
                <Card size="small"><Text type="secondary" style={{ fontSize: 11 }}>数据更新</Text><br />
                <Text style={{ fontSize: 13 }}>{new Date().toLocaleString('zh-CN')}</Text></Card>
              </Col>
            </Row>

            <Text style={{ fontSize: 11, color: '#6e7681', textTransform: 'uppercase', letterSpacing: '0.08em' }}>
              产业链全景 — {industry}
            </Text>

            <Row gutter={8} style={{ marginTop: 8, marginBottom: 16 }}>
              {(['upstream', 'midstream', 'downstream'] as const).map((stage, idx) => (
                <Col key={stage} style={{ display: 'flex', alignItems: 'center' }}>
                  {idx > 0 && <RightOutlined style={{ color: '#6e7681', margin: '0 4px' }} />}
                  <Card
                    size="small"
                    title={<Text style={{ color: colColors[stage] }}>{colTitles[stage]}</Text>}
                    style={{ flex: 1 }}
                  >
                    {data[stage].map((item, i) => (
                      <div key={i} style={{
                        padding: '6px 8px', marginBottom: 3, borderRadius: 4,
                        background: '#21262d', cursor: 'pointer', fontSize: 12,
                        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                      }}>
                        <span>{item.name}</span>
                        <Tag color={oppColors[item.opp_level]} style={{ margin: 0 }}>
                          {oppLabels[item.opp_level]}
                        </Tag>
                      </div>
                    ))}
                  </Card>
                </Col>
              ))}
            </Row>

            <Text style={{ fontSize: 11, color: '#6e7681' }}>机会优先级排序</Text>
            <Table
              size="small"
              dataSource={allItems}
              rowKey={(_, i) => String(i)}
              pagination={false}
              columns={[
                { title: '环节', dataIndex: 'name', render: t => <Text strong>{t}</Text> },
                {
                  title: '阶段', dataIndex: 'stage',
                  render: t => <Tag color={colColors[t]}>{colTitles[t]}</Tag>
                },
                {
                  title: '机会评级', dataIndex: 'opp_level',
                  render: t => <Tag color={oppColors[t]}>{oppLabels[t]}</Tag>
                },
                { title: '说明', dataIndex: 'summary', width: '40%' },
              ]}
            />
          </>
        )}
      </Spin>
    </div>
  );
}
```

- [ ] **Step 2: 验证页面**

Run: 前后端同时启动，访问 `http://localhost:5173/chain`，点击"启动 AI 分析"
Expected: 显示 KPI 卡片、三列产业链图谱、机会排序表格

- [ ] **Step 3: 提交**

```bash
git add frontend/src/pages/ChainPage.tsx
git commit -m "feat: implement chain analysis page with KPI cards and chain map"
```

---

### Task 13: 前端 — 数据查询页面

**Files:**
- Modify: `frontend/src/pages/DataPage.tsx`

- [ ] **Step 1: 实现 DataPage**

```tsx
import { useState } from 'react';
import { Input, Button, Card, Row, Col, Table, Tag, Space, Typography, Select, Spin, message, Descriptions } from 'antd';
import { SearchOutlined, DatabaseOutlined } from '@ant-design/icons';
import { getStockQuote, getStockHist, getStockFinancial, getStockReports, getStockBlocks, getStockFundFlow } from '../services/api';

const { Text } = Typography;

type Tab = 'quote' | 'hist' | 'financial' | 'reports' | 'blocks' | 'fundflow';

export default function DataPage() {
  const [code, setCode] = useState('300750');
  const [loading, setLoading] = useState(false);
  const [activeTab, setActiveTab] = useState<Tab>('quote');
  const [quote, setQuote] = useState<Record<string, any> | null>(null);
  const [hist, setHist] = useState<Record<string, any>[]>([]);
  const [financial, setFinancial] = useState<Record<string, any>[]>([]);
  const [reports, setReports] = useState<Record<string, any>[]>([]);
  const [blocks, setBlocks] = useState<Record<string, any>[]>([]);
  const [fundFlow, setFundFlow] = useState<Record<string, any>[]>([]);

  const handleSearch = async () => {
    if (!code.trim()) return;
    setLoading(true);
    try {
      const q = await getStockQuote(code.trim());
      setQuote(q);
      setActiveTab('quote');
    } catch {
      message.error('查询失败');
    } finally {
      setLoading(false);
    }
  };

  const loadTab = async (tab: Tab) => {
    setActiveTab(tab);
    setLoading(true);
    try {
      switch (tab) {
        case 'hist':
          setHist(await getStockHist(code.trim()));
          break;
        case 'financial':
          setFinancial(await getStockFinancial(code.trim()));
          break;
        case 'reports':
          setReports(await getStockReports(code.trim()));
          break;
        case 'blocks':
          setBlocks(await getStockBlocks(code.trim()));
          break;
        case 'fundflow':
          setFundFlow(await getStockFundFlow(code.trim()));
          break;
      }
    } catch {
      message.error('查询失败');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <Space style={{ marginBottom: 16 }}>
        <Input
          value={code}
          onChange={e => setCode(e.target.value)}
          placeholder="输入股票代码…"
          style={{ width: 200 }}
          onPressEnter={handleSearch}
        />
        <Button type="primary" icon={<SearchOutlined />} onClick={handleSearch} loading={loading}>
          查询
        </Button>
      </Space>

      <Row gutter={8} style={{ marginBottom: 16 }}>
        {(['quote', 'hist', 'financial', 'reports', 'blocks', 'fundflow'] as const).map(tab => (
          <Col key={tab}>
            <Card
              size="small"
              hoverable
              onClick={() => loadTab(tab)}
              style={{ borderColor: activeTab === tab ? '#1f6feb' : undefined, cursor: 'pointer', minWidth: 100 }}
            >
              <Text style={{ fontSize: 12 }}>
                {{ quote: '实时报价', hist: '历史K线', financial: '财务指标', reports: '研报', blocks: '概念板块', fundflow: '资金流向' }[tab]}
              </Text>
            </Card>
          </Col>
        ))}
      </Row>

      <Spin spinning={loading}>
        {activeTab === 'quote' && quote && (
          <Descriptions bordered size="small" column={3}>
            <Descriptions.Item label="代码">{quote.code}</Descriptions.Item>
            <Descriptions.Item label="名称">{quote.name}</Descriptions.Item>
            <Descriptions.Item label="现价">{quote.price}</Descriptions.Item>
            <Descriptions.Item label="昨收">{quote.last_close}</Descriptions.Item>
            <Descriptions.Item label="涨跌幅"><Text style={{ color: quote.change_pct >= 0 ? '#3fb950' : '#f85149' }}>{quote.change_pct}%</Text></Descriptions.Item>
            <Descriptions.Item label="PE">{quote.pe}</Descriptions.Item>
            <Descriptions.Item label="PB">{quote.pb}</Descriptions.Item>
            <Descriptions.Item label="总市值">{quote.total_mv}</Descriptions.Item>
          </Descriptions>
        )}

        {activeTab === 'hist' && (
          <Table size="small" dataSource={hist} pagination={{ pageSize: 20 }} columns={Object.keys(hist[0] || {}).map(k => ({ title: k, dataIndex: k, key: k }))} />
        )}

        {activeTab === 'financial' && (
          <Table size="small" dataSource={financial} pagination={{ pageSize: 20 }} columns={Object.keys(financial[0] || {}).map(k => ({ title: k, dataIndex: k, key: k }))} />
        )}

        {activeTab === 'reports' && reports.length > 0 && (
          <Table size="small" dataSource={reports} pagination={{ pageSize: 10 }} rowKey="id" columns={[
            { title: '标题', dataIndex: 'title', ellipsis: true },
            { title: '机构', dataIndex: 'orgSName' },
            { title: '评级', dataIndex: 'sRatingName' },
            { title: '日期', dataIndex: 'publishDate', width: 120 },
          ]} />
        )}

        {activeTab === 'blocks' && blocks.length > 0 && (
          <Table size="small" dataSource={blocks} pagination={false} columns={Object.keys(blocks[0] || {}).map(k => ({ title: k, dataIndex: k, key: k }))} />
        )}

        {activeTab === 'fundflow' && fundFlow.length > 0 && (
          <Table size="small" dataSource={fundFlow} pagination={{ pageSize: 20 }} columns={Object.keys(fundFlow[0] || {}).map(k => ({ title: k, dataIndex: k, key: k }))} />
        )}
      </Spin>
    </div>
  );
}
```

- [ ] **Step 2: 提交**

```bash
git add frontend/src/pages/DataPage.tsx
git commit -m "feat: implement data query page with 6 query types"
```

---

### Task 14: 前端 — 投资报告页面

**Files:**
- Modify: `frontend/src/pages/ReportPage.tsx`
- Create: `frontend/src/components/MarkdownRenderer.tsx`

- [ ] **Step 1: 创建 Markdown 渲染组件**

Install: `cd frontend && npm install react-markdown`

Create `frontend/src/components/MarkdownRenderer.tsx`:
```tsx
import ReactMarkdown from 'react-markdown';

export default function MarkdownRenderer({ content }: { content: string }) {
  return (
    <div style={{ fontSize: 14, lineHeight: 1.8, color: '#8b949e' }}>
      <ReactMarkdown
        components={{
          h1: ({ children }) => <h1 style={{ fontSize: 22, color: '#e6edf3', borderBottom: '1px solid rgba(48,54,61,0.9)', paddingBottom: 8 }}>{children}</h1>,
          h2: ({ children }) => <h2 style={{ fontSize: 18, color: '#e6edf3', marginTop: 24 }}>{children}</h2>,
          h3: ({ children }) => <h3 style={{ fontSize: 15, color: '#e6edf3', marginTop: 16 }}>{children}</h3>,
          p: ({ children }) => <p style={{ marginBottom: 12 }}>{children}</p>,
          strong: ({ children }) => <strong style={{ color: '#e6edf3' }}>{children}</strong>,
          ul: ({ children }) => <ul style={{ paddingLeft: 20 }}>{children}</ul>,
          li: ({ children }) => <li style={{ marginBottom: 4 }}>{children}</li>,
          ol: ({ children }) => <ol style={{ paddingLeft: 20 }}>{children}</ol>,
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}
```

- [ ] **Step 2: 实现 ReportPage**

```tsx
import { useState } from 'react';
import { Input, Button, Space, Typography, Spin, List, message } from 'antd';
import { FileTextOutlined, ThunderboltOutlined } from '@ant-design/icons';
import { generateReport, listReports, getReport } from '../services/api';
import MarkdownRenderer from '../components/MarkdownRenderer';

const { Text } = Typography;

export default function ReportPage() {
  const [industry, setIndustry] = useState('新能源汽车');
  const [generating, setGenerating] = useState(false);
  const [content, setContent] = useState('');
  const [reports, setReports] = useState<{ id: number; industry: string; created_at: string }[]>([]);
  const [loaded, setLoaded] = useState(false);

  const handleGenerate = async () => {
    if (!industry.trim()) return;
    setGenerating(true);
    setContent('');

    try {
      await generateReport(industry.trim(), (chunk) => {
        setContent(prev => prev + chunk);
      });
      message.success('报告生成完毕');
      loadHistory();
    } catch {
      message.error('生成失败');
    } finally {
      setGenerating(false);
    }
  };

  const loadHistory = async () => {
    const data = await listReports();
    setReports(data);
    setLoaded(true);
  };

  const loadReport = async (id: number) => {
    const data = await getReport(id);
    setContent(data.content);
  };

  if (!loaded) {
    loadHistory();
  }

  return (
    <div style={{ display: 'flex', gap: 16 }}>
      <div style={{ width: 260, flexShrink: 0 }}>
        <Space direction="vertical" style={{ width: '100%' }}>
          <Input value={industry} onChange={e => setIndustry(e.target.value)} placeholder="输入产业名称…" />
          <Button type="primary" icon={<ThunderboltOutlined />} onClick={handleGenerate} loading={generating} block>
            生成投资报告
          </Button>
        </Space>

        {reports.length > 0 && (
          <div style={{ marginTop: 16 }}>
            <Text type="secondary" style={{ fontSize: 11, textTransform: 'uppercase' }}>历史报告</Text>
            <List
              size="small"
              dataSource={reports}
              renderItem={r => (
                <List.Item onClick={() => loadReport(r.id)} style={{ cursor: 'pointer', padding: '6px 0' }}>
                  <div>
                    <Text style={{ fontSize: 12 }}>{r.industry}</Text><br />
                    <Text type="secondary" style={{ fontSize: 10 }}>{new Date(r.created_at).toLocaleDateString('zh-CN')}</Text>
                  </div>
                </List.Item>
              )}
            />
          </div>
        )}
      </div>

      <div style={{ flex: 1, background: '#161b22', borderRadius: 8, padding: 16 }}>
        {content ? (
          <MarkdownRenderer content={content} />
        ) : generating ? (
          <Spin tip="AI 正在生成报告..." />
        ) : (
          <Text type="secondary">输入产业名称并点击"生成投资报告"开始</Text>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 3: 提交**

```bash
git add frontend/src/pages/ReportPage.tsx frontend/src/components/MarkdownRenderer.tsx
git commit -m "feat: implement report page with SSE streaming and markdown rendering"
```

---

### Task 15: 前端 — 投资计划页面

**Files:**
- Modify: `frontend/src/pages/PlanPage.tsx`

- [ ] **Step 1: 实现 PlanPage**

```tsx
import { useState, useEffect } from 'react';
import { Button, Card, Row, Col, Table, Tag, Space, Modal, Input, InputNumber, Select, message, Popconfirm } from 'antd';
import { PlusOutlined, EditOutlined, DeleteOutlined } from '@ant-design/icons';
import { createPlan, listPlans, updatePlan, deletePlan } from '../services/api';

const { TextArea } = Input;

interface Plan {
  id: number;
  stock_code: string;
  stock_name: string;
  direction: string;
  position_ratio: number;
  target_price: number | null;
  stop_loss_price: number | null;
  reason: string | null;
  status: string;
  created_at: string;
}

const statusConfig: Record<string, { color: string; label: string }> = {
  pending: { color: 'default', label: '待执行' },
  executing: { color: 'processing', label: '执行中' },
  closed: { color: 'success', label: '已平仓' },
  stopped: { color: 'error', label: '已止损' },
};

export default function PlanPage() {
  const [plans, setPlans] = useState<Plan[]>([]);
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<Plan | null>(null);
  const [form, setForm] = useState({
    stock_code: '', stock_name: '', direction: 'buy',
    position_ratio: 10, target_price: undefined as number | undefined,
    stop_loss_price: undefined as number | undefined, reason: '',
  });

  const load = async () => {
    const data = await listPlans();
    setPlans(data);
  };

  useEffect(() => { load(); }, []);

  const handleSubmit = async () => {
    if (!form.stock_code || !form.stock_name) {
      message.error('请填写股票代码和名称');
      return;
    }
    if (editing) {
      await updatePlan(editing.id, form);
      message.success('更新成功');
    } else {
      await createPlan(form);
      message.success('创建成功');
    }
    setModalOpen(false);
    setEditing(null);
    load();
  };

  const handleEdit = (plan: Plan) => {
    setEditing(plan);
    setForm({
      stock_code: plan.stock_code, stock_name: plan.stock_name,
      direction: plan.direction, position_ratio: plan.position_ratio,
      target_price: plan.target_price ?? undefined,
      stop_loss_price: plan.stop_loss_price ?? undefined,
      reason: plan.reason || '',
    });
    setModalOpen(true);
  };

  const handleStatusChange = async (id: number, status: string) => {
    await updatePlan(id, { status });
    load();
  };

  return (
    <div>
      <Button type="primary" icon={<PlusOutlined />} onClick={() => { setEditing(null); setForm({ stock_code: '', stock_name: '', direction: 'buy', position_ratio: 10, reason: '' }); setModalOpen(true); }} style={{ marginBottom: 16 }}>
        新建计划
      </Button>

      <Table
        dataSource={plans}
        rowKey="id"
        columns={[
          { title: '代码', dataIndex: 'stock_code', width: 80 },
          { title: '名称', dataIndex: 'stock_name', render: t => <strong>{t}</strong> },
          {
            title: '方向', dataIndex: 'direction',
            render: t => <Tag color={t === 'buy' ? 'green' : 'red'}>{t === 'buy' ? '买入' : '卖出'}</Tag>,
          },
          { title: '仓位%', dataIndex: 'position_ratio' },
          { title: '目标价', dataIndex: 'target_price', render: t => t ?? '-' },
          { title: '止损价', dataIndex: 'stop_loss_price', render: t => t ?? '-' },
          {
            title: '状态', dataIndex: 'status',
            render: (status: string, record: Plan) => (
              <Select
                size="small"
                value={status}
                onChange={v => handleStatusChange(record.id, v)}
                style={{ width: 90 }}
                options={Object.entries(statusConfig).map(([k, v]) => ({ value: k, label: v.label }))}
              />
            ),
          },
          { title: '创建时间', dataIndex: 'created_at', render: t => new Date(t).toLocaleDateString('zh-CN'), width: 120 },
          {
            title: '操作', width: 80,
            render: (_: unknown, record: Plan) => (
              <Space>
                <Button size="small" icon={<EditOutlined />} onClick={() => handleEdit(record)} />
                <Popconfirm title="确定删除？" onConfirm={async () => { await deletePlan(record.id); load(); }}>
                  <Button size="small" danger icon={<DeleteOutlined />} />
                </Popconfirm>
              </Space>
            ),
          },
        ]}
      />

      <Modal
        title={editing ? '编辑投资计划' : '新建投资计划'}
        open={modalOpen}
        onOk={handleSubmit}
        onCancel={() => setModalOpen(false)}
      >
        <Space direction="vertical" style={{ width: '100%' }}>
          <Input placeholder="股票代码" value={form.stock_code} onChange={e => setForm(f => ({ ...f, stock_code: e.target.value }))} />
          <Input placeholder="股票名称" value={form.stock_name} onChange={e => setForm(f => ({ ...f, stock_name: e.target.value }))} />
          <Select value={form.direction} onChange={v => setForm(f => ({ ...f, direction: v }))} options={[{ value: 'buy', label: '买入' }, { value: 'sell', label: '卖出' }]} />
          <InputNumber placeholder="仓位比例 (%)" min={1} max={100} value={form.position_ratio} onChange={v => setForm(f => ({ ...f, position_ratio: v ?? 10 }))} style={{ width: '100%' }} />
          <InputNumber placeholder="目标价" value={form.target_price} onChange={v => setForm(f => ({ ...f, target_price: v }))} style={{ width: '100%' }} />
          <InputNumber placeholder="止损价" value={form.stop_loss_price} onChange={v => setForm(f => ({ ...f, stop_loss_price: v }))} style={{ width: '100%' }} />
          <TextArea placeholder="买入/卖出理由" value={form.reason} onChange={e => setForm(f => ({ ...f, reason: e.target.value }))} rows={3} />
        </Space>
      </Modal>
    </div>
  );
}
```

- [ ] **Step 2: 提交**

```bash
git add frontend/src/pages/PlanPage.tsx
git commit -m "feat: implement investment plan page with CRUD and status management"
```

---

### Task 16: Docker Compose 部署配置

**Files:**
- Create: `docker-compose.yml`
- Create: `backend/Dockerfile`
- Create: `frontend/Dockerfile`
- Create: `frontend/vite.config.ts` (update proxy)

- [ ] **Step 1: 创建 backend/Dockerfile**

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN mkdir -p /app/data
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

- [ ] **Step 2: 创建 frontend/Dockerfile**

```dockerfile
FROM node:20-alpine AS build
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
```

- [ ] **Step 3: 创建 frontend/nginx.conf**

```nginx
server {
    listen 80;
    location / {
        root /usr/share/nginx/html;
        try_files $uri $uri/ /index.html;
    }
    location /api/ {
        proxy_pass http://backend:8000;
        proxy_set_header Host $host;
    }
}
```

- [ ] **Step 4: 创建 docker-compose.yml**

```yaml
version: "3.8"
services:
  backend:
    build: ./backend
    ports:
      - "8000:8000"
    environment:
      - ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}
      - TUSHARE_TOKEN=${TUSHARE_TOKEN}
    volumes:
      - backend-data:/app/data

  frontend:
    build: ./frontend
    ports:
      - "3000:80"
    depends_on:
      - backend

volumes:
  backend-data:
```

- [ ] **Step 5: 提交**

```bash
git add docker-compose.yml backend/Dockerfile frontend/Dockerfile frontend/nginx.conf
git commit -m "feat: add Docker Compose deployment config"
```

---

### Task 17: 端到端验证

- [ ] **Step 1: 启动完整应用**

```bash
# Terminal 1: backend
cd backend && uvicorn app.main:app --reload --port 8000

# Terminal 2: frontend
cd frontend && npm run dev
```

- [ ] **Step 2: 验证产业链分析**

1. 访问 `http://localhost:5173/chain`
2. 输入"新能源汽车"，点击"启动 AI 分析"
3. 验证 KPI 卡片、三列图谱、排序表格显示正确

- [ ] **Step 3: 验证数据查询**

1. 访问 `http://localhost:5173/data`
2. 输入代码 `300750`，点击查询
3. 验证实时报价、历史K线、财务指标等标签页可切换

- [ ] **Step 4: 验证报告生成**

1. 访问 `http://localhost:5173/report`
2. 输入"新能源汽车"，点击"生成投资报告"
3. 验证 SSE 流式输出正常，Markdown 渲染正确

- [ ] **Step 5: 验证投资计划 CRUD**

1. 访问 `http://localhost:5173/plan`
2. 新建计划（300750/宁德时代/买入/15%）
3. 修改状态为"执行中"
4. 删除计划

- [ ] **Step 6: 最终提交**

```bash
git add -A
git commit -m "feat: complete InvestLens AI investment workbench v0.1"
```
