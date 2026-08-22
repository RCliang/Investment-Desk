"""Backtester for the sector-rotation strategy (Top-K sectors × Top-N stocks).

Simulation conventions (mirrors portfolio_backtest where applicable):
  - Rebalance every `holding_period` days at the rebalance date's close,
    with commission (0.025%, min ¥5), stamp duty (0.05% sells) and 0.1%
    slippage. Fills rounded to 100-share lots.
  - Daily exits between rebalances, evaluated on closes:
      * MA-breakdown SELL: signal on day T-1 close → exit at day T close
        (T+1 execution parity with the single-stock backtester).
      * Hard stop: entry × (1 - 10%), locked at entry.
      * Trailing take-profit: activates at +20% unrealized (close basis),
        then stop = max(hard stop, highest close × (1 - 8%)).
    A stock stopped/broken-down on a rebalance date is not re-bought the
    same day (cooldown), so stop logic keeps precedence over the target.
  - T+1: a position bought at close of day i can only be exited from i+1.

Benchmark: pool equal-weight index (daily-rebalanced mean of member
returns, no costs) — the hurdle the rotation must beat to be worth its
complexity.
"""

from __future__ import annotations

import json
import logging
import math
from dataclasses import dataclass, asdict
from datetime import date
from typing import Optional

import numpy as np
import pandas as pd
from sqlalchemy.orm import Session

from .sector_rotation import (
    SectorRotationEngine, build_breakdown_panel, build_atr_panel,
    TOP_K_SECTORS, TOP_N_PER_SECTOR, MAX_WEIGHT,
)
from .factor_model import HOLDING_PERIOD, build_close_panel
from .strategies.risk_atr import STOP_LOSS_PCT, TRAIL_ACTIVATION_PCT, TRAIL_PCT

log = logging.getLogger(__name__)

COMMISSION_RATE = 0.00025
COMMISSION_MIN = 5.0
STAMP_DUTY_RATE = 0.0005
SLIPPAGE_RATE = 0.001
LOT_SIZE = 100


@dataclass
class RotationTrade:
    ticker: str
    sector: str
    entry_date: str
    entry_price: float
    exit_date: Optional[str]
    exit_price: Optional[float]
    shares: int
    pnl: float
    pnl_pct: float
    hold_days: int
    exit_reason: str  # rebalance | breakdown | stop_loss | trailing_stop | end


