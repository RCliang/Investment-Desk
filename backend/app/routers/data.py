from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.db import get_db
from app.models.models import DataCache
from app.services.akshare_service import akshare_service
from app.services.tushare_service import tushare_service
from app.services.astock_service import astock_service
from datetime import datetime, timedelta
import hashlib
import json

router = APIRouter(prefix="/api/data", tags=["data"])


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


class QueryRequest(BaseModel):
    source: str
    action: str
    params: dict = {}


@router.post("/query")
async def query(req: QueryRequest, db: Session = Depends(get_db)):
    cache_key = hashlib.md5(f"{req.source}:{req.action}:{json.dumps(req.params, sort_keys=True)}".encode()).hexdigest()
    cached = _cache_get(db, cache_key)
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
    ttl = 300 if "hist" in req.action or "realtime" in req.action else 86400
    _cache_set(db, cache_key, result, ttl)
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
