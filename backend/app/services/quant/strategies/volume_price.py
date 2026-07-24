"""Volume factor: volume-price confirmation.

A price move on heavy volume is more trustworthy than on light volume —
that's the entire thesis. This factor *amplifies or dampens* the price
move's direction by how extreme the volume is:

  - direction = sign of today's daily return (close vs prev close)
  - intensity = turnover_pct60 in [0, 1]  (today's turnover vs trailing 60d)
  - score = direction * intensity

So +price on top-10% volume → +0.9; -price on top-10% volume → -0.9;
average-volume day → muted ±0.5.

Why this matters for AI-chain stocks: speculative names (寒武纪, 摩尔线程)
routinely gap on volume spikes. Pure price-action strategies get faked out
by low-volume drifts; the volume gate filters those.

Note: turnover_pct60 is derived from mootdx volume (see indicators.enrich),
NOT from East Money fund flow — so this factor is fully backtestable without
IP-throttled APIs.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .base import Strategy


class VolumePrice(Strategy):
    name = "volume_price"
    category = "volume"
    weight = 1.0  # sole strategy in "volume" category (volume = 0.20 of card)

    def compute(self, df: pd.DataFrame) -> pd.Series:
        close = df["close"]
        ret_sign = np.sign(close.pct_change().fillna(0.0))

        intensity = df["turnover_pct60"].fillna(0.0)
        # Map [0,1] → [0.2, 1.0] floor so even average-volume days carry a
        # small confirming weight; only sub-0.2 (very light) days get muted.
        intensity = 0.2 + 0.8 * intensity

        score = ret_sign * intensity
        return score.clip(-1.0, 1.0).fillna(0.0)
