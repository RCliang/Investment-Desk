"""Bootstrap ~100 days of board history for the 板块冷热全景 dashboard.

Sources (all EM push2his, same endpoints the fund-flow backfill uses):
  - board fund-flow history:  /api/qt/stock/fflow/daykline/get (secid=90.BKxxxx)
    → main/super/large net inflow per day
  - board kline history:      /api/qt/stock/kline/get (secid=90.BKxxxx, klt=101)
    → closes (chained into change_pct) + turnover amounts
  - benchmark HS300 kline:    secid=1.000300 → change_pct series
  - THS hot themes history:   zx.10jqka getharden per date (no auth, fast)

push2his is intermittently IP-blocked (all-or-nothing, skill #18): the
script is resumable — boards that already have enough history rows are
skipped, commits happen per board, and the run exits gracefully when the
EM circuit opens. Re-run it on another evening to fill the remainder.

Usage (from backend/):
    python scripts/backfill_em_boards.py                 # all boards
    python scripts/backfill_em_boards.py --only industries
    python scripts/backfill_em_boards.py --lmt 60 --ths-days 0

Prereq: chain_board_meta populated (run the /api/quant/boards/refresh
job or refresh_boards_daily once so the board list + classification
exist), otherwise there is nothing to backfill.
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import date, datetime
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.db import SessionLocal  # noqa: E402
from app.models.chain_models import BoardDaily, BoardMeta  # noqa: E402
from app.services.quant.board_service import (  # noqa: E402
    BENCHMARK_CODE, BoardSourceError, _em_get, fetch_ths_hot,
    compute_and_store_heat)

FFLOW_URL = "https://push2his.eastmoney.com/api/qt/stock/fflow/daykline/get"
KLINE_URL = "https://push2his.eastmoney.com/api/qt/stock/kline/get"
FFLOW_FIELDS2 = "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61,f62,f63,f64,f65"
KLINE_FIELDS2 = "f51,f52,f53,f54,f55,f56,f57"
EM_MIN_INTERVAL_HIS = 3.0     # push2his rate: ~550 req @1.5s in 20min
                              # re-triggers the IP block; 3s stays under
                              # the ~300 req/5min documented threshold
RETRIES = 3


def _his_get(url: str, params: dict) -> dict:
    """push2his GET with retry; raises BoardSourceError on hard failure."""
    last_err = None
    for attempt in range(RETRIES):
        time.sleep(EM_MIN_INTERVAL_HIS)
        try:
            d = _em_get(url, params)
            return d
        except BoardSourceError as e:
            last_err = e
            # _em_get already slept between attempts
    raise BoardSourceError(f"push2his failed: {last_err}")


def fetch_board_fflow(bk_code: str, lmt: int) -> dict[str, dict]:
    """{date: {main, super, large}} — daily net inflows (yuan)."""
    d = _his_get(FFLOW_URL, {
        "secid": f"90.{bk_code}", "fields1": "f1,f2,f3,f7",
        "fields2": FFLOW_FIELDS2, "lmt": str(lmt),
    })
    out: dict[str, dict] = {}
    for line in (d.get("data") or {}).get("klines") or []:
        p = line.split(",")
        if len(p) < 6:
            continue
        def _f(v):
            return float(v) if v not in ("-", "") else None
        out[p[0]] = {"main_net": _f(p[1]), "super_net": _f(p[4]),
                     "large_net": _f(p[5])}
    return out


def fetch_board_kline(bk_code: str, lmt: int,
                      secid: str | None = None) -> dict[str, dict]:
    """{date: {change_pct, turnover_yi}} from chained closes + amount."""
    d = _his_get(KLINE_URL, {
        "secid": secid or f"90.{bk_code}", "klt": "101", "fqt": "1",
        "fields1": "f1,f2,f3,f7", "fields2": KLINE_FIELDS2,
        "lmt": str(lmt + 5), "end": "20500101",
    })
    bars: list[tuple[str, float, float]] = []
    for line in (d.get("data") or {}).get("klines") or []:
        p = line.split(",")
        if len(p) < 7:
            continue
        try:
            bars.append((p[0], float(p[2]), float(p[6])))
        except ValueError:
            continue
    out: dict[str, dict] = {}
    prev_close = None
    for dstr, close, amount in bars:
        change_pct = None
        if prev_close:
            change_pct = round((close / prev_close - 1) * 100, 4)
        out[dstr] = {"change_pct": change_pct,
                     "turnover_yi": round(amount / 1e8, 4)}
        prev_close = close
    # the first bar has no prior close → drop it
    if out:
        first = min(out)
        out.pop(first, None)
    return out


def backfill_board(db, meta: BoardMeta, lmt: int) -> int:
    """Merge fflow + kline history into BoardDaily for one board."""
    existing = db.query(BoardDaily.date).filter(
        BoardDaily.bk_code == meta.bk_code).count()
    if existing >= lmt - 5:
        return 0
    kline = fetch_board_kline(meta.bk_code, lmt)
    fflow = fetch_board_fflow(meta.bk_code, lmt)
    if not kline:
        return -1  # no kline → likely dead board, count as skipped
    rows = []
    for dstr, k in kline.items():
        try:
            day = datetime.strptime(dstr, "%Y-%m-%d").date()
        except ValueError:
            continue
        f = fflow.get(dstr, {})
        rows.append({
            "date": day, "bk_code": meta.bk_code,
            "change_pct": k["change_pct"], "turnover_yi": k["turnover_yi"],
            "main_net": f.get("main_net"), "super_net": f.get("super_net"),
            "large_net": f.get("large_net"),
        })
    have = {r[0] for r in db.query(BoardDaily.date)
            .filter(BoardDaily.bk_code == meta.bk_code).all()}
    fresh = [r for r in rows if r["date"] not in have]
    if fresh:
        db.bulk_insert_mappings(BoardDaily, fresh)
        db.commit()
    return len(fresh)


def backfill_benchmark(db, lmt: int) -> int:
    existing = db.query(BoardDaily.date).filter(
        BoardDaily.bk_code == BENCHMARK_CODE).count()
    if existing >= lmt - 5:
        return 0
    kline = fetch_board_kline(BENCHMARK_CODE, lmt, secid=f"1.{BENCHMARK_CODE}")
    have = {r[0] for r in db.query(BoardDaily.date)
            .filter(BoardDaily.bk_code == BENCHMARK_CODE).all()}
    fresh = [{"date": datetime.strptime(d, "%Y-%m-%d").date(),
              "bk_code": BENCHMARK_CODE, "change_pct": k["change_pct"]}
             for d, k in kline.items()
             if datetime.strptime(d, "%Y-%m-%d").date() not in have]
    if fresh:
        db.bulk_insert_mappings(BoardDaily, fresh)
        db.commit()
    print(f"  benchmark HS300: +{len(fresh)} days")
    return len(fresh)


def backfill_ths(db, dates: list[date]) -> int:
    """THS hot themes for each historical date (skips already-stored)."""
    have = {r[0] for r in db.query(BoardDaily.date).distinct().all()}
    done = 0
    for d in dates:
        if d not in have:
            continue
        time.sleep(0.4)
        try:
            res = fetch_ths_hot(db, d)
            if res["tags"]:
                done += 1
        except Exception as e:  # noqa: BLE001 — one bad date shouldn't stop us
            print(f"  THS {d}: {e}")
    return done


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--lmt", type=int, default=100,
                    help="history length per board (trading days)")
    ap.add_argument("--only", choices=["all", "industries", "concepts"],
                    default="all")
    ap.add_argument("--ths-days", type=int, default=60,
                    help="THS theme history days (0 = skip)")
    ap.add_argument("--pause-every", type=int, default=40,
                    help="cool down every N boards (0 = no pacing)")
    ap.add_argument("--pause-secs", type=int, default=240,
                    help="cool-down length in seconds")
    args = ap.parse_args()
    args.pause_every = args.pause_every or 10**9  # disable pacing when 0

    db = SessionLocal()
    metas = db.query(BoardMeta).filter(
        BoardMeta.is_active == True,  # noqa: E712
        # dead boards (member_hint < 8) never display — skip their requests
        BoardMeta.member_hint >= 8).all()
    if args.only == "industries":
        metas = [m for m in metas if m.bk_type == "industry"]
    elif args.only == "concepts":
        metas = [m for m in metas if m.bk_type == "concept"]
    else:
        metas = [m for m in metas if m.bk_type in ("industry", "concept")]

    if not metas:
        print("No boards in chain_board_meta — run the daily refresh first "
              "(POST /api/quant/boards/refresh) so the list gets ingested.")
        return

    print(f"Backfilling {len(metas)} boards × {args.lmt}d "
          f"(only={args.only})")
    ok = fail = skip = rows = 0
    for i, m in enumerate(metas, 1):
        # Pacing: a long cool-down every N boards keeps the request rate far
        # below EM's ~300 req/5min block threshold on trigger-happy days.
        if i > 1 and args.pause_every and (i - 1) % args.pause_every == 0:
            print(f"  [{i}/{len(metas)}] pacing pause {args.pause_secs}s "
                  f"(ok={ok} skip={skip} fail={fail})")
            time.sleep(args.pause_secs)
        try:
            n = backfill_board(db, m, args.lmt)
            if n == 0:
                skip += 1
            elif n < 0:
                fail += 1
            else:
                ok += 1
                rows += n
            if i % 20 == 0 or i == len(metas):
                print(f"  [{i}/{len(metas)}] {m.name}: ok={ok} skip={skip} "
                      f"fail={fail} rows+{rows}")
        except BoardSourceError:
            print(f"  [{i}/{len(metas)}] EM circuit open at {m.name} "
                  f"(ok={ok} skip={skip} fail={fail}) — stopping EM part; "
                  f"re-run another time to resume.")
            break

    try:
        backfill_benchmark(db, args.lmt)
    except BoardSourceError:
        print("  benchmark backfill blocked — heat excess falls back to "
              "raw returns until next run")

    if args.ths_days > 0:
        stored = sorted({r[0] for r in db.query(BoardDaily.date)
                         .distinct().all()})
        dates = stored[-args.ths_days:]
        if dates:
            print(f"THS themes: last {len(dates)} stored dates")
            n = backfill_ths(db, dates)
            print(f"  THS done: {n} dates with tags")

    print("Recomputing heat…")
    result = compute_and_store_heat(db)
    print(f"Heat: {result}")
    db.close()


if __name__ == "__main__":
    main()
