"""Signal service: scan all A-share tickers, persist + query signals.

Two entry points:
  - scan_all(db, strategy_set, date): recompute today's (or any day's)
    composite signal for every ticker with bars, upsert into chain_signals.
    Idempotent — re-running overwrites via (ticker, date, strategy_set) UQ.
  - get_signals(db, filters): paginated query supporting action / layer /
    sub_industry / ticker filters, with the company name + chain membership
    joined for the frontend table.

Design notes:
  - Each scan pulls every ticker's full history into a DataFrame (so all
    indicators have enough warm-up). 229 tickers × ~1600 bars is ~2 MB in
    memory per ticker, processed serially → ~30-60s total. Acceptable for
    a once-daily post-close job; if it grows, batch by layer.
  - Strategy set is pluggable but currently only 'v1_default' is shipped.
    The schema reserves strategy_set for future A/B comparison.
"""

from __future__ import annotations

import json
import logging
from datetime import date, datetime
from typing import Optional

import pandas as pd
from sqlalchemy import select, func, and_, case
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.models.chain_models import (
    DailyBar, Signal, Company, SubIndustryCompany, SubIndustry, Layer,
)
from . import indicators
from . import scoring

log = logging.getLogger(__name__)

# Cap history loaded per ticker. 1000 bars ≈ 4 years; enough warm-up for
# MA60 / ATR14 / 60-day turnover percentile without over-fetching.
HISTORY_BARS = 1000


def _load_bars_df(db: Session, ticker: str, limit: int = HISTORY_BARS) -> Optional[pd.DataFrame]:
    """Load a ticker's most-recent daily bars into a DataFrame sorted ascending.

    We want the *latest* `limit` bars (so indicators see current context),
    not the earliest. SQLite LIMIT applies before ORDER BY would reverse it,
    so we subquery: select newest `limit` rows descending, then flip to
    ascending for the indicators layer (which assumes chronological order).
    """
    subq = (
        select(DailyBar.date, DailyBar.open, DailyBar.high, DailyBar.low,
               DailyBar.close, DailyBar.volume, DailyBar.amount, DailyBar.turnover_pct)
        .where(DailyBar.ticker == ticker)
        .order_by(DailyBar.date.desc())
        .limit(limit)
    ).subquery()
    rows = db.execute(
        select(subq).order_by(subq.c.date.asc())
    ).all()
    if not rows:
        return None
    df = pd.DataFrame(rows, columns=["date", "open", "high", "low", "close",
                                     "volume", "amount", "turnover_pct"])
    df["date"] = df["date"].astype(str)
    return df


def scan_all(db: Session, strategy_set: str = "v1_default",
             target_date: Optional[date] = None) -> dict:
    """Recompute and persist signals for every CN ticker.

    By default computes the *latest* available day's signal per ticker. Pass
    target_date to score a specific historical day (backfill mode).

    Returns a summary dict {scanned, buy, sell, hold, skipped, elapsed_s}.
    """
    started = datetime.utcnow()
    if target_date is None:
        target_date = _latest_bar_date(db)

    card = scoring.get_card(strategy_set)  # v1_default or trend_follow

    # All tickers that have bars.
    tickers = [r[0] for r in db.execute(
        select(DailyBar.ticker).distinct().order_by(DailyBar.ticker.asc())
    ).all()]

    counts = {"BUY": 0, "SELL": 0, "HOLD": 0, "skipped": 0}
    upsert_rows: list[dict] = []

    for i, ticker in enumerate(tickers, 1):
        df = _load_bars_df(db, ticker)
        if df is None or len(df) < 60:  # need at least MA60 warm-up
            counts["skipped"] += 1
            continue
        try:
            enriched = indicators.enrich(df)
            latest = card.latest(enriched)
        except Exception as e:
            log.warning("scan %s failed: %s", ticker, e)
            counts["skipped"] += 1
            continue

        # Use the bar's actual last date (not today) so signals align with
        # the data we have. The target_date filter is for batch backfill.
        sig_date = _parse_date(latest.get("date")) or target_date
        if target_date is not None and sig_date != target_date:
            # Ticker's latest bar isn't the target date (e.g. suspended);
            # still record under its own latest date.
            pass

        upsert_rows.append({
            "ticker": ticker,
            "date": sig_date,
            "strategy_set": strategy_set,
            "composite_score": latest["composite_score"],
            "action": latest["action"],
            "position_pct": latest["position_pct"],
            "stop_loss_price": latest["stop_loss_price"],
            "target_price": latest["target_price"],
            "detail_json": json.dumps(latest["detail"], ensure_ascii=False),
        })
        counts[latest["action"]] += 1

        # Batch upsert every 50 to keep statements manageable.
        if len(upsert_rows) >= 50:
            _upsert_signals(db, upsert_rows)
            upsert_rows.clear()

        if i % 50 == 0:
            log.info("scan progress: %d/%d (BUY=%d SELL=%d HOLD=%d skip=%d)",
                     i, len(tickers), counts["BUY"], counts["SELL"],
                     counts["HOLD"], counts["skipped"])

    if upsert_rows:
        _upsert_signals(db, upsert_rows)
    db.commit()

    elapsed = (datetime.utcnow() - started).total_seconds()
    log.info("scan_all done: %d tickers, BUY=%d SELL=%d HOLD=%d skip=%d (%.1fs)",
             len(tickers), counts["BUY"], counts["SELL"], counts["HOLD"],
             counts["skipped"], elapsed)
    return {
        "scanned": len(tickers),
        "date": str(target_date),
        "strategy_set": strategy_set,
        **counts,
        "elapsed_s": round(elapsed, 1),
    }


