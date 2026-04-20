"""AES-GCM encryption for at-rest secrets (user MetaApi API tokens).

Key is read from env `METAAPI_TOKEN_ENC_KEY` (base64-encoded 32 bytes).
If unset, encryption is a no-op — values stored plaintext with a `pt:`
prefix. Staging OK; production startup must assert the key is present.

Rotating the key invalidates every previously-stored ciphertext —
plan accordingly.
"""

import base64
import os
import secrets

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


def _key() -> bytes | None:
    raw = os.getenv("METAAPI_TOKEN_ENC_KEY", "")
    if not raw:
        return None
    try:
        k = base64.b64decode(raw)
        return k if len(k) == 32 else None
    except Exception:
        return None


def encrypt(plaintext: str) -> str:
    """Returns base64(nonce || ciphertext). Prefixes `pt:` when key unset."""
    key = _key()
    if key is None:
        return "pt:" + plaintext
    aes = AESGCM(key)
    nonce = secrets.token_bytes(12)
    ct = aes.encrypt(nonce, plaintext.encode(), None)
    return base64.b64encode(nonce + ct).decode()


def decrypt(stored: str) -> str | None:
    """Returns plaintext, or None if decryption fails."""
    if stored.startswith("pt:"):
        return stored[3:]
    key = _key()
    if key is None:
        return None
    try:
        raw = base64.b64decode(stored)
        nonce, ct = raw[:12], raw[12:]
        return AESGCM(key).decrypt(nonce, ct, None).decode()
    except Exception:
        return None
