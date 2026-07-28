"""Strategy implementations for the v1_default scorecard.

Category weights (sum to 1.0 across categories):
    trend     0.40  ← TrendMA (0.7) + BreakoutDonchian (0.3)
    momentum  0.25  ← MomentumMACD (0.5) + MomentumRSI (0.5)
    volume    0.20  ← VolumePrice (1.0)
    risk      0.15  ← RiskATR (gate, not blended)

Per-category weights sum to 1.0 within the category (e.g. trend's 0.40
splits 0.28 to MA + 0.12 to Donchian). See scoring.DEFAULT_CARD for the
canonical composition.
"""

from .base import Strategy, StrategyCategory
from .trend_ma import TrendMA
from .trend_breakout import TrendBreakout
from .breakout_donchian import BreakoutDonchian
from .momentum_macd import MomentumMACD
from .momentum_rsi import MomentumRSI
from .volume_price import VolumePrice
from .risk_atr import RiskATR

__all__ = [
    "Strategy", "StrategyCategory",
    "TrendMA", "TrendBreakout", "BreakoutDonchian",
    "MomentumMACD", "MomentumRSI",
    "VolumePrice", "RiskATR",
]
