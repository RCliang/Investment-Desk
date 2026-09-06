"""ETF rotation research lab — the single home of strategy presets and the
engine+backtester wiring (architecture review 2026-09-06, candidate 1).

Before this module the wiring ("build EtfRotationEngine + RotationBacktester
with ETF costs, market-gate tickers, defensive replacement, regime sleeve")
was copied in five places (etf_signal_service + four research scripts), and
preset dicts (SHORT_BASE / MID_BASE / BASELINE) drifted from the live
constants. Now:

  PRESETS       the canonical configurations ("mid" = live engine sans
                sleeve, "hybrid" = live scan behavior since 2026-09-05,
                "short" = the §9.5 weekly preset at its champion cell).
                etf_signal_service imports its defaults from here, so the
                live config and every research run share one source.
  run_preset    backtest a preset with sparse overrides. The ONE copy of
                the engine+backtester wiring. bars/membership injectable
                (grid loops load once; tests inject synthetic universes);
                falls back to loading the pool from `db`.
  slice_metrics  the ONE metrics-from-curve implementation (same
                convention as the validation harness: √252 Sharpe on the
                sliced equity curve).

Interface = those three exports. Grid loops, walk-forward protocols and
plots are usage patterns, not reused behaviour — they stay in scripts as
thin shells over run_preset.
"""

from __future__ import annotations

import math
from typing import Optional

import numpy as np
import pandas as pd
from sqlalchemy.orm import Session

from . import etf_pool
from .etf_rotation import EtfRotationEngine
from .rotation_backtest import RotationBacktester
from .signal_service import _load_bars_df

# ── Live constants (single source; etf_signal_service re-imports) ──────────

# ETF cost model: no stamp duty (A-share ETFs are exempt), 万1 commission,
# 0.1% slippage (conservative for top-liquidity ETFs).
ETF_COMMISSION_RATE = 0.0001
ETF_COMMISSION_MIN = 5.0
ETF_STAMP_DUTY_RATE = 0.0
ETF_SLIPPAGE_RATE = 0.001
# Hybrid regime sleeve (docs §十, go-live 2026-09-05): while 510300's
# month-END close sits below its MA250, monthly anchors hold the defensive
# trio equal-weight, exempt from stop management.
DEFENSIVE_SLEEVE = {"518880", "511010", "510880"}   # gold / treasury / dividend
REGIME_TICKER = "510300"
REGIME_MA_WINDOW = 250

_PRESET_KEYS = (
    "top_n", "buffer_rank", "holding_period",
    "windows", "weights", "vol_window", "abs_window",
    "use_abs_gate", "use_buffer",
    "use_market_gate", "market_ma_window", "use_trend_filter",
    "exit_replacement", "rebalance_mode", "rebalance_anchor",
    "weight_mode", "use_target_vol", "target_vol",
    "atr_mult", "use_defensive_sleeve",
)

_MID = dict(
    # Momentum: 3m/6m/12m risk-adjusted, the 12m leg dominant (grid-search
    # TOP1 cell, docs/etf-rotation-grid-search-plan.md).
    windows=(60, 120, 250), weights=(0.15, 0.15, 0.7),
    vol_window=20, abs_window=180,
    use_abs_gate=True, use_buffer=True,
    use_market_gate=False, market_ma_window=200, use_trend_filter=False,
    exit_replacement=True,
    rebalance_mode="fixed", rebalance_anchor="calendar",
    weight_mode="equal", use_target_vol=True, target_vol=0.12,
    # Exit rules: loose 4×ATR14 disaster brake + 3% breakdown buffer;
    # momentum/absolute gates own the exits.
    top_n=2, buffer_rank=3, holding_period=20, atr_mult=4.0,
    use_defensive_sleeve=False,
)

PRESETS: dict[str, dict] = {
    # The mid-term engine without the regime sleeve — the research baseline
    # the live scan ran before 2026-09-05.
    "mid": _MID,
    # The LIVE behavior since 2026-09-05: mid-term + defensive sleeve
    # (validated: bear +27.5%/dd 4.9% vs mid +11.6%/13.0%; full window
    # +149.4% vs +107.7% — docs §十).
    "hybrid": {**_MID, "use_defensive_sleeve": True},
    # The weekly short-rotation preset (docs §9) at its §9.5 champion cell
    # (top2 / no buffer / 3×ATR). Kept for research — walk-forward showed
    # it does NOT replace the mid-term engine (§9.5 结论).
    "short": dict(
        windows=(20, 60), weights=(0.6, 0.4),
        vol_window=20, abs_window=60,
        use_abs_gate=True, use_buffer=True,
        use_market_gate=True, market_ma_window=250, use_trend_filter=True,
        exit_replacement=True,
        rebalance_mode="fixed", rebalance_anchor="weekly",
        weight_mode="equal", use_target_vol=True, target_vol=0.12,
        top_n=2, buffer_rank=0, holding_period=5, atr_mult=3.0,
        use_defensive_sleeve=False,
    ),
}


def _resolve(name: str, overrides: Optional[dict]) -> dict:
    if name not in PRESETS:
        raise ValueError(
            f"unknown preset {name!r} — available: {sorted(PRESETS)}")
    cfg = dict(PRESETS[name])
    if overrides:
        unknown = set(overrides) - set(_PRESET_KEYS) - {
                "start_date", "end_date", "initial_capital",
                "circuit_breaker_drawdown", "breakdown_buffer"}
        if unknown:
            raise ValueError(f"unknown override keys: {sorted(unknown)}")
        cfg.update({k: v for k, v in overrides.items() if v is not None})
    return cfg


