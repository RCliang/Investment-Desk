# Data Freshness, Refresh API, and Scheduler — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a data freshness UI (top-right of dashboard), an admin refresh API with token auth, and an in-process scheduler that auto-refreshes each data type on its own cadence.

**Architecture:** Three trigger paths (CLI, HTTP, scheduler) all converge on `refresh_service.py`, which orchestrates the existing backfill scripts via `subprocess` and ingests via `load_seed_to_db.py`'s per-type loaders. Every run writes a row to `chain_refresh_log`. The freshness endpoint aggregates that table; the frontend polls it every 60s.

**Tech Stack:** Python 3 / FastAPI / SQLAlchemy (existing) + APScheduler 3.10 (new) / React 18 + TypeScript (existing).

## Global Constraints

- Working directory: `E:/2026projects/Investment-Desk` (Windows, Git Bash).
- Backend lives in `backend/`. Start with `cd backend && uvicorn app.main:app --port 8000`. SQLite DB auto-creates at `backend/data/investlens.db` via `Base.metadata.create_all` on startup.
- Frontend lives in `frontend/`. Build: `cd frontend && npm run build`. Lint: `cd frontend && npm run lint`. Both must exit 0.
- Branch: `main` (continuing the existing eye-熟悉 pattern from prior tasks).
- Backend config is module-level constants in `backend/app/config.py` loaded via `python-dotenv` from `backend/.env`. Follow this pattern (do NOT introduce pydantic-settings).
- Backend has both `async_engine` (for table creation only) and `sync_engine` + `SessionLocal` (for endpoint DB work). All refresh logic uses `SessionLocal` synchronously.
- Commit messages in Chinese, conventional-commit format (e.g. `feat(refresh): …`, `fix(scheduler): …`).
- Frontend dependencies stay at `{axios, react, react-dom, react-markdown}` — no new packages needed.
- Backend can add `apscheduler>=3.10` to `requirements.txt`. That is the only new dependency.
- No test suite exists; verification is via inline scripts + curl + build/lint. Do NOT add pytest infrastructure in this plan.
- All HTTP routes are prefixed `/api/chainkb/refresh/*` or `/api/chainkb/freshness`.
- `.env` and `.env.example` are gitignored / gittracked respectively; only `.env.example` is committed.

---

### Task 1: Backend foundation — config + ChainRefreshLog model + .env wiring

**Files:**
- Modify: `backend/app/config.py`
- Modify: `backend/app/models/chain_models.py`
- Modify: `backend/.env.example`

**Interfaces:**
- Produces: `app.config.ADMIN_REFRESH_TOKEN` (str, default `""`) — read by Task 3's auth dependency.
- Produces: `app.models.chain_models.ChainRefreshLog` ORM class — read by Tasks 2 and 3. Auto-created on next startup via existing `Base.metadata.create_all` in `app/main.py` startup (no migration step needed because chain_models is already imported there at line 27).

- [ ] **Step 1: Add `ADMIN_REFRESH_TOKEN` to config**

Append to `backend/app/config.py` (after `CACHE_TTL_CHAIN`):

```python

# Refresh API token — required for POST /api/chainkb/refresh/* endpoints.
# Generate with: python -c "import secrets; print(secrets.token_hex(16))"
# If left empty, refresh endpoints return 503 (refuse to run unauthenticated).
ADMIN_REFRESH_TOKEN = os.getenv("ADMIN_REFRESH_TOKEN", "")
```

- [ ] **Step 2: Add `ChainRefreshLog` model**

Append to `backend/app/models/chain_models.py` **before** the `__all__` block:

```python
class ChainRefreshLog(Base):
    """Audit trail for every data refresh run (manual, scheduled, or CLI).

    One row per refresh attempt. Lifecycle: insert with status='running'
    on start, update to 'succeeded' or 'failed' on completion.

    The freshness endpoint reads the most recent 'succeeded' row per
    refresh_type to compute last_success_at / minutes_ago.
    """
    __tablename__ = "chain_refresh_log"
    __table_args__ = (
        Index("ix_refresh_type_status", "refresh_type", "status"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    refresh_type = Column(String(16), nullable=False, index=True)
    # quotes | finance | reports | concepts | lockup | holders | margin | all
    started_at = Column(DateTime, nullable=False,
                        server_default=func.now(), index=True)
    finished_at = Column(DateTime, nullable=True)
    status = Column(String(16), nullable=False,
                    default="running")  # running | succeeded | failed
    rows_affected = Column(Integer, nullable=True)
    error = Column(Text, nullable=True)
    triggered_by = Column(String(16), nullable=False,
                          default="manual")  # manual | scheduler | cli
```

Update `__all__` to include `"ChainRefreshLog"`.

- [ ] **Step 3: Update `.env.example`**

Read the existing `backend/.env.example` and append (do not overwrite existing keys):

```
# Admin token for /api/chainkb/refresh/* endpoints.
# Generate with: python -c "import secrets; print(secrets.token_hex(16))"
# Leave empty to disable refresh endpoints (returns 503).
ADMIN_REFRESH_TOKEN=
```

- [ ] **Step 4: Verify table auto-creates**

Run:
```bash
cd backend && python -c "from app.models.chain_models import ChainRefreshLog; print(ChainRefreshLog.__tablename__)"
```
Expected output: `chain_refresh_log`

- [ ] **Step 5: Verify startup still works**

Run:
```bash
cd backend && python -c "from app.main import app; print('ok')"
```
Expected output: `ok` (no import errors).

- [ ] **Step 6: Commit**

```bash
cd "E:/2026projects/Investment-Desk"
git add backend/app/config.py backend/app/models/chain_models.py backend/.env.example
git commit -m "feat(backend): 添加 ADMIN_REFRESH_TOKEN 与 ChainRefreshLog 模型"
```

---

### Task 2: Refresh service — orchestrator with subprocess + per-type loaders

**Files:**
- Create: `backend/app/services/__init__.py` (empty file, may already exist)
- Create: `backend/app/services/refresh_service.py`

**Interfaces:**
- Consumes: `app.db.SessionLocal`, `app.models.chain_models.ChainRefreshLog`, `scripts.load_seed_to_db.load_quotes` / `load_finance` / `load_concept_blocks` / `load_lockup` / `load_holder_num` / `load_margin` / `load_reports`, and the existing `backend/scripts/backfill_*.py` scripts (invoked via `subprocess.run`).
- Produces: `refresh_service.refresh_quotes(session, trigger)` ... `refresh_margin(session, trigger)` and `refresh_all(session, trigger)` — each inserts a `chain_refresh_log` row, runs backfill + load, updates the row. Also produces `refresh_service.is_running(session, refresh_type)` and `refresh_service.get_job(session, job_id)` and `refresh_service.list_running(session)` and `refresh_service.freshness(session)` — used by Task 3.

**Type → script mapping** (concrete paths):
| type | script | loader | runtime |
|------|--------|--------|---------|
| `quotes` | `scripts/backfill_tencent_quotes.py` | `load_quotes(session)` → int | ~2s |
| `finance` | `scripts/backfill_mootdx_finance.py` | `load_finance(session)` → int | ~3min |
| `reports` | `scripts/backfill_em_reports.py` | `load_reports(session)` → int | ~5min |
| `concepts` | `scripts/backfill_em_concept_blocks.py` | `load_concept_blocks(session)` → tuple | ~5min |
| `lockup` | `scripts/backfill_em_lockup_expiry.py` | `load_lockup(session)` → int | ~4min |
| `holders` | `scripts/backfill_em_holder_num.py` | `load_holder_num(session)` → int | ~5min |
| `margin` | `scripts/backfill_em_margin_trading.py` | `load_margin(session)` → int | ~5min |

