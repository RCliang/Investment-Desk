"""Migrate investlens.db (SQLite) → cloud PostgreSQL.

Reads the POSTGRES_* block from backend/.env, creates the target
database (UTF8) if missing, recreates the schema via the app's
Base.metadata, streams every table's rows in chunks, then syncs
serial sequences and verifies row counts.

The app itself keeps running on SQLite — this is a data archive /
migration copy, not a cutover. To cut the app over later, point
app/db.py at the POSTGRES_* vars.

Usage (from backend/, conda env dev):
    python scripts/migrate_sqlite_to_pg.py            # full run
    python scripts/migrate_sqlite_to_pg.py --dry-run  # connectivity +
                                                       # plan only
"""

from __future__ import annotations

import argparse
import re
import sqlite3
import sys
import time
from pathlib import Path

import psycopg2
import psycopg2.extras
import sqlalchemy as sa
from sqlalchemy import create_engine, text

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from app.db import Base                                   # noqa: E402
from app.models import chain_models                       # noqa: E402/F401
from app.models import models as legacy_models            # noqa: E402/F401

SQLITE_PATH = BACKEND_DIR / "data" / "investlens.db"
ENV_PATH = BACKEND_DIR / ".env"
CHUNK = 5000


def load_env() -> dict:
    env: dict[str, str] = {}
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^(POSTGRES_[A-Z]+)=(.*)$", line.strip())
        if m:
            env[m.group(1)] = m.group(2).strip()
    missing = [k for k in ("POSTGRES_HOST", "POSTGRES_USER",
                           "POSTGRES_PASSWORD", "POSTGRES_DB")
               if not env.get(k)]
    if missing:
        raise SystemExit(f".env missing keys: {missing}")
    env.setdefault("POSTGRES_PORT", "5432")
    return env


def admin_connect(env: dict):
    return psycopg2.connect(
        host=env["POSTGRES_HOST"], port=int(env["POSTGRES_PORT"]),
        user=env["POSTGRES_USER"], password=env["POSTGRES_PASSWORD"],
        dbname="postgres", connect_timeout=15)


def create_database(env: dict) -> str:
    """CREATE DATABASE if missing (UTF8). Returns 'created'|'exists'."""
    db = env["POSTGRES_DB"]
    conn = admin_connect(env)
    conn.autocommit = True
    try:
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (db,))
        if cur.fetchone():
            return "exists"
        cur.execute(f'CREATE DATABASE "{db}" '
                    f"WITH ENCODING 'UTF8' TEMPLATE template0")
        return "created"
    finally:
        conn.close()


def fix_sequences(engine) -> list[str]:
    """Advance each table's id serial past the copied max(id)."""
    fixed = []
    with engine.begin() as conn:
        for table in Base.metadata.sorted_tables:
            pk_cols = list(table.primary_key)
            if len(pk_cols) != 1 or pk_cols[0].name != "id":
                continue
            tname = table.name
            seq = conn.execute(text(
                "SELECT pg_get_serial_sequence(:t, 'id')"), {"t": tname}
            ).scalar()
            if not seq:
                continue
            conn.execute(text(
                f"SELECT setval(:seq, GREATEST(COALESCE(MAX(id), 1), 1)) "
                f"FROM {tname}").bindparams(seq=seq))
            fixed.append(tname)
    return fixed


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    t0 = time.time()
    env = load_env()
    print(f"target: {env['POSTGRES_HOST']}:{env['POSTGRES_PORT']}"
          f"/{env['POSTGRES_DB']}  source: {SQLITE_PATH.name}")

    # connectivity + create db
    status = create_database(env)
    print(f"database {env['POSTGRES_DB']}: {status}")
    if args.dry_run:
        print("dry run: stopping after database creation check")
        return

    dsn = (f"postgresql+psycopg2://{env['POSTGRES_USER']}:"
           f"{env['POSTGRES_PASSWORD']}@{env['POSTGRES_HOST']}:"
           f"{env['POSTGRES_PORT']}/{env['POSTGRES_DB']}")
    engine = create_engine(dsn, future=True)

    # schema
    Base.metadata.create_all(engine)
    n_tables = len(Base.metadata.sorted_tables)
    print(f"schema created/verified: {n_tables} tables")

    sq = sqlite3.connect(f"file:{SQLITE_PATH}?mode=ro", uri=True)
    sqlite_tables = {r[0] for r in sq.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}

    # rerun-safe: clear all destinations first — children before parents
    # (PG enforces the FKs SQLite silently ignored).
    pg = engine.raw_connection()
    try:
        with pg.cursor() as pcur:
            for table in reversed(Base.metadata.sorted_tables):
                if table.name in sqlite_tables:
                    pcur.execute(f'DELETE FROM "{table.name}"')
        pg.commit()
    finally:
        pg.close()

    copied, skipped = [], []
    for table in Base.metadata.sorted_tables:
        name = table.name
        if name not in sqlite_tables:
            skipped.append(f"{name} (absent in sqlite)")
            continue
        cols = [c.name for c in table.columns]
        sql_cols = ", ".join(f'"{c}"' for c in cols)
        # sqlite stores booleans as 0/1 — PG boolean columns need real
        # bools, so coerce per column type before sending.
        bool_cols = {c.name for c in table.columns
                     if isinstance(c.type, sa.Boolean)}
        n = 0
        cur = sq.execute(f"SELECT {sql_cols} FROM {name}")
        pg = engine.raw_connection()
        try:
            with pg.cursor() as pcur:
                while True:
                    rows = cur.fetchmany(CHUNK)
                    if not rows:
                        break
                    rows = [tuple(bool(v) if (c in bool_cols and v is not None)
                                  else v for c, v in zip(cols, r))
                            for r in rows]
                    # execute_values: ONE multi-row INSERT per chunk —
                    # executemany would do a round trip per row and take
                    # hours over a WAN link.
                    psycopg2.extras.execute_values(
                        pcur,
                        f'INSERT INTO "{name}" ({sql_cols}) '
                        f"VALUES %s ON CONFLICT DO NOTHING",
                        rows, page_size=CHUNK)
                    n += len(rows)
                    print(f"    {name}: {n} rows", flush=True)
            pg.commit()
        finally:
            pg.close()
        copied.append((name, n))
        print(f"  {name:32s} {n:>8d} rows", flush=True)

    extra = sorted(sqlite_tables
                   - {t.name for t in Base.metadata.sorted_tables})
    if extra:
        print(f"note: sqlite tables outside metadata (not copied): {extra}")

    fix_sequences(engine)
    print(f"sequences synced on id-PK tables")

    # verify
    mismatches = []
    with engine.connect() as conn:
        for name, n in copied:
            pg_n = conn.execute(text(f'SELECT COUNT(*) FROM "{name}"')
                                ).scalar()
            if pg_n != n:
                mismatches.append(f"{name}: sqlite {n} vs pg {pg_n}")
    if mismatches:
        raise SystemExit(f"ROW COUNT MISMATCH: {mismatches}")
    total = sum(n for _, n in copied)
    print(f"verified: {len(copied)} tables, {total} rows match "
          f"| elapsed {time.time() - t0:.0f}s")
    sq.close()


if __name__ == "__main__":
    main()
