"""Tests for the ETF dual-momentum rotation stack.

Layers covered:
  1. Pool config sanity (single cash ETF, enough risk members).
  2. Blended momentum formula + no-lookahead (perturb-future invariant).
  3. Absolute-momentum gate (all-weak universe → 100% cash; uptrend held).
  4. Rank buffer (sticky retention vs naive top-N) + gate ablation knob.
  5. Engine + RotationBacktester smoke on a synthetic universe.
  6. DB integration: scan_etf_signals persists ranking + portfolio rows.
"""

from __future__ import annotations

import sys
from datetime import date as date_cls
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from app.services.quant.etf_rotation import (
    EtfRotationEngine, compute_momentum_panels, select_portfolio_at,
)
from app.services.quant import etf_pool
from app.services.quant.rotation_backtest import RotationBacktester

BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


# ── Synthetic data helpers ──────────────────────────────────────────────────

CASH = "999001"


def make_etf_bars(n: int = 320, drift: float = 0.0, vol: float = 0.012,
                  seed: int = 7, start: str = "2024-01-01") -> pd.DataFrame:
    """Deterministic random-walk bars (price-only strategy: no fund flow)."""
    rng = np.random.default_rng(seed)
    dates = pd.date_range(start, periods=n, freq="B")
    if vol == 0.0:
        rets = np.full(n, drift)  # cash-like: smooth accrual, zero variance
    else:
        rets = rng.normal(drift, vol, n)
    close = 100 * np.exp(np.cumsum(rets))
    high = close * (1 + rng.uniform(0, 0.008, n))
    low = close * (1 - rng.uniform(0, 0.008, n))
    open_ = (high + low) / 2
    volume = rng.integers(1e6, 5e7, n).astype(float)
    return pd.DataFrame({
        "date": dates.strftime("%Y-%m-%d"),
        "open": open_, "high": high, "low": low, "close": close,
        "volume": volume, "amount": volume * close,
    })


def make_universe(n: int = 320) -> dict[str, pd.DataFrame]:
    """1 cash ETF (slow accrual) + 5 risk ETFs with distinct drifts."""
    bars = {CASH: make_etf_bars(n=n, drift=7e-5, vol=0.0, seed=1)}  # ~1.8%/yr
    bars["600001"] = make_etf_bars(n=n, drift=0.003, seed=11)   # strong up
    bars["600002"] = make_etf_bars(n=n, drift=0.001, seed=12)   # mild up
    bars["600003"] = make_etf_bars(n=n, drift=-0.001, seed=13)  # mild down
    bars["600004"] = make_etf_bars(n=n, drift=-0.003, seed=14)  # strong down
    bars["600005"] = make_etf_bars(n=n, drift=0.0005, seed=15)  # barely up
    return bars


def make_bearish_universe(n: int = 320) -> dict[str, pd.DataFrame]:
    bars = {CASH: make_etf_bars(n=n, drift=7e-5, vol=0.0, seed=1)}
    for i in range(4):
        bars[f"60000{i}"] = make_etf_bars(n=n, drift=-0.002, seed=20 + i)
    return bars


# ── 1. Pool config ──────────────────────────────────────────────────────────

class TestPoolConfig:

    def test_single_cash_enough_risk(self):
        assert etf_pool.get_cash_ticker() == "511990"
        risk = etf_pool.get_risk_tickers()
        assert len(risk) >= 5
        assert etf_pool.get_cash_ticker() not in risk
        all_t = etf_pool.get_all_tickers()
        assert set(all_t) == set(risk) | {etf_pool.get_cash_ticker()}
        # membership parity for RotationBacktester's sector_of() grouping
        for t, classes in etf_pool.get_membership().items():
            assert len(classes) == 1


# ── 2. Momentum formula + no-lookahead ──────────────────────────────────────

