"""Refresh orchestration: run a backfill script then ingest via load_seed_to_db.

Three callers reach this module:
  - HTTP endpoint (app.routers.refresh)  — trigger='manual', requires token
  - APScheduler jobs (app.services.scheduler) — trigger='scheduler'
  - CLI (app.services.refresh_cli)       — trigger='cli'

All three paths converge here so logging, error handling, and concurrency
checks are uniform. The ONE inventory of refresh types is REFRESH_REGISTRY:
per type it carries the backfill script, loader, timeout, cron cadence and
refresh_all ordering. Router/CLI derive their valid-type lists and the
scheduler derives its cron jobs from it — adding a type is one registry
row, and the "list of types" can no longer drift between consumers
(architecture review 2026-09-06, candidate 2; the API list had already
drifted and lacked quotes_history/fund_flow/etf_klines).

Each refresh run:

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
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Literal, Optional

from sqlalchemy.orm import Session

from app.models.chain_models import ChainRefreshLog

log = logging.getLogger(__name__)

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent  # backend/
SCRIPTS_DIR = BACKEND_DIR / "scripts"

# Kept as a static Literal for type-checkers; test_refresh_registry pins
# it to the registry keys so it cannot drift either.
RefreshType = Literal[
    "quotes", "finance", "reports", "concepts",
    "lockup", "holders", "margin", "quotes_history", "fund_flow",
    "etf_klines", "all",
]
Trigger = Literal["manual", "scheduler", "cli"]


@dataclass(frozen=True)
class RefreshSpec:
    """Everything the three consumers need to know about one refresh type.

    cron entries are CronTrigger kwargs (Asia/Shanghai is applied by the
    scheduler); empty tuple = manual/CLI only. all_order is the position
    in refresh_all's fast→slow sequence (None = excluded from 'all').
    """

    script: str                          # backfill script in scripts/
    loader: str                          # loader fn name in load_seed_to_db
    timeout: int                         # subprocess timeout (seconds)
    extra_args: tuple[str, ...] = ()     # CLI flags for the backfill script
    cron: tuple[dict, ...] = field(default=())
    all_order: Optional[int] = None
    desc: str = ""


# ── The ONE inventory ───────────────────────────────────────────────────────
# quotes uses two cron windows (APScheduler CronTrigger can't OR): the
# 9:00-15:00 session plus the 15:00-15:30 closing auction tail.
# quotes_history / fund_flow / etf_klines run with --incremental so the
# daily job only fetches recent bars (full history is a one-off manual
# backfill of the same scripts).
REFRESH_REGISTRY: dict[str, RefreshSpec] = {
    "quotes": RefreshSpec(
        script="backfill_tencent_quotes.py", loader="load_quotes",
        timeout=60, all_order=1, desc="实时行情快照(腾讯)",
        cron=({"day_of_week": "mon-fri", "hour": "9-14", "minute": "*/5"},
              {"day_of_week": "mon-fri", "hour": "15", "minute": "0-30"}),
    ),
    "quotes_history": RefreshSpec(
        script="backfill_mootdx_klines.py", loader="load_daily_bars",
        timeout=300, extra_args=("--incremental",), all_order=2,
        desc="日K线增量(mootdx TCP, 每标的当日一根)",
        cron=({"day_of_week": "mon-fri", "hour": "16", "minute": "30"},),
    ),
    "etf_klines": RefreshSpec(
        script="backfill_etf_klines.py", loader="load_etf_daily_bars",
        timeout=300, extra_args=("--incremental",),
        desc="ETF池后复权K线增量(EM push2his)",
        cron=({"day_of_week": "mon-fri", "hour": "16", "minute": "35"},),
    ),
    "margin": RefreshSpec(
        script="backfill_em_margin_trading.py", loader="load_margin",
        timeout=900, all_order=3, desc="融资融券余额(EM)",
        cron=({"day_of_week": "mon-fri", "hour": "15", "minute": "30"},),
    ),
    "fund_flow": RefreshSpec(
        script="backfill_em_fund_flow.py", loader="load_fund_flow",
        timeout=600, extra_args=("--incremental",),
        desc="个股资金流增量(EM push2his, ~5日/标的)",
        cron=({"day_of_week": "mon-fri", "hour": "16", "minute": "40"},),
    ),
    "lockup": RefreshSpec(
        script="backfill_em_lockup_expiry.py", loader="load_lockup",
        timeout=900, all_order=4, desc="解禁日历(EM)",
        cron=({"day_of_week": "sun", "hour": "5"},),
    ),
    "holders": RefreshSpec(
        script="backfill_em_holder_num.py", loader="load_holder_num",
        timeout=900, all_order=5, desc="股东户数(EM)",
        cron=({"day": "1", "hour": "3"},),
    ),
    "reports": RefreshSpec(
        script="backfill_em_reports.py", loader="load_reports",
        timeout=900, all_order=6, desc="研报列表(EM)",
        cron=({"day_of_week": "sun", "hour": "4"},),
    ),
    "concepts": RefreshSpec(
        script="backfill_em_concept_blocks.py", loader="load_concept_blocks",
        timeout=900, all_order=7, desc="概念板块成分(EM)",
        cron=({"day": "1", "hour": "4"},),
    ),
    "finance": RefreshSpec(
        script="backfill_mootdx_finance.py", loader="load_finance",
        timeout=600, all_order=8, desc="财务三表(F10)",
        cron=({"day_of_week": "sun", "hour": "3"},),
    ),
}


def valid_types() -> list[str]:
    """Triggerable type names, sorted (includes 'all')."""
    return sorted([*REFRESH_REGISTRY, "all"])


def all_sequence() -> list[str]:
    """refresh_all's execution order: fast → slow (registry all_order)."""
    return [t for t, _ in
            sorted(((t, s.all_order) for t, s in REFRESH_REGISTRY.items()
                    if s.all_order is not None),
                   key=lambda kv: kv[1])]


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
    types = [refresh_type] if refresh_type else list(REFRESH_REGISTRY.keys())
    swept = 0
    for t in types:
        timeout = REFRESH_REGISTRY[t].timeout
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

    for t in REFRESH_REGISTRY:
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
    for t in REFRESH_REGISTRY:
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
    if refresh_type not in REFRESH_REGISTRY:
        raise ValueError(f"unknown refresh type: {refresh_type}")

    if is_running(session, refresh_type):
        # Concurrency conflict — caller (HTTP) turns this into 409.
        raise RefreshConflictError(refresh_type)

    spec = REFRESH_REGISTRY[refresh_type]
    script_name, loader_name = spec.script, spec.loader
    extra_args = list(spec.extra_args)
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
        log.info("refresh '%s': running %s %s ...",
                 refresh_type, script_name, " ".join(extra_args))
        # Run the backfill script with UTF-8 stdio. On Windows, `text=True`
        # without an explicit encoding falls back to the system locale (cp936/
        # GBK), which fails to decode non-ASCII bytes printed by the scripts
        # (e.g. Chinese research-report titles from East Money) and raises
        # UnicodeDecodeError in subprocess's internal _readerthread.
        # PYTHONUTF8=1 puts the child Python in UTF-8 mode so its print()
        # writes UTF-8 too; encoding/errors below decode the parent side.
        env = {**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}
        result = subprocess.run(
            [sys.executable, str(script_path), *extra_args],
            cwd=str(BACKEND_DIR),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
            timeout=spec.timeout,
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


def refresh_all(session: Session, trigger: Trigger = "manual") -> list[ChainRefreshLog]:
    """Sequentially run all refreshes in order: fast → slow.

    Order comes from the registry's all_order (quotes → quotes_history →
    margin → lockup → holders → reports → concepts → finance). Returns the
    list of per-type log rows. Continues on per-type failure (each failure
    is logged; does not abort the sequence).
    """
    results: list[ChainRefreshLog] = []
    for t in all_sequence():
        try:
            results.append(_run_one(session, t, trigger))
        except RefreshConflictError:
            continue  # skip if already running
        except Exception:
            # Error already logged to db; keep going.
            continue
    return results


def dispatch(refresh_type: str, session: Session, trigger: Trigger = "manual"):
    """Look up and run the refresh by name. Used by router + CLI + scheduler."""
    if refresh_type == "all":
        return refresh_all(session, trigger=trigger)
    if refresh_type not in REFRESH_REGISTRY:
        raise ValueError(f"unknown refresh type: {refresh_type}")
    return _run_one(session, refresh_type, trigger)


class RefreshConflictError(Exception):
    """Raised when a refresh of the same type is already running."""
    def __init__(self, refresh_type: str):
        self.refresh_type = refresh_type
        super().__init__(f"refresh '{refresh_type}' already running")
