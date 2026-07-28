"""Risk factor: market-regime gate + fixed-percentage stop loss.

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
  2. Stop loss: HARD 10% from entry. For the signal panel (which doesn't
     know the eventual entry price), we report close × 0.9 as the
     "if-bought-today" reference stop. The backtester overrides this with
     the actual entry price × 0.9 once a position is opened.

The compute() return value is the regime gate in {-1, 0, +1}:
    +1 = bull regime (full position allowed)
     0 = neutral
    -1 = deep bear regime (position halved)
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .base import Strategy

# Hard stop-loss: 10% below entry. A classic retail risk rule — simple,
# unambiguous, doesn't widen during volatility spikes like ATR stops.
STOP_LOSS_PCT = 0.10

# Trailing take-profit (移动止盈): once unrealized gain ≥ ACTIVATION_PCT,
# switch from the fixed stop to a trailing stop that follows the highest
# price since entry. The trail sits TRAIL_PCT below that high water mark
# and only moves up (never down) — so it locks in profit as the stock runs.
#
# Lifecycle of the stop during one holding period:
#   open       → fixed_stop = entry × (1 - STOP_LOSS_PCT)        [e.g. entry × 0.90]
#   gain < 15% → fixed_stop unchanged (still entry × 0.90)
#   gain ≥ 15% → trailing_stop = high_since_entry × (1 - TRAIL_PCT)  [e.g. high × 0.92]
#                effective_stop = max(fixed_stop, trailing_stop)
#
# Why 20%/8%: 20% activation only kicks in on confirmed big winners — small
# winners and normal uptrend pullbacks keep the loose fixed stop so the
# strategy doesn't get shaken out prematurely. 8% trail is tight enough to
# exit near the top of a blow-off but loose enough to not get shaken out by
# a single volatile session (AI-chain stocks routinely gap ±6% intraday).
TRAIL_ACTIVATION_PCT = 0.20   # activate trailing after +20% gain
TRAIL_PCT = 0.08              # trail 8% below the peak


class RiskATR(Strategy):
    """Despite the name (kept for back-compat with stored strategy_set keys),
    this now implements a fixed-percentage stop, not an ATR-based one.

    Renaming would invalidate existing chain_signals rows (detail_json keys);
    the strategy_set 'v1_default' stays stable. The ATR indicator is still
    computed in indicators.enrich() and used by the scorecard for nothing
    now, but kept available for future strategy variants.
    """
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
        stop_loss:        close × (1 - STOP_LOSS_PCT). Reference stop "if
                          bought today at today's close". The backtester
                          replaces this with entry_price × 0.9 once filled.
        """
        close = df["close"]

        # Position modifier from regime.
        gate = self.compute(df)
        allowed = gate.replace({1.0: 1.0, 0.0: 0.8, -1.0: 0.5}).fillna(0.8)

        # Hard 10% stop from today's close (signal-panel reference).
        stop = close * (1.0 - STOP_LOSS_PCT)
        return {
            "allowed_position": allowed,
            "stop_loss": stop,
        }
