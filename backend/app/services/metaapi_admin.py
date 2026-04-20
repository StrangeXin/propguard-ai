"""MetaApi account binding — validates a user-provided account ID.

Keeps the MetaApi SDK call isolated so the route layer doesn't import the
SDK directly. Returns a user-safe message on every failure path (no secrets,
actionable text).
"""

import asyncio
import logging

from app.config import get_settings

logger = logging.getLogger(__name__)


async def verify_metaapi_account(account_id: str) -> tuple[bool, str]:
    """Returns (ok, message). ok=True if the account exists and is in a
    usable state. On failure, message is user-safe.

    Named verify_* not test_* so pytest doesn't try to collect it as a test.
    """
    settings = get_settings()
    if not settings.metaapi_token:
        return False, "Server MetaApi token not configured; ask admin."

    try:
        from metaapi_cloud_sdk import MetaApi
        api = MetaApi(settings.metaapi_token)
        account = await asyncio.wait_for(
            api.metatrader_account_api.get_account(account_id), timeout=10,
        )
        state = getattr(account, "state", "UNKNOWN")
        if state == "DRAFT":
            return False, "Account is in DRAFT state. Deploy it in the MetaApi dashboard first."
        if state in ("DEPLOYING", "UNDEPLOYING"):
            return False, f"Account is {state}; retry in a few seconds."
        return True, f"Account connected (state: {state})"
    except asyncio.TimeoutError:
        return False, "MetaApi timed out. Check your network and try again."
    except Exception as e:
        msg = str(e)
        if "not found" in msg.lower():
            return False, "Account ID not found in MetaApi."
        if "unauthorized" in msg.lower() or "401" in msg:
            return False, "Access denied. Is this your account?"
        return False, f"Connection failed: {msg[:200]}"


async def verify_with_user_token(account_id: str, user_token: str) -> tuple[bool, str]:
    """Validate that `user_token` can reach `account_id`.

    Proves ownership: our server-admin token can reach ANY account, so
    we use the user's own MetaApi API token instead. If the SDK call
    succeeds, the user demonstrably controls the token.

    Returns (ok, message) with user-safe text on every failure path.
    """
    if not user_token or len(user_token) < 20:
        return False, "Missing MetaApi API token. Paste it from app.metaapi.cloud → API Access."
    try:
        from metaapi_cloud_sdk import MetaApi
        api = MetaApi(user_token)
        account = await asyncio.wait_for(
            api.metatrader_account_api.get_account(account_id), timeout=10,
        )
        state = getattr(account, "state", "UNKNOWN")
        if state == "DRAFT":
            return False, "Account is in DRAFT state. Deploy it in the MetaApi dashboard first."
        return True, f"Ownership verified (account state: {state})"
    except asyncio.TimeoutError:
        return False, "MetaApi timed out. Check network and try again."
    except Exception as e:
        msg = str(e).lower()
        if "401" in msg or "unauthorized" in msg or "forbidden" in msg:
            return False, "Token rejected by MetaApi. Double-check the API token (not the MT5 password)."
        if "not found" in msg or "404" in msg:
            return False, "This account ID isn't reachable under that token. Make sure the token is from the same MetaApi workspace as the account."
        return False, f"Verification failed: {str(e)[:200]}"
