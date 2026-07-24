"""Momentum factor: MACD golden/death cross with zero-axis filter.

Signal logic:
  1. Cross state: +1 when dif > dea (bullish alignment), -1 when dif < dea.
     This state persists between crosses (trend-following, not one-bar).
  2. Zero-axis filter: when the bullish state coincides with dif <= 0 (deep
     in bear territory), dampen the score by 0.5 — golden crosses below the
     zero axis frequently whipsaw.
  3. Strength weighting: scale the state by min(1, |dif| / atr14), so a
     tiny dif (weak momentum) produces a muted signal. ATR-normalized so the
     threshold adapts across cheap and pricey stocks.

Final score in [-1, +1]. This is a momentum *confirmation* factor — it
rarely fires alone, the ScoreCard blends it with trend & volume.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .base import Strategy


class MomentumMACD(Strategy):
    name = "momentum_macd"
    category = "momentum"
    weight = 0.5  # within "momentum" category (momentum total = 0.25 of card)

    def compute(self, df: pd.DataFrame) -> pd.Series:
        dif = df["macd_dif"]
        dea = df["macd_dea"]
        atr = df["atr14"]

        # 1. Alignment state: +1 bullish (dif>dea), -1 bearish.
        state = np.sign(dif - dea).fillna(0.0)

        # 2. Zero-axis filter: dampen bullish state when dif <= 0.
        zero_filter = pd.Series(1.0, index=df.index)
        zero_filter[(state > 0) & (dif <= 0)] = 0.5

        # 3. ATR-normalized strength: |dif| / atr14, clipped to [0, 1].
        # Small dif → small signal; large dif → full signal.
        safe_atr = atr.replace(0.0, np.nan).fillna(dif.abs().rolling(20).mean().fillna(0.01))
        safe_atr = safe_atr.replace(0.0, 0.01)
        strength = (dif.abs() / safe_atr).clip(0.0, 1.0).fillna(0.0)

        score = state * zero_filter * strength
        return score.clip(-1.0, 1.0).fillna(0.0)
