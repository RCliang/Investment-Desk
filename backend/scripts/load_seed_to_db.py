"""Idempotent loader: backfill JSONs → chain_* SQLite tables.

Reads aichainmap_seed.json (structural entities) + 6 backfill JSON files
(time-series data) and upserts them into the v1 chain tables defined in
app/models/chain_models.py.

Order matters: structural entities must be loaded before junctions and
time-series tables, because time-series rows reference tickers that must
already exist in chain_companies (FK-like discipline, though we don't
enforce hard FKs to keep SQLite upserts simple).

Usage:
    python -m app.scripts.load_seed_to_db      # from backend/
    python scripts/load_seed_to_db.py           # from backend/ (adds path)

Idempotency:
    All writes use SQLite ON CONFLICT DO UPDATE (upsert). Running twice
    with the same JSON files yields the same final state.

V1 scope: 234 CN tickers + ~30 HK/US reference companies.
"""

from __future__ import annotations

import json
import sys
from datetime import date, datetime
from pathlib import Path

# Make `app.*` importable when run as `python scripts/load_seed_to_db.py`
BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from sqlalchemy import select, func
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from app.db import SessionLocal, sync_engine, Base
from app.models import chain_models  # noqa: F401  (register tables on Base)
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

DATA_DIR = BACKEND_ROOT / "data"

# Layer order → Roman code. Keep in sync with CONTEXT.md §Layer seed set.
LAYER_CODES = {
    1: "I",
    2: "II",
    3: "III",
    4: "IV",
    5: "V",
}


# ── Helpers ───────────────────────────────────────────────────────────────

