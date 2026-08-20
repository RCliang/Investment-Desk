"""Main-force fund-flow factors for the multi-factor model.

These factors consume per-ticker daily 主力资金 (main-force net inflow,
EM definition: 超大单+大单) merged into the bar DataFrames as a
`main_net` column (元) by the rotation loader. Where fund-flow history
is absent (before the backfill start, or a suspended day), values are
NaN — the factors preserve NaN so the engine's per-stock weight
renormalization can skip them cleanly (see factor_model.compute_composite).

All three factors normalize main_net by the day's `amount` first: the
RAW ratio (主力净流入 / 成交额) is size-free, comparable across a pool
spanning 北方华创 (~千亿市值) and 仕佳光子 (~百亿), and immune to the
market-cap regression that the engine applies anyway.

  1. MainInflowMomentum20:  20d cumulative net-inflow share of turnover
  2. MainInflowPersistence: fraction of net-inflow-positive days (20d)
  3. MainInflowAcceleration: 5d mean ratio minus 20d mean ratio
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .base import Factor, build_panel_from_col


def _inflow_ratio_panel(bars: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """main_net / amount panel (daily net-inflow share of turnover).

    NaN where either input is missing. A zero amount day yields NaN
    (can't scale an inflow against no turnover).
    """
    flow = build_panel_from_col(bars, "main_net")
    if flow.empty:
        return flow
    amount = build_panel_from_col(bars, "amount")
    flow, amount = flow.align(amount, join="outer")
    return flow / amount.replace(0, np.nan)


class MainInflowMomentum20(Factor):
    """20-day cumulative main-force net inflow as a share of turnover.

    sum(main_net / amount) over 20 days ≈ 累计吸筹强度: how much of the
    traded value the main force absorbed net over the past month. Direct
    proxy for sustained institutional accumulation.
    """
    name = "main_inflow_momentum_20"
    direction = 1
    min_lookback = 25

    def compute_panel(self, bars: dict[str, pd.DataFrame]) -> pd.DataFrame:
        ratio = _inflow_ratio_panel(bars)
        return ratio.rolling(20, min_periods=15).sum()


class MainInflowPersistence(Factor):
    """Fraction of net-inflow-positive days over trailing 20 days.

    A stock the main force buys on 15 of 20 days is being accumulated
    with more conviction than one with a single huge day and outflows
    the rest — persistence separates real positioning from noise.
    """
    name = "main_inflow_persistence"
    direction = 1
    min_lookback = 25

    def compute_panel(self, bars: dict[str, pd.DataFrame]) -> pd.DataFrame:
        flow = build_panel_from_col(bars, "main_net")
        if flow.empty:
            return flow
        positive = (flow > 0).astype(float)
        positive = positive.where(flow.notna())   # keep NaN as NaN, not False
        return positive.rolling(20, min_periods=15).mean()


class MainInflowAcceleration(Factor):
    """5-day mean inflow ratio minus 20-day mean inflow ratio.

    Positive → the main force is stepping IN faster than its recent norm
    (资金加速); negative → decelerating or distributing. Captures regime
    changes in money flow that the 20d cumulative factor smooths over.
    """
    name = "main_inflow_acceleration"
    direction = 1
    min_lookback = 25

    def compute_panel(self, bars: dict[str, pd.DataFrame]) -> pd.DataFrame:
        ratio = _inflow_ratio_panel(bars)
        fast = ratio.rolling(5, min_periods=4).mean()
        slow = ratio.rolling(20, min_periods=15).mean()
        return fast - slow
