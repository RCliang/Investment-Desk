# 公司深度分析 Tab Admin Gate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rename the 「个股深度分析」 tab to 「公司深度分析」 and gate the entire deep-analysis pipeline behind the existing `ADMIN_REFRESH_TOKEN` shared secret, while keeping `/api/deep-analysis/latest` public so ChainKb tab 03 stays viewable by everyone.

**Architecture:** Reuse the existing `ADMIN_REFRESH_TOKEN` + `X-Admin-Token` header pattern from the refresh router. Extract `verify_admin_token` into a shared `app/auth.py` module so refresh + research + deep-analysis routers all import the same dependency. Frontend adds a React `AdminAuthContext` backed by localStorage (or sessionStorage if "记住我" unchecked), an axios request interceptor that injects the header on every call, and a response interceptor that clears the token on 401. Tab click when not admin opens a paper-aesthetic modal; once authenticated the tab unlocks and a 「退出管理员」 button appears on the page.

**Tech Stack:** FastAPI + Pydantic + SQLAlchemy (backend), React 18 + TypeScript 5 + Vite + Ant Design (frontend). No react-router; App.tsx uses `useState` view switching. No frontend unit test infra — validation is `npm run build` + browser smoke.

## Global Constraints

- **Shared token:** All admin endpoints read the same `ADMIN_REFRESH_TOKEN` env var (already in `backend/app/config.py:51`). Do NOT introduce new tokens.
- **Token header:** `X-Admin-Token` (literal). Compare with `secrets.compare_digest`, never `==`.
- **Empty config → 503, wrong/missing → 401.** This dual-status contract must remain consistent across all protected endpoints.
- **`/latest` stays public.** Do NOT add `Depends(verify_admin_token)` to `GET /api/deep-analysis/latest`.
- **Rename targets exactly 5 places** (see Task 2 + Task 7 + Task 8 + Task 9). Do NOT touch historical spec docs.
- **Paper aesthetic for the modal:** reuse CSS tokens (`--paper`, `--ink`, `--hi-yellow`, `--marker-red`, `--pencil`, `--ink-soft`) from `frontend/src/styles/tokens.css`. Do NOT use Ant Design `<Modal>` default chrome.
- **Tab icon:** Ant Design `LockOutlined` / `UnlockOutlined` from `@ant-design/icons`.
- **Commit message style:** conventional commits (`feat(...)`, `refactor(...)`, `test(...)`, `docs(...)`), `Co-Authored-By: Claude <noreply@anthropic.com>` trailer.
- **Frontend validation = `npm run build`** (which runs `tsc -b && vite build`). Backend validation = `pytest tests/` + manual curl.

---

## File Structure

### New files

| Path | Responsibility |
|---|---|
| `backend/app/auth.py` | Shared `verify_admin_token` FastAPI dependency (503 on unset, 401 on wrong/missing) |
| `backend/tests/test_admin_auth.py` | Unit tests for the dependency + endpoint protection matrix |
| `frontend/src/auth/AdminAuthContext.tsx` | React Context + Provider + `useAdminAuth()` hook; localStorage/sessionStorage backed |
| `frontend/src/auth/AdminLoginModal.tsx` | Paper-aesthetic modal component |
| `frontend/src/auth/admin.css` | Modal styles (scoped under `.alm-*` classes) |

### Modified files

| Path | What changes |
|---|---|
| `backend/app/routers/refresh.py` | Remove local `verify_admin_token`, import from `app.auth` (pure refactor) |
| `backend/app/routers/research.py` | Add `Depends(verify_admin_token)` to 3 endpoints (`/reports`, `/search`, `/download`) |
| `backend/app/routers/deep_analysis.py` | Add `Depends(verify_admin_token)` to 5 endpoints (NOT `/latest`); rename docstring |
| `backend/tests/conftest.py` | Add autouse fixture injecting valid `X-Admin-Token` + monkeypatch `ADMIN_REFRESH_TOKEN` so existing tests don't 401 |
| `frontend/src/services/api.ts` | Add axios request interceptor (inject header) + response interceptor (401 → clear + dispatch event) |
| `frontend/src/App.tsx` | Wrap with `AdminAuthProvider`; rename tab label; conditional `LockOutlined` / `UnlockOutlined` icon; click intercept → open modal |
| `frontend/src/pages/DeepAnalysisPage.tsx` | Rename H1 + docstring; add 「退出管理员」 button next to H1 (calls `onExit` prop) |
| `frontend/src/chainkb/components/LatestAnalysisSection.tsx` | Rename empty-state text 「前往「个股深度分析」页」 → 「前往「公司深度分析」页」 |

---

## Task 1: Extract `verify_admin_token` into `app/auth.py`

Pure refactor — no behavior change. Moves the function out of `refresh.py` into a shared module so the next task can import it from there.

**Files:**
- Create: `backend/app/auth.py`
- Modify: `backend/app/routers/refresh.py` (delete local function, change import)

**Interfaces:**
- Produces: `app.auth.verify_admin_token(x_admin_token: str = Header(default="")) -> None` — raises `HTTPException(503)` if `ADMIN_REFRESH_TOKEN` unset, `HTTPException(401)` if header missing or mismatched.

- [ ] **Step 1: Create `backend/app/auth.py`**

