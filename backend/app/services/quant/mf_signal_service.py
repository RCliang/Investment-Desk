"""Multi-factor signal service: generate & persist portfolio recommendations.

This is the production signal generator for the cross-sectional multi-factor
trend-following strategy. Unlike signal_service.scan_all (which scores each
ticker independently), this service:

  1. Loads ALL tickers' bars into a cross-sectional panel
  2. Runs the full multi-factor pipeline (factors → neutralize → IC → composite)
  3. Ranks all stocks by composite score
  4. Selects top-N for the recommended portfolio
  5. Persists results into chain_mf_signals for the frontend / daily alert

Called by:
  - APScheduler job (17:30 daily, after data refresh at 16:30 + signal scan at 17:00)
  - HTTP endpoint POST /api/quant/multi-factor/scan (admin-gated)
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime
from typing import Optional

import numpy as np
import pandas as pd
from sqlalchemy import select, func, desc, and_
from sqlalchemy.orm import Session

from app.models.chain_models import DailyBar, MfSignal, Company
from app.services.quant.factor_model import MultiFactorEngine
from app.services.quant.signal_service import _load_bars_df

log = logging.getLogger(__name__)


def scan_mf_signals(
    db: Session,
    holding_period: int = 20,
    top_n: int = 20,
    max_weight: float = 0.10,
) -> dict:
    """Run the multi-factor engine and persist today's portfolio recommendation.

    Returns a summary dict:
      {date, scanned, selected, ic_summary, top_holdings, elapsed_s}

    This is idempotent — re-running on the same date overwrites all rows
    for that date via upsert on (ticker, date).
    """
    started = datetime.utcnow()

    # Step 1: Load all tickers' bars.
    tickers = [r[0] for r in db.execute(
        select(DailyBar.ticker).distinct().order_by(DailyBar.ticker.asc())
    ).all()]

    bars: dict[str, pd.DataFrame] = {}
    for t in tickers:
        df = _load_bars_df(db, t, limit=600)
        if df is not None and len(df) >= 80:
            bars[t] = df

    if len(bars) < 20:
        raise ValueError(f"Insufficient tickers ({len(bars)}), need ≥20 for cross-sectional ranking")

    log.info("MF scan: loaded %d tickers", len(bars))

    # Step 2: Run the multi-factor engine.
    engine = MultiFactorEngine(
        holding_period=holding_period,
        top_n=top_n,
        max_weight=max_weight,
    )
    result = engine.run(bars)

    composite = result["composite"]
    factor_panels = result["factor_panels"]
    portfolios = result["portfolios"]
    ic_summary = result["ic_summary"]
    config = result["config"]

    # Step 3: Get the latest date with valid composite scores.
    valid_dates = composite.dropna(how="all").index
    if len(valid_dates) == 0:
        raise ValueError("No valid composite scores computed")
    latest_date = valid_dates[-1]
    latest_scores = composite.loc[latest_date].dropna().sort_values(ascending=False)

    # Get the portfolio for this date (or the nearest available).
    portfolio = portfolios.get(latest_date, {})
    if not portfolio and portfolios:
        portfolio = portfolios[sorted(portfolios.keys())[-1]]

    log.info("MF scan: latest_date=%s, %d ranked, %d selected",
             latest_date, len(latest_scores), len(portfolio))

    # Step 4: Build factor score details for each ticker.
    factor_details = {}
    for name, panel in factor_panels.items():
        if latest_date in panel.index:
            factor_details[name] = panel.loc[latest_date]

    # Step 5: Upsert all tickers' rankings into chain_mf_signals.
    sig_date = date.fromisoformat(str(latest_date)[:10])
    upsert_rows = []
    rank = 0
    for ticker, score in latest_scores.items():
        rank += 1
        is_selected = ticker in portfolio
        weight = portfolio.get(ticker, 0.0)

        # Factor-level scores for this ticker.
        f_scores = {}
        for fname, fvals in factor_details.items():
            if ticker in fvals.index:
                f_scores[fname] = round(float(fvals[ticker]), 4)

        upsert_rows.append({
            "ticker": ticker,
            "date": sig_date,
            "rank": rank,
            "composite_score": round(float(score), 6),
            "is_selected": is_selected,
            "weight": round(float(weight), 4),
            "factor_scores_json": json.dumps(f_scores, ensure_ascii=False),
            "ic_summary_json": json.dumps(ic_summary, ensure_ascii=False),
            "config_json": json.dumps(config, ensure_ascii=False),
        })

    # Batch upsert.
    _upsert_mf_signals(db, upsert_rows)
    db.commit()

    elapsed = (datetime.utcnow() - started).total_seconds()
    log.info("MF scan done: %d ranked, %d selected, %.1fs",
             len(upsert_rows), len(portfolio), elapsed)

    # Build summary (top holdings with company names).
    top_holdings = _enrich_with_names(db, list(portfolio.keys())[:10])
    for h in top_holdings:
        h["weight"] = round(float(portfolio.get(h["ticker"], 0)), 4)

    return {
        "date": str(sig_date),
        "scanned": len(bars),
        "ranked": len(upsert_rows),
        "selected": len(portfolio),
        "ic_summary": ic_summary,
        "top_holdings": top_holdings,
        "config": config,
        "elapsed_s": round(elapsed, 1),
    }


def _upsert_mf_signals(db: Session, rows: list[dict]) -> None:
    """Idempotent upsert into chain_mf_signals on (ticker, date)."""
    if not rows:
        return
    # Delete existing rows for this date first (in case stock count changed).
    sig_dates = {r["date"] for r in rows}
    for d in sig_dates:
        db.query(MfSignal).filter(MfSignal.date == d).delete()
    # Bulk insert.
    db.bulk_insert_mappings(MfSignal, rows)


def _enrich_with_names(db: Session, tickers: list[str]) -> list[dict]:
    """Join ticker → company name for display."""
    if not tickers:
        return []
    rows = db.execute(
        select(Company.listing_ticker, Company.name_zh)
        .where(Company.listing_ticker.in_(tickers))
    ).all()
    name_map = {r[0]: r[1] for r in rows}

    return [{"ticker": t, "name": name_map.get(t, "")} for t in tickers]


# ── Query layer (for the API) ──────────────────────────────────────────────

def get_latest_portfolio(db: Session, top_only: bool = True) -> dict:
    """Get the latest multi-factor portfolio recommendation.

    Returns:
      {
        "date": "2026-07-28",
        "holdings": [{ticker, name, rank, weight, composite_score, factor_scores}, ...],
        "ic_summary": {...},
        "config": {...},
      }
    """
    latest_date = db.execute(
        select(func.max(MfSignal.date))
    ).scalar_one()

    if latest_date is None:
        return {"date": None, "holdings": [], "ic_summary": {}, "config": {}}

    query = db.query(MfSignal).filter(MfSignal.date == latest_date)
    if top_only:
        query = query.filter(MfSignal.is_selected == True)
    rows = query.order_by(MfSignal.rank.asc()).all()

    if not rows:
        return {"date": str(latest_date), "holdings": [], "ic_summary": {}, "config": {}}

    # Join company names.
    tickers = [r.ticker for r in rows]
    name_rows = db.execute(
        select(Company.listing_ticker, Company.name_zh)
        .where(Company.listing_ticker.in_(tickers))
    ).all()
    name_map = {r[0]: r[1] for r in name_rows}

    holdings = []
    for r in rows:
        holdings.append({
            "ticker": r.ticker,
            "name": name_map.get(r.ticker, ""),
            "rank": r.rank,
            "weight": r.weight,
            "composite_score": r.composite_score,
            "is_selected": r.is_selected,
            "factor_scores": json.loads(r.factor_scores_json) if r.factor_scores_json else {},
        })

    return {
        "date": str(latest_date),
        "holdings": holdings,
        "ic_summary": json.loads(rows[0].ic_summary_json) if rows[0].ic_summary_json else {},
        "config": json.loads(rows[0].config_json) if rows[0].config_json else {},
    }


def get_ranking_history(
    db: Session, ticker: str, days: int = 60,
) -> list[dict]:
    """Get a single ticker's ranking history over the last N days.

    Useful for tracking whether a stock is improving or deteriorating
    in the model's ranking over time.
    """
    rows = db.query(MfSignal).filter(
        MfSignal.ticker == ticker,
    ).order_by(desc(MfSignal.date)).limit(days).all()

    return [
        {
            "date": str(r.date),
            "rank": r.rank,
            "composite_score": r.composite_score,
            "is_selected": r.is_selected,
            "weight": r.weight,
        }
        for r in reversed(rows)  # chronological order
    ]
