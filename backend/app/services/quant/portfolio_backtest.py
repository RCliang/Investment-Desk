"""Portfolio-level backtester for the multi-factor model.

Unlike the single-stock Backtester (which trades one ticker at a time),
this backtester manages a PORTFOLIO of N stocks selected by the factor
model, rebalanced every `holding_period` days.

Key differences from single-stock backtest:
  - Holds multiple positions simultaneously (equal-weight or cap-weighted)
  - Rebalances on fixed schedule (every 20 trading days), not on signals
  - Tracks portfolio-level metrics: total return, Sharpe, max drawdown,
    turnover, hit rate (fraction of selected stocks that beat benchmark)

A-share cost model (same as single-stock backtester):
  - Commission: 0.025% both sides, min ¥5
  - Stamp duty: 0.05% sells only
  - Slippage: 0.1% against direction
  - No T+1 enforcement at portfolio level (we rebalance every 20 days,
    so all positions are already T+1 eligible)
"""

from __future__ import annotations

import json
import math
import logging
from dataclasses import dataclass, field, asdict
from datetime import date, datetime
from typing import Optional

import numpy as np
import pandas as pd
from sqlalchemy.orm import Session

from .factor_model import MultiFactorEngine, build_close_panel
from .factor_model import HOLDING_PERIOD, TOP_N, MAX_WEIGHT

log = logging.getLogger(__name__)

COMMISSION_RATE = 0.00025
COMMISSION_MIN = 5.0
STAMP_DUTY_RATE = 0.0005
SLIPPAGE_RATE = 0.001


@dataclass
class PortfolioResult:
    """Portfolio backtest result."""
    strategy_set: str
    start_date: str
    end_date: str
    initial_capital: float
    final_equity: float
    total_return_pct: float
    annual_return_pct: float
    max_drawdown_pct: float
    sharpe_ratio: float
    rebalance_count: int
    avg_turnover_pct: float
    hit_rate_pct: float  # fraction of holdings that beat equal-weight benchmark
    equity_curve: list  # [{date, equity}]
    rebalance_log: list  # [{date, holdings: [{ticker, weight}], turnover}]
    ic_summary: dict  # factor IC stats at end of period
    config: dict


