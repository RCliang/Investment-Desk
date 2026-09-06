"""ETF dual-momentum daily service: scan, persist, query, backtest.

Daily pipeline (scheduler 17:50, after etf_klines 16:35):
  1. Load the ETF pool's (hfq) bars from chain_daily_bars — no fund-flow
     join: the strategy is price-only momentum.
  2. Run EtfRotationEngine (blended momentum → vol adjustment → absolute
     gate → rank buffer).
  3. Persist chain_etf_signals (one row per pool ETF) with the day's
     ranking, gate flag, target weights and ATR stop references.

Backtest: reuses RotationBacktester unchanged (it only reads the engine's
portfolios/ic_summary/config contract) with ETF costs — no stamp duty,
万1 commission — and the validated v2 exit rules (ATR stop + 3% breakdown
buffer).

Query layer serves the /api/quant/etf-rotation/* endpoints.
"""

from __future__ import annotations

import json
import logging
from datetime import date
from typing import Optional

import pandas as pd
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app.models.chain_models import DailyBar, EtfSignal, BacktestRun
from app.services.quant import etf_pool
from app.services.quant.etf_rotation import (
    EtfRotationEngine, TOP_N, BUFFER_RANK, HOLDING_PERIOD,
    VOL_WINDOW, ABS_WINDOW,
)
from app.services.quant.sector_rotation import build_atr_panel
from .signal_service import _load_bars_df

log = logging.getLogger(__name__)

# Costs, exit rules and the sleeve live in etf_lab.PRESETS — the single
# source shared with every research run (architecture review 2026-09-06:
# the hand-mirrored MID_BASE had already drifted). Local names re-exported
# so tests' monkeypatch targets and existing imports stay valid.
from .etf_lab import (  # noqa: E402
    ETF_COMMISSION_RATE, ETF_COMMISSION_MIN, ETF_STAMP_DUTY_RATE,
    ETF_SLIPPAGE_RATE, DEFENSIVE_SLEEVE, REGIME_TICKER, REGIME_MA_WINDOW,
    PRESETS,
)
STOP_MODE = "atr"
ATR_MULT = PRESETS["mid"]["atr_mult"]              # 4×ATR14 disaster brake
BREAKDOWN_BUFFER = 0.03
USE_TARGET_VOL = PRESETS["mid"]["use_target_vol"]
TARGET_VOL = PRESETS["mid"]["target_vol"]
# Calendar-anchored rebalancing (2026-09-03 fix): selection re-runs on the
# FIRST TRADING DAY of each month; between anchors the live recommendation
# is frozen (exits / defensive replacement still act daily). Inception =
# the first anchor: signal 2026-09-03 → execution 2026-09-04, next anchor
# 2026-10-09 (first trading day after the National Day holiday).
STRATEGY_INCEPTION = "2026-09-03"
# Hybrid regime sleeve ON for the live scan (docs §十, go-live 2026-09-05).
# PRESETS["hybrid"] ≡ this scan's engine configuration by construction.
USE_DEFENSIVE_SLEEVE = True


# ── Data loading ────────────────────────────────────────────────────────────

def load_etf_pool_bars(
    db: Session,
    limit: int = 1200,
    min_bars: int = 140,
) -> dict[str, pd.DataFrame]:
    """Pool ETFs' bars (hfq closes). min_bars > max(120d lookback + warmup):
    shorter-history members simply sit out the ranking."""
    bars: dict[str, pd.DataFrame] = {}
    for t in etf_pool.get_all_tickers():
        df = _load_bars_df(db, t, limit=limit)
        if df is None or len(df) < min_bars:
            continue
        bars[t] = df
    return bars


# ── Daily scan ──────────────────────────────────────────────────────────────

