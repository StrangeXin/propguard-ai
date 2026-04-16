"""
Broker API adapter — connects to MT4/MT5 via MetaApi.
Supports multiple MetaApi accounts (one per Prop Firm).
"""

import asyncio
import logging
from datetime import datetime

from app.models.account import AccountState, Position
from app.config import get_settings

logger = logging.getLogger(__name__)


class MetaApiConnection:
    """Single MetaApi account connection."""

    def __init__(self, account_id: str):
        self.account_id = account_id
        self.api = None
        self.account = None
        self.connection = None
        self.ready = False

    async def connect(self, token: str) -> bool:
        try:
            from metaapi_cloud_sdk import MetaApi

            self.api = MetaApi(token)
            self.account = await self.api.metatrader_account_api.get_account(self.account_id)
            logger.info(f"MetaApi [{self.account_id[:8]}]: state={self.account.state}")

            if self.account.state != 'DEPLOYED':
                await self.account.deploy()
                await self.account.wait_deployed(timeout_in_seconds=15)

            self.connection = self.account.get_rpc_connection()
            await self.connection.connect()
            await self.connection.wait_synchronized(timeout_in_seconds=15)

            self.ready = True
            logger.info(f"MetaApi [{self.account_id[:8]}]: READY")
            return True
        except Exception as e:
            logger.error(f"MetaApi [{self.account_id[:8]}] failed: {e}")
            self.ready = False
            return False

    async def get_info(self) -> dict | None:
        if not self.ready or not self.connection:
            return None
        try:
            return await self.connection.get_account_information()
        except Exception as e:
            logger.error(f"MetaApi get_info: {e}")
            return None

    async def get_positions(self) -> list:
        if not self.ready or not self.connection:
            return []
        try:
            return await self.connection.get_positions()
        except Exception as e:
            logger.error(f"MetaApi get_positions: {e}")
            return []


class BrokerAPIClient:

    def __init__(self):
        self._settings = get_settings()
        self._connections: dict[str, MetaApiConnection] = {}
        self._default_conn: MetaApiConnection | None = None

        # Build account mapping: firm_name → MetaApi account_id
        self._account_map: dict[str, str] = {}
        if self._settings.ftmo_metaapi_account_id:
            self._account_map["ftmo"] = self._settings.ftmo_metaapi_account_id
        if self._settings.metaapi_account_id:
            self._account_map["_default"] = self._settings.metaapi_account_id

    async def connect(self) -> bool:
        if not self._settings.metaapi_token:
            return False

        token = self._settings.metaapi_token
        # Collect unique account IDs
        account_ids = set(self._account_map.values())

        for aid in account_ids:
            conn = MetaApiConnection(aid)
            if await conn.connect(token):
                self._connections[aid] = conn

        # Set default
        default_id = self._account_map.get("_default")
        if default_id and default_id in self._connections:
            self._default_conn = self._connections[default_id]

        logger.info(f"Broker: {len(self._connections)} connections ready")
        return len(self._connections) > 0

    def _get_connection(self, firm_name: str) -> MetaApiConnection | None:
        """Get the MetaApi connection for a specific firm."""
        aid = self._account_map.get(firm_name.lower())
        if aid and aid in self._connections:
            return self._connections[aid]
        return self._default_conn

    @property
    def is_metaapi_ready(self) -> bool:
        return len(self._connections) > 0

    @property
    def is_okx_ready(self) -> bool:
        return False

    async def get_account_state(self, account_id: str, firm_name: str, account_size: int) -> AccountState | None:
        conn = self._get_connection(firm_name)
        if not conn or not conn.ready:
            return None

        try:
            return await asyncio.wait_for(
                self._fetch_state(conn, account_id, firm_name, account_size), timeout=10
            )
        except asyncio.TimeoutError:
            logger.warning(f"Broker timeout: {firm_name}")
        except Exception as e:
            logger.error(f"Broker error: {e}")
        return None

    async def _fetch_state(self, conn: MetaApiConnection, account_id: str, firm_name: str, account_size: int) -> AccountState | None:
        info = await conn.get_info()
        if not info:
            return None

        mt_positions = await conn.get_positions()

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

        return AccountState(
            account_id=account_id,
            firm_name=firm_name,
            account_size=account_size,
            initial_balance=initial_balance,
            current_balance=round(balance, 2),
            current_equity=round(equity, 2),
            daily_pnl=round(unrealized_pnl, 2),
            total_pnl=round(total_pnl, 2),
            equity_high_watermark=round(max(initial_balance, equity), 2),
            open_positions=positions,
            trading_days_count=0,
            challenge_start_date=datetime.now(),
            last_updated=datetime.now(),
        )
