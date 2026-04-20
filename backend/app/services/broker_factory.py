"""Factory picks the right BrokerBase for a given Owner.

All paths route through MetaApi now. Unbound owners (anon or logged-in
without their own broker account) share the default MetaApi demo at
settings.metaapi_account_id. Bound owners get their own MetaApi account.

There is no sandbox fallback — MetaApi must be configured for the app to
function. In local dev without MetaApi, endpoints will raise.
"""

from app.config import get_settings
from app.models.owner import Owner
from app.services.broker_base import BrokerBase
from app.services.metaapi_broker import MetaApiBroker


def get_broker(owner: Owner) -> BrokerBase:
    if owner.metaapi_account_id:
        return MetaApiBroker(owner.metaapi_account_id)
    settings = get_settings()
    if not settings.metaapi_account_id:
        raise RuntimeError(
            "MetaApi is not configured (settings.metaapi_account_id is empty). "
            "The shared public account requires a configured MetaApi demo account."
        )
    return MetaApiBroker(settings.metaapi_account_id)
