"""Grid search for the ETF dual-momentum strategy (docs/etf-rotation-grid-search-plan.md).

Three-layer search (avoids Cartesian explosion), direct engine+backtester
calls (no HTTP, no DB writes — ~0.5s per full backtest):

  L1  top_n × holding_period × target_vol(None|0.08|0.10|0.12|0.15)
  L2  abs_window × buffer_rank × atr_mult                (on L1 champion)
  L3  momentum windows × long-window weight × vol_window
      (+ breakdown_buffer mini-sweep)                    (on L1+L2 champions)

Fixed per plan §1.2 (already ablated): weight_mode=equal, rebalance_mode=
fixed, use_market_gate=False, use_abs_gate=True.

Anti-overfit (plan §2/§3):
  - Metrics are computed on the EVAL window 2021-09-15 → 2026-09-01 by
    slicing the equity curve, with panels fully warmed up BEFORE the
    window (bars_limit=1600 → data from 2020-01): every window-length
    config gets the same invested window, no warm-up bias.
  - Every cell reports train (2021-09 → 2024-09) AND valid (2024-09 →
    2026-09) metrics; champions must not degrade out-of-sample.
  - Champion = max train Sharpe among positive-Sharpe cells subject to
    valid Sharpe ≥ 0.7×train and valid maxDD ≤ 25%. Plateau (±1 grid
    step) is printed for every layer champion — isolated peaks are
    rejected in the analysis step, not by the script.
  - Walk-forward (optional): annual re-optimization on a coarse grid,
    next-year execution slices stitched. Sliced approximation — the
    boundary position state is each champion's own path, not a live
    switch; caveat recorded with the results.

Output: backend/data/etf_grid_search_results.json (all cells + champions
+ walk-forward; equity curves stripped) + console tables.

Usage:
    python scripts/etf_grid_search.py                # layers 1-3
    python scripts/etf_grid_search.py --walkforward  # + walk-forward phase
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from datetime import date
from pathlib import Path

import numpy as np

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from app.db import SessionLocal                              # noqa: E402
from app.services.quant import etf_pool, etf_signal_service  # noqa: E402
from app.services.quant.etf_rotation import (                # noqa: E402
    EtfRotationEngine, MOMENTUM_WINDOWS, MOMENTUM_WEIGHTS,
)
from app.services.quant.rotation_backtest import RotationBacktester  # noqa: E402

OUT_PATH = BACKEND_DIR / "data" / "etf_grid_search_results.json"

# Evaluation windows (plan §3): full / train / valid, ISO strings.
EVAL_START = "2021-09-15"
EVAL_END = "2026-09-01"
SPLIT_DATE = "2024-09-15"
# Bars depth: panels (max window 250 + vol 120) must be warm BEFORE
# EVAL_START; 1600 bars reach back to 2020-01.
BARS_LIMIT = 1600

# Fixed strategy knobs (plan §1.2 — already ablated, kept out of the grid).
FIXED = dict(weight_mode="equal", rebalance_mode="fixed",
             use_market_gate=False, use_abs_gate=True)

# Default (baseline) cell — mirrors etf_signal_service constants.
BASELINE = dict(top_n=3, holding_period=5, target_vol=None,
                buffer_rank=2, abs_window=120, atr_mult=2.0,
                breakdown_buffer=0.03,
                windows=MOMENTUM_WINDOWS, weights=MOMENTUM_WEIGHTS,
                vol_window=60)

WINDOW_COMBOS = [(10, 60, 120), (20, 60, 120), (20, 40, 120), (60, 120, 250)]


# ── Metrics from an equity-curve slice ─────────────────────────────────────

def slice_metrics(
    curve: list[dict], lo: str, hi: str,
    rebalance_log: list[dict] | None = None,
) -> dict | None:
    pts = [p for p in curve if lo <= p["date"] <= hi]
    eq = np.array([p["equity"] for p in pts], dtype=float)
    if len(pts) < 40 or eq[0] <= 0:
        return None
    total = eq[-1] / eq[0] - 1.0
    years = len(pts) / 252.0
    annual = (eq[-1] / eq[0]) ** (1.0 / years) - 1.0 if years > 0 else 0.0
    peak = np.maximum.accumulate(eq)
    dd = float(np.max((peak - eq) / peak)) if len(eq) else 0.0
    rets = np.diff(eq) / eq[:-1]
    std = rets.std(ddof=1) if len(rets) > 1 else 0.0
    sharpe = float(rets.mean() / std * math.sqrt(252)) if std > 0 else 0.0
    calmar = annual / dd if dd > 1e-9 else 0.0
    to = 0.0
    if rebalance_log is not None:
        xs = [r["turnover_pct"] for r in rebalance_log
              if lo <= r["date"] <= hi]
        to = float(np.mean(xs)) if xs else 0.0
    return {
        "total_pct": round(total * 100, 2),
        "annual_pct": round(annual * 100, 2),
        "max_dd_pct": round(dd * 100, 2),
        "sharpe": round(sharpe, 3),
        "calmar": round(calmar, 3),
        "avg_turnover_pct": round(to, 2),
    }


# ── One grid cell ───────────────────────────────────────────────────────────

_CTX: dict = {}
_CELL_CACHE: dict = {}   # cfg-key → cell (dedup across layers/WF rounds)


def _context() -> dict:
    if not _CTX:
        s = SessionLocal()
        try:
            bars = etf_signal_service.load_etf_pool_bars(s, limit=BARS_LIMIT)
        finally:
            s.close()
        classes = etf_pool.get_asset_classes()
        _CTX["bars"] = bars
        _CTX["membership"] = etf_pool.get_membership()
        _CTX["equity_like"] = {t for t, c in classes.items()
                               if c in ("宽基", "行业")}
    return _CTX


def _cfg_key(cfg: dict) -> str:
    norm = {k: (tuple(v) if isinstance(v, (list, tuple)) else v)
            for k, v in cfg.items()}
    return json.dumps(norm, sort_keys=True, default=str)


def run_cell(cfg: dict, use_cache: bool = True) -> dict:
    """Run one config over the full bar range; return full/train/valid
    sliced metrics + the raw curve (stripped before JSON dump).
    """
    key = _cfg_key({**BASELINE, **cfg})
    if use_cache and key in _CELL_CACHE:
        return _CELL_CACHE[key]

    ctx = _context()
    c = {**BASELINE, **cfg}
    engine = EtfRotationEngine(
        cash_ticker=etf_pool.get_cash_ticker(),
        top_n=c["top_n"], buffer_rank=c["buffer_rank"],
        holding_period=c["holding_period"],
        windows=tuple(c["windows"]), weights=tuple(c["weights"]),
        vol_window=c["vol_window"], abs_window=c["abs_window"],
        use_target_vol=c["target_vol"] is not None,
        target_vol=c["target_vol"] if c["target_vol"] is not None else 0.10,
        market_gate_tickers=ctx["equity_like"],
        **FIXED)
    bt = RotationBacktester(
        commission_rate=etf_signal_service.ETF_COMMISSION_RATE,
        commission_min=etf_signal_service.ETF_COMMISSION_MIN,
        stamp_duty_rate=etf_signal_service.ETF_STAMP_DUTY_RATE,
        slippage_rate=etf_signal_service.ETF_SLIPPAGE_RATE,
        stop_mode="atr", atr_mult=c["atr_mult"],
        breakdown_buffer=c["breakdown_buffer"],
        cash_tickers={etf_pool.get_cash_ticker()})
    out = bt.run(ctx["bars"], ctx["membership"], engine,
                 initial_capital=1e6)
    r = out["result"]
    curve, bench = r["equity_curve"], r["benchmark_curve"]
    log_ = r.get("rebalance_log") or []

    cell = {
        "cfg": {k: (list(v) if isinstance(v, tuple) else v)
                for k, v in c.items()},
        "full": slice_metrics(curve, EVAL_START, EVAL_END, log_),
        "train": slice_metrics(curve, EVAL_START, SPLIT_DATE, log_),
        "valid": slice_metrics(curve, SPLIT_DATE, EVAL_END, log_),
        "bench_full": slice_metrics(bench, EVAL_START, EVAL_END),
        "_curve": curve,
    }
    if any(cell[k] is None for k in ("full", "train", "valid")):
        raise RuntimeError(f"degenerate curve for cfg={c}")
    _CELL_CACHE[key] = cell
    return cell


# ── Champion picking + plateau ──────────────────────────────────────────────

CFG_KEYS = ["top_n", "holding_period", "target_vol", "buffer_rank",
            "abs_window", "atr_mult", "breakdown_buffer", "windows",
            "weights", "vol_window"]


def _fmt_cfg(c: dict) -> str:
    return " ".join(f"{k}={c[k]}" for k in CFG_KEYS if k in c)


def _print_cell(cell: dict) -> None:
    for p in ("full", "train", "valid"):
        m = cell[p]
        print(f"  {p:5s} ret {m['total_pct']:7.2f}% ann {m['annual_pct']:6.2f}%"
              f" dd {m['max_dd_pct']:6.2f}% sharpe {m['sharpe']:6.3f}"
              f" calmar {m['calmar']:6.3f} to {m['avg_turnover_pct']:5.2f}%")
    print(f"  cfg: {_fmt_cfg(cell['cfg'])}")


def pick_champion(cells: list[dict], label: str) -> dict:
    """Train-Sharpe primary, valid non-degradation gate (plan §2/§3)."""
    ok = [c for c in cells
          if c["train"]["sharpe"] > 0
          and c["valid"]["sharpe"] >= 0.7 * c["train"]["sharpe"]
          and c["valid"]["max_dd_pct"] <= 25.0]
    pool_ = ok if ok else [c for c in cells if c["train"]["sharpe"] > 0] or cells
    champ = max(pool_, key=lambda c: c["train"]["sharpe"])
    print(f"\n[{label}] champion (of {len(cells)} cells, "
          f"{len(ok)} passed valid-gate):")
    _print_cell(champ)
    if not ok:
        print("  ⚠ no cell passed the valid non-degradation gate")
    return champ


def print_top(cells: list[dict], n: int = 10, by: str = "train") -> None:
    print(f"\n  top {n} by {by} sharpe:")
    for c in sorted(cells, key=lambda x: -x[by]["sharpe"])[:n]:
        print(f"    train {c['train']['sharpe']:6.3f} valid "
              f"{c['valid']['sharpe']:6.3f} dd(v) "
              f"{c['valid']['max_dd_pct']:5.1f}% | {_fmt_cfg(c['cfg'])}")


def print_plateau(cells: list[dict], champ: dict, dims: list[str]) -> None:
    """±1 grid step around the champion in each searched dimension."""
    print(f"\n  plateau around champion:")
    for dim in dims:
        vals = sorted({c["cfg"][dim] for c in cells}, key=str)
        if champ["cfg"][dim] not in vals:
            continue
        i = vals.index(champ["cfg"][dim])
        row = []
        for j in range(max(0, i - 1), min(len(vals), i + 2)):
            v = vals[j]
            nb = [c for c in cells
                  if all(c["cfg"][k] == champ["cfg"][k]
                         for k in dims if k != dim)
                  and c["cfg"][dim] == v]
            if nb:
                m = nb[0]
                mark = "▸" if j == i else " "
                row.append(f"{mark}{dim}={v}: tr {m['train']['sharpe']:.2f}"
                           f"/va {m['valid']['sharpe']:.2f}")
        if row:
            print("    " + "  ".join(row))


# ── Layers ──────────────────────────────────────────────────────────────────

def layer1() -> list[dict]:
    return [run_cell(dict(top_n=tn, holding_period=hp, target_vol=tv))
            for tn in (2, 3, 4, 5)
            for hp in (1, 3, 5, 10, 20)
            for tv in (None, 0.08, 0.10, 0.12, 0.15)]


def _carry(champ: dict, keys: list[str]) -> dict:
    out = {}
    for k in keys:
        v = champ["cfg"][k]
        out[k] = tuple(v) if isinstance(v, list) else v
    return out


def layer2(champ: dict) -> list[dict]:
    base = _carry(champ, ["top_n", "holding_period", "target_vol",
                          "windows", "weights", "vol_window"])
    return [run_cell({**base, "abs_window": aw, "buffer_rank": br,
                      "atr_mult": am})
            for aw in (60, 90, 120, 180, 250)
            for br in (0, 1, 2, 3, 4)
            for am in (1.5, 2.0, 3.0, 4.0)]


def layer3(champ: dict) -> list[dict]:
    base = _carry(champ, ["top_n", "holding_period", "target_vol",
                          "buffer_rank", "abs_window", "atr_mult",
                          "breakdown_buffer", "vol_window"])
    cells = []
    for windows in WINDOW_COMBOS:
        for lw in (0.3, 0.5, 0.7):
            rest = round((1.0 - lw) / (len(windows) - 1), 4)
            weights = tuple([rest] * (len(windows) - 1) + [lw])
            for vw in (20, 60, 120):
                cells.append(run_cell({**base, "windows": windows,
                                       "weights": weights, "vol_window": vw}))
    # breakdown_buffer mini-sweep on the windows layer's best
    best = pick_champion(cells, "L3-windows")
    for bd in (0.0, 0.03, 0.05):
        cells.append(run_cell({**base,
                               "windows": tuple(best["cfg"]["windows"]),
                               "weights": tuple(best["cfg"]["weights"]),
                               "vol_window": best["cfg"]["vol_window"],
                               "breakdown_buffer": bd}))
    return cells


# ── Walk-forward (plan §3.2, sliced approximation) ─────────────────────────

WF_CUTOFFS = ["2022-09-15", "2023-09-15", "2024-09-15", "2025-09-15"]


def walkforward() -> list[dict]:
    """Annual re-optimization: champion picked on [EVAL_START, cutoff] by
    train-slice Sharpe over a coarse grid, then its performance is read
    on the following year's slice. Execution slices stitched 2022-09 →
    2026-09 and compared with the fixed-parameter champion in the report.
    """
    rows = []
    for i, cut in enumerate(WF_CUTOFFS):
        exec_lo = cut
        exec_hi = WF_CUTOFFS[i + 1] if i + 1 < len(WF_CUTOFFS) else EVAL_END
        best = best_sharpe = None
        for tn in (2, 3, 4):
            for hp in (3, 5, 10, 20):
                for tv in (None, 0.10, 0.12):
                    for aw in (90, 120, 180):
                        for am in (1.5, 2.0, 3.0):
                            cell = run_cell(dict(
                                top_n=tn, holding_period=hp, target_vol=tv,
                                abs_window=aw, atr_mult=am, buffer_rank=2))
                            m = slice_metrics(cell["_curve"],
                                              EVAL_START, cut)
                            if m and (best is None
                                      or m["sharpe"] > best_sharpe):
                                best, best_sharpe = cell, m["sharpe"]
        ex = slice_metrics(best["_curve"], exec_lo, exec_hi)
        rows.append({"round": i + 1, "train_end": cut,
                     "exec_window": f"{exec_lo}→{exec_hi}",
                     "cfg": best["cfg"], "train_sharpe": best_sharpe,
                     "exec": ex})
        print(f"  WF round {i+1}: train ≤{cut} | champ sharpe "
              f"{best_sharpe:.3f} | exec {exec_lo}→{exec_hi}: "
              f"{ex['total_pct']:.2f}% dd {ex['max_dd_pct']:.2f}% "
              f"sharpe {ex['sharpe']:.3f}")
    return rows


# ── Main ────────────────────────────────────────────────────────────────────

def _stripped(cell: dict) -> dict:
    return {k: v for k, v in cell.items() if not k.startswith("_")}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--walkforward", action="store_true",
                    help="also run the annual walk-forward phase")
    args = ap.parse_args()

    t0 = time.time()
    print(f"ETF grid search | bars_limit={BARS_LIMIT} | "
          f"eval {EVAL_START}→{EVAL_END} | split {SPLIT_DATE}")

    print("\n════ L1: top_n × holding_period × target_vol (100 cells) ════")
    l1 = layer1()
    print_top(l1, by="train")
    champ1 = pick_champion(l1, "L1")
    print_plateau(l1, champ1, ["top_n", "holding_period", "target_vol"])

    print("\n════ L2: abs_window × buffer_rank × atr_mult (100 cells) ════")
    l2 = layer2(champ1)
    print_top(l2, by="train")
    champ2 = pick_champion(l2, "L2")
    print_plateau(l2, champ2, ["abs_window", "buffer_rank", "atr_mult"])

    print("\n════ L3: windows × long-weight × vol_window (+bd sweep, 39) ════")
    l3 = layer3(champ2)
    print_top(l3, by="train")
    champ3 = pick_champion(l3, "L3")
    print_plateau(l3, champ3, ["vol_window", "breakdown_buffer"])

    wf = walkforward() if args.walkforward else []

    out = {
        "generated_at": str(date.today()),
        "eval_window": [EVAL_START, EVAL_END], "split": SPLIT_DATE,
        "baseline": _stripped(run_cell({})),
        "l1_champion": _stripped(champ1),
        "l2_champion": _stripped(champ2),
        "l3_champion": _stripped(champ3),
        "l1_cells": [_stripped(c) for c in l1],
        "l2_cells": [_stripped(c) for c in l2],
        "l3_cells": [_stripped(c) for c in l3],
        "walkforward": wf,
        "elapsed_s": round(time.time() - t0, 1),
    }
    OUT_PATH.write_text(json.dumps(out, ensure_ascii=False, indent=1),
                        encoding="utf-8")
    print("\nfinal champion:")
    _print_cell(champ3)
    print(f"\nresults → {OUT_PATH} | elapsed {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
