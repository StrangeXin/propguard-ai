"""
Broker API adapter — connects to MT4/MT5 via MetaApi and OKX for real account data.
No mock data. Returns None if not connected yet.
"""

import logging
from datetime import datetime

from app.models.account import AccountState, Position
from app.config import get_settings

logger = logging.getLogger(__name__)


class BrokerAPIClient:
    """Connects to MT4/MT5 via MetaApi and OKX. No mock fallback."""

    def __init__(self):
        self._settings = get_settings()
        self._api = None
        self._account = None
        self._connection = None
        self._metaapi_ready = False
        self._has_metaapi = bool(self._settings.metaapi_token and self._settings.metaapi_account_id)
        self._has_okx = bool(self._settings.okx_api_key)

    async def connect(self) -> bool:
        """Connect to all configured brokers."""
        success = False

        if self._has_metaapi:
            success = await self._connect_metaapi() or success

        if self._has_okx:
            # OKX doesn't need persistent connection, just API keys
            success = True

        return success

    async def _connect_metaapi(self) -> bool:
        try:
            from metaapi_cloud_sdk import MetaApi

            self._api = MetaApi(self._settings.metaapi_token)
            self._account = await self._api.metatrader_account_api.get_account(
                self._settings.metaapi_account_id
            )

            logger.info(f"MetaApi account state: {self._account.state}, connection: {self._account.connection_status}")

            if self._account.state == 'UNDEPLOYED':
                try:
                    await self._account.deploy()
                    await self._account.wait_deployed()
                except Exception as deploy_err:
                    logger.warning(f"Deploy failed: {deploy_err}")
                    self._account = await self._api.metatrader_account_api.get_account(
                        self._settings.metaapi_account_id
                    )

            if self._account.state == 'DEPLOYED':
                try:
                    await self._account.wait_connected(timeout_in_seconds=30)
                except Exception:
                    logger.warning("MetaApi wait_connected timed out, trying RPC anyway")

                self._connection = self._account.get_rpc_connection()
                await self._connection.connect()
                await self._connection.wait_synchronized(timeout_in_seconds=60)

                self._metaapi_ready = True
                logger.info("MetaApi connected successfully")
                return True

            raise Exception(f"Account not in DEPLOYED state: {self._account.state}")

        except Exception as e:
            logger.error(f"MetaApi connection failed: {e}")
            self._metaapi_ready = False
            return False

    @property
    def is_metaapi_ready(self) -> bool:
        return self._metaapi_ready

    @property
    def is_okx_ready(self) -> bool:
        return self._has_okx

    async def get_account_state(self, account_id: str, firm_name: str, account_size: int) -> AccountState | None:
        """Get real account state. Returns None if broker not connected yet."""

        # OKX for crypto prop firms
        if firm_name.lower() == "breakout" and self._has_okx:
            return await self._get_okx_state(account_id, firm_name, account_size)

        # MetaApi for forex/futures
        if self._metaapi_ready and self._connection:
            return await self._get_metaapi_state(account_id, firm_name, account_size)

        # Not connected yet
        return None

    async def _get_okx_state(self, account_id: str, firm_name: str, account_size: int) -> AccountState | None:
        try:
            from app.services.okx_client import get_okx_account_state
            return await get_okx_account_state(account_id, firm_name, account_size)
        except Exception as e:
            logger.error(f"OKX data fetch failed: {e}")
            return None

    async def _get_metaapi_state(self, account_id: str, firm_name: str, account_size: int) -> AccountState | None:
        try:
            info = await self._connection.get_account_information()
            mt_positions = await self._connection.get_positions()

            balance = float(info.get('balance', 0))
            equity = float(info.get('equity', 0))
            initial_balance = float(account_size)

            unrealized_pnl = equity - balance
            total_pnl = (balance - initial_balance) + unrealized_pnl

            positions = []
            for p in mt_positions:
                opened = datetime.now()
                if 'time' in p:
                    try:
                        opened = datetime.fromisoformat(str(p['time']))
                    except (ValueError, TypeError):
                        pass
                positions.append(Position(
                    symbol=p.get('symbol', ''),
                    side='long' if p.get('type') == 'POSITION_TYPE_BUY' else 'short',
                    size=float(p.get('volume', 0)),
                    entry_price=float(p.get('openPrice', 0)),
                    current_price=float(p.get('currentPrice', 0)),
                    unrealized_pnl=float(p.get('profit', 0)),
                    opened_at=opened,
                ))

            hwm = max(initial_balance, equity)

            return AccountState(
                account_id=account_id,
                firm_name=firm_name,
                account_size=account_size,
                initial_balance=initial_balance,
                current_balance=round(balance, 2),
                current_equity=round(equity, 2),
                daily_pnl=round(unrealized_pnl, 2),
                total_pnl=round(total_pnl, 2),
                equity_high_watermark=round(hwm, 2),
                open_positions=positions,
                trading_days_count=0,
                challenge_start_date=None,
                last_updated=datetime.now(),
            )

        except Exception as e:
            logger.error(f"MetaApi data fetch failed: {e}")
            return None
