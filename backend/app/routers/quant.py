"""HTTP API for the quant signal + backtest pipeline.

Endpoints under /api/quant/*:
    GET  /strategies              — list shipped strategies + weights
    GET  /signals                 — paginated signal list (action/layer/sub_industry filters)
    GET  /signals/{ticker}        — latest signal for one ticker + full detail
    POST /scan                    — re-run scan_all (admin-gated)
    POST /backtest                — run a backtest for one ticker
    GET  /backtest/{run_id}       — fetch a stored backtest result

Scan/backtest mutate state so they require the X-Admin-Token header
(shared with refresh/research/deep-analysis routers via app.auth).
"""

from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth import verify_admin_token
from app.db import get_db
from app.services.quant import scoring, signal_service

router = APIRouter(prefix="/api/quant", tags=["quant"])


# ── Strategy catalog ───────────────────────────────────────────────────────

@router.get("/strategies")
def list_strategies():
    """List the v1_default scorecard: strategies, categories, weights, thresholds."""
    card = scoring.DEFAULT_CARD
    items = []
    for s in card.strategies:
        items.append({
            "name": s.name,
            "category": s.category,
            "weight": s.weight,
            "normalized_weight": round(getattr(s, "_normalized_weight", 0.0), 4),
        })
    return {
        "strategy_set": "v1_default",
        "category_weights": {k: round(v, 3) for k, v in card.category_weights.items()},
        "buy_threshold": card.buy_threshold,
        "sell_threshold": card.sell_threshold,
        "strategies": items,
    }


# ── Signal queries ─────────────────────────────────────────────────────────

@router.get("/signals")
def list_signals(
    action: Optional[str] = Query(None, pattern="^(BUY|SELL|HOLD)$"),
    layer: Optional[str] = Query(None, description="Layer code: I/II/III/IV/V"),
    sub_industry: Optional[str] = Query(None, description="group_id e.g. II-D-3"),
    ticker: Optional[str] = None,
    strategy_set: str = Query("v1_default"),
    target_date: Optional[date] = None,
    min_score: Optional[float] = Query(None, ge=-1, le=1),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """Paginated signal list with chain membership joined."""
    return signal_service.get_signals(
        db, action=action, layer=layer, sub_industry=sub_industry,
        ticker=ticker, strategy_set=strategy_set, target_date=target_date,
        limit=limit, offset=offset, min_score=min_score,
    )


@router.get("/signals/{ticker}")
def get_signal(ticker: str, db: Session = Depends(get_db)):
    """Latest signal for one ticker with full strategy detail + chain membership."""
    result = signal_service.get_signal_detail(db, ticker)
    if result is None:
        raise HTTPException(404, f"No signal for ticker '{ticker}'")
    return result


# ── Scan trigger (admin-gated) ─────────────────────────────────────────────

@router.post("/scan")
def trigger_scan(
    strategy_set: str = Query("v1_default"),
    target_date: Optional[date] = None,
    db: Session = Depends(get_db),
    _: None = Depends(verify_admin_token),
):
    """Re-run the full-market signal scan. Admin-gated.

    Returns a summary {scanned, BUY, SELL, HOLD, skipped, elapsed_s}.
    Safe to call repeatedly — upserts on (ticker, date, strategy_set).
    """
    return signal_service.scan_all(db, strategy_set=strategy_set,
                                   target_date=target_date)


# ── Backtest ───────────────────────────────────────────────────────────────

class BacktestRequest(BaseModel):
    ticker: str = Field(..., description="6-digit CN ticker, e.g. 600519")
    strategy_set: str = "v1_default"
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    initial_capital: float = Field(1e5, gt=0)


@router.post("/backtest")
def run_backtest(
    req: BacktestRequest,
    db: Session = Depends(get_db),
    _: None = Depends(verify_admin_token),
):
    """Run a backtest for one ticker. Admin-gated (heavy compute).

    Stores the result in chain_backtest_runs and returns the run summary.
    Fetch full equity curve / trades via GET /backtest/{run_id}.
    """
    from app.services.quant import backtest as bt
    try:
        run = bt.run_and_store(
            db, ticker=req.ticker, strategy_set=req.strategy_set,
            start_date=req.start_date, end_date=req.end_date,
            initial_capital=req.initial_capital,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    return run


@router.get("/backtest/{run_id}")
def get_backtest(run_id: int, db: Session = Depends(get_db)):
    """Fetch a stored backtest run by id (with equity curve + trades)."""
    from app.services.quant import backtest as bt
    result = bt.get_run(db, run_id)
    if result is None:
        raise HTTPException(404, f"Backtest run {run_id} not found")
    return result
