"""
OKX Account API client — fetches real account balance, positions, and P&L
from OKX exchange for crypto trading.
"""

import hmac
import hashlib
import base64
import json
import logging
from datetime import datetime, timezone

import httpx

from app.models.account import AccountState, Position
from app.config import get_settings

logger = logging.getLogger(__name__)

BASE_URL = "https://www.okx.com"
DEMO_URL = "https://www.okx.com"  # same URL, different header flag


def _sign(timestamp: str, method: str, path: str, body: str, secret: str) -> str:
    """Generate OKX API signature."""
    message = timestamp + method + path + body
    mac = hmac.new(secret.encode(), message.encode(), hashlib.sha256)
    return base64.b64encode(mac.digest()).decode()


def _headers(method: str, path: str, body: str = "") -> dict:
    settings = get_settings()
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.") + \
         f"{datetime.now(timezone.utc).microsecond // 1000:03d}Z"

    sign = _sign(ts, method, path, body, settings.okx_secret_key)

    headers = {
        "OK-ACCESS-KEY": settings.okx_api_key,
        "OK-ACCESS-SIGN": sign,
        "OK-ACCESS-TIMESTAMP": ts,
        "OK-ACCESS-PASSPHRASE": settings.okx_passphrase,
        "Content-Type": "application/json",
    }
    if settings.okx_demo:
        headers["x-simulated-trading"] = "1"

    return headers


async def get_okx_balance() -> dict | None:
    """Fetch total account balance from OKX."""
    path = "/api/v5/account/balance"
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"{BASE_URL}{path}",
                headers=_headers("GET", path),
            )
            resp.raise_for_status()
            data = resp.json()

        if data.get("code") == "0" and data.get("data"):
            bal = data["data"][0]
            _f = lambda v: float(v) if v and v != "" else 0.0
            return {
                "total_equity": _f(bal.get("totalEq")),
                "available_balance": _f(bal.get("availBal")) or _f(bal.get("totalEq")),
                "unrealized_pnl": _f(bal.get("upl")),
                "currency": "USD",
                "details": [
                    {
                        "currency": d.get("ccy"),
                        "equity": _f(d.get("eq")),
                        "available": _f(d.get("availBal")),
                        "frozen": _f(d.get("frozenBal")),
                        "unrealized_pnl": _f(d.get("upl")),
                    }
                    for d in bal.get("details", [])
                    if _f(d.get("eq")) > 0
                ],
            }
    except Exception as e:
        logger.error(f"OKX balance fetch failed: {e}")
    return None


async def get_okx_positions() -> list[dict]:
    """Fetch open positions from OKX."""
    path = "/api/v5/account/positions"
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"{BASE_URL}{path}",
                headers=_headers("GET", path),
            )
            resp.raise_for_status()
            data = resp.json()

        if data.get("code") == "0" and data.get("data"):
            positions = []
            for p in data["data"]:
                pos_size = float(p.get("pos", 0))
                if pos_size == 0:
                    continue
                positions.append({
                    "symbol": p.get("instId", "").replace("-", ""),
                    "side": "long" if p.get("posSide") == "long" or pos_size > 0 else "short",
                    "size": abs(pos_size),
                    "entry_price": float(p.get("avgPx", 0)),
                    "current_price": float(p.get("markPx", 0) or p.get("last", 0)),
                    "unrealized_pnl": float(p.get("upl", 0)),
                    "leverage": p.get("lever", "1"),
                    "inst_type": p.get("instType"),
                })
            return positions
    except Exception as e:
        logger.error(f"OKX positions fetch failed: {e}")
    return []


async def get_okx_account_state(
    account_id: str, firm_name: str, account_size: int
) -> AccountState | None:
    """Build full AccountState from OKX API data."""
    balance = await get_okx_balance()
    if balance is None:
        return None

    positions_raw = await get_okx_positions()

    equity = balance["total_equity"]
    initial_balance = float(account_size)
    unrealized = balance["unrealized_pnl"]
    total_pnl = equity - initial_balance

    positions = [
        Position(
            symbol=p["symbol"],
            side=p["side"],
            size=p["size"],
            entry_price=p["entry_price"],
            current_price=p["current_price"],
            unrealized_pnl=p["unrealized_pnl"],
            opened_at=datetime.now(),
        )
        for p in positions_raw
    ]

    return AccountState(
        account_id=account_id,
        firm_name=firm_name,
        account_size=account_size,
        initial_balance=initial_balance,
        current_balance=round(equity - unrealized, 2),
        current_equity=round(equity, 2),
        daily_pnl=round(unrealized, 2),
        total_pnl=round(total_pnl, 2),
        equity_high_watermark=round(max(initial_balance, equity), 2),
        open_positions=positions,
        trading_days_count=0,
        challenge_start_date=None,
        last_updated=datetime.now(),
    )
