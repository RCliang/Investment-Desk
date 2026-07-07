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

from app.main import app
from app.models.models import ReportContent, DeepAnalysis


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

def test_analyze_invalid_company_type_returns_422(client):
    r = client.get(
        "/api/deep-analysis/analyze",
        params={"code": "301095", "oss_keys": "a.pdf", "company_type": "bogus"},
    )
    assert r.status_code == 422


def test_analyze_cache_hit_v2(client, test_db):
    """预填 v2 结构化记录 → /analyze 返回 cached 事件。"""
    from app.services.deep_analysis.schemas import AnalysisDoc
    from app.services.deep_analysis import storage

    oss_keys = ["reports/301095/a.pdf"]
    doc = AnalysisDoc(
        company_type="general", stock_code="301095",
        buckets=[], analyzed_at="2026-07-04T10:00:00Z",
        model_name="deepseek-chat",
    )
    storage.save_structured(test_db, "301095", oss_keys, "general", doc)

    with client.stream(
        "GET", "/api/deep-analysis/analyze",
        params={"code": "301095", "oss_keys": ",".join(oss_keys), "company_type": "general"},
    ) as resp:
        assert resp.status_code == 200
        events = _collect_sse_events(resp)

    event_types = [e["event"] for e in events]
    assert "cached" in event_types
    # cached 单事件,不应有 start/bucket_*
    assert "start" not in event_types
    assert "bucket_done" not in event_types


def test_analyze_force_refresh_emits_start_and_done(client, test_db, monkeypatch):
    """force_refresh=true 时跳过缓存,进入 orchestrate。
    Mock run_single_bucket,验证 start + bucket_done + done 事件序列。"""
    import asyncio
    oss_keys = ["reports/301095/a.pdf"]

    # 预填 v2 缓存(应被绕开)
    from app.services.deep_analysis.schemas import AnalysisDoc
    from app.services.deep_analysis import storage
    doc = AnalysisDoc(
        company_type="general", stock_code="301095",
        buckets=[], analyzed_at="2026-07-04T10:00:00Z",
    )
    storage.save_structured(test_db, "301095", oss_keys, "general", doc)

    # 预填 markdown(orchestrate 需要至少 200 字)
    from app.models.models import ReportContent
    from datetime import datetime
    test_db.add(ReportContent(
        oss_key=oss_keys[0], stock_code="301095", title="R",
        markdown_text="研报正文内容 " * 50,
        token_count=10, parsed_at=datetime.now(),
    ))
    test_db.commit()

    # Mock LLM:每个桶直接返回空 BucketResult
    from app.services.deep_analysis.schemas import BucketResult
    async def fake_run(bucket_id, md):
        return BucketResult(bucket_id=bucket_id, fields={})
    monkeypatch.setattr(
        "app.services.deep_analysis.runner.run_single_bucket", fake_run,
    )

    with client.stream(
        "GET", "/api/deep-analysis/analyze",
        params={
            "code": "301095",
            "oss_keys": ",".join(oss_keys),
            "company_type": "general",
            "force_refresh": "true",
        },
    ) as resp:
        assert resp.status_code == 200
        events = _collect_sse_events(resp)

    event_types = [e["event"] for e in events]
    assert "cached" not in event_types
    assert event_types[0] == "start"
    assert "bucket_done" in event_types
    assert event_types[-1] == "done"


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