- [ ] **Step 1: Create services package**

Run:
```bash
mkdir -p backend/app/services && touch backend/app/services/__init__.py
```

Verify `backend/app/services/__init__.py` exists and is empty.

- [ ] **Step 2: Write `refresh_service.py`**

Create `backend/app/services/refresh_service.py` with this exact content:

```python
"""Refresh orchestration: run a backfill script then ingest via load_seed_to_db.

Three callers reach this module:
  - HTTP endpoint (app.routers.refresh)  — trigger='manual', requires token
  - APScheduler jobs (app.services.scheduler) — trigger='scheduler'
  - CLI (app.services.refresh_cli)       — trigger='cli'

All three paths converge here so logging, error handling, and concurrency
checks are uniform. Each public refresh_* function:

  1. Checks for an existing 'running' row of the same type (skip if found).
  2. Inserts a new chain_refresh_log row with status='running'.
  3. Runs the backfill script via subprocess (cwd = backend/).
  4. Calls the matching load_* function from scripts/load_seed_to_db.py.
  5. Updates the log row to 'succeeded' (with rows_affected) or 'failed'.

Subprocess is used (rather than refactoring the scripts) to keep the
existing scripts runnable as standalone tools and to isolate failures.
"""

from __future__ import annotations

import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Literal

from sqlalchemy.orm import Session

from app.models.chain_models import ChainRefreshLog

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent  # backend/
SCRIPTS_DIR = BACKEND_DIR / "scripts"

RefreshType = Literal[
    "quotes", "finance", "reports", "concepts",
    "lockup", "holders", "margin", "all",
]
Trigger = Literal["manual", "scheduler", "cli"]

# type → (script path, loader function name in load_seed_to_db)
_TYPE_MAP: dict[str, tuple[str, str]] = {
    "quotes":   ("backfill_tencent_quotes.py",     "load_quotes"),
    "finance":  ("backfill_mootdx_finance.py",     "load_finance"),
    "reports":  ("backfill_em_reports.py",         "load_reports"),
    "concepts": ("backfill_em_concept_blocks.py",  "load_concept_blocks"),
    "lockup":   ("backfill_em_lockup_expiry.py",   "load_lockup"),
    "holders":  ("backfill_em_holder_num.py",      "load_holder_num"),
    "margin":   ("backfill_em_margin_trading.py",  "load_margin"),
}

# Per-type subprocess timeout (seconds). Generous upper bound; scripts
# have their own internal rate-limit sleeps that drive actual runtime.
_TIMEOUTS: dict[str, int] = {
    "quotes": 60, "finance": 600, "reports": 900, "concepts": 900,
    "lockup": 900, "holders": 900, "margin": 900,
}


def is_running(session: Session, refresh_type: str) -> bool:
    """Return True if a row with status='running' exists for this type."""
    return session.query(ChainRefreshLog).filter_by(
        refresh_type=refresh_type, status="running"
    ).first() is not None


def list_running(session: Session) -> list[str]:
    """Return all currently-running refresh types."""
    rows = session.query(ChainRefreshLog).filter_by(status="running").all()
    return sorted({r.refresh_type for r in rows})


def get_job(session: Session, job_id: int) -> ChainRefreshLog | None:
    return session.get(ChainRefreshLog, job_id)


def freshness(session: Session) -> dict:
    """Return per-type freshness + currently-running + recent-failures dict.

    Shape (see spec §Freshness response):
      {
        "quotes":   {"last_success_at": "ISO" | None, "status": "succeeded"|"never", "minutes_ago": int|None},
        ...,
        "running":   ["reports", ...],
        "failed_recent": {"finance": "ISO", ...}   # most recent failure per type within 7d
      }
    """
    out: dict = {}
    now = datetime.utcnow()
    seven_days_ago = now - timedelta(days=7)

    for t in _TYPE_MAP:
        latest_success = session.query(ChainRefreshLog).filter_by(
            refresh_type=t, status="succeeded"
        ).order_by(ChainRefreshLog.started_at.desc()).first()
        if latest_success is None:
            out[t] = {"last_success_at": None, "status": "never", "minutes_ago": None}
        else:
            mins = int((now - latest_success.started_at).total_seconds() / 60)
            out[t] = {
                "last_success_at": latest_success.started_at.isoformat() + "Z",
                "status": "succeeded",
                "minutes_ago": mins,
            }

    # Currently running
    out["running"] = list_running(session)

    # Most recent failure per type within last 7 days
    failed_recent: dict[str, str] = {}
    for t in _TYPE_MAP:
        recent_fail = session.query(ChainRefreshLog).filter(
            ChainRefreshLog.refresh_type == t,
            ChainRefreshLog.status == "failed",
            ChainRefreshLog.finished_at >= seven_days_ago,
        ).order_by(ChainRefreshLog.finished_at.desc()).first()
        if recent_fail and recent_fail.finished_at:
            failed_recent[t] = recent_fail.finished_at.isoformat() + "Z"
    out["failed_recent"] = failed_recent

    return out


def _run_one(session: Session, refresh_type: str, trigger: Trigger) -> ChainRefreshLog:
    """Internal: run a single (non-'all') refresh. Inserts log row, raises on failure."""
    if refresh_type not in _TYPE_MAP:
        raise ValueError(f"unknown refresh type: {refresh_type}")

    if is_running(session, refresh_type):
        # Concurrency conflict — caller (HTTP) turns this into 409.
        raise RefreshConflictError(refresh_type)

    script_name, loader_name = _TYPE_MAP[refresh_type]
    script_path = SCRIPTS_DIR / script_name

    log = ChainRefreshLog(
        refresh_type=refresh_type,
        status="running",
        triggered_by=trigger,
    )
    session.add(log)
    session.commit()
    session.refresh(log)

    try:
        # Step 1: run backfill script (writes JSON to backend/data/)
        result = subprocess.run(
            [sys.executable, str(script_path)],
            cwd=str(BACKEND_DIR),
            capture_output=True,
            text=True,
            timeout=_TIMEOUTS[refresh_type],
        )
        if result.returncode != 0:
            tail = (result.stderr or result.stdout or "")[-500:]
            raise RuntimeError(f"backfill {script_name} exited {result.returncode}: {tail}")

        # Step 2: ingest JSON into DB via the matching loader
        # Import lazily so a broken script doesn't break module import.
        from scripts import load_seed_to_db as loader_mod
        loader_fn = getattr(loader_mod, loader_name)
        rows = loader_fn(session)
        # load_concept_blocks returns a tuple (n_companies, n_concepts, n_links)
        if isinstance(rows, tuple):
            rows = sum(rows)

        log.finished_at = datetime.utcnow()
        log.status = "succeeded"
        log.rows_affected = int(rows or 0)
        session.commit()
        session.refresh(log)
        return log

    except Exception as e:
        log.finished_at = datetime.utcnow()
        log.status = "failed"
        log.error = f"{type(e).__name__}: {str(e)[:1000]}"
        session.commit()
        session.refresh(log)
        raise


def refresh_quotes(session: Session, trigger: Trigger = "manual") -> ChainRefreshLog:
    return _run_one(session, "quotes", trigger)

def refresh_finance(session: Session, trigger: Trigger = "manual") -> ChainRefreshLog:
    return _run_one(session, "finance", trigger)

def refresh_reports(session: Session, trigger: Trigger = "manual") -> ChainRefreshLog:
    return _run_one(session, "reports", trigger)

def refresh_concepts(session: Session, trigger: Trigger = "manual") -> ChainRefreshLog:
    return _run_one(session, "concepts", trigger)

def refresh_lockup(session: Session, trigger: Trigger = "manual") -> ChainRefreshLog:
    return _run_one(session, "lockup", trigger)

def refresh_holders(session: Session, trigger: Trigger = "manual") -> ChainRefreshLog:
    return _run_one(session, "holders", trigger)

def refresh_margin(session: Session, trigger: Trigger = "manual") -> ChainRefreshLog:
    return _run_one(session, "margin", trigger)

def refresh_all(session: Session, trigger: Trigger = "manual") -> list[ChainRefreshLog]:
    """Sequentially run all 7 refreshes in order: fast → slow.

    Order: quotes → margin → lockup → holders → reports → concepts → finance.
    Returns the list of per-type log rows. Continues on per-type failure
    (each failure is logged; does not abort the sequence).
    """
    order = ["quotes", "margin", "lockup", "holders", "reports", "concepts", "finance"]
    results: list[ChainRefreshLog] = []
    for t in order:
        try:
            results.append(_run_one(session, t, trigger))
        except RefreshConflictError:
            continue  # skip if already running
        except Exception:
            # Error already logged to db; keep going.
            continue
    return results


_REFRESH_FUNCTIONS = {
    "quotes": refresh_quotes,
    "finance": refresh_finance,
    "reports": refresh_reports,
    "concepts": refresh_concepts,
    "lockup": refresh_lockup,
    "holders": refresh_holders,
    "margin": refresh_margin,
    "all": refresh_all,
}


def dispatch(refresh_type: str, session: Session, trigger: Trigger = "manual"):
    """Look up the refresh function by name. Used by router + CLI + scheduler."""
    if refresh_type not in _REFRESH_FUNCTIONS:
        raise ValueError(f"unknown refresh type: {refresh_type}")
    return _REFRESH_FUNCTIONS[refresh_type](session, trigger=trigger)


class RefreshConflictError(Exception):
    """Raised when a refresh of the same type is already running."""
    def __init__(self, refresh_type: str):
        self.refresh_type = refresh_type
        super().__init__(f"refresh '{refresh_type}' already running")
```

