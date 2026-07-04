"""runner.py: orchestrate async generator + build_analysis_doc."""
import asyncio
import json
from datetime import datetime
from unittest.mock import MagicMock

import pytest

from app.models.models import ReportContent
from app.services.deep_analysis import runner, storage
from app.services.deep_analysis.analyzer import AnalyzerError
from app.services.deep_analysis.schemas import BucketResult, FieldValue


def _seed_markdown(test_db, code="301095", keys=("a.pdf",), text=None):
    for k in keys:
        test_db.add(ReportContent(
            oss_key=k, stock_code=code, title=f"R-{k}",
            markdown_text=text or ("研报正文 " * 50),
            token_count=10, parsed_at=datetime.now(),
        ))
    test_db.commit()


def _collect_events(gen):
    """同步收集 async generator 产出的所有事件。"""
    out = []
    async def drain():
        async for evt in gen:
            out.append(evt)
    asyncio.run(drain())
    return out


# ── build_analysis_doc ──────────────────────────────────────────────

def test_build_analysis_doc_computes_stats():
    buckets = [
        BucketResult(bucket_id="industry_chain", fields={"x": FieldValue(value="1")}),
        BucketResult(bucket_id="financial",      fields={"y": FieldValue(value="2")}),
    ]
    doc = runner.build_analysis_doc(
        company_type="general", code="301095",
        accumulator=buckets, model_name="deepseek-chat", error_count=1,
    )
    assert doc.version == "v2"
    assert doc.company_type == "general"
    assert doc.stock_code == "301095"
    assert doc.model_name == "deepseek-chat"
    assert doc.stats == {"ok": 2, "error": 1, "total": 3}
    assert len(doc.buckets) == 2
    assert doc.analyzed_at  # 非空 ISO 字符串


# ── orchestrate: happy path ─────────────────────────────────────────

def test_orchestrate_emits_correct_event_sequence(test_db, mocker):
    _seed_markdown(test_db)
    # mock analyzer: 不调真实 LLM,直接返回 BucketResult
    async def fake_run(bucket_id, md):
        return BucketResult(
            bucket_id=bucket_id,
            fields={"x": FieldValue(value="ok", evidence="strong")},
        )
    mocker.patch("app.services.deep_analysis.runner.run_single_bucket", fake_run)

    events = _collect_events(runner.orchestrate(
        test_db, "301095", ["a.pdf"], "general", force_refresh=False,
    ))

    event_types = [e["event"] for e in events]
    assert event_types[0] == "start"
    assert event_types[-1] == "done"
    # general 路由 4 个桶
    assert event_types.count("bucket_start") == 4
    assert event_types.count("bucket_done") == 4
    assert "bucket_error" not in event_types

    # start 事件包含桶列表
    start_payload = json.loads(events[0]["data"])
    assert start_payload["company_type"] == "general"
    assert start_payload["buckets"] == ["industry_chain", "financial", "risk", "catalyst"]


def test_orchestrate_cached_returns_single_cached_event(test_db):
    """命中缓存:只发 cached 事件,不发 start/bucket_*/done。"""
    _seed_markdown(test_db)
    # 预存 v2 记录
    from app.services.deep_analysis.schemas import AnalysisDoc
    doc = AnalysisDoc(
        company_type="general", stock_code="301095",
        buckets=[], analyzed_at="2026-07-04T10:00:00Z",
    )
    storage.save_structured(test_db, "301095", ["a.pdf"], "general", doc)

    events = _collect_events(runner.orchestrate(
        test_db, "301095", ["a.pdf"], "general", force_refresh=False,
    ))

    assert len(events) == 1
    assert events[0]["event"] == "cached"


# ── orchestrate: error paths ────────────────────────────────────────

def test_orchestrate_short_markdown_short_circuits(test_db, mocker):
    _seed_markdown(test_db, text="短")  # < 200 字
    events = _collect_events(runner.orchestrate(
        test_db, "301095", ["a.pdf"], "general", force_refresh=False,
    ))
    event_types = [e["event"] for e in events]
    # 短路:error + done,没有 start / bucket_*
    assert "start" not in event_types
    assert "bucket_start" not in event_types
    assert "error" in event_types
    assert event_types[-1] == "done"


def test_orchestrate_missing_markdown_short_circuits(test_db, mocker):
    """load_markdown 返回 None 时也短路。"""
    events = _collect_events(runner.orchestrate(
        test_db, "301095", ["nonexistent.pdf"], "general", force_refresh=False,
    ))
    event_types = [e["event"] for e in events]
    assert "error" in event_types
    assert "start" not in event_types


def test_orchestrate_continues_after_bucket_failure(test_db, mocker):
    _seed_markdown(test_db)
    call_count = {"n": 0}

    async def fake_run(bucket_id, md):
        call_count["n"] += 1
        if bucket_id == "financial":
            raise AnalyzerError("simulated failure")
        return BucketResult(bucket_id=bucket_id, fields={})

    mocker.patch("app.services.deep_analysis.runner.run_single_bucket", fake_run)

    events = _collect_events(runner.orchestrate(
        test_db, "301095", ["a.pdf"], "general", force_refresh=False,
    ))

    event_types = [e["event"] for e in events]
    assert event_types.count("bucket_start") == 4
    assert event_types.count("bucket_done") == 3
    assert event_types.count("bucket_error") == 1
    assert event_types[-1] == "done"
    # done 事件含 error_count=1
    done_payload = json.loads(events[-1]["data"])
    assert done_payload["error_count"] == 1
    assert done_payload["ok_count"] == 3
    assert call_count["n"] == 4  # 4 个桶都调了,没中断


def test_orchestrate_force_refresh_bypasses_cache(test_db, mocker):
    _seed_markdown(test_db)
    from app.services.deep_analysis.schemas import AnalysisDoc
    doc = AnalysisDoc(
        company_type="general", stock_code="301095",
        buckets=[], analyzed_at="2026-07-04T10:00:00Z",
    )
    storage.save_structured(test_db, "301095", ["a.pdf"], "general", doc)

    async def fake_run(bucket_id, md):
        return BucketResult(bucket_id=bucket_id, fields={})
    mocker.patch("app.services.deep_analysis.runner.run_single_bucket", fake_run)

    events = _collect_events(runner.orchestrate(
        test_db, "301095", ["a.pdf"], "general", force_refresh=True,
    ))
    event_types = [e["event"] for e in events]
    assert "cached" not in event_types
    assert event_types[0] == "start"
