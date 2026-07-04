"""
Deep analysis service — slim facade.

职责:
- Step 1/2 PDF 解析编排 (parse_reports / parse_status / get_cached_markdown)
- Step 4 结构化分析的历史查询 (list_history / get_analysis_by_id) — 委托给
  deep_analysis 子包;新分析流由 router 直接调用子包的 orchestrate。
"""

from __future__ import annotations

import json
import logging
from datetime import datetime

from sqlalchemy.orm import Session

from app.models.models import ReportContent, DeepAnalysis
from app.services import mineru_service, oss_service

# 子包 re-export(供老调用方逐步迁移)
from app.services.deep_analysis import (
    orchestrate,  # noqa: F401  SSE async generator(替代老 analyze_stream)
    load_history as _load_history_v2,
    load_cached as _load_cached_v2,  # noqa: F401
)

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════
# 解析编排
# ═══════════════════════════════════════════════════════════════════

def parse_reports(code: str, oss_keys: list[str], db: Session) -> dict:
    """
    提交 PDF 给 MinerU 解析。已有缓存的自动跳过。

    返回:
        {
            "total": N,
            "cached": N,
            "submitted": N,
            "failed": N,
            "results": [{"oss_key", "status": "cached|submitted|failed", "error"?, "task_id"?}]
        }
    """
    results = []
    cached_count = 0
    submitted_count = 0
    failed_count = 0

    # 查已有缓存
    existing = {
        rc.oss_key for rc in
        db.query(ReportContent).filter(ReportContent.stock_code == code).all()
    }

    for oss_key in oss_keys:
        if oss_key in existing:
            results.append({"oss_key": oss_key, "status": "cached"})
            cached_count += 1
            continue

        # 检查 OSS 中是否存在该对象
        if not oss_service.object_exists(oss_key):
            results.append({
                "oss_key": oss_key,
                "status": "failed",
                "error": "oss_key_not_found",
            })
            failed_count += 1
            continue

        # 生成签名 URL 给 MinerU 拉取
        try:
            pdf_url = oss_service.sign_url(oss_key, expires=3600)
        except Exception as e:
            logger.warning("sign_url failed for %s: %s", oss_key, e)
            results.append({
                "oss_key": oss_key, "status": "failed",
                "error": "oss_sign_error",
            })
            failed_count += 1
            continue

        # 提交 MinerU
        try:
            task_id = mineru_service.submit_parse(
                pdf_url,
                meta={"oss_key": oss_key, "stock_code": code, "title": ""},
            )
            results.append({
                "oss_key": oss_key, "status": "submitted", "task_id": task_id,
            })
            submitted_count += 1
        except RuntimeError as e:
            logger.warning("submit_parse failed for %s: %s", oss_key, e)
            results.append({
                "oss_key": oss_key, "status": "failed",
                "error": str(e),
            })
            failed_count += 1

    return {
        "total": len(oss_keys),
        "cached": cached_count,
        "submitted": submitted_count,
        "failed": failed_count,
        "results": results,
    }


def parse_status(code: str, db: Session) -> dict:
    """
    轮询该股票所有未完成的解析任务，完成的写入 report_contents。

    返回:
        {
            "code": code,
            "total": N, "done": N, "pending": N, "failed": N,
            "details": [{"oss_key", "status", "token_count"?, "error"?}]
        }
    """
    # 该股票所有 pending task：通过进程内 task 表的 stock_code 过滤
    pending_tids = [
        tid for tid in mineru_service.list_pending()
        if (mineru_service.get_task_meta(tid) or {}).get("stock_code") == code
    ]

    # 已写入 DB 的（done 的子集）
    db_records = {
        rc.oss_key: rc for rc in
        db.query(ReportContent).filter(ReportContent.stock_code == code).all()
    }

    details = []
    pending_count = 0
    failed_count = 0
    done_count = 0

    for tid in pending_tids:
        meta = mineru_service.get_task_meta(tid) or {}
        oss_key = meta.get("oss_key", "")
        try:
            result = mineru_service.poll_result(tid)
        except RuntimeError as e:
            failed_count += 1
            details.append({
                "oss_key": oss_key, "status": "failed", "error": str(e),
            })
            continue

        if result is None:
            pending_count += 1
            details.append({"oss_key": oss_key, "status": "parsing"})
        else:
            # 完成 → 写入 DB
            rc = ReportContent(
                oss_key=oss_key,
                stock_code=code,
                title=meta.get("title", ""),
                markdown_text=result["markdown"],
                token_count=result["token_count"],
                parsed_at=datetime.now(),
            )
            db.add(rc)
            db.commit()
            done_count += 1
            details.append({
                "oss_key": oss_key, "status": "done",
                "token_count": result["token_count"],
            })

    # 已在 DB 的（之前完成的）
    for oss_key, rc in db_records.items():
        # 避免与刚写入的重复
        if any(d["oss_key"] == oss_key for d in details):
            continue
        done_count += 1
        details.append({
            "oss_key": oss_key, "status": "done",
            "token_count": rc.token_count or 0,
        })

    total = done_count + pending_count + failed_count
    return {
        "code": code,
        "total": total,
        "done": done_count,
        "pending": pending_count,
        "failed": failed_count,
        "details": details,
    }


def get_cached_markdown(
    code: str, oss_keys: list[str], db: Session,
) -> list[dict]:
    """从 DB 读取已解析的 markdown，按 parsed_at 倒序（最新优先）。"""
    records = (
        db.query(ReportContent)
        .filter(
            ReportContent.stock_code == code,
            ReportContent.oss_key.in_(oss_keys),
        )
        .order_by(ReportContent.parsed_at.desc())
        .all()
    )
    return [
        {
            "oss_key": rc.oss_key,
            "title": rc.title or "",
            "markdown_text": rc.markdown_text,
            "token_count": rc.token_count or 0,
            "parsed_at": rc.parsed_at.isoformat() if rc.parsed_at else "",
        }
        for rc in records
    ]


# ═══════════════════════════════════════════════════════════════════
# 历史查询 (v1/v2 混合)
# ═══════════════════════════════════════════════════════════════════

def list_history(code: str, db: Session, limit: int = 20) -> dict:
    """历史列表(支持 v1/v2 混合)。委托给子包 + 包装为 {code, analyses}。"""
    items = _load_history_v2(db, code, limit)
    return {"code": code, "analyses": items}


def get_analysis_by_id(analysis_id: int, db: Session) -> dict | None:
    """按 id 拉取单条历史分析全文(包含 v1/v2 字段)。"""
    r = db.query(DeepAnalysis).filter(DeepAnalysis.id == analysis_id).first()
    if not r:
        return None
    return {
        "id": r.id,
        "stock_code": r.stock_code,
        "oss_keys": json.loads(r.oss_keys_json or "[]"),
        "analysis_text": r.analysis_text or "",
        "analysis_struct": json.loads(r.analysis_struct_json) if r.analysis_struct_json else None,
        "analysis_version": r.analysis_version or "v1",
        "company_type": r.company_type or "",
        "created_at": r.created_at.isoformat() if r.created_at else "",
        "model_name": r.model_name or "",
    }