- [ ] **Step 3: Verify module imports cleanly**

Run:
```bash
cd backend && python -c "from app.services.refresh_service import dispatch, freshness, is_running; print('ok')"
```
Expected: `ok` (no syntax/import errors). If `app.services.__init__.py` doesn't exist, create it as empty file.

- [ ] **Step 4: Verify `is_running` returns False on empty DB**

Run:
```bash
cd backend && python -c "from app.db import SessionLocal; from app.services.refresh_service import is_running; s=SessionLocal(); print(is_running(s, 'quotes')); s.close()"
```
Expected: `False`.

- [ ] **Step 5: Verify freshness returns 7 types on empty DB**

Run:
```bash
cd backend && python -c "from app.db import SessionLocal; from app.services.refresh_service import freshness; import json; s=SessionLocal(); print(json.dumps(freshness(s), indent=2)); s.close()"
```
Expected: JSON dict with all 7 types showing `status: never`, plus empty `running` list and empty `failed_recent` dict.

- [ ] **Step 6: Commit**

```bash
cd "E:/2026projects/Investment-Desk"
git add backend/app/services/__init__.py backend/app/services/refresh_service.py
git commit -m "feat(backend): 添加 refresh_service 编排层 (subprocess + per-type loaders)"
```

---

### Task 3: Refresh router — HTTP endpoints with token auth

**Files:**
- Create: `backend/app/routers/refresh.py`
- Modify: `backend/app/main.py`

**Interfaces:**
- Consumes: `refresh_service.dispatch`, `refresh_service.get_job`, `refresh_service.freshness`, `refresh_service.is_running`, `app.config.ADMIN_REFRESH_TOKEN`, `app.db.get_db` (existing dependency).
- Produces: 3 HTTP endpoints under `/api/chainkb/`:
  - `POST /refresh/{type}` — admin-only, sync for `quotes`, async for others.
  - `GET /refresh/status/{job_id}` — admin-only.
  - `GET /freshness` — public.

- [ ] **Step 1: Create refresh router**

Create `backend/app/routers/refresh.py` with this exact content:

```python
"""HTTP endpoints for triggering and monitoring data refreshes.

Auth: POST /refresh/{type} and GET /refresh/status/{job_id} require
X-Admin-Token header matching ADMIN_REFRESH_TOKEN env var.
GET /freshness is public (frontend polls it every 60s).

Execution model:
  - quotes: synchronous (returns 200 with final result, ~2s)
  - all other types + 'all': async via ThreadPoolExecutor(max_workers=1),
    returns 202 with job_id immediately.
"""

from __future__ import annotations

import secrets
from concurrent.futures import ThreadPoolExecutor

from fastapi import APIRouter, Depends, Header, HTTPException, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import ADMIN_REFRESH_TOKEN
from app.db import get_db
from app.services import refresh_service

router = APIRouter(prefix="/api/chainkb", tags=["refresh"])

# Single-worker pool so slow refreshes queue rather than race.
_executor = ThreadPoolExecutor(max_workers=1)

SYNC_TYPES = {"quotes"}


class SyncRefreshResponse(BaseModel):
    refresh_type: str
    status: str
    started_at: str
    finished_at: str
    rows_affected: int
    triggered_by: str


class AsyncRefreshResponse(BaseModel):
    job_id: int
    refresh_type: str
    status: str
    started_at: str
    status_url: str


class JobStatusResponse(BaseModel):
    job_id: int
    refresh_type: str
    status: str
    started_at: str
    finished_at: str | None
    rows_affected: int | None
    error: str | None
    triggered_by: str


def verify_admin_token(x_admin_token: str = Header(default="")) -> None:
    """FastAPI dependency: enforce X-Admin-Token header.

    Returns 401 on missing/wrong token, 503 if ADMIN_REFRESH_TOKEN is
    unset (empty string) in config.
    """
    if not ADMIN_REFRESH_TOKEN:
        raise HTTPException(
            status_code=503,
            detail="ADMIN_REFRESH_TOKEN not configured; refresh endpoints disabled.",
        )
    if not x_admin_token or not secrets.compare_digest(x_admin_token, ADMIN_REFRESH_TOKEN):
        raise HTTPException(status_code=401, detail="invalid or missing X-Admin-Token")


def _serialize_job(job) -> dict:
    return {
        "job_id": job.id,
        "refresh_type": job.refresh_type,
        "status": job.status,
        "started_at": job.started_at.isoformat() + "Z",
        "finished_at": job.finished_at.isoformat() + "Z" if job.finished_at else None,
        "rows_affected": job.rows_affected,
        "error": job.error,
        "triggered_by": job.triggered_by,
    }


@router.post(
    "/refresh/{refresh_type}",
    dependencies=[Depends(verify_admin_token)],
)
def trigger_refresh(refresh_type: str, db: Session = Depends(get_db)):
    """Trigger a refresh by type.

    - `quotes`: runs synchronously, returns 200 with final result.
    - other types + `all`: enqueues async, returns 202 with job_id.
    """
    valid_types = {"quotes", "finance", "reports", "concepts",
                   "lockup", "holders", "margin", "all"}
    if refresh_type not in valid_types:
        raise HTTPException(status_code=400,
                            detail=f"unknown type: {refresh_type}. "
                                   f"valid: {sorted(valid_types)}")

    # Concurrency check
    if refresh_service.is_running(db, refresh_type):
        raise HTTPException(status_code=409,
                            detail=f"refresh '{refresh_type}' already running")

    # For 'all', also check no sub-type is running
    if refresh_type == "all":
        for sub in ["quotes", "finance", "reports", "concepts",
                    "lockup", "holders", "margin"]:
            if refresh_service.is_running(db, sub):
                raise HTTPException(
                    status_code=409,
                    detail=f"cannot start 'all': sub-type '{sub}' is running",
                )

    if refresh_type in SYNC_TYPES:
        # Synchronous: block until done
        try:
            job = refresh_service.dispatch(refresh_type, db, trigger="manual")
        except refresh_service.RefreshConflictError as e:
            raise HTTPException(status_code=409, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=500,
                                detail=f"refresh failed: {type(e).__name__}: {e}")
        return JSONResponse(status_code=200, content=_serialize_job(job))

    # Async: close the request DB session, run in background thread with its own.
    from app.db import SessionLocal
    try:
        # Pre-insert the log row synchronously so we can return job_id fast.
        # Trick: call dispatch but in a non-blocking way — we use a helper that
        # just creates the row. The thread then does the actual work via the
        # same dispatch function but with a fresh session.
        # Simpler: spawn dispatch directly; it inserts its own row quickly.
        future = _executor.submit(_run_async, refresh_type)
        # Poll briefly (up to 1s) to get the job_id from the log row.
        import time
        deadline = time.time() + 1.0
        while time.time() < deadline:
            running = db.query(refresh_service.ChainRefreshLog).filter_by(
                refresh_type=refresh_type, status="running"
            ).order_by(refresh_service.ChainRefreshLog.started_at.desc()).first()
            if running:
                return JSONResponse(
                    status_code=202,
                    content={
                        "job_id": running.id,
                        "refresh_type": refresh_type,
                        "status": "running",
                        "started_at": running.started_at.isoformat() + "Z",
                        "status_url": f"/api/chainkb/refresh/status/{running.id}",
                    },
                )
            time.sleep(0.05)
        # Took >1s to even insert the row — rare. Return generic 202.
        return JSONResponse(
            status_code=202,
            content={
                "job_id": None,
                "refresh_type": refresh_type,
                "status": "queued",
                "started_at": None,
                "status_url": None,
            },
        )
    except refresh_service.RefreshConflictError as e:
        raise HTTPException(status_code=409, detail=str(e))


def _run_async(refresh_type: str) -> None:
    """Background worker: own session, run dispatch, swallow exceptions (logged in db)."""
    session = SessionLocal()
    try:
        refresh_service.dispatch(refresh_type, session, trigger="manual")
    except Exception:
        pass  # error already written to chain_refresh_log by refresh_service
    finally:
        session.close()


@router.get(
    "/refresh/status/{job_id}",
    dependencies=[Depends(verify_admin_token)],
    response_model=JobStatusResponse,
)
def get_status(job_id: int, db: Session = Depends(get_db)):
    job = refresh_service.get_job(db, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"job {job_id} not found")
    return JobStatusResponse(**_serialize_job(job))


@router.get("/freshness")
def get_freshness(db: Session = Depends(get_db)):
    """Public endpoint: per-type last-success times + currently-running list."""
    return refresh_service.freshness(db)
```

- [ ] **Step 2: Wire into main.py**

Edit `backend/app/main.py`. After the existing `from app.routers import chain, data, report, plan, chainkb` line, add `refresh` to the import. Then after the existing `app.include_router(chainkb.router)` line, add `app.include_router(refresh.router)`.

The full modified import block and router-registration block becomes:

```python
from app.routers import chain, data, report, plan, chainkb, refresh
app.include_router(chain.router)
app.include_router(data.router)
app.include_router(report.router)
app.include_router(plan.router)
app.include_router(chainkb.router)
app.include_router(refresh.router)
```

- [ ] **Step 3: Verify import works (without token configured)**

Run:
```bash
cd backend && python -c "from app.main import app; print('ok', len(app.routes))"
```
Expected: `ok` + a route count > previous.

- [ ] **Step 4: Verify token enforcement — 503 with no token configured**

Run:
```bash
cd backend && python -c "
from fastapi.testclient import TestClient
from app.main import app
client = TestClient(app)
r = client.post('/api/chainkb/refresh/quotes')
print(r.status_code, r.json())
"
```
Expected: `503 {'detail': 'ADMIN_REFRESH_TOKEN not configured; refresh endpoints disabled.'}`

- [ ] **Step 5: Verify token enforcement — 401 with wrong token**

Run:
```bash
cd backend && ADMIN_REFRESH_TOKEN=test123 python -c "
from fastapi.testclient import TestClient
from app.main import app
# Force config reload by re-importing
import app.config
app.config.ADMIN_REFRESH_TOKEN = 'test123'
client = TestClient(app)
r = client.post('/api/chainkb/refresh/quotes', headers={'X-Admin-Token': 'wrong'})
print(r.status_code, r.json())
"
```
Expected: `401 {'detail': 'invalid or missing X-Admin-Token'}`

- [ ] **Step 6: Verify public freshness endpoint works**

Run:
```bash
cd backend && python -c "
from fastapi.testclient import TestClient
from app.main import app
client = TestClient(app)
r = client.get('/api/chainkb/freshness')
print(r.status_code)
data = r.json()
print('types:', sorted(k for k in data if k not in ['running', 'failed_recent']))
print('running:', data['running'])
"
```
Expected: `200` and `types: ['concepts', 'finance', 'holders', 'lockup', 'margin', 'quotes', 'reports']`.

- [ ] **Step 7: Commit**

```bash
cd "E:/2026projects/Investment-Desk"
git add backend/app/routers/refresh.py backend/app/main.py
git commit -m "feat(backend): 添加 /api/chainkb/refresh/* 与 /freshness endpoints"
```

---

### Task 4: APScheduler — auto-refresh on configured cadences

**Files:**
- Modify: `backend/requirements.txt`
- Create: `backend/app/services/scheduler.py`
- Modify: `backend/app/main.py`

**Interfaces:**
- Consumes: `refresh_service.dispatch` (called with `trigger='scheduler'`).
- Produces: `scheduler.start_scheduler()` and `scheduler.shutdown_scheduler()` — called from `main.py` startup/shutdown hooks. Singleton `BackgroundScheduler` instance.

- [ ] **Step 1: Add apscheduler to requirements**

Edit `backend/requirements.txt`. Append (do not change existing entries):

```
apscheduler>=3.10
```

- [ ] **Step 2: Install the new dependency**

