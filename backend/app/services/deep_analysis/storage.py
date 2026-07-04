"""DB CRUD for structured analysis."""
from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime

from sqlalchemy.orm import Session

from app.models.models import ReportContent, DeepAnalysis
from app.services.deep_analysis.schemas import AnalysisDoc

logger = logging.getLogger(__name__)

_MARKDOWN_SEPARATOR = "\n\n---\n\n"


def load_markdown(db: Session, code: str, oss_keys: list[str]) -> str | None:
    """按 oss_keys 顺序取多份 markdown,用分隔符拼接。任一缺失 → 返回 None。"""
    if not oss_keys:
        return None
    records = (
        db.query(ReportContent)
        .filter(
            ReportContent.stock_code == code,
            ReportContent.oss_key.in_(oss_keys),
        )
        .all()
    )
    by_key = {r.oss_key: r for r in records}
    parts: list[str] = []
    for k in oss_keys:
        rec = by_key.get(k)
        if rec is None or not rec.markdown_text:
            return None
        parts.append(rec.markdown_text)
    return _MARKDOWN_SEPARATOR.join(parts)


def make_cache_key(code: str, oss_keys: list[str], company_type: str) -> str:
    """sha256(code|sorted_keys|company_type)[:16] — 16 字符,与老 64 字符算法不冲突。"""
    sorted_keys = sorted(oss_keys)
    raw = f"{code}|{','.join(sorted_keys)}|{company_type}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def load_cached(
    db: Session, code: str, oss_keys: list[str], company_type: str,
) -> AnalysisDoc | None:
    """命中 v2 缓存返回 AnalysisDoc,否则 None。v1 记录不算命中。"""
    cache_key = make_cache_key(code, oss_keys, company_type)
    rec = db.query(DeepAnalysis).filter(DeepAnalysis.cache_key == cache_key).first()
    if rec is None or rec.analysis_version != "v2" or not rec.analysis_struct_json:
        return None
    return AnalysisDoc.model_validate(json.loads(rec.analysis_struct_json))


def save_structured(
    db: Session, code: str, oss_keys: list[str],
    company_type: str, doc: AnalysisDoc,
) -> int:
    """持久化 v2 AnalysisDoc,返回 analysis_id。同 cache_key 覆盖。"""
    cache_key = make_cache_key(code, oss_keys, company_type)
    payload = doc.model_dump_json(ensure_ascii=False)
    existing = db.query(DeepAnalysis).filter(DeepAnalysis.cache_key == cache_key).first()
    if existing:
        existing.analysis_struct_json = payload
        existing.analysis_version = "v2"
        existing.company_type = company_type
        existing.analysis_text = ""  # 列在老 DB 是 nullable=False
        existing.model_name = doc.model_name or existing.model_name
        existing.created_at = datetime.now()
        db.commit()
        return existing.id
    rec = DeepAnalysis(
        stock_code=code,
        oss_keys_json=json.dumps(oss_keys, ensure_ascii=False),
        cache_key=cache_key,
        analysis_text="",
        analysis_struct_json=payload,
        analysis_version="v2",
        company_type=company_type,
        model_name=doc.model_name or "",
        created_at=datetime.now(),
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)
    return rec.id


def load_history(db: Session, code: str, limit: int = 20) -> list[dict]:
    """该股票历史分析列表,最新优先。"""
    records = (
        db.query(DeepAnalysis)
        .filter(DeepAnalysis.stock_code == code)
        .order_by(DeepAnalysis.created_at.desc())
        .limit(limit)
        .all()
    )
    out: list[dict] = []
    for r in records:
        preview = ""
        if r.analysis_version == "v2" and r.analysis_struct_json:
            try:
                doc = AnalysisDoc.model_validate(json.loads(r.analysis_struct_json))
                preview = f"[v2] {doc.company_type} · {doc.stats.get('ok', 0)}/{doc.stats.get('total', 0)} 桶"
            except Exception:
                preview = "[v2 解析失败]"
        else:
            preview = (r.analysis_text or "")[:120]
        out.append({
            "id": r.id,
            "created_at": r.created_at.isoformat() if r.created_at else "",
            "model_name": r.model_name or "",
            "report_count": len(json.loads(r.oss_keys_json or "[]")),
            "preview": preview,
            "analysis_version": r.analysis_version or "v1",
            "company_type": r.company_type or "",
        })
    return out
