"""
Deep analysis router — 公司深度分析 pipeline 的 HTTP 端点。

Endpoints:
- POST /api/deep-analysis/parse           提交 PDF 解析（MinerU）
- GET  /api/deep-analysis/parse-status    轮询解析进度
- GET  /api/deep-analysis/analyze         SSE 流式 AI 分析
- GET  /api/deep-analysis/history         历史分析列表
- GET  /api/deep-analysis/records/{id}    拉取单条历史分析
"""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sse_starlette.sse import EventSourceResponse

from app.auth import verify_admin_token
from app.db import get_db
from app.services import deep_analysis_service as svc
from app.services import mineru_service
from app.services.deep_analysis import orchestrate as _orchestrate
from app.services.deep_analysis.templates import COMPANY_TYPES

router = APIRouter(prefix="/api/deep-analysis", tags=["deep-analysis"])


# ═══════════════════════════════════════════════════════════════════
# POST /parse
# ═══════════════════════════════════════════════════════════════════

class ParseRequest(BaseModel):
    code: str = Field(..., min_length=6, max_length=6, pattern=r"^\d{6}$")
    oss_keys: list[str] = Field(..., min_length=1)


@router.post("/parse", dependencies=[Depends(verify_admin_token)])
async def parse(req: ParseRequest, db: Session = Depends(get_db)):
    """提交 PDF 给 MinerU 解析。已有缓存的自动跳过。"""
    # MinerU 未配置时仍允许（走 mock 模式），但显式告知调用方
    mineru_configured = mineru_service.is_configured()

    try:
        result = svc.parse_reports(req.code, req.oss_keys, db)
    except Exception as e:
        raise HTTPException(500, f"parse_error: {e}")

    return {
        **result,
        "mineru_mode": "live" if mineru_configured else "mock",
    }


# ═══════════════════════════════════════════════════════════════════
# GET /parse-status
# ═══════════════════════════════════════════════════════════════════

@router.get("/parse-status", dependencies=[Depends(verify_admin_token)])
async def parse_status(
    code: str = Query(..., min_length=6, max_length=6, pattern=r"^\d{6}$"),
    db: Session = Depends(get_db),
):
    """轮询该股票所有未完成的解析任务。"""
    return svc.parse_status(code, db)


# ═══════════════════════════════════════════════════════════════════
# GET /analyze (SSE)
# ═══════════════════════════════════════════════════════════════════

@router.get("/analyze", dependencies=[Depends(verify_admin_token)])
async def analyze(
    code: str = Query(..., min_length=6, max_length=6, pattern=r"^\d{6}$"),
    oss_keys: str = Query(..., description="逗号分隔的 oss_key 列表"),
    company_type: str = Query("general", description="企业类型"),
    force_refresh: bool = Query(False, description="为 true 时跳过缓存"),
    db: Session = Depends(get_db),
):
    """SSE 流式结构化分析。"""
    keys = [k.strip() for k in oss_keys.split(",") if k.strip()]
    if not keys:
        raise HTTPException(422, "oss_keys 不能为空")
    if company_type not in COMPANY_TYPES:
        raise HTTPException(422, f"invalid company_type: {company_type}")

    async def event_stream():
        try:
            async for evt in _orchestrate(db, code, keys, company_type, force_refresh):
                yield evt
        except Exception as e:
            yield {"event": "error", "data": json.dumps({"error": f"unexpected: {e}"}, ensure_ascii=False)}

    return EventSourceResponse(event_stream())


# ═══════════════════════════════════════════════════════════════════
# GET /history
# ═══════════════════════════════════════════════════════════════════

@router.get("/history", dependencies=[Depends(verify_admin_token)])
async def history(
    code: str = Query(..., min_length=6, max_length=6, pattern=r"^\d{6}$"),
    db: Session = Depends(get_db),
):
    """返回该股票的历史分析列表。"""
    return svc.list_history(code, db)


# ═══════════════════════════════════════════════════════════════════
# GET /records/{analysis_id}
# ═══════════════════════════════════════════════════════════════════

@router.get("/records/{analysis_id}", dependencies=[Depends(verify_admin_token)])
async def get_record(analysis_id: int, db: Session = Depends(get_db)):
    """按 id 拉取单条历史分析全文。"""
    record = svc.get_analysis_by_id(analysis_id, db)
    if not record:
        raise HTTPException(404, "analysis_not_found")
    return record


# ═══════════════════════════════════════════════════════════════════
# GET /latest
# ═══════════════════════════════════════════════════════════════════

@router.get("/latest")
async def latest(
    code: str = Query(..., min_length=6, max_length=6, pattern=r"^\d{6}$"),
    db: Session = Depends(get_db),
):
    """按 ticker 返回最新一条 v2 结构化分析(AnalysisDoc)。无则 404。

    供 ChainKb tab 03「公司拆解」按 ticker 拉取,与 /analyze SSE 的
    cached 事件 payload 同结构,前端类型零新增。
    """
    doc = svc.get_latest_v2(code, db)
    if doc is None:
        raise HTTPException(404, "no_v2_analysis")
    return doc
