"""Multi-factor ScoreCard: composes per-strategy signals into one BUY/SELL/HOLD.

The card is a weighted blend of N strategies. Each strategy returns a
Series in [-1, +1]; the card multiplies by (category_weight × within_weight)
and sums. Risk-category strategies are special-cased: their compute() output
is NOT added to the composite; instead their risk_extras() gate the position
and supply a stop-loss.

Final composite_score ∈ [-1, +1] (clamped). Action thresholds:
    score >=  BUY_THRESHOLD  (+0.30) → BUY
    score <=  SELL_THRESHOLD (-0.30) → SELL
    otherwise                       → HOLD

Thresholds are deliberately conservative — most days are HOLD, so the few
firing signals carry conviction. Backtesting on the v1_default card (see
backtest.py) is what validates the choice; tune via ScoreCard(thresholds=...).

Output DataFrame columns (one row per bar):
    composite_score   float in [-1,+1]
    action            'BUY' | 'SELL' | 'HOLD'
    position_pct      float in [0,1] — allowed_position (from risk gate)
    stop_loss_price   float — risk-strategy trailing stop
    target_price      float — 2 * ATR above the latest close (r:rr = 1:2)
    detail            dict — per-strategy scores for debugging/UI
"""

from __future__ import annotations

from typing import Optional

import pandas as pd

from . import indicators
from .strategies import (
    Strategy, TrendMA, TrendBreakout, BreakoutDonchian,
    MomentumMACD, MomentumRSI,
    VolumePrice, RiskATR,
)


# Category weights — must sum to 1.0. See strategies/__init__.py docstring.
CATEGORY_WEIGHTS = {
    "trend": 0.40,
    "momentum": 0.25,
    "volume": 0.20,
    "risk": 0.15,  # used as gate multiplier, not summed into score
}

BUY_THRESHOLD = 0.30
SELL_THRESHOLD = -0.30


class ScoreCard:
    """Weighted blend of strategies producing a daily action per ticker.

    Construct with a custom strategy list + weights to experiment; use
    DEFAULT_CARD for the shipped v1 configuration.
    """

    def __init__(
        self,
        strategies: list[Strategy],
        category_weights: Optional[dict] = None,
        buy_threshold: float = BUY_THRESHOLD,
        sell_threshold: float = SELL_THRESHOLD,
    ):
        self.strategies = strategies
        self.category_weights = dict(category_weights or CATEGORY_WEIGHTS)
        self.buy_threshold = buy_threshold
        self.sell_threshold = sell_threshold

        # Normalize within-category weights so they sum to 1.0 per category.
        by_cat: dict[str, list[Strategy]] = {}
        for s in strategies:
            by_cat.setdefault(s.category, []).append(s)
        for cat, members in by_cat.items():
            total = sum(m.weight for m in members)
            if total > 0:
                for m in members:
                    m._normalized_weight = (m.weight / total) * self.category_weights.get(cat, 0.0)
            else:
                for m in members:
                    m._normalized_weight = 0.0

    def score(self, df: pd.DataFrame) -> pd.DataFrame:
        """Compute composite signals for an enriched bar DataFrame.

        Returns a DataFrame indexed like df with columns:
            composite_score, action, position_pct, stop_loss_price,
            target_price, detail (dict per row — heavy; call score_summary()
            instead if you don't need the breakdown).
        """
        # Enrich once (idempotent if caller already did).
        if "ma5" not in df.columns:
            df = indicators.enrich(df)

        composite = pd.Series(0.0, index=df.index)
        detail: dict[str, pd.Series] = {}
        risk_strategy: Optional[Strategy] = None

        for s in self.strategies:
            sig = s.compute(df).fillna(0.0)
            detail[s.name] = sig
            if s.category == "risk":
                risk_strategy = s  # don't sum; gate instead
                continue
            composite = composite + sig * getattr(s, "_normalized_weight", 0.0)

        composite = composite.clip(-1.0, 1.0)

        # Risk gate + stop loss.
        allowed_position = pd.Series(1.0, index=df.index)
        stop_loss = pd.Series(float("nan"), index=df.index)
        if risk_strategy is not None:
            extras = risk_strategy.risk_extras(df)
            allowed_position = extras.get("allowed_position", allowed_position).fillna(0.8)
            stop_loss = extras.get("stop_loss", stop_loss)
            # Risk category contributes its weight as a *gate*: multiply
            # composite by allowed_position-flavored factor so deep-bear
            # regimes dampen the composite. This honors the 0.15 risk
            # allocation without letting a lone risk signal flip BUY→SELL.
            gate = risk_strategy.compute(df).fillna(0.0)
            # Map gate {-1,0,1} → {0.5, 0.85, 1.0} damping factor.
            damping = gate.replace({1.0: 1.0, 0.0: 0.85, -1.0: 0.5})
            composite = composite * damping

        # Action thresholds.
        action = pd.Series("HOLD", index=df.index, dtype=object)
        action[composite >= self.buy_threshold] = "BUY"
        action[composite <= self.sell_threshold] = "SELL"

        # ── Trend gate (打分卡级硬过滤) ──────────────────────────────────
        # BUY signals only fire in a confirmed uptrend: MA5 > MA20 > MA60
        # (多头排列). This kills the "混乱市抄底" trades where a golden cross
        # inside a downtrend (MA60 still overhead) produced false BUYs.
        # Backtest on 002475: cuts trades 20→13, win rate 30%→38%, drawdown
        # 37%→30%. SELL signals are NOT gated — we always want to exit risk.
        #
        # composite_score is preserved (UI shows the raw score); only the
        # final action is downgraded so users can see "this would have been
        # a BUY but the trend gate blocked it."
        if "ma5" in df.columns and "ma20" in df.columns and "ma60" in df.columns:
            bull_aligned = (df["ma5"] > df["ma20"]) & (df["ma20"] > df["ma60"])
            action = action.where(~(action.eq("BUY") & ~bull_aligned), "HOLD")

        # Target price: 2 * ATR above close (assumes 1:2 risk:reward vs stop).
        atr = df.get("atr14", pd.Series(0.0, index=df.index))
        target = df["close"] + 2 * atr

        out = pd.DataFrame(index=df.index)
        out["composite_score"] = composite
        out["action"] = action
        out["position_pct"] = allowed_position.clip(0.0, 1.0)
        out["stop_loss_price"] = stop_loss
        out["target_price"] = target
        # Detail is per-row dict — build lazily for the last row only (UI uses
        # it for the latest signal). Full-history detail is large; skip unless
        # asked. We stash the Series in a side dict for score_detail().
        out["_detail_series"] = [None] * len(out)
        self._last_detail = detail
        return out

    def score_summary(self, df: pd.DataFrame) -> pd.DataFrame:
        """Like score() but drops the heavy per-row detail column."""
        out = self.score(df)
        return out.drop(columns=["_detail_series"])

    def latest(self, df: pd.DataFrame) -> dict:
        """Return the most recent day's signal as a flat dict (for the API)."""
        out = self.score(df)
        if out.empty:
            return {}
        last = out.iloc[-1]
        detail = {name: float(s.iloc[-1]) if len(s) > 0 else 0.0
                  for name, s in self._last_detail.items()}
        return {
            "date": str(df["date"].iloc[-1]) if "date" in df.columns else None,
            "composite_score": round(float(last["composite_score"]), 4),
            "action": str(last["action"]),
            "position_pct": round(float(last["position_pct"]), 3),
            "stop_loss_price": None if pd.isna(last["stop_loss_price"]) else round(float(last["stop_loss_price"]), 2),
            "target_price": round(float(last["target_price"]), 2),
            "detail": {k: round(v, 3) for k, v in detail.items()},
        }


