"""Sector-rotation daily service: scan, persist, and query.

Daily pipeline (scheduler 17:40, after fund flow 16:40 + bars 16:30):
  1. Load the pool universe's bars with fund-flow columns merged in.
  2. Run SectorRotationEngine (factors → composite → sector strength).
  3. At the LATEST date (not just scheduled rebalance dates), run the
     3-layer selection for today's recommendation.
  4. Persist: chain_sector_scores (one row/sector) + chain_rotation_signals
     (one row/pool stock, selected or not, for full in-sector rankings).

Query layer serves the /api/quant/rotation/* endpoints: sector strength
snapshot + evolution, the recommended portfolio, and per-sector rankings.
"""

from __future__ import annotations

import json
import logging
from datetime import date, datetime, timedelta
from typing import Optional

import pandas as pd
from sqlalchemy import select, func, desc
from sqlalchemy.orm import Session

from app.models.chain_models import DailyBar, FundFlowDaily, SectorScore, RotationSignal
from app.services.quant import sector_pool
from app.services.quant.sector_rotation import (
    SectorRotationEngine, select_portfolio_at,
    build_bullish_panel, compute_divergence_panel, build_atr_panel,
    TOP_K_SECTORS, TOP_N_PER_SECTOR, MAX_WEIGHT, ENTRY_FALLBACK,
)
from .factor_model import HOLDING_PERIOD
from .signal_service import _load_bars_df

log = logging.getLogger(__name__)


# ── Data loading ────────────────────────────────────────────────────────────

def get_pool_membership() -> dict[str, list[str]]:
    """ticker → sector names, from the sector_pool config."""
    return sector_pool.get_membership()


def load_fund_flow_map(
    db: Session, tickers: list[str], limit: int = 200,
) -> dict[str, pd.DataFrame]:
    """{ticker: DataFrame(date, main_net, super_net, ...)} for the pool.

    One batched query instead of one per ticker (70 round-trips → 1).
    Dates normalized to ISO strings to match the bar loader.
    """
    if not tickers:
        return {}
    rows = db.execute(
        select(
            FundFlowDaily.ticker, FundFlowDaily.date,
            FundFlowDaily.main_net, FundFlowDaily.super_net,
            FundFlowDaily.large_net, FundFlowDaily.mid_net,
            FundFlowDaily.small_net,
        ).where(FundFlowDaily.ticker.in_(tickers))
        .order_by(FundFlowDaily.ticker.asc(), FundFlowDaily.date.desc())
        .limit(len(tickers) * limit)
    ).all()

    frames: dict[str, dict[str, list]] = {}
    for r in rows:
        buf = frames.setdefault(r[0], {c: [] for c in (
            "date", "main_net", "super_net", "large_net", "mid_net", "small_net")})
        buf["date"].append(str(r[1]))
        buf["main_net"].append(r[2])
        buf["super_net"].append(r[3])
        buf["large_net"].append(r[4])
        buf["mid_net"].append(r[5])
        buf["small_net"].append(r[6])

    out: dict[str, pd.DataFrame] = {}
    for t, cols in frames.items():
        df = pd.DataFrame(cols)
        if not df.empty:
            df = df.drop_duplicates(subset="date", keep="first")
            df = df.sort_values("date").reset_index(drop=True)
        out[t] = df
    return out


def load_pool_bars(
    db: Session,
    limit: int = 1200,
    with_fund_flow: bool = True,
    min_bars: int = 80,
) -> dict[str, pd.DataFrame]:
    """Pool tickers' bars with fund-flow columns left-joined (NaN if absent)."""
    tickers = sector_pool.get_all_tickers()
    flow_map = load_fund_flow_map(db, tickers) if with_fund_flow else {}

    bars: dict[str, pd.DataFrame] = {}
    for t in tickers:
        df = _load_bars_df(db, t, limit=limit)
        if df is None or len(df) < min_bars:
            continue
        if with_fund_flow and t in flow_map and not flow_map[t].empty:
            ff = flow_map[t]
            df = df.merge(ff, on="date", how="left")
        else:
            df["main_net"] = float("nan")
            df["super_net"] = float("nan")
            df["large_net"] = float("nan")
            df["mid_net"] = float("nan")
            df["small_net"] = float("nan")
        bars[t] = df
    return bars