class TestMomentumPanels:

    def test_blended_formula(self):
        # Explicit params: the module defaults were retuned by the 2026-09
        # grid search — this test pins the FORMULA, not the defaults.
        df = make_etf_bars(n=200, seed=3)
        close = df.set_index("date")["close"].to_frame("600001")
        windows, weights, vw = (20, 60, 120), (0.2, 0.3, 0.5), 60
        panels = compute_momentum_panels(close, windows, weights, vw)
        c = close["600001"]
        manual_raw = (0.2 * (c / c.shift(20) - 1)
                      + 0.3 * (c / c.shift(60) - 1)
                      + 0.5 * (c / c.shift(120) - 1))
        assert np.allclose(panels["raw"]["600001"].dropna(),
                           manual_raw.dropna())
        ret = close.pct_change(fill_method=None)["600001"]
        manual_vol = ret.rolling(vw).std() * np.sqrt(252)
        assert np.allclose(panels["vol"]["600001"].dropna(),
                           manual_vol.dropna())
        assert np.allclose(panels["score"]["600001"].dropna(),
                           (manual_raw / manual_vol).dropna())

    def test_tuned_defaults_freeze(self):
        # Grid-search landing (docs/etf-rotation-grid-search-plan.md 落地记录):
        # the TOP1 cell by decision — classic 3/6/12m windows, 70% on the
        # 12m leg, fast 20d vol estimator, monthly cadence, 180d absolute
        # gate, buffer 3, 12% target vol, 4×ATR disaster brake.
        import app.services.quant.etf_rotation as er
        assert er.TOP_N == 2
        assert er.BUFFER_RANK == 3
        assert er.MOMENTUM_WINDOWS == (60, 120, 250)
        assert er.MOMENTUM_WEIGHTS == (0.15, 0.15, 0.7)
        assert er.VOL_WINDOW == 20
        assert er.ABS_WINDOW == 180
        assert er.HOLDING_PERIOD == 20
        from app.services.quant import etf_signal_service as svc
        assert svc.ATR_MULT == 4.0
        assert svc.USE_TARGET_VOL is True and svc.TARGET_VOL == 0.12

    def test_cash_zero_vol_scores_nan(self):
        df = make_etf_bars(n=200, drift=7e-5, vol=0.0, seed=1)
        close = df.set_index("date")["close"].to_frame(CASH)
        panels = compute_momentum_panels(close)
        assert panels["score"][CASH].dropna().empty  # 0-vol → NaN → not ranked

    def test_engine_no_lookahead(self):
        bars = make_universe()
        engine = EtfRotationEngine(cash_ticker=CASH, top_n=2)
        before = engine.run(bars)["portfolios"]
        # Perturb the last 60 bars of every risk ETF.
        cut = len(next(iter(bars.values()))) - 60
        for t, df in bars.items():
            if t == CASH:
                continue
            df.loc[df.index >= cut, "close"] *= 1.5
            df.loc[df.index >= cut, "high"] *= 1.5
        after = engine.run(bars)["portfolios"]
        dates_sorted = sorted(before)
        untouched = [d for d in dates_sorted if d < str(bars[CASH]["date"].iloc[cut])]
        assert len(untouched) >= 5
        for d in untouched:
            assert before[d] == after[d]


# ── 3. Absolute-momentum gate ───────────────────────────────────────────────

class TestAbsoluteGate:

    def test_bearish_universe_goes_all_cash(self):
        engine = EtfRotationEngine(cash_ticker=CASH, top_n=3)
        model = engine.run(make_bearish_universe())
        valid = [d for d, w in model["portfolios"].items() if w != {CASH: 1.0}]
        # After the 120d lookback warms up, everything must sit in cash.
        assert len(valid) == 0

    def test_uptrend_selected_no_cash(self):
        engine = EtfRotationEngine(cash_ticker=CASH, top_n=2)
        model = engine.run(make_universe())
        latest = model["latest"]
        assert latest["date"] is not None
        weights = latest["weights"]
        assert CASH not in weights or weights[CASH] == 0
        assert "600001" in weights and "600002" in weights  # two strongest
        assert sum(weights.values()) == pytest.approx(1.0)

    def test_gate_off_selects_weakest_too(self):
        # Ablation knob: relative-only still fills all slots (no cash floor).
        bars = make_bearish_universe()
        engine = EtfRotationEngine(cash_ticker=CASH, top_n=3, use_abs_gate=False)
        model = engine.run(bars)
        latest = model["latest"]["weights"]
        risk_held = [t for t in latest if t != CASH]
        assert len(risk_held) == 3


