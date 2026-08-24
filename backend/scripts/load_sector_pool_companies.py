"""Register sector_pool.json companies into chain_companies.

The rotation/fund-flow backfills (--pool) pull bars for ~70 pool tickers,
but pool-only companies (not in the aichainmap seed) were never registered
in chain_companies — so signal/quote joins show blank names. This loader
closes the gap.

Idempotent: looks up by (listing_market, listing_ticker); updates the name
of existing rows, creates missing ones. Run whenever sector_pool.json gains
tickers:

    python scripts/load_sector_pool_companies.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

# Make `app.*` importable when run as `python scripts/load_sector_pool_companies.py`
BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from sqlalchemy import select

from app.db import SessionLocal
from app.models.chain_models import Company, LIFECYCLE_CANONICAL

POOL_PATH = BACKEND_ROOT / "app" / "services" / "quant" / "sector_pool.json"


def _derive_cn_market(ticker: str) -> str:
    """6-digit CN ticker → exchange code (mirrors load_seed_to_db.py)."""
    if ticker.startswith(("6", "9")):
        return "SH"
    if ticker.startswith("8"):
        return "BJ"
    return "SZ"


def main() -> None:
    pool = json.loads(POOL_PATH.read_text(encoding="utf-8"))

    # Dedup across sectors (some tickers sit in several, e.g. 华海清科).
    tickers: dict[str, str] = {}
    for cfg in pool.values():
        for t, name in cfg["stocks"]:
            tickers.setdefault(t, name)

    created = updated = 0
    session = SessionLocal()
    try:
        for ticker in sorted(tickers):
            market = _derive_cn_market(ticker)
            comp = session.execute(
                select(Company).where(
                    Company.listing_market == market,
                    Company.listing_ticker == ticker,
                )
            ).scalar_one_or_none()
            if comp:
                if comp.name_zh != tickers[ticker]:
                    comp.name_zh = tickers[ticker]
                    updated += 1
            else:
                session.add(Company(
                    name_zh=tickers[ticker],
                    listing_market=market,
                    listing_ticker=ticker,
                    is_reference=False,
                    lifecycle=LIFECYCLE_CANONICAL,
                ))
                created += 1
        session.commit()
    finally:
        session.close()

    print(f"pool tickers: {len(tickers)} | created: {created} | renamed: {updated}")


if __name__ == "__main__":
    main()
