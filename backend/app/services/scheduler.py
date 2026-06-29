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
