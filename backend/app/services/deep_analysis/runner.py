"""orchestrate: 按 company_type 路由 → 串行调 analyzer → 拼装 AnalysisDoc。"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import AsyncIterator

from sqlalchemy.orm import Session

from app.config import MODEL_NAME
from app.services.deep_analysis import storage, streaming
from app.services.deep_analysis.analyzer import AnalyzerError, run_single_bucket
from app.services.deep_analysis.schemas import AnalysisDoc, BucketResult
from app.services.deep_analysis.templates import ROUTING_TABLE

logger = logging.getLogger(__name__)

MIN_MARKDOWN_LEN = 200


def build_analysis_doc(
    company_type: str,
    code: str,
    accumulator: list[BucketResult],
    model_name: str,
    error_count: int,
) -> AnalysisDoc:
    """把 accumulator 拼成 AnalysisDoc,自动算 stats。"""
    ok = len(accumulator)
    total = ok + error_count
    return AnalysisDoc(
        company_type=company_type,
        stock_code=code,
        buckets=list(accumulator),
        analyzed_at=datetime.now(timezone.utc).isoformat(),
        model_name=model_name,
        stats={"ok": ok, "error": error_count, "total": total},
    )


async def orchestrate(
    db: Session,
    code: str,
    oss_keys: list[str],
    company_type: str,
    force_refresh: bool,
) -> AsyncIterator[dict]:
    """主流程 async generator。yield SSE {event, data} dict。"""
    # 1. 缓存命中检查
    if not force_refresh:
        cached = storage.load_cached(db, code, oss_keys, company_type)
        if cached is not None:
            yield streaming.format_cached(cached)
            return

    # 2. 加载 markdown
    markdown_text = storage.load_markdown(db, code, oss_keys)
    if markdown_text is None:
        yield streaming.format_error("markdown_not_found", {"oss_keys": oss_keys})
        yield streaming.format_done(analysis_id=0, ok_count=0, error_count=0, total=0)
        return
    if len(markdown_text) < MIN_MARKDOWN_LEN:
        yield streaming.format_error(
            "markdown_too_short", {"len": len(markdown_text), "min": MIN_MARKDOWN_LEN},
        )
        yield streaming.format_done(analysis_id=0, ok_count=0, error_count=0, total=0)
        return

    # 3. 路由
    bucket_ids = ROUTING_TABLE[company_type]
    yield streaming.format_start(company_type, bucket_ids)

    # 4. 串行调 analyzer
    accumulator: list[BucketResult] = []
    error_count = 0
    for bid in bucket_ids:
        yield streaming.format_bucket_start(bid)
        try:
            result = await run_single_bucket(bid, markdown_text)
            yield streaming.format_bucket_done(result)
            accumulator.append(result)
        except AnalyzerError as e:
            logger.warning("bucket %s failed: %s", bid, e)
            yield streaming.format_bucket_error(bid, str(e))
            error_count += 1
            continue

    # 5. 持久化 + done
    doc = build_analysis_doc(
        company_type=company_type, code=code,
        accumulator=accumulator, model_name=MODEL_NAME,
        error_count=error_count,
    )
    try:
        analysis_id = storage.save_structured(db, code, oss_keys, company_type, doc)
    except Exception as e:
        logger.exception("save_structured failed: %s", e)
        analysis_id = 0

    yield streaming.format_done(
        analysis_id=analysis_id,
        ok_count=len(accumulator),
        error_count=error_count,
        total=len(bucket_ids),
    )
