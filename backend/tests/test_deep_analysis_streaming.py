"""streaming.py: 7 种 SSE 事件格式化。"""
import json

from app.services.deep_analysis.schemas import BucketResult, FieldValue, AnalysisDoc
from app.services.deep_analysis.streaming import (
    format_start, format_bucket_start, format_bucket_done,
    format_bucket_error, format_cached, format_error, format_done,
)


def test_start_emits_bucket_list():
    evt = format_start(company_type="equipment", bucket_ids=["industry_chain", "equipment"])
    assert evt["event"] == "start"
    payload = json.loads(evt["data"])
    assert payload["version"] == "v2"
    assert payload["company_type"] == "equipment"
    assert payload["buckets"] == ["industry_chain", "equipment"]


def test_bucket_start():
    assert format_bucket_start("industry_chain") == {
        "event": "bucket_start",
        "data": json.dumps({"bucket_id": "industry_chain"}, ensure_ascii=False),
    }


def test_bucket_done_includes_serialized_result():
    br = BucketResult(bucket_id="financial", fields={"x": FieldValue(value="1", evidence="strong")})
    evt = format_bucket_done(br)
    assert evt["event"] == "bucket_done"
    payload = json.loads(evt["data"])
    assert payload["bucket_id"] == "financial"
    assert payload["result"]["fields"]["x"]["value"] == "1"


def test_bucket_error():
    evt = format_bucket_error("financial", "JSON parse failed after 1 retry")
    assert evt["event"] == "bucket_error"
    payload = json.loads(evt["data"])
    assert payload["bucket_id"] == "financial"
    assert "JSON parse" in payload["error"]


def test_cached_serializes_full_doc():
    doc = AnalysisDoc(
        company_type="general", stock_code="301095",
        buckets=[], analyzed_at="2026-07-04T10:00:00Z",
    )
    evt = format_cached(doc)
    assert evt["event"] == "cached"
    payload = json.loads(evt["data"])
    assert payload["stock_code"] == "301095"


def test_error_short_circuit():
    evt = format_error(reason="markdown_too_short", extra={"len": 42})
    payload = json.loads(evt["data"])
    assert payload["reason"] == "markdown_too_short"
    assert payload["len"] == 42


def test_done_has_counts():
    evt = format_done(analysis_id=42, ok_count=4, error_count=1, total=5)
    payload = json.loads(evt["data"])
    assert payload == {"version": "v2", "analysis_id": 42, "ok_count": 4, "error_count": 1, "total": 5}


def test_chinese_quote_not_mangled():
    """UTF-8 中文不乱码。"""
    br = BucketResult(bucket_id="industry_chain",
                      fields={"x": FieldValue(value="国产化率约15%", evidence="medium", quote="原文片段")})
    evt = format_bucket_done(br)
    assert "国产化率" in evt["data"]
    assert "原文片段" in evt["data"]
