"""Factor library for the cross-sectional multi-factor model.

Exports all trend-following factors used by the multi-factor engine.
"""

from .base import Factor, build_close_panel, build_panel_from_col
from .trend_factors import (
    PriceMomentum20,
    PriceMomentum60,
    TrendSlope,
    MultiMAAlignment,
    BreakoutStrength,
    VolumeMomentum,
    TrendConsistency,
)

__all__ = [
    "Factor",
    "build_close_panel",
    "build_panel_from_col",
    "PriceMomentum20",
    "PriceMomentum60",
    "TrendSlope",
    "MultiMAAlignment",
    "BreakoutStrength",
    "VolumeMomentum",
    "TrendConsistency",
]
