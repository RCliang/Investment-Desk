from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.config import CACHE_TTL_FINANCIAL, CACHE_TTL_MARKET
from app.db import get_db
from app.services.cache import cache_get, cache_set
from app.services.akshare_service import akshare_service
from app.services.tushare_service import tushare_service
from app.services.astock_service import astock_service
from datetime import datetime
import hashlib
import json

router = APIRouter(prefix="/api/data", tags=["data"])


class QueryRequest(BaseModel):
    source: str
    action: str
    params: dict = {}


@router.post("/query")
async def query(req: QueryRequest, db: Session = Depends(get_db)):
    cache_key = hashlib.md5(f"{req.source}:{req.action}:{json.dumps(req.params, sort_keys=True)}".encode()).hexdigest()
    cached = cache_get(db, "data", cache_key)
    if cached:
        return cached

    if req.source == "akshare":
        svc = akshare_service
    elif req.source == "tushare":
        svc = tushare_service
    elif req.source == "astock":
        svc = astock_service
    else:
        raise HTTPException(400, f"Unknown source: {req.source}")

    handler = getattr(svc, req.action, None)
    if not handler:
        raise HTTPException(400, f"Unknown action: {req.action}")

    result = handler(**req.params)
    # Same classification rule as before, but wired to the config TTLs
    # (the hard-coded 300/86400 mirrored CACHE_TTL_MARKET/FINANCIAL).
    ttl = (CACHE_TTL_MARKET if "hist" in req.action
           or "realtime" in req.action else CACHE_TTL_FINANCIAL)
    cache_set(db, "data", cache_key, result, ttl)
    return result


@router.get("/stock/{code}")
async def stock_quote(code: str):
    quote = astock_service.get_stock_quote_tx(code)
    if not quote:
        raise HTTPException(404, f"Stock {code} not found")
    return quote


@router.get("/stock/{code}/hist")
async def stock_hist(code: str, period: str = "daily"):
    return akshare_service.get_stock_hist(code, period=period)


@router.get("/stock/{code}/financial")
async def stock_financial(code: str):
    return akshare_service.get_stock_financial(code)


@router.get("/stock/{code}/fund-flow")
async def stock_fund_flow(code: str):
    return akshare_service.get_fund_flow(code)


@router.get("/stock/{code}/reports")
async def stock_reports(code: str, page: int = 1, size: int = 10):
    return astock_service.get_research_reports(code, page=page, size=size)


@router.get("/stock/{code}/blocks")
async def stock_blocks(code: str):
    return astock_service.get_stock_concept_blocks(code)
