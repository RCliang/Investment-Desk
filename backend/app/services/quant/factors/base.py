"""Factor base class for the cross-sectional multi-factor model.

Unlike the single-stock Strategy class (which outputs a per-day signal
in [-1,+1] for one ticker), a Factor outputs a cross-sectional panel:
a DataFrame indexed by date, columns=ticker, values=factor exposure.

The multi-factor engine then:
  1. Ranks each factor cross-sectionally
  2. Neutralizes for market cap
  3. Combines with IC-adaptive weights
  4. Selects top-ranked stocks for the portfolio
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

import numpy as np
import pandas as pd


class Factor(ABC):
    """Abstract base for cross-sectional factors.

    Subclasses implement compute_panel() which returns a panel DataFrame
    (date × ticker). Values can be raw (will be ranked + neutralized).
    """

    name: str = "base"
    direction: int = 1  # +1 = higher value = more bullish; -1 = reverse
    min_lookback: int = 60  # minimum bars needed before factor is valid

    @abstractmethod
    def compute_panel(self, bars: dict[str, pd.DataFrame]) -> pd.DataFrame:
        """Compute the factor panel from per-ticker bar DataFrames.

        bars: {ticker: DataFrame(date, open, high, low, close, volume, amount, ...)}
        Returns: DataFrame(index=date, columns=ticker, values=factor_exposure)
        """
        ...


def build_close_panel(bars: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Build a close-price panel from per-ticker DataFrames.

    Utility used by multiple factors and the engine. Aligns all tickers
    on a common date index, forward-fills missing values (illiquid stocks).
    """
    closes = {}
    for ticker, df in bars.items():
        s = df.set_index(df["date"].astype(str))["close"]
        closes[ticker] = s
    panel = pd.DataFrame(closes)
    return panel.sort_index()


def build_panel_from_col(bars: dict[str, pd.DataFrame], col: str) -> pd.DataFrame:
    """Build a panel for any column from per-ticker DataFrames."""
    data = {}
    for ticker, df in bars.items():
        if col not in df.columns:
            continue
        s = df.set_index(df["date"].astype(str))[col]
        data[ticker] = s
    return pd.DataFrame(data).sort_index()
