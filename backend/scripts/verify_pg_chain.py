"""Full-chain verification of the cloud-PostgreSQL cutover.

Exercises, against DATABASE_URL (backend/.env):
  1. startup migrations path (async engine → create_all, PG dialect branch)
  2. dialect-aware ON CONFLICT upsert (chain_signals) — rolled back
  3. live ETF scan (bars read + signals write + hybrid regime sleeve)
  4. ETF backtest + store (bars read + chain_backtest_runs write)
  5. read layer (get_latest_scores / get_latest_portfolio)
  6. FastAPI TestClient: startup (create_all + scheduler start) →
     /api/health + /api/quant/etf-rotation/scores → shutdown

Usage:
    python scripts/verify_pg_chain.py
"""

from __future__ import annotations

import sys
import time
from datetime import date
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

import asyncio  # noqa: E402


def step(n: int, title: str) -> None:
    print(f"\n[{n}] {title}", flush=True)


def main() -> None:
    from app.db import async_engine, sync_engine, SessionLocal
    url = sync_engine.url
    step(0, f"engine → {url.render_as_string(hide_password=True)}")
    assert url.get_backend_name() == "postgresql"

    # ── 1. startup migrations path (same as app startup) ──────────────
    step(1, "async startup migrations (create_all via asyncpg)")

    async def _migrate_and_dispose():
        # migrate, then dispose INSIDE the same run: asyncpg connections
        # are loop-bound and unusable from the TestClient's fresh loop.
        from app.main import _run_migrations
        from app.db import Base
        from app.models.models import (  # noqa: F401
            ChainAnalysis, DataCache, Report, InvestmentPlan,
            ReportContent, DeepAnalysis)
        from app.models import chain_models  # noqa: F401
        async with async_engine.begin() as conn:
            await conn.run_sync(_run_migrations)
        await async_engine.dispose()

    t0 = time.time()
    asyncio.run(_migrate_and_dispose())
    print(f"    ok in {time.time() - t0:.1f}s")

    # ── 2. dialect-aware upsert (rolled back) ─────────────────────────
    step(2, "ON CONFLICT upsert on chain_signals (postgresql dialect)")
    from app.services.quant.signal_service import _upsert_signals
    db = SessionLocal()
    try:
        row = {
            "ticker": "000000", "date": date(2000, 1, 1),
            "strategy_set": "_pgverify",
            "composite_score": 0.0, "action": "hold",
            "position_pct": 0, "stop_loss_price": None,
            "target_price": None, "detail_json": "{}",
        }
        _upsert_signals(db, [row])          # insert …
        _upsert_signals(db, [{**row, "composite_score": 1.0}])  # … + update
        db.rollback()                       # leave nothing behind
        print("    insert + conflict-update compiled and executed; rolled back")
    finally:
        db.close()

    # ── 3. live ETF scan on PG ────────────────────────────────────────
    step(3, "scan_etf_signals (live, hybrid sleeve) on PG")
    from app.services.quant import etf_signal_service
    db = SessionLocal()
    try:
        t0 = time.time()
        result = etf_signal_service.scan_etf_signals(db)
        print(f"    date={result['date']} scanned={result['scanned']} "
              f"selected={result['selected']} "
              f"regime.risk_off={result['regime']['risk_off']} "
              f"elapsed={result['elapsed_s']}s (wall {time.time() - t0:.1f}s)")
        print(f"    holdings: {[(h['ticker'], h['weight']) for h in result['holdings']]}")
    finally:
        db.close()

    # ── 4. backtest + store on PG ─────────────────────────────────────
    step(4, "run_backtest_and_store (hybrid) on PG")
    db = SessionLocal()
    try:
        t0 = time.time()
        out = etf_signal_service.run_backtest_and_store(
            db, use_defensive_sleeve=True,
            strategy_set="etf_momentum_rotation",
            start_date=date(2024, 1, 1))
        keys = {k: out.get(k) for k in ("run_id", "total_return_pct",
                                        "max_drawdown_pct", "sharpe")}
        print(f"    {keys} | wall {time.time() - t0:.1f}s")
    finally:
        db.close()

    # ── 5. read layer ─────────────────────────────────────────────────
    step(5, "read layer (latest scores / portfolio)")
    db = SessionLocal()
    try:
        scores = etf_signal_service.get_latest_scores(db)
        port = etf_signal_service.get_latest_portfolio(db)
        print(f"    scores date={scores['date']} etfs={len(scores['etfs'])}"
              f" | portfolio date={port.get('date')} "
              f"holdings={len(port.get('holdings', []))}")
    finally:
        db.close()

    # ── 6. TestClient end-to-end (startup + endpoints + shutdown) ─────
    step(6, "FastAPI TestClient: startup/scheduler + API endpoints")
    from fastapi.testclient import TestClient
    from app.main import app
    with TestClient(app) as client:
        r = client.get("/api/health")
        print(f"    GET /api/health → {r.status_code} {r.json()}")
        r = client.get("/api/quant/etf-rotation/scores")
        body = r.json()
        print(f"    GET /api/quant/etf-rotation/scores → {r.status_code} "
              f"date={body.get('date')} etfs={len(body.get('etfs', []))}")
        assert r.status_code == 200
    from app.services.scheduler import _scheduler
    print(f"    scheduler after shutdown: "
          f"{type(_scheduler).__name__ if _scheduler else 'stopped'}")

    print("\nALL CHECKS PASSED — cloud PostgreSQL chain verified")


if __name__ == "__main__":
    main()
