"""Sector watchlist pool for the sector-rotation strategy.

The pool is the hard-constrained universe of the rotation strategy:
8 sectors (CPO / HBM / 先进封装 / 半导体设备 / CMP / 机器人执行器 /
测试设备 / 半导体材料), ~70 A-share tickers. Defined in
sector_pool.json next to this module (tracked source config — NOT in
backend/data/, which is gitignored output territory).

A stock MAY belong to multiple sectors (e.g. 华海清科 688120 is in both
半导体设备 and CMP); aggregation is per-sector so duplicates are expected
and harmless.

aliases are keyword synonyms kept for future news/announcement linkage —
nothing consumes them yet.
"""

from __future__ import annotations

import json
import threading
from functools import lru_cache
from pathlib import Path

_POOL_PATH = Path(__file__).resolve().parent / "sector_pool.json"

_lock = threading.Lock()


def _load_raw() -> dict:
    with _lock:
        return json.loads(_POOL_PATH.read_text(encoding="utf-8"))


def get_sectors() -> dict[str, dict]:
    """Full pool: {sector_name: {"aliases": [...], "stocks": [[ticker, name], ...]}}."""
    return _load_raw()


def get_membership() -> dict[str, list[str]]:
    """ticker → list of sector names it belongs to (multi-membership allowed)."""
    membership: dict[str, list[str]] = {}
    for sector, cfg in _load_raw().items():
        for ticker, _name in cfg["stocks"]:
            membership.setdefault(ticker, []).append(sector)
    return membership


def get_sector_members(sector: str) -> list[str]:
    """Tickers of one sector (empty list if unknown sector)."""
    cfg = _load_raw().get(sector)
    return [t for t, _n in cfg["stocks"]] if cfg else []


def get_all_tickers() -> list[str]:
    """Deduplicated, sorted list of all pool tickers."""
    return sorted(get_membership().keys())


def get_names() -> dict[str, str]:
    """ticker → display name (first occurrence wins across sectors)."""
    names: dict[str, str] = {}
    for cfg in _load_raw().values():
        for ticker, name in cfg["stocks"]:
            names.setdefault(ticker, name)
    return names
