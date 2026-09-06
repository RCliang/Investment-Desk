"""Defensive-asset rotation validation (gold / treasury / dividend + cash).

Motivation: the 2021-09→2024-09 bear window killed every momentum config
while defensive buy&hold was the only green (gold +54.7%, bond Sharpe 2.05).
This harness tests whether a DEDICATED monthly momentum rotation over the
defensive trio behaves better than sitting in cash during equity bears,
without hurting the full window.

Protocol (parameter-light — no new knobs vs the mid-term preset):
  pool        518880 gold / 511010 treasury / 510880 dividend + 511990 cash
  engine      MID_BASE verbatim except top_n ∈ {1, 2} (2 cells only) and
              exit_replacement=False (the pool is already all-defensive)
  windows     bear 2021-09-01→2024-09-30, full 2019-10-08→2026-09-04,
              plus calendar years
  hybrid      regime switch: 510300 above MA250 → mid-term live preset;
              below → defensive rotation. Regime state sampled monthly
              (month-end close vs MA250, applied next month) to avoid
              whipsaw; each flip charged 0.25% round-trip on the book.

Output: backend/data/etf_defensive_rotation_results.json + console tables.

Usage:
    python scripts/etf_defensive_rotation_validation.py
"""

from __future__ import annotations

import json
import math
import sys
import time
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))
sys.path.insert(0, str(BACKEND_DIR / "scripts"))

from etf_short_validation import (  # noqa: E402
    EVAL_END, EVAL_START, TRAIN_END, _context,
)
from app.services.quant import etf_pool  # noqa: E402
from app.services.quant.etf_lab import (  # noqa: E402
    DEFENSIVE_SLEEVE as _LAB_SLEEVE, run_preset,
)

OUT_PATH = BACKEND_DIR / "data" / "etf_defensive_rotation_results.json"

BEAR_LO, BEAR_HI = "2021-09-01", "2024-09-30"
DEFENSIVE = sorted(_LAB_SLEEVE)                   # single source: etf_lab
CASH = etf_pool.get_cash_ticker()                 # 511990
FLIP_COST = 0.0025                                # per regime flip, round trip


def run_defensive(top_n: int) -> dict:
    """MID preset over the defensive trio (bars/membership filtered)."""
    ctx = _context()
    bars = {t: ctx["bars"][t] for t in [*DEFENSIVE, CASH]}
    membership = {t: ctx["membership"][t] for t in bars}
    # sleeve OFF here: this arm measures momentum-rotation OVER the trio
    # (the hypothesis that failed), not the regime overlay.
    return run_preset("mid", overrides={"top_n": top_n,
                                        "exit_replacement": False},
                      bars=bars, membership=membership)["result"]


def run_mid() -> dict:
    """Live mid-term preset on the full pool (head-to-head reference)."""
    ctx = _context()
    return run_preset("mid", bars=ctx["bars"],
                      membership=ctx["membership"])["result"]


def series_of(curve: list[dict]) -> pd.Series:
    s = pd.Series({p["date"]: p["equity"] for p in curve}, dtype=float)
    s.index = pd.to_datetime(s.index)
    return s


def metrics(s: pd.Series, lo: str, hi: str) -> dict:
    s = s[(s.index >= lo) & (s.index <= hi)]
    rets = s.pct_change().dropna()
    peak = s.cummax()
    dd = float(((peak - s) / peak).max())
    std = rets.std(ddof=1)
    years = len(s) / 252
    ann = (s.iloc[-1] / s.iloc[0]) ** (1 / years) - 1 if years > 0 else 0.0
    return {"total_pct": round(s.iloc[-1] / s.iloc[0] - 1, 4) * 100,
            "annual_pct": round(ann, 4) * 100,
            "max_dd_pct": round(dd, 4) * 100,
            "sharpe": round(float(rets.mean() / std * math.sqrt(252)), 3)
            if std > 0 else 0.0}


def regime_monthly(ctx: dict) -> pd.Series:
    """Month-sampled equity regime: 510300 month-end close vs MA250."""
    px = ctx["bars"]["510300"].set_index("date")["close"]
    px.index = pd.to_datetime(px.index)
    ma = px.rolling(250).mean()
    above = (px > ma).astype(float)
    # month-end state applies to the NEXT month (no look-ahead)
    monthly = above.resample("ME").last().shift(1).ffill()
    return monthly


