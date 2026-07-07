"""Shared fixtures for deep-analysis tests."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base, get_db
from app.main import app

# Test token — must match TEST_ADMIN_TOKEN used by monkeypatch below.
TEST_ADMIN_TOKEN = "test-admin-token-abc123"


@pytest.fixture(autouse=True)
def patch_admin_token(monkeypatch):
    """Autouse: ensure ADMIN_REFRESH_TOKEN is set to a known value during tests.

    Without this, any test that hits a protected endpoint would 401.
    """
    import app.auth as auth_module
    import app.config as config_module
    monkeypatch.setattr(config_module, "ADMIN_REFRESH_TOKEN", TEST_ADMIN_TOKEN)
    monkeypatch.setattr(auth_module, "ADMIN_REFRESH_TOKEN", TEST_ADMIN_TOKEN)


@pytest.fixture(scope="function")
def test_db():
    """每测试独立 in-memory SQLite。"""
    engine = create_engine(
        "sqlite:///:memory:",
        echo=False,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = Session()
    yield db
    db.close()
    engine.dispose()


@pytest.fixture(scope="function")
def client(test_db):
    """TestClient with injected DB + default X-Admin-Token header."""
    def override_get_db():
        try:
            yield test_db
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        c.headers.update({"X-Admin-Token": TEST_ADMIN_TOKEN})
        yield c
    app.dependency_overrides.clear()
