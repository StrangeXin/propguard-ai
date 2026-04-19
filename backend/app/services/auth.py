"""
User authentication — JWT-based register/login with Supabase persistence.
Falls back to in-memory if Supabase is not available.
"""

import hashlib
import hmac
import secrets
import time
from datetime import datetime

import jwt

from app.models.owner import Owner
from app.services.database import db_create_user, db_get_user_by_email, db_get_user_by_id, db_update_user

JWT_SECRET = "propguard-jwt-secret-change-in-production"
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_HOURS = 72

# In-memory fallback
_users_mem: dict[str, dict] = {}


def _hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    h = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100000)
    return f"{salt}:{h.hex()}"


def _verify_password(password: str, stored: str) -> bool:
    salt, h = stored.split(":")
    check = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100000)
    return hmac.compare_digest(check.hex(), h)


def _safe_user(user: dict) -> dict:
    return {k: v for k, v in user.items() if k != "password_hash"}


def register_user(email: str, password: str, name: str = "") -> dict:
    email = email.lower().strip()
    if len(password) < 6:
        raise ValueError("Password must be at least 6 characters")

    # Check existing
    existing = db_get_user_by_email(email) or _users_mem.get(email)
    if existing:
        raise ValueError("Email already registered")

    pw_hash = _hash_password(password)
    user_name = name or email.split("@")[0]

    # Try Supabase first
    db_user = db_create_user(email, user_name, pw_hash)
    if db_user:
        return _safe_user(db_user)

    # Fallback to memory
    user = {
        "id": secrets.token_hex(8),
        "email": email,
        "name": user_name,
        "password_hash": pw_hash,
        "tier": "free",
        "telegram_chat_id": None,
        "metaapi_account_id": None,
        "created_at": datetime.now().isoformat(),
    }
    _users_mem[email] = user
    return _safe_user(user)


def login_user(email: str, password: str) -> dict:
    email = email.lower().strip()

    user = db_get_user_by_email(email) or _users_mem.get(email)
    if not user or not _verify_password(password, user["password_hash"]):
        raise ValueError("Invalid email or password")

    token = jwt.encode(
        {"user_id": user["id"], "email": user["email"], "exp": time.time() + JWT_EXPIRE_HOURS * 3600},
        JWT_SECRET,
        algorithm=JWT_ALGORITHM,
    )
    return {"token": token, "user": _safe_user(user)}


def verify_token(token: str) -> dict | None:
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        email = payload.get("email")
        user = db_get_user_by_email(email) or _users_mem.get(email)
        if user:
            return _safe_user(user)
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
        pass
    return None


def get_user_by_id(user_id: str) -> dict | None:
    user = db_get_user_by_id(user_id)
    if user:
        return _safe_user(user)
    for u in _users_mem.values():
        if u["id"] == user_id:
            return _safe_user(u)
    return None


def update_user(user_id: str, updates: dict) -> dict | None:
    result = db_update_user(user_id, updates)
    if result:
        return _safe_user(result)
    for email, u in _users_mem.items():
        if u["id"] == user_id:
            for k, v in updates.items():
                if k not in ("id", "email", "password_hash"):
                    u[k] = v
            return _safe_user(u)
    return None


def link_telegram(user_id: str, chat_id: str) -> bool:
    result = db_update_user(user_id, {"telegram_chat_id": chat_id})
    if result:
        return True
    for u in _users_mem.values():
        if u["id"] == user_id:
            u["telegram_chat_id"] = chat_id
            return True
    return False


def user_dict_to_owner(user: dict) -> Owner:
    """Map a user row (from DB or in-memory) to an Owner."""
    return Owner(
        id=user["id"],
        kind="user",
        plan=user.get("tier") or "free",
        metaapi_account_id=user.get("metaapi_account_id"),
    )