# ── Daily scan ──────────────────────────────────────────────────────────────

def scan_rotation_signals(
    db: Session,
    top_k: int = TOP_K_SECTORS,
    top_n_per_sector: int = TOP_N_PER_SECTOR,
    holding_period: int = HOLDING_PERIOD,
) -> dict:
    """Run the rotation engine and persist today's snapshot. Idempotent.

    Returns {date, sector_count, scanned, selected, top_sectors,
    holdings, elapsed_s}.
    """
    started = datetime.utcnow()

    bars = load_pool_bars(db, limit=1200, with_fund_flow=True)
    if len(bars) < 10:
        raise ValueError(
            f"Insufficient pool bars ({len(bars)}), need ≥10 — run the "
            f"mootdx backfill for pool tickers first")

    membership = get_pool_membership()
    engine = SectorRotationEngine(
        membership,
        top_k=top_k,
        top_n_per_sector=top_n_per_sector,
        holding_period=holding_period,
    )
    model = engine.run(bars)

    composite = model["composite"]
    strength = model["sector"]["strength"]
    flow_rank = model["sector"]["flow_rank"]
    tech_rank = model["sector"]["tech_rank"]
    detail = model["sector"]["detail"]
    factor_panels = model["factor_panels"]

    valid_dates = composite.dropna(how="all").index
    if len(valid_dates) == 0:
        raise ValueError("No valid composite scores computed")
    latest = valid_dates[-1]

    bullish = build_bullish_panel(bars)
    divergence = compute_divergence_panel(bars)
    # Stop reference for the signal panel: matches the validated v2 exit
    # rule (close − 2×ATR14, volatility-scaled), falling back to the v1
    # fixed 10% when ATR isn't formed. Displayed as the "if-bought-today"
    # hard-stop level.
    atr_panel = build_atr_panel(bars)
    weights, sel_detail = select_portfolio_at(
        latest, composite, strength, bullish, membership,
        top_k=top_k, top_n_per_sector=top_n_per_sector,
        entry_fallback=ENTRY_FALLBACK, max_weight=MAX_WEIGHT,
    )
    selected_sectors = {d["sector"] for d in sel_detail["top_sectors"]}

    sig_date = date.fromisoformat(str(latest)[:10])

    # ── Persist sector scores ────────────────────────────────────────────
    db.query(SectorScore).filter(SectorScore.date == sig_date).delete()
    sector_rows = []
    pool = sector_pool.get_sectors()
    if latest in strength.index:
        s_row = strength.loc[latest]
        f_row = flow_rank.loc[latest] if (not flow_rank.empty
                                          and latest in flow_rank.index) else None
        t_row = tech_rank.loc[latest] if latest in tech_rank.index else None
        fm_row = detail["flow_mean_20d"].loc[latest] \
            if (not detail["flow_mean_20d"].empty
                and latest in detail["flow_mean_20d"].index) else None
        am_row = detail["align_share_20d"].loc[latest] \
            if latest in detail["align_share_20d"].index else None
        mm_row = detail["momentum_20d"].loc[latest] \
            if latest in detail["momentum_20d"].index else None
        for sec in pool:
            if sec not in s_row.index or pd.isna(s_row.get(sec)):
                continue
            sector_rows.append({
                "date": sig_date,
                "sector": sec,
                "strength": round(float(s_row[sec]), 6),
                "flow_dim": round(float(f_row[sec]), 6)
                if f_row is not None and sec in f_row.index
                and pd.notna(f_row[sec]) else None,
                "tech_dim": round(float(t_row[sec]), 6)
                if t_row is not None and sec in t_row.index
                and pd.notna(t_row[sec]) else None,
                "member_count": len(pool[sec]["stocks"]),
                "is_selected": sec in selected_sectors,
                "detail_json": json.dumps({
                    "flow_mean_20d": round(float(fm_row[sec]), 6)
                    if fm_row is not None and sec in fm_row.index
                    and pd.notna(fm_row[sec]) else None,
                    "align_share_20d": round(float(am_row[sec]), 6)
                    if am_row is not None and sec in am_row.index
                    and pd.notna(am_row[sec]) else None,
                    "momentum_20d": round(float(mm_row[sec]), 6)
                    if mm_row is not None and sec in mm_row.index
                    and pd.notna(mm_row[sec]) else None,
                }, ensure_ascii=False),
            })
    if sector_rows:
        db.bulk_insert_mappings(SectorScore, sector_rows)

    # ── Persist per-stock signals (full pool, in-sector ranking) ─────────
    db.query(RotationSignal).filter(RotationSignal.date == sig_date).delete()
    stock_rows = []
    close_at = None
    for t, df in bars.items():
        df_idx = df.set_index("date")
        if str(latest) in df_idx.index:
            close_at = float(df_idx.loc[str(latest), "close"])
        else:
            close_at = None
        sectors = membership.get(t, [])
        if not sectors:
            continue
        # Display sector: the one through which the stock is selected,
        # else its first membership.
        sel_sector = next(
            (d["sector"] for d in sel_detail["top_sectors"] if t in d["chosen"]),
            sectors[0])

        score = composite.loc[latest].get(t) if latest in composite.index else None
        if score is None or pd.isna(score):
            continue

        member_scores = {}
        sec_members = [tt for tt, ss in membership.items() if sel_sector in ss]
        if latest in composite.index:
            for tt in sec_members:
                v = composite.loc[latest].get(tt)
                if v is not None and not pd.isna(v):
                    member_scores[tt] = float(v)
        rank_in_sector = sorted(
            member_scores, key=member_scores.get, reverse=True).index(t) + 1 \
            if t in member_scores else None

        f_scores = {}
        for fname, panel in factor_panels.items():
            if latest in panel.index and t in panel.columns:
                v = panel.loc[latest, t]
                if not pd.isna(v):
                    f_scores[fname] = round(float(v), 4)

        entry_ok = bool(bullish.loc[latest].get(t, False)) \
            if latest in bullish.index else False
        div_flag = bool(divergence.loc[latest].get(t, False)) \
            if latest in divergence.index else False

        def _stop_ref(t: str, close: Optional[float]) -> Optional[float]:
            if close is None:
                return None
            if latest in atr_panel.index and t in atr_panel.columns:
                atr_val = atr_panel.loc[latest, t]
                if pd.notna(atr_val) and atr_val > 0:
                    return round(close - 2.0 * float(atr_val), 3)
            return round(close * 0.9, 3)

        stock_rows.append({
            "date": sig_date,
            "ticker": t,
            "sector": sel_sector,
            "rank_in_sector": rank_in_sector,
            "composite_score": round(float(score), 6),
            "is_selected": t in weights,
            "weight": round(float(weights.get(t, 0.0)), 4),
            "entry_ok": entry_ok,
            "divergence_flag": div_flag,
            "stop_loss_price": _stop_ref(t, close_at),
            "trail_stop_price": None,
            "factor_scores_json": json.dumps(f_scores, ensure_ascii=False),
        })
    if stock_rows:
        db.bulk_insert_mappings(RotationSignal, stock_rows)
    db.commit()

    elapsed = (datetime.utcnow() - started).total_seconds()
    names = sector_pool.get_names()
    holdings = [
        {"ticker": t, "name": names.get(t, ""), "weight": round(w, 4)}
        for t, w in sorted(weights.items(), key=lambda kv: -kv[1])
    ]
    log.info("Rotation scan done: date=%s, %d sectors, %d stocks, %d selected, %.1fs",
             sig_date, len(sector_rows), len(stock_rows), len(weights), elapsed)

    return {
        "date": str(sig_date),
        "sector_count": len(sector_rows),
        "scanned": len(stock_rows),
        "selected": len(weights),
        "top_sectors": sel_detail["top_sectors"],
        "holdings": holdings,
        "ic_summary": model["ic_summary"],
        "config": model["config"],
        "elapsed_s": round(elapsed, 1),
    }


