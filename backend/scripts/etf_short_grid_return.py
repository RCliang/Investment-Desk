"""Return-maximizing grid search for the SHORT weekly ETF rotation preset.

Extends etf_short_validation.py's protocol: the doc's three core knobs
(top_n / buffer_rank / atr_mult) plus the two axes the ablation showed
move returns most (abs_window, use_target_vol). Ranking is by FULL-window
total return per the request — but train/valid splits are recorded for
every cell so overfit champions (good full-window, dead out-of-sample)
are visible.

Grid (162 cells):
  top_n         {1, 2, 3}
  buffer_rank   {0, 2, 3}
  atr_mult      {2.0, 3.0, 4.0}
  abs_window    {60, 120, 180}
  use_target_vol {True, False}
Everything else stays FIXED at the short preset (SHORT_BASE): 20/60 risk-
adjusted momentum 6:4, weekly last-trading-day anchor, MA20 trend entry
filter, market gate MA250, equal weights, defensive exit-replacement.

Output: backend/data/etf_short_grid_return_results.json + console tables.

Usage:
    python scripts/etf_short_grid_return.py
"""

from __future__ import annotations

import json
import sys
import time
from datetime import date
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))
sys.path.insert(0, str(BACKEND_DIR / "scripts"))

from etf_short_validation import (  # noqa: E402
    EVAL_END, EVAL_START, TRAIN_END, run_config, _stripped,
)

OUT_PATH = BACKEND_DIR / "data" / "etf_short_grid_return_results.json"

GRID_AXES = {
    "top_n": [1, 2, 3],
    "buffer_rank": [0, 2, 3],
    "atr_mult": [2.0, 3.0, 4.0],
    "abs_window": [60, 120, 180],
    "use_target_vol": [True, False],
}


def main() -> None:
    import itertools

    keys = list(GRID_AXES)
    combos = [dict(zip(keys, vals))
              for vals in itertools.product(*(GRID_AXES[k] for k in keys))]
    print(f"ETF short-rotation RETURN grid: {len(combos)} cells | "
          f"eval {EVAL_START}→{EVAL_END} | split {TRAIN_END}")

    t0 = time.time()
    cells = []
    for i, cfg in enumerate(combos, 1):
        try:
            cell = run_config(cfg)
        except RuntimeError as e:          # degenerate curve (e.g. always cash)
            print(f"  [{i:3d}/{len(combos)}] SKIP {_stripped(cfg)}: {e}")
            continue
        cells.append(cell)
        if i % 10 == 0 or i == len(combos):
            best = max(cells, key=lambda c: c["full"]["total_pct"])
            print(f"  [{i:3d}/{len(combos)}] elapsed {time.time() - t0:5.0f}s "
                  f"| best so far {best['full']['total_pct']:+.1f}% "
                  f"({_fmt(best['cfg'])})")

    cells.sort(key=lambda c: -c["full"]["total_pct"])

    print("\n════ top 20 by FULL-window total return ════")
    print("  rank   full%   train%  valid%   dd%  sharpe(f/t/v)  calmar  "
          "to%   cfg")
    for r, c in enumerate(cells[:20], 1):
        f, tr, v = c["full"], c["train"], c["valid"]
        print(f"  {r:4d}  {f['total_pct']:7.1f} {tr['total_pct']:7.1f} "
              f"{v['total_pct']:7.1f} {f['max_dd_pct']:6.1f} "
              f"{f['sharpe']:5.2f}/{tr['sharpe']:5.2f}/{v['sharpe']:5.2f} "
              f"{f['calmar']:6.2f} {f['avg_turnover_pct']:5.1f}  {_fmt(c['cfg'])}")

    robust = [c for c in cells
              if c["valid"]["sharpe"] >= 0.7 * c["train"]["sharpe"]
              and c["valid"]["total_pct"] > 0]
    print(f"\n  {len(robust)}/{len(cells)} cells survive the "
          f"valid-sharpe≥0.7×train + valid>0 sanity gate; "
          f"best of those:")
    if robust:
        c = max(robust, key=lambda x: x["full"]["total_pct"])
        f = c["full"]
        print(f"    ret {f['total_pct']:+.1f}% dd {f['max_dd_pct']:.1f}% "
              f"sharpe {f['sharpe']:.2f} | {_fmt(c['cfg'])}")

    out = {
        "generated_at": str(date.today()),
        "objective": "max full-window total return",
        "eval_window": [EVAL_START, EVAL_END], "split": TRAIN_END,
        "grid_axes": GRID_AXES,
        "cells": [_stripped(c) for c in cells],
        "elapsed_s": round(time.time() - t0, 1),
    }
    OUT_PATH.write_text(json.dumps(out, ensure_ascii=False, indent=1),
                        encoding="utf-8")
    print(f"\nresults → {OUT_PATH} | elapsed {time.time() - t0:.0f}s")


def _fmt(c: dict) -> str:
    keys = ["top_n", "buffer_rank", "atr_mult", "abs_window",
            "use_target_vol"]
    return " ".join(f"{k}={c[k]}" for k in keys if k in c)


if __name__ == "__main__":
    main()