def scan_etf_signals(
    db: Session,
    top_n: int = TOP_N,
    buffer_rank: int = BUFFER_RANK,
    holding_period: int = HOLDING_PERIOD,
) -> dict:
    """Run the dual-momentum engine and persist today's snapshot. Idempotent.

    Returns {date, scanned, selected, cash_weight, holdings, elapsed_s}.
    """
    from datetime import datetime
    started = datetime.utcnow()

    bars = load_etf_pool_bars(db)
    if len(bars) < 6:
        raise ValueError(
            f"Insufficient ETF bars ({len(bars)}), need ≥6 — run the ETF "
            f"kline backfill first (refresh type etf_klines)")

    engine = EtfRotationEngine(
        cash_ticker=etf_pool.get_cash_ticker(),
        top_n=top_n, buffer_rank=buffer_rank, holding_period=holding_period,
        use_target_vol=USE_TARGET_VOL, target_vol=TARGET_VOL,
        rebalance_anchor="calendar", calendar_start=STRATEGY_INCEPTION,
        defensive_sleeve=DEFENSIVE_SLEEVE if USE_DEFENSIVE_SLEEVE else None,
        regime_ticker=REGIME_TICKER, regime_ma_window=REGIME_MA_WINDOW)
    model = engine.run(bars)

    latest = model["latest"]["date"]
    if latest is None:
        raise ValueError("No valid momentum scores computed (warm-up?)")
    weights = model["latest"]["weights"]
    score = model["panels"]["score"]
    raw = model["panels"]["raw"]
    vol = model["panels"]["vol"]
    abs_ret = model["panels"][f"r{engine.abs_window}"]

    score_row = score.loc[latest].dropna()
    ranked = score_row.sort_values(ascending=False, kind="mergesort")
    ranks = {t: i + 1 for i, t in enumerate(ranked.index)}
    abs_row = abs_ret.loc[latest]
    cash_ret = abs_row.get(etf_pool.get_cash_ticker())

    # Stop reference for held risk ETFs: validated v2 rule (close − 2×ATR14).
    atr_panel = build_atr_panel(bars)

    sig_date = date.fromisoformat(str(latest)[:10])
    names = etf_pool.get_names()
    asset_classes = etf_pool.get_asset_classes()
    cash_t = etf_pool.get_cash_ticker()

    db.query(EtfSignal).filter(EtfSignal.date == sig_date).delete()
    rows = []
    for t in bars:
        if t == cash_t:
            continue  # cash ETF has no momentum rank; only its parking weight
        if t not in ranks:
            continue  # warm-up / insufficient history — sits out
        close_at = float(bars[t].iloc[-1]["close"])
        atr_val = atr_panel.loc[latest, t] \
            if (latest in atr_panel.index and t in atr_panel.columns) else None
        stop = None
        if pd.notna(atr_val) and atr_val > 0:
            stop = round(close_at - ATR_MULT * float(atr_val), 3)
        rows.append({
            "date": sig_date,
            "ticker": t,
            "name": names.get(t, ""),
            "asset_class": asset_classes.get(t, ""),
            "momentum_raw": round(float(raw.loc[latest, t]), 6)
            if pd.notna(raw.loc[latest, t]) else None,
            "momentum_score": round(float(score.loc[latest, t]), 6),
            "momentum_rank": ranks[t],
            "abs_momentum_pass": bool(
                cash_ret is not None and pd.notna(cash_ret)
                and pd.notna(abs_row.get(t))
                and float(abs_row[t]) >= float(cash_ret)),
            "is_selected": t in weights,
            "weight": round(float(weights.get(t, 0.0)), 4),
            "stop_price": stop,
            "detail_json": json.dumps({
                f"r{engine.windows[i]}": round(
                    float(model["panels"][f"r{w}"].loc[latest, t]), 6)
                if pd.notna(model["panels"][f"r{w}"].loc[latest, t]) else None
                for i, w in enumerate(engine.windows)
            }, ensure_ascii=False),
        })
    # Cash row is always written (weight 0 when fully invested) so the
    # pool snapshot is complete and the frontend can show the parking slot.
    rows.append({
        "date": sig_date, "ticker": cash_t,
        "name": names.get(cash_t, ""),
        "asset_class": asset_classes.get(cash_t, ""),
        "momentum_raw": None, "momentum_score": None,
        "momentum_rank": None, "abs_momentum_pass": True,
        "is_selected": cash_t in weights,
        "weight": round(float(weights.get(cash_t, 0.0)), 4),
        "stop_price": None, "detail_json": "",
    })
    if rows:
        db.bulk_insert_mappings(EtfSignal, rows)
    db.commit()

    elapsed = (datetime.utcnow() - started).total_seconds()
    selected = [t for t in weights if t != cash_t]
    log.info("ETF rotation scan done: date=%s, %d ranked, %d selected, "
             "cash=%.0f%%, %.1fs", sig_date, len(ranks), len(selected),
             weights.get(cash_t, 0.0) * 100, elapsed)

    regime = model.get("regime")
    if regime is not None:
        log.info("ETF rotation regime: risk_off=%s sleeve=%s (%s vs MA%d)",
                 regime.get("risk_off"), regime.get("sleeve"),
                 regime.get("regime_ticker"), regime.get("regime_ma_window"))

    return {
        "date": str(sig_date),
        "scanned": len(ranks),
        "selected": len(selected),
        "cash_weight": round(float(weights.get(cash_t, 0.0)), 4),
        "holdings": [
            {"ticker": t, "name": names.get(t, ""), "weight": round(w, 4)}
            for t, w in sorted(weights.items(), key=lambda kv: -kv[1])
        ],
        "regime": regime,
        "config": model["config"],
        "elapsed_s": round(elapsed, 1),
    }


