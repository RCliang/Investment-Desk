"""Query layer for the v1 chain knowledge base.

Each public function corresponds to one endpoint in routers/chainkb.py.
All functions take a sync `Session` and return plain dicts ready for
JSON serialization.

Design notes:
- Date columns are converted to ISO strings via `_iso()` so the caller
  can `json.dumps()` without TypeError.
- Empty time-series return `[]` (not `null`) for safe frontend chaining.
- Lifecycle filter defaults to 'canonical' for structural entities; the
  KB is the curated surface, 'generated' rows are hidden until promoted.
- N+1 avoidance: `/tree` pre-aggregates company counts via a single
  GROUP BY query instead of per-sub-industry COUNT.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Iterable

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.chain_models import (
    Layer,
    SubIndustry,
    Company,
    Concept,
    SubIndustryCompany,
    CompanyConcept,
    Quote,
    FinanceSnapshot,
    LockupEvent,
    HolderPeriod,
    MarginDaily,
    ResearchReport,
    LIFECYCLE_CANONICAL,
)


# ── Serialization helpers ────────────────────────────────────────────────

def _iso(d: date | datetime | None) -> str | None:
    """date/datetime → 'YYYY-MM-DD' or 'YYYY-MM-DDTHH:MM:SS'. None passthrough."""
    if d is None:
        return None
    if isinstance(d, datetime):
        return d.isoformat(sep="T")
    return d.isoformat()


def _company_brief(c: Company) -> dict:
    """Short company info for lists/search results."""
    return {
        "id": c.id,
        "ticker": c.listing_ticker,
        "name_zh": c.name_zh,
        "name_en": c.name_en or "",
        "market": c.listing_market or "",
        "is_reference": bool(c.is_reference),
        "lifecycle": c.lifecycle,
    }


def _quote_to_dict(q: Quote | None) -> dict | None:
    if q is None:
        return None
    return {
        "price": q.price,
        "last_close": q.last_close,
        "open": q.open,
        "high": q.high,
        "low": q.low,
        "change_amt": q.change_amt,
        "change_pct": q.change_pct,
        "amount_wan": q.amount_wan,
        "turnover_pct": q.turnover_pct,
        "pe_ttm": q.pe_ttm,
        "pe_static": q.pe_static,
        "pb": q.pb,
        "mcap_yi": q.mcap_yi,
        "float_mcap_yi": q.float_mcap_yi,
        "limit_up": q.limit_up,
        "limit_down": q.limit_down,
        "vol_ratio": q.vol_ratio,
        "amplitude_pct": q.amplitude_pct,
        "fetched_at": _iso(q.fetched_at),
        "source": q.source,
    }


def _finance_to_dict(f: FinanceSnapshot | None) -> dict | None:
    if f is None:
        return None
    return {
        "eps": f.eps,
        "bvps": f.bvps,
        "roe_pct": f.roe_pct,
        "net_margin_pct": f.net_margin_pct,
        "gross_margin_pct": f.gross_margin_pct,
        "revenue_yi": f.revenue_yi,
        "net_profit_yi": f.net_profit_yi,
        "debt_ratio_pct": f.debt_ratio_pct,
        "float_shares": f.float_shares,
        "total_shares": f.total_shares,
        "fetched_at": _iso(f.fetched_at),
        "source": f.source,
    }


def _lockup_to_dict(e: LockupEvent) -> dict:
    return {
        "date": _iso(e.date),
        "type": e.type or "",
        "shares_wan": e.shares_wan,
        "ratio_pct": e.ratio_pct,
        "mcap_wan": e.mcap_wan,
        "total_shares_ratio_pct": e.total_shares_ratio_pct,
        "is_upcoming": bool(e.is_upcoming),
    }


def _holder_to_dict(h: HolderPeriod) -> dict:
    return {
        "end_date": _iso(h.end_date),
        "notice_date": _iso(h.notice_date),
        "holder_num": h.holder_num,
        "change_num": h.change_num,
        "change_ratio_pct": h.change_ratio_pct,
        "avg_free_shares": h.avg_free_shares,
        "avg_hold_amt_yi": h.avg_hold_amt_yi,
        "close_price": h.close_price,
    }


def _margin_to_dict(m: MarginDaily) -> dict:
    return {
        "date": _iso(m.date),
        "rzye_yi": m.rzye_yi,
        "rqye_yi": m.rqye_yi,
        "rzrqye_yi": m.rzrqye_yi,
        "rzmre_yi": m.rzmre_yi,
        "rzche_yi": m.rzche_yi,
        "rzjme_yi": m.rzjme_yi,
        "rqmcl_wan": m.rqmcl_wan,
        "rqchl_wan": m.rqchl_wan,
        "rqjmg_wan": m.rqjmg_wan,
        "rzyezb_pct": m.rzyezb_pct,
        "close_price": m.close_price,
        "change_pct": m.change_pct,
    }


def _report_to_dict(r: ResearchReport) -> dict:
    return {
        "publish_date": _iso(r.publish_date),
        "broker": r.broker or "",
        "title": r.title or "",
        "rating": r.rating or "",
        "industry": r.industry or "",
        "info_code": r.info_code or "",
        "predict_this_year_eps": r.predict_this_year_eps,
        "predict_next_year_eps": r.predict_next_year_eps,
        "predict_next_two_year_eps": r.predict_next_two_year_eps,
    }


# ── Internal lookups ─────────────────────────────────────────────────────

def _find_company_by_ticker(db: Session, ticker: str) -> Company | None:
    """Resolve ticker → Company.

    CN markets (SH/SZ/BJ) are tried first to disambiguate from HK/US
    reference tickers that could collide.
    """
    # Prefer CN-listed companies (SH/SZ/BJ) for a 6-digit ticker
    cn = db.execute(
        select(Company).where(
            Company.listing_ticker == ticker,
            Company.listing_market.in_(["SH", "SZ", "BJ"]),
        )
    ).scalar_one_or_none()
    if cn:
        return cn
    # Fallback: any market
    return db.execute(
        select(Company).where(Company.listing_ticker == ticker)
    ).scalar_one_or_none()


# ── Public query functions (one per endpoint) ────────────────────────────

def get_tree(db: Session) -> dict:
    """Full structural tree: layers → sub_industries with company counts."""
    # Pre-aggregate non-reference company counts per sub_industry
    count_rows = db.execute(
        select(
            SubIndustryCompany.sub_industry_id,
            func.count(SubIndustryCompany.id).label("cnt"),
        )
        .join(Company, SubIndustryCompany.company_id == Company.id)
        .where(Company.is_reference.is_(False))
        .group_by(SubIndustryCompany.sub_industry_id)
    ).all()
    counts = {row.sub_industry_id: row.cnt for row in count_rows}

    # Fetch canonical layers ordered by layer_order
    layers = db.execute(
        select(Layer)
        .where(Layer.lifecycle == LIFECYCLE_CANONICAL)
        .order_by(Layer.layer_order)
    ).scalars().all()
    layer_by_id = {l.id: l for l in layers}

    # Fetch canonical sub_industries for those layers
    sub_inds = db.execute(
        select(SubIndustry)
        .where(
            SubIndustry.layer_id.in_(layer_by_id.keys()),
            SubIndustry.lifecycle == LIFECYCLE_CANONICAL,
        )
        .order_by(SubIndustry.group_id)
    ).scalars().all()

    # Group sub_industries by layer
    subs_by_layer: dict[int, list[SubIndustry]] = {}
    for s in sub_inds:
        subs_by_layer.setdefault(s.layer_id, []).append(s)

    return {
        "layers": [
            {
                "code": l.code,
                "name_zh": l.name_zh,
                "name_en": l.name_en,
                "layer_order": l.layer_order,
                "sub_industries": [
                    {
                        "id": s.id,
                        "group_id": s.group_id,
                        "name_zh": s.name_zh,
                        "name_en": s.name_en or "",
                        "company_count": counts.get(s.id, 0),
                    }
                    for s in subs_by_layer.get(l.id, [])
                ],
            }
            for l in layers
        ]
    }


def get_sub_industry_detail(db: Session, group_id: str) -> dict | None:
    """One sub_industry with its companies + latest quote + finance snapshot."""
    sub = db.execute(
        select(SubIndustry).where(SubIndustry.group_id == group_id)
    ).scalar_one_or_none()
    if sub is None:
        return None

    layer = db.execute(
        select(Layer).where(Layer.id == sub.layer_id)
    ).scalar_one_or_none()

    # Companies in this sub_industry
    companies = db.execute(
        select(Company)
        .join(SubIndustryCompany,
              SubIndustryCompany.company_id == Company.id)
        .where(SubIndustryCompany.sub_industry_id == sub.id)
        .order_by(Company.is_reference.asc(),  # CN (False=0) first
                  Company.name_zh)
    ).scalars().all()

    if not companies:
        return {
            "sub_industry": _sub_industry_brief(sub, layer),
            "companies": [],
        }

    tickers = [c.listing_ticker for c in companies if c.listing_ticker]

    # Bulk fetch quotes + finances for all tickers
    quotes_by_t = {}
    finances_by_t = {}
    if tickers:
        q_rows = db.execute(
            select(Quote).where(Quote.ticker.in_(tickers))
        ).scalars().all()
        quotes_by_t = {q.ticker: q for q in q_rows}

        f_rows = db.execute(
            select(FinanceSnapshot).where(FinanceSnapshot.ticker.in_(tickers))
        ).scalars().all()
        finances_by_t = {f.ticker: f for f in f_rows}

    return {
        "sub_industry": _sub_industry_brief(sub, layer),
        "companies": [
            {
                **_company_brief(c),
                "quote": _quote_to_dict(quotes_by_t.get(c.listing_ticker)),
                "finance": _finance_to_dict(finances_by_t.get(c.listing_ticker)),
            }
            for c in companies
        ],
    }


def _sub_industry_brief(sub: SubIndustry, layer: Layer | None) -> dict:
    return {
        "id": sub.id,
        "group_id": sub.group_id,
        "name_zh": sub.name_zh,
        "name_en": sub.name_en or "",
        "layer_code": layer.code if layer else None,
        "layer_name_zh": layer.name_zh if layer else None,
    }


def get_company_profile(db: Session, ticker: str) -> dict | None:
    """Full profile for one company: structural + quote + finance + relations."""
    comp = _find_company_by_ticker(db, ticker)
    if comp is None:
        return None

    quote = db.execute(
        select(Quote).where(Quote.ticker == comp.listing_ticker)
    ).scalar_one_or_none()

    finance = db.execute(
        select(FinanceSnapshot).where(FinanceSnapshot.ticker == comp.listing_ticker)
    ).scalar_one_or_none()

    # Concepts tagged to this company
    concepts = db.execute(
        select(Concept)
        .join(CompanyConcept, CompanyConcept.concept_id == Concept.id)
        .where(CompanyConcept.company_id == comp.id)
        .order_by(Concept.tag_type, Concept.name)
    ).scalars().all()

    # Sub-industries this company belongs to
    sub_inds = db.execute(
        select(SubIndustry, Layer)
        .join(SubIndustryCompany,
              SubIndustryCompany.sub_industry_id == SubIndustry.id)
        .outerjoin(Layer, Layer.id == SubIndustry.layer_id)
        .where(SubIndustryCompany.company_id == comp.id)
        .order_by(SubIndustry.group_id)
    ).all()

    return {
        "company": {
            **_company_brief(comp),
            "description": comp.description or "",
        },
        "quote": _quote_to_dict(quote),
        "finance": _finance_to_dict(finance),
        "concepts": [
            {"name": c.name, "tag_type": c.tag_type}
            for c in concepts
        ],
        "sub_industries": [
            {
                "id": s.id,
                "group_id": s.group_id,
                "name_zh": s.name_zh,
                "name_en": s.name_en or "",
                "layer_code": l.code if l else None,
                "layer_name_zh": l.name_zh if l else None,
            }
            for s, l in sub_inds
        ],
    }


def get_company_timeseries(
    db: Session, ticker: str, types: Iterable[str], limit: int,
) -> dict | None:
    """Aggregated time-series for a company.

    Returns None if the ticker itself is unknown; otherwise returns a dict
    with each requested series (empty list if no rows for that series).
    """
    comp = _find_company_by_ticker(db, ticker)
    if comp is None:
        return None

    tk = comp.listing_ticker
    types_set = {t.strip() for t in types}

    result: dict = {"ticker": tk}

    if "lockup" in types_set:
        rows = db.execute(
            select(LockupEvent)
            .where(LockupEvent.ticker == tk)
            .order_by(LockupEvent.date.desc(), LockupEvent.is_upcoming.desc())
            .limit(limit)
        ).scalars().all()
        result["lockup"] = [_lockup_to_dict(r) for r in rows]
    if "holders" in types_set:
        rows = db.execute(
            select(HolderPeriod)
            .where(HolderPeriod.ticker == tk)
            .order_by(HolderPeriod.end_date.desc())
            .limit(limit)
        ).scalars().all()
        result["holders"] = [_holder_to_dict(r) for r in rows]
    if "margin" in types_set:
        rows = db.execute(
            select(MarginDaily)
            .where(MarginDaily.ticker == tk)
            .order_by(MarginDaily.date.desc())
            .limit(limit)
        ).scalars().all()
        result["margin"] = [_margin_to_dict(r) for r in rows]
    if "reports" in types_set:
        rows = db.execute(
            select(ResearchReport)
            .where(ResearchReport.ticker == tk)
            .order_by(ResearchReport.publish_date.desc())
            .limit(limit)
        ).scalars().all()
        result["reports"] = [_report_to_dict(r) for r in rows]

    return result


def search_companies(db: Session, q: str, limit: int) -> dict:
    """Substring search on name_zh / name_en / listing_ticker.

    Returns canonical + reference matches. Reference companies are flagged
    via `is_reference: true` so the UI can visually distinguish them.
    """
    pattern = f"%{q}%"
    companies = db.execute(
        select(Company)
        .where(
            (Company.name_zh.ilike(pattern))
            | (Company.name_en.ilike(pattern))
            | (Company.listing_ticker.ilike(pattern))
        )
        .order_by(Company.is_reference.asc(), Company.name_zh)
        .limit(limit)
    ).scalars().all()

    if not companies:
        return {"q": q, "results": []}

    # Bulk-fetch sub_industry memberships for all matched companies
    comp_ids = [c.id for c in companies]
    link_rows = db.execute(
        select(SubIndustryCompany.company_id, SubIndustry)
        .join(SubIndustry,
              SubIndustryCompany.sub_industry_id == SubIndustry.id)
        .where(SubIndustryCompany.company_id.in_(comp_ids))
    ).all()

    subs_by_comp: dict[int, list[SubIndustry]] = {}
    for cid, s in link_rows:
        subs_by_comp.setdefault(cid, []).append(s)

    return {
        "q": q,
        "results": [
            {
                **_company_brief(c),
                "sub_industries": [
                    {"group_id": s.group_id, "name_zh": s.name_zh}
                    for s in subs_by_comp.get(c.id, [])
                ],
            }
            for c in companies
        ],
    }
