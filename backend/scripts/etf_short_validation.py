"""Validation harness for the SHORT ETF rotation preset (etf_short_rotation).

docs/ETF轮动策略设计方案.md §九 落地设计 — parameter-light protocol:

  Grid (36 cells): top_n {1,2,3} × buffer_rank {0,2,3,5} × atr_mult
  {2,3,4}. Everything else is FIXED from logic, not searched:
  momentum 20/60 (6:4) risk-adjusted, abs gate 60d, weekly last-trading-day
  anchor, MA20 trend entry filter, market gate MA250, 12% target vol,
  equal weights, defensive exit-replacement.

  Anti-overfit: metrics sliced into TRAIN 2019-10-08→2023-12-29 and
  VALID 2024-01-01→2026-09-04; champion = max train Sharpe among cells
  with valid Sharpe ≥ 0.7×train and valid maxDD ≤ 25%. Bars go back to
  2016 (limit 2600) so every fixed window is warm before EVAL_START —
  all cells share identical windows, no differential warm-up bias.

  Head-to-head: the live mid-term preset (calendar monthly, 60/120/250,
  abs 180, gate OFF) on the same window + pool equal-weight + 510300
  buy&hold. Decision rule (§9.3): the short preset must beat the
  mid-term engine after costs or it does not go live.

Output: backend/data/etf_short_validation_results.json + console tables.

Usage:
    python scripts/etf_short_validation.py
"""

from __future__ import annotations

import json
import math
import sys
import time
from collections import Counter
from datetime import date
from pathlib import Path

import numpy as np

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from app.db import SessionLocal                              # noqa: E402
from app.services.quant import etf_pool, etf_signal_service  # noqa: E402
from app.services.quant.etf_rotation import EtfRotationEngine  # noqa: E402
from app.services.quant.rotation_backtest import RotationBacktester  # noqa: E402

OUT_PATH = BACKEND_DIR / "data" / "etf_short_validation_results.json"

EVAL_START = "2019-10-08"
TRAIN_END = "2023-12-29"
EVAL_END = "2026-09-04"
BARS_LIMIT = 2600            # ~2016-01 → every fixed window warm by 2019-10

# Short preset — everything FIXED outside the grid (§9.1).
SHORT_BASE = dict(
    windows=(20, 60), weights=(0.6, 0.4), vol_window=20, abs_window=60,
    rebalance_anchor="weekly", rebalance_mode="fixed", holding_period=5,
    use_abs_gate=True, use_buffer=True, use_market_gate=True,
    market_ma_window=250, use_trend_filter=True, weight_mode="equal",
    use_target_vol=True, target_vol=0.12, exit_replacement=True,
)
# Live mid-term preset (mirrors etf_signal_service defaults + scan config).
MID_BASE = dict(
    windows=(60, 120, 250), weights=(0.15, 0.15, 0.7), vol_window=20,
    abs_window=180, rebalance_anchor="calendar", rebalance_mode="fixed",
    holding_period=20, use_abs_gate=True, use_buffer=True,
    use_market_gate=False, market_ma_window=200, use_trend_filter=False,
    weight_mode="equal", use_target_vol=True, target_vol=0.12,
    exit_replacement=True, top_n=2, buffer_rank=3, atr_mult=4.0,
)


# ── Metrics from an equity-curve slice (same convention as etf_grid_search) ─

def slice_metrics(curve: list[dict], lo: str, hi: str,
                  rebalance_log: list[dict] | None = None) -> dict | None:
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


# ── Run one config ──────────────────────────────────────────────────────────

_CTX: dict = {}


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
        _CTX["defensive"] = {t for t, c in classes.items() if c == "防守"}
    return _CTX


