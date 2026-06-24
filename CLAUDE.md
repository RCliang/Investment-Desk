# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

InvestLens (Investment-Desk) is a personal A-share investment research workbench. It combines AI-powered industry chain analysis, multi-source stock data queries, streaming report generation, and investment plan management. Backend is Python/FastAPI; frontend is React/TypeScript/Vite with Ant Design.

## Common Commands

### Backend (from `backend/`)
```bash
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000     # dev
uvicorn app.main:app --host 0.0.0.0 --port 8000  # prod
```
The dev server runs on `http://localhost:8000`. SQLite DB auto-creates at `backend/data/investlens.db` on startup (`Base.metadata.create_all` in `app/main.py`).

### Frontend (from `frontend/`)
```bash
npm install
npm run dev       # Vite dev server on http://localhost:5173
npm run build     # tsc -b && vite build
npm run lint      # ESLint
npm run preview   # preview production build
```

### Docker (full stack)
```bash
docker-compose up --build   # backend :8000, frontend :3000 (nginx proxies /api/* to backend)
```

### Environment
Backend reads from env (see `backend/app/config.py`):
- `DEEPSEEK_API_KEY` — DeepSeek API for chain analysis and report generation
- `MODEL_NAME` — Model identifier (default `deepseek-chat`; alternative `deepseek-reasoner` for R1)
- `TUSHARE_TOKEN` — Tushare Pro financial data

All default to empty strings (except `MODEL_NAME`). The LLM service falls back to mock data when `DEEPSEEK_API_KEY` is absent, so the app runs without it in development. Frontend dev requires the backend CORS origin `http://localhost:5173` (already configured in `app/main.py`).

**Local dev with `.env`** — `python-dotenv` is already in `requirements.txt`. On startup `config.py` calls `load_dotenv(BASE_DIR / ".env")`, so to set keys locally:
```bash
cd backend
copy .env.example .env   # then edit .env and fill in real keys
```
`.env` is gitignored; `.env.example` is committed as a template. Production deployments should inject real env vars instead of relying on the file.

## Architecture

### Two-service split
- **`backend/`** — FastAPI app. Entry: `app/main.py` registers four routers (`chain`, `data`, `report`, `plan`) and creates tables on startup.
- **`frontend/`** — React SPA. Entry: `src/main.tsx` → `src/App.tsx` (router + Ant Design dark theme).

### Backend layering (per feature)
Each of the four features follows the same shape:
```
routers/<feature>.py   →  HTTP endpoints, request validation, caching decisions
  └─ services/<feature>_service.py  →  business logic, external calls, LLM/data sources
```
Routers live in `app/routers/`, services in `app/services/`, ORM models in `app/models/models.py`, config in `app/config.py`, DB engine in `app/db.py`.

**Data source services** (independent of feature routers):
- `llm_service.py` — DeepSeek via OpenAI-compatible SDK; model from `MODEL_NAME` env (default `deepseek-chat`), 4096 max tokens; returns mock JSON when `DEEPSEEK_API_KEY` is unset.
- `akshare_service.py` — general A-share market/financial data via akshare.
- `tushare_service.py` — professional financial indicators via tushare (requires `TUSHARE_TOKEN`).
- `astock_service.py` — real-time quotes, research reports, fund flow, concept sectors.

### Frontend structure
- `src/pages/` — four page components matching backend features: `ChainPage`, `DataPage`, `ReportPage`, `PlanPage` (routes defined in `App.tsx`).
- `src/services/api.ts` — axios client; base URL `/api` (proxied to backend in dev via Vite, in prod via nginx).
- `src/components/` — shared UI (KPI cards, chain columns, markdown renderer, plan modal).

### Cross-cutting patterns
- **SSE streaming** — report generation uses `sse-starlette` on the backend and `EventSource`/fetch-stream on the frontend to render markdown incrementally.
- **Caching** — `data_cache` table stores external API responses with TTLs from `config.py`: market data 5 min, financial 1 day, chain analysis 7 days. Routers check cache before calling external services.
- **Dark theme** — Ant Design dark algorithm applied globally in `App.tsx`; GitHub-inspired styling. Keep new UI consistent with this.
- **Four DB tables** — `chain_analyses`, `data_cache`, `reports`, `plans`. Schema is defined in `app/models/models.py`; adding a table requires importing the model in `main.py`'s `startup()` so `create_all` picks it up.

## Design Documents

Authoritative specs live in `docs/superpowers/`:
- `specs/2026-06-21-investment-desk-design.md` — full system design, API contracts, data schemas.
- `plans/2026-06-21-investment-desk-plan.md` — 17-task implementation plan.

Consult these when changing architecture or API shape.

## Skills Available

`.claude/skills/` contains three domain skills relevant to data work: `a-stock-data`, `akshare`, `tushare-api`. They document the same external data sources the backend services wrap — invoke them when extending market/financial data features.

## Agent skills

### Issue tracker
GitHub Issues (`RCliang/Investment-Desk`). External PRs are not a triage surface. See `docs/agents/issue-tracker.md`.

### Triage labels
Five canonical default names (needs-triage / needs-info / ready-for-agent / ready-for-human / wontfix). See `docs/agents/triage-labels.md`.

### Domain docs
Single-context — one `CONTEXT.md` + `docs/adr/` at the repo root. See `docs/agents/domain.md`.
