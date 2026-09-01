"""ETF watchlist pool for the dual-momentum rotation strategy.

The pool is the hard-constrained universe of the ETF rotation strategy:
5 宽基 + 8 行业 + 债/金/纳指 防守 + 货币ETF(空仓载体), 17 tickers total.
Defined in etf_pool.json next to this module (tracked source config — NOT
in backend/data/, which is gitignored output territory).

Unlike sector_pool (stock → multiple sectors), each ETF maps to exactly one
asset_class and one role ("risk" ranks for momentum, "cash" is the empty-
position vehicle and the absolute-momentum hurdle).

Pool hygiene (design doc §风险): annual review — drop anything with规模<10亿
or 日均成交<5000万; liquidity numbers to be verified once the data pipeline
is live.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path

_POOL_PATH = Path(__file__).resolve().parent / "etf_pool.json"

_lock = threading.Lock()


def _load_raw() -> dict:
    with _lock:
        return json.loads(_POOL_PATH.read_text(encoding="utf-8"))


def get_pool() -> list[dict]:
    """Full pool entries: [{ticker, name, asset_class, role}, ...]."""
    return _load_raw()["etfs"]


def get_risk_tickers() -> list[str]:
    """Tickers that compete for momentum ranking (everything but cash)."""
    return [e["ticker"] for e in _load_raw()["etfs"] if e["role"] == "risk"]


def get_cash_ticker() -> str:
    """The single cash-parking ETF (absolute-momentum hurdle + fallback)."""
    return _load_raw()["cash_ticker"]


def get_all_tickers() -> list[str]:
    """Deduplicated, sorted list of all pool tickers (incl. cash)."""
    return sorted(e["ticker"] for e in _load_raw()["etfs"])


def get_names() -> dict[str, str]:
    """ticker → display name."""
    return {e["ticker"]: e["name"] for e in _load_raw()["etfs"]}


def get_asset_classes() -> dict[str, str]:
    """ticker → asset_class label (rotation_membership parity for the
    backtester's per-group PnL breakdown)."""
    return {e["ticker"]: e["asset_class"] for e in _load_raw()["etfs"]}


def get_membership() -> dict[str, list[str]]:
    """ticker → [asset_class] — same shape as sector_pool.get_membership()
    so RotationBacktester's sector_of() grouping works unchanged."""
    return {e["ticker"]: [e["asset_class"]] for e in _load_raw()["etfs"]}
