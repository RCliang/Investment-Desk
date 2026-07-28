"""Pure trend-following strategy: buy on confirmed uptrend, sell on
confirmed breakdown. No RSI/MACD/volume exits — those noise sources are
what caused the v1_default card to fire SELL inside healthy uptrends.

Signal logic:
  BUY (+1):   first day a full bull alignment establishes
              (MA5 > MA20 > MA60). Persists while alignment holds, but
              the backtester's "only buy when flat" rule means persistent
              +1 just means "stay long" — it won't add to the position.
  SELL (-1):  MA5 < MA20 AND close has been below MA20 for ≥2 consecutive
              days. The 2-day confirmation filters single-day wash-outs
              (a common market-maker shakeout pattern in AI-chain stocks
              where intraday drops pierce MA20 then close back above).
  HOLD (0):   everything else.

This deliberately conflicts with mean-reversion (RSI) and short-term
momentum (MACD) — a trend-following purist system. Pair it via the
TrendFollowCard (single-strategy card) rather than blending into v1_default.

Exit hierarchy in the backtester:
  1. hard stop / trailing stop (risk layer, always on)
  2. this strategy's SELL (trend breakdown)
  3. end-of-backtest force-close
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .base import Strategy


class TrendBreakout(Strategy):
    name = "trend_breakout"
    category = "trend"
    weight = 1.0

    def compute(self, df: pd.DataFrame) -> pd.Series:
        ma5 = df["ma5"]
        ma20 = df["ma20"]
        ma60 = df["ma60"]
        close = df["close"]

        # Full bull alignment: the BUY condition.
        bull = (ma5 > ma20) & (ma20 > ma60)

        # Breakdown condition: MA5 < MA20 AND close below MA20.
        # Use the raw (unconfirmed) flag first, then require 2-day persistence.
        raw_break = (ma5 < ma20) & (close < ma20)
        # Persist via a rolling 2-day AND: confirmed only if both today and
        # yesterday satisfy raw_break. .rolling(2).sum()==2 means both True.
        confirmed_break = raw_break.rolling(window=2, min_periods=2).sum() == 2

        score = pd.Series(0.0, index=df.index)
        score[bull] = 1.0
        # SELL takes precedence over BUY if somehow both flags are true
        # (shouldn't happen since bull requires ma5>ma20 and break requires
        # ma5<ma20, but defensive).
        score[confirmed_break.fillna(False)] = -1.0

        return score.fillna(0.0)
