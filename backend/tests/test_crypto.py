"""AES-GCM roundtrip + plaintext fallback tests."""

import base64
import os
from unittest.mock import patch

from app.services.crypto import encrypt, decrypt


class TestCrypto:
    def test_roundtrip_with_key(self):
        key = base64.b64encode(b"\x00" * 32).decode()
        with patch.dict(os.environ, {"METAAPI_TOKEN_ENC_KEY": key}):
            ct = encrypt("my-secret-token")
            assert not ct.startswith("pt:")
            assert decrypt(ct) == "my-secret-token"

    def test_no_key_falls_back_to_plaintext(self):
        with patch.dict(os.environ, {"METAAPI_TOKEN_ENC_KEY": ""}):
            ct = encrypt("secret")
            assert ct.startswith("pt:")
            assert decrypt(ct) == "secret"

    def test_wrong_length_key_falls_back(self):
        short = base64.b64encode(b"\x00" * 16).decode()
        with patch.dict(os.environ, {"METAAPI_TOKEN_ENC_KEY": short}):
            ct = encrypt("s")
            assert ct.startswith("pt:")

    def test_malformed_ciphertext_returns_none(self):
        key = base64.b64encode(b"\x00" * 32).decode()
        with patch.dict(os.environ, {"METAAPI_TOKEN_ENC_KEY": key}):
            assert decrypt("garbage-not-base64!") is None
