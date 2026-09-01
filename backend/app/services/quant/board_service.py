"""Market board heat (板块冷热全景): ingest, heat scoring, and queries.

Daily pipeline (scheduler 17:45, after the 17:40 rotation scan):
  1. EM clist board snapshot (fs=m:90+t:1/2/3 merged & deduped) — one
     pass gives every board's change_pct, turnover, main inflow (f62),
     up/down counts and leader. The fs↔type mapping has drifted across
     EM revisions, so bk_type is resolved via a chain_concepts name
     cross-check + suffix heuristics instead of trusting fs.
  2. HS300 benchmark daily change (Tencent, never blocked).
  3. THS hot-theme strong-stock counts (zx.10jqka getharden, no auth).
  4. Recompute the heat composite + lifecycle tags into chain_board_heat.

Resilience: the daily run needs only ~15 clist requests. EM is IP-blocked
intermittently (skill #18, all-or-nothing), so every EM call goes through
a throttled session with retry + circuit breaker — on failure the job
aborts loudly and retries next night; nothing degrades silently. The
100-day history bootstrap lives in scripts/backfill_em_boards.py (same
push2his endpoints as backfill_em_fund_flow.py, resumable per board).

Heat model (per trade date, cross-sectional percentile ranks 0-100):
  heat = 0.35×动量 + 0.30×资金 + 0.20×广度 + 0.15×题材
    动量 = rank(20d cumulative return minus HS300 over the same window)
    资金 = rank(20d cumulative main inflow / 20d cumulative turnover)
    广度 = rank(20d mean of up/(up+down))          [snapshot days only]
    题材 = rank(THS strong-stock count of tags matched to this board)
  heat_ema = 5-day EMA. Lifecycle tags (see _lifecycle_tag) classify
  boards into mainline(主线) / starting(启动) / fading(退潮) / cool(冷却).
"""

from __future__ import annotations

import logging
import random
import re
import time
from datetime import date, datetime, timedelta
from typing import Optional

import numpy as np
import pandas as pd
import requests
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.chain_models import (
    BoardDaily, BoardHeat, BoardMeta, Concept, DailyBar, ThemeDaily,
)

log = logging.getLogger(__name__)


class BoardSourceError(RuntimeError):
    """Raised when the EM board source is unreachable (IP-blocked)."""


# ── Tunables ───────────────────────────────────────────────────────────────

HEAT_WEIGHTS = {"momentum": 0.35, "flow": 0.30, "breadth": 0.20, "theme": 0.15}
HEAT_EMA_SPAN = 5
MOMENTUM_WINDOW = 20            # days for cum return / flow ratio / breadth
MAINLINE_WINDOW = 15            # days scanned for sustained top-quartile heat
MAINLINE_MIN_DAYS = 8           # ≥N of MAINLINE_WINDOW days at heat ≥ threshold
MAINLINE_HEAT_THRESHOLD = 75.0  # top-quartile cut on the percentile heat
FADING_EMA_BELOW = 50.0
ZOMBIE_MIN_MEMBERS = 8          # member_hint floor for display eligibility
ZOMBIE_MIN_TURNOVER_YI = 5.0    # 20d avg turnover (亿) floor (None = unknown, passes)
CONCEPT_DISPLAY_TOP = 20
INDUSTRY_DISPLAY_TOP = 60       # heatmap row cap (2026 taxonomy: ~790 incl. Ⅱ/Ⅲ)
OVERVIEW_TOP_PER_TYPE = 20      # leaderboard cap per type

BENCHMARK_CODE = "000300"       # HS300, stored in BoardDaily as a board

# fs values fetched & merged: EM's fs↔type semantics drifted (t:1/t:2/t:3),
# so all three are pulled and classification never trusts fs alone.
_BOARD_FS_LISTS = ("m:90+t:1", "m:90+t:2", "m:90+t:3")
_CLIST_FIELDS = ("f12,f14,f3,f6,f8,f62,f66,f72,f104,f105,"
                 "f128,f136,f140,f124")
_EM_PAGE_SIZE = 100
_EM_MAX_PAGES = 8               # safety cap per fs (800 boards)

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
EM_SESSION = requests.Session()
EM_SESSION.headers.update({"User-Agent": UA})
EM_MIN_INTERVAL = 1.2           # push2 clist is calmer than push2his but stay safe
_em_last = [0.0]
_em_fail_streak = [0]
_EM_FAIL_STREAK_LIMIT = 4       # all-or-nothing IP block → stop hammering

_THS_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "Chrome/117.0.0.0 Safari/537.36"),
}

# Earnings/announcement-style THS tags — real themes for board matching,
# these are stock-specific events, tracked separately as the 业绩线.
_PERF_TAG_RE = re.compile(
    r"增长|扭亏|预增|预减|预盈|亏损|减亏|摘帽|退市|ST|回购|增持|减持|重组|更名|"
    r"中标|签约|订单|年报|季报|中报|三季报|半年报|业绩|分红|股权|定增|收购")

