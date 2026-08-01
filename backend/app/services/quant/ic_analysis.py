"""IC (Information Coefficient) analysis for multi-factor model.

IC measures the rank correlation (Spearman) between a factor's cross-sectional
values and the forward returns over the holding period. High |IC| means the
factor has predictive power for ranking stocks.

Key concepts:
  - Rank IC: Spearman correlation between factor ranks and return ranks.
    More robust than Pearson IC to outliers (common in A-shares).
  - IC mean: average IC over a rolling window → factor's recent effectiveness.
  - ICIR (IC Information Ratio): IC_mean / IC_std → stability of prediction.

We use a 60-day rolling IC window to adaptively weight factors: factors that
have been predicting well recently get higher weight in the composite.

This module is designed for cross-sectional (panel) data — it operates on
DataFrames indexed by date with columns for each ticker.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from typing import Optional


def compute_rank_ic(
    factor_panel: pd.DataFrame,
    forward_returns: pd.DataFrame,
) -> pd.Series:
    """Compute daily rank IC (Spearman) between factor and forward returns.

    Both inputs are panel DataFrames: index=date, columns=ticker.
    Returns a Series indexed by date, each value ∈ [-1, +1].

    For each date:
      IC_t = spearman(factor_values_t, forward_return_t)

    Only dates with ≥10 valid cross-sectional pairs are counted (sparse
    days give meaningless correlations).
    """
    ics = {}
    common_dates = factor_panel.index.intersection(forward_returns.index)
    for dt in common_dates:
        f = factor_panel.loc[dt].dropna()
        r = forward_returns.loc[dt].dropna()
        common = f.index.intersection(r.index)
        if len(common) < 10:
            continue
        f_ranked = f.loc[common].rank()
        r_ranked = r.loc[common].rank()
        corr = f_ranked.corr(r_ranked, method="pearson")
        if np.isfinite(corr):
            ics[dt] = corr
    return pd.Series(ics, name="rank_ic")


def rolling_ic_stats(
    ic_series: pd.Series,
    window: int = 60,
) -> pd.DataFrame:
    """Compute rolling IC statistics for adaptive factor weighting.

    Returns DataFrame with columns:
      - ic_mean: rolling mean IC (factor effectiveness trend)
      - ic_std:  rolling std IC (factor stability)
      - icir:    ic_mean / ic_std (information ratio)
      - ic_pct_positive: fraction of positive-IC days in window
    """
    df = pd.DataFrame(index=ic_series.index)
    df["ic_mean"] = ic_series.rolling(window, min_periods=20).mean()
    df["ic_std"] = ic_series.rolling(window, min_periods=20).std()
    df["icir"] = df["ic_mean"] / df["ic_std"].replace(0, np.nan)
    df["icir"] = df["icir"].fillna(0).clip(-3, 3)
    df["ic_pct_positive"] = (
        ic_series.rolling(window, min_periods=20)
        .apply(lambda x: (x > 0).mean(), raw=True)
    )
    return df


def adaptive_factor_weights(
    ic_stats: dict[str, pd.DataFrame],
    date: pd.Timestamp,
    method: str = "icir",
) -> dict[str, float]:
    """Compute adaptive weights for each factor based on recent IC performance.

    ic_stats: {factor_name: DataFrame from rolling_ic_stats()}
    date: the rebalance date
    method: weighting method
      - "icir": weight ∝ max(ICIR, 0) — favors stable predictors
      - "ic_mean": weight ∝ max(IC_mean, 0) — favors strong predictors
      - "equal": equal weight (baseline for comparison)

    Returns {factor_name: weight} summing to 1.0.
    Negative-IC factors are excluded (weight=0) since we don't short in A-shares.
    """
    raw_scores = {}
    for name, stats in ic_stats.items():
        if date not in stats.index:
            raw_scores[name] = 0.0
            continue
        row = stats.loc[date]
        if method == "icir":
            raw_scores[name] = max(float(row.get("icir", 0)), 0)
        elif method == "ic_mean":
            raw_scores[name] = max(float(row.get("ic_mean", 0)), 0)
        else:
            raw_scores[name] = 1.0

    total = sum(raw_scores.values())
    if total == 0:
        # All factors useless → equal weight fallback
        n = len(raw_scores) or 1
        return {k: 1.0 / n for k in raw_scores}
    return {k: v / total for k, v in raw_scores.items()}


def forward_returns_panel(
    close_panel: pd.DataFrame,
    horizon: int = 20,
) -> pd.DataFrame:
    """Compute forward returns over `horizon` trading days.

    close_panel: index=date, columns=ticker, values=close price.
    Returns same shape: forward_return_t = close[t+horizon] / close[t] - 1.

    Used for IC computation (training) — the last `horizon` rows are NaN
    (we can't know future returns, which is correct).
    """
    return close_panel.shift(-horizon) / close_panel - 1.0
