"""Risk factor: market-regime gate + ATR-based stop loss.

This is the only 'risk'-category strategy. It does NOT contribute a
directional score to the composite; instead it gates the *position size*
and supplies a per-day stop-loss price. The ScoreCard reads these via
risk_extras().

Two responsibilities:
  1. Market-regime gate: when the stock itself is in a deep drawdown
     (close < MA60 * 0.85, i.e. >15% below the 60-day MA), halve the
     allowed position — bear regimes deserve smaller bets even when
     micro signals fire BUY. We use the stock's own MA60 as a per-ticker
     regime proxy (no index dependency → fully backtestable per ticker).
  2. Stop loss: trailing stop at close - 2 * ATR14. Tightened to 1.5 * ATR
     when the trend is strongly bullish (MA5 > MA20 > MA60) to lock gains.

The compute() return value is the regime gate in {-1, 0, +1}:
    +1 = bull regime (full position allowed)
     0 = neutral
    -1 = deep bear regime (position halved)
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .base import Strategy


class RiskATR(Strategy):
    name = "risk_atr"
    category = "risk"
    weight = 1.0  # not blended into composite; weight unused

    def compute(self, df: pd.DataFrame) -> pd.Series:
        close = df["close"]
        ma60 = df["ma60"]
        ma5 = df["ma5"]
        ma20 = df["ma20"]

        # Regime: deep bear when close < 0.85 * MA60.
        gate = pd.Series(1.0, index=df.index, dtype=float)  # default bull
        gate[close < ma60 * 0.85] = -1.0
        # Neutral band: between 0.85*MA60 and MA60 but MA5 < MA20 (short
        # term down within an up regime) → 0.
        neutral = (close >= ma60 * 0.85) & (close < ma60) & (ma5 < ma20)
        gate[neutral] = 0.0
        return gate.fillna(0.0)

    def risk_extras(self, df: pd.DataFrame) -> dict:
        """Return per-day {allowed_position, stop_loss} Series.

        allowed_position: 1.0 in bull regime, 0.5 in deep bear, 0.8 neutral.
        stop_loss:        close - k*ATR, where k=1.5 in strong uptrend else 2.0.
        """
        close = df["close"]
        atr = df["atr14"]
        ma5 = df["ma5"]
        ma20 = df["ma20"]
        ma60 = df["ma60"]

        # Position modifier from regime.
        gate = self.compute(df)
        allowed = gate.replace({1.0: 1.0, 0.0: 0.8, -1.0: 0.5}).fillna(0.8)

        # Stop-loss multiplier: tighter (1.5) when MA5>MA20>MA60 (strong up).
        strong_up = (ma5 > ma20) & (ma20 > ma60)
        k = pd.Series(2.0, index=df.index)
        k[strong_up] = 1.5

        stop = close - k * atr
        return {
            "allowed_position": allowed,
            "stop_loss": stop,
        }