# ── 4. Rank buffer + selection unit rules ───────────────────────────────────

class TestSelection:

    @staticmethod
    def _panels(ranks: dict[str, int], cash_ret: float = 0.01,
                rets: float = 0.05) -> tuple[pd.DataFrame, pd.DataFrame]:
        dt = pd.Timestamp("2026-09-01")
        score = pd.DataFrame(
            [[{1: 3.0, 2: 2.5, 3: 2.0, 4: 1.5, 5: 1.0, 6: 0.5}[r] for r in ranks.values()]],
            index=[dt], columns=list(ranks))
        abs_ret = pd.DataFrame(
            [[rets for _ in ranks] + [cash_ret]],
            index=[dt], columns=list(ranks) + [CASH])
        return score, abs_ret

    def test_buffer_retains_in_band_holding(self):
        ranks = {"A": 1, "B": 2, "D": 3, "C": 4, "E": 5, "F": 6}
        score, abs_ret = self._panels(ranks)
        # Held {A,B,C}; C dropped to rank 4 (inside top_n+2) → kept, D blocked.
        w, detail = select_portfolio_at(
            pd.Timestamp("2026-09-01"), score, abs_ret, CASH,
            ["A", "B", "C"], top_n=3, buffer_rank=2)
        assert set(w) == {"A", "B", "C"}
        assert detail["retained"] == ["A", "B", "C"]

    def test_no_buffer_is_naive_top_n(self):
        ranks = {"A": 1, "B": 2, "D": 3, "C": 4, "E": 5, "F": 6}
        score, abs_ret = self._panels(ranks)
        w, _ = select_portfolio_at(
            pd.Timestamp("2026-09-01"), score, abs_ret, CASH,
            ["A", "B", "C"], top_n=3, buffer_rank=2, use_buffer=False)
        assert set(w) == {"A", "B", "D"}

    def test_out_of_band_holding_released(self):
        ranks = {"A": 1, "B": 2, "D": 3, "E": 4, "F": 5, "C": 6}
        score, abs_ret = self._panels(ranks)
        # C fell to rank 6 (> top_n+2) → released, D enters.
        w, detail = select_portfolio_at(
            pd.Timestamp("2026-09-01"), score, abs_ret, CASH,
            ["A", "B", "C"], top_n=3, buffer_rank=2)
        assert set(w) == {"A", "B", "D"}
        assert "C" not in detail["retained"]

    def test_gate_blocks_weak_earner(self):
        ranks = {"A": 1, "B": 2, "C": 3, "D": 4, "E": 5, "F": 6}
        # C's 120d return (0.005) < cash (0.01) → gated out; slot parks cash.
        score, abs_ret = self._panels(ranks, cash_ret=0.01, rets=0.05)
        abs_ret.loc[pd.Timestamp("2026-09-01"), "C"] = 0.005
        w, _ = select_portfolio_at(
            pd.Timestamp("2026-09-01"), score, abs_ret, CASH, [], top_n=3)
        assert set(w) == {"A", "B", CASH}
        assert w[CASH] == pytest.approx(1 / 3)

    def test_empty_slots_park_cash(self):
        ranks = {"A": 1, "B": 2, "C": 3}
        score = pd.DataFrame([[3.0, 2.0, 1.0]], index=[pd.Timestamp("2026-09-01")],
                             columns=["A", "B", "C"])
        abs_ret = pd.DataFrame([[0.05, 0.05, 0.05, 0.01]],
                               index=[pd.Timestamp("2026-09-01")],
                               columns=["A", "B", "C", CASH])
        w, _ = select_portfolio_at(
            pd.Timestamp("2026-09-01"), score, abs_ret, CASH, [], top_n=5)
        assert w[CASH] == pytest.approx(2 / 5)  # 3 of 5 slots filled


# ── 4b. Event-driven replacement (exit → same-day refill) ──────────────────