# ── Query layer (for the API) ───────────────────────────────────────────────

def get_latest_sector_scores(db: Session) -> dict:
    """Latest sector snapshot: strength + both dims + selection flag."""
    latest_date = db.execute(select(func.max(SectorScore.date))).scalar_one()
    if latest_date is None:
        return {"date": None, "sectors": []}
    rows = db.query(SectorScore).filter(
        SectorScore.date == latest_date
    ).order_by(desc(SectorScore.strength)).all()
    return {
        "date": str(latest_date),
        "sectors": [
            {
                "sector": r.sector,
                "strength": r.strength,
                "flow_dim": r.flow_dim,
                "tech_dim": r.tech_dim,
                "member_count": r.member_count,
                "is_selected": r.is_selected,
                "detail": json.loads(r.detail_json) if r.detail_json else {},
            }
            for r in rows
        ],
    }


def get_sector_history(db: Session, days: int = 30) -> dict:
    """Strength evolution: {date: {sector: strength}} for the last N days."""
    latest_date = db.execute(select(func.max(SectorScore.date))).scalar_one()
    if latest_date is None:
        return {"dates": [], "series": {}}
    cutoff = latest_date - timedelta(days=days)
    rows = db.query(SectorScore).filter(
        SectorScore.date >= cutoff
    ).order_by(SectorScore.date.asc()).all()

    dates: list[str] = []
    series: dict[str, list[float]] = {}
    for r in rows:
        d = str(r.date)
        if d not in dates:
            dates.append(d)
        series.setdefault(r.sector, []).append(round(r.strength, 4))
    return {"dates": dates, "series": series}


