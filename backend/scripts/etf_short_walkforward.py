"""Walk-forward validation for the SHORT weekly rotation grid.

Proper out-of-sample selection test: for each test year, rank all 162
grid configs by TRAILING 2-calendar-year Sharpe, take the top 5 as an
equal-weight portfolio, and measure its forward-year performance. A
config family that only worked in-sample shows up here as the WF
portfolio collapsing in later test years.

Comparison lines per test year: WF top-5 portfolio, the FIXED Sharpe
champion (picked once on the full window — the overfit reference), the
return champion, and the live mid-term preset. Same cost model and bars
as etf_short_validation.py; Sharpe convention identical (√252).

Output: backend/data/etf_short_walkforward_results.json + console table.

Usage:
    python scripts/etf_short_walkforward.py
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

from etf_short_grid_return import GRID_AXES, _fmt  # noqa: E402
from etf_short_validation import (  # noqa: E402
    EVAL_END, EVAL_START, MID_BASE, run_config,
)
from plot_etf_equity_curves import run_raw  # noqa: E402

OUT_PATH = BACKEND_DIR / "data" / "etf_short_walkforward_results.json"

RETURN_CHAMPION = dict(top_n=1, buffer_rank=3, atr_mult=3.0,
                       abs_window=120, use_target_vol=False)
SHARPE_CHAMPION = dict(top_n=3, buffer_rank=3, atr_mult=4.0,
                       abs_window=120, use_target_vol=True)

TEST_YEARS = [2021, 2022, 2023, 2024, 2025, 2026]
TOP_K = 5


def seg_metrics(curve: list[dict], lo: str, hi: str) -> dict | None:
    pts = [p for p in curve if lo <= p["date"] <= hi]
    eq = np.array([p["equity"] for p in pts], dtype=float)
    if len(pts) < 40 or eq[0] <= 0:
        return None
    rets = np.diff(eq) / eq[:-1]
    std = rets.std(ddof=1) if len(rets) > 1 else 0.0
    peak = np.maximum.accumulate(eq)
    return {
        "total_pct": round((eq[-1] / eq[0] - 1) * 100, 2),
        "sharpe": round(float(rets.mean() / std * math.sqrt(252)), 3)
        if std > 0 else 0.0,
        "max_dd_pct": round(float(np.max((peak - eq) / peak)) * 100, 2),
        "_rets": rets, "_dates": [p["date"] for p in pts][1:],
    }


def to_curve(raw: dict) -> list[dict]:
    return raw["equity_curve"]


def main() -> None:
    t0 = time.time()
    print("building candidate curve pool (162 grid cells)...")
    import itertools
    keys = list(GRID_AXES)
    combos = [dict(zip(keys, v))
              for v in itertools.product(*(GRID_AXES[k] for k in keys))]
    cells = []
    for i, cfg in enumerate(combos, 1):
        try:
            cells.append(run_config(cfg))       # keeps _curve
        except RuntimeError:
            pass
        if i % 40 == 0:
            print(f"  {i}/{len(combos)} cells | {time.time() - t0:.0f}s")

    mid_raw = run_raw(None, "mid")
    print(f"pool ready: {len(cells)} cells + mid-term | "
          f"{time.time() - t0:.0f}s\n")

    fixed = {
        "WF_top5": None,  # computed per year
        "sharpe_champ_fixed": next(
            c for c in cells
            if all(c["cfg"][k] == v for k, v in SHARPE_CHAMPION.items())),
        "return_champ_fixed": next(
            c for c in cells
            if all(c["cfg"][k] == v for k, v in RETURN_CHAMPION.items())),
        "mid_term": {"_curve": to_curve(mid_raw)},
    }

    rows = []
    for y in TEST_YEARS:
        lo, hi = f"{y}-01-01", f"{y}-12-31"
        train_lo = f"{y - 2}-01-01"
        if y == 2021:
            train_lo = EVAL_START               # shorter trailing window
        # trailing-Sharpe ranking → top-K portfolio
        ranked = sorted(
            (c for c in cells
             if (m := seg_metrics(c["_curve"], train_lo, f"{y - 1}-12-31"))),
            key=lambda c: -seg_metrics(c["_curve"], train_lo,
                                       f"{y - 1}-12-31")["sharpe"])
        top = ranked[:TOP_K]
        # equal-weight daily-return portfolio of the top-K on the test year
        segs = [seg_metrics(c["_curve"], lo, hi) for c in top]
        segs = [s for s in segs if s is not None]
        n = min(len(s["_rets"]) for s in segs)
        wf_rets = np.mean([s["_rets"][:n] for s in segs], axis=0)
        std = wf_rets.std(ddof=1)
        wf = {
            "total_pct": round((np.prod(1 + wf_rets) - 1) * 100, 2),
            "sharpe": round(float(wf_rets.mean() / std * math.sqrt(252)), 3)
            if std > 0 else 0.0,
        }
        picked = " ".join(_fmt(c["cfg"]) + " |" for c in top)

        row = {"year": y, "wf_top5": wf,
               "wf_picked": [_fmt(c["cfg"]) for c in top]}
        for name, cell in fixed.items():
            if cell is None:
                continue
            m = seg_metrics(cell["_curve"], lo, hi)
            row[name] = ({k: m[k] for k in ("total_pct", "sharpe",
                                            "max_dd_pct")}
                         if m else None)
        rows.append(row)
        print(f"── test {y} (trailing train {train_lo}→{y - 1}) ──")
        print(f"  WF_top5        ret {wf['total_pct']:+7.1f}%  "
              f"sharpe {wf['sharpe']:5.2f}   picked: {picked}")
        for name in ("sharpe_champ_fixed", "return_champ_fixed", "mid_term"):
            m = row[name]
            print(f"  {name:17s} ret {m['total_pct']:+7.1f}%  "
                  f"sharpe {m['sharpe']:5.2f}  dd {m['max_dd_pct']:5.1f}%")

    # compound the WF portfolio vs fixed lines across test years
    print("\n════ compounded over test years ════")
    for name in ("wf_top5", "sharpe_champ_fixed", "return_champ_fixed",
                 "mid_term"):
        tot = 1.0
        for row in rows:
            m = row[name]
            tot *= 1 + m["total_pct"] / 100 if m else 1.0
        print(f"  {name:17s} {(tot - 1) * 100:+8.1f}%")

    out = {
        "generated_at": str(date.today()),
        "protocol": {"test_years": TEST_YEARS, "top_k": TOP_K,
                     "trailing_train_years": 2,
                     "selection_metric": "trailing sharpe"},
        "sharpe_champion": SHARPE_CHAMPION,
        "return_champion": RETURN_CHAMPION,
        "rows": [{k: v for k, v in r.items() if k != "wf_picked"}
                 for r in rows],
        "wf_picked_by_year": {str(r["year"]): r["wf_picked"] for r in rows},
        "elapsed_s": round(time.time() - t0, 1),
    }
    OUT_PATH.write_text(json.dumps(out, ensure_ascii=False, indent=1),
                        encoding="utf-8")
    print(f"\nresults → {OUT_PATH} | elapsed {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
