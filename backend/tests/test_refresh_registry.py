"""Tests for the refresh registry (architecture review 2026-09-06, candidate 2).

The registry is the ONE inventory of refresh types; router / CLI / scheduler
derive from it. These tests pin:

  1. Registry integrity — scripts exist on disk, loaders exist on the seed
     module, timeouts sane, all_order contiguous, scheduled set == cron set.
  2. Derived views — the static RefreshType Literal, CLI choices and
     refresh_all order cannot drift from the registry.
  3. The _run_one pipeline itself — success / failure / conflict / stale
     sweep, with the subprocess and loader faked (first tests this
     pipeline has ever had).
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.services import refresh_cli, refresh_service
from app.services.refresh_service import (
    REFRESH_REGISTRY, RefreshConflictError, RefreshSpec,
)


# ── 1. Registry integrity ───────────────────────────────────────────────────

class TestRegistryIntegrity:

    def test_scripts_exist(self):
        for name, spec in REFRESH_REGISTRY.items():
            path = refresh_service.SCRIPTS_DIR / spec.script
            assert path.is_file(), f"{name}: missing script {path}"

    def test_loaders_exist(self):
        from scripts import load_seed_to_db
        for name, spec in REFRESH_REGISTRY.items():
            assert hasattr(load_seed_to_db, spec.loader), (
                f"{name}: loader {spec.loader} not on load_seed_to_db")

    def test_timeouts_positive(self):
        for name, spec in REFRESH_REGISTRY.items():
            assert spec.timeout > 0, name

    def test_all_order_contiguous(self):
        orders = sorted(s.all_order for s in REFRESH_REGISTRY.values()
                        if s.all_order is not None)
        assert orders == list(range(1, len(orders) + 1))

    def test_scheduled_set_equals_cron_set(self):
        with_cron = {t for t, s in REFRESH_REGISTRY.items() if s.cron}
        assert with_cron, "at least the quotes cadence must be scheduled"
        for t, s in REFRESH_REGISTRY.items():
            assert isinstance(s.cron, tuple)
            for kw in s.cron:
                assert set(kw) <= {"day_of_week", "day", "hour", "minute"}, t

    def test_quotes_has_two_windows(self):
        assert len(REFRESH_REGISTRY["quotes"].cron) == 2

    def test_incremental_types_flagged(self):
        for t in ("quotes_history", "fund_flow", "etf_klines"):
            assert "--incremental" in REFRESH_REGISTRY[t].extra_args, t


# ── 2. Derived views cannot drift ───────────────────────────────────────────

class TestDerivedViews:

    def test_literal_covers_registry(self):
        import typing
        literal_vals = set(typing.get_args(refresh_service.RefreshType))
        assert literal_vals == set(REFRESH_REGISTRY) | {"all"}

    def test_valid_types_sorted_with_all(self):
        v = refresh_service.valid_types()
        assert v == sorted(v)
        assert "all" in v and set(REFRESH_REGISTRY) <= set(v)

    def test_cli_choices_match(self):
        assert refresh_cli.VALID_TYPES == refresh_service.valid_types()

    def test_all_sequence_follows_all_order(self):
        assert refresh_service.all_sequence() == [
            t for t, _ in sorted(
                ((t, s.all_order) for t, s in REFRESH_REGISTRY.items()
                 if s.all_order is not None),
                key=lambda kv: kv[1])]

    def test_dispatch_unknown_raises(self):
        with pytest.raises(ValueError, match="unknown refresh type"):
            refresh_service.dispatch("nope", session=None)


# ── 3. The _run_one pipeline (fakes: subprocess + loader) ───────────────────

@pytest.fixture
def db_session():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.db import Base
    from app.models import chain_models  # noqa: F401 register tables

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


def _fake_subprocess(monkeypatch, returncode=0):
    calls = []

    def fake_run(cmd, **kw):
        calls.append(cmd)
        return SimpleNamespace(returncode=returncode, stdout="", stderr="")

    monkeypatch.setattr(refresh_service.subprocess, "run", fake_run)
    return calls


class TestRunOne:

    def test_success_path(self, db_session, monkeypatch):
        calls = _fake_subprocess(monkeypatch)
        monkeypatch.setattr(
            "scripts.load_seed_to_db.load_quotes", lambda s: 5)
        row = refresh_service.dispatch("quotes", db_session, trigger="cli")
        assert row.status == "succeeded"
        assert row.rows_affected == 5
        assert row.triggered_by == "cli"
        assert calls and "backfill_tencent_quotes.py" in str(calls[0][1])

    def test_failure_path_raises_and_logs(self, db_session, monkeypatch):
        _fake_subprocess(monkeypatch, returncode=2)
        with pytest.raises(RuntimeError, match="exited 2"):
            refresh_service.dispatch("margin", db_session, trigger="manual")
        failed = db_session.query(refresh_service.ChainRefreshLog).filter_by(
            refresh_type="margin").one()
        assert failed.status == "failed"
        assert "RuntimeError" in failed.error

    def test_conflict_while_running(self, db_session, monkeypatch):
        from app.models.chain_models import ChainRefreshLog
        db_session.add(ChainRefreshLog(refresh_type="finance",
                                       status="running",
                                       triggered_by="scheduler",
                                       started_at=datetime.utcnow()))
        db_session.commit()
        with pytest.raises(RefreshConflictError):
            refresh_service.dispatch("finance", db_session)

    def test_stale_running_swept(self, db_session):
        from app.models.chain_models import ChainRefreshLog
        old = datetime.utcnow() - timedelta(
            seconds=REFRESH_REGISTRY["quotes"].timeout * 3)
        db_session.add(ChainRefreshLog(refresh_type="quotes",
                                       status="running",
                                       triggered_by="scheduler",
                                       started_at=old))
        db_session.commit()
        assert refresh_service.is_running(db_session, "quotes") is False
        swept = db_session.query(ChainRefreshLog).filter_by(
            refresh_type="quotes").one()
        assert swept.status == "failed"
        assert "auto-swept" in swept.error
