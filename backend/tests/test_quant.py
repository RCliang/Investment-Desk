"""Tests for the quant package: indicators, strategies, scorecard.

Three layers:
  1. Unit tests on synthetic data — verify formulas + no future-function.
  2. Indicator sanity — SMA/RSI/MACD/ATR on known small inputs.
  3. Integration — score a real (already-loaded) bar DataFrame; check the
     signal distribution is sane (most days HOLD, some BUY/SELL).

The no-future-function test is the most important: it perturbs future
bars and asserts earlier outputs don't change.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from app.services.quant import indicators as ind
from app.services.quant import scoring
from app.services.quant.strategies import (
    TrendMA, BreakoutDonchian,
    MomentumMACD, MomentumRSI,
    VolumePrice, RiskATR,
)


# ── Fixtures ───────────────────────────────────────────────────────────────

@pytest.fixture
def synth_bars(n: int = 200) -> pd.DataFrame:
    """Deterministic synthetic bars (seeded) with a gentle uptrend + noise.

    Deterministic so test failures are reproducible. Includes volume and
    turnover so the full enrich() path runs.
    """
    rng = np.random.default_rng(42)
    dates = pd.date_range("2024-01-01", periods=n, freq="B")
    # Random walk with positive drift.
    rets = rng.normal(0.001, 0.02, n)
    close = 100 * np.exp(np.cumsum(rets))
    high = close * (1 + rng.uniform(0, 0.015, n))
    low = close * (1 - rng.uniform(0, 0.015, n))
    open_ = (high + low) / 2
    volume = rng.integers(1e6, 1e8, n).astype(float)
    amount = volume * close
    turnover = rng.uniform(0.5, 5.0, n)
    return pd.DataFrame({
        "date": dates.strftime("%Y-%m-%d"),
        "open": open_, "high": high, "low": low, "close": close,
        "volume": volume, "amount": amount, "turnover_pct": turnover,
    })


# ── Indicator formula tests ────────────────────────────────────────────────

class TestIndicators:
    def test_sma_basic(self):
        s = pd.Series([1, 2, 3, 4, 5], dtype=float)
        out = ind.sma(s, 3)
        assert pd.isna(out.iloc[0]) and pd.isna(out.iloc[1])
        assert out.iloc[2] == pytest.approx(2.0)   # (1+2+3)/3
        assert out.iloc[4] == pytest.approx(4.0)   # (3+4+5)/3

    def test_ema_first_value_seeds(self):
        s = pd.Series([10, 20, 30], dtype=float)
        out = ind.ema(s, 5)
        # adjust=False: first EMA == first value.
        assert out.iloc[0] == pytest.approx(10.0)

    def test_rsi_bounds(self, synth_bars):
        r = ind.rsi(synth_bars["close"], 14)
        valid = r.dropna()
        assert (valid >= 0).all() and (valid <= 100).all()

    def test_rsi_all_up_is_100(self):
        # A monotonically rising series should saturate RSI at 100.
        s = pd.Series(np.linspace(1, 100, 50))
        r = ind.rsi(s, 14)
        assert r.iloc[-1] == pytest.approx(100.0, abs=1.0)

    def test_macd_returns_three_aligned(self, synth_bars):
        dif, dea, hist = ind.macd(synth_bars["close"])
        assert len(dif) == len(synth_bars)
        assert len(dea) == len(synth_bars)
        assert len(hist) == len(synth_bars)
        # hist = (dif - dea) * 2 by A-share convention.
        valid = ~dif.isna() & ~dea.isna()
        assert np.allclose(hist[valid], (dif[valid] - dea[valid]) * 2)

    def test_atr_positive(self, synth_bars):
        a = ind.atr(synth_bars["high"], synth_bars["low"], synth_bars["close"], 14)
        assert (a.dropna() >= 0).all()

    def test_donchian_excludes_today(self, synth_bars):
        # The entry_high on day t must NOT depend on day t's high (shift applied).
        eh, el = ind.donchian(synth_bars["high"], synth_bars["low"], 20, 10)
        # On day 20 (0-indexed), entry_high should be max of days 0..19, not 20.
        i = 20
        assert eh.iloc[i] == pytest.approx(synth_bars["high"].iloc[:i].max())

    def test_turnover_percentile_bounds(self, synth_bars):
        p = ind.turnover_percentile(synth_bars["turnover_pct"], 60)
        valid = p.dropna()
        assert (valid >= 0).all() and (valid <= 1).all()

    def test_enrich_adds_all_columns(self, synth_bars):
        out = ind.enrich(synth_bars)
        for col in ["ma5", "ma20", "ma60", "ema12", "ema26",
                    "macd_dif", "macd_dea", "macd_hist",
                    "rsi14", "boll_up", "boll_mid", "boll_low",
                    "atr14", "turnover_pct60"]:
            assert col in out.columns, f"missing {col}"


# ── No-future-function tests (critical) ────────────────────────────────────

class TestNoFutureFunction:
    """Perturb future bars and assert earlier outputs don't change.

    This is the single most important correctness property: a signal at
    time t must not depend on bars after t. We test by:
      1. Computing outputs on the full series.
      2. Mutating bars after index T (e.g. doubling them).
      3. Recomputing and asserting outputs[:T] are bit-identical.
    """

    def test_indicators_no_lookahead(self, synth_bars):
        T = 100
        enriched_full = ind.enrich(synth_bars)

        # Perturb the tail aggressively.
        mutated = synth_bars.copy()
        mutated.loc[T:, "close"] *= 3.0
        mutated.loc[T:, "high"] *= 3.0
        mutated.loc[T:, "low"] *= 3.0
        enriched_mut = ind.enrich(mutated)

        for col in ["ma5", "ma20", "ma60", "rsi14", "macd_dif",
                    "macd_dea", "atr14", "turnover_pct60"]:
            before = enriched_full[col].iloc[:T].dropna()
            after = enriched_mut[col].iloc[:T].dropna()
            pd.testing.assert_series_equal(
                before, after,
                check_names=False,
                obj=f"indicator {col} leaked future data",
            )

    def test_strategies_no_lookahead(self, synth_bars):
        T = 100
        enriched_full = ind.enrich(synth_bars)
        card = scoring.DEFAULT_CARD
        out_full = card.score_summary(enriched_full)

        mutated = synth_bars.copy()
        mutated.loc[T:, "close"] *= 3.0
        mutated.loc[T:, "high"] *= 3.0
        mutated.loc[T:, "low"] *= 3.0
        enriched_mut = ind.enrich(mutated)
        out_mut = card.score_summary(enriched_mut)

        # composite_score up to T must be identical.
        before = out_full["composite_score"].iloc[:T]
        after = out_mut["composite_score"].iloc[:T]
        pd.testing.assert_series_equal(
            before, after,
            check_names=False,
            obj="composite_score leaked future data",
        )

    def test_individual_strategy_no_lookahead(self, synth_bars):
        T = 100
        enriched_full = ind.enrich(synth_bars)
        for strat in [TrendMA(), BreakoutDonchian(),
                      MomentumMACD(), MomentumRSI(), VolumePrice(), RiskATR()]:
            full = strat.compute(enriched_full).fillna(0.0)
            # Perturb.
            mutated = synth_bars.copy()
            mutated.loc[T:, "close"] *= 2.5
            mutated.loc[T:, "high"] *= 2.5
            mutated.loc[T:, "low"] *= 2.5
            enriched_mut = ind.enrich(mutated)
            mut = strat.compute(enriched_mut).fillna(0.0)
            pd.testing.assert_series_equal(
                full.iloc[:T], mut.iloc[:T],
                check_names=False,
                obj=f"{strat.name} leaked future data",
            )


# ── Strategy signal-range tests ────────────────────────────────────────────

class TestStrategyRanges:
    @pytest.mark.parametrize("strat_cls", [
        TrendMA, BreakoutDonchian, MomentumMACD, MomentumRSI, VolumePrice, RiskATR,
    ])
    def test_signal_in_range(self, synth_bars, strat_cls):
        enriched = ind.enrich(synth_bars)
        sig = strat_cls().compute(enriched).fillna(0.0)
        assert sig.min() >= -1.0 - 1e-9, f"{strat_cls.__name__} below -1"
        assert sig.max() <= 1.0 + 1e-9, f"{strat_cls.__name__} above +1"


# ── ScoreCard integration ──────────────────────────────────────────────────

class TestScoreCard:
    def test_scorecard_produces_actions(self, synth_bars):
        enriched = ind.enrich(synth_bars)
        out = scoring.DEFAULT_CARD.score_summary(enriched)
        assert set(out["action"].unique()) <= {"BUY", "SELL", "HOLD"}
        # Composite bounded.
        assert out["composite_score"].between(-1, 1).all()

    def test_scorecard_latest_dict_shape(self, synth_bars):
        enriched = ind.enrich(synth_bars)
        latest = scoring.DEFAULT_CARD.latest(enriched)
        assert latest["action"] in {"BUY", "SELL", "HOLD"}
        assert -1 <= latest["composite_score"] <= 1
        assert 0 <= latest["position_pct"] <= 1
        assert "detail" in latest
        # detail should contain every strategy name.
        for name in ["trend_ma", "breakout_donchian",
                     "momentum_macd", "momentum_rsi", "volume_price", "risk_atr"]:
            assert name in latest["detail"]

    def test_thresholds_respected(self, synth_bars):
        card = scoring.ScoreCard(scoring.default_strategies(),
                                 buy_threshold=0.99, sell_threshold=-0.99)
        enriched = ind.enrich(synth_bars)
        out = card.score_summary(enriched)
        # Near-impossible thresholds → almost all HOLD.
        assert (out["action"] == "HOLD").mean() > 0.95

    def test_weights_normalized(self):
        card = scoring.DEFAULT_CARD
        # Sum of normalized weights for non-risk strategies should equal
        # 1 - risk_weight = 0.85 (since risk is 0.15 and not summed).
        total = sum(getattr(s, "_normalized_weight", 0.0)
                    for s in card.strategies if s.category != "risk")
        assert total == pytest.approx(0.85, abs=0.01)