```python
"""Shared admin auth dependency.

Used by routers that protect privileged endpoints (refresh, research,
deep-analysis) with a single shared X-Admin-Token header compared
against ADMIN_REFRESH_TOKEN from config.
"""
from __future__ import annotations

import secrets

from fastapi import Header, HTTPException

from app.config import ADMIN_REFRESH_TOKEN


def verify_admin_token(x_admin_token: str = Header(default="")) -> None:
    """FastAPI dependency: enforce X-Admin-Token header.

    - 503 if ADMIN_REFRESH_TOKEN unset (defensive: prevents accidental
      open access when misconfigured).
    - 401 if header missing or mismatched.
    """
    if not ADMIN_REFRESH_TOKEN:
        raise HTTPException(
            status_code=503,
            detail="ADMIN_REFRESH_TOKEN not configured; admin endpoints disabled.",
        )
    if not x_admin_token or not secrets.compare_digest(x_admin_token, ADMIN_REFRESH_TOKEN):
        raise HTTPException(status_code=401, detail="invalid or missing X-Admin-Token")
```

- [ ] **Step 2: Refactor `backend/app/routers/refresh.py`**

Find this block (currently around lines 23, 63-75):

```python
from app.config import ADMIN_REFRESH_TOKEN    # line 23 — DELETE
# ... (other code) ...

def verify_admin_token(x_admin_token: str = Header(default="")) -> None:
    """FastAPI dependency: enforce X-Admin-Token header.

    Returns 401 on missing/wrong token, 503 if ADMIN_REFRESH_TOKEN is
    unset (empty string) in config.
    """
    if not ADMIN_REFRESH_TOKEN:
        raise HTTPException(
            status_code=503,
            detail="ADMIN_REFRESH_TOKEN not configured; refresh endpoints disabled.",
        )
    if not x_admin_token or not secrets.compare_digest(x_admin_token, ADMIN_REFRESH_TOKEN):
        raise HTTPException(status_code=401, detail="invalid or missing X-Admin-Token")
```

Replace by deleting the function body entirely AND adding the import. The top imports section should now contain:

```python
from app.auth import verify_admin_token
```

Remove now-unused imports if they become unused (`secrets`, `ADMIN_REFRESH_TOKEN`, `Header` if no longer referenced). Verify with a quick scan of remaining code in the file — `Header` is likely unused after this, `secrets` definitely is, `ADMIN_REFRESH_TOKEN` definitely is.

- [ ] **Step 3: Run existing tests to verify no regression**

Run:
```bash
cd backend
PYTHONPATH=. python -m pytest tests/test_deep_analysis.py tests/test_analyze_smoke.py tests/test_mineru_smoke.py tests/test_mineru_zip_extract.py tests/test_deep_analysis_storage.py
```

