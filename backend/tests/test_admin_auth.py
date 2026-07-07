"""Unit tests for shared verify_admin_token dependency + endpoint protection matrix."""
import pytest
from fastapi import Depends, FastAPI, Header
from fastapi.testclient import TestClient

from app.auth import verify_admin_token


def _build_probe_app() -> FastAPI:
    """Tiny app with 2 routes: one protected, one public. Lets us test the
    dependency in isolation without booting the real routers' external calls.
    """
    app = FastAPI()

    @app.get("/protected")
    def protected(_: None = Depends(verify_admin_token)):
        return {"ok": True}

    @app.get("/public")
    def public():
        return {"ok": True}

    return app


def test_verify_admin_token_missing_header_returns_401(monkeypatch):
    import app.auth as m
    monkeypatch.setattr(m, "ADMIN_REFRESH_TOKEN", "secret")
    client = TestClient(_build_probe_app())
    r = client.get("/protected")
    assert r.status_code == 401
    assert "invalid or missing X-Admin-Token" in r.json()["detail"]


def test_verify_admin_token_wrong_token_returns_401(monkeypatch):
    import app.auth as m
    monkeypatch.setattr(m, "ADMIN_REFRESH_TOKEN", "secret")
    client = TestClient(_build_probe_app())
    r = client.get("/protected", headers={"X-Admin-Token": "wrong"})
    assert r.status_code == 401


def test_verify_admin_token_correct_token_passes(monkeypatch):
    import app.auth as m
    monkeypatch.setattr(m, "ADMIN_REFRESH_TOKEN", "secret")
    client = TestClient(_build_probe_app())
    r = client.get("/protected", headers={"X-Admin-Token": "secret"})
    assert r.status_code == 200
    assert r.json() == {"ok": True}


def test_verify_admin_token_unset_config_returns_503(monkeypatch):
    import app.auth as m
    monkeypatch.setattr(m, "ADMIN_REFRESH_TOKEN", "")
    client = TestClient(_build_probe_app())
    # Even if a token is sent, 503 wins because the server isn't configured.
    r = client.get("/protected", headers={"X-Admin-Token": "anything"})
    assert r.status_code == 503
    assert "not configured" in r.json()["detail"]


def test_protected_endpoint_matrix():
    """Walk the real app's routes and assert exactly 8 endpoints are protected
    (i.e. depend on verify_admin_token), and /latest is NOT.
    """
    from app.main import app
    from app.auth import verify_admin_token

    def _uses_auth_dep(route) -> bool:
        dependants = getattr(route, "dependant", None)
        if dependants is None:
            return False
        for d in dependants.dependencies:
            if d.call is verify_admin_token:
                return True
        return False

    protected = []
    unprotected = []
    for route in app.routes:
        path = getattr(route, "path", "")
        if not path.startswith(("/api/research", "/api/deep-analysis")):
            continue
        if _uses_auth_dep(route):
            protected.append(path)
        else:
            unprotected.append(path)

    # Expected protected (dedup path templates):
    expected_protected = {
        "/api/research/reports",
        "/api/research/search",
        "/api/research/download",
        "/api/deep-analysis/parse",
        "/api/deep-analysis/parse-status",
        "/api/deep-analysis/analyze",
        "/api/deep-analysis/history",
        "/api/deep-analysis/records/{analysis_id}",
    }
    assert set(protected) == expected_protected, (
        f"protected mismatch.\n  got: {sorted(protected)}\n"
        f"  expected: {sorted(expected_protected)}"
    )
    assert "/api/deep-analysis/latest" in unprotected, \
        f"/latest MUST stay public, got protected list: {unprotected}"
