"""Batch download daily bars via mootdx (通达信协议) for monitored tickers.

Uses mootdx's TdxHq_API which connects directly to 通达信 servers (more
reliable than web scraping EastMoney). Downloads ~2.5 years of history.

Run: python backfill_mootdx.py
"""
import time
import sqlite3
from datetime import datetime, timedelta
from typing import Optional

from mootdx.quotes import Quotes

DB_PATH = "data/investlens.db"
BARS_PER_TICKER = 600  # ~2.5 years (trading days)


def get_monitored_tickers(db: sqlite3.Connection) -> list[str]:
    """Get all distinct tickers from chain_margin_daily."""
    rows = db.execute(
        "SELECT DISTINCT ticker FROM chain_margin_daily ORDER BY ticker"
    ).fetchall()
    return [r[0] for r in rows]


def ticker_to_mootdx(code: str) -> tuple[int, str]:
    """Convert ticker code to mootdx market + code.
    
    mootdx market: 0 = SZ (深圳), 1 = SH (上海)
    """
    if code.startswith("6") or code.startswith("9"):
        return 1, code  # SH
    elif code.startswith("0") or code.startswith("2") or code.startswith("3"):
        return 0, code  # SZ
    else:
        return 0, code  # default SZ


def download_bars(client, ticker: str) -> list[dict]:
    """Download daily bars via mootdx for one ticker."""
    market, code = ticker_to_mootdx(ticker)
    try:
        df = client.bars(symbol=code, frequency=9, offset=BARS_PER_TICKER)
        # frequency=9 means daily bars
        if df is None or len(df) == 0:
            return []
        
        records = []
        for _, row in df.iterrows():
            # mootdx columns: datetime, open, close, high, low, vol, amount, year, month, day, hour, minute, datetime_str
            dt_str = str(row["datetime"])[:10]  # "2024-01-02"
            records.append({
                "ticker": ticker,
                "date": dt_str,
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
                "volume": float(row["vol"]),
                "amount": float(row["amount"]),
                "turnover_pct": None,
                "source": "mootdx",
            })
        return records
    except Exception as e:
        print(f"  ERROR {ticker}: {e}")
        return []


def insert_bars(db: sqlite3.Connection, records: list[dict]):
    """Insert bars with INSERT OR REPLACE."""
    db.executemany(
        """INSERT OR REPLACE INTO chain_daily_bars
           (ticker, date, open, high, low, close, volume, amount, turnover_pct, source)
           VALUES (:ticker, :date, :open, :high, :low, :close, :volume, :amount,
                   :turnover_pct, :source)""",
        records,
    )
    db.commit()


def main():
    db = sqlite3.connect(DB_PATH)
    tickers = get_monitored_tickers(db)
    print(f"Found {len(tickers)} monitored tickers")
    print(f"Bars per ticker: {BARS_PER_TICKER} (~{BARS_PER_TICKER//240} years)\n")

    # Connect to mootdx best server
    print("Connecting to mootdx server...")
    client = Quotes.factory(market="std")
    print("Connected.\n")

    success = 0
    fail = 0
    total_bars = 0

    for i, ticker in enumerate(tickers):
        # Check existing
        existing = db.execute(
            "SELECT COUNT(*) FROM chain_daily_bars WHERE ticker = ?", (ticker,)
        ).fetchone()[0]
        if existing > 100:
            print(f"[{i+1}/{len(tickers)}] {ticker}: SKIP ({existing} bars)")
            success += 1
            continue

        print(f"[{i+1}/{len(tickers)}] {ticker}: ", end="", flush=True)
        records = download_bars(client, ticker)

        if records:
            insert_bars(db, records)
            total_bars += len(records)
            success += 1
            print(f"OK ({len(records)} bars)")
        else:
            fail += 1
            print("FAIL")

        # mootdx rate limit is less strict, but still pace it
        if (i + 1) % 50 == 0:
            time.sleep(0.5)

    print(f"\n{'='*60}")
    print(f"Done: {success} success, {fail} fail, {total_bars} bars downloaded")

    row = db.execute("SELECT COUNT(*), COUNT(DISTINCT ticker) FROM chain_daily_bars").fetchone()
    print(f"DB now: {row[0]} total bars, {row[1]} tickers")

    db.close()


if __name__ == "__main__":
    main()