Expected: 32 passed, 2 skipped (same as before — refresh router's existing protection logic unchanged).

- [ ] **Step 4: Quick smoke that refresh endpoints still reject bad tokens**

Run:
```bash
cd backend
PYTHONPATH=. ADMIN_REFRESH_TOKEN=test123 python -c "
from fastapi.testclient import TestClient
from app.main import app
c = TestClient(app)
# missing header → 401
r = c.post('/api/chainkb/refresh/quotes')
print('no header:', r.status_code, r.json())
# wrong token → 401
r = c.post('/api/chainkb/refresh/quotes', headers={'X-Admin-Token': 'wrong'})
print('wrong:', r.status_code, r.json())
# correct → not 401 (likely 409 or 200 depending on running state)
r = c.post('/api/chainkb/refresh/quotes', headers={'X-Admin-Token': 'test123'})
print('correct:', r.status_code)
"
```

Expected: `no header: 401 ...`, `wrong: 401 ...`, `correct: <not 401>`.

- [ ] **Step 5: Commit**

```bash
cd E:/2026projects/Investment-Desk
git add backend/app/auth.py backend/app/routers/refresh.py
git commit -m "$(cat <<'EOF'
refactor(auth): extract verify_admin_token to shared app/auth.py

Pure refactor — no behavior change. Moves the dependency out of refresh.py
into a shared module so research and deep-analysis routers can import the
same admin gate in the next commit.

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Apply admin gate to 8 pipeline endpoints + rename docstring

Adds `Depends(verify_admin_token)` to 8 endpoints across `research.py` (3) and `deep_analysis.py` (5). Crucially does NOT add it to `/latest`. Also renames the docstring on `deep_analysis.py`.

**Files:**
- Modify: `backend/app/routers/research.py`
- Modify: `backend/app/routers/deep_analysis.py`

**Interfaces:**
- Consumes: `app.auth.verify_admin_token` (produced in Task 1)
- Produces: 8 endpoints now return 401/503 without valid token; `/latest` still public.

- [ ] **Step 1: Modify `backend/app/routers/research.py`**

Add the import near the existing `from app.config import ...` block (around line 17):

```python
from app.auth import verify_admin_token
```

Then add `dependencies=[Depends(verify_admin_token)]` to all 3 endpoint decorators. The result for each:

```python
@router.get("/reports", dependencies=[Depends(verify_admin_token)])
# ... existing handler ...

@router.get("/search", dependencies=[Depends(verify_admin_token)])
# ... existing handler ...

@router.post("/download", dependencies=[Depends(verify_admin_token)])
# ... existing handler ...
```

Keep all existing parameters, request bodies, and handler code untouched. Only the decorator line changes.

- [ ] **Step 2: Modify `backend/app/routers/deep_analysis.py`**

Two changes:

(a) Rename docstring at line 2 from `Deep analysis router — 个股深度分析 pipeline 的 HTTP 端点。` to `Deep analysis router — 公司深度分析 pipeline 的 HTTP 端点。`

(b) Add import after existing imports:

```python
from app.auth import verify_admin_token
```

(c) Add `dependencies=[Depends(verify_admin_token)]` to exactly these 5 decorators (NOT `/latest`):

```python
@router.post("/parse", dependencies=[Depends(verify_admin_token)])
@router.get("/parse-status", dependencies=[Depends(verify_admin_token)])
@router.get("/analyze", dependencies=[Depends(verify_admin_token)])
@router.get("/history", dependencies=[Depends(verify_admin_token)])
@router.get("/records/{analysis_id}", dependencies=[Depends(verify_admin_token)])

# CRITICAL: /latest stays public — ChainKb tab 03 uses it for all visitors
@router.get("/latest")
```

- [ ] **Step 3: Verify with curl that 8 endpoints reject unauth, /latest stays public**

Run:
```bash
cd backend
PYTHONPATH=. ADMIN_REFRESH_TOKEN=test123 python -c "
from fastapi.testclient import TestClient
from app.main import app
c = TestClient(app)

# These should ALL be 401 (or 405 for wrong method, that's fine too)
endpoints_get = [
    '/api/research/reports?code=688256',
    '/api/research/search?keyword=test',
    '/api/deep-analysis/parse-status?code=688256',
    '/api/deep-analysis/analyze?code=688256',
    '/api/deep-analysis/history?code=688256',
    '/api/deep-analysis/records/1',
]
print('=== GET without token (expect 401) ===')
for ep in endpoints_get:
    r = c.get(ep)
    print(f'  {r.status_code} {ep}')

print('=== POST without token (expect 401) ===')
for ep in ['/api/deep-analysis/parse', '/api/research/download']:
    r = c.post(ep, json={})
    print(f'  {r.status_code} {ep}')

print('=== /latest without token (expect NOT 401) ===')
r = c.get('/api/deep-analysis/latest?code=688256')
print(f'  {r.status_code} /api/deep-analysis/latest  (200 or 404 are OK, 401 is a BUG)')

print('=== GET with token (expect NOT 401) ===')
h = {'X-Admin-Token': 'test123'}
r = c.get('/api/research/reports?code=688256', headers=h)
print(f'  {r.status_code} /api/research/reports')
"
```

Expected:
- All 6 GET endpoints without token: **401**
- Both POST endpoints without token: **401**
- `/latest` without token: **200 or 404** (NOT 401)
- GET `/api/research/reports` with token: **200** (or non-401)

- [ ] **Step 4: Commit**

```bash
cd E:/2026projects/Investment-Desk
git add backend/app/routers/research.py backend/app/routers/deep_analysis.py
git commit -m "$(cat <<'EOF'
feat(auth): gate research + deep-analysis pipeline behind admin token

Adds Depends(verify_admin_token) to 8 endpoints:
- research: /reports, /search, /download
- deep-analysis: /parse, /parse-status, /analyze, /history, /records/{id}

GET /api/deep-analysis/latest stays public — ChainKb tab 03 uses it to
display AI analysis results to all visitors. Also renames the
deep_analysis.py docstring from 个股深度分析 to 公司深度分析.

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: Update `conftest.py` + add auth unit tests

Existing tests now hit 401 on protected endpoints. Add an autouse fixture that monkeypatches `ADMIN_REFRESH_TOKEN` and injects the header via dependency override. Then add focused tests for `verify_admin_token`.

**Files:**
- Modify: `backend/tests/conftest.py`
- Create: `backend/tests/test_admin_auth.py`

**Interfaces:**
- Produces: autouse fixture (no test needs to opt in) + 5 unit tests.

- [ ] **Step 1: Update `backend/tests/conftest.py`**

Add a new autouse fixture AND extend the existing `client` fixture so it always sends a valid `X-Admin-Token` header. Modify the file:

```python
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
```

Note: we monkeypatch BOTH `app.config.ADMIN_REFRESH_TOKEN` AND `app.auth.ADMIN_REFRESH_TOKEN` because `app/auth.py` imported the value via `from app.config import ADMIN_REFRESH_TOKEN` (binds the name at import time).

- [ ] **Step 2: Run existing tests to confirm autouse fixture restores green**

Run:
```bash
cd backend
PYTHONPATH=. python -m pytest tests/ -v --tb=short 2>&1 | tail -30
```

Expected: All previously-passing tests still pass (32+ passed, 2 skipped). If any test now 401's because it calls a protected endpoint without the fixture, the autouse fixture should fix it.

- [ ] **Step 3: Create `backend/tests/test_admin_auth.py`**

```python
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
```

- [ ] **Step 4: Run the new tests**

Run:
```bash
cd backend
PYTHONPATH=. python -m pytest tests/test_admin_auth.py -v
```

Expected: 5 passed.

- [ ] **Step 5: Run full test suite to confirm no regression**

Run:
```bash
cd backend
PYTHONPATH=. python -m pytest tests/ 2>&1 | tail -5
```

Expected: All tests pass (32 prior + 5 new = 37+ passed).

- [ ] **Step 6: Commit**

```bash
cd E:/2026projects/Investment-Desk
git add backend/tests/conftest.py backend/tests/test_admin_auth.py
git commit -m "$(cat <<'EOF'
test(auth): add verify_admin_token unit tests + autouse fixture

Adds 5 tests covering 401/503 paths and an endpoint-protection matrix
that asserts exactly 8 endpoints are gated and /latest stays public.
Autouse fixture in conftest patches ADMIN_REFRESH_TOKEN so existing
tests don't 401 on the newly-protected endpoints.

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: Frontend — create `AdminAuthContext`

React Context + Provider + `useAdminAuth()` hook. Reads/writes `localStorage` (or `sessionStorage`). Listens for cross-tab `storage` events + custom `admin:unauthorized` event dispatched by the axios interceptor (Task 6).

No UI yet — this task only delivers the context module and verifies it compiles.

**Files:**
- Create: `frontend/src/auth/AdminAuthContext.tsx`

**Interfaces:**
- Produces: `AdminAuthProvider` component, `useAdminAuth()` hook returning `{ token: string | null, isAdmin: boolean, login(token: string, remember: boolean): void, logout(): void }`.

- [ ] **Step 1: Create `frontend/src/auth/AdminAuthContext.tsx`**

```tsx
import { createContext, useContext, useEffect, useState, type ReactNode } from 'react';

const STORAGE_KEY = 'adminToken';

interface AdminAuthContextValue {
  token: string | null;
  isAdmin: boolean;
  login: (token: string, remember: boolean) => void;
  logout: () => void;
}

const AdminAuthContext = createContext<AdminAuthContextValue>({
  token: null,
  isAdmin: false,
  login: () => {},
  logout: () => {},
});

function readToken(): string | null {
  if (typeof window === 'undefined') return null;
  return localStorage.getItem(STORAGE_KEY) ?? sessionStorage.getItem(STORAGE_KEY);
}

function clearTokenEverywhere() {
  localStorage.removeItem(STORAGE_KEY);
  sessionStorage.removeItem(STORAGE_KEY);
}

export function AdminAuthProvider({ children }: { children: ReactNode }) {
  const [token, setToken] = useState<string | null>(() => readToken());

  // Cross-tab sync: another tab changed the token.
  useEffect(() => {
    const handler = (e: StorageEvent) => {
      if (e.key === STORAGE_KEY) setToken(readToken());
    };
    window.addEventListener('storage', handler);
    return () => window.removeEventListener('storage', handler);
  }, []);

  // Axios response interceptor (Task 6) dispatches this on 401.
  useEffect(() => {
    const handler = () => {
      clearTokenEverywhere();
      setToken(null);
    };
    window.addEventListener('admin:unauthorized', handler);
    return () => window.removeEventListener('admin:unauthorized', handler);
  }, []);

  const login = (tok: string, remember: boolean) => {
    clearTokenEverywhere(); // defensive: never leave stale tokens in the other storage
    const storage = remember ? localStorage : sessionStorage;
    storage.setItem(STORAGE_KEY, tok);
    setToken(tok);
  };

  const logout = () => {
    clearTokenEverywhere();
    setToken(null);
  };

  return (
    <AdminAuthContext.Provider value={{ token, isAdmin: !!token, login, logout }}>
      {children}
    </AdminAuthContext.Provider>
  );
}

// eslint-disable-next-line react-refresh/only-export-components
export function useAdminAuth(): AdminAuthContextValue {
  return useContext(AdminAuthContext);
}
```

- [ ] **Step 2: Verify it compiles**

Run:
```bash
cd frontend
npm run build 2>&1 | tail -10
```

Expected: Build succeeds. Note: `AdminAuthContext` is not yet imported anywhere, but it should still compile as an unused module. If Vite tree-shakes it without error, that's fine.

- [ ] **Step 3: Commit**

```bash
cd E:/2026projects/Investment-Desk
git add frontend/src/auth/AdminAuthContext.tsx
git commit -m "$(cat <<'EOF'
feat(frontend): add AdminAuthContext for admin token state

React Context backed by localStorage (persistent) or sessionStorage
(per-browser-session), chosen by the remember flag at login time.
Listens for cross-tab storage events and the custom admin:unauthorized
event dispatched by the axios 401 interceptor (added in next task).

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: Frontend — `admin.css` + `AdminLoginModal`

Paper-aesthetic modal component. Uses the project's CSS tokens. Self-contained — takes `open`, `onClose`, `errorMsg` props.

**Files:**
- Create: `frontend/src/auth/admin.css`
- Create: `frontend/src/auth/AdminLoginModal.tsx`

**Interfaces:**
- Consumes: `useAdminAuth().login(token, remember)` from Task 4.
- Produces: `<AdminLoginModal open={bool} onClose={fn} errorMsg={string} />` component.

- [ ] **Step 1: Create `frontend/src/auth/admin.css`**

```css
/* Admin login modal — paper aesthetic, scoped under .alm-* classes.
   Reuses tokens from styles/tokens.css: --paper, --ink, --hi-yellow,
   --marker-red, --pencil, --ink-soft. */
.alm-overlay {
  position: fixed;
  inset: 0;
  background: rgba(26, 43, 74, 0.45);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
  font-family: 'Patrick Hand', 'Caveat', cursive;
  animation: alm-fade 0.15s ease-out;
}
@keyframes alm-fade {
  from { opacity: 0; }
  to   { opacity: 1; }
}

.alm-card {
  background: var(--paper);
  border: 2.5px solid var(--ink);
  border-radius: 6px;
  padding: 22px 26px 20px;
  width: 360px;
  max-width: calc(100vw - 32px);
  box-shadow: 4px 6px 0 rgba(26, 43, 74, 0.18);
  transform: rotate(-0.3deg);
  position: relative;
}

.alm-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 4px;
}
.alm-icon {
  font-size: 18px;
  color: var(--ink);
}
.alm-title {
  font-family: 'Caveat', cursive;
  font-weight: 700;
  font-size: 26px;
  color: var(--ink);
  line-height: 1;
}

.alm-subtitle {
  font-size: 13px;
  color: var(--ink-soft);
  margin: 6px 0 14px;
  line-height: 1.4;
}

.alm-input {
  width: 100%;
  background: var(--paper);
  border: 2px solid var(--ink);
  border-radius: 4px;
  padding: 8px 12px;
  font-family: 'Patrick Hand', cursive;
  font-size: 15px;
  color: var(--ink);
  outline: none;
  transition: border-color 0.15s ease;
  box-sizing: border-box;
}
.alm-input:focus {
  border-color: var(--marker-red);
}

.alm-error {
  color: var(--marker-red);
  font-size: 13px;
  margin-top: 8px;
  font-family: 'Patrick Hand', cursive;
}

.alm-remember {
  display: flex;
  align-items: center;
  gap: 6px;
  margin: 14px 0 18px;
  font-size: 13px;
  color: var(--ink-soft);
  cursor: pointer;
  user-select: none;
}
.alm-remember input {
  accent-color: var(--ink);
  cursor: pointer;
}

.alm-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}

.alm-btn {
  background: var(--hi-yellow);
  color: var(--ink);
  border: 2px solid var(--ink);
  padding: 6px 16px;
  border-radius: 4px;
  font-family: 'Patrick Hand', cursive;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  box-shadow: 2px 2px 0 rgba(26, 43, 74, 0.12);
  transition: transform 0.1s ease, box-shadow 0.1s ease;
}
.alm-btn:hover:not(:disabled) {
  transform: translate(-1px, -1px);
  box-shadow: 3px 3px 0 rgba(26, 43, 74, 0.16);
}
.alm-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
  box-shadow: none;
}

.alm-btn-ghost {
  background: transparent;
  color: var(--ink-soft);
  border: 2px dashed var(--pencil);
  box-shadow: none;
}
.alm-btn-ghost:hover:not(:disabled) {
  background: rgba(26, 43, 74, 0.04);
  color: var(--ink);
  transform: none;
  box-shadow: none;
}
```

- [ ] **Step 2: Create `frontend/src/auth/AdminLoginModal.tsx`**

```tsx
import { useState, type FormEvent } from 'react';
import { LockOutlined } from '@ant-design/icons';
import { useAdminAuth } from './AdminAuthContext';
import './admin.css';

interface Props {
  open: boolean;
  onClose: () => void;
  errorMsg?: string;
}

/**
 * Admin login modal — paper aesthetic.
 * Calls login(token, remember) on submit; the parent decides when to show it.
 */
export default function AdminLoginModal({ open, onClose, errorMsg }: Props) {
  const { login } = useAdminAuth();
  const [token, setToken] = useState('');
  const [remember, setRemember] = useState(true);

  if (!open) return null;

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    const trimmed = token.trim();
    if (!trimmed) return;
    login(trimmed, remember);
    setToken('');
    setRemember(true);
    onClose();
  };

  return (
    <div className="alm-overlay" onClick={onClose}>
      <form className="alm-card" onClick={(e) => e.stopPropagation()} onSubmit={handleSubmit}>
        <div className="alm-header">
          <LockOutlined className="alm-icon" />
          <span className="alm-title">管理员验证</span>
        </div>
        <p className="alm-subtitle">
          「公司深度分析」需要管理员权限。请输入 admin token 继续。
        </p>
        <input
          className="alm-input"
          type="password"
          placeholder="X-Admin-Token"
          value={token}
          onChange={(e) => setToken(e.target.value)}
          autoFocus
        />
        {errorMsg && <div className="alm-error">{errorMsg}</div>}
        <label className="alm-remember">
          <input
            type="checkbox"
            checked={remember}
            onChange={(e) => setRemember(e.target.checked)}
          />
          <span>记住我(永久保留在此浏览器)</span>
        </label>
        <div className="alm-actions">
          <button type="button" className="alm-btn alm-btn-ghost" onClick={onClose}>
            取消
          </button>
          <button type="submit" className="alm-btn" disabled={!token.trim()}>
            进入
          </button>
        </div>
      </form>
    </div>
  );
}
```

- [ ] **Step 3: Verify build**

Run:
```bash
cd frontend
npm run build 2>&1 | tail -10
```

Expected: Build succeeds. (Modal not yet used by App — that's Task 7.)

- [ ] **Step 4: Commit**

```bash
cd E:/2026projects/Investment-Desk
git add frontend/src/auth/admin.css frontend/src/auth/AdminLoginModal.tsx
git commit -m "$(cat <<'EOF'
feat(frontend): add paper-style AdminLoginModal component

Self-contained modal with paper aesthetic (Caveat + Patrick Hand fonts,
hand-drawn border, slight rotation). Takes open/onClose/errorMsg props.
Includes 记住我 checkbox that toggles localStorage vs sessionStorage.

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: Frontend — axios interceptors

Inject `X-Admin-Token` on every request, clear token + dispatch event on 401.

**Files:**
- Modify: `frontend/src/services/api.ts`

**Interfaces:**
- Consumes: `adminToken` key in localStorage/sessionStorage.
- Produces: globally-injected auth header; `admin:unauthorized` window event on 401 (consumed by `AdminAuthContext` from Task 4).

- [ ] **Step 1: Read current top of `frontend/src/services/api.ts`**

Run:
```bash
head -20 frontend/src/services/api.ts
```

Confirm the existing first lines look like:
```typescript
import axios from 'axios';

const api = axios.create({
  baseURL: '/api',
  ...
});
```

- [ ] **Step 2: Add interceptors after `axios.create()`**

Insert this block immediately after the `const api = axios.create({...});` declaration (before any exported function):

```typescript
// ── Admin auth interceptors ────────────────────────────────────────
// Request: attach X-Admin-Token if a token is stored.
api.interceptors.request.use((config) => {
  const stored =
    localStorage.getItem('adminToken') ?? sessionStorage.getItem('adminToken');
  if (stored) {
    config.headers['X-Admin-Token'] = stored;
  }
  return config;
});

// Response: on 401, clear any stored token and notify the auth context.
// AdminAuthContext listens for this event and resets its state + the
// app reopens the login modal.
api.interceptors.response.use(
  (resp) => resp,
  (error) => {
    const status = error?.response?.status;
    if (status === 401) {
      localStorage.removeItem('adminToken');
      sessionStorage.removeItem('adminToken');
      window.dispatchEvent(new Event('admin:unauthorized'));
    }
    return Promise.reject(error);
  },
);
```

- [ ] **Step 3: Verify build**

Run:
```bash
cd frontend
npm run build 2>&1 | tail -10
```

Expected: Build succeeds.

- [ ] **Step 4: Commit**

```bash
cd E:/2026projects/Investment-Desk
git add frontend/src/services/api.ts
git commit -m "$(cat <<'EOF'
feat(frontend): add axios admin-token interceptors

Request interceptor injects X-Admin-Token header from localStorage (or
sessionStorage) on every call. Response interceptor clears the token
and dispatches an admin:unauthorized event on 401, which AdminAuthContext
listens for to reset state and reopen the login modal.

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: Frontend — wire `App.tsx` (Provider + tab rename + icon + modal)

The integration task. Wraps app in `AdminAuthProvider`, renames tab label, adds LockOutlined/UnlockOutlined icons, intercepts click to open modal if not admin.

**Files:**
- Modify: `frontend/src/App.tsx`

**Interfaces:**
- Consumes: `AdminAuthProvider`, `useAdminAuth`, `AdminLoginModal` from Tasks 4-5.

- [ ] **Step 1: Rewrite `frontend/src/App.tsx`**

Replace the entire file content with:

```tsx
import { useState } from 'react';
import { LockOutlined, UnlockOutlined } from '@ant-design/icons';
import ChainPage from './pages/ChainPage';
import DeepAnalysisPage from './pages/DeepAnalysisPage';
import { AdminAuthProvider, useAdminAuth } from './auth/AdminAuthContext';
import AdminLoginModal from './auth/AdminLoginModal';
import './nav.css';

type View = 'chain' | 'deep';

interface NavItem {
  key: View;
  label: string;
  locked: boolean; // true = requires admin
}

const NAV_ITEMS: NavItem[] = [
  { key: 'chain', label: '产业链知识库', locked: false },
  { key: 'deep', label: '公司深度分析', locked: true },
];

function AppInner() {
  const { isAdmin } = useAdminAuth();
  const [view, setView] = useState<View>('chain');
  const [loginModalOpen, setLoginModalOpen] = useState(false);
  const [loginError, setLoginError] = useState('');

  const handleNavClick = (item: NavItem) => {
    if (item.locked && !isAdmin) {
      setLoginError(''); // fresh open, no stale error
      setLoginModalOpen(true);
      return;
    }
    setView(item.key);
  };

  // AdminAuthContext clears the token on 401; we watch isAdmin going
  // false while the user is on the 'deep' view, and bounce them back
  // to 'chain' + reopen the modal with an error.
  // Implemented as an effect on isAdmin.
  // (Doing this in AppInner keeps view/modal state local.)
  // Use a separate effect via useEffect:
  // (Import useEffect at the top — see step 2 if you forgot.)

  return (
    <div className="app-root">
      <nav className="app-nav">
        <span className="app-nav-brand">InvestLens</span>
        <div className="app-nav-items">
          {NAV_ITEMS.map((item) => {
            const locked = item.locked && !isAdmin;
            const unlocked = item.locked && isAdmin;
            return (
              <button
                key={item.key}
                className={`app-nav-item ${view === item.key ? 'active' : ''}`}
                onClick={() => handleNavClick(item)}
              >
                {locked && <LockOutlined style={{ marginRight: 6 }} />}
                {unlocked && <UnlockOutlined style={{ marginRight: 6 }} />}
                {item.label}
              </button>
            );
          })}
        </div>
      </nav>
      <main className="app-main">
        {view === 'chain' && <ChainPage />}
        {view === 'deep' && isAdmin && <DeepAnalysisPage onExit={() => setView('chain')} />}
        {view === 'deep' && !isAdmin && (
          <div style={{ padding: 32, color: 'var(--ink-soft)' }}>
            此页面需要管理员权限。
          </div>
        )}
      </main>
      <AdminLoginModal
        open={loginModalOpen}
        onClose={() => setLoginModalOpen(false)}
        errorMsg={loginError}
      />
    </div>
  );
}

export default function App() {
  return (
    <AdminAuthProvider>
      <AppInner />
    </AdminAuthProvider>
  );
}
```

- [ ] **Step 2: Add the `useEffect` import and the bounce-on-401 effect**

Modify the file:

(a) Top import line:
```typescript
import { useEffect, useState } from 'react';
```

(b) Inside `AppInner`, after the state declarations and before the `return`, add:

```typescript
  // Watch for unexpected 401 (axios interceptor cleared the token while
  // the user is sitting on the protected page). Reopen modal + show error.
  useEffect(() => {
    if (!isAdmin && view === 'deep') {
      setLoginError('管理员 token 已失效,请重新输入。');
      setLoginModalOpen(true);
    }
  }, [isAdmin, view]);
```

- [ ] **Step 3: Verify build**

Run:
```bash
cd frontend
npm run build 2>&1 | tail -10
```

Expected: Build succeeds.

- [ ] **Step 4: Commit**

```bash
cd E:/2026projects/Investment-Desk
git add frontend/src/App.tsx
git commit -m "$(cat <<'EOF'
feat(frontend): rename tab to 公司深度分析 + gate behind admin modal

Wraps App in AdminAuthProvider. Tab label renamed from 个股深度分析 to
公司深度分析 with conditional LockOutlined (when locked) / UnlockOutlined
(when authenticated) icons. Clicking the locked tab opens AdminLoginModal
instead of switching view. If a 401 fires while sitting on the page
(token cleared by axios interceptor), the modal reopens with an error.

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
)"
```

---

## Task 8: Frontend — `DeepAnalysisPage` rename + logout button

Renames H1 + docstring, adds 「退出管理员」 button next to H1. The button calls `logout()` from context + invokes the `onExit` prop passed from App to switch view back to chain.

**Files:**
- Modify: `frontend/src/pages/DeepAnalysisPage.tsx`

**Interfaces:**
- Consumes: `useAdminAuth().logout()` from Task 4, `onExit: () => void` prop from App (Task 7).

- [ ] **Step 1: Read the relevant parts of `DeepAnalysisPage.tsx`**

Run:
```bash
sed -n '1,30p' frontend/src/pages/DeepAnalysisPage.tsx
sed -n '75,100p' frontend/src/pages/DeepAnalysisPage.tsx
```

Note: line numbers may shift slightly — the goal is to find (a) the file docstring + Props interface, (b) the `<h1>` in the render.

- [ ] **Step 2: Add imports and `onExit` prop**

At the top imports, add:

```typescript
import { LogoutOutlined } from '@ant-design/icons';
import { useAdminAuth } from '../auth/AdminAuthContext';
```

Modify the Props interface to accept `onExit`:

```typescript
interface Props {
  // ... existing props ...
  onExit: () => void;
}
```

If the existing Props interface is unnamed or implicit, give it a name and apply it. The function signature should look like:

```typescript
export default function DeepAnalysisPage({
  /* existing destructure */,
  onExit,
}: Props) {
  const { logout } = useAdminAuth();
  // ...
}
```

- [ ] **Step 3: Rename docstring + H1, add logout button**

Find the file-level docstring (line ~24): `个股深度分析页面 — 4 步向导。` → `公司深度分析页面 — 4 步向导。`

Find the H1 (line ~84): `<h1>个股深度分析</h1>` → wrap it in a `.row-between` with the logout button. The result should look like:

```tsx
<div className="row-between">
  <h1>公司深度分析</h1>
  <button
    className="btn btn-ghost"
    onClick={() => {
      logout();
      onExit();
    }}
    style={{ fontSize: 13 }}
  >
    <LogoutOutlined /> 退出管理员
  </button>
</div>
```

(The surrounding `<div className="da-header">` may already be a row-between; if so, place the button inside that existing wrapper instead of creating a new one. Inspect the current structure and choose the smaller diff.)

- [ ] **Step 4: Verify build**

Run:
```bash
cd frontend
npm run build 2>&1 | tail -10
```

Expected: Build succeeds. TypeScript should catch any prop misuse.

- [ ] **Step 5: Commit**

```bash
cd E:/2026projects/Investment-Desk
git add frontend/src/pages/DeepAnalysisPage.tsx
git commit -m "$(cat <<'EOF'
feat(frontend): rename H1 to 公司深度分析 + add 退出管理员 button

Updates docstring + visible H1 from 个股深度分析 to 公司深度分析.
Adds a 「退出管理员」 button next to the H1 that calls logout() and
the onExit prop from App to switch back to the chain view.

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
)"
```

---

## Task 9: Frontend — `LatestAnalysisSection` rename + final smoke

Last rename in `LatestAnalysisSection.tsx` (ChainKb tab 03 empty-state text). Then full build + manual browser smoke test covering the whole flow.

**Files:**
- Modify: `frontend/src/chainkb/components/LatestAnalysisSection.tsx`

- [ ] **Step 1: Rename empty-state text**

Find line ~51 in `frontend/src/chainkb/components/LatestAnalysisSection.tsx`:

```tsx
前往「个股深度分析」页 → 选择企业类型 → 上传研报 → 一键生成
```

Change to:

```tsx
前往「公司深度分析」页 → 选择企业类型 → 上传研报 → 一键生成
```

- [ ] **Step 2: Final build verification**

Run:
```bash
cd frontend
npm run build 2>&1 | tail -15
```

Expected: Build succeeds, all 5 rename sites are now consistent.

- [ ] **Step 3: Final backend test run**

Run:
```bash
cd backend
PYTHONPATH=. python -m pytest tests/ 2>&1 | tail -5
```

Expected: All tests pass (no regression).

- [ ] **Step 4: Manual browser smoke test**

Start backend and frontend:
```bash
# Terminal 1
cd backend
ADMIN_REFRESH_TOKEN=test123 uvicorn app.main:app --reload --port 8000

# Terminal 2
cd frontend
npm run dev
```

Open http://localhost:5173 and walk through:

| Scenario | Expected |
|---|---|
| Look at nav | Tab reads 「🔒 公司深度分析」 with lock icon |
| Click tab | Modal pops up in paper aesthetic (slight rotation, hand-drawn border) |
| Click 取消 | Modal closes, stays on ChainKb view |
| Click tab again, enter wrong token, click 进入 | Modal closes briefly, view tries to switch but axios 401 → modal reopens with red 「管理员 token 已失效」 error |
| Click tab, enter `test123`, check 记住我, click 进入 | Modal closes, tab icon switches to 🔓, DeepAnalysisPage renders |
| Reload page | Still authenticated (localStorage), tab shows 🔓 |
| Click 「退出管理员」 button next to H1 | View switches back to chain, tab icon switches back to 🔒 |
| Open DevTools → Application → Local Storage | `adminToken` key is gone |
| Click tab, enter `test123`, uncheck 记住我, click 进入 | Works; reload page → logged out (sessionStorage cleared on tab close) |
| Switch to ChainKb → search 688256 → tab 03 | 「AI 公司拆解」 section renders normally (latest endpoint is public) |

If anything fails, debug + fix before committing.

- [ ] **Step 5: Commit**

```bash
cd E:/2026projects/Investment-Desk
git add frontend/src/chainkb/components/LatestAnalysisSection.tsx
git commit -m "$(cat <<'EOF'
feat(frontend): rename LatestAnalysisSection empty-state hint to 公司深度分析

Last of 5 rename sites for the tab relabel. With this, all user-visible
references to 个股深度分析 are gone (historical spec docs intentionally
untouched).

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
)"
```

---

## Self-Review

**Spec coverage** — all 5 rename sites and 8 protected endpoints covered:
- Rename App.tsx tab → Task 7 ✓
- Rename DeepAnalysisPage H1 + docstring → Task 8 ✓
- Rename LatestAnalysisSection empty-state → Task 9 ✓
- Rename deep_analysis.py docstring → Task 2 ✓
- Backend `app/auth.py` → Task 1 ✓
- Refresh refactor → Task 1 ✓
- 8 endpoints protected → Task 2 ✓
- `/latest` left public → Task 2 verification + Task 3 matrix test ✓
- conftest fixture → Task 3 ✓
- AdminAuthContext → Task 4 ✓
- AdminLoginModal + paper CSS → Task 5 ✓
- 「记住我」 checkbox → Task 5 ✓
- axios interceptors → Task 6 ✓
- Tab lock icon → Task 7 ✓
- Tab click modal → Task 7 ✓
- Logout button → Task 8 ✓
- Cross-tab sync → Task 4 ✓
- 401 → modal reopen with error → Task 6 + Task 7 useEffect ✓
- Backend tests pass → Task 3, Task 9 ✓
- Browser smoke → Task 9 ✓

**Placeholder scan** — no TBD / TODO / vague "handle edge cases" / "add appropriate validation". All code blocks are complete.

**Type consistency** —
- `verify_admin_token(x_admin_token: str = Header(default=""))` — same signature in `app/auth.py` (Task 1), the probe app in `test_admin_auth.py` (Task 3), and the route decorators (Task 2).
- `useAdminAuth()` returns `{ token, isAdmin, login, logout }` — used consistently in Tasks 5, 7, 8.
- `AdminLoginModal` props `{ open, onClose, errorMsg }` — produced in Task 5, consumed in Task 7 with matching types.
- `onExit: () => void` — added to Props in Task 8, passed in Task 7's `<DeepAnalysisPage onExit={...} />`.
- Storage key `'adminToken'` — same literal in Tasks 4, 6.

All consistent.
