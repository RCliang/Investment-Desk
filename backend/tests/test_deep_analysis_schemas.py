"""FieldValue / BucketResult / AnalysisDoc 单元测试。"""
import pytest
from pydantic import ValidationError

from app.services.deep_analysis.schemas import FieldValue, BucketResult, AnalysisDoc


def test_field_value_accepts_string():
    fv = FieldValue(value="约15%", evidence="medium", quote="...")
    assert fv.value == "约15%"
    assert fv.evidence == "medium"


def test_field_value_accepts_list():
    fv = FieldValue(value=["北方华创", "中微公司"], evidence="strong")
    assert isinstance(fv.value, list)


def test_field_value_accepts_null_defaults():
    fv = FieldValue()
    assert fv.value is None
    assert fv.evidence == "unknown"
    assert fv.quote is None


def test_field_value_rejects_bad_evidence():
    with pytest.raises(ValidationError):
        FieldValue(value="x", evidence="bogus")


def test_bucket_result_accepts_dict_fields():
    br = BucketResult(bucket_id="industry_chain", fields={
        "domestic_share": FieldValue(value="15%", evidence="medium"),
    })
    assert br.bucket_id == "industry_chain"
    assert "domestic_share" in br.fields


def test_analysis_doc_stats_default():
    doc = AnalysisDoc(
        company_type="equipment", stock_code="688120",
        buckets=[], analyzed_at="2026-07-04T10:00:00Z",
    )
    assert doc.version == "v2"
    assert doc.stats == {"ok": 0, "error": 0, "total": 0}
