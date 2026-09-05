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
from datetime import date
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
# MA20 trend-confirmation entry filter (short-rotation preset): an ETF is
# only eligible while it closes above a RISING MA20. Fixed per the design
# doc (§二 辅助因子) — not exposed as separate knobs.
TREND_MA_WINDOW = 20
TREND_SLOPE_WINDOW = 5     # MA20 > MA20[5d ago] defines "rising"


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
        use_trend_filter: bool = False,
        replacement_tickers: Optional[set[str]] = None,
        rebalance_mode: str = "fixed",
        rebalance_anchor: str = "grid",
        calendar_start: Optional[str] = None,
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
        if rebalance_anchor not in ("grid", "calendar", "weekly"):
            raise ValueError(
                "rebalance_anchor must be 'grid', 'calendar' or 'weekly'")
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
        # equity-like subset (宽基+行业) so 防守 (国债/黄金/红利) stay rankable.
        self.market_gate_tickers = market_gate_tickers
        # MA20 trend-confirmation entry filter (short-rotation preset):
        # while on, an ETF below a falling MA20 is ineligible — neither
        # selected nor retained (blocked-holding semantics: the slot frees
        # for the best eligible name, same as the market gate). Warm-up
        # (MA20/slope not yet formed) counts as blocked — conservative.
        self.use_trend_filter = use_trend_filter
        # Mid-cycle replacement candidate restriction (None = whole pool
        # with band rules). When set (e.g. the defensive class), the
        # refill semantics change to "upgraded cash parking": the best
        # gate-passing member of the set by score, regardless of overall
        # cross-sectional rank — the freed slot parks in defense instead
        # of the money ETF, not a bet on rotation rank.
        self.replacement_tickers = replacement_tickers
        self.rebalance_mode = rebalance_mode
        self.rebalance_anchor = rebalance_anchor
        # calendar anchors: first trading day of each month on/after this
        # ISO date (strategy inception — the month of inception anchors on
        # its first trading day ≥ inception, e.g. 2026-09-03). None → all
        # months in the panel (backtest).
        self.calendar_start = calendar_start
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

    def _anchor_dates(self, all_dates: list) -> list:
        """Rebalance dates for fixed mode.

        "grid"     — every holding_period-th trading day from the panel
                     start (legacy; phase drifts with the sliding data
                     window, ±15pct full-window variance measured).
        "calendar" — the FIRST TRADING DAY of each month: a stable,
                     calendar-meaningful cadence ("rebalance on the first
                     trading day of each month"), immune to window phase.
                     calendar_start restricts anchors to months on/after
                     the strategy inception date.
        "weekly"   — the LAST TRADING DAY of each ISO week (short-rotation
                     preset: signal + fills at the week's final close).
                     Holiday-shortened weeks anchor on their actual last
                     session, computed retrospectively from the panel — a
                     live Thursday scan before a holiday Friday sees
                     Thursday as the week's last session and fires the
                     same day. calendar_start restricts anchors to weeks
                     on/after the inception date.
        """
        if self.rebalance_anchor == "grid":
            return all_dates[::self.holding_period]
        if self.rebalance_anchor == "weekly":
            anchors: list = []
            cur_week, pending = None, None
            for d in all_dates:
                if self.calendar_start and d < self.calendar_start:
                    continue
                week = date.fromisoformat(d).isocalendar()[:2]
                if week != cur_week:
                    if pending is not None:
                        anchors.append(pending)
                    cur_week = week
                pending = d
            if pending is not None:
                anchors.append(pending)
            return anchors
        anchors, last_month = [], None
        for d in all_dates:
            if self.calendar_start and d < self.calendar_start:
                continue
            month = d[:7]
            if month != last_month:
                anchors.append(d)
                last_month = month
        return anchors

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
        # MA20 trend-confirmation panel (boolean): close above a rising
        # MA20. NaN comparisons fold to False → warm-up counts as blocked.
        trend_ok: Optional[pd.DataFrame] = None
        if self.use_trend_filter:
            ma = close.rolling(TREND_MA_WINDOW,
                               min_periods=TREND_MA_WINDOW).mean()
            ma_rising = ma > ma.shift(TREND_SLOPE_WINDOW)
            trend_ok = (close > ma) & ma_rising
        # Kept for pick_replacement(): mid-cycle slot refills after exits
        # (fixed cadence + event-driven replacement — see service layer).
        self._repl_ctx = (panels["score"], abs_ret, daily_ret,
                          panels["vol"], trend_ok)

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
            """Tickers excluded from ranking on this date (None = all open).

            Union of the market gate (equity-like subset below the market
            MA) and the trend filter (any non-cash ticker below a falling
            MA20). Blocked holdings free their slot to the best eligible
            name — same semantics for both gates.
            """
            blocked: Optional[set[str]] = None
            if market_ok is not None:
                ok = market_ok.get(dt)
                # bool(ok): market_ok holds numpy.bool_ — a bare `ok is
                # True` is False for np.True_ and would block equity-like
                # names EVERY day the gate is on (regression, caught by
                # the short-rotation weekly backtest).
                if not (pd.isna(ok) or bool(ok)):
                    gate_set = self.market_gate_tickers
                    if gate_set is None:
                        gate_set = set(close.columns) - {self.cash_ticker}
                    blocked = {t for t in gate_set if t in close.columns}
            if trend_ok is not None:
                if dt in trend_ok.index:
                    row = trend_ok.loc[dt]
                    failed = {t for t in close.columns
                              if t != self.cash_ticker
                              and not bool(row.get(t, False))}
                else:  # date outside the panel → nothing eligible anyway
                    failed = set(close.columns) - {self.cash_ticker}
                blocked = failed if blocked is None else blocked | failed
            return blocked

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
            for dt in self._anchor_dates(all_dates):
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

        # Daily "what would we hold today" snapshot.
        valid = panels["score"].dropna(how="all").index
        latest = valid[-1] if len(valid) else None
        latest_snapshot: dict = {"date": None, "weights": {}, "detail": {}}
        if latest is not None:
            if (self.rebalance_anchor in ("calendar", "weekly")
                    and latest not in portfolios):
                # Calendar/weekly anchors freeze the portfolio between
                # rebalance dates (backtest parity): the in-force
                # recommendation on a non-anchor day is the last anchor's
                # portfolio, NOT a fresh selection. Mid-cycle exits and
                # defensive replacement are handled by the daily exit
                # rules, not re-selection.
                anchors_le = [d for d in portfolios if d <= latest]
                if anchors_le:
                    a = anchors_le[-1]
                    latest_snapshot = {
                        "date": latest, "anchor": a,
                        "weights": portfolios[a],
                        "detail": selection_detail[a],
                        "prev_holdings": selection_detail[a]["selected"],
                    }
            else:
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
                "use_trend_filter": self.use_trend_filter,
                "rebalance_mode": self.rebalance_mode,
                "rebalance_anchor": self.rebalance_anchor,
                "calendar_start": self.calendar_start,
                "weight_mode": self.weight_mode,
                "use_target_vol": self.use_target_vol,
                "target_vol": self.target_vol,
                "cash_ticker": self.cash_ticker,
            },
        }

    def pick_replacement(
        self,
        dt,
        held_positions: list[str],
        exited_today: set[str],
    ) -> dict[str, float]:
        """Event-driven slot refill: after a risk ETF exits mid-cycle, pick
        the next-best eligible replacement the SAME day instead of parking
        in cash until the next scheduled rebalance.

        Rules mirror the scheduled selection (same gate + band semantics):
        candidates must (a) not be held, (b) not have exited today, (c)
        rank ≤ top_n + buffer (band width — a slot opened by an exit, so
        band-level entrants are consistent with the sticky buffer), (d)
        pass the absolute-momentum gate and — when the trend filter is on —
        the MA20 trend-confirmation filter. With replacement_tickers
        set (defensive parking), (c) is dropped and candidates come only
        from that set — best gate-passer by score, "upgraded cash
        parking" semantics (a defensive name below a falling MA20 fails
        (d) → the slot stays in the money ETF). Buys are sized at 1/top_n
        per slot, then target-vol scaled like a normal rebalance. Cash
        exits don't trigger refills; market-gate overlay not applied
        (defensive names are never market-gated).

        Called by RotationBacktester's replacement_fn hook; requires
        run() to have been called first (panel context).
        """
        if not hasattr(self, "_repl_ctx"):
            return {}
        score, abs_ret, daily_ret, vol_panel, trend_ok = self._repl_ctx
        exited_risk = {t for t in exited_today if t != self.cash_ticker}
        if not exited_risk:
            return {}
        held = [t for t in held_positions if t != self.cash_ticker]
        n_slots = self.top_n - len(held)
        if n_slots <= 0 or dt not in score.index or dt not in abs_ret.index:
            return {}

        score_row = score.loc[dt].dropna()
        if score_row.empty:
            return {}
        ranked = score_row.sort_values(ascending=False, kind="mergesort")
        ranks = {t: i + 1 for i, t in enumerate(ranked.index)}
        abs_row = abs_ret.loc[dt]
        cash_ret = abs_row.get(self.cash_ticker)

        exclude = set(held) | exited_risk | {self.cash_ticker}
        gate_pass = lambda t: (  # noqa: E731 — gate with cash-hurdle fallback
            pd.notna(abs_row.get(t))
            and (not self.use_abs_gate
                 or (cash_ret is not None and pd.notna(cash_ret)
                     and float(abs_row[t]) >= float(cash_ret)))
            and (not self.use_trend_filter or trend_ok is None
                 or (dt in trend_ok.index and t in trend_ok.columns
                     and bool(trend_ok.at[dt, t]))))

        if self.replacement_tickers is not None:
            # Designated parking universe ("upgraded cash parking"): the
            # best gate-passing member by score, regardless of overall
            # rank — the slot parks in defense, not a rank bet.
            picks = [t for t in ranked.index
                     if t in self.replacement_tickers
                     and t not in exclude and gate_pass(t)][:n_slots]
        else:
            band = (self.top_n + self.buffer_rank
                    if self.use_buffer else self.top_n)
            picks = [t for t in ranked.index
                     if t not in exclude and ranks[t] <= band
                     and gate_pass(t)][:n_slots]
        if not picks:
            return {}

        # Size like a normal rebalance: full would-be portfolio at 1/top_n
        # per slot, then target-vol / weight-mode scaling on the whole.
        weights = {t: 1.0 / self.top_n for t in held + picks}
        detail = {"selected": held + picks}
        weights = self._apply_weight_mode(dt, weights, detail,
                                          daily_ret, vol_panel)
        # Return only the additions, at their scaled weights.
        return {t: weights[t] for t in picks if weights.get(t, 0) > 0}