# Board-name blacklists. EM's 2026 board universe mixes style/index-member
# boards (融资融券/深股通/小盘股…) and earnings-event boards (2026中报预增)
# into the fs lists; both pollute cross-sectional heat, so they are
# classified out at ingest. EM industries also carry Ⅱ/Ⅲ sub-industries.
_PERF_BOARD_RE = re.compile(
    r"[12]\d{3}(年报|中报|三季报|一季报)|预增|预减|预盈|预亏|扭亏|首亏|减亏|业绩")
_STYLE_INDEX_RE = re.compile(
    r"融资融券|沪股通|深股通|机构重仓|QFII重仓|社保重仓|基金重仓|险资重仓|"
    r"央国企改革|创业板综|科创板综|北证50|小盘股|中盘股|大盘股|微盘股|"
    r"白马股|绩优股|亏损股|ST股|次新股|破发股|破净股|破增发价|趋势股|"
    r"股权分散|股权质押|MSCI|富时罗素|标普|上证50|上证180|上证380|"
    r"中证500|中证100|中证1000|沪深300|HS300|深证成指|百元股|低价股|"
    r"高价股|高送转|昨日涨停|昨日连板|昨日触板|连续缩量|连续放量|"
    r"逼近涨停|独角兽|注册制|昨涨停|举牌|超级品牌|茅指数|宁组合")

# Region boards sometimes appear without the 板块 suffix (e.g. 黑龙江).
_REGION_RE = re.compile(
    r"^(北京|上海|天津|重庆|河北|山西|内蒙古|辽宁|吉林|黑龙江|江苏|浙江|"
    r"安徽|福建|江西|山东|河南|湖北|湖南|广东|广西|海南|四川|贵州|云南|"
    r"西藏|陕西|甘肃|青海|宁夏|新疆|香港|澳门|台湾)$|^[\u4e00-\u9fa5]{2,4}板块$")


# ── EM throttled client ────────────────────────────────────────────────────

def _em_get(url: str, params: dict) -> dict:
    """Throttled EM GET with retry + circuit breaker. Raises BoardSourceError."""
    if _em_fail_streak[0] >= _EM_FAIL_STREAK_LIMIT:
        raise BoardSourceError("EM circuit open (consecutive failures)")
    last_err: Exception | None = None
    for attempt in range(3):
        wait = EM_MIN_INTERVAL - (time.time() - _em_last[0])
        if wait > 0:
            time.sleep(wait + random.uniform(0.1, 0.4))
        try:
            r = EM_SESSION.get(
                url, params=params, timeout=15,
                headers={"User-Agent": UA,
                         "Referer": "https://quote.eastmoney.com/",
                         "Origin": "https://quote.eastmoney.com"})
            if r.status_code != 200:
                raise RuntimeError(f"HTTP {r.status_code}")
            _em_fail_streak[0] = 0
            return r.json()
        except Exception as e:  # noqa: BLE001 — retry any transport error
            last_err = e
            time.sleep(2 ** attempt + random.uniform(0.5, 1.5))
    _em_fail_streak[0] += 1
    raise BoardSourceError(f"EM request failed after retries: {last_err}")


# ── Board classification ───────────────────────────────────────────────────

def _load_concept_name_types(db: Session) -> dict[str, str]:
    """{concept name → tag_type} from chain_concepts (industry/concept/...)."""
    rows = db.execute(select(Concept.name, Concept.tag_type)).all()
    return {name: ttype for name, ttype in rows}


def _classify_board(name: str, fs_hint: str,
                    concept_types: dict[str, str]) -> str:
    """Resolve bk_type for a board name.

    Priority: perf/style blacklists (pollute cross-sectional heat) >
    chain_concepts cross-check > 概念/板块 suffix > Ⅱ/Ⅲ sub-industry >
    fs fallback. The fs labels are empirical (t:2 carries the expanded
    industry taxonomy incl. Ⅱ/Ⅲ levels in 2026).
    """
    if _PERF_BOARD_RE.search(name):
        return "perf"
    if _STYLE_INDEX_RE.search(name):
        return "index"
    ttype = concept_types.get(name)
    if ttype in ("industry", "concept", "region", "index"):
        return ttype
    if _REGION_RE.match(name):
        return "region"
    if name.endswith("概念"):
        return "concept"
    if name.endswith(("Ⅱ", "Ⅲ")):
        return "industry"
    return "industry" if fs_hint == "m:90+t:2" else "concept"


# ── Ingest: EM board snapshot ──────────────────────────────────────────────

def _fetch_fs_boards(fs: str) -> list[dict]:
    """One clist fs → raw board dicts (paginated)."""
    items: list[dict] = []
    for pn in range(1, _EM_MAX_PAGES + 1):
        d = _em_get("https://push2.eastmoney.com/api/qt/clist/get", {
            "pn": str(pn), "pz": str(_EM_PAGE_SIZE), "po": "1", "np": "1",
            "fltt": "2", "invt": "2", "fs": fs, "fields": _CLIST_FIELDS,
        })
        diff = (d.get("data") or {}).get("diff") or []
        if not diff:
            break
        items.extend(diff)
        if len(diff) < _EM_PAGE_SIZE:
            break
    return items