def _upsert_signals(db: Session, rows: list[dict]) -> None:
    """Idempotent upsert into chain_signals on (ticker, date, strategy_set)."""
    if not rows:
        return
    stmt = sqlite_insert(Signal).values(rows)
    update_cols = {
        "composite_score": stmt.excluded.composite_score,
        "action": stmt.excluded.action,
        "position_pct": stmt.excluded.position_pct,
        "stop_loss_price": stmt.excluded.stop_loss_price,
        "target_price": stmt.excluded.target_price,
        "detail_json": stmt.excluded.detail_json,
    }
    stmt = stmt.on_conflict_do_update(
        index_elements=["ticker", "date", "strategy_set"],
        set_=update_cols,
    )
    db.execute(stmt)


def _latest_bar_date(db: Session) -> date:
    """Most recent bar date across all tickers (the 'today' for signals)."""
    d = db.execute(select(func.max(DailyBar.date))).scalar_one()
    return d or date.today()


def _parse_date(s) -> Optional[date]:
    if s is None or s == "":
        return None
    try:
        return date.fromisoformat(str(s)[:10])
    except ValueError:
        return None


# ── Query layer (for the API) ──────────────────────────────────────────────

def get_signals(
    db: Session,
    action: Optional[str] = None,
    layer: Optional[str] = None,
    sub_industry: Optional[str] = None,
    ticker: Optional[str] = None,
    strategy_set: str = "v1_default",
    target_date: Optional[date] = None,
    limit: int = 100,
    offset: int = 0,
    min_score: Optional[float] = None,
) -> dict:
    """Paginated signal list with company + chain membership joined.

    Returns {total, date, items: [...]} where each item has:
        ticker, name, action, composite_score, position_pct,
        stop_loss_price, target_price, layer_code, layer_name,
        sub_industry_id, sub_industry_name, detail
    """
    # Default to latest signal date if not specified.
    if target_date is None:
        target_date = _latest_signal_date(db, strategy_set)

    # Base query: signals joined to companies (for name).
    q = (
        select(
            Signal.ticker,
            Signal.date,
            Signal.composite_score,
            Signal.action,
            Signal.position_pct,
            Signal.stop_loss_price,
            Signal.target_price,
            Signal.detail_json,
            Company.name_zh.label("name"),
            Company.listing_market,
        )
        .outerjoin(Company, Company.listing_ticker == Signal.ticker)
        .where(Signal.strategy_set == strategy_set)
    )
    if target_date is not None:
        q = q.where(Signal.date == target_date)
    if action:
        q = q.where(Signal.action == action)
    if ticker:
        q = q.where(Signal.ticker == ticker)
    if min_score is not None:
        q = q.where(Signal.composite_score >= min_score)

    # Layer / sub_industry filter requires the chain join. We pre-compute
    # the set of qualifying tickers to keep the query flat.
    if layer or sub_industry:
        sq = (
            select(SubIndustryCompany.company_id.label("cid"))
            .join(SubIndustry, SubIndustry.id == SubIndustryCompany.sub_industry_id)
        )
        if sub_industry:
            sq = sq.where(SubIndustry.group_id == sub_industry)
        if layer:
            sq = sq.join(Layer, Layer.id == SubIndustry.layer_id).where(Layer.code == layer)
        qualifier_q = (
            select(Company.listing_ticker)
            .where(Company.id.in_(sq))
        )
        qualifying = [r[0] for r in db.execute(qualifier_q).all()]
        if not qualifying:
            return {"total": 0, "date": str(target_date) if target_date else None, "items": []}
        q = q.where(Signal.ticker.in_(qualifying))

    # Count + page.
    count_q = select(func.count()).select_from(q.subquery())
    total = db.execute(count_q).scalar_one()

    # Sort: BUY first by score desc, then SELL by score asc, then HOLD.
    q = q.order_by(
        case({"BUY": 0, "SELL": 1, "HOLD": 2}, value=Signal.action),
        func.abs(Signal.composite_score).desc(),
    )
    rows = db.execute(q.offset(offset).limit(limit)).all()

    # Enrich each row with chain membership (one pass).
    items = []
    for r in rows:
        chains = _ticker_chain(db, r.ticker) if r.name else []
        items.append({
            "ticker": r.ticker,
            "name": r.name or "",
            "market": r.listing_market,
            "date": str(r.date),
            "action": r.action,
            "composite_score": round(r.composite_score, 3),
            "position_pct": round(r.position_pct, 3) if r.position_pct is not None else 0,
            "stop_loss_price": r.stop_loss_price,
            "target_price": r.target_price,
            "chains": chains,
            "detail": json.loads(r.detail_json) if r.detail_json else {},
        })

    return {
        "total": total,
        "date": str(target_date) if target_date else None,
        "strategy_set": strategy_set,
        "items": items,
    }


