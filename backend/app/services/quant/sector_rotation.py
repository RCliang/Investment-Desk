"""Sector-rotation engine: sector strength + 3-layer portfolio construction.

Strategy shape (mid-term trend, monthly rebalance):

  Layer 1 — sector:   8 pool sectors scored 0-1 by a 50/50 blend of a
                      fund-flow dim (sector-aggregated main_net/amount,
                      20d smoothed, cross-sector rank) and a technical dim
                      (bullish-MA member share + sector-index 20d momentum,
                      cross-sector rank). Top-K sectors enter the portfolio.
  Layer 2 — stock:    within each selected sector, stocks ranked by the
                      MultiFactorEngine composite (7 trend factors + 3
                      fund-flow factors, ICIR-adaptive weights). Top-N per
                      sector, non-bullish-MA candidates skipped with a
                      ≤2-name fallback (trend gate inherited from
                      trend_follow).
  Layer 3 — exit:     daily checks (consumed by rotation_backtest /
                      rotation_service): MA-breakdown SELL (MA5<MA20 and
                      2 consecutive closes below MA20), hard stop -10%,
                      trailing take-profit (+20% activation / -8% giveback).

Where fund-flow history is absent (before the backfill start), every
panel degrades gracefully to NaN and the strength blend falls back to
the technical dim alone — that is the long-history skeleton mode.
"""

from __future__ import annotations

import logging
from typing import Optional

import numpy as np
import pandas as pd

from .factor_model import MultiFactorEngine, HOLDING_PERIOD
from .factors import (
    build_close_panel, build_panel_from_col,
    PriceMomentum20, PriceMomentum60, TrendSlope,
    MultiMAAlignment, BreakoutStrength, VolumeMomentum, TrendConsistency,
    MainInflowMomentum20, MainInflowPersistence, MainInflowAcceleration,
)

log = logging.getLogger(__name__)

# ── Defaults (all overridable; mirrored by the API/backtest params) ────────
TOP_K_SECTORS = 3        # sectors held in the rotation portfolio
TOP_N_PER_SECTOR = 2     # stocks picked per selected sector (≤6 names)
ENTRY_FALLBACK = 2       # max non-bullish candidates to skip when filling Top-N
MAX_WEIGHT = 0.20        # single-stock cap (1/6 ≈ 0.167 sits below this)
STRENGTH_WINDOW = 20     # smoothing window for both strength dims


def _sector_columns(panel: pd.DataFrame, members: list[str]) -> list[str]:
    """Members actually present in a panel's columns."""
    return [t for t in members if t in panel.columns]


