"""Shared admin auth dependency.

Used by routers that protect privileged endpoints (refresh, research,
deep-analysis) with a single shared X-Admin-Token header compared
against ADMIN_REFRESH_TOKEN from config.
"""
from __future__ import annotations

import secrets

from fastapi import Header, HTTPException

from app.config import ADMIN_REFRESH_TOKEN


def verify_admin_token(x_admin_token: str = Header(default="")) -> None:
    """FastAPI dependency: enforce X-Admin-Token header.

    - 503 if ADMIN_REFRESH_TOKEN unset (defensive: prevents accidental
      open access when misconfigured).
    - 401 if header missing or mismatched.
    """
    if not ADMIN_REFRESH_TOKEN:
        raise HTTPException(
            status_code=503,
            detail="ADMIN_REFRESH_TOKEN not configured; admin endpoints disabled.",
        )
    if not x_admin_token or not secrets.compare_digest(x_admin_token, ADMIN_REFRESH_TOKEN):
        raise HTTPException(status_code=401, detail="invalid or missing X-Admin-Token")
