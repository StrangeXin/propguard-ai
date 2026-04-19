"""Factory picks the right BrokerBase for a given Owner.

This is the single entry point used by every trading endpoint.
"""

from app.models.owner import Owner
from app.services.broker_base import BrokerBase
from app.services.metaapi_broker import MetaApiBroker
from app.services.sandbox_broker import SandboxBroker


def get_broker(owner: Owner) -> BrokerBase:
    if owner.metaapi_account_id:
        return MetaApiBroker(owner.metaapi_account_id)
    return SandboxBroker(owner)