def _f(v, default=None):
    """EM field → float, treating '-' and '' as missing."""
    if v in ("-", "", None):
        return default
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def fetch_board_snapshot(db: Session) -> dict:
    """Fetch + classify all boards, upsert meta & daily rows.

    Returns {date, boards, classified: {industry: n, concept: n, ...}}.
    """
    concept_types = _load_concept_name_types(db)
    merged: dict[str, dict] = {}
    snapshot_ts = 0.0
    for fs in _BOARD_FS_LISTS:
        for it in _fetch_fs_boards(fs):
            code = it.get("f12")
            if not code or not str(code).startswith("BK"):
                continue
            if code in merged:
                continue  # first fs wins; classification re-resolved below
            merged[code] = {
                "bk_code": code,
                "name": it.get("f14", ""),
                "fs_hint": fs,
                "change_pct": _f(it.get("f3")),
                "turnover_yi": (_f(it.get("f6")) or 0.0) / 1e8,
                "turnover_rate": _f(it.get("f8")),
                "main_net": _f(it.get("f62")),
                "super_net": _f(it.get("f66")),
                "large_net": _f(it.get("f72")),
                "up_cnt": int(it["f104"]) if it.get("f104") not in (None, "-") else None,
                "down_cnt": int(it["f105"]) if it.get("f105") not in (None, "-") else None,
                "leader_name": it.get("f128") or None,
                "leader_code": it.get("f140") or None,
                "leader_change": _f(it.get("f136")),
                "ts": _f(it.get("f124"), 0.0) or 0.0,
            }
            snapshot_ts = max(snapshot_ts, merged[code]["ts"])

    if not merged:
        raise BoardSourceError("EM board lists all empty (blocked or changed)")

    snap_date = _resolve_snapshot_date(db, snapshot_ts)
    if snap_date is None:
        raise BoardSourceError("cannot resolve snapshot trade date")

    stats: dict[str, int] = {}
    today = date.today()
    rows_meta, rows_daily = [], []
    for b in merged.values():
        btype = _classify_board(b["name"], b["fs_hint"], concept_types)
        stats[btype] = stats.get(btype, 0) + 1
        members = (b["up_cnt"] or 0) + (b["down_cnt"] or 0)
        rows_meta.append({
            "bk_code": b["bk_code"], "name": b["name"], "bk_type": btype,
            "member_hint": members or None,
            "first_seen": today, "last_seen": today, "is_active": True,
        })
        rows_daily.append({
            "date": snap_date, "bk_code": b["bk_code"],
            "change_pct": b["change_pct"], "turnover_yi": b["turnover_yi"],
            "turnover_rate": b["turnover_rate"], "main_net": b["main_net"],
            "super_net": b["super_net"], "large_net": b["large_net"],
            "up_cnt": b["up_cnt"], "down_cnt": b["down_cnt"],
            "leader_name": b["leader_name"], "leader_code": b["leader_code"],
            "leader_change": b["leader_change"],
        })

    _upsert_board_meta(db, rows_meta)
    _upsert_board_daily(db, rows_daily)
    return {"date": snap_date, "boards": len(rows_daily), "classified": stats}


def _resolve_snapshot_date(db: Session, snapshot_ts: float) -> Optional[date]:
    """Snapshot trade date from the EM update timestamp, with DB fallback.

    f124 freezes at the last quote update, so weekends/holidays resolve to
    the previous trade day automatically. Fallback: latest bar date in DB.
    """
    if snapshot_ts and snapshot_ts > 1e9:
        return datetime.fromtimestamp(snapshot_ts).date()
    return db.execute(select(func.max(DailyBar.date))).scalar_one_or_none()


# ── Ingest: benchmark (Tencent, unblocked) ─────────────────────────────────

def fetch_benchmark_tencent(db: Session, snap_date: date) -> dict:
    """HS300 daily change from Tencent → BoardDaily('000300')."""
    url = "https://qt.gtimg.cn/q=s_sh" + BENCHMARK_CODE
    r = requests.get(url, headers={"User-Agent": UA}, timeout=10)
    parts = r.text.split("~")
    if len(parts) < 6:
        raise BoardSourceError(f"bad tencent benchmark payload: {r.text[:80]}")
    change_pct = float(parts[5])
    _upsert_board_meta(db, [{
        "bk_code": BENCHMARK_CODE, "name": "沪深300", "bk_type": "benchmark",
        "member_hint": None, "first_seen": snap_date, "last_seen": snap_date,
        "is_active": True,
    }])
    _upsert_board_daily(db, [{
        "date": snap_date, "bk_code": BENCHMARK_CODE,
        "change_pct": change_pct,
    }])
    return {"date": snap_date, "change_pct": change_pct}


# ── Ingest: THS hot themes ─────────────────────────────────────────────────