def build_bullish_panel(bars: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Per-stock bullish MA alignment: MA5 > MA20 > MA60 (bool panel).

    NaN during warm-up / missing data compares False — a stock without a
    formed trend is simply not entry-eligible.
    """
    close = build_close_panel(bars)
    ma5 = close.rolling(5, min_periods=5).mean()
    ma20 = close.rolling(20, min_periods=20).mean()
    ma60 = close.rolling(60, min_periods=60).mean()
    return (ma5 > ma20) & (ma20 > ma60)


def build_breakdown_panel(
    bars: dict[str, pd.DataFrame],
    buffer: float = 0.0,
) -> pd.DataFrame:
    """Per-stock MA-breakdown SELL condition (trend_breakout parity).

    MA5 < MA20 AND close < MA20 × (1 - buffer) for 2 consecutive days
    (the rolling-2 sum filters one-day shakeouts). Exit signal on day T
    → executed T+1 in the backtester, mirroring the single-stock
    backtester's timing.

    `buffer` (e.g. 0.03 = 3%) widens the breakdown trigger below MA20 —
    in high-volatility sectors a close marginally under MA20 is noise,
    not a trend break (v2 anti-whipsaw knob).
    """
    close = build_close_panel(bars)
    ma5 = close.rolling(5, min_periods=5).mean()
    ma20 = close.rolling(20, min_periods=20).mean()
    trigger_level = ma20 * (1.0 - buffer)
    raw_break = ((ma5 < ma20) & (close < trigger_level)).astype(float)
    raw_break = raw_break.where(close.notna())
    return raw_break.rolling(2, min_periods=2).sum() == 2


def build_atr_panel(
    bars: dict[str, pd.DataFrame],
    window: int = 14,
) -> pd.DataFrame:
    """ATR14 panel for volatility-scaled stops.

    TR = max(high - low, |high - prev_close|, |low - prev_close|);
    ATR = rolling mean of TR over `window` days. Missing bars propagate
    NaN (warm-up days, suspended dates).
    """
    highs, lows, closes = {}, {}, {}
    for t, df in bars.items():
        idx = df["date"].astype(str)
        highs[t] = pd.Series(df["high"].values, index=idx)
        lows[t] = pd.Series(df["low"].values, index=idx)
        closes[t] = pd.Series(df["close"].values, index=idx)
    h = pd.DataFrame(highs).sort_index()
    l = pd.DataFrame(lows).sort_index()
    c = pd.DataFrame(closes).sort_index()
    pc = c.shift(1)
    tr = (h - l)
    tr = tr.where(tr >= (h - pc).abs(), (h - pc).abs())
    tr = tr.where(tr >= (l - pc).abs(), (l - pc).abs())
    return tr.rolling(window, min_periods=window).mean()


def compute_sector_strength(
    bars: dict[str, pd.DataFrame],
    membership: dict[str, list[str]],
    window: int = STRENGTH_WINDOW,
) -> dict:
    """Sector strength panel (date × sector) plus dimensional breakdown.

    Returns {strength, flow_rank, tech_rank, detail} — all DataFrames
    indexed by date with one column per sector. strength/tech_rank/flow_rank
    ∈ [0,1] are cross-SECTOR rank percentiles (8 names per date); detail
    carries the un-ranked means/momentum for display.
    """
    close = build_close_panel(bars)
    amount = build_panel_from_col(bars, "amount")
    flow = build_panel_from_col(bars, "main_net")

    sectors = sorted({s for members in membership.values() for s in members})

    # ── Fund-flow dim ────────────────────────────────────────────────────
    # Daily main_net/amount per stock → equal-weight sector mean → 20d
    # smoothing → cross-sector rank. Size-free by construction.
    if not flow.empty and not amount.empty:
        flow, amount = flow.align(amount, join="outer")
        ratio = flow / amount.replace(0, np.nan)
        flow_means, flow_smoothed = {}, {}
        for sec in sectors:
            cols = _sector_columns(ratio, [t for t, ss in membership.items() if sec in ss])
            if not cols:
                continue
            flow_means[sec] = ratio[cols].mean(axis=1, skipna=True)
            flow_smoothed[sec] = flow_means[sec].rolling(window, min_periods=window // 2).mean()
        flow_raw = pd.DataFrame(flow_smoothed).sort_index()
        flow_rank = flow_raw.rank(axis=1, pct=True)
    else:
        flow_raw = pd.DataFrame()
        flow_rank = pd.DataFrame()

    # ── Technical dim ────────────────────────────────────────────────────
    # (a) share of members in bullish MA alignment, 20d-smoothed;
    # (b) equal-weight sector index 20d momentum.
    bullish = build_bullish_panel(bars)
    ret = close.pct_change(fill_method=None)
    align_share, momentum = {}, {}
    for sec in sectors:
        members = [t for t, ss in membership.items() if sec in ss]
        acols = _sector_columns(bullish, members)
        rcols = _sector_columns(ret, members)
        if acols:
            align_share[sec] = bullish[acols].mean(axis=1, skipna=True).rolling(
                window, min_periods=window // 2).mean()
        if rcols:
            sector_index = (1.0 + ret[rcols].mean(axis=1, skipna=True)).cumprod()
            momentum[sec] = sector_index / sector_index.shift(window) - 1.0
    align_df = pd.DataFrame(align_share).sort_index()
    mom_df = pd.DataFrame(momentum).sort_index()
    tech_rank = (align_df.rank(axis=1, pct=True) + mom_df.rank(axis=1, pct=True)) / 2.0

    # ── Blend: 50/50, per-date fallback to tech-only when flow is absent ─
    common = tech_rank.index.union(flow_rank.index) if not flow_rank.empty \
        else tech_rank.index
    strength = pd.DataFrame(np.nan, index=common, columns=tech_rank.columns)
    for dt in common:
        tech_row = tech_rank.loc[dt] if dt in tech_rank.index else pd.Series(dtype=float)
        if dt in flow_rank.index:
            flow_row = flow_rank.loc[dt]
            has_flow = flow_row.notna().any()
        else:
            flow_row, has_flow = None, False
        if has_flow and dt in tech_rank.index:
            strength.loc[dt] = 0.5 * flow_row + 0.5 * tech_row
        elif dt in tech_rank.index:
            strength.loc[dt] = tech_row

    return {
        "strength": strength,
        "flow_rank": flow_rank,
        "tech_rank": tech_rank,
        "detail": {
            "flow_mean_20d": flow_raw,
            "align_share_20d": align_df,
            "momentum_20d": mom_df,
        },
    }


def compute_divergence_panel(bars: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Warning flag for monitoring (not a selection input).

    True when the close is at its 20-day high while the 20-day cumulative
    main-force net inflow is negative — price strength without main-force
    participation.
    """
    close = build_close_panel(bars)
    amount = build_panel_from_col(bars, "amount")
    flow = build_panel_from_col(bars, "main_net")
    if flow.empty or amount.empty:
        return pd.DataFrame(False, index=close.index, columns=close.columns)
    flow, amount = flow.align(amount, join="outer")
    close = close.reindex(flow.index)
    ratio = flow / amount.replace(0, np.nan)
    cum_outflow = ratio.rolling(20, min_periods=15).sum() < 0
    at_high = close >= close.rolling(20, min_periods=20).max()
    return cum_outflow & at_high


def select_portfolio_at(
    dt,
    composite: pd.DataFrame,
    strength: pd.DataFrame,
    bullish: pd.DataFrame,
    membership: dict[str, list[str]],
    top_k: int = TOP_K_SECTORS,
    top_n_per_sector: int = TOP_N_PER_SECTOR,
    entry_fallback: int = ENTRY_FALLBACK,
    max_weight: float = MAX_WEIGHT,
) -> tuple[dict[str, float], dict]:
    """Run the 3-layer selection for ONE date.

    Shared by the engine's rebalance loop and the daily service scan (which
    wants today's recommendation without waiting for the next scheduled
    rebalance date). Returns ({ticker: weight}, detail) — detail carries the
    per-sector picks/skips for display and diagnostics.
    """
    if dt not in strength.index or dt not in composite.index:
        return {}, {"top_sectors": [], "n_stocks": 0}
    scores_by_sector = composite.loc[dt]
    sector_row = strength.loc[dt].dropna()
    top_sectors = sector_row.sort_values(ascending=False).head(top_k)

    picks: list[str] = []
    detail_sectors = []
    bullish_at = bullish.loc[dt] if dt in bullish.index else pd.Series(dtype=bool)
    for sec, s_val in top_sectors.items():
        members = [t for t, ss in membership.items() if sec in ss]
        cols = _sector_columns(composite, members)
        if not cols:
            continue
        ranked = scores_by_sector[cols].dropna().sort_values(ascending=False)
        candidates = ranked.index[:top_n_per_sector + entry_fallback]
        chosen, skipped = [], []
        for t in candidates:
            if bool(bullish_at.get(t, False)):
                chosen.append(t)
                if len(chosen) >= top_n_per_sector:
                    break
            else:
                skipped.append(t)
        picks.extend(chosen)
        detail_sectors.append({
            "sector": sec,
            "strength": round(float(s_val), 4),
            "chosen": chosen,
            "skipped_non_bullish": skipped,
        })

    weights: dict[str, float] = {}
    if picks:
        n = len(picks)
        weight = min(1.0 / n, max_weight)
        # No renormalization: with few picks the cap binds and the
        # remainder intentionally stays cash (e.g. 4 picks × 0.20 = 80%
        # invested) rather than inflating weights past the cap.
        weights = {t: weight for t in picks}
    return weights, {"top_sectors": detail_sectors, "n_stocks": len(picks)}


class SectorRotationEngine:
    """3-layer sector-rotation portfolio constructor.

    Usage:
        engine = SectorRotationEngine(membership, top_k=3, top_n_per_sector=2)
        result = engine.run(bars, start_date, end_date)
        # result["portfolios"]: {rebalance_date: {ticker: weight}}
    """

    def __init__(
        self,
        membership: dict[str, list[str]],
        top_k: int = TOP_K_SECTORS,
        top_n_per_sector: int = TOP_N_PER_SECTOR,
        entry_fallback: int = ENTRY_FALLBACK,
        holding_period: int = HOLDING_PERIOD,
        max_weight: float = MAX_WEIGHT,
        use_fund_flow_factors: bool = True,
        fund_flow_direction: int = 1,
        ic_window: int = 60,
        weighting_method: str = "icir",
    ):
        self.membership = membership
        self.top_k = top_k
        self.top_n_per_sector = top_n_per_sector
        self.entry_fallback = entry_fallback
        self.holding_period = holding_period
        self.max_weight = max_weight
        self.use_fund_flow_factors = use_fund_flow_factors
        self.fund_flow_direction = fund_flow_direction

        factors = [
            PriceMomentum20(), PriceMomentum60(), TrendSlope(),
            MultiMAAlignment(), BreakoutStrength(), VolumeMomentum(),
            TrendConsistency(),
        ]
        if use_fund_flow_factors:
            flow_factors = [
                MainInflowMomentum20(), MainInflowPersistence(),
                MainInflowAcceleration(),
            ]
            # -1 flips all three main-force factors to contrarian
            # (money chasing as a local-top signal) — experimental knob,
            # justified when their IC regime is persistently negative.
            for f in flow_factors:
                f.direction = fund_flow_direction
            factors += flow_factors
        self.mf = MultiFactorEngine(
            factors=factors,
            holding_period=holding_period,
            # Not used for selection (engine's own get_portfolio is bypassed)
            # but kept consistent for config snapshots.
            top_n=top_k * top_n_per_sector,
            max_weight=max_weight,
            ic_window=ic_window,
            weighting_method=weighting_method,
        )

    def run(
        self,
        bars: dict[str, pd.DataFrame],
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> dict:
        """Full pipeline: factors → composite → sector strength → selection.

        Returns {factor_panels, ic_stats, composite, sector, portfolios,
        selection_detail, ic_summary, config}.
        """
        log.info("Rotation: computing factor panels for %d tickers...", len(bars))
        factor_panels = self.mf.compute_all_factors(bars)

        close_panel = build_close_panel(bars)
        if start_date:
            close_panel = close_panel[close_panel.index >= start_date]
        if end_date:
            close_panel = close_panel[close_panel.index <= end_date]

        log.info("Rotation: computing IC stats...")
        ic_stats = self.mf.compute_ic_stats(factor_panels, close_panel)

        log.info("Rotation: building composite...")
        composite = self.mf.compute_composite(factor_panels, ic_stats)

        log.info("Rotation: scoring sectors...")
        sector = compute_sector_strength(bars, self.membership)

        bullish = build_bullish_panel(bars)

        # Rebalance dates follow the same convention as MultiFactorEngine.run.
        all_dates = list(composite.index)
        rebalance_dates = all_dates[::self.holding_period]

        log.info("Rotation: selecting Top-%d sectors × Top-%d stocks at %d dates...",
                 self.top_k, self.top_n_per_sector, len(rebalance_dates))
        portfolios: dict[str, dict[str, float]] = {}
        selection_detail: dict[str, dict] = {}
        for dt in rebalance_dates:
            weights, detail = select_portfolio_at(
                dt, composite, sector["strength"], bullish, self.membership,
                top_k=self.top_k,
                top_n_per_sector=self.top_n_per_sector,
                entry_fallback=self.entry_fallback,
                max_weight=self.max_weight,
            )
            if weights:
                portfolios[dt] = weights
            selection_detail[dt] = detail

        # IC summary at the latest date with IC data (mirror mf engine).
        ic_summary: dict = {}
        ic_latest = None
        for stats in ic_stats.values():
            valid = stats[stats["ic_mean"].notna()].index
            if len(valid) > 0 and (ic_latest is None or valid[-1] > ic_latest):
                ic_latest = valid[-1]
        if ic_latest is not None:
            for name, stats in ic_stats.items():
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
            "sector": sector,
            "portfolios": portfolios,
            "selection_detail": selection_detail,
            "ic_summary": ic_summary,
            "config": {
                "holding_period": self.holding_period,
                "top_k_sectors": self.top_k,
                "top_n_per_sector": self.top_n_per_sector,
                "entry_fallback": self.entry_fallback,
                "max_weight": self.max_weight,
                "strength_window": STRENGTH_WINDOW,
                "use_fund_flow_factors": self.use_fund_flow_factors,
                "fund_flow_direction": self.fund_flow_direction,
                "factors": [f.name for f in self.mf.factors],
            },
        }
