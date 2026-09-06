"""Tests for the response-cache seam (architecture review 2026-09-06,
candidate 3): one module behind three routers, TTLs from config,
opportunistic purge.

Layers:
  1. cache module unit tests — round-trip, namespace isolation, expiry,
     purge, throttle, non-JSON-native serialization.
  2. Router integration — /api/data/query hits the upstream exactly once
     for a repeated request; the stored key/rows go through the module.
"""

from __future__ import annotations

import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

import pytest

BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.config import CACHE_TTL_FINANCIAL, CACHE_TTL_MARKET
from app.models.models import DataCache
from app.services import cache


@pytest.fixture
def db_session():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.db import Base
    from app.models import models  # noqa: F401 register tables

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


class TestCacheModule:

    def test_roundtrip_and_namespace_isolation(self, db_session):
        cache.cache_set(db_session, "data", "k1", {"a": 1}, 60)
        cache.cache_set(db_session, "research", "k1", {"b": 2}, 60)
        assert cache.cache_get(db_session, "data", "k1") == {"a": 1}
        assert cache.cache_get(db_session, "research", "k1") == {"b": 2}
        assert cache.cache_get(db_session, "other", "k1") is None

    def test_key_format_matches_historical_research_rows(self, db_session):
        cache.cache_set(db_session, "research", "code:600519:pages2", {}, 60)
        row = db_session.query(DataCache).one()
        assert row.cache_key == "research:code:600519:pages2"

    def test_expired_returns_none(self, db_session):
        cache.cache_set(db_session, "data", "k", {"x": 1}, -1)  # already past
        assert cache.cache_get(db_session, "data", "k") is None

    def test_overwrite_keeps_single_row(self, db_session):
        cache.cache_set(db_session, "data", "k", {"v": 1}, 60)
        cache.cache_set(db_session, "data", "k", {"v": 2}, 60)
        rows = db_session.query(DataCache).all()
        assert len(rows) == 1
        assert cache.cache_get(db_session, "data", "k") == {"v": 2}

    def test_datetime_serialized_via_default_str(self, db_session):
        payload = {"ts": datetime(2026, 9, 6, 12, 0, 0)}
        cache.cache_set(db_session, "data", "k", payload, 60)
        out = cache.cache_get(db_session, "data", "k")
        assert out["ts"] == "2026-09-06 12:00:00"

    def test_purge_removes_only_expired(self, db_session):
        now = datetime.now()
        db_session.add_all([
            DataCache(cache_key="a", result_json="{}",
                      expires_at=now - timedelta(seconds=1)),
            DataCache(cache_key="b", result_json="{}",
                      expires_at=now + timedelta(seconds=60)),
        ])
        db_session.commit()
        assert cache.purge_expired(db_session) == 1
        remaining = {r.cache_key for r in db_session.query(DataCache).all()}
        assert remaining == {"b"}

    def test_write_triggers_throttled_purge(self, db_session, monkeypatch):
        # force the purge window open
        monkeypatch.setattr(cache, "_last_purge", 0.0)
        monkeypatch.setattr(time, "monotonic",
                            lambda: 10_000.0)  # far past _last_purge
        stale = DataCache(cache_key="old", result_json="{}",
                          expires_at=datetime.now() - timedelta(days=30))
        db_session.add(stale)
        db_session.commit()
        cache.cache_set(db_session, "data", "k", {"v": 1}, 60)
        assert db_session.query(DataCache).filter_by(
            cache_key="old").count() == 0
        # within the window: a second write must NOT purge (throttle)
        db_session.add(DataCache(cache_key="old2", result_json="{}",
                                 expires_at=datetime.now() - timedelta(days=30)))
        db_session.commit()
        cache.cache_set(db_session, "data", "k2", {"v": 1}, 60)
        assert db_session.query(DataCache).filter_by(
            cache_key="old2").count() == 1


class TestDataQueryEndpoint:

    def test_second_request_hits_cache(self, client, test_db, monkeypatch):
        # data.py imports the SERVICE OBJECT, not the module — patch the
        # object the router actually dispatches through.
        from app.routers import data as data_router
        calls = []

        def fake_handler(**params):
            calls.append(params)
            return {"price": 42.0}

        monkeypatch.setattr(data_router.akshare_service,
                            "get_test_cache", fake_handler, raising=False)
        body = {"source": "akshare", "action": "get_test_cache",
                "params": {"ticker": "600519"}}
        r1 = client.post("/api/data/query", json=body)
        r2 = client.post("/api/data/query", json=body)
        assert r1.status_code == r2.status_code == 200
        assert r1.json() == r2.json() == {"price": 42.0}
        assert len(calls) == 1, "second request must be served from cache"

        row = test_db.query(DataCache).one()
        assert row.cache_key.startswith("data:")
        delta = (row.expires_at - datetime.now()).total_seconds()
        # action name without hist/realtime → the FINANCIAL (1d) policy
        assert CACHE_TTL_FINANCIAL - 5 <= delta <= CACHE_TTL_FINANCIAL

    def test_hist_action_gets_market_ttl(self, client, test_db, monkeypatch):
        from app.routers import data as data_router
        monkeypatch.setattr(data_router.akshare_service, "get_test_hist",
                            lambda **kw: {"bars": []}, raising=False)
        body = {"source": "akshare", "action": "get_test_hist",
                "params": {"ticker": "600519"}}
        r = client.post("/api/data/query", json=body)
        assert r.status_code == 200
        row = test_db.query(DataCache).one()
        delta = (row.expires_at - datetime.now()).total_seconds()
        assert delta <= CACHE_TTL_MARKET
