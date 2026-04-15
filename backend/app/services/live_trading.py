"""
Live Trading via MetaApi — places real orders on the connected MT5 account.
Currently connected to MT5 Demo (MetaQuotes-Demo), so all trades are simulated
by the broker. Switch to a live account to trade with real money.
"""

import logging
from app.config import get_settings

logger = logging.getLogger(__name__)


async def get_metaapi_connection():
    """Get the active MetaApi RPC connection from broker."""
    from app.api.routes import broker
    if broker._connection and broker._metaapi_ready:
        return broker._connection
    return None


async def mt5_place_order(
    symbol: str,
    side: str,
    volume: float,
    stop_loss: float | None = None,
    take_profit: float | None = None,
) -> dict:
    """Place a market order on MT5 via MetaApi."""
    conn = await get_metaapi_connection()
    if not conn:
        return {"success": False, "error": "MetaApi not connected"}

    try:
        action_type = "ORDER_TYPE_BUY" if side == "buy" else "ORDER_TYPE_SELL"

        order_params = {
            "symbol": symbol,
            "actionType": action_type,
            "volume": volume,
        }
        if stop_loss is not None:
            order_params["stopLoss"] = stop_loss
        if take_profit is not None:
            order_params["takeProfit"] = take_profit

        result = await conn.create_market_buy_order(
            symbol, volume, stop_loss, take_profit
        ) if side == "buy" else await conn.create_market_sell_order(
            symbol, volume, stop_loss, take_profit
        )

        logger.info(f"MT5 order placed: {side} {symbol} {volume} → {result}")

        return {
            "success": True,
            "order_id": result.get("orderId", result.get("positionId", "")),
            "symbol": symbol,
            "side": side,
            "volume": volume,
            "price": result.get("price", 0),
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "comment": result.get("comment", ""),
            "source": "metaapi_mt5",
        }

    except Exception as e:
        logger.error(f"MT5 order failed: {e}")
        return {"success": False, "error": str(e)}


async def mt5_close_position(position_id: str) -> dict:
    """Close a position on MT5."""
    conn = await get_metaapi_connection()
    if not conn:
        return {"success": False, "error": "MetaApi not connected"}

    try:
        result = await conn.close_position(position_id)
        logger.info(f"MT5 position closed: {position_id} → {result}")
        return {"success": True, "result": result}
    except Exception as e:
        logger.error(f"MT5 close failed: {e}")
        return {"success": False, "error": str(e)}


async def mt5_modify_position(
    position_id: str,
    stop_loss: float | None = None,
    take_profit: float | None = None,
) -> dict:
    """Modify SL/TP of an existing MT5 position."""
    conn = await get_metaapi_connection()
    if not conn:
        return {"success": False, "error": "MetaApi not connected"}

    try:
        result = await conn.modify_position(position_id, stop_loss, take_profit)
        logger.info(f"MT5 position modified: {position_id} → SL={stop_loss} TP={take_profit}")
        return {"success": True, "result": result}
    except Exception as e:
        logger.error(f"MT5 modify failed: {e}")
        return {"success": False, "error": str(e)}


async def mt5_get_positions() -> list[dict]:
    """Get all open positions from MT5."""
    conn = await get_metaapi_connection()
    if not conn:
        return []

    try:
        positions = await conn.get_positions()
        return [
            {
                "id": str(p.get("id", "")),
                "symbol": p.get("symbol", ""),
                "side": "long" if p.get("type") == "POSITION_TYPE_BUY" else "short",
                "volume": p.get("volume", 0),
                "entry_price": p.get("openPrice", 0),
                "current_price": p.get("currentPrice", 0),
                "stop_loss": p.get("stopLoss"),
                "take_profit": p.get("takeProfit"),
                "profit": p.get("profit", 0),
                "swap": p.get("swap", 0),
                "commission": p.get("commission", 0),
            }
            for p in positions
        ]
    except Exception as e:
        logger.error(f"MT5 get positions failed: {e}")
        return []


async def mt5_get_orders() -> list[dict]:
    """Get pending orders from MT5."""
    conn = await get_metaapi_connection()
    if not conn:
        return []

    try:
        orders = await conn.get_orders()
        return [
            {
                "id": str(o.get("id", "")),
                "symbol": o.get("symbol", ""),
                "type": o.get("type", ""),
                "volume": o.get("volume", 0),
                "price": o.get("openPrice", 0),
                "stop_loss": o.get("stopLoss"),
                "take_profit": o.get("takeProfit"),
            }
            for o in orders
        ]
    except Exception as e:
        logger.error(f"MT5 get orders failed: {e}")
        return []
