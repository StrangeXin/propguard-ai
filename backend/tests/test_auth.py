"""Tests for auth system (in-memory fallback mode)."""

from app.services.auth import register_user, login_user, verify_token, _users_mem


class TestAuth:
    def setup_method(self):
        _users_mem.clear()

    def test_register(self):
        user = register_user("test@test.com", "password123", "Test")
        assert user["email"] == "test@test.com"
        assert user["name"] == "Test"
        assert user["tier"] == "free"
        assert "password_hash" not in user

    def test_register_duplicate(self):
        register_user("dup@test.com", "password123")
        try:
            register_user("dup@test.com", "password456")
            assert False, "Should have raised ValueError"
        except ValueError as e:
            assert "already registered" in str(e)

    def test_register_short_password(self):
        try:
            register_user("short@test.com", "12345")
            assert False, "Should have raised ValueError"
        except ValueError as e:
            assert "6 characters" in str(e)

    def test_login(self):
        register_user("login@test.com", "password123", "Login User")
        result = login_user("login@test.com", "password123")
        assert "token" in result
        assert result["user"]["email"] == "login@test.com"

    def test_login_wrong_password(self):
        register_user("wrong@test.com", "password123")
        try:
            login_user("wrong@test.com", "wrongpass")
            assert False, "Should have raised ValueError"
        except ValueError:
            pass

    def test_verify_token(self):
        register_user("verify@test.com", "password123", "Verify")
        result = login_user("verify@test.com", "password123")
        user = verify_token(result["token"])
        assert user is not None
        assert user["email"] == "verify@test.com"

    def test_verify_invalid_token(self):
        user = verify_token("invalid.token.here")
        assert user is None