# ── Backtest ────────────────────────────────────────────────────────────────

def run_backtest_and_store(
    db: Session,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    initial_capital: float = 1e6,
    top_n: int = TOP_N,
    buffer_rank: int = BUFFER_RANK,
    holding_period: int = HOLDING_PERIOD,
    use_abs_gate: bool = True,
    use_buffer: bool = True,
    use_market_gate: bool = False,
    market_ma_window: int = 200,
    rebalance_mode: str = "fixed",
    rebalance_anchor: str = "calendar",
    weight_mode: str = "equal",
    use_target_vol: bool = USE_TARGET_VOL,
    target_vol: float = TARGET_VOL,
    exit_replacement: bool = True,
    momentum_windows: Optional[list[int]] = None,
    momentum_weights: Optional[list[float]] = None,
    vol_window: int = VOL_WINDOW,
    abs_window: int = ABS_WINDOW,
    use_trend_filter: bool = False,
    circuit_breaker_drawdown: float = 0.0,
    use_defensive_sleeve: bool = False,
    atr_mult: Optional[float] = None,   # None → preset value
    strategy_set: str = "etf_momentum_rotation",
    bars_limit: int = 1200,
) -> dict:
    """Run the ETF dual-momentum backtest, store, return summary.

    Reuses RotationBacktester with ETF costs (no stamp duty) and the
    validated v2 exit rules; benchmark = pool equal-weight (daily
    rebalanced, no costs), the same hurdle convention as the sector
    rotation.

    use_market_gate blocks 宽基+行业 tickers while 510300 trades below
    its `market_ma_window` MA (防守 names + cash stay rankable).
    rebalance_mode: 'fixed' = every holding_period days; 'dynamic' =
    daily check, trade only when the holding set changes.
    rebalance_anchor: 'grid' | 'calendar' (monthly first trading day,
    live default) | 'weekly' (last trading day of each ISO week — the
    short-rotation cadence).
    weight_mode: 'equal' = 1/top_n per slot; 'risk_parity' = inverse-vol
    sizing among the selected. use_target_vol scales risk weights down
    (freed share → cash) when the vol_window covariance estimate exceeds
    `target_vol`.
    momentum_windows/weights/vol_window/abs_window: the momentum
    parameterization (defaults = the tuned mid-term 60/120/250 preset;
    the short-rotation preset passes (20,60)/(0.6,0.4)/20/60).
    use_trend_filter: MA20 trend-confirmation entry filter (close above
    a rising MA20 to be eligible).
    circuit_breaker_drawdown: portfolio-level force-liquidation
    threshold (0 = off, research switch).
    use_defensive_sleeve: hybrid mode — while the regime proxy's
    month-end close is below its MA250, anchors hold the defensive trio
    equal-weight (live preset since 2026-09-05; sleeve names exempt from
    stop management). Requires 'calendar' or 'weekly' anchors.
    strategy_set: label persisted on the BacktestRun row
    (etf_momentum_rotation | etf_short_rotation).
    """
    bars = load_etf_pool_bars(db, limit=bars_limit)
    if not bars:
        raise ValueError("No ETF bars loaded — run the ETF kline backfill "
                         "first (refresh type etf_klines)")

    # The ONE wiring copy lives in etf_lab.run_preset (architecture review
    # 2026-09-06): this service resolves preset ∪ explicit params — None
    # overrides fall through to the preset, whose values ARE these
    # function's defaults (both sourced from etf_lab.PRESETS).
    from .etf_lab import run_preset
    lab_out = run_preset(
        "hybrid" if use_defensive_sleeve else "mid",
        overrides={
            "top_n": top_n, "buffer_rank": buffer_rank,
            "holding_period": holding_period,
            "windows": momentum_windows, "weights": momentum_weights,
            "vol_window": vol_window, "abs_window": abs_window,
            "use_abs_gate": use_abs_gate, "use_buffer": use_buffer,
            "use_market_gate": use_market_gate,
            "market_ma_window": market_ma_window,
            "use_trend_filter": use_trend_filter,
            "exit_replacement": exit_replacement,
            "rebalance_mode": rebalance_mode,
            "rebalance_anchor": rebalance_anchor,
            "weight_mode": weight_mode,
            "use_target_vol": use_target_vol, "target_vol": target_vol,
            "atr_mult": atr_mult,
            "circuit_breaker_drawdown": circuit_breaker_drawdown,
            "start_date": start_date, "end_date": end_date,
            "initial_capital": initial_capital,
        },
        db=db, bars=bars, bars_limit=bars_limit)
    r = lab_out["result"]

    row = BacktestRun(
        ticker="ETF_ROTATION",
        strategy_set=strategy_set,
        start_date=date.fromisoformat(r["start_date"]),
        end_date=date.fromisoformat(r["end_date"]),
        initial_capital=r["initial_capital"],
        final_equity=r["final_equity"],
        total_return_pct=r["total_return_pct"],
        annual_return_pct=r["annual_return_pct"],
        max_drawdown_pct=r["max_drawdown_pct"],
        sharpe_ratio=r["sharpe_ratio"],
        win_rate_pct=r["win_rate_pct"],
        trade_count=r["trade_count"],
        avg_hold_days=float(holding_period),
        equity_curve_json=json.dumps(r["equity_curve"]),
        trades_json=json.dumps(r["trades"]),
        params_json=json.dumps({
            "config": r["config"],
            "ic_summary": r["ic_summary"],
            "rebalance_log": r["rebalance_log"],
            "benchmark_curve": r["benchmark_curve"],
            "benchmark_total_return_pct": r["benchmark_total_return_pct"],
            "excess_return_pct": r["excess_return_pct"],
            "asset_class_pnl": r["sector_pnl"],
            "avg_turnover_pct": r["avg_turnover_pct"],
            "exit_rules": r["exit_rules"],
        }),
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    return {"run_id": row.id, **{k: v for k, v in r.items()
                                  if k not in ("equity_curve", "trades",
                                               "benchmark_curve",
                                               "rebalance_log")}}


# ── Query layer (for the API) ───────────────────────────────────────────────

def get_latest_scores(db: Session) -> dict:
    """Latest momentum snapshot for the whole pool (full ranking)."""
    latest_date = db.execute(select(func.max(EtfSignal.date))).scalar_one()
    if latest_date is None:
        return {"date": None, "etfs": []}
    rows = db.query(EtfSignal).filter(
        EtfSignal.date == latest_date
    ).order_by(EtfSignal.momentum_rank.asc().nulls_last()).all()
    return {
        "date": str(latest_date),
        "etfs": [
            {
                "ticker": r.ticker,
                "name": r.name,
                "asset_class": r.asset_class,
                "momentum_raw": r.momentum_raw,
                "momentum_score": r.momentum_score,
                "momentum_rank": r.momentum_rank,
                "abs_momentum_pass": r.abs_momentum_pass,
                "is_selected": r.is_selected,
                "weight": r.weight,
                "stop_price": r.stop_price,
                "detail": json.loads(r.detail_json) if r.detail_json else {},
            }
            for r in rows
        ],
    }


def get_latest_portfolio(db: Session) -> dict:
    """Latest target portfolio (selected rows only, cash included)."""
    latest_date = db.execute(select(func.max(EtfSignal.date))).scalar_one()
    if latest_date is None:
        return {"date": None, "holdings": []}
    rows = db.query(EtfSignal).filter(
        EtfSignal.date == latest_date,
        EtfSignal.is_selected == True,  # noqa: E712
    ).order_by(EtfSignal.weight.desc()).all()
    return {
        "date": str(latest_date),
        "holdings": [
            {
                "ticker": r.ticker,
                "name": r.name,
                "asset_class": r.asset_class,
                "momentum_score": r.momentum_score,
                "momentum_rank": r.momentum_rank,
                "weight": r.weight,
                "stop_price": r.stop_price,
            }
            for r in rows
        ],
    }
