"""A-share-aware backtester.

Models the constraints that distinguish A-share trading from US/HK:
  - T+1: a position bought today cannot be sold until the next trading day.
  - 涨跌停 (price limit): when the open hits the limit-up/down band, the
    order is rejected (assumed locked — no fill). 10% for main board, 20%
    for STAR/ChiNext (auto-detected from ticker prefix).
  - 印花税 (stamp duty): 0.05% on sells only (buyer exempt).
  - 佣金 (commission): 0.025% both sides, min ¥5.
  - 滑点 (slippage): 0.1% against the order direction.
  - 最小手数 (lot size): 100 shares.

Signal timing: the ScoreCard produces a signal on day T using close→close
data; execution happens on day T+1's open. This is enforced by reading
`signal[T]` and filling at `open[T+1]` — no look-ahead.

Position sizing: each BUY uses `position_pct` (from the risk gate) of
current cash equity. SELL exits the full position. ATR stop-loss triggers
an emergency exit at the stop price (intraday low breach).

Outputs:
    BacktestResult — total/annualized return, max drawdown, Sharpe, win
    rate, trade list, daily equity curve.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field, asdict
from datetime import date, datetime
from typing import Optional

import numpy as np
import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.chain_models import DailyBar, BacktestRun
from . import indicators, scoring
from .strategies.risk_atr import STOP_LOSS_PCT, TRAIL_ACTIVATION_PCT, TRAIL_PCT

# ── Cost model (A-share defaults) ──────────────────────────────────────────

COMMISSION_RATE = 0.00025   # 0.025% per side
COMMISSION_MIN = 5.0        # ¥5 minimum per trade
STAMP_DUTY_RATE = 0.0005    # 0.05% sells only
SLIPPAGE_RATE = 0.001       # 0.1% against direction
LOT_SIZE = 100              # shares per lot

# Limit-up/down bands by board.
_LIMIT_BAND_MAIN = 0.10     # 60xxxx, 00xxxx, 30xxxx? (30=ChiNext 20%)
_LIMIT_BAND_GEM = 0.20      # 30xxxx ChiNext, 68xxxx STAR
_LIMIT_BAND_BJ = 0.30       # 83/87/92/43 north exchange


def _limit_band(ticker: str) -> float:
    """Price-limit band for a ticker's board."""
    if ticker.startswith("688") or ticker.startswith("30"):
        return _LIMIT_BAND_GEM
    if ticker.startswith(("83", "87", "92", "43", "920")):
        return _LIMIT_BAND_BJ
    return _LIMIT_BAND_MAIN


# ── Result types ───────────────────────────────────────────────────────────

@dataclass
class Trade:
    entry_date: str
    entry_price: float
    exit_date: Optional[str]
    exit_price: Optional[float]
    shares: int
    pnl: float
    pnl_pct: float
    hold_days: int
    exit_reason: str  # "signal" | "stop_loss" | "trailing_stop" | "end"


@dataclass
class BacktestResult:
    ticker: str
    strategy_set: str
    start_date: str
    end_date: str
    initial_capital: float
    final_equity: float
    total_return_pct: float
    annual_return_pct: float
    max_drawdown_pct: float
    sharpe_ratio: float
    win_rate_pct: float
    trade_count: int
    avg_hold_days: float
    equity_curve: list  # [{date, equity}]
    trades: list        # [Trade as dict]
    params: dict


# ── Engine ─────────────────────────────────────────────────────────────────

