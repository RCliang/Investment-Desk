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
    useful for tracking if a stock is improving or deteriorating in the
    model's assessment.
    """
    from app.services.quant import mf_signal_service
    history = mf_signal_service.get_ranking_history(db, ticker, days=days)
    if not history:
        raise HTTPException(404, f"No MF signal history for '{ticker}'")
    return {"ticker": ticker, "history": history}


# ── Sector Rotation (板块轮动中期趋势策略) ────────────────────────────────────

@router.get("/rotation/sectors")
def get_rotation_sectors(db: Session = Depends(get_db)):
    """Latest sector strength snapshot (8 pool sectors).

    Returns each sector's composite strength [0,1], the fund-flow and
    technical dimensional ranks behind it, member count, and whether the
    sector is in today's Top-K rotation portfolio.
    """
    from app.services.quant import rotation_service
    return rotation_service.get_latest_sector_scores(db)


@router.get("/rotation/sector-history")
def get_rotation_sector_history(
    days: int = Query(30, ge=1, le=180, description="回看天数"),
    db: Session = Depends(get_db),
):
    """Sector strength evolution over the last N days (for the heatmap)."""
    from app.services.quant import rotation_service
    return rotation_service.get_sector_history(db, days=days)


@router.get("/rotation/portfolio")
def get_rotation_portfolio(db: Session = Depends(get_db)):
    """Latest recommended rotation portfolio (Top-K sectors × Top-N stocks).

    Includes per-holding factor scores, entry confirmation (bullish MA
    alignment), divergence warning, and the reference hard-stop level.
    """
    from app.services.quant import rotation_service
    return rotation_service.get_latest_portfolio(db)


@router.get("/rotation/rankings")
def get_rotation_rankings(
    sector: Optional[str] = Query(None, description="板块名, 缺省=全部"),
    db: Session = Depends(get_db),
):
    """Full in-sector rankings for the latest date (whole pool)."""
    from app.services.quant import rotation_service
    return rotation_service.get_rotation_rankings(db, sector=sector)


@router.post("/rotation/scan")
def trigger_rotation_scan(
    top_k: int = Query(3, ge=1, le=8),
    top_n_per_sector: int = Query(2, ge=1, le=5),
    db: Session = Depends(get_db),
    _: None = Depends(verify_admin_token),
):
    """Run the rotation scan NOW (admin-gated).

    Normally triggered by the scheduler at 17:40 on trading days. Persists
    chain_sector_scores + chain_rotation_signals for the latest bar date.
    """
    from app.services.quant import rotation_service
    try:
        return rotation_service.scan_rotation_signals(
            db, top_k=top_k, top_n_per_sector=top_n_per_sector)
    except ValueError as e:
        raise HTTPException(400, str(e))


class RotationBacktestRequest(BaseModel):
    """Request body for the sector-rotation portfolio backtest."""
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    initial_capital: float = Field(1e6, gt=0, description="初始资金(元)")
    holding_period: int = Field(20, ge=5, le=60, description="调仓周期(交易日)")
    top_k: int = Field(3, ge=1, le=8, description="持仓板块数")
    top_n_per_sector: int = Field(2, ge=1, le=5, description="每板块持仓股票数")
    max_weight: float = Field(0.20, gt=0, le=0.40, description="单只最大权重")
    use_fund_flow_factors: bool = Field(
        True, description="false=纯技术面骨架(长历史) / true=含主力资金流因子")
    stop_mode: str = Field(
        "fixed", pattern="^(fixed|atr)$",
        description="硬止损: fixed=入场价×0.9 | atr=入场价−2×ATR14(波动自适应)")
    atr_mult: float = Field(2.0, gt=0, le=6, description="ATR 止损倍数")
    breakdown_buffer: float = Field(
        0.0, ge=0, le=0.10,
        description="破位缓冲带: close 需低于 MA20×(1-buffer) 才算破位(0.03=3%%)")


@router.post("/rotation/backtest")
def run_rotation_backtest(
    req: RotationBacktestRequest,
    db: Session = Depends(get_db),
):
    """Run the sector-rotation portfolio backtest.

    Not admin-gated (read-only compute like /multi-factor/backtest):
    loads pool bars + fund flow, runs the 3-layer engine with daily trend
    exits, simulates with A-share costs, and benchmarks against the
    pool equal-weight index. Full curve/trades via GET /backtest/{run_id}.
    """
    from app.services.quant import rotation_backtest
    try:
        return rotation_backtest.run_and_store(
            db,
            start_date=req.start_date,
            end_date=req.end_date,
            initial_capital=req.initial_capital,
            holding_period=req.holding_period,
            top_k=req.top_k,
            top_n_per_sector=req.top_n_per_sector,
            max_weight=req.max_weight,
            use_fund_flow_factors=req.use_fund_flow_factors,
            stop_mode=req.stop_mode,
            atr_mult=req.atr_mult,
            breakdown_buffer=req.breakdown_buffer,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