Run:
```bash
cd backend && pip install "apscheduler>=3.10"
```
Expected: install completes with no errors.

- [ ] **Step 3: Write scheduler.py**

Create `backend/app/services/scheduler.py` with this exact content:

```python
"""APScheduler in-process scheduler for automatic data refreshes.

Started on FastAPI startup, gracefully shut down on FastAPI shutdown.
Each job calls refresh_service.dispatch(<type>, session, trigger='scheduler').

Cadences (timezone Asia/Shanghai):
  quotes   mon-fri 9:30-15:00 every 5 min  (two cron triggers; APScheduler can't OR)
  margin   mon-fri 15:30
  finance  sun 03:00
  reports  sun 04:00
  lockup   sun 05:00
  holders  1st of month 03:00
  concepts 1st of month 04:00

If uvicorn restarts, schedules reset (in-process scheduler). Acceptable
for a personal tool; documented in spec §Risks.
"""

from __future__ import annotations

import logging
from typing import Optional

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.executors.pool import ThreadPoolExecutor as APSchedulerPool

from app.db import SessionLocal
from app.services import refresh_service

log = logging.getLogger(__name__)

_scheduler: Optional[BackgroundScheduler] = None

# quotes: two triggers because APScheduler CronTrigger doesn't support OR.
#   1. mon-fri 09:00-14:59 every 5 min
#   2. mon-fri 15:00-15:30 every 5 min
_QUOTES_TRIGGERS = [
    CronTrigger(day_of_week="mon-fri", hour="9-14", minute="*/5",
                timezone="Asia/Shanghai"),
    CronTrigger(day_of_week="mon-fri", hour="15", minute="0-30",
                timezone="Asia/Shanghai"),
]
_MARGIN_TRIGGER = CronTrigger(day_of_week="mon-fri", hour="15", minute="30",
                              timezone="Asia/Shanghai")
_FINANCE_TRIGGER = CronTrigger(day_of_week="sun", hour="3",
                               timezone="Asia/Shanghai")
_REPORTS_TRIGGER = CronTrigger(day_of_week="sun", hour="4",
                               timezone="Asia/Shanghai")
_LOCKUP_TRIGGER = CronTrigger(day_of_week="sun", hour="5",
                              timezone="Asia/Shanghai")
_HOLDERS_TRIGGER = CronTrigger(day="1", hour="3",
                               timezone="Asia/Shanghai")
_CONCEPTS_TRIGGER = CronTrigger(day="1", hour="4",
                                timezone="Asia/Shanghai")


def _run_refresh(refresh_type: str) -> None:
    """Job wrapper: own session, swallow exceptions (logged in chain_refresh_log)."""
    session = SessionLocal()
    try:
        refresh_service.dispatch(refresh_type, session, trigger="scheduler")
    except Exception:
        log.exception("scheduled refresh '%s' failed", refresh_type)
    finally:
        session.close()


def start_scheduler() -> None:
    """Idempotent: safe to call multiple times."""
    global _scheduler
    if _scheduler is not None:
        return

    _scheduler = BackgroundScheduler(
        executors={"default": APSchedulerPool(max_workers=1)},
        timezone="Asia/Shanghai",
        job_defaults={
            "coalesce": True,        # if multiple fires missed, run once
            "max_instances": 1,      # never overlap same job
            "misfire_grace_time": 600,
        },
    )

    # Register quotes with two triggers (APScheduler supports multiple per job-id)
    for i, trig in enumerate(_QUOTES_TRIGGERS):
        _scheduler.add_job(
            _run_refresh, trig,
            args=["quotes"], id=f"quotes_{i}",
            replace_existing=True,
        )
    for type_name, trig in [
        ("margin",   _MARGIN_TRIGGER),
        ("finance",  _FINANCE_TRIGGER),
        ("reports",  _REPORTS_TRIGGER),
        ("lockup",   _LOCKUP_TRIGGER),
        ("holders",  _HOLDERS_TRIGGER),
        ("concepts", _CONCEPTS_TRIGGER),
    ]:
        _scheduler.add_job(
            _run_refresh, trig,
            args=[type_name], id=type_name,
            replace_existing=True,
        )

    _scheduler.start()
    log.info("scheduler started with %d jobs",
             len(_scheduler.get_jobs()))


def shutdown_scheduler() -> None:
    global _scheduler
    if _scheduler is None:
        return
    _scheduler.shutdown(wait=False)
    _scheduler = None


def get_scheduler() -> Optional[BackgroundScheduler]:
    return _scheduler
```

- [ ] **Step 4: Wire startup/shutdown into main.py**

Edit `backend/app/main.py`. Add two new lifecycle hooks after the existing `startup()` function:

```python
@app.on_event("startup")
async def startup_scheduler():
    """Start APScheduler after tables exist (assumes startup() ran first)."""
    from app.services.scheduler import start_scheduler
    start_scheduler()


@app.on_event("shutdown")
async def shutdown_scheduler():
    from app.services.scheduler import shutdown_scheduler
    shutdown_scheduler()
```

Note: FastAPI runs startup hooks in registration order; since the new hook is registered after `startup()`, the DB tables will exist when the scheduler starts.

- [ ] **Step 5: Verify scheduler starts without errors**

Run:
```bash
cd backend && python -c "
from app.services.scheduler import start_scheduler, get_scheduler, shutdown_scheduler
start_scheduler()
s = get_scheduler()
jobs = sorted([(j.id, str(j.trigger)) for j in s.get_jobs()])
for j in jobs: print(j)
shutdown_scheduler()
"
```
Expected: prints 8 job entries (quotes_0, quotes_1, margin, finance, reports, lockup, holders, concepts) with their cron strings. No exceptions.

- [ ] **Step 6: Verify full app boots and scheduler is registered**

Run:
```bash
cd backend && python -c "
from fastapi.testclient import TestClient
from app.main import app
from app.services.scheduler import get_scheduler
with TestClient(app) as client:
    s = get_scheduler()
    print('scheduler running:', s is not None and s.running)
    print('job count:', len(s.get_jobs()) if s else 0)
    r = client.get('/api/health')
    print('health:', r.status_code, r.json())
"
```
Expected: `scheduler running: True`, `job count: 8`, `health: 200 {'status': 'ok'}`.

- [ ] **Step 7: Commit**

```bash
cd "E:/2026projects/Investment-Desk"
git add backend/requirements.txt backend/app/services/scheduler.py backend/app/main.py
git commit -m "feat(backend): 添加 APScheduler 自动刷新调度"
```

---

### Task 5: CLI — token-free local refresh

**Files:**
- Create: `backend/app/services/refresh_cli.py`

**Interfaces:**
- Consumes: `refresh_service.dispatch`, `refresh_service.get_job`, `refresh_service.ChainRefreshLog`.
- Produces: a module runnable as `python -m app.services.refresh_cli [type|--status <id>|--list]` from the `backend/` directory.

- [ ] **Step 1: Write refresh_cli.py**

Create `backend/app/services/refresh_cli.py` with this exact content:

```python
"""CLI entrypoint for triggering refreshes without going through HTTP.

Usage (from backend/ dir):
  python -m app.services.refresh_cli quotes         # sync, blocks ~2s
  python -m app.services.refresh_cli reports        # async, returns job_id immediately
  python -m app.services.refresh_cli all            # async, full refresh
  python -m app.services.refresh_cli --status 42    # query job status
  python -m app.services.refresh_cli --list         # show 20 most recent jobs

No token required (runs in-process, calls refresh_service directly).
"""

from __future__ import annotations

import argparse
import sys
import threading
import time
from datetime import datetime

from app.db import SessionLocal
from app.services import refresh_service


VALID_TYPES = ["quotes", "finance", "reports", "concepts",
               "lockup", "holders", "margin", "all"]


def cmd_run(refresh_type: str) -> int:
    session = SessionLocal()
    try:
        # 'quotes' is fast enough to run sync even from CLI
        if refresh_type == "quotes":
            print(f"running {refresh_type} synchronously...")
            t0 = time.time()
            try:
                job = refresh_service.refresh_quotes(session, trigger="cli")
                elapsed = time.time() - t0
                print(f"  → job #{job.id} {job.status} "
                      f"rows={job.rows_affected} elapsed={elapsed:.1f}s")
                return 0 if job.status == "succeeded" else 1
            except Exception as e:
                print(f"  → failed: {e}", file=sys.stderr)
                return 1

        # All other types (including 'all'): spawn in background thread,
        # poll the log row to surface job_id, then exit.
        print(f"starting {refresh_type} in background...")
        result: dict = {}

        def worker():
            s2 = SessionLocal()
            try:
                refresh_service.dispatch(refresh_type, s2, trigger="cli")
            except Exception as e:
                result["error"] = str(e)
            finally:
                s2.close()

        t = threading.Thread(target=worker, daemon=True)
        t.start()

        # Poll for up to 2s to capture the job_id row
        deadline = time.time() + 2.0
        while time.time() < deadline:
            from app.models.chain_models import ChainRefreshLog
            row = session.query(ChainRefreshLog).filter_by(
                refresh_type=refresh_type, status="running"
            ).order_by(ChainRefreshLog.started_at.desc()).first()
            if row:
                print(f"  → job #{row.id} started at {row.started_at}")
                print(f"  → status: python -m app.services.refresh_cli --status {row.id}")
                return 0
            time.sleep(0.05)

        print("  → job queued but job_id not yet visible; check --list")
        return 0
    finally:
        session.close()


def cmd_status(job_id: int) -> int:
    session = SessionLocal()
    try:
        job = refresh_service.get_job(session, job_id)
        if not job:
            print(f"job {job_id} not found", file=sys.stderr)
            return 1
        print(f"job #{job.id}")
        print(f"  type:         {job.refresh_type}")
        print(f"  status:       {job.status}")
        print(f"  started_at:   {job.started_at}")
        print(f"  finished_at:  {job.finished_at}")
        print(f"  rows:         {job.rows_affected}")
        print(f"  triggered_by: {job.triggered_by}")
        if job.error:
            print(f"  error:        {job.error[:500]}")
        return 0
    finally:
        session.close()


def cmd_list() -> int:
    session = SessionLocal()
    try:
        from app.models.chain_models import ChainRefreshLog
        rows = session.query(ChainRefreshLog).order_by(
            ChainRefreshLog.started_at.desc()
        ).limit(20).all()
        if not rows:
            print("(no refresh runs yet)")
            return 0
        print(f"{'id':>4}  {'type':<10}  {'status':<10}  {'started':<20}  {'rows':>8}  by")
        for r in rows:
            print(f"{r.id:>4}  {r.refresh_type:<10}  {r.status:<10}  "
                  f"{r.started_at:%Y-%m-%d %H:%M:%S}  "
                  f"{(r.rows_affected or 0):>8}  {r.triggered_by}")
        return 0
    finally:
        session.close()


def main() -> int:
    p = argparse.ArgumentParser(prog="refresh_cli",
                                description="Trigger chainkb data refresh (no token required)")
    p.add_argument("type", nargs="?", choices=VALID_TYPES,
                   help="refresh type to run")
    p.add_argument("--status", type=int, metavar="JOB_ID",
                   help="show status of a specific job")
    p.add_argument("--list", action="store_true",
                   help="list 20 most recent jobs")
    args = p.parse_args()

    if args.list:
        return cmd_list()
    if args.status is not None:
        return cmd_status(args.status)
    if args.type:
        return cmd_run(args.type)
    p.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Verify --list works on empty DB**

Run:
```bash
cd backend && python -m app.services.refresh_cli --list
```
Expected: `(no refresh runs yet)` and exit code 0.

- [ ] **Step 3: Verify --help works**

Run:
```bash
cd backend && python -m app.services.refresh_cli --help
```
Expected: usage text shows all 8 type choices + `--status` + `--list` options.

- [ ] **Step 4: Verify unknown type is rejected**

Run:
```bash
cd backend && python -m app.services.refresh_cli unknown_type 2>&1 | tail -3
```
Expected: argparse error message listing valid choices.

- [ ] **Step 5: Commit**

```bash
cd "E:/2026projects/Investment-Desk"
git add backend/app/services/refresh_cli.py
git commit -m "feat(backend): 添加 refresh_cli 本地免 token 触发器"
```

---

### Task 6: Frontend types + API client

**Files:**
- Modify: `frontend/src/types/chainkb.ts`
- Modify: `frontend/src/services/api.ts`

**Interfaces:**
- Consumes: existing `api` axios instance in `services/api.ts`.
- Produces: `FreshnessEntry` + `FreshnessResponse` types; `getFreshness()` function. Used by Task 7's `useFreshness` hook.

- [ ] **Step 1: Add types to chainkb.ts**

Read the existing `frontend/src/types/chainkb.ts` and append at the end (do not change existing types):

```typescript

// ── Freshness (data update timestamps) ──────────────────────────────────────
export interface FreshnessEntry {
  last_success_at: string | null;  // ISO datetime or null if never succeeded
  status: 'succeeded' | 'never';
  minutes_ago: number | null;      // integer minutes since last_success_at
}

export interface FreshnessResponse {
  quotes: FreshnessEntry;
  finance: FreshnessEntry;
  reports: FreshnessEntry;
  concepts: FreshnessEntry;
  lockup: FreshnessEntry;
  holders: FreshnessEntry;
  margin: FreshnessEntry;
  running: string[];                        // currently-running refresh types
  failed_recent: Record<string, string>;    // type → ISO datetime of most recent failure (within 7d)
}
```

- [ ] **Step 2: Add getFreshness to api.ts**

Read the existing `frontend/src/services/api.ts` and append at the end (do not change existing functions):

```typescript

// --- Freshness (data update timestamps) ---
import type { FreshnessResponse } from '../types/chainkb';

export async function getFreshness(): Promise<FreshnessResponse> {
  const { data } = await api.get<FreshnessResponse>('/api/chainkb/freshness');
  return data;
}
```

- [ ] **Step 3: Verify build passes**

Run:
```bash
cd frontend && npm run build 2>&1 | tail -8
```
Expected: exits 0, bundle produced.

- [ ] **Step 4: Verify lint passes**

Run:
```bash
cd frontend && npm run lint 2>&1 | tail -3
```
Expected: exits 0, no errors.

- [ ] **Step 5: Commit**

```bash
cd "E:/2026projects/Investment-Desk"
git add frontend/src/types/chainkb.ts frontend/src/services/api.ts
git commit -m "feat(frontend): 添加 Freshness 类型与 getFreshness API"
```

---

### Task 7: useFreshness hook + DataFreshness component

**Files:**
- Modify: `frontend/src/chainkb/hooks/useChainKb.ts`
- Create: `frontend/src/chainkb/components/DataFreshness.tsx`

**Interfaces:**
- Consumes: `getFreshness` from `services/api`, `FreshnessResponse` from `types/chainkb`.
- Produces: `useFreshness()` hook returning `FreshnessResponse | null`; `<DataFreshness />` React component.

- [ ] **Step 1: Add useFreshness to useChainKb.ts**

Read `frontend/src/chainkb/hooks/useChainKb.ts`. Append at the end (do not change existing hooks):

```typescript

