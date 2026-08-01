"""Cross-sectional multi-factor model engine for trend-following.

This is fundamentally different from the per-ticker Strategy/ScoreCard system:
  - Per-ticker: each stock evaluated independently, BUY/SELL/HOLD per stock.
  - Cross-sectional: ALL stocks ranked against each other on each date.

Pipeline:
  1. Load all tickers' bar data into a panel (date × ticker).
  2. Compute each factor's panel values.
  3. For each date: neutralize factor values against market-cap proxy.
  4. Convert to cross-sectional rank percentile ∈ [0, 1].
  5. Compute rolling IC for each factor (adaptive weighting signal).
  6. Combine factors using IC-weighted average.
  7. Select top-N stocks for the portfolio.

Market-cap neutralization (市值中性化):
  Since we don't have total shares outstanding, we use trading amount as a
  liquidity/market-cap proxy. For each date, we regress factor values
  against log(amount) and take the residual. This removes the systematic
  tilt where large-cap stocks score differently from small-caps — the
  composite should pick stocks on trend merit alone, not size.

  residual_i = factor_i - (α + β · log(amount_i))

  Implemented via simple OLS per date (fast: one small regression per date).
"""

from __future__ import annotations

import logging
import numpy as np
import pandas as pd
from typing import Optional

from .factors import (
    Factor, build_close_panel, build_panel_from_col,
    PriceMomentum20, PriceMomentum60, TrendSlope,
    MultiMAAlignment, BreakoutStrength, VolumeMomentum, TrendConsistency,
)
from . import ic_analysis

log = logging.getLogger(__name__)

HOLDING_PERIOD = 20  # target holding days (trading days)
IC_WINDOW = 60       # rolling IC lookback for adaptive weighting
TOP_N = 20           # number of stocks to hold in the portfolio
MAX_WEIGHT = 0.10    # max single-stock weight (equal-weight cap)


def neutralize(
    factor_panel: pd.DataFrame,
    mcap_proxy: pd.DataFrame,
) -> pd.DataFrame:
    """Market-cap neutralize a factor panel via cross-sectional regression.

    For each date, regress factor values on log(amount) and take residuals.
    This removes any systematic large-cap / small-cap bias from the factor.

    factor_panel: DataFrame(date × ticker), raw factor values.
    mcap_proxy:   DataFrame(date × ticker), trading amount as cap proxy.
    Returns:      DataFrame(date × ticker), residuals (neutralized).
    """
    result = factor_panel.copy()
    common_dates = factor_panel.index.intersection(mcap_proxy.index)
    for dt in common_dates:
        f = factor_panel.loc[dt]
        m = mcap_proxy.loc[dt]
        common = f.dropna().index.intersection(m.dropna().index)
        if len(common) < 10:
            continue
        x = np.log(m.loc[common].values.astype(float) + 1.0)
        y = f.loc[common].values.astype(float)
        # OLS: y = alpha + beta * x + residual
        x_with_const = np.column_stack([np.ones(len(x)), x])
        try:
            beta, _, _, _ = np.linalg.lstsq(x_with_const, y, rcond=None)
            residuals = y - x_with_const @ beta
            result.loc[dt, common] = residuals
        except np.linalg.LinAlgError:
            pass
    return result


def rank_normalize(panel: pd.DataFrame) -> pd.DataFrame:
    """Convert factor values to cross-sectional rank percentile ∈ [0, 1].

    This makes different factors comparable (they may have very different
    scales) and is robust to outliers. The IC computation also operates
    on ranks, so this step is consistent.
    """
    return panel.rank(axis=1, pct=True)