class TestPickReplacement:

    def test_replacement_rules(self):
        """Rank/band/gate/exclusion rules of the mid-cycle refill."""
        dt = pd.Timestamp("2026-09-01")
        tickers = ["A", "B", "C", "D", "E", "F"]
        score = pd.DataFrame(
            [[6.0, 5.0, 4.0, 3.0, 2.0, 1.0]], index=[dt], columns=tickers)
        abs_ret = pd.DataFrame(
            [[0.05, 0.05, 0.05, 0.005, 0.05, 0.05, 0.01],
             [0.05, 0.05, 0.05, 0.005, 0.05, 0.05, 0.01]],
            index=[dt, dt - pd.Timedelta(days=1)],
            columns=tickers + [CASH])
        engine = EtfRotationEngine(cash_ticker=CASH, top_n=2, buffer_rank=3)
        engine._repl_ctx = (score, abs_ret, None, None, None)

        # A exited today, B held: replacement = C (rank 3 ≤ band 5, passes
        # gate). D (rank 4) is gated out (0.005 < cash 0.01); A excluded.
        picks = engine.pick_replacement(dt, ["B"], {"A"})
        assert list(picks) == ["C"]
        assert 0 < picks["C"] <= 0.5  # ≤ 1/top_n (vol-scaled)

        # No exit today → no refill.
        assert engine.pick_replacement(dt, ["A", "B"], set()) == {}

        # Cash-only exit → no refill.
        assert engine.pick_replacement(dt, ["A", "B"], {CASH}) == {}

        # Portfolio already full → no refill.
        assert engine.pick_replacement(dt, ["B", "C"], {"A"}) == {}

        # C gated out too → E (rank 5, exactly at band edge) steps in.
        abs_ret.loc[dt, "C"] = 0.005
        assert list(engine.pick_replacement(dt, ["B"], {"A"})) == ["E"]

        # All band candidates gated → no refill (F rank 6 is outside band).
        abs_ret.loc[dt, "E"] = 0.005
        assert engine.pick_replacement(dt, ["B"], {"A"}) == {}

    def test_defensive_replacement_universe(self):
        """replacement_tickers: designated parking universe — best
        gate-passer from the set regardless of cross-sectional rank."""
        dt = pd.Timestamp("2026-09-01")
        tickers = ["A", "B", "C", "D", "E", "F"]
        score = pd.DataFrame(
            [[6.0, 5.0, 4.0, 3.0, 2.0, 1.0]], index=[dt], columns=tickers)
        abs_ret = pd.DataFrame(
            [[0.05, 0.05, 0.05, 0.05, 0.05, 0.005, 0.01]],
            index=[dt], columns=tickers + [CASH])
        engine = EtfRotationEngine(cash_ticker=CASH, top_n=2, buffer_rank=3,
                                   replacement_tickers={"E", "F"})
        engine._repl_ctx = (score, abs_ret, None, None, None)

        # F is rank 6 (way outside band) but the designated universe picks
        # by score — except F fails the cash-hurdle gate → E picked.
        picks = engine.pick_replacement(dt, ["A"], {"B"})
        assert list(picks) == ["E"]
        # E gated too → no refill (stay cash).
        abs_ret.loc[dt, "E"] = 0.005
        assert engine.pick_replacement(dt, ["A"], {"B"}) == {}

    def test_replacement_buys_off_rebalance_grid(self):
        """Integration: with the hook on, entries appear on non-grid dates."""
        bars = make_universe()
        engine = EtfRotationEngine(cash_ticker=CASH, top_n=2, holding_period=20)
        membership = {t: ["ETF"] for t in bars}
        base = RotationBacktester(stamp_duty_rate=0.0, stop_mode="atr",
                                  atr_mult=4.0, breakdown_buffer=0.03)
        out0 = base.run(bars, membership, engine, initial_capital=1e6)
        repl = RotationBacktester(stamp_duty_rate=0.0, stop_mode="atr",
                                  atr_mult=4.0, breakdown_buffer=0.03,
                                  replacement_fn=engine.pick_replacement)
        out1 = repl.run(bars, membership, engine, initial_capital=1e6)
        dates = list(pd.Series({p["date"]: p["equity"]
                                for p in out0["result"]["equity_curve"]}).index)
        grid = set(dates[::20])
        off_grid = [t for t in out1["result"]["trades"]
                    if t["entry_date"] not in grid]
        assert off_grid, "expected same-day replacement entries off the grid"
        assert out1["result"]["trade_count"] >= out0["result"]["trade_count"]


