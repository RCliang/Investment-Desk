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

import logging
import os
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Literal

from sqlalchemy.orm import Session

from app.models.chain_models import ChainRefreshLog

log = logging.getLogger(__name__)

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
    """Return True if a row with status='running' exists for this type.

    Auto-clears stale 'running' rows that have exceeded their expected timeout.
    """
    _sweep_stale(session, refresh_type)
    return session.query(ChainRefreshLog).filter_by(
        refresh_type=refresh_type, status="running"
    ).first() is not None


def _sweep_stale(session: Session, refresh_type: str | None = None) -> int:
    """Mark stale 'running' rows as 'failed' if they exceeded their timeout.

    A row is stale if started_at + 2 * timeout < now.
    Returns the number of rows swept.
    """
    now = datetime.utcnow()
    types = [refresh_type] if refresh_type else list(_TYPE_MAP.keys())
    swept = 0
    for t in types:
        timeout = _TIMEOUTS.get(t, 900)
        threshold = now - timedelta(seconds=timeout * 2)
        stale_rows = session.query(ChainRefreshLog).filter(
            ChainRefreshLog.refresh_type == t,
            ChainRefreshLog.status == "running",
            ChainRefreshLog.started_at < threshold,
        ).all()
        for row in stale_rows:
            row.status = "failed"
            row.finished_at = row.started_at + timedelta(seconds=timeout)
            row.error = f"auto-swept: stale running exceeded {timeout * 2}s"
            swept += 1
            log.warning("swept stale running job #%d type=%s started=%s",
                        row.id, row.refresh_type, row.started_at)
    if swept:
        session.commit()
    return swept


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

    log_row = ChainRefreshLog(
        refresh_type=refresh_type,
        status="running",
        triggered_by=trigger,
    )
    session.add(log_row)
    session.commit()
    session.refresh(log_row)

    try:
        # Step 1: run backfill script (writes JSON to backend/data/)
        log.info("refresh '%s': running %s ...", refresh_type, script_name)
        # Run the backfill script with UTF-8 stdio. On Windows, `text=True`
        # without an explicit encoding falls back to the system locale (cp936/
        # GBK), which fails to decode non-ASCII bytes printed by the scripts
        # (e.g. Chinese research-report titles from East Money) and raises
        # UnicodeDecodeError in subprocess's internal _readerthread.
        # PYTHONUTF8=1 puts the child Python in UTF-8 mode so its print()
        # writes UTF-8 too; encoding/errors below decode the parent side.
        env = {**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}
        result = subprocess.run(
            [sys.executable, str(script_path)],
            cwd=str(BACKEND_DIR),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
            timeout=_TIMEOUTS[refresh_type],
        )
        if result.returncode != 0:
            tail = (result.stderr or result.stdout or "")[-500:]
            raise RuntimeError(f"backfill {script_name} exited {result.returncode}: {tail}")

        log.info("refresh '%s': backfill done, loading into DB ...", refresh_type)

        # Step 2: ingest JSON into DB via the matching loader
        # Import lazily so a broken script doesn't break module import.
        from scripts import load_seed_to_db as loader_mod
        loader_fn = getattr(loader_mod, loader_name)
        rows = loader_fn(session)
        # load_concept_blocks returns a tuple (n_companies, n_concepts, n_links)
        if isinstance(rows, tuple):
            rows = sum(rows)

        log_row.finished_at = datetime.utcnow()
        log_row.status = "succeeded"
        log_row.rows_affected = int(rows or 0)
        session.commit()
        session.refresh(log_row)
        log.info("refresh '%s': succeeded rows=%d", refresh_type, log_row.rows_affected)
        return log_row

    except Exception as e:
        log_row.finished_at = datetime.utcnow()
        log_row.status = "failed"
        log_row.error = f"{type(e).__name__}: {str(e)[:1000]}"
        session.commit()
        session.refresh(log_row)
        log.error("refresh '%s': failed — %s: %s", refresh_type, type(e).__name__, e)
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
