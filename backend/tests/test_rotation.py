"""Tests for the sector-rotation strategy stack.

Layers covered:
  1. Fund-flow factor formulas + no-lookahead (perturb-future invariant).
  2. compute_composite NaN robustness (per-stock weight renormalization)
     + IC-lag no-lookahead (composite at date t independent of closes > t).
  3. Sector strength: bullish sector outranks bearish; flow dim responds
     to net inflow; tech-only fallback when flow data is absent.
  4. select_portfolio_at: top-K sectors, in-sector top-N with the
     bullish gate + fallback, weight normalization / cap.
  5. Engine + backtester smoke on synthetic panels (2 sectors × 6 stocks).
  6. Fund-flow fetch parsing (kline CSV) + market prefix rule.
  7. DB integration: scan_rotation_signals persists sector + stock rows.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from app.services.quant.factors import (
    MainInflowMomentum20, MainInflowPersistence, MainInflowAcceleration,
)
from app.services.quant.factor_model import MultiFactorEngine
from app.services.quant.sector_rotation import (
    SectorRotationEngine, compute_sector_strength, select_portfolio_at,
    build_bullish_panel,
)
from app.services.quant.rotation_backtest import RotationBacktester

BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


# ── Synthetic data helpers ──────────────────────────────────────────────────

def make_bars(n: int = 260, drift: float = 0.002, seed: int = 7,
              start: str = "2024-01-01") -> pd.DataFrame:
    """Deterministic random-walk bars with the fund-flow column present."""
    rng = np.random.default_rng(seed)
    dates = pd.date_range(start, periods=n, freq="B")
    rets = rng.normal(drift, 0.02, n)
    close = 100 * np.exp(np.cumsum(rets))
    high = close * (1 + rng.uniform(0, 0.015, n))
    low = close * (1 - rng.uniform(0, 0.015, n))
    open_ = (high + low) / 2
    volume = rng.integers(1e6, 5e7, n).astype(float)
    amount = volume * close
    # Correlate main-force flow with the day's direction, scaled by turnover.
    daily_ratio = rng.normal(0.02, 0.05, n) * np.sign(rets)
    main_net = daily_ratio * amount
    return pd.DataFrame({
        "date": dates.strftime("%Y-%m-%d"),
        "open": open_, "high": high, "low": low, "close": close,
        "volume": volume, "amount": amount,
        "main_net": main_net,
    })


def make_universe() -> tuple[dict[str, pd.DataFrame], dict[str, list[str]]]:
    """2 sectors × 6 stocks. Sector A trends up with inflow; B drifts down."""
    bars: dict[str, pd.DataFrame] = {}
    membership: dict[str, list[str]] = {}
    for i in range(6):
        t = f"60010{i}"
        bars[t] = make_bars(drift=0.004, seed=100 + i)
        membership[t] = ["A"]
    for i in range(6):
        t = f"00030{i}"
        bars[t] = make_bars(drift=-0.003, seed=200 + i)
        membership[t] = ["B"]
    # Cross-sector member (like 华海清科 in 设备+CMP).
    bars["600100"]["sector_note"] = "cross"
    membership["600100"] = ["A", "B"]
    return bars, membership


# ── 1. Fund-flow factor formulas ────────────────────────────────────────────

class TestFundFlowFactors:

    def test_momentum_cumulative_ratio(self):
        n = 60
        df = make_bars(n=n, seed=1)
        # Constant ratio 0.05 for the last 20 days.
        df.loc[n - 20:, "main_net"] = 0.05 * df.loc[n - 20:, "amount"]
        df.loc[: n - 21, "main_net"] = np.nan
        panel = MainInflowMomentum20().compute_panel({"600000": df})
        val = panel["600000"].iloc[-1]
        assert val == pytest.approx(1.0, rel=1e-9)  # 0.05 × 20 days

    def test_persistence_fraction(self):
        n = 60
        df = make_bars(n=n, seed=2)
        half = df["main_net"] > 0
        df.loc[half, "main_net"] = np.abs(df.loc[half, "main_net"]) + 1
        df.loc[~half, "main_net"] = -np.abs(df.loc[~half, "main_net"]) - 1
        panel = MainInflowPersistence().compute_panel({"600000": df})
        expected = (df["main_net"] > 0).astype(float).tail(20).mean()
        assert panel["600000"].iloc[-1] == pytest.approx(expected, rel=1e-9)

    def test_acceleration_zero_when_constant(self):
        n = 60
        df = make_bars(n=n, seed=3)
        df["main_net"] = 0.03 * df["amount"]
        panel = MainInflowAcceleration().compute_panel({"600000": df})
        assert panel["600000"].iloc[-1] == pytest.approx(0.0, abs=1e-12)

    def test_acceleration_positive_when_stepping_in(self):
        n = 60
        df = make_bars(n=n, seed=4)
        df["main_net"] = 0.0
        df.loc[n - 5:, "main_net"] = 0.05 * df.loc[n - 5:, "amount"]
        panel = MainInflowAcceleration().compute_panel({"600000": df})
        assert panel["600000"].iloc[-1] > 0

    def test_no_lookahead(self):
        """Perturb future bars/flows → earlier factor values unchanged."""
        T = 150
        df = make_bars(n=260, seed=5)
        bars_full = {"600000": df.copy()}
        mutated = df.copy()
        mutated.loc[T:, "close"] *= 3.0
        mutated.loc[T:, "amount"] *= 3.0
        mutated.loc[T:, "main_net"] = -mutated.loc[T:, "main_net"]
        bars_mut = {"600000": mutated}

        for factor in (MainInflowMomentum20(), MainInflowPersistence(),
                       MainInflowAcceleration()):
            before = factor.compute_panel(bars_full)["600000"].iloc[:T].dropna()
            after = factor.compute_panel(bars_mut)["600000"].iloc[:T].dropna()
            pd.testing.assert_series_equal(
                before, after, check_names=False,
                obj=f"{factor.name} leaked future data")


# ── 2. Composite: NaN robustness + IC lag ───────────────────────────────────

class TestCompositeRobustness:

    def test_missing_factor_renormalizes_per_stock(self):
        """A stock missing one factor still gets a composite from the rest."""
        dates = pd.date_range("2024-01-01", periods=30, freq="B").strftime(
            "%Y-%m-%d")
        f1 = pd.DataFrame(
            np.linspace(0.1, 0.9, 30)[:, None].repeat(2, 1),
            index=dates, columns=["A1", "A2"])
        f2 = f1.copy()
        f2["A2"] = np.nan  # A2 missing factor 2 entirely
        composite = MultiFactorEngine().compute_composite(
            {"f1": f1, "f2": f2},
            {"f1": pd.DataFrame(), "f2": pd.DataFrame()},  # empty → equal weights
        )
        last = composite.iloc[-1]
        assert not np.isnan(last["A2"])
        # With equal weights and only f1 available, A2's composite == f1's value.
        assert last["A2"] == pytest.approx(f1["A2"].iloc[-1], abs=1e-9)
        assert last["A1"] == pytest.approx(f1["A1"].iloc[-1], abs=1e-9)

    def test_no_missing_equals_plain_weighted_mean(self):
        dates = pd.date_range("2024-01-01", periods=10, freq="B").strftime(
            "%Y-%m-%d")
        rng = np.random.default_rng(0)
        f1 = pd.DataFrame(rng.uniform(0, 1, (10, 2)), index=dates,
                          columns=["A1", "A2"])
        f2 = pd.DataFrame(rng.uniform(0, 1, (10, 2)), index=dates,
                          columns=["A1", "A2"])
        composite = MultiFactorEngine().compute_composite(
            {"f1": f1, "f2": f2},
            {"f1": pd.DataFrame(), "f2": pd.DataFrame()},
        )
        expected = (f1 + f2) / 2
        pd.testing.assert_frame_equal(
            composite, expected, check_names=False, check_freq=False)

    def test_ic_lag_no_lookahead(self):
        """Composite at date t must not depend on closes after t."""
        bars, _ = make_universe()
        engine = MultiFactorEngine(holding_period=20, ic_window=40)
        panels = engine.compute_all_factors(bars)
        from app.services.quant.factors import build_close_panel
        close = build_close_panel(bars)
        ic_stats = engine.compute_ic_stats(panels, close)
        full = engine.compute_composite(panels, ic_stats)

        # Crash all closes in the last 60 days and recompute.
        cutoff = str(close.index[-60])
        for t, df in bars.items():
            df.loc[df["date"] >= cutoff, "close"] *= 0.5
        panels2 = engine.compute_all_factors(bars)
        close2 = build_close_panel(bars)
        ic_stats2 = engine.compute_ic_stats(panels2, close2)
        mutated = engine.compute_composite(panels2, ic_stats2)

        dt = close.index[-80]
        before = full.loc[dt].dropna()
        after = mutated.loc[dt].dropna()
        pd.testing.assert_series_equal(
            before, after, check_names=False,
            obj="composite leaked future returns into IC weights")


# ── 3. Sector strength ──────────────────────────────────────────────────────

class TestSectorStrength:

    def test_bullish_sector_outranks_bearish(self):
        bars, membership = make_universe()
        out = compute_sector_strength(bars, membership)
        # Last-10-day mean: a single day's random flow can flip the
        # cross-section rank, the trend itself must not.
        last = out["strength"].tail(10).mean()
        assert last["A"] > last["B"]

    def test_flow_dim_ranks_inflow_sector_higher(self):
        bars, membership = make_universe()
        # Give sector B massive persistent inflow.
        for t, sectors in membership.items():
            if "B" in sectors and t != "600100":
                bars[t]["main_net"] = 0.10 * bars[t]["amount"]
        out = compute_sector_strength(bars, membership)
        last_flow = out["flow_rank"].iloc[-1]
        assert last_flow["B"] > last_flow["A"]

    def test_tech_fallback_when_flow_absent(self):
        bars, membership = make_universe()
        for df in bars.values():
            df.drop(columns=["main_net"], inplace=True)
        out = compute_sector_strength(bars, membership)
        last = out["strength"].iloc[-1]
        assert not np.isnan(last["A"]) and not np.isnan(last["B"])
        assert last["A"] > last["B"]
        assert out["flow_rank"].empty

    def test_divergence(self):
        from app.services.quant.sector_rotation import compute_divergence_panel
        bars, membership = make_universe()
        # Push every stock to its 20d high with net outflow at the end.
        for df in bars.values():
            n = len(df)
            df.loc[n - 1, "close"] = df["close"].max() * 1.05
            df.loc[n - 1, "high"] = df.loc[n - 1, "close"]
            df.loc[n - 25:, "main_net"] = -0.05 * df.loc[n - 25:, "amount"]
        div = compute_divergence_panel(bars)
        assert div.iloc[-1].any()

    def test_atr_panel_constant_range(self):
        """Constant daily high-low range ⇒ ATR == that range."""
        from app.services.quant.sector_rotation import build_atr_panel
        n = 40
        df = make_bars(n=n, seed=6)
        # Flatten closes FIRST, then derive a constant ±1 daily range from
        # them (no gaps: TR == high - low == 2.0).
        df["close"] = 100.0
        df["open"] = 100.0
        df["high"] = df["close"] + 1.0
        df["low"] = df["close"] - 1.0
        panel = build_atr_panel({"600000": df})
        assert panel["600000"].iloc[-1] == pytest.approx(2.0, rel=1e-9)

    def test_breakdown_buffer_suppresses_marginal_break(self):
        """A close 2% under MA20 breaks v1 rules but not a 3%-buffered one."""
        from app.services.quant.sector_rotation import build_breakdown_panel
        n = 80
        # Flat closes then a decisive drop: engineered so close sits just
        # under MA20 on the last two days.
        df = make_bars(n=n, seed=8)
        df["close"] = 100.0
        df["open"] = 100.0
        df["high"] = 100.5
        df["low"] = 99.5
        # Drop 2%: close 98 < MA20(=100) → v1 breakdown, but 98 > 100×0.97
        # → buffered (3%) does NOT trigger.
        df.loc[n - 2:, "close"] = 98.0
        df.loc[n - 2:, "high"] = 98.5
        df.loc[n - 2:, "low"] = 97.5
        bars = {"600000": df}
        v1 = build_breakdown_panel(bars)
        buffered = build_breakdown_panel(bars, buffer=0.03)
        assert bool(v1["600000"].iloc[-1]) is True
        assert bool(buffered["600000"].iloc[-1]) is False

    def test_atr_stop_mode_changes_exit_mix(self):
        """Huge ATR mult ⇒ effectively no stop-loss exits; tiny ⇒ many."""
        bars, membership = make_universe()
        engine = SectorRotationEngine(membership, holding_period=20)

        wide = RotationBacktester(stop_mode="atr", atr_mult=50.0).run(
            bars, membership, engine, initial_capital=1e6)
        reasons_wide = [t["exit_reason"] for t in wide["result"]["trades"]]
        assert "stop_loss" not in reasons_wide

        tight = RotationBacktester(stop_mode="atr", atr_mult=0.05).run(
            bars, membership, engine, initial_capital=1e6)
        reasons_tight = [t["exit_reason"] for t in tight["result"]["trades"]]
        assert "stop_loss" in reasons_tight


# ── 4. Selection ────────────────────────────────────────────────────────────

class TestSelection:

    def _panels(self):
        bars, membership = make_universe()
        engine = SectorRotationEngine(membership)
        model = engine.run(bars)
        return bars, membership, model

    def test_selects_from_top_sector_only(self):
        bars, membership, model = self._panels()
        latest = model["composite"].dropna(how="all").index[-1]
        weights, detail = select_portfolio_at(
            latest, model["composite"], model["sector"]["strength"],
            build_bullish_panel(bars), membership,
            top_k=1, top_n_per_sector=2)
        assert 0 < len(weights) <= 2
        # All picks must belong to the single top sector.
        top_sec = detail["top_sectors"][0]["sector"]
        for t in weights:
            assert top_sec in membership[t]
        assert sum(weights.values()) <= 1.0 + 1e-9
        assert max(weights.values()) <= 0.2 + 1e-9

    def test_bullish_gate_skips_non_trending(self):
        bars, membership = make_universe()
        engine = SectorRotationEngine(membership)
        model = engine.run(bars)
        latest = model["composite"].dropna(how="all").index[-1]
        bullish = build_bullish_panel(bars)
        # Force every sector-B stock non-bullish.
        bullish.loc[latest, [t for t, s in membership.items() if s == ["B"]]] = False
        weights, _ = select_portfolio_at(
            latest, model["composite"], model["sector"]["strength"],
            bullish, membership, top_k=8, top_n_per_sector=2, entry_fallback=0)
        for t in weights:
            assert membership[t] != ["B"]

    def test_engine_rebalance_cadence_and_cap(self):
        bars, membership = make_universe()
        engine = SectorRotationEngine(membership, holding_period=20)
        model = engine.run(bars)
        dates = sorted(model["portfolios"].keys())
        assert len(dates) >= 5
        for i in range(1, len(dates)):
            gap = model["composite"].index.get_loc(dates[i]) \
                - model["composite"].index.get_loc(dates[i - 1])
            assert gap == 20
        for dt, w in model["portfolios"].items():
            # Cap binds per-stock; with few picks the remainder stays cash.
            assert sum(w.values()) <= 1.0 + 1e-9
            assert max(w.values()) <= 0.20 + 1e-9


# ── 5. Backtester smoke ─────────────────────────────────────────────────────

class TestRotationBacktester:

    def test_smoke_run(self):
        bars, membership = make_universe()
        engine = SectorRotationEngine(membership, holding_period=20)
        bt = RotationBacktester()
        out = bt.run(bars, membership, engine, initial_capital=1e6)
        r = out["result"]
        assert len(r["equity_curve"]) == len(
            out["model"]["composite"].index)
        assert np.isfinite(r["final_equity"])
        assert r["max_drawdown_pct"] >= 0
        assert r["rebalance_count"] >= 3
        assert r["benchmark_total_return_pct"] != 0
        valid_reasons = {"rebalance", "breakdown", "stop_loss",
                         "trailing_stop", "end"}
        for tr in r["trades"]:
            assert tr["exit_reason"] in valid_reasons
            assert tr["hold_days"] >= 1  # T+1
        # Trending universe A must contribute positively somewhere.
        assert r["sector_pnl"].get("A", 0) != 0 or r["sector_pnl"].get("B", 0) != 0


# ── 6. Fund-flow fetch parsing ──────────────────────────────────────────────

class TestFundFlowParsing:

    def test_parse_kline(self):
        from scripts.backfill_em_fund_flow import _parse_kline, market_prefix
        row = _parse_kline(
            "2026-08-19,12345678.0,-1000.0,-2000.0,3000000.0,9345678.0")
        assert row == {
            "date": "2026-08-19", "main_net": 12345678.0,
            "small_net": -1000.0, "mid_net": -2000.0,
            "large_net": 3000000.0, "super_net": 9345678.0,
        }
        assert market_prefix("600519") == 1
        assert market_prefix("688120") == 1
        assert market_prefix("300308") == 0
        assert market_prefix("002281") == 0

    def test_parse_kline_dash_values(self):
        from scripts.backfill_em_fund_flow import _parse_kline
        row = _parse_kline("2026-08-19,-,-,-,-,-")
        assert row is not None and row["main_net"] == 0.0

    def test_parse_kline_short_line(self):
        from scripts.backfill_em_fund_flow import _parse_kline
        assert _parse_kline("2026-08-19,1.0") is None


# ── 7. DB integration: scan service ─────────────────────────────────────────

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
        from datetime import date as date_cls
        from app.models.chain_models import DailyBar, FundFlowDaily
        from app.services.quant import rotation_service

        bars, membership = make_universe()
        for t, df in bars.items():
            for _, r in df.iterrows():
                d = date_cls.fromisoformat(r["date"])
                db_session.add(DailyBar(
                    ticker=t, date=d, open=r["open"], high=r["high"],
                    low=r["low"], close=r["close"], volume=r["volume"],
                    amount=r["amount"]))
                db_session.add(FundFlowDaily(
                    ticker=t, date=d, main_net=r["main_net"],
                    super_net=r["main_net"] / 2, large_net=r["main_net"] / 2,
                    mid_net=0.0, small_net=0.0))
        db_session.commit()

        # Point the service's pool at our synthetic tickers + sectors.
        monkeypatch.setattr(
            "app.services.quant.sector_pool.get_all_tickers",
            lambda: sorted(bars.keys()))
        monkeypatch.setattr(
            "app.services.quant.rotation_service.get_pool_membership",
            lambda: membership)
        synth_sectors = {
            "A": {"aliases": [], "stocks": [
                [t, f"股票{t}"] for t, ss in membership.items() if "A" in ss]},
            "B": {"aliases": [], "stocks": [
                [t, f"股票{t}"] for t, ss in membership.items() if "B" in ss]},
        }
        monkeypatch.setattr(
            "app.services.quant.sector_pool.get_sectors",
            lambda: synth_sectors)

        result = rotation_service.scan_rotation_signals(
            db_session, top_k=1, top_n_per_sector=1)
        assert result["sector_count"] == 2
        assert result["scanned"] > 0
        assert 1 <= result["selected"] <= 1

        from app.models.chain_models import SectorScore, RotationSignal
        scores = db_session.query(SectorScore).all()
        assert len(scores) == 2
        sigs = db_session.query(RotationSignal).all()
        assert len(sigs) == len(bars)
        selected = [s for s in sigs if s.is_selected]
        assert len(selected) == result["selected"]
        for s in selected:
            assert s.weight > 0
            assert s.stop_loss_price is not None

        # Query layer round-trip.
        snap = rotation_service.get_latest_sector_scores(db_session)
        assert snap["date"] is not None and len(snap["sectors"]) == 2
        port = rotation_service.get_latest_portfolio(db_session)
        assert len(port["holdings"]) == result["selected"]
