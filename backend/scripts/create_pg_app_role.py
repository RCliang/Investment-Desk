"""Create the restricted app role for the cloud PostgreSQL.

Runs as the postgres superuser (POSTGRES_* in backend/.env) and creates
`investlens_app`: LOGIN, NOCREATEDB/NOSUPERUSER (defaults), CONNECT on
the investlens database ONLY (PUBLIC connect is revoked from every other
non-template database), full DML on public-schema tables + sequences,
and default privileges so future postgres-created tables stay reachable.

The generated password is printed once — store it in backend/.env as
DATABASE_URL.

Usage (from backend/):
    python scripts/create_pg_app_role.py            # create + grant
    python scripts/create_pg_app_role.py --password <pw>   # explicit pw
"""

from __future__ import annotations

import argparse
import secrets
import sys
from pathlib import Path

import psycopg2

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR / "scripts"))

from migrate_sqlite_to_pg import load_env  # noqa: E402

ROLE = "investlens_app"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--password", help="explicit password (default: random)")
    args = ap.parse_args()
    env = load_env()
    db = env["POSTGRES_DB"]
    pwd = args.password or secrets.token_urlsafe(18)

    # 1) server level: role + database scoping
    conn = psycopg2.connect(
        host=env["POSTGRES_HOST"], port=int(env["POSTGRES_PORT"]),
        user=env["POSTGRES_USER"], password=env["POSTGRES_PASSWORD"],
        dbname="postgres", connect_timeout=15)
    conn.autocommit = True
    try:
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (ROLE,))
        if cur.fetchone():
            cur.execute(f'ALTER ROLE "{ROLE}" WITH LOGIN PASSWORD %s', (pwd,))
            created = "existing (password reset)"
        else:
            cur.execute(f'CREATE ROLE "{ROLE}" LOGIN PASSWORD %s', (pwd,))
            created = "created"
        cur.execute(f'GRANT CONNECT ON DATABASE "{db}" TO "{ROLE}"')

        # lock every other non-template database: revoke PUBLIC connect
        cur.execute(
            "SELECT datname FROM pg_database "
            "WHERE datistemplate = false AND datname != %s", (db,))
        others = [r[0] for r in cur.fetchall()]
        for other in others:
            cur.execute(f'REVOKE CONNECT ON DATABASE "{other}" FROM PUBLIC')
        print(f"role {ROLE}: {created} | connect granted on {db} only "
              f"(PUBLIC connect revoked on: {others or 'none'})")
    finally:
        conn.close()

    # 2) database level: schema/tables/sequences + future defaults
    conn = psycopg2.connect(
        host=env["POSTGRES_HOST"], port=int(env["POSTGRES_PORT"]),
        user=env["POSTGRES_USER"], password=env["POSTGRES_PASSWORD"],
        dbname=db, connect_timeout=15)
    conn.autocommit = True
    try:
        cur = conn.cursor()
        cur.execute(f'GRANT USAGE, CREATE ON SCHEMA public TO "{ROLE}"')
        cur.execute(f'GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES '
                    f'IN SCHEMA public TO "{ROLE}"')
        cur.execute(f'GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES '
                    f'IN SCHEMA public TO "{ROLE}"')
        cur.execute(f'ALTER DEFAULT PRIVILEGES FOR ROLE '
                    f'{env["POSTGRES_USER"]} IN SCHEMA public '
                    f'GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES '
                    f'TO "{ROLE}"')
        cur.execute(f'ALTER DEFAULT PRIVILEGES FOR ROLE '
                    f'{env["POSTGRES_USER"]} IN SCHEMA public '
                    f'GRANT USAGE, SELECT, UPDATE ON SEQUENCES '
                    f'TO "{ROLE}"')
        cur.execute("SELECT count(*) FROM information_schema.tables "
                    "WHERE table_schema = 'public'")
        n_tables = cur.fetchone()[0]
    finally:
        conn.close()
    print(f"grants applied on {db} (public schema, {n_tables} tables)")

    print("\nDATABASE_URL for backend/.env:")
    print(f"DATABASE_URL=postgresql+psycopg2://{ROLE}:{pwd}"
          f"@{env['POSTGRES_HOST']}:{env['POSTGRES_PORT']}/{db}")


if __name__ == "__main__":
    main()