def fetch_ths_hot(db: Session, snap_date: date) -> dict:
    """THS strong-stock theme counts → chain_theme_daily.

    Non-trading day / pre-publication returns 0 rows and is a no-op.
    """
    url = (f"http://zx.10jqka.com.cn/event/api/getharden/date/{snap_date}/"
           f"orderby/date/orderway/desc/charset/GBK/")
    r = requests.get(url, headers=_THS_HEADERS, timeout=10)
    data = r.json()
    if data.get("errocode", 0) != 0:
        raise BoardSourceError(f"THS error: {data.get('errormsg')}")
    rows = data.get("data") or []
    if not rows:
        return {"date": str(snap_date), "tags": 0, "strong": 0}

    counts: dict[str, int] = {}
    for row in rows:
        for tag in str(row.get("reason") or "").split("+"):
            tag = tag.strip()
            if not tag:
                continue
            counts[tag] = counts.get(tag, 0) + 1

    db.query(ThemeDaily).filter(ThemeDaily.date == snap_date).delete()
    db.bulk_insert_mappings(ThemeDaily, [
        {"date": snap_date, "tag": tag,
         "tag_type": "perf" if _PERF_TAG_RE.search(tag) else "theme",
         "strong_cnt": cnt}
        for tag, cnt in counts.items()
    ])
    db.commit()
    return {"date": str(snap_date), "tags": len(counts), "strong": len(rows)}


# ── Upsert helpers ─────────────────────────────────────────────────────────

def _upsert_board_meta(db: Session, rows: list[dict]) -> int:
    """Upsert meta rows; member_hint keeps the historical max."""
    if not rows:
        return 0
    codes = [r["bk_code"] for r in rows]
    existing: dict[str, BoardMeta] = {
        m.bk_code: m for m in db.query(BoardMeta)
        .filter(BoardMeta.bk_code.in_(codes)).all()}
    fresh = 0
    for r in rows:
        m = existing.get(r["bk_code"])
        if m is None:
            db.add(BoardMeta(**r))
            fresh += 1
            continue
        m.name = r["name"]
        m.bk_type = r["bk_type"]
        m.last_seen = r["last_seen"]
        m.is_active = True
        if r.get("member_hint"):
            m.member_hint = max(m.member_hint or 0, r["member_hint"])
    db.commit()
    return fresh


def _upsert_board_daily(db: Session, rows: list[dict]) -> int:
    """Idempotent (date, bk_code) upsert: re-runs replace the stored values
    (an intraday manual refresh is superseded by the 17:45 close snapshot)."""
    if not rows:
        return 0
    snap_date = rows[0]["date"]
    existing = {bk for (bk,) in db.query(BoardDaily.bk_code)
                .filter(BoardDaily.date == snap_date).all()}
    stale = [r["bk_code"] for r in rows if r["bk_code"] in existing]
    if stale:
        db.query(BoardDaily).filter(
            BoardDaily.date == snap_date,
            BoardDaily.bk_code.in_(stale)).delete(synchronize_session=False)
    db.bulk_insert_mappings(BoardDaily, rows)
    db.commit()
    return len(rows) - len(stale)


# ── Heat computation ───────────────────────────────────────────────────────

def _theme_counts_matrix(db: Session, dates: list[date],
                          boards: pd.DataFrame) -> pd.DataFrame:
    """(date × bk_code) matched THS strong-stock counts.

    Boards × tags are matched once on normalized names (概念 suffix
    stripped, substring match ≥2 chars), then counts summed per board.
    """
    if not dates:
        return pd.DataFrame()
    rows = db.query(ThemeDaily).filter(
        ThemeDaily.date >= min(dates), ThemeDaily.tag_type == "theme"
    ).all()
    if not rows:
        return pd.DataFrame(0.0, index=dates, columns=boards.index)

    by_date: dict[date, dict[str, int]] = {}
    for r in rows:
        by_date.setdefault(r.date, {})[r.tag] = r.strong_cnt

    # board name → matched tags (static across the window)
    norm_names = {
        bk: (row["name"] or "").replace("概念", "").replace("板块", "").strip()
        for bk, row in boards.iterrows()}
    all_tags = {t for d in by_date.values() for t in d}
    board_tags: dict[str, list[str]] = {bk: [] for bk in boards.index}
    for tag in all_tags:
        ntag = tag.replace("概念", "").strip()
        if len(ntag) < 2:
            continue
        for bk, nname in norm_names.items():
            if ntag == nname or (len(ntag) >= 2 and ntag in nname) \
                    or (len(nname) >= 2 and nname in ntag):
                board_tags[bk].append(tag)

    mat = pd.DataFrame(0.0, index=dates, columns=boards.index)
    for d in dates:
        day_counts = by_date.get(d, {})
        for bk, tags in board_tags.items():
            mat.loc[d, bk] = float(sum(day_counts.get(t, 0) for t in tags))
    return mat


def _pct_rank(df: pd.DataFrame) -> pd.DataFrame:
    """Cross-sectional percentile rank per row → [0,100]."""
    if df.empty:
        return df
    return df.rank(axis=1, pct=True, na_option="keep") * 100.0


def _lifecycle_tag(heat_hist: list[float], ema_now: float,
                   flow20_now: float, tag_hist: list[str]) -> str:
    """mainline / starting / fading / cool for one board-date.

    mainline: ≥MAINLINE_MIN_DAYS of the last MAINLINE_WINDOW days at heat
              ≥ threshold AND 20d cumulative main inflow positive.
    starting: top-quartile today but not yet sustained.
    fading:   was mainline within the last 9 days, heat EMA below median.
    """
    window = heat_hist[-MAINLINE_WINDOW:]
    if len(window) >= 10:
        above = sum(1 for v in window if v >= MAINLINE_HEAT_THRESHOLD)
        if above >= MAINLINE_MIN_DAYS and flow20_now > 0:
            return "mainline"
        if window[-1] >= MAINLINE_HEAT_THRESHOLD and above <= MAINLINE_MIN_DAYS:
            return "starting"
    for prev in tag_hist[-9:]:
        if prev == "mainline" and ema_now < FADING_EMA_BELOW:
            return "fading"
    return "cool"


