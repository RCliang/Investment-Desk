"""Trend factor: MA crossover + regime filter.

Two sub-signals blended into one trend score:
  1. MA5 × MA20 crossover — the classic short-term trend trigger.
     Golden cross (MA5 crosses above MA20) → +1; death cross → -1. The
     signal persists between crosses (trend-following, not a one-bar spike).
  2. MA60 regime — being above the 60-day MA is a +0.5 tailwind, below is
     a -0.5 headwind. This filters out counter-trend MA5×MA20 whipsaws.

Final = sign(crossover) * (0.7 + 0.3 * regime_sign), so a golden cross
*above* MA60 scores +1.0 (full strength), while a golden cross *below*
MA60 scores +0.4 (dampened). Symmetric for death crosses.

This is the highest-weighted factor in the v1_default card (trend gets 40%
total, split 0.7/0.3 with Donchian breakout).
"""

from __future__ import annotations

import pandas as pd

from .base import Strategy


class TrendMA(Strategy):
    name = "trend_ma"
    category = "trend"
    weight = 0.7  # within "trend" category (trend total = 0.40 of card)

    def compute(self, df: pd.DataFrame) -> pd.Series:
        ma5 = df["ma5"]
        ma20 = df["ma20"]
        ma60 = df["ma60"]

        # Crossover state: +1 when MA5 > MA20, else -1. (Not the *event* —
        # the state. Trend-following holds the signal until the opposite
        # cross, not just on the cross day.)
        cross_state = pd.Series(np_sign(ma5 - ma20), index=df.index)

        # Regime: above MA60 → tailwind. Using sign lets the blend stay in
        # [-1, +1] regardless of how far above/below.
        regime = pd.Series(np_sign(ma60 - df["close"]) * -1.0, index=df.index)
        # ^ invert: above MA60 (close < ma60 is False) → regime +1.

        # Blend: state dominates (0.7), regime modulates (0.3).
        score = cross_state * 0.7 + regime * 0.3
        # Clamp to [-1, 1] for safety (blend can hit ±1.0 exactly).
        return score.clip(-1.0, 1.0)


def np_sign(s: pd.Series) -> pd.Series:
    """Like np.sign but returns +1/-1 (no zeros — ties count as +1).

    Plain np.sign returns 0 when ma5==ma20, which would zero the trend
    signal on flat days. We treat exact equality as mildly bullish to
    avoid flickering.
    """
    import numpy as np
    return np.sign(s.fillna(0.0)).replace(0.0, 1.0)
