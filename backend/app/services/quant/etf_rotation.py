"""ETF dual-momentum rotation engine (混合池双动量).

Signal stack, per rebalance date (monthly by default, T-close data →
T-close fills — the same convention as the sector-rotation engine):

  1. Relative momentum — blended multi-window return
     (0.25×R60 + 0.25×R120 + 0.5×R250) divided by annualized 20d volatility
     (Sharpe-style ranking; the vol division is also the first line of
     defence against momentum crashes).
  2. Absolute momentum — an ETF's 180d return must beat the CASH ETF's
     own 180d return to be eligible. Unfilled Top-N slots park in the
     cash ETF instead of back-filling weak names; all-fail → 100% cash.
  3. Rank buffer — holdings are sticky: a held ETF stays while it still
     ranks ≤ top_n + buffer_rank and passes the gate (retention takes
     the slots first); fresh entrants (rank ≤ top_n) only fill the
     remaining slots. One rebalance of "grace" cuts churn in sideways
     markets. use_buffer=False degrades to the naive top-N.

    Side effect: a rank-1 newcomer waits one cycle if all holdings sit
    inside the band — accepted; the band is ±2 ranks on a weekly cadence.

  4. Market-timing gate (optional, use_market_gate) — when the market
     proxy (510300 by default) closes below its own MA (200d default),
     equity-like tickers are blocked from ranking that day; defensive
     names (国债/黄金/纳指) and cash stay eligible. A regime overlay on
     top of the per-ETF absolute-momentum gate, for systemic drawdowns.

  Rebalance cadence (rebalance_mode):
    fixed    — every holding_period trading days (weekly default);
    dynamic  — the selection is re-checked daily but trades only when
               the holding set actually changes (band hysteresis keeps
               turnover low; exits stop lagging the grid by up to 4 days).

Why not ICIR factor weighting (sector_rotation's approach): IC statistics
on a ~17-ETF cross-section are pure noise. Fixed rule-based scoring is
parameter-light, interpretable and harder to overfit — hence a separate
engine rather than extending SectorRotationEngine.

Output contract mirrors SectorRotationEngine.run(): the returned dict
carries {"portfolios": {date: {ticker: weight}}}, "ic_summary" ({}) and
"config" keys, so RotationBacktester consumes it unchanged (it only reads
those three). Prices must be dividend-ADJUSTED (hfq) — see
scripts/backfill_etf_klines.py; the cash ETF's adjusted series accrues its
yield, which makes it a self-consistent absolute-momentum hurdle.
"""

from __future__ import annotations

import logging
import math
from typing import Optional

import numpy as np
import pandas as pd

from .factors import build_close_panel

log = logging.getLogger(__name__)

# ── Defaults (all overridable; mirrored by the API/backtest params) ────────
# Tuned 2026-09-02 by the 3-layer grid search, then switched to the TOP1
# cell by decision (docs/etf-rotation-grid-search-plan.md 落地记录):
# classic 3/6/12-month dual-momentum windows with 70% weight on the 12m
# leg, fast (20d) vol estimator — it drives BOTH the score denominator
# and the target-vol covariance, i.e. quick de-risking in vol spikes.
TOP_N = 2                  # risk ETFs held (concentration beat 3/4 in search)
BUFFER_RANK = 3            # holding retained while rank ≤ TOP_N + 3
MOMENTUM_WINDOWS = (60, 120, 250)     # ≈ 3m / 6m / 12m
MOMENTUM_WEIGHTS = (0.15, 0.15, 0.7)  # long-window leg dominates (TOP1)
VOL_WINDOW = 20            # volatility estimator window (days)
ABS_WINDOW = 180           # absolute-momentum lookback (days)
HOLDING_PERIOD = 20        # rebalance cadence in trading days (monthly)


def compute_momentum_panels(
    close: pd.DataFrame,
    windows: tuple[int, ...] = MOMENTUM_WINDOWS,
    weights: tuple[float, ...] = MOMENTUM_WEIGHTS,
    vol_window: int = VOL_WINDOW,
) -> dict[str, pd.DataFrame]:
    """Raw / risk-adjusted momentum + volatility panels (date × ticker).

    raw      = Σ w_i × R_i                      (blended multi-window return)
    vol      = annualized rolling std of daily returns
    score    = raw / vol                        (NaN when either input is)
    """
    ret_panels = {w: close / close.shift(w) - 1.0 for w in windows}
    raw = sum(wgt * ret_panels[w] for w, wgt in zip(windows, weights))
    daily_ret = close.pct_change(fill_method=None)
    vol = daily_ret.rolling(vol_window, min_periods=vol_window).std() * math.sqrt(252)
    # Floor near-zero vol → NaN: a frozen/cash-like series (fp noise std
    # ~1e-17) must not produce an astronomical score and hijack the rank.
    score = raw / vol.where(vol > 1e-6)
    return {"raw": raw, "vol": vol, "score": score,
            **{f"r{w}": p for w, p in ret_panels.items()}}