class Backtester:
    """Event-loop backtester. One ticker, one strategy card, one capital base.

    Usage:
        bt = Backtester()
        result = bt.run(df, signals_df, ticker='600519')
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
        df: pd.DataFrame,
        signals: pd.DataFrame,
        ticker: str,
        initial_capital: float = 1e5,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        strategy_set: str = "v1_default",
    ) -> BacktestResult:
        """Backtest one ticker.

        df:       raw bar DataFrame (will be enriched internally)
        signals:  ScoreCard.score_summary() output (action/position_pct/stop_loss)
        """
        enriched = indicators.enrich(df) if "ma5" not in df.columns else df
        # Merge bars + signals on row index (both aligned to df).
        merged = enriched.copy()
        for col in ("action", "position_pct", "stop_loss_price"):
            if col in signals.columns:
                merged[col] = signals[col].values

        band = _limit_band(ticker)
        dates = merged["date"].values
        opens = merged["open"].values
        highs = merged["high"].values
        lows = merged["low"].values
        closes = merged["close"].values
        prev_closes = pd.Series(closes).shift(1).values
        actions = merged["action"].values if "action" in merged.columns else np.array(["HOLD"] * len(merged), dtype=object)
        # NOTE: stop_loss_price is still merged (the signal panel displays it
        # as the "if-bought-today" reference), but the backtester no longer
        # reads it per-bar. Instead it uses a fixed stop locked at entry
        # (entry_price × (1 - STOP_LOSS_PCT)). See fixed_stop below.
        position_pcts = merged["position_pct"].values if "position_pct" in merged.columns else np.ones(len(merged))

        # Date slice.
        start_idx = 0
        end_idx = len(merged) - 1
        if start_date:
            for i, d in enumerate(dates):
                if str(d) >= start_date:
                    start_idx = i
                    break
        if end_date:
            for i in range(len(dates) - 1, -1, -1):
                if str(dates[i]) <= end_date:
                    end_idx = i
                    break

        # State.
        cash = initial_capital
        shares_held = 0
        entry_price = 0.0
        entry_date = None
        entry_idx = -1  # T+1: can't sell on the buy day
        # Fixed-percentage stop: locked at entry_price × (1 - STOP_LOSS_PCT)
        # when the position opens, held constant until the position closes.
        # (Previous version read a per-bar ATR stop which widened with vol.)
        fixed_stop = 0.0
        # Trailing take-profit state. high_since_entry tracks the highest
        # close since the position opened; once unrealized gain exceeds
        # TRAIL_ACTIVATION_PCT, the effective stop becomes
        # max(fixed_stop, high_since_entry × (1 - TRAIL_PCT)). This locks
        # in profit on extended runs (solves the "高位回吐" problem where
        # lagging SELL signals gave back 30-40% of peak gains).
        high_since_entry = 0.0
        trailing_active = False
        trades: list[Trade] = []
        equity_curve: list[dict] = []
        peak_equity = initial_capital
        max_dd = 0.0
        daily_returns: list[float] = []
        prev_equity = initial_capital

        for i in range(start_idx, end_idx + 1):
            d = str(dates[i])
            o = opens[i]
            h = highs[i]
            l = lows[i]
            c = closes[i]
            pc = prev_closes[i] if not math.isnan(prev_closes[i]) else c
            act = actions[i]
            pos_pct = position_pcts[i] if not math.isnan(position_pcts[i]) else 1.0

            # ── 0. Update trailing-stop state (before the stop check).
            # Track the highest close since entry; once the position is
            # sufficiently in profit, activate the trailing stop.
            if shares_held > 0 and c > high_since_entry:
                high_since_entry = c
            if shares_held > 0 and not trailing_active and entry_price > 0:
                if (high_since_entry - entry_price) / entry_price >= TRAIL_ACTIVATION_PCT:
                    trailing_active = True

            # Effective stop: fixed (entry × 0.9) until trailing activates,
            # then max(fixed, high × (1 - TRAIL_PCT)). The max() ensures
            # the stop never moves DOWN — trailing only ever tightens.
            if shares_held > 0:
                effective_stop = fixed_stop
                if trailing_active:
                    trailing_stop = high_since_entry * (1.0 - TRAIL_PCT)
                    effective_stop = max(effective_stop, trailing_stop)
            else:
                effective_stop = 0.0

            # ── 1. Stop-loss / take-profit check (intraday low breach).
            # Fires when the day's low breaches effective_stop. exit_reason
            # distinguishes fixed stop (initial risk) from trailing (profit
            # lock) so backtests can tell them apart.
            if shares_held > 0 and i > entry_idx and effective_stop > 0 and l <= effective_stop:
                fill = effective_stop
                proceeds, cost = self._sell_cost(shares_held, fill)
                cash += proceeds
                pnl = proceeds - (shares_held * entry_price)
                reason = "trailing_stop" if trailing_active and fill > entry_price * (1 - STOP_LOSS_PCT) else "stop_loss"
                trades.append(Trade(
                    entry_date=str(entry_date), entry_price=entry_price,
                    exit_date=d, exit_price=fill, shares=shares_held,
                    pnl=pnl, pnl_pct=pnl / (shares_held * entry_price) if entry_price else 0,
                    hold_days=i - entry_idx, exit_reason=reason,
                ))
                shares_held = 0
                entry_price = 0.0
                fixed_stop = 0.0
                high_since_entry = 0.0
                trailing_active = False
                entry_date = None
                entry_idx = -1
                # Stop-loss preempts the day's signal.
                fixed_stop = 0.0
                entry_date = None
                entry_idx = -1
                # Stop-loss preempts the day's signal.
                act = "HOLD"

            # ── 2. Signal execution at open (T+1: signal from day i-1 acts on day i).
            # We read the *previous* day's signal for execution. This enforces
            # no same-day reaction. Index shift handled below.
            sig_idx = i - 1
            if sig_idx >= start_idx:
                sig_act = actions[sig_idx]
                sig_pos = position_pcts[sig_idx] if not math.isnan(position_pcts[sig_idx]) else 1.0

                # SELL: exit at open (T+1 after the SELL signal), if not in limit-down.
                limit_down = pc * (1 - band)
                if sig_act == "SELL" and shares_held > 0 and i > entry_idx:
                    if o > limit_down:  # can fill
                        fill = o * (1 - self.slippage_rate)  # slippage against sell
                        proceeds, _ = self._sell_cost(shares_held, fill)
                        cash += proceeds
                        pnl = proceeds - (shares_held * entry_price)
                        trades.append(Trade(
                            entry_date=str(entry_date), entry_price=entry_price,
                            exit_date=d, exit_price=fill, shares=shares_held,
                            pnl=pnl, pnl_pct=pnl / (shares_held * entry_price) if entry_price else 0,
                            hold_days=i - entry_idx, exit_reason="signal",
                        ))
                        shares_held = 0
                        entry_price = 0.0
                        fixed_stop = 0.0
                        high_since_entry = 0.0
                        trailing_active = False
                        entry_date = None
                        entry_idx = -1

                # BUY: enter at open (T+1 after the BUY signal), if not in limit-up.
                limit_up = pc * (1 + band)
                if sig_act == "BUY" and shares_held == 0:
                    if o < limit_up:  # can fill
                        fill = o * (1 + self.slippage_rate)  # slippage against buy
                        target_value = cash * sig_pos
                        lots = int((target_value / fill) // LOT_SIZE)
                        buy_shares = lots * LOT_SIZE
                        if buy_shares > 0:
                            cost_value = buy_shares * fill
                            commission = max(cost_value * self.commission_rate, self.commission_min)
                            cash -= (cost_value + commission)
                            shares_held = buy_shares
                            entry_price = fill
                            # Lock the hard 10% stop at entry. Stays as the
                            # floor; trailing stop (if activated later) only
                            # ever raises it via max().
                            fixed_stop = fill * (1.0 - STOP_LOSS_PCT)
                            # Seed high-water mark at the fill price; the
                            # first bar's close will update it if higher.
                            high_since_entry = fill
                            trailing_active = False
                            entry_date = dates[sig_idx]
                            entry_idx = i

            # ── 3. Mark-to-market equity at close.
            equity = cash + shares_held * c
            equity_curve.append({"date": d, "equity": round(equity, 2)})
            peak_equity = max(peak_equity, equity)
            dd = (peak_equity - equity) / peak_equity if peak_equity > 0 else 0
            max_dd = max(max_dd, dd)
            if prev_equity > 0:
                daily_returns.append((equity - prev_equity) / prev_equity)
            prev_equity = equity

        # ── 4. Force-close any open position at the last bar.
        if shares_held > 0:
            last_close = closes[end_idx]
            proceeds, _ = self._sell_cost(shares_held, last_close)
            cash += proceeds
            pnl = proceeds - (shares_held * entry_price)
            trades.append(Trade(
                entry_date=str(entry_date), entry_price=entry_price,
                exit_date=str(dates[end_idx]), exit_price=last_close,
                shares=shares_held, pnl=pnl,
                pnl_pct=pnl / (shares_held * entry_price) if entry_price else 0,
                hold_days=end_idx - entry_idx, exit_reason="end",
            ))
            shares_held = 0
            # Patch last equity_curve entry to reflect the close.
            equity_curve[-1]["equity"] = round(cash, 2)

        final_equity = cash
        total_return = (final_equity - initial_capital) / initial_capital * 100
        # Annualized: 252 trading days.
        n_days = max(end_idx - start_idx + 1, 1)
        years = n_days / 252
        annual = ((final_equity / initial_capital) ** (1 / years) - 1) * 100 if years > 0 and final_equity > 0 else 0
        # Sharpe (daily returns, annualized × sqrt(252), rf=0).
        if daily_returns:
            dr = np.array(daily_returns)
            std = dr.std(ddof=1) if len(dr) > 1 else 0
            sharpe = (dr.mean() / std * math.sqrt(252)) if std > 0 else 0
        else:
            sharpe = 0
        # Win rate.
        closed = [t for t in trades if t.exit_reason != "end" or True]
        wins = sum(1 for t in trades if t.pnl > 0)
        win_rate = (wins / len(trades) * 100) if trades else 0
        avg_hold = (sum(t.hold_days for t in trades) / len(trades)) if trades else 0

        return BacktestResult(
            ticker=ticker,
            strategy_set=strategy_set,
            start_date=str(dates[start_idx]),
            end_date=str(dates[end_idx]),
            initial_capital=initial_capital,
            final_equity=round(final_equity, 2),
            total_return_pct=round(total_return, 2),
            annual_return_pct=round(annual, 2),
            max_drawdown_pct=round(max_dd * 100, 2),
            sharpe_ratio=round(sharpe, 3),
            win_rate_pct=round(win_rate, 1),
            trade_count=len(trades),
            avg_hold_days=round(avg_hold, 1),
            equity_curve=equity_curve,
            trades=[asdict(t) for t in trades],
            params={
                "commission_rate": self.commission_rate,
                "commission_min": self.commission_min,
                "stamp_duty_rate": self.stamp_duty_rate,
                "slippage_rate": self.slippage_rate,
                "lot_size": LOT_SIZE,
                "limit_band": band,
            },
        )

    def _sell_cost(self, shares: int, price: float) -> tuple[float, float]:
        """Returns (net_proceeds, total_cost) for a sell.

        Sell costs: commission (min ¥5) + stamp duty (0.05%).
        """
        gross = shares * price
        commission = max(gross * self.commission_rate, self.commission_min)
        stamp = gross * self.stamp_duty_rate
        return gross - commission - stamp, commission + stamp


# ── Persistence helpers (called by routers/quant.py) ───────────────────────

def run_and_store(
    db: Session,
    ticker: str,
    strategy_set: str = "v1_default",
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    initial_capital: float = 1e5,
) -> dict:
    """Run a backtest, persist to chain_backtest_runs, return summary dict."""
    from . import signal_service as ss

    df = ss._load_bars_df(db, ticker)
    if df is None or len(df) < 60:
        raise ValueError(f"insufficient bars for {ticker} (need ≥60, got {len(df) if df is not None else 0})")

    enriched = indicators.enrich(df)
    card = scoring.get_card(strategy_set)
    signals = card.score_summary(enriched)

    bt = Backtester()
    result = bt.run(
        df, signals, ticker=ticker,
        initial_capital=initial_capital,
        start_date=str(start_date) if start_date else None,
        end_date=str(end_date) if end_date else None,
        strategy_set=strategy_set,
    )

    row = BacktestRun(
        ticker=ticker,
        strategy_set=strategy_set,
        start_date=date.fromisoformat(result.start_date),
        end_date=date.fromisoformat(result.end_date),
        initial_capital=result.initial_capital,
        final_equity=result.final_equity,
        total_return_pct=result.total_return_pct,
        annual_return_pct=result.annual_return_pct,
        max_drawdown_pct=result.max_drawdown_pct,
        sharpe_ratio=result.sharpe_ratio,
        win_rate_pct=result.win_rate_pct,
        trade_count=result.trade_count,
        avg_hold_days=result.avg_hold_days,
        equity_curve_json=json.dumps(result.equity_curve),
        trades_json=json.dumps(result.trades),
        params_json=json.dumps(result.params),
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    return {
        "run_id": row.id,
        "ticker": result.ticker,
        "start_date": result.start_date,
        "end_date": result.end_date,
        "initial_capital": result.initial_capital,
        "final_equity": result.final_equity,
        "total_return_pct": result.total_return_pct,
        "annual_return_pct": result.annual_return_pct,
        "max_drawdown_pct": result.max_drawdown_pct,
        "sharpe_ratio": result.sharpe_ratio,
        "win_rate_pct": result.win_rate_pct,
        "trade_count": result.trade_count,
        "avg_hold_days": result.avg_hold_days,
        "params": result.params,
        # Omit heavy equity_curve / trades from the summary; fetch via GET /backtest/{id}.
    }


def get_run(db: Session, run_id: int) -> Optional[dict]:
    """Fetch a stored backtest run with equity curve + trades."""
    row = db.get(BacktestRun, run_id)
    if row is None:
        return None
    return {
        "run_id": row.id,
        "ticker": row.ticker,
        "strategy_set": row.strategy_set,
        "start_date": str(row.start_date),
        "end_date": str(row.end_date),
        "initial_capital": row.initial_capital,
        "final_equity": row.final_equity,
        "total_return_pct": row.total_return_pct,
        "annual_return_pct": row.annual_return_pct,
        "max_drawdown_pct": row.max_drawdown_pct,
        "sharpe_ratio": row.sharpe_ratio,
        "win_rate_pct": row.win_rate_pct,
        "trade_count": row.trade_count,
        "avg_hold_days": row.avg_hold_days,
        "equity_curve": json.loads(row.equity_curve_json) if row.equity_curve_json else [],
        "trades": json.loads(row.trades_json) if row.trades_json else [],
        "params": json.loads(row.params_json) if row.params_json else {},
        "created_at": str(row.created_at),
    }
