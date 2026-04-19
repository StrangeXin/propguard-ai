"""BrokerFactory picks the right implementation based on Owner."""

from app.models.owner import Owner
from app.services.broker_factory import get_broker
from app.services.metaapi_broker import MetaApiBroker
from app.services.sandbox_broker import SandboxBroker


class TestBrokerFactory:
    def test_owner_without_metaapi_gets_sandbox(self):
        owner = Owner(id="u-1", kind="user", plan="free", metaapi_account_id=None)
        broker = get_broker(owner)
        assert isinstance(broker, SandboxBroker)

    def test_owner_with_metaapi_gets_metaapi(self):
        owner = Owner(id="u-2", kind="user", plan="pro", metaapi_account_id="acc-xyz")
        broker = get_broker(owner)
        assert isinstance(broker, MetaApiBroker)

    def test_anon_always_gets_sandbox(self):
        owner = Owner(id="a-1", kind="anon", plan="anon", metaapi_account_id=None)
        broker = get_broker(owner)
        assert isinstance(broker, SandboxBroker)