# ── 4c. Calendar-anchored rebalancing (每月首个交易日) ─────────────────────

class TestCalendarAnchor:

    def test_anchor_dates_month_firsts(self):
        engine = EtfRotationEngine(cash_ticker=CASH, rebalance_anchor="calendar")
        dates = ["2026-08-03", "2026-08-04", "2026-08-29",
                 "2026-09-01", "2026-09-02", "2026-10-09"]
        assert engine._anchor_dates(dates) == \
            ["2026-08-03", "2026-09-01", "2026-10-09"]

    def test_calendar_start_inception(self):
        # Months before the inception date get NO anchor; the inception
        # month anchors on its first trading day ≥ inception.
        engine = EtfRotationEngine(cash_ticker=CASH,
                                   rebalance_anchor="calendar",
                                   calendar_start="2026-09-03")
        dates = ["2026-07-01", "2026-08-03", "2026-09-01", "2026-09-03",
                 "2026-09-04", "2026-10-09"]
        assert engine._anchor_dates(dates) == ["2026-09-03", "2026-10-09"]

    def test_grid_anchor_unchanged(self):
        engine = EtfRotationEngine(cash_ticker=CASH)  # default grid
        dates = [str(i) for i in range(10)]
        assert engine._anchor_dates(dates) == dates[::20]

    def test_latest_frozen_between_anchors(self):
        """Non-anchor days carry the last anchor's portfolio (backtest
        parity: no mid-month re-selection)."""
        bars = make_universe()
        engine = EtfRotationEngine(cash_ticker=CASH, top_n=2,
                                   rebalance_anchor="calendar")
        model = engine.run(bars)
        anchors = sorted(model["portfolios"])
        latest = model["latest"]["date"]
        if latest in model["portfolios"]:      # latest happens to be an anchor
            assert model["latest"]["weights"] == model["portfolios"][latest]
        else:
            last_anchor = [a for a in anchors if a <= latest][-1]
            assert model["latest"]["anchor"] == last_anchor
            assert model["latest"]["weights"] == model["portfolios"][last_anchor]
        # anchors are month-first business days
        months = [a[:7] for a in anchors]
        assert len(months) == len(set(months))


# ── 4d. Weekly-anchored rebalancing (短线版周频锚点) ─────────────────────────

class TestWeeklyAnchor:

    def test_anchor_dates_weekly_lasts(self):
        # 2026-08-03 is a Monday: three partial/full ISO weeks, each
        # anchoring on its LAST panel date (a Friday when the week is
        # complete, mid-week when the tail is cut).
        engine = EtfRotationEngine(cash_ticker=CASH, rebalance_anchor="weekly")
        dates = ["2026-08-03", "2026-08-04", "2026-08-05", "2026-08-06",
                 "2026-08-07", "2026-08-10", "2026-08-11", "2026-08-12",
                 "2026-08-17", "2026-08-18"]
        assert engine._anchor_dates(dates) == \
            ["2026-08-07", "2026-08-12", "2026-08-18"]

    def test_weekly_anchor_spans_year_boundary(self):
        # 2024-12-30 (Mon), 12-31 and 2025-01-02, 01-03 share ISO week
        # 2025-W1 (01-01 holiday) → exactly ONE anchor.
        engine = EtfRotationEngine(cash_ticker=CASH, rebalance_anchor="weekly")
        dates = ["2024-12-30", "2024-12-31", "2025-01-02", "2025-01-03"]
        assert engine._anchor_dates(dates) == ["2025-01-03"]

    def test_weekly_anchor_inception(self):
        # Weeks entirely before the inception date get NO anchor; the
        # inception week anchors on its last panel date.
        engine = EtfRotationEngine(cash_ticker=CASH,
                                   rebalance_anchor="weekly",
                                   calendar_start="2026-08-10")
        dates = ["2026-08-03", "2026-08-04", "2026-08-05", "2026-08-06",
                 "2026-08-07", "2026-08-10", "2026-08-11", "2026-08-12"]
        assert engine._anchor_dates(dates) == ["2026-08-12"]

    def test_latest_frozen_between_weekly_anchors(self):
        bars = make_universe()
        engine = EtfRotationEngine(cash_ticker=CASH, top_n=2,
                                   rebalance_anchor="weekly")
        model = engine.run(bars)
        anchors = sorted(model["portfolios"])
        # exactly one anchor per ISO week
        weeks = [date_cls.fromisoformat(d).isocalendar()[:2] for d in anchors]
        assert len(weeks) == len(set(weeks))
        latest = model["latest"]["date"]
        if latest not in model["portfolios"]:
            last_anchor = [a for a in anchors if a <= latest][-1]
            assert model["latest"]["anchor"] == last_anchor
            assert model["latest"]["weights"] == model["portfolios"][last_anchor]