// ── Freshness: polls /api/chainkb/freshness every 60s ───────────────────────
export function useFreshness() {
  const [data, setData] = useState<FreshnessResponse | null>(null);
  useEffect(() => {
    let cancelled = false;
    const tick = async () => {
      try {
        const f = await getFreshness();
        if (!cancelled) setData(f);
      } catch {
        // silent — backend may be down; UI shows last known state
      }
    };
    tick();
    const id = setInterval(tick, 60_000);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, []);
  return data;
}
```

Also add the missing imports at the top of the file if not already present:
```typescript
import type { FreshnessResponse } from '../../types/chainkb';
import { getFreshness } from '../../services/api';
```

- [ ] **Step 2: Write DataFreshness component**

Create `frontend/src/chainkb/components/DataFreshness.tsx`:

```typescript
import type { FreshnessResponse, FreshnessEntry } from '../../types/chainkb';

const TYPE_LABELS: { key: keyof FreshnessResponse; label: string }[] = [
  { key: 'quotes',   label: '现价' },
  { key: 'finance',  label: '财务' },
  { key: 'reports',  label: '研报' },
  { key: 'concepts', label: '概念' },
  { key: 'lockup',   label: '解禁' },
  { key: 'holders',  label: '股东' },
  { key: 'margin',   label: '融资融券' },
];

function formatAgo(minutes: number | null): string {
  if (minutes == null) return '从未';
  if (minutes < 1) return '刚刚';
  if (minutes < 60) return `${minutes}分钟前`;
  if (minutes < 1440) return `${Math.floor(minutes / 60)}小时前`;
  return `${Math.floor(minutes / 1440)}天前`;
}

function entryDisplay(
  entry: FreshnessEntry,
  isRunning: boolean,
  failedAt: string | undefined,
): { text: string; className: string; title?: string } {
  if (isRunning) {
    return { text: '更新中…', className: 'fresh-running', title: '后台正在更新此数据' };
  }
  if (failedAt) {
    return {
      text: '失败',
      className: 'fresh-failed',
      title: `最近失败: ${failedAt}`,
    };
  }
  return {
    text: formatAgo(entry.minutes_ago),
    className: 'fresh-ok',
  };
}

interface DataFreshnessProps {
  freshness: FreshnessResponse | null;
}

export default function DataFreshness({ freshness }: DataFreshnessProps) {
  if (!freshness) {
    return <div className="freshness-strip freshness-loading">数据更新时间载入中…</div>;
  }

  const runningSet = new Set(freshness.running);

  return (
    <div className="freshness-strip">
      {TYPE_LABELS.map(({ key, label }) => {
        const entry = freshness[key as keyof FreshnessResponse] as FreshnessEntry;
        const failedAt = freshness.failed_recent[key as string];
        const { text, className, title } = entryDisplay(
          entry,
          runningSet.has(key as string),
          failedAt,
        );
        return (
          <span key={key as string} className={`fresh-item ${className}`} title={title}>
            <span className="fresh-label">{label}</span>
            <span className="fresh-value">{text}</span>
          </span>
        );
      })}
    </div>
  );
}
```

- [ ] **Step 3: Verify build passes**

Run:
```bash
cd frontend && npm run build 2>&1 | tail -8
```
Expected: exits 0. Watch for TS errors about the `key as keyof FreshnessResponse` cast — if TS complains, simplify by using `string` index.

- [ ] **Step 4: Verify lint passes**

Run:
```bash
cd frontend && npm run lint 2>&1 | tail -3
```
Expected: exits 0.

- [ ] **Step 5: Commit**

```bash
cd "E:/2026projects/Investment-Desk"
git add frontend/src/chainkb/hooks/useChainKb.ts frontend/src/chainkb/components/DataFreshness.tsx
git commit -m "feat(frontend): 添加 useFreshness hook 与 DataFreshness 组件"
```

---

### Task 8: ChainKbPage integration + CSS

**Files:**
- Modify: `frontend/src/chainkb/ChainKbPage.tsx`
- Modify: `frontend/src/chainkb/chainkb.css`

**Interfaces:**
- Consumes: `useFreshness` hook, `<DataFreshness />` component.
- Produces: visible freshness strip in the dashboard header.

- [ ] **Step 1: Read current ChainKbPage header structure**

Run:
```bash
grep -n "chainkb-header\|chainkb-title\|<header\|InvestLens" frontend/src/chainkb/ChainKbPage.tsx | head -20
```
Note the exact lines of the existing header.

- [ ] **Step 2: Wire DataFreshness into header**

Edit `frontend/src/chainkb/ChainKbPage.tsx`:

1. Add imports near the top (alongside existing imports from `./components/...`):
```typescript
import DataFreshness from './components/DataFreshness';
import { useFreshness } from './hooks/useChainKb';
```

2. Inside the `ChainKbPage` function (before the `return`), call the hook:
```typescript
const freshness = useFreshness();
```

3. Modify the existing `<header>` block (or add one if missing). Wrap the title block in a flex container with `<DataFreshness />`:

```tsx
<header className="chainkb-header">
  <div className="chainkb-title">
    {/* existing title contents — keep them as-is */}
    <h1>InvestLens · 产业链图谱</h1>
    {/* any existing subtitle */}
  </div>
  <DataFreshness freshness={freshness} />
</header>
```

If the existing header is structured differently, preserve all existing children of the title block. Only add the wrapper + `<DataFreshness />` sibling.

- [ ] **Step 3: Add CSS for header + freshness strip**

Append to `frontend/src/chainkb/chainkb.css`:

```css

/* ====== Header with freshness strip ====== */
.chainkb-root .chainkb-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
  flex-wrap: wrap;
  padding: 8px 0 12px;
}
.chainkb-root .chainkb-title {
  flex: 0 1 auto;
}

.chainkb-root .freshness-strip {
  display: flex;
  flex-wrap: wrap;
  gap: 6px 14px;
  justify-content: flex-end;
  font-family: 'JetBrains Mono', monospace;
  font-size: 11px;
  color: var(--pencil);
  max-width: 560px;
  line-height: 1.4;
}
.chainkb-root .freshness-strip.freshness-loading {
  font-style: italic;
  opacity: 0.6;
}
.chainkb-root .fresh-item {
  display: inline-flex;
  gap: 4px;
  align-items: baseline;
}
.chainkb-root .fresh-label {
  color: var(--ink);
  opacity: 0.75;
}
.chainkb-root .fresh-value {
  font-weight: 500;
}
.chainkb-root .fresh-item.fresh-running .fresh-value {
  color: var(--ink);
  border-bottom: 1px dotted var(--ink);
  animation: fresh-pulse 1.5s ease-in-out infinite;
}
.chainkb-root .fresh-item.fresh-failed .fresh-value {
  color: #e85a4f;
  font-weight: 600;
  cursor: help;
}
.chainkb-root .fresh-item.fresh-ok .fresh-value {
  color: var(--pencil);
}

