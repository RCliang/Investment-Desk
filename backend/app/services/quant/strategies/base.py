"""Strategy base class — the contract every factor implements.

A Strategy turns a bar DataFrame into a daily signal Series in [-1, +1]:
    +1.0  strongest buy
     0    neutral / no opinion
    -1.0  strongest sell

The ScoreCard (scoring.py) weights these into one composite per day.

Hard rule (no future function): row t of the returned Series may only
depend on df.iloc[0..t]. All indicators used here are pandas rolling/ewm/
shift based, which preserve this. Subclasses must NOT reference df.shift(-n)
or df.iloc[t+1:].

Categories:
    - "trend"     directional bias from moving averages / breakouts
    - "momentum"  rate-of-change / oscillator signals
    - "volume"    volume-price confirmation
    - "risk"      does NOT produce a buy/sell score; instead returns
                  modifiers (allowed position, stop-loss price) via a
                  RiskModifier consumed by ScoreCard. Its `compute()`
                  still returns a Series (the market-regime gate, in
                  [-1,+1]) but ScoreCard reads `risk_extras()` separately.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Literal, Optional

import pandas as pd

StrategyCategory = Literal["trend", "momentum", "volume", "risk"]


class Strategy(ABC):
    """Abstract base. Subclasses set name/category/weight and implement compute."""

    name: str = "base"
    category: StrategyCategory = "trend"
    # Default weight inside its category. ScoreCard normalizes weights so
    # they sum to 1.0 across all strategies, so absolute values are relative.
    weight: float = 1.0

    @abstractmethod
    def compute(self, df: pd.DataFrame) -> pd.Series:
        """Return a daily signal in [-1, +1], indexed like df.

        df is an enriched bar DataFrame (indicators.enrich() already applied),
        sorted ascending by date. NaN values are treated as 0 (neutral) by
        the ScoreCard; subclasses may return NaN for warm-up rows.
        """
        ...

    def risk_extras(self, df: pd.DataFrame) -> dict:
        """Optional: return per-day risk modifiers.

        Only 'risk'-category strategies override this. Returns a dict of
        aligned Series, e.g. {"allowed_position": Series, "stop_loss": Series}.
        ScoreCard uses these to clip the final position and attach a stop.
        """
        return {}