class MultiFactorEngine:
    """Cross-sectional multi-factor model for trend-following.

    Usage:
        engine = MultiFactorEngine(factors=[...], holding_period=20)
        result = engine.run(bars, start_date, end_date)

    The engine:
      1. Computes all factor panels
      2. Neutralizes against market cap
      3. Computes historical IC for adaptive weighting
      4. Combines into a composite score
      5. Selects top-N stocks at each rebalance date
    """

    def __init__(
        self,
        factors: Optional[list[Factor]] = None,
        holding_period: int = HOLDING_PERIOD,
        top_n: int = TOP_N,
        max_weight: float = MAX_WEIGHT,
        ic_window: int = IC_WINDOW,
        weighting_method: str = "icir",
    ):
        self.factors = factors or self._default_factors()
        self.holding_period = holding_period
        self.top_n = top_n
        self.max_weight = max_weight
        self.ic_window = ic_window
        self.weighting_method = weighting_method

    @staticmethod
    def _default_factors() -> list[Factor]:
        """Default trend-following factor set."""
        return [
            PriceMomentum20(),
            PriceMomentum60(),
            TrendSlope(),
            MultiMAAlignment(),
            BreakoutStrength(),
            VolumeMomentum(),
            TrendConsistency(),
        ]

    def compute_all_factors(self, bars: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
        """Compute all factor panels. Returns {name: neutralized + ranked panel}."""
        # Market cap proxy: 20-day average trading amount.
        amount_panel = build_panel_from_col(bars, "amount")
        mcap_proxy = amount_panel.rolling(20, min_periods=10).mean()

        panels = {}
        for factor in self.factors:
            raw = factor.compute_panel(bars)
            # Apply direction (-1 reverses the factor).
            if factor.direction == -1:
                raw = -raw
            # Neutralize against market cap.
            neutral = neutralize(raw, mcap_proxy)
            # Rank-normalize to [0, 1] cross-sectionally.
            ranked = rank_normalize(neutral)
            panels[factor.name] = ranked
        return panels

    def compute_ic_stats(
        self,
        factor_panels: dict[str, pd.DataFrame],
        close_panel: pd.DataFrame,
    ) -> dict[str, pd.DataFrame]:
        """Compute rolling IC stats for each factor.

        Uses forward returns at the target holding period (20 days).
        """
        fwd_ret = ic_analysis.forward_returns_panel(close_panel, self.holding_period)
        ic_stats = {}
        for name, panel in factor_panels.items():
            ic_series = ic_analysis.compute_rank_ic(panel, fwd_ret)
            ic_stats[name] = ic_analysis.rolling_ic_stats(ic_series, self.ic_window)
        return ic_stats

    def compute_composite(
        self,
        factor_panels: dict[str, pd.DataFrame],
        ic_stats: dict[str, pd.DataFrame],
    ) -> pd.DataFrame:
        """Combine factor panels into a composite score using IC-adaptive weights.

        For each date, compute factor weights from IC stats, then weighted-average
        the rank-normalized panels. Result is a composite panel ∈ [0, 1].

        Dates before the IC warmup period use equal weights.
        """
        all_dates = sorted(set().union(*(p.index for p in factor_panels.values())))
        composite = pd.DataFrame(
            np.nan,
            index=all_dates,
            columns=next(iter(factor_panels.values())).columns,
        )

        for dt in all_dates:
            weights = ic_analysis.adaptive_factor_weights(
                ic_stats, dt, method=self.weighting_method,
            )
            row = pd.Series(0.0, index=composite.columns)
            weight_sum = 0.0
            for name, panel in factor_panels.items():
                w = weights.get(name, 0)
                if w == 0 or dt not in panel.index:
                    continue
                vals = panel.loc[dt]
                row = row.add(vals * w, fill_value=0)
                weight_sum += w
            if weight_sum > 0:
                composite.loc[dt] = row / weight_sum

        return composite

    def get_portfolio(
        self,
        composite: pd.DataFrame,
        rebalance_dates: list[str],
    ) -> dict[str, dict[str, float]]:
        """Select top-N stocks at each rebalance date with equal weights.

        Returns {date: {ticker: weight}}.
        Weights are equal (1/N) capped at max_weight.
        """
        portfolios = {}
        for dt in rebalance_dates:
            if dt not in composite.index:
                continue
            scores = composite.loc[dt].dropna().sort_values(ascending=False)
            selected = scores.head(self.top_n).index.tolist()
            if not selected:
                continue
            n = len(selected)
            weight = min(1.0 / n, self.max_weight)
            # Normalize weights to sum to 1.
            total = weight * n
            portfolios[dt] = {t: weight / total for t in selected}
        return portfolios

    def run(
        self,
        bars: dict[str, pd.DataFrame],
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> dict:
        """Full pipeline: factors → IC → composite → portfolio selection.

        bars: {ticker: DataFrame(date, open, high, low, close, volume, amount, ...)}
        Returns a dict with:
          - factor_panels: {name: DataFrame}
          - ic_stats: {name: DataFrame}
          - composite: DataFrame
          - portfolios: {date: {ticker: weight}}
          - ic_summary: per-factor IC summary at the end date
        """
        log.info("Computing factor panels for %d tickers...", len(bars))
        factor_panels = self.compute_all_factors(bars)

        close_panel = build_close_panel(bars)
        if start_date:
            close_panel = close_panel[close_panel.index >= start_date]
        if end_date:
            close_panel = close_panel[close_panel.index <= end_date]

        log.info("Computing IC stats (window=%d, horizon=%d)...",
                 self.ic_window, self.holding_period)
        ic_stats = self.compute_ic_stats(factor_panels, close_panel)

        log.info("Building composite score...")
        composite = self.compute_composite(factor_panels, ic_stats)

        # Rebalance dates: every `holding_period` days.
        all_dates = list(composite.index)
        rebalance_dates = all_dates[::self.holding_period]

        log.info("Selecting top-%d portfolio at %d rebalance dates...",
                 self.top_n, len(rebalance_dates))
        portfolios = self.get_portfolio(composite, rebalance_dates)

        # IC summary at the latest available date.
        # IC stats have fewer dates than composite (forward returns
        # are NaN for the last `holding_period` days), so find the
        # latest date that actually has IC data.
        ic_summary = {}
        ic_latest = None
        for stats in ic_stats.values():
            valid = stats[stats["ic_mean"].notna()].index
            if len(valid) > 0:
                d = valid[-1]
                if ic_latest is None or d > ic_latest:
                    ic_latest = d
        if ic_latest is not None:
            for name, stats in ic_stats.items():
                # Use asof to get the nearest valid date.
                try:
                    row = stats.loc[ic_latest]
                except KeyError:
                    idx = stats.index.get_indexer([ic_latest], method="ffill")[0]
                    if idx < 0:
                        continue
                    row = stats.iloc[idx]
                ic_summary[name] = {
                    "ic_mean": round(float(row.get("ic_mean", 0)), 4),
                    "icir": round(float(row.get("icir", 0)), 4),
                    "ic_pct_positive": round(float(row.get("ic_pct_positive", 0)), 4),
                }

        return {
            "factor_panels": factor_panels,
            "ic_stats": ic_stats,
            "composite": composite,
            "portfolios": portfolios,
            "ic_summary": ic_summary,
            "config": {
                "holding_period": self.holding_period,
                "top_n": self.top_n,
                "max_weight": self.max_weight,
                "ic_window": self.ic_window,
                "weighting_method": self.weighting_method,
                "factors": [f.name for f in self.factors],
            },
        }
