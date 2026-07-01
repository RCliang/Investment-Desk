"""
Deep analysis pipeline integration tests.

覆盖：
- /parse-status 状态查询
- /analyze 缓存命中路径（不调 LLM）
- /analyze force_refresh 路径（mock LLM stream）
- /history 列表格式
- /records/{id} 单条拉取
- 参数校验

LLM/MinerU/OSS 全部走 mock 或被缓存绕开，无外部依赖。
"""

import json
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base, get_db
from app.main import app
from app.models.models import ReportContent, DeepAnalysis


# ── 测试用 in-memory SQLite ────────────────────────────────────────

@pytest.fixture(scope="function")
def test_db():
    """
    每个测试用独立的内存 SQLite。
    StaticPool + check_same_thread=False 让同一连接被多线程共享
    （TestClient 的 async 请求会在独立线程执行）。
    """
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
    """TestClient 注入测试 DB"""
    def override_get_db():
        try:
            yield test_db
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


# ─────────────────────────────────────────────────────────────────────
# /parse-status
# ─────────────────────────────────────────────────────────────────────

def test_parse_status_empty(client):
    """无任何 pending 任务时应返回 0/0/0"""
    r = client.get("/api/deep-analysis/parse-status", params={"code": "301095"})
    assert r.status_code == 200
    data = r.json()
    assert data["code"] == "301095"
    assert data["total"] == 0
    assert data["done"] == 0
    assert data["pending"] == 0


def test_parse_status_with_db_records(client, test_db):
    """DB 中已有解析记录时应在 status 中体现"""
    rc = ReportContent(
        oss_key="reports/301095/test.pdf",
        stock_code="301095",
        title="测试研报",
        markdown_text="# test",
        token_count=10,
        parsed_at=datetime.now(),
    )
    test_db.add(rc)
    test_db.commit()

    r = client.get("/api/deep-analysis/parse-status", params={"code": "301095"})
    data = r.json()
    assert data["done"] == 1
    assert data["total"] == 1
    assert len(data["details"]) == 1
    assert data["details"][0]["oss_key"] == "reports/301095/test.pdf"
    assert data["details"][0]["status"] == "done"
    assert data["details"][0]["token_count"] == 10


# ─────────────────────────────────────────────────────────────────────
# /analyze — cache hit path (no LLM call)
# ─────────────────────────────────────────────────────────────────────

def test_analyze_cache_hit(client, test_db):
    """预填 deep_analyses → /analyze 直接返回 cached 事件"""
    oss_keys = ["reports/301095/a.pdf", "reports/301095/b.pdf"]
    cache_key = _compute_key_for_test("301095", oss_keys)

    rec = DeepAnalysis(
        stock_code="301095",
        oss_keys_json=json.dumps(oss_keys),
        cache_key=cache_key,
        analysis_text="# 已有分析\n这是缓存内容。",
        model_name="deepseek-chat",
        created_at=datetime.now(),
    )
    test_db.add(rec)
    test_db.commit()

    with client.stream(
        "GET", "/api/deep-analysis/analyze",
        params={"code": "301095", "oss_keys": ",".join(oss_keys)},
    ) as resp:
        assert resp.status_code == 200
        events = _collect_sse_events(resp)

    event_types = [e["event"] for e in events]
    assert "cached" in event_types
    assert "done" in event_types
    # 不应有 chunk（缓存命中不流式）
    assert "chunk" not in event_types

    cached_event = next(e for e in events if e["event"] == "cached")
    payload = json.loads(cached_event["data"])
    assert "已有分析" in payload["analysis_text"]


def test_analyze_force_refresh_skips_cache(client, test_db, monkeypatch):
    """force_refresh=true 时跳过缓存，进入流式分支。
    Mock analyze_stream 返回 chunk，避免真实 LLM 调用。"""
    oss_keys = ["reports/301095/a.pdf"]

    # 预填缓存（应被绕开）
    cache_key = _compute_key_for_test("301095", oss_keys)
    test_db.add(DeepAnalysis(
        stock_code="301095", oss_keys_json=json.dumps(oss_keys),
        cache_key=cache_key, analysis_text="cached",
        model_name="deepseek-chat", created_at=datetime.now(),
    ))
    test_db.commit()

    # Mock LLM 流：返回两个 chunk
    def fake_stream(code, keys, db):
        yield "MOCK_CHUNK_1"
        yield "MOCK_CHUNK_2"
    monkeypatch.setattr(
        "app.routers.deep_analysis.svc.analyze_stream", fake_stream,
    )

    with client.stream(
        "GET", "/api/deep-analysis/analyze",
        params={
            "code": "301095",
            "oss_keys": ",".join(oss_keys),
            "force_refresh": "true",
        },
    ) as resp:
        assert resp.status_code == 200
        events = _collect_sse_events(resp)

    event_types = [e["event"] for e in events]
    assert "cached" not in event_types
    assert "chunk" in event_types
    assert "done" in event_types

    chunks = [e for e in events if e["event"] == "chunk"]
    joined = "".join(json.loads(c["data"])["content"] for c in chunks)
    assert joined == "MOCK_CHUNK_1MOCK_CHUNK_2"