def _load(name: str) -> dict:
    path = DATA_DIR / name
    if not path.exists():
        raise SystemExit(f"backfill JSON not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _derive_cn_market(ticker: str) -> str:
    """6-digit CN ticker → exchange code."""
    if ticker.startswith(("6", "9")):
        return "SH"
    if ticker.startswith("8"):
        return "BJ"
    return "SZ"


def _classify_concept(name: str) -> str:
    """Heuristic tag_type per CONTEXT.md §Concept classification."""
    if name.endswith("板块") or "板块" in name:
        return "region"
    if "概念" in name:
        return "concept"
    # Heuristic: index-like tags
    index_markers = ("HS300", "上证50", "上证180", "沪深300", "中证500",
                     "深成500", "MSCI", "富时罗素", "标准普尔", "央视50")
    if any(m in name for m in index_markers):
        return "index"
    return "industry"


def _upsert_many(session, model, rows: list[dict], conflict_cols: list[str]) -> int:
    """Bulk SQLite upsert. `rows` must be non-empty and uniform in keys.

    Falls back to ON CONFLICT DO NOTHING when the row has no columns outside
    conflict_cols (pure junction tables).
    """
    if not rows:
        return 0
    stmt = sqlite_insert(model).values(rows)
    update_cols = {
        col: getattr(stmt.excluded, col)
        for col in rows[0].keys()
        if col not in conflict_cols
    }
    if update_cols:
        stmt = stmt.on_conflict_do_update(
            index_elements=conflict_cols,
            set_=update_cols,
        )
    else:
        # Pure junction table — nothing to update, just skip duplicates.
        stmt = stmt.on_conflict_do_nothing(index_elements=conflict_cols)
    session.execute(stmt)
    return len(rows)


def _count(session, model) -> int:
    return session.execute(select(func.count()).select_from(model)).scalar_one()


# ── Loader stages (one per JSON file) ─────────────────────────────────────

def load_seed_structural(session) -> dict:
    """Load aichainmap_seed.json → Layer + SubIndustry + Company + SubIndustryCompany.

    Seed data is canonical (lifecycle='canonical') since it is the human-curated
    aichainmap reference. HK/US reference peers go into chain_companies with
    is_reference=True.
    """
    seed = _load("aichainmap_seed.json")
    stats = {"layers": 0, "sub_industries": 0, "companies_new": 0,
             "companies_existing": 0, "links": 0}

    # Layer codes are a closed set per ADR-0002
    layer_id_by_order: dict[int, int] = {}

    for L in seed["layers"]:
        order = L["layer_order"]
        code = LAYER_CODES.get(order)
        if code is None:
            raise SystemExit(f"unknown layer_order {order} in seed")

        # Upsert Layer by code (unique)
        existing = session.execute(
            select(Layer).where(Layer.code == code)
        ).scalar_one_or_none()
        if existing:
            existing.name_zh = L["name_zh"]
            existing.name_en = L["name_en"]
            existing.layer_order = order
            layer = existing
        else:
            layer = Layer(
                code=code,
                name_zh=L["name_zh"],
                name_en=L["name_en"],
                layer_order=order,
                lifecycle=LIFECYCLE_CANONICAL,
                description=L.get("description", ""),
            )
            session.add(layer)
            session.flush()
            stats["layers"] += 1
        layer_id_by_order[order] = layer.id

        # SubIndustries under this Layer
        for s in L["sub_industries"]:
            group_id = s["group_id"]
            existing_sub = session.execute(
                select(SubIndustry).where(SubIndustry.group_id == group_id)
            ).scalar_one_or_none()
            if existing_sub:
                existing_sub.name_zh = s["name_zh"]
                existing_sub.layer_id = layer.id
                sub = existing_sub
            else:
                sub = SubIndustry(
                    group_id=group_id,
                    layer_id=layer.id,
                    name_zh=s["name_zh"],
                    name_en=s.get("name_en", ""),
                    lifecycle=LIFECYCLE_CANONICAL,
                )
                session.add(sub)
                session.flush()
                stats["sub_industries"] += 1

            # Companies under this SubIndustry
            for c in s["visible_companies"]:
                market_flag = c.get("market", "CN")
                raw_ticker = str(c["ticker"])
                name = c["name"]

                if market_flag == "CN":
                    listing_market = _derive_cn_market(raw_ticker)
                    listing_ticker = raw_ticker
                    is_reference = False
                elif market_flag == "HK":
                    listing_market = "HK"
                    listing_ticker = raw_ticker
                    is_reference = True
                elif market_flag == "US":
                    listing_market = "US"
                    listing_ticker = raw_ticker
                    is_reference = True
                else:
                    listing_market = market_flag
                    listing_ticker = raw_ticker
                    is_reference = True

                # Lookup or create Company by (listing_market, listing_ticker)
                comp = session.execute(
                    select(Company).where(
                        Company.listing_market == listing_market,
                        Company.listing_ticker == listing_ticker,
                    )
                ).scalar_one_or_none()
                if comp:
                    comp.name_zh = name
                    comp.is_reference = is_reference
                    # Seed carries canonical status; promote generated→canonical
                    if comp.lifecycle != LIFECYCLE_CANONICAL:
                        comp.lifecycle = LIFECYCLE_CANONICAL
                    stats["companies_existing"] += 1
                else:
                    comp = Company(
                        name_zh=name,
                        listing_market=listing_market,
                        listing_ticker=listing_ticker,
                        is_reference=is_reference,
                        lifecycle=LIFECYCLE_CANONICAL,
                    )
                    session.add(comp)
                    session.flush()
                    stats["companies_new"] += 1

                # Junction: SubIndustryCompany
                link_exists = session.execute(
                    select(SubIndustryCompany).where(
                        SubIndustryCompany.sub_industry_id == sub.id,
                        SubIndustryCompany.company_id == comp.id,
                    )
                ).scalar_one_or_none()
                if not link_exists:
                    session.add(SubIndustryCompany(
                        sub_industry_id=sub.id,
                        company_id=comp.id,
                        role="member",
                    ))
                    stats["links"] += 1

    return stats


def load_quotes(session) -> int:
    """backfill_tencent_quotes.json → Quote (one row per ticker, latest snapshot)."""
    data = _load("backfill_tencent_quotes.json")
    rows = []
    for q in data.get("quotes", []):
        rows.append({
            "ticker": q["ticker"],
            "name": q.get("name", ""),
            "price": q.get("price"),
            "last_close": q.get("last_close"),
            "open": q.get("open"),
            "high": q.get("high"),
            "low": q.get("low"),
            "change_amt": q.get("change_amt"),
            "change_pct": q.get("change_pct"),
            "amount_wan": q.get("amount_wan"),
            "turnover_pct": q.get("turnover_pct"),
            "pe_ttm": q.get("pe_ttm"),
            "pe_static": q.get("pe_static"),
            "pb": q.get("pb"),
            "mcap_yi": q.get("mcap_yi"),
            "float_mcap_yi": q.get("float_mcap_yi"),
            "limit_up": q.get("limit_up"),
            "limit_down": q.get("limit_down"),
            "vol_ratio": q.get("vol_ratio"),
            "amplitude_pct": q.get("amplitude_pct"),
            "source": "tencent",
        })
    return _upsert_many(session, Quote, rows, ["ticker"])


def load_finance(session) -> int:
    """backfill_mootdx_finance.json → FinanceSnapshot (one row per ticker)."""
    data = _load("backfill_mootdx_finance.json")
    rows = []
    for f in data.get("snapshots", []):
        # mootdx returns share counts as absolute integers; schema wants 万股.
        total_shares_raw = f.get("total_shares") or 0
        float_shares_raw = f.get("float_shares") or 0
        rows.append({
            "ticker": f["ticker"],
            "eps": f.get("eps"),
            "bvps": f.get("bvps"),
            "roe_pct": f.get("roe_pct"),
            "net_margin_pct": f.get("net_margin_pct"),
            "gross_margin_pct": f.get("gross_margin_pct"),
            "revenue_yi": f.get("revenue_yi"),
            "net_profit_yi": f.get("net_profit_yi"),
            "debt_ratio_pct": f.get("debt_ratio_pct"),
            "float_shares": float_shares_raw / 1e4 if float_shares_raw else None,
            "total_shares": total_shares_raw / 1e4 if total_shares_raw else None,
            "source": "mootdx",
        })
    return _upsert_many(session, FinanceSnapshot, rows, ["ticker"])


def load_concept_blocks(session) -> tuple[int, int, int]:
    """backfill_em_concept_blocks.json → Concept + CompanyConcept.

    Returns (concepts_new, concepts_existing, links).
    """
    data = _load("backfill_em_concept_blocks.json")
    concepts_new = 0
    concepts_existing = 0
    links = 0

    # Build ticker → company_id cache for CN companies
    cn_tickers = list(data.get("tickers", {}).keys())
    comp_cache: dict[str, int] = {}
    if cn_tickers:
        rows = session.execute(
            select(Company.id, Company.listing_ticker).where(
                Company.listing_ticker.in_(cn_tickers),
                Company.listing_market.in_(["SH", "SZ", "BJ"]),
            )
        ).all()
        for cid, ticker in rows:
            comp_cache[ticker] = cid

    # First pass: upsert all Concept rows
    concept_id_cache: dict[str, int] = {}
    for ticker, payload in data.get("tickers", {}).items():
        if payload.get("total_boards", 0) == 0:
            continue
        for board in payload.get("boards", []):
            name = board.get("name", "").strip()
            if not name:
                continue
            if name in concept_id_cache:
                continue
            existing = session.execute(
                select(Concept).where(Concept.name == name)
            ).scalar_one_or_none()
            if existing:
                concept_id_cache[name] = existing.id
                concepts_existing += 1
            else:
                c = Concept(
                    name=name,
                    tag_type=_classify_concept(name),
                    lifecycle=LIFECYCLE_CANONICAL,
                )
                session.add(c)
                session.flush()
                concept_id_cache[name] = c.id
                concepts_new += 1

    # Second pass: insert CompanyConcept links (bulk)
    link_rows = []
    seen_links: set[tuple[int, int]] = set()
    for ticker, payload in data.get("tickers", {}).items():
        company_id = comp_cache.get(ticker)
        if not company_id:
            continue
        if payload.get("total_boards", 0) == 0:
            continue
        for board in payload.get("boards", []):
            name = board.get("name", "").strip()
            concept_id = concept_id_cache.get(name)
            if not concept_id:
                continue
            key = (company_id, concept_id)
            if key in seen_links:
                continue
            seen_links.add(key)
            link_rows.append({"company_id": company_id, "concept_id": concept_id})

    if link_rows:
        _upsert_many(session, CompanyConcept, link_rows,
                     ["company_id", "concept_id"])
        links = len(link_rows)

    return concepts_new, concepts_existing, links


def load_lockup(session) -> int:
    """backfill_em_lockup_expiry.json → LockupEvent."""
    data = _load("backfill_em_lockup_expiry.json")
    rows = []
    for ticker, payload in data.get("tickers", {}).items():
        # 'history' events are past; mark is_upcoming=False
        for ev in payload.get("history", []):
            rows.append({
                "ticker": ticker,
                "date": _to_date(ev.get("date")),
                "type": ev.get("type", "") or "",
                "shares_wan": ev.get("shares_wan"),
                "ratio_pct": ev.get("ratio_pct"),
                "mcap_wan": ev.get("mcap_wan"),
                "total_shares_ratio_pct": ev.get("total_shares_ratio_pct"),
                "is_upcoming": False,
            })
        # 'upcoming' events are forward-looking
        for ev in payload.get("upcoming", []):
            rows.append({
                "ticker": ticker,
                "date": _to_date(ev.get("date")),
                "type": ev.get("type", "") or "",
                "shares_wan": ev.get("shares_wan"),
                "ratio_pct": ev.get("ratio_pct"),
                "mcap_wan": ev.get("mcap_wan"),
                "total_shares_ratio_pct": ev.get("total_shares_ratio_pct"),
                "is_upcoming": True,
            })
    # Dedupe on (ticker, date, type) keeping the last occurrence
    deduped: dict[tuple, dict] = {}
    for r in rows:
        key = (r["ticker"], r["date"], r["type"])
        deduped[key] = r
    return _upsert_many(session, LockupEvent, list(deduped.values()),
                        ["ticker", "date", "type"])


def load_holder_num(session) -> int:
    """backfill_em_holder_num.json → HolderPeriod."""
    data = _load("backfill_em_holder_num.json")
    rows = []
    for ticker, payload in data.get("tickers", {}).items():
        for p in payload.get("history", []):
            rows.append({
                "ticker": ticker,
                "end_date": _to_date(p.get("end_date")),
                "notice_date": _to_date(p.get("notice_date")),
                "holder_num": p.get("holder_num"),
                "change_num": p.get("change_num"),
                "change_ratio_pct": p.get("change_ratio_pct"),
                "avg_free_shares": p.get("avg_free_shares"),
                "avg_hold_amt_yi": p.get("avg_hold_amt_yi"),
                "close_price": p.get("close_price"),
            })
    return _upsert_many(session, HolderPeriod, rows, ["ticker", "end_date"])


def load_margin(session) -> int:
    """backfill_em_margin_trading.json → MarginDaily."""
    data = _load("backfill_em_margin_trading.json")
    rows = []
    for ticker, payload in data.get("tickers", {}).items():
        if not payload.get("margin_eligible"):
            continue
        for d in payload.get("history", []):
            rows.append({
                "ticker": ticker,
                "date": _to_date(d.get("date")),
                "rzye_yi": d.get("rzye_yi"),
                "rqye_yi": d.get("rqye_yi"),
                "rzrqye_yi": d.get("rzrqye_yi"),
                "rzmre_yi": d.get("rzmre_yi"),
                "rzche_yi": d.get("rzche_yi"),
                "rzjme_yi": d.get("rzjme_yi"),
                "rqmcl_wan": d.get("rqmcl_wan"),
                "rqchl_wan": d.get("rqchl_wan"),
                "rqjmg_wan": d.get("rqjmg_wan"),
                "rzyezb_pct": d.get("rzyezb_pct"),
                "close_price": d.get("close_price"),
                "change_pct": d.get("change_pct"),
            })
    return _upsert_many(session, MarginDaily, rows, ["ticker", "date"])


def load_reports(session) -> int:
    """backfill_em_reports.json → ResearchReport."""
    data = _load("backfill_em_reports.json")
    rows = []
    for ticker, payload in data.get("tickers", {}).items():
        for r in payload.get("reports", []):
            rows.append({
                "ticker": ticker,
                "publish_date": _to_date(r.get("publish_date")),
                "broker": r.get("broker", "") or "",
                "title": r.get("title", "") or "",
                "rating": r.get("rating", "") or "",
                "industry": r.get("industry", "") or "",
                "info_code": r.get("info_code", "") or "",
                "predict_this_year_eps": _safe_float(r.get("predict_this_year_eps")),
                "predict_next_year_eps": _safe_float(r.get("predict_next_year_eps")),
                "predict_next_two_year_eps": _safe_float(r.get("predict_next_two_year_eps")),
            })
    return _upsert_many(session, ResearchReport, rows, ["ticker", "info_code"])


def _safe_float(v):
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _to_date(v):
    """Accept 'YYYY-MM-DD' / 'YYYY-MM-DDTHH:MM:SS' / datetime / date / '' → date | None."""
    if v is None or v == "":
        return None
    if isinstance(v, date) and not isinstance(v, datetime):
        return v
    if isinstance(v, datetime):
        return v.date()
    s = str(v).strip()
    if not s:
        return None
    # Trim fractional seconds / time portion if present
    s = s.split("T")[0].split(" ")[0]
    try:
        return date.fromisoformat(s)
    except ValueError:
        return None


# ── Main ─────────────────────────────────────────────────────────────────

def main():
    # Ensure tables exist (no-op if already present)
    Base.metadata.create_all(sync_engine)

    print("=" * 72)
    print("InvestLens v1 — seed loader")
    print("=" * 72)
    print(f"  DB: {sync_engine.url.database}")
    print()

    with SessionLocal() as session:
        # Structural first
        s = load_seed_structural(session)
        print(f"  [seed] layers={s['layers']} sub_industries={s['sub_industries']} "
              f"companies_new={s['companies_new']} "
              f"companies_existing={s['companies_existing']} "
              f"links={s['links']}")

        # Time-series
        n_q = load_quotes(session)
        print(f"  [quotes] upserted={n_q}")

        n_f = load_finance(session)
        print(f"  [finance] upserted={n_f}")

        c_new, c_exist, n_links = load_concept_blocks(session)
        print(f"  [concepts] new={c_new} existing={c_exist} "
              f"company_concept_links={n_links}")

        n_l = load_lockup(session)
        print(f"  [lockup] upserted={n_l}")

        n_h = load_holder_num(session)
        print(f"  [holder_num] upserted={n_h}")

        n_m = load_margin(session)
        print(f"  [margin] upserted={n_m}")

        n_r = load_reports(session)
        print(f"  [reports] upserted={n_r}")

        session.commit()

    # Post-load table counts
    print()
    print("  Final table row counts:")
    with SessionLocal() as session:
        for model in (Layer, SubIndustry, Company, Concept,
                      SubIndustryCompany, CompanyConcept,
                      Quote, FinanceSnapshot, LockupEvent, HolderPeriod,
                      MarginDaily, ResearchReport):
            n = _count(session, model)
            print(f"    {model.__tablename__:<32} {n:>6}")

    print()
    print("Done.")


if __name__ == "__main__":
    main()
