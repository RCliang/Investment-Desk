# Data Freshness, Refresh API, and Scheduler — Design Spec

**Date:** 2026-06-26
**Author:** InvestLens
**Status:** Approved (pending spec review)

## Goal

The chain knowledge base (`/api/chainkb/*`) currently has **zero automatic refresh** — every data source (quotes, financials, reports, etc.) is loaded by manually running `backend/scripts/backfill_*.py`. This makes time-sensitive data (especially stock prices) stale immediately.

This spec adds three capabilities:
1. **UI freshness indicator** in the top-right of the chainkb dashboard.
2. **Admin refresh API** (`/api/chainkb/refresh/{type}`) with token auth.
3. **Automatic scheduler** (APScheduler in-process) running each data type on its own cadence.

A CLI shortcut (`python -m app.services.refresh_cli <type>`) gives the owner a token-free way to trigger refreshes locally.

## Scope

### In scope
- Refactor 7 existing `scripts/backfill_*.py` into importable functions in `app/services/refresh_service.py`.
- New `chain_refresh_log` table tracking every refresh run.
- New `routers/refresh.py` with three endpoints: `POST /refresh/{type}`, `GET /refresh/status/{job_id}`, `GET /freshness`.
- New `services/scheduler.py` running APScheduler `BackgroundScheduler` on FastAPI startup.
- New `services/refresh_cli.py` for token-free local triggers.
- Frontend `DataFreshness` component + `useFreshness` hook + `ChainKbPage` integration.
- Token-based auth via `ADMIN_REFRESH_TOKEN` env var.