def run_config(cfg: dict) -> dict:
    """One backtest (engine + backtester fully configured). Returns
    {cfg, full/train/valid metrics, bench slice, curve, trades, rebal_log}.
    """
    ctx = _context()
    c = {**SHORT_BASE, **cfg}
    engine = EtfRotationEngine(
        cash_ticker=etf_pool.get_cash_ticker(),
        top_n=c["top_n"], buffer_rank=c["buffer_rank"],
        holding_period=c["holding_period"],
        windows=tuple(c["windows"]), weights=tuple(c["weights"]),
        vol_window=c["vol_window"], abs_window=c["abs_window"],
        use_abs_gate=c["use_abs_gate"], use_buffer=c["use_buffer"],
        use_market_gate=c["use_market_gate"],
        market_ma_window=c["market_ma_window"],
        market_gate_tickers=ctx["equity_like"],
        use_trend_filter=c["use_trend_filter"],
        replacement_tickers=ctx["defensive"] if c["exit_replacement"] else None,
        rebalance_mode=c["rebalance_mode"],
        rebalance_anchor=c["rebalance_anchor"],
        weight_mode=c["weight_mode"],
        use_target_vol=c["use_target_vol"], target_vol=c["target_vol"])
    bt = RotationBacktester(
        commission_rate=etf_signal_service.ETF_COMMISSION_RATE,
        commission_min=etf_signal_service.ETF_COMMISSION_MIN,
        stamp_duty_rate=etf_signal_service.ETF_STAMP_DUTY_RATE,
        slippage_rate=etf_signal_service.ETF_SLIPPAGE_RATE,
        stop_mode="atr", atr_mult=c["atr_mult"],
        breakdown_buffer=0.03,
        cash_tickers={etf_pool.get_cash_ticker()},
        replacement_fn=engine.pick_replacement if c["exit_replacement"]
        else None)
    out = bt.run(ctx["bars"], ctx["membership"], engine,
                 initial_capital=1e6)
    r = out["result"]
    curve, bench = r["equity_curve"], r["benchmark_curve"]
    log_ = r.get("rebalance_log") or []
    trades = r.get("trades") or []
    cell = {
        "cfg": {k: (list(v) if isinstance(v, tuple) else v)
                for k, v in c.items()},
        "full": slice_metrics(curve, EVAL_START, EVAL_END, log_),
        "train": slice_metrics(curve, EVAL_START, TRAIN_END, log_),
        "valid": slice_metrics(curve, TRAIN_END, EVAL_END, log_),
        "bench_full": slice_metrics(bench, EVAL_START, EVAL_END),
        "trade_count": r["trade_count"],
        "win_rate_pct": r["win_rate_pct"],
        "exit_reasons": dict(Counter(t["exit_reason"] for t in trades)),
        "asset_pnl": r["sector_pnl"],
        "_curve": curve,
        "_trades": trades,
    }
    if any(cell[k] is None for k in ("full", "train", "valid")):
        raise RuntimeError(f"degenerate curve for cfg={c}")
    return cell


def _print_cell(cell: dict) -> None:
    for p in ("full", "train", "valid"):
        m = cell[p]
        print(f"  {p:5s} ret {m['total_pct']:7.2f}% ann {m['annual_pct']:6.2f}%"
              f" dd {m['max_dd_pct']:6.2f}% sharpe {m['sharpe']:6.3f}"
              f" calmar {m['calmar']:6.3f} to {m['avg_turnover_pct']:5.2f}%")


def _fmt(c: dict) -> str:
    keys = ["top_n", "buffer_rank", "atr_mult", "use_trend_filter",
            "use_market_gate", "use_abs_gate", "use_target_vol"]
    return " ".join(f"{k}={c[k]}" for k in keys if k in c)


def pick_champion(cells: list[dict], label: str) -> dict:
    ok = [c for c in cells
          if c["train"]["sharpe"] > 0
          and c["valid"]["sharpe"] >= 0.7 * c["train"]["sharpe"]
          and c["valid"]["max_dd_pct"] <= 25.0]
    pool_ = ok if ok else [c for c in cells if c["train"]["sharpe"] > 0] or cells
    champ = max(pool_, key=lambda c: c["train"]["sharpe"])
    print(f"\n[{label}] champion (of {len(cells)} cells, "
          f"{len(ok)} passed valid-gate):")
    _print_cell(champ)
    print(f"  cfg: {_fmt(champ['cfg'])}")
    if not ok:
        print("  ⚠ no cell passed the valid non-degradation gate")
    return champ


def yearly(cell: dict) -> dict[str, float]:
    """Calendar-year returns from the equity curve."""
    out: dict[str, float] = {}
    for y in range(2019, 2027):
        lo, hi = f"{y}-01-01", f"{y}-12-31"
        pts = [p for p in cell["_curve"] if lo <= p["date"] <= hi]
        if len(pts) >= 2 and pts[0]["equity"] > 0:
            out[str(y)] = round(pts[-1]["equity"] / pts[0]["equity"] - 1, 4)
    return out


def buyhold_510300() -> dict:
    ctx = _context()
    df = ctx["bars"]["510300"].set_index("date")["close"]
    df = df[(df.index >= EVAL_START) & (df.index <= EVAL_END)]
    eq = df / df.iloc[0]
    rets = eq.pct_change().dropna()
    std = rets.std()
    return {
        "total_pct": round((eq.iloc[-1] - 1) * 100, 2),
        "annual_pct": round(((eq.iloc[-1]) ** (252 / len(eq)) - 1) * 100, 2),
        "sharpe": round(float(rets.mean() / std * math.sqrt(252)), 3)
        if std > 0 else 0.0,
    }


