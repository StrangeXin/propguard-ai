"""Factory picks the right BrokerBase for a given Owner.

Routing:
  - Bound (owner.metaapi_account_id non-null) → MetaApiBroker with that id.
  - Unbound but MetaApi configured → MetaApiBroker with settings.metaapi_account_id
    (the shared public account — see shared-public-account design doc).
  - Unbound with no MetaApi config → SandboxBroker (local-dev fallback).
"""

from app.config import get_settings
from app.models.owner import Owner
from app.services.broker_base import BrokerBase
from app.services.metaapi_broker import MetaApiBroker
from app.services.sandbox_broker import SandboxBroker


def get_broker(owner: Owner) -> BrokerBase:
    if owner.metaapi_account_id:
        return MetaApiBroker(owner.metaapi_account_id)
    settings = get_settings()
    if settings.metaapi_account_id:
        return MetaApiBroker(settings.metaapi_account_id)
    return SandboxBroker(owner)
