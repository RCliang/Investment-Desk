"""Trend factor: Donchian channel breakout (turtle-trading trigger).

The pure trend-following trigger:
  - Buy  (+1) when close > prior 20-day high (new 20-day high).
  - Sell (-1) when close < prior 10-day low  (new 10-day low).
  - Otherwise: 0 (no opinion — let the trend run).

`donchian()` already excludes today via .shift(1), so "new high" means
genuinely above the *previous* 20-day max, not a trivial same-day tie.

This is intentionally sparse — it only fires on breakouts, leaving the
in-trend scoring to MA. Combined with MA in the trend category, breakout
acts as the *trigger* while MA provides the *bias*. Weights inside trend:
MA 0.7, Donchian 0.3.
"""

from __future__ import annotations

import pandas as pd

from .base import Strategy
from ..indicators import donchian


class BreakoutDonchian(Strategy):
    name = "breakout_donchian"
    category = "trend"
    weight = 0.3  # within "trend" category

    def compute(self, df: pd.DataFrame) -> pd.Series:
        entry_high, exit_low = donchian(df["high"], df["low"], entry_n=20, exit_n=10)
        close = df["close"]

        score = pd.Series(0.0, index=df.index, dtype=float)
        score[close > entry_high] = 1.0
        score[close < exit_low] = -1.0
        return score.fillna(0.0)
