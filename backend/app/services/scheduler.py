"""APScheduler in-process scheduler for automatic data refreshes.

Started on FastAPI startup, gracefully shut down on FastAPI shutdown.
Each job calls refresh_service.dispatch(<type>, session, trigger='scheduler').

Backfill-type cadences live in refresh_service.REFRESH_REGISTRY (the ONE
inventory — script, loader, timeout and cron together). The scan jobs
(signal/mf/rotation/boards/etf, no backfill subprocess) are wired below
( timezone Asia/Shanghai): signal 17:00, mf 17:30, rotation 17:40,
boards 17:45, etf_scan 17:50 on trading days.

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

# ── Scan-job triggers (no backfill subprocess — not registry types) ─────────
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
# Market board heat refresh: after the rotation scan, snapshots every EM
# industry/concept board (clist ×3 fs, ~15 requests) + HS300 benchmark
# (Tencent) + THS hot themes, then recomputes the heat composite and
# lifecycle tags. Aborts loudly if EM is IP-blocked; nothing degrades.
_BOARDS_REFRESH_TRIGGER = CronTrigger(day_of_week="mon-fri", hour="17", minute="45",
                                      timezone="Asia/Shanghai")
# ETF dual-momentum scan: after all evening scans, persists the pool's
# momentum ranking + target portfolio into chain_etf_signals.
_ETF_SCAN_TRIGGER = CronTrigger(day_of_week="mon-fri", hour="17", minute="50",
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


def _run_boards_refresh() -> None:
    """Job wrapper: run the market board heat pipeline.

    EM clist snapshot + Tencent benchmark + THS themes + heat recompute
    into chain_board_meta/daily/heat + chain_theme_daily. Raises through
    BoardSourceError when EM is blocked (logged, retried next night).
    """
    session = SessionLocal()
    try:
        from app.services.quant import board_service
        result = board_service.refresh_boards_daily(session)
        log.info("scheduled boards refresh: date=%s, boards=%d, tags=%d, %.1fs",
                 result["date"], result["boards"], result["theme_tags"],
                 result["elapsed_s"])
    except Exception:
        log.exception("scheduled boards refresh failed")
    finally:
        session.close()


def _run_etf_scan() -> None:
    """Job wrapper: run the ETF dual-momentum scan.

    Computes the pool's blended/vol-adjusted momentum ranking, applies the
    absolute-momentum gate + rank buffer, and persists the target portfolio
    into chain_etf_signals.
    """
    session = SessionLocal()
    try:
        from app.services.quant import etf_signal_service
        result = etf_signal_service.scan_etf_signals(session)
        log.info("scheduled ETF rotation scan: date=%s, selected=%d, "
                 "cash=%.0f%%, %.1fs", result["date"], result["selected"],
                 result["cash_weight"] * 100, result["elapsed_s"])
    except Exception:
        log.exception("scheduled ETF rotation scan failed")
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

    # Backfill-type jobs: cron specs come straight from the registry
    # (quotes carries two windows → job ids quotes_0 / quotes_1).
    for type_name, spec in refresh_service.REFRESH_REGISTRY.items():
        for i, cron_kw in enumerate(spec.cron):
            _scheduler.add_job(
                _run_refresh,
                CronTrigger(**cron_kw, timezone="Asia/Shanghai"),
                args=[type_name],
                id=type_name if len(spec.cron) == 1 else f"{type_name}_{i}",
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

    # Market board heat pipeline (板块冷热全景).
    _scheduler.add_job(
        _run_boards_refresh, _BOARDS_REFRESH_TRIGGER,
        id="boards_refresh", replace_existing=True,
    )

    # ETF dual-momentum scan (混合池双动量轮动).
    _scheduler.add_job(
        _run_etf_scan, _ETF_SCAN_TRIGGER,
        id="etf_scan", replace_existing=True,
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