# ── 4e. MA20 trend-confirmation entry filter (短线版) ────────────────────────

class TestTrendFilter:

    def test_trend_filter_blocks_falling_ma20(self):
        bars = make_universe()
        # Force 600004 into a clean breakdown: strictly lower closes over
        # the last 80 bars → below a falling MA20 at every late anchor.
        df = bars["600004"]
        n, tail = len(df), 80
        base = df.iloc[n - tail - 1]["close"]
        for k in range(tail):
            df.loc[df.index[n - tail + k], "close"] = base * (1 - 0.004 * (k + 1))
        kw = dict(cash_ticker=CASH, top_n=5, use_abs_gate=False,
                  rebalance_anchor="grid", holding_period=5)
        on = EtfRotationEngine(use_trend_filter=True, **kw)
        late = [w for d, w in on.run(bars)["portfolios"].items()
                if d >= bars[CASH]["date"].iloc[n - 40]]
        assert late
        for w in late:
            assert "600004" not in w
        # Filter off + relative-only + top_n=5 → every slot fills, the
        # broken name included.
        off = EtfRotationEngine(**kw)
        late_off = [w for d, w in off.run(bars)["portfolios"].items()
                    if d >= bars[CASH]["date"].iloc[n - 40]]
        assert any("600004" in w for w in late_off)

    def test_replacement_respects_trend_filter(self):
        dt = pd.Timestamp("2026-09-01")
        tickers = ["A", "B", "C", "D", "E", "F"]
        score = pd.DataFrame(
            [[6.0, 5.0, 4.0, 3.0, 2.0, 1.0]], index=[dt], columns=tickers)
        abs_ret = pd.DataFrame(
            [[0.05] * 6 + [0.01]], index=[dt], columns=tickers + [CASH])
        trend_ok = pd.DataFrame(
            [[True, True, False, True, True, True]],
            index=[dt], columns=tickers)
        engine = EtfRotationEngine(cash_ticker=CASH, top_n=2, buffer_rank=3,
                                   use_trend_filter=True)
        engine._repl_ctx = (score, abs_ret, None, None, trend_ok)
        # C is the next-best by rank but below its MA20 → D steps in.
        assert list(engine.pick_replacement(dt, ["B"], {"A"})) == ["D"]


# ── 4f. Portfolio circuit breaker (研究开关) ─────────────────────────────────

class TestCircuitBreaker:

    def test_breaker_liquidates_bear_and_cools_down(self):
        # Bear universe + relative-only selection keeps the book invested
        # while it grinds down (-0.4%/day); per-position exits are
        # disabled (huge ATR mult, huge breakdown buffer) so ONLY the
        # breaker can act.
        bars = {CASH: make_etf_bars(n=500, drift=7e-5, vol=0.0, seed=1)}
        for i in range(4):
            bars[f"60000{i}"] = make_etf_bars(n=500, drift=-0.004,
                                              seed=30 + i)
        engine = EtfRotationEngine(cash_ticker=CASH, top_n=2,
                                   use_abs_gate=False)
        membership = {t: ["ETF"] for t in bars}
        bt = RotationBacktester(stamp_duty_rate=0.0, stop_mode="atr",
                                atr_mult=100.0, breakdown_buffer=0.90,
                                circuit_breaker_drawdown=0.20,
                                circuit_breaker_cooldown=10)
        out = bt.run(bars, membership, engine, initial_capital=1e6)
        r = out["result"]
        assert r["circuit_breaker_events"], "breaker never fired in a bear"
        cb_trades = [t for t in r["trades"]
                     if t["exit_reason"] == "circuit_breaker"]
        assert cb_trades, "no circuit_breaker exits recorded"
        # Finite completion + no re-trigger loop is implied by finishing.
        assert np.isfinite(r["final_equity"]) and r["final_equity"] > 0

    def test_breaker_off_by_default(self):
        bars = make_bearish_universe(n=500)
        engine = EtfRotationEngine(cash_ticker=CASH, top_n=2,
                                   use_abs_gate=False)
        membership = {t: ["ETF"] for t in bars}
        bt = RotationBacktester(stamp_duty_rate=0.0, stop_mode="atr",
                                atr_mult=100.0, breakdown_buffer=0.90)
        out = bt.run(bars, membership, engine, initial_capital=1e6)
        assert out["result"]["circuit_breaker_events"] == []


