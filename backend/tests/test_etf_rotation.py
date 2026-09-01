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
        df = make_etf_bars(n=200, seed=3)
        close = df.set_index("date")["close"].to_frame("600001")
        panels = compute_momentum_panels(close)
        c = close["600001"]
        manual_raw = (0.2 * (c / c.shift(20) - 1)
                      + 0.3 * (c / c.shift(60) - 1)
                      + 0.5 * (c / c.shift(120) - 1))
        assert panels["raw"]["600001"].dropna().equals(
            manual_raw.dropna()) or np.allclose(
            panels["raw"]["600001"].dropna(), manual_raw.dropna())
        ret = close.pct_change(fill_method=None)["600001"]
        manual_vol = ret.rolling(60).std() * np.sqrt(252)
        assert np.allclose(panels["vol"]["600001"].dropna(),
                           manual_vol.dropna())
        assert np.allclose(panels["score"]["600001"].dropna(),
                           (manual_raw / manual_vol).dropna())

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