def main() -> None:
    t0 = time.time()
    ctx = _context()

    results = {}
    curves = {}
    for tn in (1, 2):
        r = run_defensive(tn)
        curves[f"def_top{tn}"] = series_of(r["equity_curve"])
        results[f"def_top{tn}"] = {
            "bear": metrics(curves[f"def_top{tn}"], BEAR_LO, BEAR_HI),
            "full": metrics(curves[f"def_top{tn}"], EVAL_START, EVAL_END),
        }
    mid = run_mid()
    curves["mid_term"] = series_of(mid["equity_curve"])
    results["mid_term"] = {
        "bear": metrics(curves["mid_term"], BEAR_LO, BEAR_HI),
        "full": metrics(curves["mid_term"], EVAL_START, EVAL_END),
    }

    # buy & hold references on both windows
    for t, name in (*zip(DEFENSIVE, ["gold", "treasury", "dividend"]),
                    (CASH, "cash")):
        px = ctx["bars"][t].set_index("date")["close"]
        px.index = pd.to_datetime(px.index)
        curves[f"bh_{name}"] = px / px.iloc[0]
        results[f"bh_{name}"] = {
            "bear": metrics(px, BEAR_LO, BEAR_HI),
            "full": metrics(px, EVAL_START, EVAL_END),
        }

    # hybrid: mid-term in equity-up months, defensive rotation (top1) below
    common = curves["mid_term"].index.intersection(curves["def_top1"].index)
    reg = regime_monthly(ctx)
    def_r = curves["def_top1"].pct_change().reindex(common)
    mid_r = curves["mid_term"].pct_change().reindex(common)
    reg = reg.reindex(common).ffill()
    hyb = pd.Series(np.nan, index=common)
    use_def = (reg < 1.0).fillna(False)
    hyb[use_def] = def_r[use_def]
    hyb[~use_def] = mid_r[~use_def]
    flips = use_def.astype(int).diff().abs().fillna(0)
    hyb = hyb - flips * FLIP_COST
    hyb.iloc[0] = 0.0
    curves["hybrid"] = (1 + hyb.fillna(0)).cumprod()
    results["hybrid"] = {
        "bear": metrics(curves["hybrid"], BEAR_LO, BEAR_HI),
        "full": metrics(curves["hybrid"], EVAL_START, EVAL_END),
        "flips": int(flips.sum()),
        "months_in_defensive": int(use_def.sum()),
    }

    for name in ("def_top1", "def_top2", "mid_term", "bh_gold", "bh_treasury",
                 "bh_dividend", "bh_cash", "hybrid"):
        b, f = results[name]["bear"], results[name]["full"]
        extra = (f" | flips {results[name]['flips']}, "
                 f"{results[name]['months_in_defensive']}m in def"
                 if name == "hybrid" else "")
        print(f"{name:14s} bear {b['total_pct']:+7.1f}% dd {b['max_dd_pct']:5.1f}% "
              f"sh {b['sharpe']:5.2f} | full {f['total_pct']:+8.1f}% "
              f"dd {f['max_dd_pct']:5.1f}% sh {f['sharpe']:5.2f}{extra}")

    print("\n── calendar years (total %) ──")
    print("year  def_top1  mid_term  hybrid  gold")
    for y in range(2020, 2027):
        lo, hi = f"{y}-01-01", f"{y}-12-31"
        row = [metrics(curves[c], lo, hi)["total_pct"]
               if len(curves[c][(curves[c].index >= lo) & (curves[c].index <= hi)]) > 40 else float("nan")
               for c in ("def_top1", "mid_term", "hybrid")]
        g = metrics(curves["bh_gold"], lo, hi)["total_pct"] \
            if len(curves["bh_gold"][(curves["bh_gold"].index >= lo) & (curves["bh_gold"].index <= hi)]) > 40 else float("nan")
        print(f"{y}  {row[0]:+8.1f}  {row[1]:+8.1f}  {row[2]:+8.1f}  {g:+7.1f}")

    out = {"generated_at": str(date.today()), "windows": {
               "bear": [BEAR_LO, BEAR_HI], "full": [EVAL_START, EVAL_END]},
           "protocol": {"pool": DEFENSIVE + [CASH], "preset": "MID_BASE "
                        "verbatim except top_n, exit_replacement=False",
                        "flip_cost": FLIP_COST},
           "results": results,
           "elapsed_s": round(time.time() - t0, 1)}
    OUT_PATH.write_text(json.dumps(out, ensure_ascii=False, indent=1,
                                   default=float), encoding="utf-8")
    print(f"\nresults → {OUT_PATH} | elapsed {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()


# ── Integrated hybrid (engine-level regime sleeve, live code path) ─────────

def run_integrated_hybrid(ctx: dict | None = None) -> dict:
    """The go-live path: PRESETS["hybrid"] via the lab's one wiring copy.
    Reproduces the numbers quoted in docs §十."""
    ctx = ctx or _context()
    return run_preset("hybrid", bars=ctx["bars"],
                      membership=ctx["membership"])["result"]
