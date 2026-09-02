"""Plot the grid-search TOP10 configs' equity curves (line chart).

Reads backend/data/etf_grid_search_results.json, ranks all layer cells by
FULL-window Sharpe (the plan's primary selection metric), dedups configs,
re-runs the top 10 to recover their equity curves (curves are stripped
from the JSON; ~0.5s per cell), and renders:

  - top-10 curves (thin, ranked colors)
  - the landed champion (thick crimson; from the sensitivity round, not a
    grid cell, so it is added explicitly)
  - the equal-weight pool benchmark (gray dashed)
  - a train/valid split marker at 2024-09-15

Output: docs/etf-grid-search-top10-curves.png (embedded in
docs/etf-rotation-grid-search-plan.md 执行结果).

Usage:
    python scripts/etf_grid_top10_plot.py [n=10]
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))
sys.path.insert(0, str(BACKEND_DIR / "scripts"))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

from etf_grid_search import EVAL_START, EVAL_END, SPLIT_DATE, run_cell  # noqa: E402

RESULTS = BACKEND_DIR / "data" / "etf_grid_search_results.json"
OUT_PNG = BACKEND_DIR.parent / "docs" / "etf-grid-search-top10-curves.png"

# CJK font: tofu boxes otherwise on Windows defaults.
plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "SimSun"]
plt.rcParams["axes.unicode_minus"] = False

# The landed champion = grid TOP1 cell by decision (2026-09-02 落地记录):
# tv0.12 / lw0.7 / atr4.0 — identical to the #1 grid cell, so the thick
# crimson line overlays #1 on purpose (the decision marker).
CHAMPION = dict(top_n=2, holding_period=20, target_vol=0.12, buffer_rank=3,
                abs_window=180, atr_mult=4.0, breakdown_buffer=0.03,
                windows=(60, 120, 250), weights=(0.15, 0.15, 0.7),
                vol_window=20)


def _norm_curve(curve: list[dict], lo: str = EVAL_START, hi: str = EVAL_END):
    pts = [p for p in curve if lo <= p["date"] <= hi]
    if not pts:
        return None, None
    base = pts[0]["equity"]
    x = pd.to_datetime([p["date"] for p in pts])
    y = [p["equity"] / base for p in pts]
    return x, y


def _short_label(cfg: dict) -> str:
    w = cfg["windows"]
    return (f"top{cfg['top_n']} hp{cfg['holding_period']} "
            f"tv{cfg['target_vol'] or '关'} 窗口{','.join(map(str, w))} "
            f"lw{cfg['weights'][-1]} vw{cfg['vol_window']} "
            f"atr{cfg['atr_mult']} buf{cfg['buffer_rank']} abs{cfg['abs_window']}")


def main(n: int = 10) -> None:
    res = json.loads(RESULTS.read_text(encoding="utf-8"))
    cells, seen = [], set()
    for layer in ("l1_cells", "l2_cells", "l3_cells"):
        for c in res.get(layer, []):
            key = json.dumps(c["cfg"], sort_keys=True, default=str)
            if key in seen:
                continue
            seen.add(key)
            cells.append(c)
    top = sorted(cells, key=lambda c: -c["full"]["sharpe"])[:n]

    fig, ax = plt.subplots(figsize=(11.5, 7.6), dpi=150)

    # benchmark (dashed gray)
    bench = run_cell({})
    bx, by = _norm_curve(bench["_curve"])
    ax.plot(bx, by, color="#9aa0a6", lw=1.5, ls="--", zorder=2,
            label=f"等权基准 (夏普 {bench['full']['sharpe']:.2f} / 回撤 "
                  f"{bench['full']['max_dd_pct']:.0f}%)")

    # top-n curves — tab10: high mutual contrast vs viridis' mid-range mash
    cmap = plt.get_cmap("tab10")
    for i, c in enumerate(top):
        cell = run_cell({**c["cfg"],
                         "windows": tuple(c["cfg"]["windows"]),
                         "weights": tuple(c["cfg"]["weights"])})
        x, y = _norm_curve(cell["_curve"])
        ax.plot(x, y, color=cmap(i % 10), lw=1.3, alpha=0.9, zorder=3,
                label=f"#{i+1} {_short_label(c['cfg'])} "
                      f"(夏普 {c['full']['sharpe']:.2f})")

    # landed champion (thick crimson)
    champ = run_cell(CHAMPION)
    cx, cy = _norm_curve(champ["_curve"])
    ax.plot(cx, cy, color="#c0392b", lw=2.6, zorder=5,
            label=f"★ 最终冠军 {_short_label(CHAMPION)} "
                  f"(夏普 {champ['full']['sharpe']:.2f} / 回撤 "
                  f"{champ['full']['max_dd_pct']:.1f}%)")

    # train/valid split marker
    split = pd.to_datetime(SPLIT_DATE)
    ax.axvline(split, color="#7f8c8d", lw=1.0, ls=":", zorder=1)
    ymax = ax.get_ylim()[1]
    ax.text(split, ymax, "  训练期 | 验证期 →", fontsize=9, color="#7f8c8d",
            va="top", ha="left")

    ax.set_title(f"ETF 轮动网格搜索 TOP{n} 收益率曲线（按全窗夏普排序，"
                 f"{EVAL_START} → {EVAL_END}，含成本）", fontsize=13)
    ax.set_ylabel("累计净值（期初 = 1）")
    ax.set_xlabel("日期")
    ax.grid(alpha=0.25, lw=0.5)
    # legend below the canvas: keeps every curve unobstructed
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.10),
              ncol=2, fontsize=7.6, framealpha=0.95, labelspacing=0.4,
              borderpad=0.6, columnspacing=1.6)
    fig.tight_layout()
    OUT_PNG.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT_PNG, bbox_inches="tight")
    print(f"saved → {OUT_PNG}")

    # markdown table for the doc
    lines = ["| 排名 | 配置 | 全窗收益 | 回撤 | 夏普 | 训练夏普 | 验证夏普 |",
             "|---|---|---|---|---|---|---|"]
    for i, c in enumerate(top):
        f = c["full"]
        lines.append(
            f"| #{i+1} | `{_short_label(c['cfg'])}` | {f['total_pct']:.1f}% "
            f"| {f['max_dd_pct']:.1f}% | {f['sharpe']:.3f} "
            f"| {c['train']['sharpe']:.2f} | {c['valid']['sharpe']:.2f} |")
    print("\n".join(lines))


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 10)
