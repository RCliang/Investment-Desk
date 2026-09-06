"""Tests for etf_lab — the preset + wiring single source (architecture
review 2026-09-06, candidate 1).

Covers:
  1. Preset integrity: every preset carries the full knob set; hybrid ≡
     mid + sleeve; the live service constants ≡ PRESETS["mid"] (the
     drift-kill guarantee).
  2. run_preset on a synthetic universe (bars injection — no DB), sleeve
     activation included via the regime universe from test_etf_rotation.
  3. Error modes: unknown preset, unknown override key.
  4. slice_metrics math pin.
"""

from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pytest

BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.services.quant import etf_lab
from app.services.quant import etf_signal_service as svc
from test_etf_rotation import CASH, SLEEVE, make_regime_universe


def synth_membership(bars):
    return {t: ["ETF"] for t in bars}


def patch_pool(monkeypatch, bars):
    """Point the pool accessors at the synthetic universe (same pattern
    as the scan tests in test_etf_rotation)."""
    from app.services.quant import etf_pool
    monkeypatch.setattr(etf_pool, "get_cash_ticker", lambda: CASH)
    monkeypatch.setattr(etf_pool, "get_asset_classes",
                        lambda: {t: ("货币" if t == CASH else
                                     "防守" if t in SLEEVE else "宽基")
                                 for t in bars})


# ── 1. Preset integrity ─────────────────────────────────────────────────────

class TestPresets:

    def test_every_preset_carries_all_knobs(self):
        for name, preset in etf_lab.PRESETS.items():
            missing = set(etf_lab._PRESET_KEYS) - set(preset)
            assert not missing, f"{name} missing {missing}"

    def test_hybrid_is_mid_plus_sleeve(self):
        mid = etf_lab.PRESETS["mid"]
        hyb = etf_lab.PRESETS["hybrid"]
        diff = {k for k in mid if mid[k] != hyb[k]}
        assert diff == {"use_defensive_sleeve"}
        assert hyb["use_defensive_sleeve"] is True
        assert mid["use_defensive_sleeve"] is False

    def test_short_preset_is_doc_section_nine(self):
        short = etf_lab.PRESETS["short"]
        assert tuple(short["windows"]) == (20, 60)
        assert tuple(short["weights"]) == (0.6, 0.4)
        assert short["abs_window"] == 60
        assert short["rebalance_anchor"] == "weekly"
        assert short["use_trend_filter"] is True
        assert short["use_market_gate"] is True
        assert short["market_ma_window"] == 250
        # §9.5 champion cell
        assert (short["top_n"], short["buffer_rank"],
                short["atr_mult"]) == (2, 0, 3.0)

    def test_live_service_constants_come_from_presets(self):
        """The drift-kill guarantee: scan defaults ≡ PRESETS values."""
        mid = etf_lab.PRESETS["mid"]
        assert svc.ATR_MULT == mid["atr_mult"]
        assert svc.USE_TARGET_VOL == mid["use_target_vol"]
        assert svc.TARGET_VOL == mid["target_vol"]
        assert svc.DEFENSIVE_SLEEVE == etf_lab.DEFENSIVE_SLEEVE
        assert svc.REGIME_TICKER == etf_lab.REGIME_TICKER
        assert svc.REGIME_MA_WINDOW == etf_lab.REGIME_MA_WINDOW
        assert (svc.TOP_N, svc.BUFFER_RANK, svc.HOLDING_PERIOD) == (
            mid["top_n"], mid["buffer_rank"], mid["holding_period"])


# ── 2. run_preset on a synthetic universe ───────────────────────────────────

class TestRunPresetSynthetic:

    def test_mid_runs_without_db(self, monkeypatch):
        bars = make_regime_universe()
        patch_pool(monkeypatch, bars)
        out = etf_lab.run_preset("mid", bars=bars,
                                 membership=synth_membership(bars))
        r = out["result"]
        assert np.isfinite(r["final_equity"]) and r["final_equity"] > 0
        assert out["cfg"]["rebalance_anchor"] == "calendar"

    def test_hybrid_sleeve_trades_on_synthetic(self, monkeypatch):
        bars = make_regime_universe()
        patch_pool(monkeypatch, bars)
        # synthetic sleeve names stand in for the real trio
        monkeypatch.setattr(etf_lab, "DEFENSIVE_SLEEVE", set(SLEEVE))
        out = etf_lab.run_preset("hybrid", bars=bars,
                                 membership=synth_membership(bars))
        r = out["result"]
        sleeve_trades = [t for t in r["trades"] if t["ticker"] in SLEEVE]
        assert sleeve_trades, "sleeve should trade in the risk-off months"
        assert all(t["exit_reason"] == "rebalance" for t in sleeve_trades)
        assert out["cfg"]["use_defensive_sleeve"] is True

    def test_override_wins_and_none_falls_through(self, monkeypatch):
        bars = make_regime_universe()
        patch_pool(monkeypatch, bars)
        out = etf_lab.run_preset("mid", overrides={"top_n": 3, "atr_mult": None},
                                 bars=bars, membership=synth_membership(bars))
        assert out["cfg"]["top_n"] == 3
        assert out["cfg"]["atr_mult"] == etf_lab.PRESETS["mid"]["atr_mult"]


# ── 3. Error modes ──────────────────────────────────────────────────────────

class TestRunPresetErrors:

    def test_unknown_preset(self):
        with pytest.raises(ValueError, match="unknown preset"):
            etf_lab.run_preset("champion", overrides={})

    def test_unknown_override_key(self):
        with pytest.raises(ValueError, match="unknown override"):
            etf_lab.run_preset("mid", overrides={"momentum_windows": [20]})


# ── 4. slice_metrics math pin ───────────────────────────────────────────────

class TestSliceMetrics:

    def test_quadrupling_curve(self):
        d0 = date(2024, 1, 1)
        curve = [{"date": str(d0 + timedelta(days=i)),
                  "equity": 1e6 * 4 ** (i / 47)} for i in range(48)]
        m = etf_lab.slice_metrics(curve, "2024-01-01", "2024-02-29")
        assert m["total_pct"] == 300.0          # 1e6 → exactly 4e6
        assert m["max_dd_pct"] == 0.0
        assert m["sharpe"] > 5                  # smooth monotone curve
        assert m["avg_turnover_pct"] == 0.0

    def test_too_short_slice_returns_none(self):
        curve = [{"date": f"2024-01-{d:02d}", "equity": 1e6 + d}
                 for d in range(1, 11)]
        assert etf_lab.slice_metrics(curve, "2024-01-01", "2024-01-31") is None