def compute_and_store_heat(db: Session, lookback_dates: int = 160) -> dict:
    """Recompute BoardHeat for the whole stored history. Idempotent.

    Loads pivots of BoardDaily (+ benchmark), builds the four component
    percentile panels, blends into heat, smooths with EMA and walks dates
    forward to assign lifecycle tags (tags depend on their own history).
    """
    daily = pd.read_sql(
        db.query(BoardDaily).statement, db.bind, parse_dates=["date"])
    if daily.empty:
        return {"dates": 0, "boards": 0}

    metas = {m.bk_code: m for m in db.query(BoardMeta).all()}
    eligible = {c for c, m in metas.items()
                if m.bk_type in ("industry", "concept")}
    daily = daily[daily["bk_code"].isin(eligible | {BENCHMARK_CODE})]
    if daily.empty:
        return {"dates": 0, "boards": 0}

    daily["date"] = daily["date"].dt.date
    chg = daily.pivot(index="date", columns="bk_code", values="change_pct")
    main = daily.pivot(index="date", columns="bk_code", values="main_net")
    turnover = daily.pivot(index="date", columns="bk_code", values="turnover_yi")
    up = daily.pivot(index="date", columns="bk_code", values="up_cnt")
    down = daily.pivot(index="date", columns="bk_code", values="down_cnt")

    # drop ghost boards (listed but never quoted ≥5 days)
    valid = chg.columns[chg.notna().sum() >= 5]
    keep = [c for c in valid if c != BENCHMARK_CODE]
    if not keep:
        return {"dates": 0, "boards": 0}
    boards = chg[keep]
    main, turnover = main[keep], turnover[keep]
    up, down = up[keep], down[keep]
    bench = (chg[BENCHMARK_CODE] if BENCHMARK_CODE in chg.columns
             else pd.Series(0.0, index=chg.index)).fillna(0.0)

    dates = list(boards.index)
    if len(dates) > lookback_dates:
        dates = dates[-lookback_dates:]
        first = dates[0]
        boards, main, turnover = (boards.loc[first:], main.loc[first:],
                                  turnover.loc[first:])
        up, down, bench = up.loc[first:], down.loc[first:], bench.loc[first:]

    w = MOMENTUM_WINDOW
    # 20d cumulative return (%), chained via logs; NaN days skipped by rolling
    cum_board = np.expm1(np.log1p(boards / 100.0)
                         .rolling(w, min_periods=w // 2).sum())
    cum_bench = np.expm1(np.log1p(bench / 100.0)
                         .rolling(w, min_periods=w // 2).sum())
    mom_excess = (cum_board.sub(cum_bench, axis=0)) * 100.0

    # 20d flow ratio: cum main inflow (亿) / cum turnover (亿)
    flow20 = (main / 1e8).rolling(w, min_periods=w // 2).sum()
    turn20 = turnover.rolling(w, min_periods=w // 2).sum()
    flow_ratio = flow20 / turn20.where(turn20 != 0.0)
    turnover_avg = turnover.rolling(w, min_periods=w // 2).mean()

    # breadth: 20d mean of up/(up+down) — snapshot days only (backfill rows NaN)
    up_ratio = (up / (up + down)).astype(float)
    breadth = up_ratio.rolling(w, min_periods=5).mean()

    boards_meta = pd.DataFrame(
        {bk: {"name": metas[bk].name} for bk in keep}).T
    theme = _theme_counts_matrix(db, dates, boards_meta)
    theme = theme.reindex(index=boards.index, columns=boards.columns,
                          fill_value=0.0)

    # percentile blend, renormalizing weights over available components
    comps = {
        "momentum": _pct_rank(mom_excess),
        "flow": _pct_rank(flow_ratio),
        "breadth": _pct_rank(breadth),
        "theme": _pct_rank(theme),
    }
    wsum = sum(HEAT_WEIGHTS.values())
    heat = pd.DataFrame(0.0, index=boards.index, columns=boards.columns)
    wsum_avail = pd.DataFrame(0.0, index=boards.index, columns=boards.columns)
    for name, panel in comps.items():
        wgt = HEAT_WEIGHTS[name]
        heat = heat + panel.fillna(0.0) * wgt
        wsum_avail = wsum_avail + panel.notna().astype(float) * wgt
    heat = heat / wsum_avail.where(wsum_avail > 0, wsum)
    heat_ema = heat.ewm(span=HEAT_EMA_SPAN, min_periods=1).mean()

    # persist: delete the recomputed range, insert chunked
    db.query(BoardHeat).filter(BoardHeat.date >= dates[0]).delete(
        synchronize_session=False)

    rows: list[dict] = []
    heat_hist: dict[str, list[float]] = {bk: [] for bk in keep}
    tag_hist: dict[str, list[str]] = {bk: [] for bk in keep}
    for d in dates:
        row_heat = heat.loc[d]
        ranked = row_heat.sort_values(ascending=False)
        rank_map = {bk: i + 1 for i, bk in enumerate(ranked.index)}
        row_ema = heat_ema.loc[d]
        row_flow = flow20.loc[d] if d in flow20.index else None
        row_mom = mom_excess.loc[d] if d in mom_excess.index else None
        row_fr = flow_ratio.loc[d] if d in flow_ratio.index else None
        row_br = breadth.loc[d] if d in breadth.index else None
        row_tv = turnover_avg.loc[d] if d in turnover_avg.index else None
        row_th = theme.loc[d] if d in theme.index else None
        for bk in keep:
            hv = row_heat.get(bk)
            if hv is None or pd.isna(hv):
                continue
            f20 = float(row_flow.get(bk)) if row_flow is not None \
                and pd.notna(row_flow.get(bk)) else 0.0
            ema_v = row_ema.get(bk)
            ema_v = float(ema_v) if pd.notna(ema_v) else float(hv)
            tag = _lifecycle_tag(heat_hist[bk], ema_v, f20, tag_hist[bk])
            heat_hist[bk].append(float(hv))
            tag_hist[bk].append(tag)

            mom_v = row_mom.get(bk) if row_mom is not None else None
            fr_v = row_fr.get(bk) if row_fr is not None else None
            br_v = row_br.get(bk) if row_br is not None else None
            tv_v = row_tv.get(bk) if row_tv is not None else None
            th_v = row_th.get(bk) if row_th is not None else None
            rows.append({
                "date": d, "bk_code": bk,
                "mom_excess_20d": None if mom_v is None or pd.isna(mom_v)
                else round(float(mom_v), 4),
                "flow_ratio_20d": None if fr_v is None or pd.isna(fr_v)
                else round(float(fr_v), 6),
                "breadth_20d": None if br_v is None or pd.isna(br_v)
                else round(float(br_v), 4),
                "turnover_avg_20d": None if tv_v is None or pd.isna(tv_v)
                else round(float(tv_v), 3),
                "theme_cnt": int(th_v) if th_v is not None
                and not pd.isna(th_v) else 0,
                "heat": round(float(hv), 2),
                "heat_ema": round(ema_v, 2),
                "tag": tag,
                "heat_rank": rank_map.get(bk),
            })

    for i in range(0, len(rows), 5000):
        db.bulk_insert_mappings(BoardHeat, rows[i:i + 5000])
    db.commit()
    log.info("board heat computed: %d dates × %d boards → %d rows",
             len(dates), len(keep), len(rows))
    return {"dates": len(dates), "boards": len(keep), "rows": len(rows)}


# ── Daily orchestrator ─────────────────────────────────────────────────────

def refresh_boards_daily(db: Session) -> dict:
    """Nightly entry: snapshot → benchmark → THS → heat. Raises on EM block."""
    started = datetime.utcnow()
    snap = fetch_board_snapshot(db)
    bench = fetch_benchmark_tencent(db, snap["date"])
    try:
        ths = fetch_ths_hot(db, snap["date"])
    except Exception:  # noqa: BLE001 — THS down shouldn't kill the pipeline
        log.exception("THS hot fetch failed (theme dim = 0 today)")
        ths = {"tags": 0, "strong": 0}
    heat = compute_and_store_heat(db)
    return {
        "date": str(snap["date"]),
        "boards": snap["boards"],
        "classified": snap["classified"],
        "benchmark_pct": bench["change_pct"],
        "theme_tags": ths["tags"],
        "theme_strong": ths["strong"],
        "heat": heat,
        "elapsed_s": round((datetime.utcnow() - started).total_seconds(), 1),
    }


# ── Query layer (API) ──────────────────────────────────────────────────────

def _display_set(db: Session) -> tuple[list[dict], list[dict], date | None]:
    """(industries, concepts-top20, latest_date) at the latest heat date.

    Both types are zombie-filtered (member count + 20d avg turnover —
    turnover passes while unknown during the first ~10 days so the panel
    isn't empty during bootstrap). Concepts truncate to
    CONCEPT_DISPLAY_TOP by heat_ema, per product decision.
    """
    latest = db.execute(select(func.max(BoardHeat.date))).scalar_one_or_none()
    if latest is None:
        return [], [], None
    rows = (db.query(BoardHeat, BoardMeta)
            .join(BoardMeta, BoardMeta.bk_code == BoardHeat.bk_code)
            .filter(BoardHeat.date == latest,
                    BoardMeta.is_active == True,  # noqa: E712
                    BoardMeta.bk_type.in_(("industry", "concept")))
            .all())
    industries, concepts = [], []
    for heat_row, meta in rows:
        item = {
            "bk_code": meta.bk_code, "name": meta.name,
            "bk_type": meta.bk_type,
            "heat": heat_row.heat, "heat_ema": heat_row.heat_ema,
            "tag": heat_row.tag, "heat_rank": heat_row.heat_rank,
            "mom_excess_20d": heat_row.mom_excess_20d,
            "flow_ratio_20d": heat_row.flow_ratio_20d,
            "breadth_20d": heat_row.breadth_20d,
            "theme_cnt": heat_row.theme_cnt or 0,
            "turnover_avg_20d": heat_row.turnover_avg_20d,
            "member_hint": meta.member_hint,
        }
        (industries if meta.bk_type == "industry" else concepts).append(item)

    def _eligible(b: dict) -> bool:
        if (b["member_hint"] or 0) < ZOMBIE_MIN_MEMBERS:
            return False
        tv = b["turnover_avg_20d"]
        return tv is None or tv >= ZOMBIE_MIN_TURNOVER_YI

    industries = sorted(
        (b for b in industries if _eligible(b)),
        key=lambda x: -(x["heat_ema"] or 0))
    concepts = sorted(
        (b for b in concepts if _eligible(b)),
        key=lambda x: -(x["heat_ema"] or 0))[:CONCEPT_DISPLAY_TOP]
    return industries, concepts, latest


def _latest_leaders(db: Session, latest: date,
                    codes: list[str]) -> dict[str, dict]:
    rows = (db.query(BoardDaily)
            .filter(BoardDaily.date == latest, BoardDaily.bk_code.in_(codes))
            .all())
    return {r.bk_code: {"name": r.leader_name, "code": r.leader_code,
                        "change": r.leader_change} for r in rows}


def _sparklines(db: Session, latest: date, days: int,
                codes: list[str]) -> dict[str, dict]:
    """Per-board window series: heat_ema / excess / cumulative main inflow."""
    if not codes:
        return {}
    cutoff = latest - timedelta(days=int(days * 1.7) + 10)
    heat_rows = (db.query(BoardHeat)
                 .filter(BoardHeat.date >= cutoff, BoardHeat.bk_code.in_(codes))
                 .order_by(BoardHeat.date.asc()).all())
    daily_rows = (db.query(BoardDaily.date, BoardDaily.bk_code,
                           BoardDaily.main_net)
                  .filter(BoardDaily.date >= cutoff,
                          BoardDaily.bk_code.in_(codes))
                  .order_by(BoardDaily.date.asc()).all())

    series: dict[str, dict[str, list]] = {}
    for r in heat_rows:
        s = series.setdefault(r.bk_code, {
            "heat": [], "excess": [], "flow_cum": [], "dates": []})
        s["dates"].append(str(r.date))
        s["heat"].append(r.heat_ema)
        s["excess"].append(r.mom_excess_20d)
    for d, bk, main_net in daily_rows:
        if bk in series:
            series[bk]["flow_cum"].append((str(d), main_net))
    out: dict[str, dict] = {}
    for bk, s in series.items():
        # align the three series to the heat dates (truncate to last N)
        n = min(days, len(s["dates"]))
        dates_n = s["dates"][-n:]
        flow_by_date = dict(s["flow_cum"])
        cum, running = [], 0.0
        for d in dates_n:
            running += flow_by_date.get(d) or 0.0
            cum.append(round(running / 1e8, 3))  # 亿元
        out[bk] = {
            "dates": dates_n,
            "heat": [round(v, 1) if v is not None else None
                     for v in s["heat"][-n:]],
            "excess": [round(v, 2) if v is not None else None
                       for v in s["excess"][-n:]],
            "flow_cum": cum,
        }
    return out


def get_overview(db: Session, days: int = 20) -> dict:
    """Leaderboard for the display set + sparkline series for cards."""
    industries, concepts, latest = _display_set(db)
    if latest is None:
        return {"date": None, "industries": [], "concepts": []}
    industries = industries[:OVERVIEW_TOP_PER_TYPE]
    codes = [b["bk_code"] for b in industries + concepts]
    leaders = _latest_leaders(db, latest, codes)
    sparks = _sparklines(db, latest, days, codes)
    for b in industries + concepts:
        b["leader"] = leaders.get(b["bk_code"])
        b["spark"] = sparks.get(b["bk_code"])
    return {
        "date": str(latest),
        "industries": industries,
        "concepts": concepts,
        "weights": HEAT_WEIGHTS,
        "zombie_filter": {"min_members": ZOMBIE_MIN_MEMBERS,
                          "min_turnover_yi": ZOMBIE_MIN_TURNOVER_YI},
    }


def get_heatmap(db: Session, days: int = 30) -> dict:
    """Heat matrix for the display set over the last N trade dates."""
    industries, concepts, latest = _display_set(db)
    if latest is None:
        return {"date": None, "dates": [], "rows": []}
    display = industries[:INDUSTRY_DISPLAY_TOP] + concepts
    codes = [b["bk_code"] for b in display]

    cutoff = latest - timedelta(days=int(days * 1.7) + 10)
    rows = (db.query(BoardHeat)
            .filter(BoardHeat.date >= cutoff, BoardHeat.bk_code.in_(codes))
            .order_by(BoardHeat.date.asc()).all())
    per_board: dict[str, dict[str, float]] = {c: {} for c in codes}
    dates_seen: set[str] = set()
    for r in rows:
        per_board[r.bk_code][str(r.date)] = r.heat
        dates_seen.add(str(r.date))
    dates = sorted(dates_seen)[-days:]

    out_rows = []
    for b in display:
        vals = per_board.get(b["bk_code"], {})
        out_rows.append({
            "bk_code": b["bk_code"], "name": b["name"],
            "bk_type": b["bk_type"], "tag": b["tag"],
            "heat_ema": b["heat_ema"],
            "values": [vals.get(d) for d in dates],
        })
    return {"date": str(latest), "dates": dates, "rows": out_rows}


def get_board_detail(db: Session, bk_code: str, days: int = 100) -> dict | None:
    """One board's full series + benchmark for drill-down."""
    meta = db.query(BoardMeta).filter(BoardMeta.bk_code == bk_code).first()
    if meta is None:
        return None
    latest = db.execute(select(func.max(BoardHeat.date))
                        .where(BoardHeat.bk_code == bk_code)).scalar_one_or_none()
    if latest is None:
        latest = db.execute(select(func.max(BoardDaily.date))
                            .where(BoardDaily.bk_code == bk_code)
                            ).scalar_one_or_none()
    if latest is None:
        return {"bk_code": bk_code, "name": meta.name, "bk_type": meta.bk_type,
                "dates": [], "change_pct": [], "excess": [], "main_net": [],
                "heat": [], "leaders": []}

    cutoff = latest - timedelta(days=int(days * 1.6) + 10)
    daily_rows = (db.query(BoardDaily)
                  .filter(BoardDaily.date >= cutoff,
                          BoardDaily.bk_code.in_([bk_code, BENCHMARK_CODE]))
                  .order_by(BoardDaily.date.asc()).all())
    bench_chg: dict[str, float] = {}
    board_chg: dict[str, float] = {}
    main_net: dict[str, float | None] = {}
    leaders: list[dict] = []
    for r in daily_rows:
        if r.bk_code == BENCHMARK_CODE:
            bench_chg[str(r.date)] = r.change_pct or 0.0
        else:
            board_chg[str(r.date)] = r.change_pct or 0.0
            main_net[str(r.date)] = r.main_net
            if r.leader_name and (not leaders or
                                  leaders[-1]["name"] != r.leader_name):
                leaders.append({"date": str(r.date), "name": r.leader_name,
                                "code": r.leader_code, "change": r.leader_change})
    dates = sorted(board_chg.keys())[-days:]

    # cumulative excess return within the window (chained from window start)
    excess, cum_b, cum_k = [], 1.0, 1.0
    for d in dates:
        cum_b *= 1 + (board_chg.get(d) or 0.0) / 100
        cum_k *= 1 + (bench_chg.get(d) or 0.0) / 100
        excess.append(round((cum_b - cum_k) * 100, 2))

    heat_rows = (db.query(BoardHeat)
                 .filter(BoardHeat.date >= cutoff, BoardHeat.bk_code == bk_code)
                 .order_by(BoardHeat.date.asc()).all())
    heat_by_date = {str(r.date): r for r in heat_rows}

    return {
        "bk_code": bk_code, "name": meta.name, "bk_type": meta.bk_type,
        "member_hint": meta.member_hint,
        "dates": dates,
        "change_pct": [board_chg.get(d) for d in dates],
        "excess": excess,
        "main_net": [main_net.get(d) for d in dates],
        "heat": [{
            "heat": heat_by_date[d].heat if d in heat_by_date else None,
            "heat_ema": heat_by_date[d].heat_ema if d in heat_by_date else None,
            "tag": heat_by_date[d].tag if d in heat_by_date else None,
        } for d in dates],
        "leaders": leaders[-8:][::-1],   # most-recent-first, max 8
        "latest": ({
            "tag": heat_rows[-1].tag, "heat": heat_rows[-1].heat,
            "heat_ema": heat_rows[-1].heat_ema,
            "heat_rank": heat_rows[-1].heat_rank,
            "theme_cnt": heat_rows[-1].theme_cnt,
        } if heat_rows else None),
    }


def get_theme_trends(db: Session, days: int = 20) -> dict:
    """THS theme strong-count evolution: top themes + top perf tags."""
    latest = db.execute(select(func.max(ThemeDaily.date))).scalar_one_or_none()
    if latest is None:
        return {"date": None, "dates": [], "themes": {}, "perf": {}}
    cutoff = latest - timedelta(days=int(days * 1.7) + 10)
    rows = (db.query(ThemeDaily)
            .filter(ThemeDaily.date >= cutoff)
            .order_by(ThemeDaily.date.asc()).all())
    dates = sorted({str(r.date) for r in rows})[-days:]

    themes: dict[str, dict[str, int]] = {}
    perfs: dict[str, dict[str, int]] = {}
    for r in rows:
        target = themes if r.tag_type == "theme" else perfs
        target.setdefault(r.tag, {})[str(r.date)] = r.strong_cnt

    def _series(top: dict, n: int) -> dict[str, list[int]]:
        ranked = sorted(top.items(),
                        key=lambda kv: -sum(kv[1].values()))[:n]
        return {tag: [cnts.get(d, 0) for d in dates] for tag, cnts in ranked}

    return {
        "date": str(latest), "dates": dates,
        "themes": _series(themes, 15),
        "perf": _series(perfs, 8),
    }
