"""Technical indicators for the quant signal/backtest pipeline.

All functions are pure pandas (no future-function leakage): each output row
at index t depends only on input rows [0..t]. pandas `rolling`/`ewm`/`shift`
guarantee this — they never look forward. Strategies build on top of these
primitives, so correctness here propagates to signals and backtests.

Conventions:
  - Input: a DataFrame with columns ['open','high','low','close','volume',
    'amount','date'] sorted ascending by date (loader guarantees this).
  - Output: a Series aligned to the input index. NaN where undefined
    (e.g. RSI needs 14 bars before producing a value).
  - All math in float; callers handle NaN via fillna(0) at the boundary.

References: standard TA formulas (Wilders 1978 for RSI/MACD/ATR).
"""

from __future__ import annotations

import numpy as np
import pandas as pd


# ── Moving averages ────────────────────────────────────────────────────────

def sma(close: pd.Series, n: int) -> pd.Series:
    """Simple moving average. NaN for the first n-1 rows."""
    return close.rolling(window=n, min_periods=n).mean()


def ema(close: pd.Series, n: int) -> pd.Series:
    """Exponential moving average (pandas default span=n, adjust=False).

    adjust=False uses the recursive form y_t = (1-α)·y_{t-1} + α·x_t,
    matching the standard trading-platform EMA definition. The first valid
    value seeds from x_0 (no warm-up bias correction).
    """
    return close.ewm(span=n, adjust=False).mean()


# ── MACD ───────────────────────────────────────────────────────────────────

def macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9):
    """MACD indicator (Gerald Appel).

    Returns (dif, dea, hist):
      - dif  = EMA(fast) - EMA(slow)         # the MACD line
      - dea  = EMA(dif, signal)              # the signal line
      - hist = (dif - dea) * 2               # bar histogram (A-share convention: ×2)

    Golden cross: dif crosses above dea.
    Death cross:  dif crosses below dea.
    Zero-axis filter: dif > 0 suggests bullish momentum.
    """
    ema_fast = ema(close, fast)
    ema_slow = ema(close, slow)
    dif = ema_fast - ema_slow
    dea = dif.ewm(span=signal, adjust=False).mean()
    hist = (dif - dea) * 2
    return dif, dea, hist


# ── RSI (Wilder) ────────────────────────────────────────────────────────────

def rsi(close: pd.Series, n: int = 14) -> pd.Series:
    """Relative Strength Index, Wilder's smoothing (the standard RSI).

    RSI > 70 → overbought; RSI < 30 → oversold.
    Uses Wilder's smoothing (alpha = 1/n) which differs from a plain EMA
    (alpha = 2/(n+1)); this matches what A-share platforms display.
    """
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = (-delta).clip(lower=0.0)
    # Wilder smoothing = EMA with alpha=1/n, i.e. com=1/alpha-1 = n-1.
    avg_gain = gain.ewm(alpha=1.0 / n, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1.0 / n, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0.0, np.nan)
    rsi_val = 100.0 - (100.0 / (1.0 + rs))
    # When avg_loss == 0 (all gains), RSI = 100. Replace NaN-from-division.
    return rsi_val.fillna(100.0)


# ── Bollinger Bands ────────────────────────────────────────────────────────

def boll(close: pd.Series, n: int = 20, k: float = 2.0):
    """Bollinger Bands.

    Returns (upper, mid, lower):
      - mid   = SMA(close, n)
      - upper = mid + k · std
      - lower = mid - k · std
    std uses ddof=0 (population) to match most trading platforms.
    """
    mid = sma(close, n)
    std = close.rolling(window=n, min_periods=n).std(ddof=0)
    upper = mid + k * std
    lower = mid - k * std
    return upper, mid, lower


# ── ATR (Average True Range, Wilder) ───────────────────────────────────────

