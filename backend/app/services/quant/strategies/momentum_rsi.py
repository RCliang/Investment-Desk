"""Momentum factor: RSI mean-reversion (contrarian at extremes).

RSI is a counter-trend factor — it fires against the prevailing move:
  - Oversold bounce: RSI < 30 then crosses back above 30 → buy (+1).
    Strengthened when RSI is deeply oversold (< 20).
  - Overbought fade: RSI > 70 then crosses below 70 → sell (-1).
    Strengthened when RSI is extremely overbought (> 80).
  - Between 30 and 70: no signal (neutral).

This deliberately conflicts with trend-following factors at extremes —
the ScoreCard's weighted blend is what resolves the tension. RSI alone
is too noisy in strong trends, which is why it carries only 0.5 weight
inside the momentum category (MACD gets the other 0.5).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .base import Strategy


class MomentumRSI(Strategy):
    name = "momentum_rsi"
    category = "momentum"
    weight = 0.5  # within "momentum" category

    def compute(self, df: pd.DataFrame) -> pd.Series:
        rsi = df["rsi14"]

        score = pd.Series(0.0, index=df.index, dtype=float)

        # Oversold zone: RSI crosses back above 30 → mean-reversion buy.
        # Use shift to detect "was below 30 yesterday, is above today".
        below_30 = rsi < 30
        bounce = below_30.shift(1, fill_value=False) & ~below_30
        # Deep oversold (< 20) gives a stronger bounce signal.
        deep = rsi < 20
        deep_bounce = deep.shift(1, fill_value=False) & ~deep
        score = score.where(~bounce, 1.0)
        score = score.where(~deep_bounce, 1.0)  # deep overrides normal

        # Overbought zone: RSI crosses below 70 → mean-reversion sell.
        above_70 = rsi > 70
        fade = above_70.shift(1, fill_value=False) & ~above_70
        extreme = rsi > 80
        extreme_fade = extreme.shift(1, fill_value=False) & ~extreme
        score = score.where(~fade, -1.0)
        score = score.where(~extreme_fade, -1.0)

        return score.fillna(0.0)