# ── Main ────────────────────────────────────────────────────────────────────

def _stripped(cell: dict) -> dict:
    return {k: v for k, v in cell.items() if not k.startswith("_")}


def main():
    t0 = time.time()
    print(f"ETF SHORT-rotation validation | bars_limit={BARS_LIMIT} | "
          f"train {EVAL_START}→{TRAIN_END} | valid →{EVAL_END}")

    print("\n════ grid: top_n × buffer_rank × atr_mult (36 cells) ════")
    grid = []
    for tn in (1, 2, 3):
        for br in (0, 2, 3, 5):
            for am in (2.0, 3.0, 4.0):
                cell = run_config(dict(top_n=tn, buffer_rank=br, atr_mult=am))
                grid.append(cell)
    print("\n  top 10 by train sharpe:")
    for c in sorted(grid, key=lambda x: -x["train"]["sharpe"])[:10]:
        print(f"    train {c['train']['sharpe']:6.3f} valid "
              f"{c['valid']['sharpe']:6.3f} dd(v) "
              f"{c['valid']['max_dd_pct']:5.1f}% | {_fmt(c['cfg'])}")
    champ = pick_champion(grid, "GRID")

    base = {k: champ["cfg"][k] for k in ("top_n", "buffer_rank", "atr_mult")}

    print("\n════ ablations at champion ════")
    ablations = {}
    for label, cfg in [
        ("no_trend_filter", {**base, "use_trend_filter": False}),
        ("no_market_gate", {**base, "use_market_gate": False}),
        ("no_gates", {**base, "use_trend_filter": False,
                      "use_market_gate": False}),
        ("no_target_vol", {**base, "use_target_vol": False}),
        ("no_abs_gate", {**base, "use_abs_gate": False}),
        ("no_exit_replacement", {**base, "exit_replacement": False}),
        ("no_buffer", {**base, "use_buffer": False}),
    ]:
        cell = run_config(cfg)
        ablations[label] = cell
        m = cell["full"]
        print(f"  {label:20s} ret {m['total_pct']:8.2f}% "
              f"dd {m['max_dd_pct']:6.2f}% sharpe {m['sharpe']:6.3f} "
              f"trades {cell['trade_count']:4d}")

    print("\n════ head-to-head vs mid-term preset (same window, same pool) ════")
    mid = run_config(MID_BASE)
    print("  short champion:")
    _print_cell(champ)
    print("  mid-term (live preset):")
    _print_cell(mid)

    bench = champ["bench_full"]
    bh = buyhold_510300()
    print(f"\n  pool equal-weight (no costs): ret {bench['total_pct']:.2f}% "
          f"dd {bench['max_dd_pct']:.2f}% sharpe {bench['sharpe']:.3f}")
    print(f"  510300 buy&hold:             ret {bh['total_pct']:.2f}% "
          f"sharpe {bh['sharpe']:.3f}")

    print("\n  yearly returns:")
    ys, ym = yearly(champ), yearly(mid)
    years = sorted(set(ys) | set(ym))
    print("    year  short  mid-term")
    for y in years:
        print(f"    {y}  {ys.get(y, float('nan')):+.1%}  "
              f"{ym.get(y, float('nan')):+.1%}")

    out = {
        "generated_at": str(date.today()),
        "eval_window": [EVAL_START, EVAL_END], "split": TRAIN_END,
        "bars_limit": BARS_LIMIT,
        "pool_size": len(_CTX["bars"]),
        "short_base": {k: (list(v) if isinstance(v, tuple) else v)
                       for k, v in SHORT_BASE.items()},
        "grid_cells": [_stripped(c) for c in grid],
        "champion": _stripped(champ),
        "champion_yearly": yearly(champ),
        "ablations": {k: _stripped(v) for k, v in ablations.items()},
        "mid_term": _stripped(mid),
        "mid_term_yearly": yearly(mid),
        "benchmark_pool_ew": bench,
        "benchmark_510300": bh,
        "elapsed_s": round(time.time() - t0, 1),
    }
    OUT_PATH.write_text(json.dumps(out, ensure_ascii=False, indent=1),
                        encoding="utf-8")
    print(f"\nresults → {OUT_PATH} | elapsed {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