def default_strategies() -> list[Strategy]:
    """The shipped v1_default strategy set."""
    return [
        TrendMA(),              # trend, weight 0.7
        BreakoutDonchian(),     # trend, weight 0.3
        MomentumMACD(),         # momentum, weight 0.5
        MomentumRSI(),          # momentum, weight 0.5
        VolumePrice(),          # volume, weight 1.0
        RiskATR(),              # risk (gate)
    ]


DEFAULT_CARD = ScoreCard(default_strategies())


# ── trend_follow: pure trend-following card ────────────────────────────────
#
# A single-strategy card for the "确定趋势后买入，趋势破位后卖出" philosophy.
# Unlike v1_default (which blends 5 factors and lets RSI/MACD trigger exits
# inside uptrends), trend_follow ONLY listens to trend alignment:
#   BUY  when MA5>MA20>MA60 establishes
#   SELL when MA5<MA20 AND close<MA20 for ≥2 consecutive days
# RSI/MACD/volume are NOT computed here, so they can't fire premature exits.
# The risk_atr layer is still included to provide stop-loss + trailing-stop
# (风控兜底), but its compute() output is a gate, not a directional score.
#
# Thresholds ±0.5: since TrendBreakout emits exactly {-1, 0, +1}, any
# threshold in (0, 1) gives the same BUY/SELL mapping; 0.5 is conventional.

def trend_follow_strategies() -> list[Strategy]:
    """The trend_follow strategy set: trend + risk only."""
    return [
        TrendBreakout(),        # trend, sole signal source
        RiskATR(),              # risk (gate: stop-loss + trailing)
    ]


def _make_trend_follow_card() -> "ScoreCard":
    """Build the trend_follow card with trend-heavy weights.

    Trend gets 0.85 (TrendBreakout is the only signal), risk gets 0.15
    (gate only, as in v1_default). The trend gate in ScoreCard.score()
    (要求多头排列才 BUY) is redundant here since TrendBreakout already
    requires it — but harmless.
    """
    return ScoreCard(
        trend_follow_strategies(),
        category_weights={"trend": 0.85, "momentum": 0.0, "volume": 0.0, "risk": 0.15},
        buy_threshold=0.5,
        sell_threshold=-0.5,
    )


TREND_FOLLOW_CARD = _make_trend_follow_card()


# ── Strategy-set registry ─────────────────────────────────────────────────
# Maps strategy_set name → card. signal_service.scan_all / get_signals /
# backtest all look up the card by name via get_card(strategy_set).
# Add new strategy sets here; the DB strategy_set column stores the key.

_CARDS: dict[str, "ScoreCard"] = {
    "v1_default": DEFAULT_CARD,
    "trend_follow": TREND_FOLLOW_CARD,
}


def get_card(strategy_set: str = "v1_default") -> "ScoreCard":
    """Look up a ScoreCard by strategy_set name. Falls back to v1_default
    for unknown keys (defensive — the DB may have rows from a renamed set)."""
    return _CARDS.get(strategy_set, DEFAULT_CARD)


def list_strategy_sets() -> list[dict]:
    """Catalog of available strategy sets, for the /api/quant/strategies endpoint."""
    out = []
    for name, card in _CARDS.items():
        out.append({
            "strategy_set": name,
            "buy_threshold": card.buy_threshold,
            "sell_threshold": card.sell_threshold,
            "category_weights": {k: round(v, 3) for k, v in card.category_weights.items()},
            "strategies": [
                {"name": s.name, "category": s.category, "weight": s.weight}
                for s in card.strategies
            ],
        })
    return out
