"""
FastAPI dependency that resolves every request to an Owner.

Resolution order:
  1. Authorization: Bearer <jwt> → authenticated user Owner.
  2. anon_session_id cookie → existing anonymous Owner (last_active_at touched).
  3. Neither → new anonymous session is created and cookie is set on response.
"""

import hashlib
import logging
import uuid

from fastapi import Depends, HTTPException, Request, Response

from app.models.owner import Owner
from app.services.anon_sessions import (
    create_anon_session,
    get_anon_session,
    touch_anon_session,
)

logger = logging.getLogger(__name__)

ANON_COOKIE = "anon_session_id"
ANON_COOKIE_MAX_AGE = 60 * 60 * 24 * 30  # 30 days


def _hash_ip(ip: str | None) -> str | None:
    """Deterministic per-deployment hash for IP-based quota bookkeeping.

    Salt from env `IP_HASH_SALT` makes hashes non-portable across deployments
    so a leaked ip_quota_usage table can't be rainbow-tabled back to IPs
    without also leaking the salt. Review I2 (PR 3b): without the salt this
    is just SHA256(ip) — reversible via a precomputed IP→hash table.

    Use only for quota enforcement, NOT as a privacy-preserving identifier.
    """
    if not ip:
        return None
    import os
    salt = os.getenv("IP_HASH_SALT", "propguard-default-salt-change-in-prod")
    return hashlib.sha256((salt + ":" + ip).encode()).hexdigest()[:32]


def _mint_anon(request: Request, response: Response) -> Owner:
    ip = request.client.host if request.client else None
    ua = request.headers.get("user-agent")
    sid = create_anon_session(ip_hash=_hash_ip(ip), user_agent=ua)
    if sid is None:
        sid = str(uuid.uuid4())
        logger.warning("anon session DB insert failed, using ephemeral id")
    # secure=True requires HTTPS; gate on scheme so local http dev keeps the cookie.
    is_https = request.url.scheme == "https"
    response.set_cookie(
        key=ANON_COOKIE,
        value=sid,
        max_age=ANON_COOKIE_MAX_AGE,
        httponly=True,
        secure=is_https,
        samesite="lax",
    )
    return Owner(id=sid, kind="anon", plan="anon", metaapi_account_id=None)


def get_owner(request: Request, response: Response) -> Owner:
    # 1. Authorization: Bearer <jwt>
    auth_header = request.headers.get("authorization", "")
    if auth_header.lower().startswith("bearer "):
        from app.services.auth import verify_token, user_dict_to_owner
        token = auth_header[7:].strip()
        user = verify_token(token)
        if user:
            return user_dict_to_owner(user)
        # Invalid/expired JWT — fall through to anon resolution.

    # 2. Existing anon cookie
    sid = request.cookies.get(ANON_COOKIE)
    if sid:
        row = get_anon_session(sid)
        if row and row.get("claimed_by_user_id") is None:
            touch_anon_session(sid)
            return Owner(id=sid, kind="anon", plan="anon", metaapi_account_id=None)

    # 3. Mint a fresh anon session
    return _mint_anon(request, response)


def require_user(owner: Owner = Depends(get_owner)) -> Owner:
    """Endpoints that still require authentication use this instead of get_owner."""
    if owner.kind != "user":
        raise HTTPException(status_code=401, detail="Authentication required")
    return owner
