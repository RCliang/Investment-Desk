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
    """List all available strategy sets with their weights and thresholds.

    Returns a catalog (v1_default multi-factor + trend_follow pure trend) so
    the frontend can show a strategy-set picker. Each set's `strategies` list
    shows the active factors and weights.
    """
    return {"strategy_sets": scoring.list_strategy_sets()}


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
):
    """Run a backtest for one ticker.

    NOT admin-gated: a backtest is a pure read-only compute (reads bars,
    writes only its own result row). Unlike /scan (full-market batch write)
    or /refresh (expensive backfill subprocess), it's cheap and safe to
    expose — the whole point of the panel is letting anyone explore how a
    strategy would have performed on a given ticker.

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


# ── Multi-Factor Portfolio (截面多因子趋势跟踪) ──────────────────────────────

@router.get("/multi-factor/factors")
def list_factors():
    """List available cross-sectional factors for the multi-factor model.

    Returns each factor's name, direction, and description so the frontend
    can show a factor picker and explain what each factor measures.
    """
    from app.services.quant.factor_model import MultiFactorEngine

    engine = MultiFactorEngine()
    factor_info = []
    for f in engine.factors:
        factor_info.append({
            "name": f.name,
            "direction": "看多" if f.direction == 1 else "看空",
            "min_lookback": f.min_lookback,
        })
    return {
        "factors": factor_info,
        "config": {
            "holding_period": engine.holding_period,
            "top_n": engine.top_n,
            "max_weight": engine.max_weight,
            "ic_window": engine.ic_window,
            "weighting_method": engine.weighting_method,
        },
    }


class PortfolioBacktestRequest(BaseModel):
    """Request body for multi-factor portfolio backtest.

    Runs the full cross-sectional pipeline: factor computation → IC analysis
    → market-cap neutralization → composite scoring → top-N selection →
    portfolio simulation with 20-day rebalancing.
    """
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    initial_capital: float = Field(1e6, gt=0, description="初始资金(元)")
    holding_period: int = Field(20, ge=5, le=60, description="调仓周期(交易日)")
    top_n: int = Field(20, ge=5, le=50, description="持仓股票数")
    max_weight: float = Field(0.10, gt=0, le=0.30, description="单只最大权重")


@router.post("/multi-factor/backtest")
def run_multi_factor_backtest(
    req: PortfolioBacktestRequest,
    db: Session = Depends(get_db),
):
    """Run a multi-factor portfolio backtest.

    This is the core of the trend-following multi-factor model:
      1. Load ALL tickers' daily bars from DB
      2. Compute 7 trend-following factors (momentum, MA slope, breakout...)
      3. Market-cap neutralize each factor (removes size bias)
      4. Compute rolling IC (60-day) for adaptive factor weighting
      5. Combine factors into a composite score (ICIR-weighted)
      6. Select top-N stocks every `holding_period` days
      7. Simulate with realistic A-share transaction costs

    Returns portfolio-level metrics: total return, Sharpe, max drawdown,
    hit rate, IC summary per factor, and the rebalance log.
    """
    from app.services.quant import portfolio_backtest as pbt
    try:
        result = pbt.run_and_store(
            db,
            start_date=req.start_date,
            end_date=req.end_date,
            initial_capital=req.initial_capital,
            holding_period=req.holding_period,
            top_n=req.top_n,
            max_weight=req.max_weight,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    return result


# ── Multi-Factor Daily Signal (每日信号) ──────────────────────────────────────

@router.post("/multi-factor/scan")
def trigger_mf_scan(
    top_n: int = Query(20, ge=5, le=50, description="持仓股票数"),
    db: Session = Depends(get_db),
    _: None = Depends(verify_admin_token),
):
    """Run the multi-factor cross-sectional scan NOW (admin-gated).

    This is normally triggered by the scheduler at 17:30 on trading days,
    but can be manually triggered here for testing or ad-hoc runs.

    Generates the Top-N portfolio recommendation and stores it in
    chain_mf_signals. Returns a summary with selected holdings.
    """
    from app.services.quant import mf_signal_service
    try:
        result = mf_signal_service.scan_mf_signals(db, top_n=top_n)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return result


@router.get("/multi-factor/portfolio")
def get_latest_mf_portfolio(
    top_only: bool = Query(True, description="仅返回入选组合, false=返回全排名"),
    db: Session = Depends(get_db),
):
    """Get the latest multi-factor portfolio recommendation.

    Returns the most recent Top-N stock selection with weights, ranks,
    composite scores, and per-factor breakdowns. This is what you'd
    actually trade if following the strategy.

    The portfolio is refreshed daily at 17:30 by the scheduler.
    """
    from app.services.quant import mf_signal_service
    return mf_signal_service.get_latest_portfolio(db, top_only=top_only)


@router.get("/multi-factor/history/{ticker}")
def get_mf_ranking_history(
    ticker: str,
    days: int = Query(60, ge=1, le=500),
    db: Session = Depends(get_db),
):
    """Get a ticker's multi-factor ranking history.

    Shows how the stock's rank and composite score evolved over time —
    useful for tracking if a stock is improving or deteriorating in
    the model's assessment.
    """
    from app.services.quant import mf_signal_service
    history = mf_signal_service.get_ranking_history(db, ticker, days=days)
    if not history:
        raise HTTPException(404, f"No MF signal history for '{ticker}'")
    return {"ticker": ticker, "history": history}