# ── 4g. Market-gate numpy-bool regression + cash-proxy stop exemption ───────

class TestMarketGateBool:

    def test_open_gate_selects_equity_names(self):
        # Regression: market_ok holds numpy.bool_ — a bare `ok is True`
        # was False for np.True_, blocking equity-like names EVERY day
        # the gate was enabled (first exposed by the short-rotation
        # weekly backtest). Proxy in a steady uptrend → gate OPEN → the
        # strong names must actually be selected.
        bars = make_universe()
        gated = {"600001", "600002", "600003", "600004", "600005"}
        engine = EtfRotationEngine(
            cash_ticker=CASH, top_n=2, use_market_gate=True,
            market_ticker="600001", market_ma_window=200,
            market_gate_tickers=gated)
        weights = engine.run(bars)["latest"]["weights"]
        risk_held = [t for t in weights if t != CASH]
        assert risk_held, ("gate-open day selected nothing — "
                           "numpy.bool_ regression is back")

    def test_closed_gate_blocks_equity_names(self):
        bars = make_universe()
        gated = {"600001", "600002", "600003", "600004", "600005"}
        engine = EtfRotationEngine(
            cash_ticker=CASH, top_n=2, use_market_gate=True,
            market_ticker="600004",  # strong downtrend → below MA200
            market_ma_window=200, market_gate_tickers=gated)
        weights = engine.run(bars)["latest"]["weights"]
        assert weights == {CASH: 1.0}


class TestCashProxyStopExemption:

    @staticmethod
    def _crashing_cash_universe(n=300):
        """Bearish risk names + a 'money' ETF that gaps down 30% mid-
        sample: with the exemption off the parked cash position gets
        stopped out; with it on the parking is never risk-managed."""
        bars = make_bearish_universe(n=n)
        cash = make_etf_bars(n=n, drift=0.0, vol=0.0, seed=9)
        for col in ("open", "high", "low", "close"):
            cash.loc[cash.index >= 150, col] *= 0.7
        bars[CASH] = cash
        return bars

    def test_cash_position_not_stopped(self):
        bars = self._crashing_cash_universe()
        engine = EtfRotationEngine(cash_ticker=CASH, top_n=2,
                                   windows=(20, 60), weights=(0.6, 0.4),
                                   abs_window=60, holding_period=5)
        membership = {t: ["ETF"] for t in bars}
        bt = RotationBacktester(stamp_duty_rate=0.0, stop_mode="atr",
                                atr_mult=1.0, breakdown_buffer=0.03,
                                cash_tickers={CASH})
        trades = bt.run(bars, membership, engine,
                        initial_capital=1e6)["result"]["trades"]
        cash_exits = {t["exit_reason"] for t in trades if t["ticker"] == CASH}
        assert cash_exits <= {"rebalance", "end"}, cash_exits

    def test_legacy_cash_position_stops(self):
        # Negative control: without the exemption the same crash DOES
        # stop the parked position out (the test can see the bug).
        bars = self._crashing_cash_universe()
        engine = EtfRotationEngine(cash_ticker=CASH, top_n=2,
                                   windows=(20, 60), weights=(0.6, 0.4),
                                   abs_window=60, holding_period=5)
        membership = {t: ["ETF"] for t in bars}
        bt = RotationBacktester(stamp_duty_rate=0.0, stop_mode="atr",
                                atr_mult=1.0, breakdown_buffer=0.03)
        trades = bt.run(bars, membership, engine,
                        initial_capital=1e6)["result"]["trades"]
        cash_exits = {t["exit_reason"] for t in trades if t["ticker"] == CASH}
        assert "stop_loss" in cash_exits or "breakdown" in cash_exits


