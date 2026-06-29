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