def get_latest_portfolio(db: Session) -> dict:
    """Latest recommended rotation portfolio with factor detail."""
    latest_date = db.execute(
        select(func.max(RotationSignal.date))).scalar_one()
    if latest_date is None:
        return {"date": None, "holdings": []}
    rows = db.query(RotationSignal).filter(
        RotationSignal.date == latest_date,
        RotationSignal.is_selected == True,  # noqa: E712
    ).order_by(RotationSignal.weight.desc()).all()
    names = sector_pool.get_names()
    return {
        "date": str(latest_date),
        "holdings": [
            {
                "ticker": r.ticker,
                "name": names.get(r.ticker, ""),
                "sector": r.sector,
                "rank_in_sector": r.rank_in_sector,
                "weight": r.weight,
                "composite_score": r.composite_score,
                "entry_ok": r.entry_ok,
                "divergence_flag": r.divergence_flag,
                "stop_loss_price": r.stop_loss_price,
                "factor_scores": json.loads(r.factor_scores_json)
                if r.factor_scores_json else {},
            }
            for r in rows
        ],
    }


def get_rotation_rankings(db: Session, sector: Optional[str] = None) -> dict:
    """Full in-sector rankings for the latest date (all pool stocks)."""
    latest_date = db.execute(
        select(func.max(RotationSignal.date))).scalar_one()
    if latest_date is None:
        return {"date": None, "stocks": []}
    q = db.query(RotationSignal).filter(RotationSignal.date == latest_date)
    if sector:
        q = q.filter(RotationSignal.sector == sector)
    rows = q.order_by(RotationSignal.sector.asc(),
                      RotationSignal.rank_in_sector.asc()).all()
    names = sector_pool.get_names()
    return {
        "date": str(latest_date),
        "stocks": [
            {
                "ticker": r.ticker,
                "name": names.get(r.ticker, ""),
                "sector": r.sector,
                "rank_in_sector": r.rank_in_sector,
                "composite_score": r.composite_score,
                "is_selected": r.is_selected,
                "weight": r.weight,
                "entry_ok": r.entry_ok,
                "divergence_flag": r.divergence_flag,
                "stop_loss_price": r.stop_loss_price,
            }
            for r in rows
        ],
    }
