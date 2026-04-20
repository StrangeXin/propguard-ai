"""broker_factory picks the right BrokerBase for an Owner."""

from unittest.mock import patch, MagicMock

from app.models.owner import Owner
from app.services.broker_factory import get_broker
from app.services.metaapi_broker import MetaApiBroker


def _owner(metaapi_account_id=None, kind="user"):
    plan = "anon" if kind == "anon" else "free"
    return Owner(id="u1", kind=kind, plan=plan, metaapi_account_id=metaapi_account_id)


def test_bound_owner_routes_to_metaapi_with_their_account():
    broker = get_broker(_owner(metaapi_account_id="acc-bound"))
    assert isinstance(broker, MetaApiBroker)
    assert broker._account_id == "acc-bound"


def test_unbound_owner_routes_to_shared_metaapi_when_configured():
    mock_settings = MagicMock(metaapi_account_id="acc-shared")
    with patch("app.services.broker_factory.get_settings", return_value=mock_settings):
        broker = get_broker(_owner())
    assert isinstance(broker, MetaApiBroker)
    assert broker._account_id == "acc-shared"


def test_unbound_anon_also_routes_to_shared_metaapi():
    mock_settings = MagicMock(metaapi_account_id="acc-shared")
    with patch("app.services.broker_factory.get_settings", return_value=mock_settings):
        broker = get_broker(_owner(kind="anon"))
    assert isinstance(broker, MetaApiBroker)
    assert broker._account_id == "acc-shared"


def test_unbound_owner_raises_when_metaapi_not_configured():
    import pytest
    mock_settings = MagicMock(metaapi_account_id="")
    with patch("app.services.broker_factory.get_settings", return_value=mock_settings):
        with pytest.raises(RuntimeError, match="MetaApi is not configured"):
            get_broker(_owner())