class RotationBacktester:
    """Portfolio backtester with per-position trend exits.

    Exit-rule knobs (v1 defaults reproduce the original fixed rules):
      stop_mode:        "fixed" = entry × (1 - 10%) | "atr" = entry − mult×ATR14
      atr_mult:         ATR multiplier for stop distance (default 2.0)
      breakdown_buffer: fraction below MA20 that still counts as noise
                        (0.0 = v1 exact-breakdown; 0.03 = 3% buffer)
    """

    def __init__(
        self,
        commission_rate: float = COMMISSION_RATE,
        commission_min: float = COMMISSION_MIN,
        stamp_duty_rate: float = STAMP_DUTY_RATE,
        slippage_rate: float = SLIPPAGE_RATE,
        stop_mode: str = "fixed",
        atr_mult: float = 2.0,
        breakdown_buffer: float = 0.0,
    ):
        self.commission_rate = commission_rate
        self.commission_min = commission_min
        self.stamp_duty_rate = stamp_duty_rate
        self.slippage_rate = slippage_rate
        if stop_mode not in ("fixed", "atr"):
            raise ValueError(f"unknown stop_mode: {stop_mode}")
        self.stop_mode = stop_mode
        self.atr_mult = atr_mult
        self.breakdown_buffer = breakdown_buffer

    def _entry_stop(
        self,
        fill: float,
        dt,
        ticker: str,
        atr_panel,
    ) -> float:
        """Hard-stop level locked at entry.

        "atr": entry − atr_mult × ATR14(entry date) — volatility-scaled, so
        calm names get tighter stops and high-vol semis don't get shaken
        out by their own noise. Falls back to the fixed rule when ATR is
        not yet formed (warm-up / missing bars).
        """
        if self.stop_mode == "atr" and atr_panel is not None:
            try:
                atr_val = atr_panel.loc[dt, ticker]
            except KeyError:
                atr_val = None
            if atr_val is not None and pd.notna(atr_val) and atr_val > 0:
                return fill - self.atr_mult * float(atr_val)
        return fill * (1.0 - STOP_LOSS_PCT)

    def _sell(self, shares: int, price: float) -> float:
        gross = shares * price
        commission = max(gross * self.commission_rate, self.commission_min)
        stamp = gross * self.stamp_duty_rate
        return gross - commission - stamp

    def _buy_cost(self, shares: int, price: float) -> float:
        cost = shares * price
        return cost + max(cost * self.commission_rate, self.commission_min)

    def run(
        self,
        bars: dict[str, pd.DataFrame],
        membership: dict[str, list[str]],
        engine: SectorRotationEngine,
        initial_capital: float = 1e6,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> dict:
        model = engine.run(bars, start_date, end_date)
        portfolios = model["portfolios"]

        close_panel = build_close_panel(bars)
        if start_date:
            close_panel = close_panel[close_panel.index >= start_date]
        if end_date:
            close_panel = close_panel[close_panel.index <= end_date]
        breakdown = build_breakdown_panel(
            bars, buffer=self.breakdown_buffer).reindex(close_panel.index)
        atr_panel = build_atr_panel(bars) if self.stop_mode == "atr" else None

        all_dates = list(close_panel.index)
        if len(all_dates) < engine.holding_period + 5:
            raise ValueError(
                f"Insufficient data: {len(all_dates)} bars, "
                f"need ≥{engine.holding_period + 5}"
            )

        cash = initial_capital
        # position state: ticker → dict(shares, entry_price, entry_idx,
        # high_close, trailing, fixed_stop, entry_date, sector)
        positions: dict[str, dict] = {}
        trades: list[RotationTrade] = []
        equity_curve: list[dict] = []
        rebalance_log: list[dict] = []
        peak = initial_capital
        max_dd = 0.0
        prev_equity = initial_capital
        daily_returns: list[float] = []
        turnovers: list[float] = []

        def sector_of(ticker: str) -> str:
            return membership.get(ticker, ["?"])[0]

        for i, dt in enumerate(all_dates):
            prices = close_panel.loc[dt]

            def price_of(t: str) -> Optional[float]:
                if t in prices.index and pd.notna(prices[t]) and prices[t] > 0:
                    return float(prices[t])
                return None

            # ── 1. Per-position exits (close basis). ──────────────────────
            cooldown: set[str] = set()
            for t, pos in list(positions.items()):
                if i <= pos["entry_idx"]:  # T+1
                    continue
                c = price_of(t)
                if c is None:
                    continue
                pos["high_close"] = max(pos["high_close"], c)
                if not pos["trailing"]:
                    gain = (pos["high_close"] - pos["entry_price"]) / pos["entry_price"]
                    if gain >= TRAIL_ACTIVATION_PCT:
                        pos["trailing"] = True
                eff_stop = pos["fixed_stop"]
                if pos["trailing"]:
                    eff_stop = max(eff_stop, pos["high_close"] * (1.0 - TRAIL_PCT))

                reason = None
                if c <= eff_stop:
                    reason = ("trailing_stop" if pos["trailing"]
                              and eff_stop > pos["fixed_stop"] else "stop_loss")
                elif i > 0 and dt in breakdown.index:
                    prev_row = breakdown.loc[all_dates[i - 1]] \
                        if all_dates[i - 1] in breakdown.index else None
                    if prev_row is not None and bool(prev_row.get(t, False)):
                        reason = "breakdown"

                if reason:
                    fill = c * (1 - self.slippage_rate)
                    proceeds = self._sell(pos["shares"], fill)
                    cash += proceeds
                    cost_basis = pos["shares"] * pos["entry_price"]
                    trades.append(RotationTrade(
                        ticker=t, sector=sector_of(t),
                        entry_date=pos["entry_date"], entry_price=pos["entry_price"],
                        exit_date=dt, exit_price=round(fill, 4),
                        shares=pos["shares"], pnl=round(proceeds - cost_basis, 2),
                        pnl_pct=round((proceeds - cost_basis) / cost_basis, 4)
                        if cost_basis else 0.0,
                        hold_days=i - pos["entry_idx"], exit_reason=reason,
                    ))
                    del positions[t]
                    cooldown.add(t)

            # ── 2. Rebalance to target weights (close fills). ─────────────
            if dt in portfolios:
                target = portfolios[dt]
                equity_now = cash + sum(
                    (price_of(t) or pos["entry_price"]) * pos["shares"]
                    for t, pos in positions.items()
                )
                old_value = 0.0
                for t in list(positions.keys()):
                    p = price_of(t)
                    if p is None:
                        continue
                    pos = positions[t]
                    if t not in target or t in cooldown:
                        fill = p * (1 - self.slippage_rate)
                        cash += self._sell(pos["shares"], fill)
                        cost_basis = pos["shares"] * pos["entry_price"]
                        trades.append(RotationTrade(
                            ticker=t, sector=sector_of(t),
                            entry_date=pos["entry_date"],
                            entry_price=pos["entry_price"],
                            exit_date=dt, exit_price=round(fill, 4),
                            shares=pos["shares"],
                            pnl=round(
                                pos["shares"] * fill * (1 - self.stamp_duty_rate)
                                - max(pos["shares"] * fill * self.commission_rate,
                                      self.commission_min)
                                - cost_basis, 2),
                            pnl_pct=round(fill / pos["entry_price"] - 1, 4)
                            if pos["entry_price"] else 0.0,
                            hold_days=i - pos["entry_idx"],
                            exit_reason="rebalance",
                        ))
                        del positions[t]
                    else:
                        old_value += pos["shares"] * p

                for t, w in target.items():
                    if t in cooldown or t in positions:
                        continue
                    p = price_of(t)
                    if p is None:
                        continue
                    budget = equity_now * w
                    lots = int(budget / (p * (1 + self.slippage_rate)) // LOT_SIZE)
                    buy_shares = lots * LOT_SIZE
                    if buy_shares <= 0:
                        continue
                    fill = p * (1 + self.slippage_rate)
                    cash -= self._buy_cost(buy_shares, fill)
                    positions[t] = {
                        "shares": buy_shares,
                        "entry_price": fill,
                        "entry_idx": i,
                        "high_close": fill,
                        "trailing": False,
                        "fixed_stop": self._entry_stop(fill, dt, t, atr_panel),
                        "entry_date": dt,
                        "sector": sector_of(t),
                    }

                new_value = sum(
                    (price_of(t) or 0.0) * pos["shares"]
                    for t, pos in positions.items()
                )
                turnover = abs(new_value - old_value) / equity_now \
                    if equity_now > 0 else 0.0
                turnovers.append(turnover)
                rebalance_log.append({
                    "date": dt,
                    "holdings": [
                        {"ticker": t, "sector": sector_of(t),
                         "weight": round(w, 4)}
                        for t, w in target.items()
                    ],
                    "turnover_pct": round(turnover * 100, 2),
                    "n_stocks": len(target),
                })

            # ── 3. Mark to market. ────────────────────────────────────────
            equity = cash + sum(
                (price_of(t) or 0.0) * pos["shares"]
                for t, pos in positions.items()
            )
            if not np.isfinite(equity):
                equity = prev_equity
            equity_curve.append({"date": dt, "equity": round(equity, 2)})
            peak = max(peak, equity)
            dd = (peak - equity) / peak if peak > 0 else 0
            max_dd = max(max_dd, dd)
            if prev_equity > 0:
                daily_returns.append((equity - prev_equity) / prev_equity)
            prev_equity = equity

        # ── 4. Force-close at the end. ─────────────────────────────────────
        last_dt = all_dates[-1]
        for t, pos in positions.items():
            c = price_of(t)
            if c is None:
                continue
            fill = c * (1 - self.slippage_rate)
            proceeds = self._sell(pos["shares"], fill)
            cash += proceeds
            cost_basis = pos["shares"] * pos["entry_price"]
            trades.append(RotationTrade(
                ticker=t, sector=sector_of(t),
                entry_date=pos["entry_date"], entry_price=pos["entry_price"],
                exit_date=last_dt, exit_price=round(fill, 4),
                shares=pos["shares"], pnl=round(proceeds - cost_basis, 2),
                pnl_pct=round((proceeds - cost_basis) / cost_basis, 4)
                if cost_basis else 0.0,
                hold_days=len(all_dates) - 1 - pos["entry_idx"],
                exit_reason="end",
            ))
        if positions:
            equity_curve[-1]["equity"] = round(cash, 2)
            positions.clear()

        final_equity = equity_curve[-1]["equity"]

        # ── 5. Metrics + benchmark. ───────────────────────────────────────
        total_return = (final_equity - initial_capital) / initial_capital * 100
        n_days = len(all_dates)
        years = n_days / 252
        annual = ((final_equity / initial_capital) ** (1 / years) - 1) * 100 \
            if years > 0 and final_equity > 0 else 0.0
        if daily_returns:
            dr = np.array(daily_returns)
            std = dr.std(ddof=1) if len(dr) > 1 else 0.0
            sharpe = dr.mean() / std * math.sqrt(252) if std > 0 else 0.0
        else:
            sharpe = 0.0

        bench_curve, bench_total = self._benchmark(close_panel, initial_capital)

        # Per-sector closed-trade PnL.
        sector_pnl: dict[str, float] = {}
        for tr in trades:
            sector_pnl[tr.sector] = sector_pnl.get(tr.sector, 0.0) + tr.pnl

        return {
            "model": model,
            "result": {
                "start_date": str(all_dates[0]),
                "end_date": str(all_dates[-1]),
                "initial_capital": initial_capital,
                "final_equity": final_equity,
                "total_return_pct": round(total_return, 2),
                "annual_return_pct": round(annual, 2),
                "max_drawdown_pct": round(max_dd * 100, 2),
                "sharpe_ratio": round(sharpe, 3),
                "rebalance_count": len(rebalance_log),
                "avg_turnover_pct": round(
                    sum(turnovers) / len(turnovers) * 100 if turnovers else 0.0, 2),
                "trade_count": len(trades),
                "win_rate_pct": round(
                    sum(1 for tr in trades if tr.pnl > 0) / len(trades) * 100
                    if trades else 0.0, 1),
                "benchmark_total_return_pct": round(bench_total * 100, 2),
                "excess_return_pct": round(
                    total_return - bench_total * 100, 2),
                "sector_pnl": {k: round(v, 2)
                               for k, v in sorted(sector_pnl.items())},
                "equity_curve": equity_curve,
                "benchmark_curve": bench_curve,
                "trades": [asdict(t) for t in trades],
                "rebalance_log": rebalance_log,
                "ic_summary": model["ic_summary"],
                "config": model["config"],
                "exit_rules": {
                    "stop_mode": self.stop_mode,
                    "atr_mult": self.atr_mult,
                    "breakdown_buffer": self.breakdown_buffer,
                    "trailing_activation_pct": TRAIL_ACTIVATION_PCT,
                    "trailing_giveback_pct": TRAIL_PCT,
                    "hard_stop_fallback_pct": STOP_LOSS_PCT,
                },
            },
        }

    @staticmethod
    def _benchmark(
        close_panel: pd.DataFrame, initial_capital: float,
    ) -> tuple[list[dict], float]:
        """Pool equal-weight index (daily-rebalanced, no costs)."""
        ret = close_panel.pct_change(fill_method=None)
        mean_ret = ret.mean(axis=1, skipna=True).fillna(0.0)
        nav = (1.0 + mean_ret).cumprod()
        curve = [
            {"date": dt, "equity": round(float(nav.loc[dt]) * initial_capital, 2)}
            for dt in close_panel.index
        ]
        total = float(nav.iloc[-1]) - 1.0 if len(nav) else 0.0
        return curve, total


def run_and_store(
    db: Session,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    initial_capital: float = 1e6,
    holding_period: int = HOLDING_PERIOD,
    top_k: int = TOP_K_SECTORS,
    top_n_per_sector: int = TOP_N_PER_SECTOR,
    max_weight: float = MAX_WEIGHT,
    use_fund_flow_factors: bool = True,
    bars_limit: int = 1200,
    stop_mode: str = "fixed",
    atr_mult: float = 2.0,
    breakdown_buffer: float = 0.0,
) -> dict:
    """Run the rotation backtest on the pool universe, store, return summary."""
    from . import rotation_service
    from app.models.chain_models import BacktestRun

    bars = rotation_service.load_pool_bars(db, limit=bars_limit,
                                           with_fund_flow=True)
    if not bars:
        raise ValueError("No pool bars loaded — run the mootdx backfill first")

    membership = rotation_service.get_pool_membership()
    engine = SectorRotationEngine(
        membership,
        top_k=top_k,
        top_n_per_sector=top_n_per_sector,
        holding_period=holding_period,
        max_weight=max_weight,
        use_fund_flow_factors=use_fund_flow_factors,
    )
    bt = RotationBacktester(
        stop_mode=stop_mode,
        atr_mult=atr_mult,
        breakdown_buffer=breakdown_buffer,
    )
    out = bt.run(
        bars, membership, engine,
        initial_capital=initial_capital,
        start_date=str(start_date) if start_date else None,
        end_date=str(end_date) if end_date else None,
    )
    r = out["result"]

    row = BacktestRun(
        ticker="ROTATION",
        strategy_set="sector_rotation",
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
            "sector_pnl": r["sector_pnl"],
            "avg_turnover_pct": r["avg_turnover_pct"],
        }),
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    return {"run_id": row.id, **{k: v for k, v in r.items()
                                  if k not in ("equity_curve", "trades",
                                               "benchmark_curve",
                                               "rebalance_log")}}