@keyframes fresh-pulse {
  0%, 100% { opacity: 1; }
  50%      { opacity: 0.5; }
}

@media (max-width: 768px) {
  .chainkb-root .chainkb-header {
    flex-direction: column;
    align-items: stretch;
  }
  .chainkb-root .freshness-strip {
    justify-content: flex-start;
    max-width: none;
  }
}
```

- [ ] **Step 4: Verify build + lint**

Run:
```bash
cd frontend && npm run build 2>&1 | tail -8 && echo "---LINT---" && npm run lint 2>&1 | tail -3
```
Expected: both exit 0.

- [ ] **Step 5: Commit**

```bash
cd "E:/2026projects/Investment-Desk"
git add frontend/src/chainkb/ChainKbPage.tsx frontend/src/chainkb/chainkb.css
git commit -m "feat(frontend): header 集成 DataFreshness 显示数据更新时间"
```

---

### Task 9: E2E smoke test

**Files:** no code changes — verification only, no commit.

**Interfaces:** Validates the entire chain end-to-end.

- [ ] **Step 1: Generate a real admin token and add to .env**

Run:
```bash
cd backend && python -c "import secrets; print(secrets.token_hex(16))"
```
Take the output (32 hex chars). Append to `backend/.env` (create the file if it doesn't exist):
```
ADMIN_REFRESH_TOKEN=<paste the 32 hex chars here>
```

Verify:
```bash
cd backend && python -c "from app.config import ADMIN_REFRESH_TOKEN; print('token configured:', bool(ADMIN_REFRESH_TOKEN))"
```
Expected: `token configured: True`.

- [ ] **Step 2: Start backend in background**

Run (in background):
```bash
cd backend && uvicorn app.main:app --port 8000
```
Wait for `Application startup complete` in logs.

- [ ] **Step 3: Verify scheduler started with 8 jobs**

Run:
```bash
curl -s http://localhost:8000/api/health
```
Expected: `{"status":"ok"}`. Also check backend logs for `scheduler started with 8 jobs`.

- [ ] **Step 4: Verify freshness endpoint (public) returns 7 types**

Run:
```bash
curl -s http://localhost:8000/api/chainkb/freshness | python -m json.tool | head -20
```
Expected: JSON with all 7 types showing `"status": "never"` (or `"succeeded"` if any prior runs).

- [ ] **Step 5: Run a CLI refresh (no token needed)**

Run:
```bash
cd backend && python -m app.services.refresh_cli quotes
```
Expected: `running quotes synchronously... → job #N succeeded rows=234 elapsed=...`.

- [ ] **Step 6: Verify freshness now shows quotes as recently updated**

Run:
```bash
curl -s http://localhost:8000/api/chainkb/freshness | python -c "import json,sys; d=json.load(sys.stdin); print('quotes:', d['quotes'])"
```
Expected: `quotes: {'last_success_at': '<recent ISO>', 'status': 'succeeded', 'minutes_ago': 0}`.

- [ ] **Step 7: Verify HTTP refresh with token works (sync quotes)**

Run:
```bash
TOKEN=$(cd backend && python -c "from app.config import ADMIN_REFRESH_TOKEN; print(ADMIN_REFRESH_TOKEN)")
curl -s -X POST -H "X-Admin-Token: $TOKEN" http://localhost:8000/api/chainkb/refresh/quotes | python -m json.tool
```
Expected: 200 response with `status: succeeded` and `rows_affected: ~234`.

- [ ] **Step 8: Verify HTTP refresh rejects bad token**

Run:
```bash
curl -s -o /dev/null -w "%{http_code}\n" -X POST -H "X-Admin-Token: wrong" http://localhost:8000/api/chainkb/refresh/quotes
```
Expected: `401`.

- [ ] **Step 9: Verify async refresh (reports) returns 202 + job_id**

Run:
```bash
curl -s -X POST -H "X-Admin-Token: $TOKEN" http://localhost:8000/api/chainkb/refresh/reports
```
Expected: 202 response with `job_id`, `status: running`, `status_url`. **Don't wait for completion** (takes 5 min) — just verify the response shape.

- [ ] **Step 10: Verify --list shows the runs we just did**

Run:
```bash
cd backend && python -m app.services.refresh_cli --list
```
Expected: table showing the manual+cli runs with timestamps.

- [ ] **Step 11: Verify frontend dev server boots and renders freshness**

Start frontend in another terminal (background):
```bash
cd frontend && npm run dev
```
Open `http://localhost:5173/` in a browser. Verify:
- Top-right of dashboard shows 7 labels (现价/财务/研报/概念/解禁/股东/融资融券) with time-ago values.
- `现价` shows `刚刚` or `X分钟前` (because we just refreshed quotes).
- Others show `从未` or `X天前` (never refreshed or stale).
- No console errors.

- [ ] **Step 12: Final whole-branch review**

Dispatch a final reviewer with the full branch diff (per superpowers:requesting-code-review). Fix any Critical/Important findings, then invoke `superpowers:finishing-a-development-branch`.

- [ ] **Step 13: Cleanup**

Kill backend and frontend servers. No commit (this task is verification only).

---

## Self-review

### 1. Spec coverage check
- Spec §Data model (ChainRefreshLog table) → Task 1 ✓
- Spec §API contracts (3 endpoints) → Task 3 ✓
- Spec §Refresh type mapping (8 functions) → Task 2 ✓
- Spec §Scheduler config (7 jobs) → Task 4 ✓
- Spec §Auth (token + 503 on empty) → Task 1 (config) + Task 3 (dependency) ✓
- Spec §CLI → Task 5 ✓
- Spec §Frontend DataFreshness + useFreshness + ChainKbPage + CSS → Tasks 6, 7, 8 ✓
- Spec §Verification → Task 9 ✓

### 2. Placeholder scan
No TBD/TODO/etc. All code blocks contain executable code.

### 3. Type consistency
- `refresh_service.dispatch(type, session, trigger='manual')` — same signature used in Tasks 2, 3, 4, 5 ✓
- `refresh_service.freshness(session)` — returns dict shape used by Task 3 endpoint and (indirectly via api.ts) by Task 7 component ✓
- `ChainRefreshLog` field names (`refresh_type`, `started_at`, `finished_at`, `status`, `rows_affected`, `error`, `triggered_by`) — consistent across Tasks 1, 2, 3, 5 ✓
- `FreshnessEntry` / `FreshnessResponse` field names — consistent across Tasks 6, 7, 8 ✓
- `verify_admin_token` dependency — defined in Task 3, applied to both protected endpoints ✓

### 4. Order dependencies
- Task 1 (model + config) → must precede Task 2 (model + config consumers)
- Task 2 (refresh_service) → must precede Tasks 3, 4, 5 (all call dispatch)
- Task 3 (router) and Task 4 (scheduler) → independent of each other, both depend on Task 2
- Task 5 (CLI) → depends only on Task 2
- Task 6 (types + api) → must precede Task 7 (hook + component consume them)
- Task 7 → must precede Task 8 (page integration)
- Task 9 → runs last, exercises everything