### Out of scope (deferred)
- User accounts / multi-tenant auth.
- Webhook-based refresh triggers from external systems.
- Incremental backfill (currently full-overwrite per type; still acceptable at this scale).
- Refresh history UI (admin can query DB directly if needed).
- Pause-on-market-holiday logic (scheduler just runs; if data source returns nothing, that's fine).
- Notification system for failed jobs (logged to `chain_refresh_log`; admin checks UI).

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│  FastAPI process (uvicorn)                                       │
│                                                                  │
│  ┌─────────────────────┐   ┌──────────────────────────────┐    │
│  │  APScheduler        │   │  routers/refresh.py           │    │
│  │  BackgroundScheduler│   │  POST /refresh/{type}         │    │
│  │  started on startup │   │   - quotes: sync              │    │
│  │  - 5min quotes      │   │   - 其他 7 项: async + job_id │    │
│  │  - daily margin     │   │  GET /refresh/status/{job_id} │    │
│  │  - weekly finance   │   │  GET /freshness (public)      │    │
│  │  - weekly reports   │   └──────────────────────────────┘    │
│  │  - weekly lockup    │                                       │
│  │  - monthly holders  │   ┌──────────────────────────────┐    │
│  │  - monthly concepts │   │  refresh_cli.py               │    │
│  └─────────┬───────────┘   │  (python -m, token-free)      │    │
│            │               └──────────┬───────────────────┘    │
│            └──────────────────────────┤                         │
│                                       ▼                         │
│                            ┌───────────────────────┐            │
│                            │  refresh_service.py   │            │
│                            │  refresh_quotes()     │            │
│                            │  refresh_finance()    │            │
│                            │  refresh_reports()    │            │
│                            │  refresh_concepts()   │            │
│                            │  refresh_lockup()     │            │
│                            │  refresh_holders()    │            │
│                            │  refresh_margin()     │            │
│                            │  refresh_all()        │            │
│                            └──────────┬────────────┘            │
│                                       ▼                         │
│                            ┌───────────────────────┐            │
│                            │  chain_refresh_log     │            │
│                            │  + 各业务表写入        │            │
│                            └──────────┬────────────┘            │
└───────────────────────────────────────┼─────────────────────────┘
                                        ▼
                   ┌────────────────────────────────────────┐
                   │  Frontend ChainKbPage                   │
                   │  右上角 <DataFreshness />               │
                   │  useFreshness() polls every 60s         │
                   └────────────────────────────────────────┘
```

Three trigger paths (CLI, HTTP, Scheduler) all converge on the same `refresh_service` functions, ensuring consistent logging, error handling, and concurrency control.

## Data model

### New table: `chain_refresh_log`

```python
class ChainRefreshLog(Base):
    __tablename__ = "chain_refresh_log"
    id            = Column(Integer, primary_key=True, autoincrement=True)
    refresh_type  = Column(String(16), index=True)  # quotes|finance|reports|concepts|lockup|holders|margin|all
    started_at    = Column(DateTime, default=datetime.utcnow, index=True)
    finished_at   = Column(DateTime, nullable=True)
    status        = Column(String(16), default="running", index=True)  # running|succeeded|failed
    rows_affected = Column(Integer, nullable=True)
    error         = Column(Text, nullable=True)
    triggered_by  = Column(String(16), default="manual")  # manual|scheduler|cli
```

**Lifecycle:**
1. Before refresh starts: insert row with `status='running'`, `started_at=now`.
2. On success: update `status='succeeded'`, `finished_at=now`, `rows_affected=N`.
3. On failure: update `status='failed'`, `finished_at=now`, `error=<stack trace>`.

**Concurrency control:** Before starting a refresh of type X, check if there's already a row with `refresh_type=X AND status='running'`. If yes, abort with `409 Conflict` (HTTP) or skip-with-log (scheduler/CLI).

### Freshness query

```sql
SELECT refresh_type, MAX(started_at) AS last_success_at
FROM chain_refresh_log
WHERE status='succeeded'
GROUP BY refresh_type;
```

API computes `minutes_ago = (now - last_success_at).total_seconds() / 60` for each type.

## API contracts

### `POST /api/chainkb/refresh/{type}`

**Auth:** `X-Admin-Token: <ADMIN_REFRESH_TOKEN>` header required.

**Path param `type`:** one of `quotes | finance | reports | concepts | lockup | holders | margin | all`.

**Behavior:**
- `quotes`: run synchronously, block until done (~2s), return final result.
- All others: enqueue in `ThreadPoolExecutor(max_workers=1)` (singleton), return `job_id` immediately.
- Concurrency check: if a job of the same type is already running, return `409 Conflict`.

**Sync response (200):**
```json
{
  "refresh_type": "quotes",
  "status": "succeeded",
  "started_at": "2026-06-26T15:30:00Z",
  "finished_at": "2026-06-26T15:30:02Z",
  "rows_affected": 234,
  "triggered_by": "manual"
}
```

**Async response (202):**
```json
{
  "job_id": 42,
  "refresh_type": "reports",
  "status": "running",
  "started_at": "2026-06-26T15:30:00Z",
  "status_url": "/api/chainkb/refresh/status/42"
}
```

**Error responses:**
- `400 Bad Request` — unknown type.
- `401 Unauthorized` — missing or wrong token.
- `409 Conflict` — same type already running.
- `503 Service Unavailable` — `ADMIN_REFRESH_TOKEN` not configured (empty string in env).

### `GET /api/chainkb/refresh/status/{job_id}`

**Auth:** `X-Admin-Token` header required.

**Response (200):**
```json
{
  "job_id": 42,
  "refresh_type": "reports",
  "status": "running",  // or succeeded|failed
  "started_at": "2026-06-26T15:30:00Z",
  "finished_at": null,
  "rows_affected": null,
  "error": null,
  "triggered_by": "manual"
}
```

**Errors:** `401`, `404` (unknown job_id).

### `GET /api/chainkb/freshness`

**Auth:** none (public, read-only).

**Response (200):**
```json
{
  "quotes":   { "last_success_at": "2026-06-26T15:30:00Z", "status": "succeeded", "minutes_ago": 3 },
  "finance":  { "last_success_at": "2026-06-23T03:00:00Z", "status": "succeeded", "minutes_ago": 4320 },
  "reports":  { "last_success_at": "2026-06-21T04:00:00Z", "status": "succeeded", "minutes_ago": 7200 },
  "concepts": { "last_success_at": "2026-06-01T04:00:00Z", "status": "succeeded", "minutes_ago": 36000 },
  "lockup":   { "last_success_at": "2026-06-21T05:00:00Z", "status": "succeeded", "minutes_ago": 7200 },
  "holders":  { "last_success_at": "2026-06-01T03:00:00Z", "status": "succeeded", "minutes_ago": 36000 },
  "margin":   { "last_success_at": "2026-06-26T15:30:00Z", "status": "succeeded", "minutes_ago": 3 },
  "running":   ["reports"],
  "failed_recent": { "finance": "2026-06-22T03:00:00Z" }
}
```

- `running`: list of currently-running refresh types (drives "更新中…" UI).
- `failed_recent`: most recent failure per type within last 7 days (drives red "失败" UI).

## Refresh type → function mapping

| type | sync? | function in refresh_service.py | data source | est. runtime |
|------|-------|--------------------------------|-------------|--------------|
| `quotes` | ✅ sync | `refresh_quotes(session, trigger)` | Tencent batch `qt.gtimg.cn` | ~2s |
| `finance` | async | `refresh_finance(session, trigger)` | mootdx TCP port 7709 | ~3min |
| `reports` | async | `refresh_reports(session, trigger)` | 东财 `reportapi.eastmoney.com` | ~5min |
| `concepts` | async | `refresh_concepts(session, trigger)` | 东财 `push2.eastmoney.com` | ~5min |
| `lockup` | async | `refresh_lockup(session, trigger)` | 东财 `datacenter-web` | ~4min |
| `holders` | async | `refresh_holders(session, trigger)` | 东财 `RPT_F10_EH_HOLDERNUM` | ~5min |
| `margin` | async | `refresh_margin(session, trigger)` | 东财 `RPTA_WEB_RZRQ_GGMX` | ~5min |
| `all` | async | `refresh_all(session, trigger)` | 串行 顺序：quotes → finance → margin → lockup → holders → reports → concepts | ~30min |

Each function:
1. Inserts a `chain_refresh_log` row (`status='running'`, `triggered_by=<trigger>`).
2. Calls the original backfill logic (fetched from `scripts/backfill_*.py`, refactored to be importable).
3. Loads the resulting JSON into the appropriate chain tables via existing `load_seed_to_db.py` logic (also refactored into a function).
4. Updates the log row on success/failure.

## Scheduler config

**Location:** `backend/app/services/scheduler.py`

**Lifecycle:** started in `app/main.py` startup, gracefully shut down on FastAPI shutdown.

**Jobs (timezone `Asia/Shanghai`):**

| Job | CronTrigger | Description |
|-----|-------------|-------------|
| `quotes` | `day_of_week='mon-fri', hour='9-14', minute='*/5'` + `day_of_week='mon-fri', hour='15', minute='0-30'` | Trading hours, every 5 min |
| `margin` | `day_of_week='mon-fri', hour='15', minute='30'` | Once after close |
| `finance` | `day_of_week='sun', hour='3'` | Weekly Sunday |
| `reports` | `day_of_week='sun', hour='4'` | Weekly Sunday |
| `lockup` | `day_of_week='sun', hour='5'` | Weekly Sunday |
| `holders` | `day='1', hour='3'` | Monthly 1st |
| `concepts` | `day='1', hour='4'` | Monthly 1st |

**Notes:**
- The two `quotes` triggers are added as separate jobs (APScheduler doesn't support OR-ing cron expressions natively).
- Each job calls the corresponding `refresh_*(session, trigger='scheduler')` function.
- Scheduler jobs bypass the HTTP concurrency check but still respect the DB-level check (a manual refresh running will block a scheduler invocation — desired behavior).

**Failure isolation:** each job wrapped in try/except; failures logged to `chain_refresh_log` and the scheduler keeps running. APScheduler's `misfire_grace_time=600` and `coalesce=True` configured.

## Auth

**Config:** `backend/app/config.py` adds:
```python
admin_refresh_token: str = ""
```

**Env:** `.env` adds `ADMIN_REFRESH_TOKEN=<32-char hex string>`. `.env.example` gets placeholder.

**Validation:** if `admin_refresh_token == ""`, the refresh POST endpoint returns `503` with body `{"detail": "ADMIN_REFRESH_TOKEN not configured"}`. This prevents accidental open access in misconfigured deployments.

**Middleware / dependency:** a FastAPI `Depends(verify_admin_token)` that compares `request.headers.get('X-Admin-Token')` with `settings.admin_refresh_token` using `secrets.compare_digest`. Applied only to POST `/refresh/{type}` and GET `/refresh/status/{job_id}`.

## CLI

**File:** `backend/app/services/refresh_cli.py`

**Usage:**
```bash
cd backend
python -m app.services.refresh_cli quotes              # sync, prints result
python -m app.services.refresh_cli reports             # async, prints job_id, exits
python -m app.services.refresh_cli all                 # async, prints job_id
python -m app.services.refresh_cli --status 42         # query job status
python -m app.services.refresh_cli --list              # list recent jobs
```

**Behavior:**
- Imports `refresh_service` functions directly; does NOT go through HTTP.
- No token required (running locally on the server).
- Creates DB session inline (reuses `app/db.py` `SessionLocal`).
- Writes to `chain_refresh_log` with `triggered_by='cli'`.
- For async types, spawns the same `ThreadPoolExecutor` job and exits immediately, printing `job_id`.

## Frontend

### `frontend/src/chainkb/components/DataFreshness.tsx`

**Layout** (top-right of `ChainKbPage` header):
```
┌─────────────────────────────────────────────────────────┐
│  现价 3分钟前 · 财务 2天前 · 研报 5天前 · 融资融券 1天前 │
│  解禁 4天前 · 股东 12天前 · 概念 25天前                  │
└─────────────────────────────────────────────────────────┘
```

**Styling:**
- Font: `'JetBrains Mono', monospace`, 11px.
- Color: `var(--pencil)` (default), `#e85a4f` (failed), `var(--ink)` (running, with dotted underline).
- Right-aligned, wraps to second line on narrow screens.

**Time format (`minutes_ago` → display):**
- `null` → `"从未"`
- `<1` → `"刚刚"`
- `<60` → `"X分钟前"`
- `<1440` → `"X小时前"`
- `>=1440` → `"X天前"`

**Status indicators:**
- `running` → "更新中…" with subtle pulse animation.
- `failed_recent` contains type → red "失败" text, `title` attribute has error.
- Otherwise normal "X时间前".

### `useFreshness` hook (`frontend/src/chainkb/hooks/useChainKb.ts`)

```typescript
export function useFreshness() {
  const [data, setData] = useState<FreshnessResponse | null>(null);
  useEffect(() => {
    let cancelled = false;
    const tick = async () => {
      try {
        const f = await getFreshness();
        if (!cancelled) setData(f);
      } catch { /* silent */ }
    };
    tick();
    const id = setInterval(tick, 60_000);
    return () => { cancelled = true; clearInterval(id); };
  }, []);
  return data;
}
```

Polls `/api/chainkb/freshness` on mount + every 60s. No abort on unmount beyond clearing the interval.

### API + types additions

**`frontend/src/services/api.ts`:**
```typescript
export async function getFreshness(): Promise<FreshnessResponse> {
  const { data } = await api.get<FreshnessResponse>('/api/chainkb/freshness');
  return data;
}
```

**`frontend/src/types/chainkb.ts`:**
```typescript
export interface FreshnessEntry {
  last_success_at: string | null;
  status: 'succeeded' | 'never';
  minutes_ago: number | null;
}
export interface FreshnessResponse {
  quotes: FreshnessEntry;
  finance: FreshnessEntry;
  reports: FreshnessEntry;
  concepts: FreshnessEntry;
  lockup: FreshnessEntry;
  holders: FreshnessEntry;
  margin: FreshnessEntry;
  running: string[];
  failed_recent: Record<string, string>;
}
```

### Integration in `ChainKbPage.tsx`

Header becomes a flex row:
```tsx
<header className="chainkb-header">
  <div className="chainkb-title">
    <h1>InvestLens · 产业链图谱</h1>
    <span className="chainkb-sub">...</span>
  </div>
  <DataFreshness />  {/* new */}
</header>
```

CSS in `chainkb.css` adds:
```css
.chainkb-root .chainkb-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
}
```

## File changes

### Backend — new
- `backend/app/services/refresh_service.py` — 8 refresh functions + helpers
- `backend/app/services/scheduler.py` — APScheduler setup
- `backend/app/services/refresh_cli.py` — CLI entrypoint

### Backend — modify
- `backend/app/models/chain_models.py` — add `ChainRefreshLog`
- `backend/app/main.py` — register refresh router, start/stop scheduler on startup/shutdown
- `backend/app/config.py` — add `admin_refresh_token` field
- `backend/.env.example` — add `ADMIN_REFRESH_TOKEN=`
- `backend/scripts/backfill_*.py` — refactor internals into importable helpers (keep `if __name__ == '__main__'` shim for backward compat)
- `backend/scripts/load_seed_to_db.py` — expose `load_all_to_db(session)` function

### Frontend — new
- `frontend/src/chainkb/components/DataFreshness.tsx`

### Frontend — modify
- `frontend/src/chainkb/hooks/useChainKb.ts` — add `useFreshness`
- `frontend/src/chainkb/ChainKbPage.tsx` — render `<DataFreshness />` in header
- `frontend/src/services/api.ts` — add `getFreshness()`
- `frontend/src/types/chainkb.ts` — add `FreshnessEntry`, `FreshnessResponse`
- `frontend/src/chainkb/chainkb.css` — header flex layout + freshness styles

## Verification

1. **Migration auto-applies:** `chain_refresh_log` table created on startup (`Base.metadata.create_all`).
2. **CLI smoke test:**
   ```bash
   python -m app.services.refresh_cli quotes
   # expect: "quotes succeeded, 234 rows, 1.8s"
   ```
3. **HTTP smoke test:**
   ```bash
   curl -X POST -H "X-Admin-Token: $TOKEN" http://localhost:8000/api/chainkb/refresh/quotes
   # expect: 200 + sync response body
   curl -X POST -H "X-Admin-Token: $TOKEN" http://localhost:8000/api/chainkb/refresh/reports
   # expect: 202 + async response with job_id
   curl http://localhost:8000/api/chainkb/refresh/status/<job_id> -H "X-Admin-Token: $TOKEN"
   ```
4. **Public freshness endpoint:**
   ```bash
   curl http://localhost:8000/api/chainkb/freshness
   # expect: JSON with all 7 types populated
   ```
5. **Token enforcement:**
   ```bash
   curl -X POST http://localhost:8000/api/chainkb/refresh/quotes
   # expect: 401
   curl -X POST -H "X-Admin-Token: wrong" http://localhost:8000/api/chainkb/refresh/quotes
   # expect: 401
   ```
6. **Concurrency check:**
   - Start a slow refresh (reports).
   - While running, POST another `/refresh/reports`.
   - Expect: `409 Conflict`.
7. **Scheduler:** check `chain_refresh_log` after the first scheduled `quotes` run fires (within 5 min of startup if during trading hours).
8. **Frontend:** open dashboard, verify freshness strip appears top-right with sensible values; kill backend and verify graceful "—" fallback.

## Non-goals

- Real-time push (WebSocket) of freshness changes — 60s polling is enough.
- Per-user token rotation.
- Refresh job prioritization / queue management beyond the single global mutex per type.
- Pause/resume individual schedules via API (edit code + restart is fine).
- Distributed scheduler (single-process is sufficient for this personal tool).
- Retry policy (failed jobs wait for next scheduled run or manual retrigger).
- Frontend "刷新" button (CLI + scheduler cover the need; can add later if wanted).

## Risks / edge cases

- **APScheduler in-process:** dies when uvicorn restarts. Acceptable for personal tool; document that restarts reset the schedule.
- **East Money rate limits:** existing backfill scripts already have 1.0s + jitter throttling. Carried over into `refresh_service` unchanged.
- **Race between manual + scheduled refresh:** DB-level running-check prevents overlap.
- **`Base.metadata.create_all` on existing DB:** adds new table cleanly; existing tables untouched.
- **Frontend polling during backend down:** silent failure, UI shows last known values; once backend returns, resumes.
- **Token leakage in logs:** FastAPI access log records headers by default in some setups; verify uvicorn config does NOT log `X-Admin-Token`. Add `--log-headers=False` or filter if needed.