def select_portfolio_at(
    dt,
    score: pd.DataFrame,
    abs_ret: pd.DataFrame,
    cash_ticker: str,
    prev_holdings: list[str],
    top_n: int = TOP_N,
    buffer_rank: int = BUFFER_RANK,
    use_abs_gate: bool = True,
    use_buffer: bool = True,
    blocked: Optional[set[str]] = None,
) -> tuple[dict[str, float], dict]:
    """Dual-momentum selection for ONE date. Returns ({ticker: weight}
    including the cash parking position, detail dict for display).

    Weight is per-slot 1/top_n — unfilled slots stay cash rather than
    inflating survivors ("不补弱者"), so weights always sum to 1.

    `blocked` (market-timing gate): tickers excluded from ranking on this
    date — neither retained nor entered. Blocked holdings free their slot
    to the best eligible name (or cash if none passes).
    """
    empty = ({cash_ticker: 1.0}, {"selected": [], "retained": [],
                                  "n_selected": 0, "cash_weight": 1.0})
    if dt not in score.index or dt not in abs_ret.index:
        return empty
    score_row = score.loc[dt].dropna()
    if blocked:
        score_row = score_row.drop(index=[t for t in blocked
                                           if t in score_row.index])
    if score_row.empty:
        return empty
    # mergesort → deterministic tie order (column order)
    ranked = score_row.sort_values(ascending=False, kind="mergesort")
    ranks = {t: i + 1 for i, t in enumerate(ranked.index)}

    abs_row = abs_ret.loc[dt]
    cash_ret = abs_row.get(cash_ticker)
    if use_abs_gate and cash_ret is not None and pd.notna(cash_ret):
        gate = {t: pd.notna(abs_row.get(t))
                and float(abs_row[t]) >= float(cash_ret)
                for t in ranked.index}
    else:  # A/B ablation knob: relative momentum only
        gate = {t: pd.notna(abs_row.get(t)) for t in ranked.index}

    eligible = [t for t in ranked.index if gate[t]]

    # Sticky retention: in-band holdings (rank ≤ top_n + buffer) take the
    # slots first; entrants (rank ≤ top_n) fill what is left. With
    # use_buffer=False the band collapses to top_n → naive top-N.
    band = top_n + buffer_rank if use_buffer else top_n
    retained = sorted(
        (t for t in prev_holdings
         if t in ranks and ranks[t] <= band and gate.get(t, False)),
        key=lambda t: ranks[t])[:top_n]

    selected = list(retained)
    for t in eligible:
        if len(selected) >= top_n:
            break
        if t not in selected and ranks[t] <= top_n:
            selected.append(t)

    if not selected:
        return empty
    w = 1.0 / top_n
    weights = {t: w for t in selected}
    cash_w = round(1.0 - w * len(selected), 6)
    if cash_w > 0:
        weights[cash_ticker] = cash_w
    detail = {
        "selected": selected,
        "retained": retained,
        "n_selected": len(selected),
        "cash_weight": 1.0 - w * len(selected),
    }
    return weights, detail


