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
# Daily-bar incremental refresh: after close + after margin, mootdx TCP.
# Only fetches today's bar per ticker via --incremental flag.
_QUOTES_HISTORY_TRIGGER = CronTrigger(day_of_week="mon-fri", hour="16", minute="30",
                                      timezone="Asia/Shanghai")
# Fund-flow incremental refresh (EM push2his, ~70 pool tickers × ~1.7s):
# after the daily-bar refresh lands, before the signal scans consume it.
_FUND_FLOW_TRIGGER = CronTrigger(day_of_week="mon-fri", hour="16", minute="40",
                                 timezone="Asia/Shanghai")
# Quant signal scan: 30 min after the daily-bar refresh lands, recompute
# all signals so the /api/quant/signals endpoint is fresh next morning.
_SIGNAL_SCAN_TRIGGER = CronTrigger(day_of_week="mon-fri", hour="17", minute="00",
                                   timezone="Asia/Shanghai")
# Multi-factor cross-sectional scan: runs after the per-ticker scan,
# generates the daily Top-20 portfolio recommendation with IC-adaptive
# weighting + market-cap neutralization. ~15s on 200 tickers.
_MF_SCAN_TRIGGER = CronTrigger(day_of_week="mon-fri", hour="17", minute="30",
                               timezone="Asia/Shanghai")
# Sector-rotation scan: after the multi-factor scan, computes sector
# strength (fund-flow + technical) and the Top-K sectors × Top-N stocks
# rotation portfolio for the pool universe.
_ROTATION_SCAN_TRIGGER = CronTrigger(day_of_week="mon-fri", hour="17", minute="40",
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


def _run_signal_scan() -> None:
    """Job wrapper: recompute quant signals for all tickers.

    Separate from _run_refresh because the scan is pure in-DB compute
    (no backfill script subprocess); it calls signal_service.scan_all directly.
    """
    session = SessionLocal()
    try:
        from app.services.quant import signal_service
        result = signal_service.scan_all(session)
        log.info("scheduled signal scan: %s", result)
    except Exception:
        log.exception("scheduled signal scan failed")
    finally:
        session.close()


def _run_mf_scan() -> None:
    """Job wrapper: run the multi-factor cross-sectional scan.

    Generates the daily Top-N portfolio recommendation using the
    trend-following multi-factor model (IC-adaptive weighting +
    market-cap neutralization). Results stored in chain_mf_signals.
    """
    session = SessionLocal()
    try:
        from app.services.quant import mf_signal_service
        result = mf_signal_service.scan_mf_signals(session)
        log.info("scheduled MF scan: date=%s, selected=%d, %.1fs",
                 result["date"], result["selected"], result["elapsed_s"])
    except Exception:
        log.exception("scheduled MF scan failed")
    finally:
        session.close()


def _run_rotation_scan() -> None:
    """Job wrapper: run the sector-rotation scan.

    Computes sector strength (fund-flow dim + technical dim) for the 8
    pool sectors and persists the Top-K × Top-N rotation portfolio into
    chain_sector_scores / chain_rotation_signals.
    """
    session = SessionLocal()
    try:
        from app.services.quant import rotation_service
        result = rotation_service.scan_rotation_signals(session)
        log.info("scheduled rotation scan: date=%s, sectors=%d, selected=%d, %.1fs",
                 result["date"], result["sector_count"],
                 result["selected"], result["elapsed_s"])
    except Exception:
        log.exception("scheduled rotation scan failed")
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
        ("margin",         _MARGIN_TRIGGER),
        ("quotes_history", _QUOTES_HISTORY_TRIGGER),
        ("fund_flow",      _FUND_FLOW_TRIGGER),
        ("finance",        _FINANCE_TRIGGER),
        ("reports",        _REPORTS_TRIGGER),
        ("lockup",         _LOCKUP_TRIGGER),
        ("holders",        _HOLDERS_TRIGGER),
        ("concepts",       _CONCEPTS_TRIGGER),
    ]:
        _scheduler.add_job(
            _run_refresh, trig,
            args=[type_name], id=type_name,
            replace_existing=True,
        )

    # Quant signal scan — separate handler (no backfill subprocess).
    _scheduler.add_job(
        _run_signal_scan, _SIGNAL_SCAN_TRIGGER,
        id="signal_scan", replace_existing=True,
    )

    # Multi-factor cross-sectional scan (Top-N portfolio recommendation).
    _scheduler.add_job(
        _run_mf_scan, _MF_SCAN_TRIGGER,
        id="mf_scan", replace_existing=True,
    )

    # Sector-rotation scan (Top-K sectors × Top-N stocks portfolio).
    _scheduler.add_job(
        _run_rotation_scan, _ROTATION_SCAN_TRIGGER,
        id="rotation_scan", replace_existing=True,
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