def atr(high: pd.Series, low: pd.Series, close: pd.Series, n: int = 14) -> pd.Series:
    """Average True Range, Wilder smoothing. Used for volatility-scaled stops.

    TR_t = max(high_t - low_t, |high_t - close_{t-1}|, |low_t - close_{t-1}|)
    ATR = Wilder-smoothed TR over n periods.
    """
    prev_close = close.shift(1)
    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    # Wilder smoothing on TR.
    return tr.ewm(alpha=1.0 / n, adjust=False).mean()


# ── Turnover (换手率) percentile ────────────────────────────────────────────

def turnover_percentile(turnover: pd.Series, n: int = 60) -> pd.Series:
    """Historical percentile rank of today's turnover within the trailing n days.

    Returns a Series in [0, 1]: 0.9 means today's turnover exceeds 90% of
    the prior 60 days → "heavy volume". Used by the volume-price strategy
    to detect 放量 without depending on the (IP-throttled) East Money fund
    flow API — mootdx-derived turnover is fully backtestable.

    Implementation: rolling rank, normalized by window size. pandas
    `rolling.rank(pct=True)` does exactly this and is forward-safe.
    """
    return turnover.rolling(window=n, min_periods=n // 2).rank(pct=True)


# ── Donchian channel (breakout) ────────────────────────────────────────────

def donchian(high: pd.Series, low: pd.Series, entry_n: int = 20, exit_n: int = 10):
    """Donchian channel breakout levels (turtle-trading basis).

    Returns (entry_high, exit_low):
      - entry_high = rolling max of prior entry_n highs (NOT including today,
        to avoid trivial same-day breakout) → buy signal when close > this.
      - exit_low   = rolling min of prior exit_n lows → sell signal when close < this.

    The `.shift(1)` excludes the current bar so a "new 20-day high" only
    fires when today's close genuinely exceeds the *previous* 20-day max.
    """
    entry_high = high.rolling(window=entry_n).max().shift(1)
    exit_low = low.rolling(window=exit_n).min().shift(1)
    return entry_high, exit_low


# ── Convenience: attach all indicators to a bar DataFrame ──────────────────

def enrich(df: pd.DataFrame) -> pd.DataFrame:
    """Add common indicator columns to a bar DataFrame in place-ish (returns copy).

    Input columns required: open, high, low, close, volume, amount, turnover_pct.
    Adds: ma5, ma20, ma60, ema12, ema26, macd_dif, macd_dea, macd_hist,
          rsi14, boll_up, boll_mid, boll_low, atr14, turnover_pct60.

    `turnover_pct` may be missing (Tencent enrichment is optional); in that
    case we derive a proxy turnover = volume / rolling-max(volume, 60) so
    the volume-price strategy still works for backtest-only bars.
    """
    out = df.copy()
    close = out["close"]
    high = out["high"]
    low = out["low"]

    out["ma5"] = sma(close, 5)
    out["ma20"] = sma(close, 20)
    out["ma60"] = sma(close, 60)
    out["ema12"] = ema(close, 12)
    out["ema26"] = ema(close, 26)

    dif, dea, hist = macd(close)
    out["macd_dif"] = dif
    out["macd_dea"] = dea
    out["macd_hist"] = hist

    out["rsi14"] = rsi(close, 14)

    up, mid, lo = boll(close)
    out["boll_up"] = up
    out["boll_mid"] = mid
    out["boll_low"] = lo

    out["atr14"] = atr(high, low, close, 14)

    # Turnover: prefer the Tencent-provided turnover_pct; else proxy from
    # volume relative to its 60-day max. The proxy keeps volume-price signals
    # working even for mootdx-only bars (where we don't yet have shares-out
    # to compute a true turnover ratio).
    if "turnover_pct" in out.columns and out["turnover_pct"].notna().any():
        out["turnover_pct60"] = turnover_percentile(out["turnover_pct"], 60)
    else:
        vol_proxy = out["volume"] / out["volume"].rolling(60, min_periods=20).max()
        out["turnover_pct60"] = turnover_percentile(vol_proxy.fillna(0.0), 60)

    return out
