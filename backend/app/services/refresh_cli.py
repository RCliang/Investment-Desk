"""CLI entrypoint for triggering refreshes without going through HTTP.

Usage (from backend/ dir):
  python -m app.services.refresh_cli quotes         # blocks until done
  python -m app.services.refresh_cli reports        # blocks until done (slow)
  python -m app.services.refresh_cli all            # blocks, runs all 7 types
  python -m app.services.refresh_cli --status 42    # query job status
  python -m app.services.refresh_cli --list         # show 20 most recent jobs

No token required (runs in-process, calls refresh_service directly).
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime

from app.db import SessionLocal
from app.services import refresh_service


VALID_TYPES = ["quotes", "finance", "reports", "concepts",
               "lockup", "holders", "margin", "all"]


def cmd_run(refresh_type: str) -> int:
    session = SessionLocal()
    try:
        print(f"running {refresh_type} ...", flush=True)
        t0 = time.time()

        try:
            result = refresh_service.dispatch(refresh_type, session, trigger="cli")
        except refresh_service.RefreshConflictError:
            print(f"  → skipped: {refresh_type} already running", file=sys.stderr)
            return 1
        except Exception as e:
            print(f"  → failed: {e}", file=sys.stderr)
            return 1

        elapsed = time.time() - t0

        if isinstance(result, list):
            # refresh_all returns a list of log rows
            succeeded = [r for r in result if r.status == "succeeded"]
            failed = [r for r in result if r.status == "failed"]
            print(f"  → done in {elapsed:.1f}s: {len(succeeded)} succeeded, {len(failed)} failed")
            for r in succeeded:
                print(f"    ✓ {r.refresh_type}: rows={r.rows_affected}")
            for r in failed:
                print(f"    ✗ {r.refresh_type}: {r.error[:200]}")
            return 1 if failed else 0
        else:
            # single refresh
            print(f"  → job #{result.id} {result.status} "
                  f"rows={result.rows_affected} elapsed={elapsed:.1f}s")
            return 0 if result.status == "succeeded" else 1
    finally:
        session.close()


def cmd_status(job_id: int) -> int:
    session = SessionLocal()
    try:
        job = refresh_service.get_job(session, job_id)
        if not job:
            print(f"job {job_id} not found", file=sys.stderr)
            return 1
        print(f"job #{job.id}")
        print(f"  type:         {job.refresh_type}")
        print(f"  status:       {job.status}")
        print(f"  started_at:   {job.started_at}")
        print(f"  finished_at:  {job.finished_at}")
        print(f"  rows:         {job.rows_affected}")
        print(f"  triggered_by: {job.triggered_by}")
        if job.error:
            print(f"  error:        {job.error[:500]}")
        return 0
    finally:
        session.close()


def cmd_list() -> int:
    session = SessionLocal()
    try:
        from app.models.chain_models import ChainRefreshLog
        rows = session.query(ChainRefreshLog).order_by(
            ChainRefreshLog.started_at.desc()
        ).limit(20).all()
        if not rows:
            print("(no refresh runs yet)")
            return 0
        print(f"{'id':>4}  {'type':<10}  {'status':<10}  {'started':<20}  {'rows':>8}  by")
        for r in rows:
            print(f"{r.id:>4}  {r.refresh_type:<10}  {r.status:<10}  "
                  f"{r.started_at:%Y-%m-%d %H:%M:%S}  "
                  f"{(r.rows_affected or 0):>8}  {r.triggered_by}")
        return 0
    finally:
        session.close()


def main() -> int:
    p = argparse.ArgumentParser(prog="refresh_cli",
                                description="Trigger chainkb data refresh (no token required)")
    p.add_argument("type", nargs="?", choices=VALID_TYPES,
                   help="refresh type to run")
    p.add_argument("--status", type=int, metavar="JOB_ID",
                   help="show status of a specific job")
    p.add_argument("--list", action="store_true",
                   help="list 20 most recent jobs")
    args = p.parse_args()

    if args.list:
        return cmd_list()
    if args.status is not None:
        return cmd_status(args.status)
    if args.type:
        return cmd_run(args.type)
    p.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
