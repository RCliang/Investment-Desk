"""SSE event formatters: 产出 {event, data} dict 供 EventSourceResponse yield。"""
from __future__ import annotations

import json
from typing import Any

from app.services.deep_analysis.schemas import AnalysisDoc, BucketResult


def _emit(event: str, payload: dict[str, Any]) -> dict[str, str]:
    return {"event": event, "data": json.dumps(payload, ensure_ascii=False)}


def format_start(company_type: str, bucket_ids: list[str]) -> dict[str, str]:
    return _emit("start", {
        "version": "v2",
        "company_type": company_type,
        "buckets": bucket_ids,
    })


def format_bucket_start(bucket_id: str) -> dict[str, str]:
    return _emit("bucket_start", {"bucket_id": bucket_id})


def format_bucket_done(result: BucketResult) -> dict[str, str]:
    return _emit("bucket_done", {
        "bucket_id": result.bucket_id,
        "result": result.model_dump(),
    })


def format_bucket_error(bucket_id: str, error: str) -> dict[str, str]:
    return _emit("bucket_error", {"bucket_id": bucket_id, "error": error})


def format_cached(doc: AnalysisDoc) -> dict[str, str]:
    return _emit("cached", doc.model_dump())


def format_error(reason: str, extra: dict[str, Any] | None = None) -> dict[str, str]:
    payload = {"reason": reason}
    if extra:
        payload.update(extra)
    return _emit("error", payload)


def format_done(analysis_id: int, ok_count: int, error_count: int, total: int) -> dict[str, str]:
    return _emit("done", {
        "version": "v2",
        "analysis_id": analysis_id,
        "ok_count": ok_count,
        "error_count": error_count,
        "total": total,
    })