# ── 5. Engine + backtester smoke ────────────────────────────────────────────

class TestBacktestSmoke:

    def test_rotation_backtester_on_etf_engine(self):
        bars = make_universe()
        engine = EtfRotationEngine(cash_ticker=CASH, top_n=2)
        membership = {t: ["ETF"] for t in bars}
        bt = RotationBacktester(stamp_duty_rate=0.0, stop_mode="atr",
                                atr_mult=2.0, breakdown_buffer=0.03)
        out = bt.run(bars, membership, engine, initial_capital=1e6)
        r = out["result"]
        assert np.isfinite(r["final_equity"]) and r["final_equity"] > 0
        assert len(r["equity_curve"]) > 200
        assert r["benchmark_total_return_pct"] != 0.0
        # Cash parking must appear somewhere across the warm-up phase.
        cash_dates = [
            d for d, w in out["model"]["portfolios"].items()
            if w.get(CASH, 0) > 0]
        assert cash_dates  # warm-up weeks are 100% cash by construction


# ── 6. DB integration: scan service ─────────────────────────────────────────

class TestScanService:

    @pytest.fixture
    def db_session(self):
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from app.db import Base
        from app.models import chain_models  # noqa: F401 register tables

        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        session = sessionmaker(bind=engine)()
        yield session
        session.close()

    def test_scan_persists_rows(self, db_session, monkeypatch):
        from app.models.chain_models import DailyBar, EtfSignal
        from app.services.quant import etf_signal_service

        bars = make_universe()
        for t, df in bars.items():
            for _, r in df.iterrows():
                db_session.add(DailyBar(
                    ticker=t, date=date_cls.fromisoformat(r["date"]),
                    open=r["open"], high=r["high"], low=r["low"],
                    close=r["close"], volume=r["volume"], amount=r["amount"]))
        db_session.commit()

        risk = [t for t in bars if t != CASH]
        monkeypatch.setattr(etf_pool, "get_all_tickers",
                            lambda: sorted(bars))
        monkeypatch.setattr(etf_pool, "get_cash_ticker", lambda: CASH)
        monkeypatch.setattr(
            etf_pool, "get_names",
            lambda: {t: f"ETF{t}" for t in bars})
        monkeypatch.setattr(
            etf_pool, "get_asset_classes",
            lambda: {t: ("货币" if t == CASH else "宽基") for t in bars})
        # Calendar anchors are gated on the real inception (2026-09-03);
        # the synthetic universe lives in 2024-2025 — shift inception into
        # its range so the scan has anchors.
        monkeypatch.setattr(etf_signal_service, "STRATEGY_INCEPTION",
                            bars[CASH]["date"].iloc[0])

        result = etf_signal_service.scan_etf_signals(db_session, top_n=2)
        assert result["scanned"] == len(risk)
        assert 1 <= result["selected"] <= 2
        assert result["cash_weight"] >= 0

        sigs = db_session.query(EtfSignal).all()
        assert len(sigs) == len(bars)  # every risk ETF + cash row
        selected = [s for s in sigs if s.is_selected and s.ticker != CASH]
        assert len(selected) == result["selected"]
        for s in selected:
            assert s.weight > 0 and s.stop_price is not None
        cash_rows = [s for s in sigs if s.ticker == CASH]
        assert len(cash_rows) == 1
        assert cash_rows[0].is_selected == (result["cash_weight"] > 0)

        # Query layer round-trip.
        snap = etf_signal_service.get_latest_scores(db_session)
        assert snap["date"] is not None
        assert len(snap["etfs"]) == len(bars)
        port = etf_signal_service.get_latest_portfolio(db_session)
        assert len(port["holdings"]) == result["selected"] + (
            1 if result["cash_weight"] > 0 else 0)
