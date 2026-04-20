"""test_metaapi_account wraps MetaApi SDK errors into user-safe messages."""

import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.metaapi_admin import verify_metaapi_account


def _patch_sdk(fake_api):
    """Install a fake metaapi_cloud_sdk module so import works in tests."""
    module = MagicMock()
    module.MetaApi = MagicMock(return_value=fake_api)
    return patch.dict(sys.modules, {"metaapi_cloud_sdk": module})


class TestMetaApiAdmin:
    @pytest.mark.asyncio
    async def test_success_returns_state(self):
        fake_account = MagicMock(state="DEPLOYED")
        fake_api = MagicMock()
        fake_api.metatrader_account_api.get_account = AsyncMock(return_value=fake_account)
        with patch("app.services.metaapi_admin.get_settings") as s, _patch_sdk(fake_api):
            s.return_value.metaapi_token = "x"
            ok, msg = await verify_metaapi_account("acc-123456789012345678901234")
            assert ok
            assert "DEPLOYED" in msg

    @pytest.mark.asyncio
    async def test_missing_token(self):
        with patch("app.services.metaapi_admin.get_settings") as s:
            s.return_value.metaapi_token = ""
            ok, msg = await verify_metaapi_account("acc-x")
            assert not ok
            assert "not configured" in msg.lower()

    @pytest.mark.asyncio
    async def test_draft_state_rejected(self):
        fake_account = MagicMock(state="DRAFT")
        fake_api = MagicMock()
        fake_api.metatrader_account_api.get_account = AsyncMock(return_value=fake_account)
        with patch("app.services.metaapi_admin.get_settings") as s, _patch_sdk(fake_api):
            s.return_value.metaapi_token = "x"
            ok, msg = await verify_metaapi_account("acc-123456789012345678901234")
            assert not ok
            assert "DRAFT" in msg

    @pytest.mark.asyncio
    async def test_not_found(self):
        fake_api = MagicMock()
        fake_api.metatrader_account_api.get_account = AsyncMock(
            side_effect=Exception("Account not found"))
        with patch("app.services.metaapi_admin.get_settings") as s, _patch_sdk(fake_api):
            s.return_value.metaapi_token = "x"
            ok, msg = await verify_metaapi_account("acc-xxxxxxxxxxxxxxxxxxxxxxxx")
            assert not ok
            assert "not found" in msg.lower()

    @pytest.mark.asyncio
    async def test_timeout(self):
        fake_api = MagicMock()
        fake_api.metatrader_account_api.get_account = AsyncMock(
            side_effect=__import__("asyncio").TimeoutError())
        with patch("app.services.metaapi_admin.get_settings") as s, _patch_sdk(fake_api):
            s.return_value.metaapi_token = "x"
            ok, msg = await verify_metaapi_account("acc-xxxxxxxxxxxxxxxxxxxxxxxx")
            assert not ok
            assert "timed out" in msg.lower()


class TestVerifyWithUserToken:
    @pytest.mark.asyncio
    async def test_missing_token_rejected(self):
        from app.services.metaapi_admin import verify_with_user_token
        ok, msg = await verify_with_user_token("acc-xxxxxxxxxxxxxxxxxxxxxxxx", "")
        assert not ok
        assert "token" in msg.lower()

    @pytest.mark.asyncio
    async def test_short_token_rejected(self):
        from app.services.metaapi_admin import verify_with_user_token
        ok, msg = await verify_with_user_token("acc-xxxxxxxxxxxxxxxxxxxxxxxx", "tiny")
        assert not ok

    @pytest.mark.asyncio
    async def test_unauthorized_token(self):
        from app.services.metaapi_admin import verify_with_user_token
        fake_api = MagicMock()
        fake_api.metatrader_account_api.get_account = AsyncMock(
            side_effect=Exception("401 unauthorized"))
        with _patch_sdk(fake_api):
            ok, msg = await verify_with_user_token(
                "acc-xxxxxxxxxxxxxxxxxxxxxxxx",
                "user-token-xxxxxxxxxxxxxxxxxx",
            )
            assert not ok
            assert "rejected" in msg.lower()

    @pytest.mark.asyncio
    async def test_not_found_under_token(self):
        from app.services.metaapi_admin import verify_with_user_token
        fake_api = MagicMock()
        fake_api.metatrader_account_api.get_account = AsyncMock(
            side_effect=Exception("404 account not found"))
        with _patch_sdk(fake_api):
            ok, msg = await verify_with_user_token(
                "acc-xxxxxxxxxxxxxxxxxxxxxxxx",
                "user-token-xxxxxxxxxxxxxxxxxx",
            )
            assert not ok
            assert "workspace" in msg.lower() or "reachable" in msg.lower()

    @pytest.mark.asyncio
    async def test_success(self):
        from app.services.metaapi_admin import verify_with_user_token
        fake_account = MagicMock(state="DEPLOYED")
        fake_api = MagicMock()
        fake_api.metatrader_account_api.get_account = AsyncMock(return_value=fake_account)
        with _patch_sdk(fake_api):
            ok, msg = await verify_with_user_token(
                "acc-xxxxxxxxxxxxxxxxxxxxxxxx",
                "user-token-xxxxxxxxxxxxxxxxxx",
            )
            assert ok
            assert "DEPLOYED" in msg
