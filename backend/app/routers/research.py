"""
Research router — 研报搜索 + 下载接口。
GET  /api/research/reports   — 按股票代码（东财 reportapi）
GET  /api/research/search    — 按关键词语义搜索（iwencai）
POST /api/research/download  — 批量下载 PDF 上传 OSS
"""

import hashlib
import json
import logging
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth import verify_admin_token
from app.config import CACHE_TTL_RESEARCH, IWENCAI_API_KEY
from app.db import get_db
from app.models.models import DataCache
from app.services import oss_service
from app.services.research_service import (
    download_and_upload_reports,
    fetch_reports_by_code,
    search_reports_by_keyword,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/research", tags=["research"])


# ── 缓存 helpers（复用 data_cache 表）──

def _cache_get(db: Session, key: str):
    cached = db.query(DataCache).filter(DataCache.cache_key == key).first()
    if cached and cached.expires_at > datetime.now():
        return json.loads(cached.result_json)
    return None


def _cache_set(db: Session, key: str, data, ttl: int):
    db.query(DataCache).filter(DataCache.cache_key == key).delete()
    record = DataCache(
        cache_key=key,
        result_json=json.dumps(data, ensure_ascii=False, default=str),
        expires_at=datetime.now() + timedelta(seconds=ttl),
    )
    db.add(record)
    db.commit()


# ═══════════════════════════════════════════════════════════════════
# GET /api/research/reports?code=301095&max_pages=2
# ═══════════════════════════════════════════════════════════════════

@router.get("/reports", dependencies=[Depends(verify_admin_token)])
async def get_reports_by_code(
    code: str = Query(..., min_length=6, max_length=6, pattern=r"^\d{6}$"),
    max_pages: int = Query(2, ge=1, le=5),
    db: Session = Depends(get_db),
):
    """按股票代码搜索研报（东财 reportapi）"""
    cache_key = f"research:code:{code}:pages{max_pages}"
    cached = _cache_get(db, cache_key)
    if cached:
        return cached

    try:
        reports = fetch_reports_by_code(code, max_pages=max_pages)
    except Exception as e:
        logger.warning("fetch_reports_by_code failed: %s", e)
        return {"code": code, "total": 0, "reports": [], "error": "upstream_error"}

    result = {"code": code, "total": len(reports), "reports": reports}
    _cache_set(db, cache_key, result, CACHE_TTL_RESEARCH)
    return result


# ═══════════════════════════════════════════════════════════════════
# GET /api/research/search?keyword=EDA+硅光&size=50
# ═══════════════════════════════════════════════════════════════════

@router.get("/search", dependencies=[Depends(verify_admin_token)])
async def search_reports(
    keyword: str = Query(..., min_length=1),
    size: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """按关键词语义搜索研报（iwencai）"""
    if not IWENCAI_API_KEY:
        raise HTTPException(503, detail="IWENCAI_API_KEY not configured")

    kw_hash = hashlib.md5(keyword.encode()).hexdigest()
    cache_key = f"research:kw:{kw_hash}:s{size}"
    cached = _cache_get(db, cache_key)
    if cached:
        return cached

    try:
        reports = search_reports_by_keyword(keyword, size=size)
    except RuntimeError as e:
        error_msg = str(e)
        if "not configured" in error_msg:
            raise HTTPException(503, detail=error_msg)
        logger.warning("search_reports_by_keyword failed: %s", e)
        return {"keyword": keyword, "total": 0, "reports": [], "error": "iwencai_error"}
    except Exception as e:
        logger.warning("search_reports_by_keyword failed: %s", e)
        return {"keyword": keyword, "total": 0, "reports": [], "error": "iwencai_error"}

    result = {"keyword": keyword, "total": len(reports), "reports": reports}
    _cache_set(db, cache_key, result, CACHE_TTL_RESEARCH)
    return result


# ═══════════════════════════════════════════════════════════════════
# POST /api/research/download
# ═══════════════════════════════════════════════════════════════════

class ReportItem(BaseModel):
    info_code: str = Field(..., min_length=1)
    publish_date: str = ""
    org_name: str = ""
    title: str = ""


class DownloadRequest(BaseModel):
    code: str = Field(..., min_length=6, max_length=6, pattern=r"^\d{6}$")
    reports: list[ReportItem] = Field(..., min_length=1)


@router.post("/download", dependencies=[Depends(verify_admin_token)])
async def download_reports(req: DownloadRequest):
    """批量下载研报 PDF 并上传到阿里云 OSS"""
    if not oss_service.is_configured():
        raise HTTPException(503, detail="OSS not configured")

    reports_dicts = [r.model_dump() for r in req.reports]
    results = download_and_upload_reports(reports_dicts, req.code)

    success = sum(1 for r in results if r["status"] in ("ok", "exists"))
    failed = sum(1 for r in results if r["status"] == "failed")

    return {
        "total": len(results),
        "success": success,
        "failed": failed,
        "results": results,
    }