# ─────────────────────────────────────────────────────────────────────
# /history
# ─────────────────────────────────────────────────────────────────────

def test_history_format(client, test_db):
    """history 端点返回格式校验，最新优先"""
    import hashlib
    for i in range(3):
        test_db.add(DeepAnalysis(
            stock_code="301095",
            oss_keys_json=json.dumps([f"reports/301095/{i}.pdf"]),
            cache_key=hashlib.sha256(f"key-{i}".encode()).hexdigest()[:64],
            analysis_text=f"# 分析 {i}\n内容内容内容内容",
            model_name="deepseek-chat",
            created_at=datetime.now() - timedelta(days=i),
        ))
    test_db.commit()

    r = client.get("/api/deep-analysis/history", params={"code": "301095"})
    assert r.status_code == 200
    data = r.json()
    assert data["code"] == "301095"
    assert len(data["analyses"]) == 3
    # 最新优先（created_at 倒序）
    assert "分析 0" in data["analyses"][0]["preview"]
    for item in data["analyses"]:
        assert "id" in item
        assert "created_at" in item
        assert "report_count" in item
        assert "preview" in item


def test_history_empty(client):
    r = client.get("/api/deep-analysis/history", params={"code": "000001"})
    assert r.status_code == 200
    assert r.json()["analyses"] == []


# ─────────────────────────────────────────────────────────────────────
# /records/{id}
# ─────────────────────────────────────────────────────────────────────

def test_get_record_found(client, test_db):
    rec = DeepAnalysis(
        stock_code="301095",
        oss_keys_json=json.dumps(["reports/301095/x.pdf"]),
        cache_key="k" * 64,
        analysis_text="# 全文\n内容...",
        model_name="deepseek-chat",
        created_at=datetime.now(),
    )
    test_db.add(rec)
    test_db.commit()
    test_db.refresh(rec)

    r = client.get(f"/api/deep-analysis/records/{rec.id}")
    assert r.status_code == 200
    data = r.json()
    assert data["stock_code"] == "301095"
    assert "全文" in data["analysis_text"]
    assert isinstance(data["oss_keys"], list)


def test_get_record_not_found(client):
    r = client.get("/api/deep-analysis/records/99999")
    assert r.status_code == 404


# ─────────────────────────────────────────────────────────────────────
# 参数校验
# ─────────────────────────────────────────────────────────────────────

def test_parse_rejects_bad_code(client):
    r = client.post("/api/deep-analysis/parse", json={"code": "abc", "oss_keys": ["a"]})
    assert r.status_code == 422


def test_parse_rejects_empty_oss_keys(client):
    r = client.post("/api/deep-analysis/parse", json={"code": "301095", "oss_keys": []})
    assert r.status_code == 422


def test_analyze_rejects_empty_oss_keys(client):
    r = client.get(
        "/api/deep-analysis/analyze",
        params={"code": "301095", "oss_keys": ""},
    )
    assert r.status_code == 422


# ─────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────

def _compute_key_for_test(code: str, oss_keys: list[str]) -> str:
    """与 deep_analysis_service.compute_cache_key 保持一致的测试 helper"""
    import hashlib
    sorted_keys = sorted(oss_keys)
    raw = f"{code}|{'|'.join(sorted_keys)}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:64]


def _collect_sse_events(resp) -> list[dict]:
    """从 TestClient stream response 收集 SSE 事件"""
    events = []
    current_event = "message"
    for line in resp.iter_lines():
        if not line:
            continue
        if isinstance(line, bytes):
            line = line.decode("utf-8")
        if line.startswith("event:"):
            current_event = line.split(":", 1)[1].strip()
        elif line.startswith("data:"):
            data = line.split(":", 1)[1].strip()
            events.append({"event": current_event, "data": data})
            current_event = "message"  # reset
    return events
