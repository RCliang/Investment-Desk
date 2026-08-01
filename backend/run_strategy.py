"""Run multi-factor trend-following strategy on real monitored stocks.

Loads all bars from DB, runs the full pipeline:
  Factor computation → Market-cap neutralization → IC analysis →
  Composite scoring → Portfolio selection → Backtest with costs
"""
import json
import sqlite3
import time

import pandas as pd
import numpy as np

from app.services.quant.factor_model import MultiFactorEngine
from app.services.quant.portfolio_backtest import PortfolioBacktester
from app.services.quant.signal_service import _load_bars_df
from app.db import SessionLocal
from sqlalchemy import select
from app.models.chain_models import DailyBar


def load_all_bars(db) -> dict[str, pd.DataFrame]:
    """Load all tickers' bars from DB."""
    tickers = [r[0] for r in db.execute(
        select(DailyBar.ticker).distinct().order_by(DailyBar.ticker.asc())
    ).all()]

    bars = {}
    for t in tickers:
        df = _load_bars_df(db, t, limit=600)
        if df is not None and len(df) >= 80:
            bars[t] = df
    return bars


def main():
    db = SessionLocal()
    print("=" * 70)
    print("  Multi-Factor Trend-Following Strategy — Real Stock Backtest")
    print("  Holding Period: 20 days | Top-N: 20 stocks | IC Window: 60 days")
    print("=" * 70)

    # Step 1: Load data
    print("\n[1/4] Loading bars from database...")
    t0 = time.time()
    bars = load_all_bars(db)
    print(f"  Loaded {len(bars)} tickers in {time.time()-t0:.1f}s")

    # Data summary
    all_dates = set()
    for df in bars.values():
        all_dates.update(df["date"].tolist())
    print(f"  Date range: {min(all_dates)} to {max(all_dates)}")
    print(f"  Avg bars per ticker: {np.mean([len(df) for df in bars.values()]):.0f}")

    # Step 2: Run factor model
    print("\n[2/4] Running multi-factor engine...")
    print(f"  Factors: momentum_20, momentum_60, trend_slope, multi_ma_align,")
    print(f"          breakout_strength, volume_momentum, trend_consistency")
    print(f"  Pipeline: compute → neutralize → IC rank → ICIR weight → composite")

    engine = MultiFactorEngine(
        holding_period=20,
        top_n=20,
        max_weight=0.10,
        ic_window=60,
        weighting_method="icir",
    )

    t0 = time.time()
    model_result = engine.run(bars)
    print(f"  Factor model completed in {time.time()-t0:.1f}s")

    # IC Summary
    print(f"\n  ── IC Summary (latest valid date) ──")
    print(f"  {'Factor':<22} {'IC Mean':>8} {'ICIR':>8} {'Win Rate':>10}")
    print(f"  {'─'*22} {'─'*8} {'─'*8} {'─'*10}")
    for name, stats in model_result["ic_summary"].items():
        ic = stats["ic_mean"]
        icir = stats["icir"]
        win = stats["ic_pct_positive"]
        indicator = " ★" if abs(icir) > 0.5 else ""
        print(f"  {name:<22} {ic:>8.4f} {icir:>8.4f} {win:>9.1%}{indicator}")

    # Step 3: Portfolio backtest
    print("\n[3/4] Running portfolio backtest...")
    bt = PortfolioBacktester()
    t0 = time.time()
    result = bt.run(
        bars, engine,
        initial_capital=1_000_000,
        strategy_set="multi_factor_trend",
    )
    print(f"  Backtest completed in {time.time()-t0:.1f}s")

    # Step 4: Results
    print(f"\n[4/4] Results")
    print(f"  {'='*50}")
    print(f"  Period:          {result.start_date} → {result.end_date}")
    print(f"  Initial Capital: ¥{result.initial_capital:>14,.0f}")
    print(f"  Final Equity:    ¥{result.final_equity:>14,.0f}")
    print(f"  {'─'*50}")
    print(f"  Total Return:    {result.total_return_pct:>+10.2f}%")
    print(f"  Annual Return:   {result.annual_return_pct:>+10.2f}%")
    print(f"  Max Drawdown:    {result.max_drawdown_pct:>10.2f}%")
    print(f"  Sharpe Ratio:    {result.sharpe_ratio:>10.3f}")
    print(f"  {'─'*50}")
    print(f"  Rebalances:      {result.rebalance_count:>10}")
    print(f"  Avg Turnover:    {result.avg_turnover_pct:>9.1f}%")
    print(f"  Hit Rate:        {result.hit_rate_pct:>9.1f}%")
    print(f"  {'='*50}")

    # Latest portfolio
    if result.rebalance_log:
        rb = result.rebalance_log[-1]
        print(f"\n  Latest Portfolio ({rb['date']}):")
        print(f"  {'Ticker':<10} {'Weight':>8}")
        print(f"  {'─'*10} {'─'*8}")
        for h in sorted(rb["holdings"], key=lambda x: -x["weight"])[:10]:
            print(f"  {h['ticker']:<10} {h['weight']:>7.1%}")
        if len(rb["holdings"]) > 10:
            print(f"  ... and {len(rb['holdings'])-10} more")

    # Save result
    with open("multi_factor_result.json", "w") as f:
        json.dump({
            "summary": {
                "total_return_pct": result.total_return_pct,
                "annual_return_pct": result.annual_return_pct,
                "max_drawdown_pct": result.max_drawdown_pct,
                "sharpe_ratio": result.sharpe_ratio,
                "hit_rate_pct": result.hit_rate_pct,
                "rebalance_count": result.rebalance_count,
                "avg_turnover_pct": result.avg_turnover_pct,
            },
            "ic_summary": result.ic_summary,
            "config": result.config,
            "rebalance_dates": [r["date"] for r in result.rebalance_log],
            "last_portfolio": result.rebalance_log[-1] if result.rebalance_log else None,
        }, f, indent=2, ensure_ascii=False, default=str)
    print(f"\n  Results saved to multi_factor_result.json")

    db.close()
    print("\nDone!")


if __name__ == "__main__":
    main()
