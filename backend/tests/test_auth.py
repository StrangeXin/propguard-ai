"""Tests for auth system — uses unique emails per run to avoid Supabase conflicts."""

import secrets
from app.services.auth import register_user, login_user, verify_token, _users_mem


def _unique_email(prefix: str) -> str:
    return f"{prefix}-{secrets.token_hex(4)}@test.propguard.ai"


class TestAuth:
    def setup_method(self):
        _users_mem.clear()

    def test_register(self):
        email = _unique_email("reg")
        user = register_user(email, "password123", "Test")
        assert user["email"] == email
        assert user["name"] == "Test"
        assert user["tier"] == "free"
        assert "password_hash" not in user

    def test_register_duplicate(self):
        email = _unique_email("dup")
        register_user(email, "password123")
        try:
            register_user(email, "password456")
            assert False, "Should have raised ValueError"
        except ValueError as e:
            assert "already registered" in str(e)

    def test_register_short_password(self):
        try:
            register_user(_unique_email("short"), "12345")
            assert False, "Should have raised ValueError"
        except ValueError as e:
            assert "6 characters" in str(e)

    def test_login(self):
        email = _unique_email("login")
        register_user(email, "password123", "Login User")
        result = login_user(email, "password123")
        assert "token" in result
        assert result["user"]["email"] == email

    def test_login_wrong_password(self):
        email = _unique_email("wrong")
        register_user(email, "password123")
        try:
            login_user(email, "wrongpass")
            assert False, "Should have raised ValueError"
        except ValueError:
            pass

    def test_verify_token(self):
        email = _unique_email("verify")
        register_user(email, "password123", "Verify")
        result = login_user(email, "password123")
        user = verify_token(result["token"])
        assert user is not None
        assert user["email"] == email

    def test_verify_invalid_token(self):
        user = verify_token("invalid.token.here")
        assert user is None


class TestMetaapiColumn:
    def test_registered_user_has_metaapi_account_id_none(self):
        email = _unique_email("meta")
        user = register_user(email, "password123")
        # Must be present as a key so downstream user_dict_to_owner can read it.
        assert "metaapi_account_id" in user
        assert user["metaapi_account_id"] is None


class TestUserToOwner:
    def test_free_user_without_metaapi(self):
        from app.services.auth import user_dict_to_owner
        user = {"id": "u-1", "email": "a@b.c", "tier": "free", "metaapi_account_id": None}
        o = user_dict_to_owner(user)
        assert o.id == "u-1"
        assert o.kind == "user"
        assert o.plan == "free"
        assert o.metaapi_account_id is None

    def test_pro_user_with_metaapi(self):
        from app.services.auth import user_dict_to_owner
        user = {"id": "u-2", "tier": "pro", "metaapi_account_id": "acct-xyz"}
        o = user_dict_to_owner(user)
        assert o.plan == "pro"
        assert o.metaapi_account_id == "acct-xyz"

    def test_missing_tier_defaults_free(self):
        from app.services.auth import user_dict_to_owner
        user = {"id": "u-3"}
        o = user_dict_to_owner(user)
        assert o.plan == "free"
        assert o.metaapi_account_id is None