def _load_pool_bars(db: Session, limit: int) -> dict[str, pd.DataFrame]:
    bars: dict[str, pd.DataFrame] = {}
    for t in etf_pool.get_all_tickers():
        df = _load_bars_df(db, t, limit=limit)
        if df is None or len(df) < 140:
            continue
        bars[t] = df
    return bars


def run_preset(
    name: str,
    overrides: Optional[dict] = None,
    *,
    db: Optional[Session] = None,
    bars: Optional[dict[str, pd.DataFrame]] = None,
    membership: Optional[dict[str, list[str]]] = None,
    bars_limit: int = 2600,
) -> dict:
    """Backtest one preset. Returns {"cfg": resolved, "result": backtester
    result dict (equity_curve, trades, metrics, ...)}.

    bars/membership injectable: grid loops load once and reuse; tests feed
    synthetic universes. Without bars, loads the pool via `db` (opens its
    own session when omitted — cloud PG round-trips make repeated loads
    expensive).
    """
    cfg = _resolve(name, overrides)

    if bars is None:
        if db is None:
            from app.db import SessionLocal
            db = SessionLocal()
            try:
                bars = _load_pool_bars(db, bars_limit)
            finally:
                db.close()
        else:
            bars = _load_pool_bars(db, bars_limit)
    if membership is None:
        membership = etf_pool.get_membership()
    if etf_pool.get_cash_ticker() not in bars:
        raise ValueError(
            f"cash ETF {etf_pool.get_cash_ticker()} missing from bars — "
            f"pool/data mismatch (run the ETF kline backfill first)")

    classes = etf_pool.get_asset_classes()
    equity_like = {t for t, c in classes.items() if c in ("宽基", "行业")}
    defensive = {t for t, c in classes.items() if c == "防守"}
    sleeve = DEFENSIVE_SLEEVE if cfg["use_defensive_sleeve"] else None

    engine = EtfRotationEngine(
        cash_ticker=etf_pool.get_cash_ticker(),
        top_n=cfg["top_n"], buffer_rank=cfg["buffer_rank"],
        holding_period=cfg["holding_period"],
        windows=tuple(cfg["windows"]), weights=tuple(cfg["weights"]),
        vol_window=cfg["vol_window"], abs_window=cfg["abs_window"],
        use_abs_gate=cfg["use_abs_gate"], use_buffer=cfg["use_buffer"],
        use_market_gate=cfg["use_market_gate"],
        market_ma_window=cfg["market_ma_window"],
        market_gate_tickers=equity_like,
        use_trend_filter=cfg["use_trend_filter"],
        replacement_tickers=defensive if cfg["exit_replacement"] else None,
        rebalance_mode=cfg["rebalance_mode"],
        rebalance_anchor=cfg["rebalance_anchor"],
        weight_mode=cfg["weight_mode"],
        use_target_vol=cfg["use_target_vol"], target_vol=cfg["target_vol"],
        defensive_sleeve=sleeve,
        regime_ticker=REGIME_TICKER, regime_ma_window=REGIME_MA_WINDOW)
    bt = RotationBacktester(
        commission_rate=ETF_COMMISSION_RATE,
        commission_min=ETF_COMMISSION_MIN,
        stamp_duty_rate=ETF_STAMP_DUTY_RATE,
        slippage_rate=ETF_SLIPPAGE_RATE,
        stop_mode="atr", atr_mult=cfg["atr_mult"],
        breakdown_buffer=cfg.get("breakdown_buffer", 0.03),
        circuit_breaker_drawdown=cfg.get("circuit_breaker_drawdown", 0.0),
        cash_tickers={etf_pool.get_cash_ticker()} | (sleeve or set()),
        replacement_fn=engine.pick_replacement if cfg["exit_replacement"]
        else None)
    out = bt.run(
        bars, membership, engine,
        initial_capital=overrides.get("initial_capital", 1e6)
        if overrides else 1e6,
        start_date=str(overrides["start_date"])
        if overrides and overrides.get("start_date") else None,
        end_date=str(overrides["end_date"])
        if overrides and overrides.get("end_date") else None,
    )
    return {"cfg": cfg, "result": out["result"]}


def slice_metrics(
    curve: list[dict],
    lo: str,
    hi: str,
    rebalance_log: Optional[list[dict]] = None,
) -> Optional[dict]:
    """Metrics from an equity-curve slice — the ONE canonical version
    (validation-harness convention: annualized by trading-day count, Sharpe
    = mean/std × √252 on sliced daily returns)."""
    pts = [p for p in curve if lo <= p["date"] <= hi]
    eq = np.array([p["equity"] for p in pts], dtype=float)
    if len(pts) < 40 or eq[0] <= 0:
        return None
    total = eq[-1] / eq[0] - 1.0
    years = len(pts) / 252.0
    annual = (eq[-1] / eq[0]) ** (1.0 / years) - 1.0 if years > 0 else 0.0
    peak = np.maximum.accumulate(eq)
    dd = float(np.max((peak - eq) / peak)) if len(eq) else 0.0
    rets = np.diff(eq) / eq[:-1]
    std = rets.std(ddof=1) if len(rets) > 1 else 0.0
    sharpe = float(rets.mean() / std * math.sqrt(252)) if std > 0 else 0.0
    calmar = annual / dd if dd > 1e-9 else 0.0
    to = 0.0
    if rebalance_log is not None:
        xs = [r["turnover_pct"] for r in rebalance_log
              if lo <= r["date"] <= hi]
        to = float(np.mean(xs)) if xs else 0.0
    return {
        "total_pct": round(total * 100, 2),
        "annual_pct": round(annual * 100, 2),
        "max_dd_pct": round(dd * 100, 2),
        "sharpe": round(sharpe, 3),
        "calmar": round(calmar, 3),
        "avg_turnover_pct": round(to, 2),
    }
