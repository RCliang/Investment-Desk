"""storage.py: markdown 加载、cache_key、AnalysisDoc 持久化。"""
import json
from datetime import datetime

import pytest

from app.models.models import ReportContent, DeepAnalysis
from app.services.deep_analysis import storage
from app.services.deep_analysis.schemas import (
    AnalysisDoc, BucketResult, FieldValue,
)


# ── load_markdown ────────────────────────────────────────────────────

def test_load_markdown_concatenates_multiple_reports(test_db):
    test_db.add(ReportContent(
        oss_key="a.pdf", stock_code="301095", title="R1",
        markdown_text="AAA", token_count=1, parsed_at=datetime.now(),
    ))
    test_db.add(ReportContent(
        oss_key="b.pdf", stock_code="301095", title="R2",
        markdown_text="BBB", token_count=1, parsed_at=datetime.now(),
    ))
    test_db.commit()
    md = storage.load_markdown(test_db, "301095", ["a.pdf", "b.pdf"])
    assert "AAA" in md
    assert "BBB" in md
    assert "---" in md  # 分隔符


def test_load_markdown_returns_none_if_any_missing(test_db):
    test_db.add(ReportContent(
        oss_key="a.pdf", stock_code="301095", title="R1",
        markdown_text="AAA", token_count=1, parsed_at=datetime.now(),
    ))
    test_db.commit()
    # b.pdf 不存在
    assert storage.load_markdown(test_db, "301095", ["a.pdf", "b.pdf"]) is None


def test_load_markdown_empty_keys_returns_none(test_db):
    assert storage.load_markdown(test_db, "301095", []) is None


# ── make_cache_key ───────────────────────────────────────────────────

def test_cache_key_is_16_chars():
    key = storage.make_cache_key("301095", ["a.pdf"], "equipment")
    assert len(key) == 16


def test_cache_key_differs_by_company_type():
    k1 = storage.make_cache_key("301095", ["a.pdf"], "equipment")
    k2 = storage.make_cache_key("301095", ["a.pdf"], "material")
    assert k1 != k2


def test_cache_key_independent_of_order():
    k1 = storage.make_cache_key("301095", ["a.pdf", "b.pdf"], "general")
    k2 = storage.make_cache_key("301095", ["b.pdf", "a.pdf"], "general")
    assert k1 == k2


# ── save_structured + load_cached ───────────────────────────────────

def _make_doc(company_type="equipment", stock_code="301095"):
    return AnalysisDoc(
        company_type=company_type, stock_code=stock_code,
        buckets=[BucketResult(bucket_id="industry_chain",
                              fields={"x": FieldValue(value="15%", evidence="medium")})],
        analyzed_at="2026-07-04T10:00:00Z",
        model_name="deepseek-chat",
        stats={"ok": 1, "error": 0, "total": 1},
    )


def test_save_and_load_roundtrip(test_db):
    doc = _make_doc()
    aid = storage.save_structured(
        test_db, "301095", ["a.pdf"], "equipment", doc,
    )
    assert isinstance(aid, int)

    loaded = storage.load_cached(test_db, "301095", ["a.pdf"], "equipment")
    assert loaded is not None
    assert loaded.company_type == "equipment"
    assert loaded.buckets[0].bucket_id == "industry_chain"
    assert loaded.buckets[0].fields["x"].value == "15%"


def test_load_cached_returns_none_for_v1_records(test_db):
    """老 v1 记录(无 analysis_struct_json)load_cached 应返回 None。"""
    test_db.add(DeepAnalysis(
        stock_code="301095",
        oss_keys_json=json.dumps(["a.pdf"]),
        cache_key="k" * 16,
        analysis_text="# 老的 markdown",
        analysis_version="v1",
        model_name="deepseek-chat",
        created_at=datetime.now(),
    ))
    test_db.commit()
    # 即使 cache_key 算法不同,这里也直接验 v1 不被 v2 视为 cached
    assert storage.load_cached(test_db, "301095", ["a.pdf"], "equipment") is None


def test_save_structured_writes_empty_analysis_text(test_db):
    """v2 记录 analysis_text 必须写空串(列在老 DB 是 nullable=False)。"""
    doc = _make_doc()
    aid = storage.save_structured(
        test_db, "301095", ["a.pdf"], "equipment", doc,
    )
    rec = test_db.query(DeepAnalysis).filter(DeepAnalysis.id == aid).one()
    assert rec.analysis_text == ""
    assert rec.analysis_version == "v2"
    assert rec.company_type == "equipment"


def test_save_structured_overwrites_same_cache_key(test_db):
    doc1 = _make_doc()
    aid1 = storage.save_structured(test_db, "301095", ["a.pdf"], "equipment", doc1)
    doc2 = AnalysisDoc(
        company_type="equipment", stock_code="301095",
        buckets=[], analyzed_at="2026-07-04T11:00:00Z",
        stats={"ok": 0, "error": 0, "total": 0},
    )
    aid2 = storage.save_structured(test_db, "301095", ["a.pdf"], "equipment", doc2)
    assert aid1 == aid2  # 覆盖,不新增
    assert test_db.query(DeepAnalysis).count() == 1


# ── load_history ────────────────────────────────────────────────────

def test_load_history_returns_v2_records_with_metadata(test_db):
    doc = _make_doc()
    storage.save_structured(test_db, "301095", ["a.pdf"], "equipment", doc)
    history = storage.load_history(test_db, "301095")
    assert len(history) == 1
    item = history[0]
    assert item["analysis_version"] == "v2"
    assert item["company_type"] == "equipment"
    assert item["id"] > 0
