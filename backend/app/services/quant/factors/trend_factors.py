"""Trend-following factors for the multi-factor model.

Each factor outputs a cross-sectional panel (date × ticker). The engine
will rank + neutralize + IC-weight these into a composite score.

Factors designed for 20-day holding period trend following:
  1. PriceMomentum20: 20-day return (classic momentum)
  2. TrendSlope: MA20 slope normalized by price (trend strength)
  3. MultiMAAlign: degree of bullish MA alignment (MA5>MA20>MA60)
  4. BreakoutStrength: distance from 20-day high (breakout proximity)
  5. VolumeMomentum: volume-weighted price momentum
  6. TrendConsistency: fraction of up-days in 20-day window
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .base import Factor, build_close_panel


class PriceMomentum20(Factor):
    """20-day price momentum: return over trailing 20 days.

    Classic trend factor: stocks that went up most in the past 20 days
    tend to continue (momentum effect). Well-documented in A-shares
    at the 1-4 week horizon.
    """
    name = "price_momentum_20"
    direction = 1
    min_lookback = 25

    def compute_panel(self, bars: dict[str, pd.DataFrame]) -> pd.DataFrame:
        close = build_close_panel(bars)
        return close / close.shift(20) - 1.0


class PriceMomentum60(Factor):
    """60-day (3-month) price momentum — medium-term trend.

    Complements the 20-day with a slower trend signal. Stocks in a
    sustained 3-month uptrend are more likely to continue than those
    with only a short pop.
    """
    name = "price_momentum_60"
    direction = 1
    min_lookback = 65

    def compute_panel(self, bars: dict[str, pd.DataFrame]) -> pd.DataFrame:
        close = build_close_panel(bars)
        return close / close.shift(60) - 1.0


class TrendSlope(Factor):
    """MA20 slope as a percentage of price — trend direction strength.

    slope = (MA20_today - MA20_5days_ago) / MA20_today

    Captures whether the moving average is rising (positive) or falling
    (negative), normalized so it's comparable across price levels.
    """
    name = "trend_slope"
    direction = 1
    min_lookback = 30

    def compute_panel(self, bars: dict[str, pd.DataFrame]) -> pd.DataFrame:
        close = build_close_panel(bars)
        ma20 = close.rolling(20, min_periods=20).mean()
        slope = (ma20 - ma20.shift(5)) / ma20.replace(0, np.nan)
        return slope


class MultiMAAlignment(Factor):
    """Degree of bullish MA alignment.

    Measures how "stacked" the moving averages are:
      score = ((MA5 - MA20) + (MA20 - MA60)) / close

    Positive and large → strong bull alignment (MA5 > MA20 > MA60).
    Negative → bear alignment.
    Continuous (not binary) so it can be ranked cross-sectionally.
    """
    name = "multi_ma_align"
    direction = 1
    min_lookback = 65

    def compute_panel(self, bars: dict[str, pd.DataFrame]) -> pd.DataFrame:
        close = build_close_panel(bars)
        ma5 = close.rolling(5).mean()
        ma20 = close.rolling(20, min_periods=20).mean()
        ma60 = close.rolling(60, min_periods=60).mean()
        spread = ((ma5 - ma20) + (ma20 - ma60)) / close.replace(0, np.nan)
        return spread


class BreakoutStrength(Factor):
    """Proximity to 20-day high — breakout momentum.

    value = (close - rolling_low_20) / (rolling_high_20 - rolling_low_20)

    Values near 1.0 → at the top of its range (strong breakout).
    Values near 0.0 → near the bottom (weak).
    This is essentially a Donchian-range position indicator.
    """
    name = "breakout_strength"
    direction = 1
    min_lookback = 25

    def compute_panel(self, bars: dict[str, pd.DataFrame]) -> pd.DataFrame:
        # Build high/low panels
        highs, lows, closes = {}, {}, {}
        for t, df in bars.items():
            idx = df["date"].astype(str)
            highs[t] = pd.Series(df["high"].values, index=idx)
            lows[t] = pd.Series(df["low"].values, index=idx)
            closes[t] = pd.Series(df["close"].values, index=idx)
        high_panel = pd.DataFrame(highs).sort_index()
        low_panel = pd.DataFrame(lows).sort_index()
        close_panel = pd.DataFrame(closes).sort_index()

        rolling_high = high_panel.rolling(20, min_periods=20).max()
        rolling_low = low_panel.rolling(20, min_periods=20).min()
        range_val = (rolling_high - rolling_low).replace(0, np.nan)
        return (close_panel - rolling_low) / range_val


class VolumeMomentum(Factor):
    """Volume-weighted price momentum.

    sum(amount * sign(return)) / sum(amount) over 20 days.

    Up-days with heavy volume carry more weight — confirms institutional
    buying behind a trend. Down-days on heavy volume signal distribution.
    """
    name = "volume_momentum"
    direction = 1
    min_lookback = 25

    def compute_panel(self, bars: dict[str, pd.DataFrame]) -> pd.DataFrame:
        weighted_returns = {}
        for t, df in bars.items():
            idx = df["date"].astype(str)
            ret = df["close"].pct_change()
            amount = df.get("amount", df.get("volume", pd.Series(dtype=float)))
            if len(amount) == 0:
                continue
            # Reset index alignment
            amount = pd.Series(amount.values, index=idx)
            ret = pd.Series(ret.values, index=idx)
            signed = ret * amount
            # Rolling 20-day weighted return
            num = signed.rolling(20, min_periods=15).sum()
            den = amount.rolling(20, min_periods=15).sum().replace(0, np.nan)
            weighted_returns[t] = num / den
        return pd.DataFrame(weighted_returns).sort_index()


class TrendConsistency(Factor):
    """Fraction of positive-return days in trailing 20 days.

    A stock that went up 15 out of 20 days (75% consistency) is in a
    smoother uptrend than one that went up 15% in a single day then
    chopped sideways. High consistency → more likely to persist.
    """
    name = "trend_consistency"
    direction = 1
    min_lookback = 25

    def compute_panel(self, bars: dict[str, pd.DataFrame]) -> pd.DataFrame:
        close = build_close_panel(bars)
        daily_ret = close.pct_change(fill_method=None)
        positive = (daily_ret > 0).astype(float)
        return positive.rolling(20, min_periods=15).mean()