class PortfolioBacktester:
    """Backtest a multi-factor portfolio strategy.

    Workflow:
      1. Run MultiFactorEngine to get rebalance portfolios
      2. For each rebalance period, hold the selected stocks
      3. Track daily portfolio value using actual closes
      4. Apply transaction costs at each rebalance
      5. Compute portfolio-level performance metrics
    """

    def __init__(
        self,
        commission_rate: float = COMMISSION_RATE,
        commission_min: float = COMMISSION_MIN,
        stamp_duty_rate: float = STAMP_DUTY_RATE,
        slippage_rate: float = SLIPPAGE_RATE,
    ):
        self.commission_rate = commission_rate
        self.commission_min = commission_min
        self.stamp_duty_rate = stamp_duty_rate
        self.slippage_rate = slippage_rate

    def run(
        self,
        bars: dict[str, pd.DataFrame],
        engine: MultiFactorEngine,
        initial_capital: float = 1e6,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        strategy_set: str = "multi_factor_trend",
    ) -> PortfolioResult:
        """Run a portfolio backtest.

        bars:   {ticker: DataFrame} — must include date, close columns.
        engine: configured MultiFactorEngine (factors, holding_period, etc.)
        """
        # Step 1: Run the factor model.
        model_result = engine.run(bars, start_date, end_date)
        portfolios = model_result["portfolios"]
        composite = model_result["composite"]

        # Step 2: Build close-price panel for daily NAV tracking.
        close_panel = build_close_panel(bars)
        if start_date:
            close_panel = close_panel[close_panel.index >= start_date]
        if end_date:
            close_panel = close_panel[close_panel.index <= end_date]

        all_dates = list(close_panel.index)
        if len(all_dates) < engine.holding_period + 5:
            raise ValueError(
                f"Insufficient data: {len(all_dates)} bars, "
                f"need ≥{engine.holding_period + 5}"
            )

        # Step 3: Simulate portfolio over time.
        cash = initial_capital
        holdings: dict[str, float] = {}  # ticker → shares
        equity_curve: list[dict] = []
        rebalance_log: list[dict] = []
        peak_equity = initial_capital
        max_dd = 0.0
        daily_returns: list[float] = []
        prev_equity = initial_capital
        turnovers: list[float] = []
        rebalance_count = 0

        # Sort rebalance dates.
        rebalance_dates = sorted(portfolios.keys())

        for i, dt in enumerate(all_dates):
            # Check if this is a rebalance date.
            if dt in portfolios:
                target_weights = portfolios[dt]
                # Compute current equity for rebalancing.
                current_prices = close_panel.loc[dt]
                position_value = sum(
                    shares * current_prices[t]
                    for t, shares in holdings.items()
                    if t in current_prices.index and pd.notna(current_prices[t])
                )
                total_equity = cash + position_value

                # Liquidate positions not in new portfolio.
                new_holdings: dict[str, float] = {}
                old_value = 0.0
                for t, shares in holdings.items():
                    if t not in current_prices.index or pd.isna(current_prices[t]):
                        new_holdings[t] = shares  # can't trade (suspended), keep
                        continue
                    price = float(current_prices[t])
                    if t not in target_weights:
                        # Sell all.
                        fill = price * (1 - self.slippage_rate)
                        gross = shares * fill
                        commission = max(gross * self.commission_rate, self.commission_min)
                        stamp = gross * self.stamp_duty_rate
                        cash += gross - commission - stamp
                        old_value += gross
                    else:
                        new_holdings[t] = shares
                        old_value += shares * price

                # Buy new positions.
                for t, w in target_weights.items():
                    if t not in current_prices.index or pd.isna(current_prices[t]):
                        continue
                    price = float(current_prices[t])
                    target_value = total_equity * w
                    current_shares = new_holdings.get(t, 0)
                    current_value = current_shares * price
                    diff = target_value - current_value
                    if abs(diff) < 100:  # skip negligible trades
                        continue
                    if diff > 0:
                        # Buy
                        fill = price * (1 + self.slippage_rate)
                        buy_shares = int(diff / fill // 100) * 100
                        if buy_shares > 0:
                            cost = buy_shares * fill
                            commission = max(cost * self.commission_rate, self.commission_min)
                            cash -= (cost + commission)
                            new_holdings[t] = current_shares + buy_shares
                    elif diff < 0:
                        # Sell excess
                        fill = price * (1 - self.slippage_rate)
                        sell_shares = min(int(-diff / fill // 100) * 100, current_shares)
                        if sell_shares > 0:
                            gross = sell_shares * fill
                            commission = max(gross * self.commission_rate, self.commission_min)
                            stamp = gross * self.stamp_duty_rate
                            cash += gross - commission - stamp
                            new_holdings[t] = current_shares - sell_shares

                # Compute turnover.
                new_value = sum(
                    s * float(current_prices[t])
                    for t, s in new_holdings.items()
                    if t in current_prices.index and pd.notna(current_prices[t])
                )
                turnover = abs(new_value - old_value) / total_equity if total_equity > 0 else 0
                turnovers.append(turnover)

                holdings = {t: s for t, s in new_holdings.items() if s > 0}
                rebalance_count += 1
                rebalance_log.append({
                    "date": dt,
                    "holdings": [
                        {"ticker": t, "weight": round(w, 4)}
                        for t, w in target_weights.items()
                    ],
                    "turnover_pct": round(turnover * 100, 2),
                    "n_stocks": len(target_weights),
                })

            # Step 4: Daily mark-to-market.
            if dt in close_panel.index:
                prices = close_panel.loc[dt]
                position_value = sum(
                    shares * float(prices[t])
                    for t, shares in holdings.items()
                    if t in prices.index and pd.notna(prices[t])
                )
                equity = cash + position_value
            else:
                equity = prev_equity
            # Guard against NaN (suspended stocks with no valid price).
            if not np.isfinite(equity):
                equity = prev_equity

            equity_curve.append({"date": dt, "equity": round(equity, 2)})
            peak_equity = max(peak_equity, equity)
            dd = (peak_equity - equity) / peak_equity if peak_equity > 0 else 0
            max_dd = max(max_dd, dd)
            if prev_equity > 0:
                daily_returns.append((equity - prev_equity) / prev_equity)
            prev_equity = equity

        # Step 5: Compute metrics.
        final_equity = equity_curve[-1]["equity"] if equity_curve else initial_capital
        total_return = (final_equity - initial_capital) / initial_capital * 100
        n_days = len(all_dates)
        years = n_days / 252
        annual = (
            ((final_equity / initial_capital) ** (1 / years) - 1) * 100
            if years > 0 and final_equity > 0 else 0
        )
        if daily_returns:
            dr = np.array(daily_returns)
            std = dr.std(ddof=1) if len(dr) > 1 else 0
            sharpe = (dr.mean() / std * math.sqrt(252)) if std > 0 else 0
        else:
            sharpe = 0
        avg_turnover = (sum(turnovers) / len(turnovers) * 100) if turnovers else 0

        # Hit rate: fraction of rebalance stocks that were profitable
        # over the holding period (simplified: check if they appear in
        # the next rebalance or gained value).
        hit_rate = self._compute_hit_rate(rebalance_log, close_panel, engine.holding_period)

        return PortfolioResult(
            strategy_set=strategy_set,
            start_date=str(all_dates[0]),
            end_date=str(all_dates[-1]),
            initial_capital=initial_capital,
            final_equity=round(final_equity, 2),
            total_return_pct=round(total_return, 2),
            annual_return_pct=round(annual, 2),
            max_drawdown_pct=round(max_dd * 100, 2),
            sharpe_ratio=round(sharpe, 3),
            rebalance_count=rebalance_count,
            avg_turnover_pct=round(avg_turnover, 2),
            hit_rate_pct=round(hit_rate, 1),
            equity_curve=equity_curve,
            rebalance_log=rebalance_log,
            ic_summary=model_result["ic_summary"],
            config=model_result["config"],
        )

    def _compute_hit_rate(
        self,
        rebalance_log: list[dict],
        close_panel: pd.DataFrame,
        holding_period: int,
    ) -> float:
        """Compute what fraction of selected stocks gained over holding period."""
        if not rebalance_log or len(rebalance_log) < 2:
            return 0.0
        hits = 0
        total = 0
        for i, rb in enumerate(rebalance_log[:-1]):
            dt = rb["date"]
            tickers = [h["ticker"] for h in rb["holdings"]]
            # Find the close `holding_period` days later.
            idx = close_panel.index.get_loc(dt)
            future_idx = idx + holding_period
            if future_idx >= len(close_panel):
                continue
            future_dt = close_panel.index[future_idx]
            for t in tickers:
                if t not in close_panel.columns:
                    continue
                p0 = close_panel.loc[dt, t]
                p1 = close_panel.loc[future_dt, t]
                if pd.notna(p0) and pd.notna(p1) and p0 > 0:
                    if p1 > p0:
                        hits += 1
                    total += 1
        return (hits / total * 100) if total > 0 else 0


def run_and_store(
    db: Session,
    strategy_set: str = "multi_factor_trend",
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    initial_capital: float = 1e6,
    holding_period: int = HOLDING_PERIOD,
    top_n: int = TOP_N,
    max_weight: float = MAX_WEIGHT,
) -> dict:
    """Run a multi-factor portfolio backtest, store result, return summary.

    Loads all tickers' bars from DB, runs the factor model + portfolio
    backtester, stores the result in chain_backtest_runs (using ticker
    = 'PORTFOLIO' to distinguish from single-stock runs).
    """
    from .signal_service import _load_bars_df
    from app.models.chain_models import BacktestRun

    # Load all tickers.
    tickers = [r[0] for r in db.execute(
        "SELECT DISTINCT ticker FROM chain_daily_bars ORDER BY ticker"
    ).all()] if False else []  # SQLAlchemy select

    from sqlalchemy import select
    from app.models.chain_models import DailyBar
    tickers = [r[0] for r in db.execute(
        select(DailyBar.ticker).distinct().order_by(DailyBar.ticker.asc())
    ).all()]

    log.info("Loading bars for %d tickers...", len(tickers))
    bars = {}
    for t in tickers:
        df = _load_bars_df(db, t, limit=600)  # ~2.5 years
        if df is not None and len(df) >= 80:
            bars[t] = df

    log.info("Running multi-factor engine on %d tickers...", len(bars))
    engine = MultiFactorEngine(
        holding_period=holding_period,
        top_n=top_n,
        max_weight=max_weight,
    )
    bt = PortfolioBacktester()
    result = bt.run(
        bars, engine,
        initial_capital=initial_capital,
        start_date=str(start_date) if start_date else None,
        end_date=str(end_date) if end_date else None,
        strategy_set=strategy_set,
    )

    # Store (using ticker='PORTFOLIO' sentinel).
    row = BacktestRun(
        ticker="PORTFOLIO",
        strategy_set=strategy_set,
        start_date=date.fromisoformat(result.start_date),
        end_date=date.fromisoformat(result.end_date),
        initial_capital=result.initial_capital,
        final_equity=result.final_equity,
        total_return_pct=result.total_return_pct,
        annual_return_pct=result.annual_return_pct,
        max_drawdown_pct=result.max_drawdown_pct,
        sharpe_ratio=result.sharpe_ratio,
        win_rate_pct=result.hit_rate_pct,
        trade_count=result.rebalance_count,
        avg_hold_days=float(holding_period),
        equity_curve_json=json.dumps(result.equity_curve),
        trades_json=json.dumps(result.rebalance_log),
        params_json=json.dumps({
            **result.config,
            "ic_summary": result.ic_summary,
        }),
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    return {
        "run_id": row.id,
        "ticker": "PORTFOLIO",
        "strategy_set": strategy_set,
        "start_date": result.start_date,
        "end_date": result.end_date,
        "initial_capital": result.initial_capital,
        "final_equity": result.final_equity,
        "total_return_pct": result.total_return_pct,
        "annual_return_pct": result.annual_return_pct,
        "max_drawdown_pct": result.max_drawdown_pct,
        "sharpe_ratio": result.sharpe_ratio,
        "rebalance_count": result.rebalance_count,
        "avg_turnover_pct": result.avg_turnover_pct,
        "hit_rate_pct": result.hit_rate_pct,
        "ic_summary": result.ic_summary,
        "config": result.config,
    }
