"""Quant signal + backtest package.

Public API:
    indicators  — pure pandas TA primitives (no future-function leakage)
    scoring     — multi-factor ScoreCard composing per-strategy signals
    strategies  — individual Strategy implementations (trend/momentum/volume/risk)
    signal_service — full-market scan + persistence to chain_signals
    backtest    — A-share-aware backtester (T+1, limit-up/down, fees)

The shipped configuration is `v1_default`, surfaced via scoring.DEFAULT_CARD.
"""
from . import indicators  # noqa: F401