def _latest_signal_date(db: Session, strategy_set: str) -> Optional[date]:
    d = db.execute(
        select(func.max(Signal.date)).where(Signal.strategy_set == strategy_set)
    ).scalar_one_or_none()
    return d


def _ticker_chain(db: Session, ticker: str) -> list[dict]:
    """Return the ticker's sub_industry memberships (group_id + layer)."""
    rows = db.execute(
        select(
            SubIndustry.group_id, SubIndustry.name_zh,
            Layer.code, Layer.name_zh,
        )
        .select_from(Company)
        .join(SubIndustryCompany, SubIndustryCompany.company_id == Company.id)
        .join(SubIndustry, SubIndustry.id == SubIndustryCompany.sub_industry_id)
        .join(Layer, Layer.id == SubIndustry.layer_id)
        .where(Company.listing_ticker == ticker)
    ).all()
    return [
        {"sub_industry_id": r.group_id, "sub_industry_name": r.name_zh,
         "layer_code": r.code, "layer_name": r.name_zh}
        for r in rows
    ]


def get_signal_detail(db: Session, ticker: str,
                      strategy_set: str = "v1_default") -> Optional[dict]:
    """Latest signal for one ticker, with full strategy detail + recent bars."""
    row = db.execute(
        select(Signal)
        .where(Signal.ticker == ticker, Signal.strategy_set == strategy_set)
        .order_by(Signal.date.desc())
        .limit(1)
    ).scalar_one_or_none()
    if row is None:
        return None

    company = db.execute(
        select(Company.name_zh, Company.listing_market)
        .where(Company.listing_ticker == ticker)
    ).first()

    return {
        "ticker": ticker,
        "name": company.name_zh if company else "",
        "market": company.listing_market if company else None,
        "date": str(row.date),
        "action": row.action,
        "composite_score": round(row.composite_score, 4),
        "position_pct": round(row.position_pct, 3),
        "stop_loss_price": row.stop_loss_price,
        "target_price": row.target_price,
        "detail": json.loads(row.detail_json) if row.detail_json else {},
        "chains": _ticker_chain(db, ticker),
    }
