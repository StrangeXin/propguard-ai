"""Tests for the Owner value object."""

import pytest

from app.models.owner import Owner


class TestOwner:
    def test_user_owner(self):
        o = Owner(id="u-1", kind="user", plan="pro", metaapi_account_id="acct-123")
        assert o.kind == "user"
        assert o.plan == "pro"
        assert o.metaapi_account_id == "acct-123"

    def test_anon_owner(self):
        o = Owner(id="a-1", kind="anon", plan="anon", metaapi_account_id=None)
        assert o.kind == "anon"
        assert o.metaapi_account_id is None

    def test_anon_kind_must_have_anon_plan(self):
        with pytest.raises(ValueError, match="anon owners must have plan='anon'"):
            Owner(id="a-1", kind="anon", plan="pro", metaapi_account_id=None)

    def test_anon_cannot_have_metaapi_binding(self):
        with pytest.raises(ValueError, match="anon owners cannot bind metaapi"):
            Owner(id="a-1", kind="anon", plan="anon", metaapi_account_id="acct-1")

    def test_frozen(self):
        o = Owner(id="u-1", kind="user", plan="free", metaapi_account_id=None)
        with pytest.raises(Exception):  # FrozenInstanceError or AttributeError
            o.plan = "pro"
