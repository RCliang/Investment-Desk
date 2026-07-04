"""Structured extraction schemas (Pydantic v2)."""
from __future__ import annotations

from typing import Literal, Union
from pydantic import BaseModel, Field


FieldValueT = Union[str, int, float, list[str], None]


class FieldValue(BaseModel):
    """单字段三件套。找不到的字段统一填 {value:null, evidence:"unknown", quote:null}。"""
    value: FieldValueT = None
    evidence: Literal["strong", "medium", "weak", "unknown"] = "unknown"
    quote: str | None = None


class BucketResult(BaseModel):
    """单桶结果。fields 是 dict 而非固定字段,允许不同 bucket 有不同字段集。"""
    bucket_id: str
    fields: dict[str, FieldValue] = Field(default_factory=dict)


class AnalysisDoc(BaseModel):
    """完整结构化分析文档(持久化到 analysis_struct_json)。"""
    version: Literal["v2"] = "v2"
    company_type: str
    stock_code: str
    buckets: list[BucketResult]
    analyzed_at: str  # ISO 8601 UTC
    model_name: str = ""
    stats: dict[str, int] = Field(
        default_factory=lambda: {"ok": 0, "error": 0, "total": 0}
    )
