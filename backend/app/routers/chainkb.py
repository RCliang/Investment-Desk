"""Read-only HTTP API for the v1 chain knowledge base.

Five endpoints under /api/chainkb/* expose the static Layer → SubIndustry →
Company tree plus per-company market/financial snapshots and time-series.

This is a separate feature from /api/chain/* (which is the LLM-powered
industry analysis flow). The KB router reads only from the chain_* tables
populated by backend/scripts/load_seed_to_db.py.

All endpoints are sync (matches existing routers) and return raw dicts
serialized by services/chainkb_service.py.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.services import chainkb_service

router = APIRouter(prefix="/api/chainkb", tags=["chainkb"])

# Default types fetched by the timeseries endpoint
_DEFAULT_TS_TYPES = "lockup,holders,margin,reports"
_VALID_TS_TYPES = {"lockup", "holders", "margin", "reports"}


@router.get("/tree")
def get_tree(db: Session = Depends(get_db)):
    """Full structural tree: 5 layers → 48 sub_industries with company counts."""
    return chainkb_service.get_tree(db)


@router.get("/sub_industries/{group_id}")
def get_sub_industry(group_id: str, db: Session = Depends(get_db)):
    """One sub_industry with its companies (incl. latest quote + finance)."""
    result = chainkb_service.get_sub_industry_detail(db, group_id)
    if result is None:
        raise HTTPException(404, f"Sub-industry '{group_id}' not found")
    return result


@router.get("/companies/{ticker}")
def get_company(ticker: str, db: Session = Depends(get_db)):
    """Company profile: structural + latest quote + finance + concepts + sub_industries."""
    result = chainkb_service.get_company_profile(db, ticker)
    if result is None:
        raise HTTPException(404, f"Company '{ticker}' not found")
    return result


@router.get("/companies/{ticker}/timeseries")
def get_timeseries(
    ticker: str,
    types: str = Query(_DEFAULT_TS_TYPES,
                       description="Comma-separated: lockup,holders,margin,reports"),
    limit: int = Query(30, ge=1, le=100, description="Per-series row cap"),
    db: Session = Depends(get_db),
):
    """Aggregated time-series for a company drill-down."""
    requested = {t.strip() for t in types.split(",") if t.strip()}
    invalid = requested - _VALID_TS_TYPES
    if invalid:
        raise HTTPException(
            400,
            f"Unknown series type(s): {sorted(invalid)}. "
            f"Valid: {sorted(_VALID_TS_TYPES)}",
        )
    if not requested:
        requested = set(_DEFAULT_TS_TYPES.split(","))
    result = chainkb_service.get_company_timeseries(db, ticker, requested, limit)
    if result is None:
        raise HTTPException(404, f"Company '{ticker}' not found")
    return result


@router.get("/search")
def search(
    q: str = Query(..., min_length=1, description="Name or ticker substring"),
    limit: int = Query(20, ge=1, le=50),
    db: Session = Depends(get_db),
):
    """Company search by name (zh/en) or ticker."""
    return chainkb_service.search_companies(db, q, limit)
