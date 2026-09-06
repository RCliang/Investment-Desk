"""Equity-curve chart: short-rotation champion vs mid-term live preset.

Re-runs the two head-to-head configs from etf_short_validation.py (identical
engine/backtester wiring, same bars and cost model) and plots normalized
daily NAV plus drawdown, alongside the pool equal-weight index and 510300
buy & hold. Numbers must reconcile with backend/data/
etf_short_validation_results.json.

Output: backend/data/etf_short_vs_midterm_equity.png

Usage:
    python scripts/plot_etf_equity_curves.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))
sys.path.insert(0, str(BACKEND_DIR / "scripts"))

from etf_short_validation import (  # noqa: E402
    EVAL_END, EVAL_START, TRAIN_END, _context,
)
from app.services.quant.etf_lab import run_preset  # noqa: E402

OUT_PATH = BACKEND_DIR / "data" / "etf_short_vs_midterm_equity.png"

SHORT_CHAMPION = dict(top_n=2, buffer_rank=0, atr_mult=3.0)
RETURN_CHAMPION = dict(top_n=1, buffer_rank=3, atr_mult=3.0,
                       abs_window=120, use_target_vol=False)
SHARPE_CHAMPION = dict(top_n=3, buffer_rank=3, atr_mult=4.0,
                       abs_window=120, use_target_vol=True)


def run_raw(cfg: dict | None, preset: str) -> dict:
    """Raw backtest result via etf_lab.run_preset (the ONE wiring copy);
    keeps equity_curve + benchmark_curve that etf_short_validation strips."""
    return run_preset(preset, overrides=cfg, bars=_context()["bars"],
                      membership=_context()["membership"])["result"]


def to_series(curve: list[dict], label: str) -> pd.Series:
    s = pd.Series({p["date"]: p["equity"] for p in curve}, name=label)
    s.index = pd.to_datetime(s.index)
    return s[(s.index >= EVAL_START) & (s.index <= EVAL_END)]


def main() -> None:
    short = run_raw(SHORT_CHAMPION, "short")
    ret_champ = run_raw(RETURN_CHAMPION, "short")
    sharpe_champ = run_raw(SHARPE_CHAMPION, "short")
    mid = run_raw(None, "mid")
    short_ret = short["equity_curve"][-1]["equity"] / 1e6 - 1
    mid_ret = mid["equity_curve"][-1]["equity"] / 1e6 - 1
    print(f"curve starts {short['equity_curve'][0]['date']} (warm-up from "
          f"2016); raw end-to-end returns short {short_ret:+.1%} "
          f"mid {mid_ret:+.1%}")

    s_short = to_series(short["equity_curve"], None)
    s_mid = to_series(mid["equity_curve"], None)
    s_ret = to_series(ret_champ["equity_curve"], None)
    s_sharpe = to_series(sharpe_champ["equity_curve"], None)
    s_ew = to_series(short["benchmark_curve"], None)
    curves = [
        s_sharpe.rename(f"短线Sharpe冠军·top3/atr4/abs120/波动率控制 "
                        f"({s_sharpe.iloc[-1] / s_sharpe.iloc[0] - 1:+.1%})"),
        s_mid.rename(f"中期版·实盘配置 ({s_mid.iloc[-1] / s_mid.iloc[0] - 1:+.1%})"),
        s_ret.rename(f"短线收益冠军·top1/无波动率控制 (参照) "
                     f"({s_ret.iloc[-1] / s_ret.iloc[0] - 1:+.1%})"),
        s_ew.rename(f"池等权基准·无成本 ({s_ew.iloc[-1] / s_ew.iloc[0] - 1:+.1%})"),
    ]
    ctx = _context()
    bh = ctx["bars"]["510300"].set_index("date")["close"]
    bh.index = pd.to_datetime(bh.index)
    bh = bh[(bh.index >= EVAL_START) & (bh.index <= EVAL_END)]
    curves.append((bh / bh.iloc[0]).rename(
        f"510300 买入持有 ({bh.iloc[-1] / bh.iloc[0] - 1:+.1%})"))

    # normalize every curve to 1.0 at EVAL_START
    curves = [c / c.iloc[0] for c in curves]

    plt.rcParams["font.sans-serif"] = [
        "PingFang SC", "Hiragino Sans GB", "Arial Unicode MS", "Heiti TC",
        "STHeiti", "sans-serif"]
    plt.rcParams["axes.unicode_minus"] = False

    fig, (ax, ax2) = plt.subplots(
        2, 1, figsize=(12, 7.5), sharex=True,
        gridspec_kw={"height_ratios": [3, 1]}, dpi=150)

    colors = ["#2ca02c", "#1f77b4", "#d62728", "#9467bd", "#7f7f7f"]
    for c, color in zip(curves, colors):
        ax.plot(c.index, c.values, lw=1.6, color=color, label=c.name)

    split = pd.Timestamp(TRAIN_END)
    ax.axvline(split, color="#2ca02c", ls="--", lw=1.2, alpha=0.8)
    ax.text(split, ax.get_ylim()[1] * 0.97, " 样本内|样本外切分线",
            color="#2ca02c", fontsize=9, va="top")
    ax.set_ylabel("累计净值(起点=1)")
    ax.set_title("ETF轮动策略回测净值对比(2019-10 → 2026-09,含万1佣金+0.1%滑点)",
                 fontsize=13)
    ax.legend(loc="upper left", frameon=False, fontsize=10)
    ax.grid(alpha=0.3)

    for c, color in zip(curves, colors):
        dd = c / c.cummax() - 1
        ax2.fill_between(dd.index, dd.values * 100, 0, color=color, alpha=0.35)
        ax2.plot(dd.index, dd.values * 100, lw=1.0, color=color)
    ax2.set_ylabel("回撤 (%)")
    ax2.grid(alpha=0.3)

    fig.tight_layout()
    fig.savefig(OUT_PATH, bbox_inches="tight")
    print(f"chart → {OUT_PATH}")


if __name__ == "__main__":
    main()