class EtfRotationEngine:
    """Dual-momentum portfolio constructor for the ETF pool.

    Usage:
        engine = EtfRotationEngine(cash_ticker="511990")
        result = engine.run(bars, start_date, end_date)
        # result["portfolios"]: {rebalance_date: {ticker: weight}}
    """

    def __init__(
        self,
        cash_ticker: str,
        top_n: int = TOP_N,
        buffer_rank: int = BUFFER_RANK,
        holding_period: int = HOLDING_PERIOD,
        windows: tuple[int, ...] = MOMENTUM_WINDOWS,
        weights: tuple[float, ...] = MOMENTUM_WEIGHTS,
        vol_window: int = VOL_WINDOW,
        abs_window: int = ABS_WINDOW,
        use_abs_gate: bool = True,
        use_buffer: bool = True,
        use_market_gate: bool = False,
        market_ticker: str = "510300",
        market_ma_window: int = 200,
        market_gate_tickers: Optional[set[str]] = None,
        rebalance_mode: str = "fixed",
        weight_mode: str = "equal",
        use_target_vol: bool = False,
        target_vol: float = 0.10,
    ):
        if len(windows) != len(weights):
            raise ValueError("windows/weights length mismatch")
        if abs_window not in windows:
            # abs panel is read off the r-panels; make sure it exists
            windows = windows + (abs_window,)
            weights = weights + (0.0,)
        if rebalance_mode not in ("fixed", "dynamic"):
            raise ValueError("rebalance_mode must be 'fixed' or 'dynamic'")
        if weight_mode not in ("equal", "risk_parity"):
            raise ValueError("weight_mode must be 'equal' or 'risk_parity'")
        if target_vol <= 0:
            raise ValueError("target_vol must be positive")
        self.cash_ticker = cash_ticker
        self.top_n = top_n
        self.buffer_rank = buffer_rank
        self.holding_period = holding_period
        self.windows = windows
        self.weights = weights
        self.vol_window = vol_window
        self.abs_window = abs_window
        self.use_abs_gate = use_abs_gate
        self.use_buffer = use_buffer
        self.use_market_gate = use_market_gate
        self.market_ticker = market_ticker
        self.market_ma_window = market_ma_window
        # None → gate every non-cash ticker; the service passes the
        # equity-like subset (宽基+行业) so 防守 (国债/黄金/纳指) stay rankable.
        self.market_gate_tickers = market_gate_tickers
        self.rebalance_mode = rebalance_mode
        self.weight_mode = weight_mode
        self.use_target_vol = use_target_vol
        self.target_vol = target_vol

    def _apply_weight_mode(
        self,
        dt,
        weights: dict[str, float],
        detail: dict,
        daily_ret: pd.DataFrame,
        vol_panel: pd.DataFrame,
    ) -> dict[str, float]:
        """Post-process selection weights. Selection is untouched — only
        how the slots are sized changes.

        risk_parity: inverse-vol weights among the selected (w_i ∝ 1/σ_i);
        any pre-existing cash parking share is kept as-is. Falls back to
        equal weights when any member's vol is missing/degenerate.

        target_vol: estimate the portfolio's annualized vol from the
        vol_window covariance of daily returns; if it exceeds target_vol,
        scale all risk weights by target/σ (never lever up — long-only,
        min(1, ·)) and park the freed share in the cash ETF.
        """
        selected = detail.get("selected") or []
        if not selected:
            return weights
        cash_w = weights.get(self.cash_ticker, 0.0)

        if self.weight_mode == "risk_parity":
            vols: dict[str, float] = {}
            valid = True
            for t in selected:
                try:
                    v = vol_panel.at[dt, t]
                except KeyError:
                    valid = False
                    break
                if pd.isna(v) or float(v) <= 1e-6:
                    valid = False
                    break
                vols[t] = float(v)
            if valid:
                inv = {t: 1.0 / v for t, v in vols.items()}
                total = sum(inv.values())
                weights = {t: x / total for t, x in inv.items()}
                if cash_w > 0:
                    weights[self.cash_ticker] = cash_w

        if self.use_target_vol:
            risk_w = {t: w for t, w in weights.items()
                      if t != self.cash_ticker and w > 0}
            if risk_w:
                cols = [t for t in risk_w if t in daily_ret.columns]
                hist = (daily_ret.loc[:dt, cols]
                        .tail(self.vol_window).dropna())
                # Pairwise-complete covariance; demand a usable sample.
                if len(hist) >= self.vol_window // 2 and len(cols) == len(risk_w):
                    cov = hist.cov().values * 252.0
                    w_vec = np.array([risk_w[t] for t in hist.columns])
                    var = float(w_vec @ cov @ w_vec)
                    sigma = math.sqrt(max(var, 0.0))
                    if sigma > self.target_vol > 0:
                        k = self.target_vol / sigma
                        risk_total = sum(risk_w.values())
                        weights = {t: w * k for t, w in weights.items()}
                        weights[self.cash_ticker] = (
                            weights.get(self.cash_ticker, 0.0)
                            + (1.0 - k) * risk_total)
        return weights

    def run(
        self,
        bars: dict[str, pd.DataFrame],
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> dict:
        """Full pipeline: momentum panels → gate → buffered Top-N selection.

        Returns {panels, portfolios, selection_detail, latest, ic_summary,
        config} — the portfolios/ic_summary/config trio is the contract
        RotationBacktester reads.
        """
        if self.cash_ticker not in bars:
            raise ValueError(
                f"cash ETF {self.cash_ticker} missing from bars — pool/data "
                f"mismatch (run the ETF kline backfill first)")

        close = build_close_panel(bars)
        if start_date:
            close = close[close.index >= start_date]
        if end_date:
            close = close[close.index <= end_date]

        log.info("ETF rotation: computing momentum panels for %d tickers...",
                 close.shape[1])
        panels = compute_momentum_panels(
            close, self.windows, self.weights, self.vol_window)
        abs_ret = panels[f"r{self.abs_window}"]
        daily_ret = close.pct_change(fill_method=None)  # for target-vol cov

        # Market-timing gate: a boolean per-date Series from the market
        # proxy's close vs its own SMA. Below-MA dates block the
        # equity-like tickers; MA warm-up (NaN) counts as open — momentum
        # panels are NaN there anyway, so nothing trades on those days.
        market_ok: Optional[pd.Series] = None
        if self.use_market_gate:
            if self.market_ticker not in close.columns:
                raise ValueError(
                    f"market proxy {self.market_ticker} missing from bars — "
                    f"pool/data mismatch (run the ETF kline backfill first)")
            mkt = close[self.market_ticker]
            ma = mkt.rolling(self.market_ma_window,
                             min_periods=self.market_ma_window).mean()
            market_ok = mkt > ma

        def blocked_at(dt) -> Optional[set[str]]:
            """Tickers the market gate excludes on this date (None = open)."""
            if market_ok is None:
                return None
            ok = market_ok.get(dt)
            if ok is True or pd.isna(ok):
                return None
            gate_set = self.market_gate_tickers
            if gate_set is None:
                gate_set = set(close.columns) - {self.cash_ticker}
            return {t for t in gate_set if t in close.columns}

        # Same rebalance-grid convention as SectorRotationEngine.run.
        all_dates = list(close.index)

        portfolios: dict[str, dict[str, float]] = {}
        selection_detail: dict[str, dict] = {}
        prev_holdings: list[str] = []

        if self.rebalance_mode == "dynamic":
            # Dynamic rebalancing: the selection is re-checked EVERY day,
            # but a trade is recorded only when the holding set actually
            # changes (holding drops out of the retention band / fails the
            # gates / all-fail → cash). The band still provides the
            # hysteresis that keeps turnover low — this mode just removes
            # the up-to-(holding_period-1)-day lag of the fixed grid.
            for dt in all_dates:
                weights, detail = select_portfolio_at(
                    dt, panels["score"], abs_ret, self.cash_ticker,
                    prev_holdings, top_n=self.top_n,
                    buffer_rank=self.buffer_rank,
                    use_abs_gate=self.use_abs_gate,
                    use_buffer=self.use_buffer,
                    blocked=blocked_at(dt))
                weights = self._apply_weight_mode(
                    dt, weights, detail, daily_ret, panels["vol"])
                selected = detail["selected"]
                if set(selected) != set(prev_holdings):
                    portfolios[dt] = weights
                    selection_detail[dt] = detail
                    prev_holdings = selected
        else:
            for dt in all_dates[::self.holding_period]:
                weights, detail = select_portfolio_at(
                    dt, panels["score"], abs_ret, self.cash_ticker,
                    prev_holdings, top_n=self.top_n,
                    buffer_rank=self.buffer_rank,
                    use_abs_gate=self.use_abs_gate, use_buffer=self.use_buffer,
                    blocked=blocked_at(dt))
                weights = self._apply_weight_mode(
                    dt, weights, detail, daily_ret, panels["vol"])
                portfolios[dt] = weights
                selection_detail[dt] = detail
                prev_holdings = detail["selected"]

        # Daily "what would we hold today" snapshot: select at the latest
        # valid date using the holdings of the last recorded rebalance
        # before it as the buffer state.
        valid = panels["score"].dropna(how="all").index
        latest = valid[-1] if len(valid) else None
        latest_snapshot: dict = {"date": None, "weights": {}, "detail": {}}
        if latest is not None:
            prev_dates = [d for d in portfolios if d < latest]
            prev = selection_detail[prev_dates[-1]]["selected"] \
                if prev_dates else []
            w_now, d_now = select_portfolio_at(
                latest, panels["score"], abs_ret, self.cash_ticker, prev,
                top_n=self.top_n, buffer_rank=self.buffer_rank,
                use_abs_gate=self.use_abs_gate, use_buffer=self.use_buffer,
                blocked=blocked_at(latest))
            w_now = self._apply_weight_mode(
                latest, w_now, d_now, daily_ret, panels["vol"])
            latest_snapshot = {
                "date": latest, "weights": w_now, "detail": d_now,
                "prev_holdings": prev,
            }

        return {
            "panels": panels,
            "portfolios": portfolios,
            "selection_detail": selection_detail,
            "latest": latest_snapshot,
            # RotationBacktester reads these two keys — placeholders that
            # keep its result JSON intact (no factor ICs in this strategy).
            "ic_summary": {},
            "config": {
                "holding_period": self.holding_period,
                "top_n": self.top_n,
                "buffer_rank": self.buffer_rank,
                "windows": list(self.windows),
                "weights": list(self.weights),
                "vol_window": self.vol_window,
                "abs_window": self.abs_window,
                "use_abs_gate": self.use_abs_gate,
                "use_buffer": self.use_buffer,
                "use_market_gate": self.use_market_gate,
                "market_ticker": self.market_ticker,
                "market_ma_window": self.market_ma_window,
                "rebalance_mode": self.rebalance_mode,
                "weight_mode": self.weight_mode,
                "use_target_vol": self.use_target_vol,
                "target_vol": self.target_vol,
                "cash_ticker": self.cash_ticker,
            },
        }
