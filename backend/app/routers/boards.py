"""HTTP API for the market board heat dashboard (板块冷热全景).

Endpoints under /api/quant/boards/*:
    GET  /overview                 — leaderboard: all industries + concept
                                     Top-20 (zombie-filtered) with lifecycle
                                     tags + sparkline series
    GET  /heatmap?days=30          — heat matrix (display set × trade dates)
    GET  /themes?days=20           — THS theme strong-count evolution
    GET  /{bk_code}/detail?days=100 — one board's full drill-down series
    POST /refresh                  — run the nightly pipeline NOW (admin)

The nightly pipeline normally runs at 17:45 on trading days (scheduler);
/refresh re-runs it on demand (~1 min, ~15 EM requests). The 100-day
history bootstrap is CLI-only: python scripts/backfill_em_boards.py.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.auth import verify_admin_token
from app.db import get_db

router = APIRouter(prefix="/api/quant/boards", tags=["quant-boards"])


@router.get("/overview")
def get_overview(
    days: int = Query(20, ge=5, le=60, description="sparkline 窗口(交易日)"),
    db: Session = Depends(get_db),
):
    """Leaderboard for the display set + per-board sparkline series."""
    from app.services.quant import board_service
    return board_service.get_overview(db, days=days)


@router.get("/heatmap")
def get_heatmap(
    days: int = Query(30, ge=5, le=100, description="热力矩阵列数(交易日)"),
    db: Session = Depends(get_db),
):
    """Heat matrix: rows = display-set boards (sorted by heat EMA desc,
    industries then concepts), cols = trade dates, values = heat [0,100]."""
    from app.services.quant import board_service
    return board_service.get_heatmap(db, days=days)


@router.get("/themes")
def get_theme_trends(
    days: int = Query(20, ge=5, le=60),
    db: Session = Depends(get_db),
):
    """THS hot-theme strong-stock counts over time (themes + 业绩线)."""
    from app.services.quant import board_service
    return board_service.get_theme_trends(db, days=days)


@router.get("/{bk_code}/detail")
def get_board_detail(
    bk_code: str,
    days: int = Query(100, ge=10, le=160),
    db: Session = Depends(get_db),
):
    """One board's drill-down: daily change, cumulative excess return vs
    HS300, main inflow, heat/tag series, recent leaders."""
    from app.services.quant import board_service
    result = board_service.get_board_detail(db, bk_code, days=days)
    if result is None:
        raise HTTPException(404, f"Board '{bk_code}' not found")
    return result


@router.post("/refresh")
def trigger_refresh(db: Session = Depends(get_db),
                    _: None = Depends(verify_admin_token)):
    """Run the nightly board pipeline NOW (admin-gated).

    ~15 EM clist requests + Tencent benchmark + THS themes + heat recompute.
    Raises 502 when EM is IP-blocked — retry later, nothing is lost.
    """
    from app.services.quant import board_service
    try:
        return board_service.refresh_boards_daily(db)
    except board_service.BoardSourceError as e:
        raise HTTPException(502, f"board source unavailable: {e}")
