"""DB-backed response cache — the ONE implementation (architecture review
2026-09-06, candidate 3).

Before this module the same "cache a remote call" behaviour existed as two
verbatim `_cache_get/_cache_set` copies (routers/data.py + routers/research.py),
one entity-doubles-as-cache variant (chain.py), and a set of hand-rolled key
formats — while three of the four CACHE_TTL_* constants in config.py were
dead and data.py hard-coded its TTLs behind a string sniff on the action
name. Now:

  cache_get(db, ns, key)            → cached payload or None
  cache_set(db, ns, key, data, ttl) → overwrite-style write
  purge_expired(db)                 → delete rows past expires_at

Conventions:
  - Full cache_key = "{ns}:{key}". "research:*" keys keep their historical
    format, so rows written before this module still hit.
  - TTLs come from config (CACHE_TTL_MARKET / FINANCIAL / CHAIN / RESEARCH)
    — callers should not hard-code seconds.
  - cache_set opportunistically purges expired rows, at most once per hour
    per process (the table used to grow monotonically — only same-key
    overwrites ever deleted anything).
"""

from __future__ import annotations

import json
import logging
import threading
import time
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.models.models import DataCache

log = logging.getLogger(__name__)

_PURGE_INTERVAL_S = 3600          # opportunistic purge cadence per process
_last_purge = 0.0                 # time.monotonic() of the last purge
_purge_lock = threading.Lock()    # router threads + scheduler share this


def _full_key(ns: str, key: str) -> str:
    return f"{ns}:{key}"


def cache_get(db: Session, ns: str, key: str):
    """Return the cached payload for (ns, key), or None when absent/expired."""
    cached = db.query(DataCache).filter(
        DataCache.cache_key == _full_key(ns, key)).first()
    if cached and cached.expires_at > datetime.now():
        return json.loads(cached.result_json)
    return None


def cache_set(db: Session, ns: str, key: str, data, ttl_seconds: int) -> None:
    """Overwrite-style write (same key → single row, as before)."""
    fk = _full_key(ns, key)
    db.query(DataCache).filter(DataCache.cache_key == fk).delete()
    db.add(DataCache(
        cache_key=fk,
        result_json=json.dumps(data, ensure_ascii=False, default=str),
        expires_at=datetime.now() + timedelta(seconds=ttl_seconds),
    ))
    db.commit()
    _maybe_purge(db)


def purge_expired(db: Session) -> int:
    """Delete every row past its expires_at. Returns rows removed."""
    removed = db.query(DataCache).filter(
        DataCache.expires_at < datetime.now()).delete()
    db.commit()
    return removed


def _maybe_purge(db: Session) -> None:
    """Purge at most once per interval — cheap enough to hang off writes."""
    global _last_purge
    if time.monotonic() - _last_purge < _PURGE_INTERVAL_S:
        return
    with _purge_lock:
        if time.monotonic() - _last_purge < _PURGE_INTERVAL_S:
            return
        try:
            purged = purge_expired(db)
        except Exception:
            log.exception("opportunistic cache purge failed")
            return
        if purged:
            log.info("purged %d expired data_cache rows", purged)
        _last_purge = time.monotonic()
