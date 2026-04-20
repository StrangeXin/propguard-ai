"""
Live Trading via MetaApi — places real orders on the connected MT5 account.
Currently connected to MT5 Demo (MetaQuotes-Demo), so all trades are simulated
by the broker. Switch to a live account to trade with real money.
"""

import logging
from app.config import get_settings

logger = logging.getLogger(__name__)


async def get_metaapi_connection(firm_name: str = "ftmo"):
    """Get the active MetaApi RPC connection from broker."""
    from app.api.routes import broker
    conn = broker._get_connection(firm_name)
    if conn and conn.ready and conn.connection:
        return conn.connection
    # Fallback to any available connection
    for c in broker._connections.values():
        if c.ready and c.connection:
            return c.connection
    return None


async def resolve_symbol(symbol: str, conn=None) -> str:
    """Resolve symbol name for the connected broker.
    FTMO uses .sim suffix (e.g. EURUSD.sim), other brokers use plain names.
    """
    if not conn:
        conn = await get_metaapi_connection()
    if not conn:
        return symbol

    # Try original first
    try:
        await conn.get_symbol_price(symbol)
        return symbol
    except Exception:
        pass

    # Try with .sim suffix (FTMO)
    sim = f"{symbol}.sim"
    try:
        await conn.get_symbol_price(sim)
        return sim
    except Exception:
        pass

    # Try with other common suffixes
    for suffix in [".pro", ".raw", ".m", ".z"]:
        try:
            await conn.get_symbol_price(f"{symbol}{suffix}")
            return f"{symbol}{suffix}"
        except Exception:
            pass

    return symbol


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
        # Resolve symbol name for this broker (e.g. EURUSD → EURUSD.sim for FTMO)
        resolved = await resolve_symbol(symbol, conn)

        result = await conn.create_market_buy_order(
            resolved, volume, stop_loss, take_profit
        ) if side == "buy" else await conn.create_market_sell_order(
            resolved, volume, stop_loss, take_profit
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


async def mt5_create_pending_order(
    symbol: str,
    side: str,
    volume: float,
    price: float,
    order_type: str = "limit",
    stop_loss: float | None = None,
    take_profit: float | None = None,
) -> dict:
    """Create a pending order (limit or stop)."""
    conn = await get_metaapi_connection()
    if not conn:
        return {"success": False, "error": "MetaApi not connected"}

    try:
        resolved = await resolve_symbol(symbol, conn)

        if order_type == "limit":
            if side == "buy":
                result = await conn.create_limit_buy_order(resolved, volume, price, stop_loss, take_profit)
            else:
                result = await conn.create_limit_sell_order(resolved, volume, price, stop_loss, take_profit)
        else:  # stop order
            if side == "buy":
                result = await conn.create_stop_buy_order(resolved, volume, price, stop_loss, take_profit)
            else:
                result = await conn.create_stop_sell_order(resolved, volume, price, stop_loss, take_profit)

        logger.info(f"MT5 pending order: {order_type} {side} {symbol} {volume} @ {price} → {result}")
        return {
            "success": True,
            "order_id": result.get("orderId", ""),
            "symbol": symbol,
            "side": side,
            "volume": volume,
            "price": price,
            "order_type": order_type,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
        }
    except Exception as e:
        logger.error(f"MT5 pending order failed: {e}")
        return {"success": False, "error": str(e)}


async def mt5_cancel_order(order_id: str) -> dict:
    """Cancel a pending order."""
    conn = await get_metaapi_connection()
    if not conn:
        return {"success": False, "error": "MetaApi not connected"}

    try:
        result = await conn.cancel_order(order_id)
        logger.info(f"MT5 order cancelled: {order_id}")
        return {"success": True, "order_id": order_id}
    except Exception as e:
        logger.error(f"MT5 cancel order failed: {e}")
        return {"success": False, "error": str(e)}


async def mt5_close_position_partially(position_id: str, volume: float) -> dict:
    """Partially close a position."""
    conn = await get_metaapi_connection()
    if not conn:
        return {"success": False, "error": "MetaApi not connected"}

    try:
        result = await conn.close_position_partially(position_id, volume)
        logger.info(f"MT5 partial close: {position_id} volume={volume} → {result}")
        return {"success": True, "position_id": position_id, "closed_volume": volume}
    except Exception as e:
        logger.error(f"MT5 partial close failed: {e}")
        return {"success": False, "error": str(e)}


async def mt5_get_symbol_spec(symbol: str) -> dict | None:
    """Get symbol specification (spread, contract size, min lot, etc.)."""
    conn = await get_metaapi_connection()
    if not conn:
        return None

    try:
        resolved = await resolve_symbol(symbol, conn)
        spec = await conn.get_symbol_specification(resolved)
        return {
            "symbol": spec.get("symbol"),
            "description": spec.get("description", ""),
            "currency": spec.get("currencyProfit", ""),
            "digits": spec.get("digits", 5),
            "contract_size": spec.get("contractSize", 100000),
            "min_volume": spec.get("volumeMin", 0.01),
            "max_volume": spec.get("volumeMax", 100),
            "volume_step": spec.get("volumeStep", 0.01),
            "spread": spec.get("spread"),
            "trade_mode": spec.get("tradeMode", ""),
        }
    except Exception as e:
        logger.error(f"MT5 symbol spec failed for {symbol}: {e}")
        return None


async def mt5_get_symbol_price(symbol: str) -> dict | None:
    """Get real-time bid/ask price for a symbol."""
    conn = await get_metaapi_connection()
    if not conn:
        return None

    try:
        resolved = await resolve_symbol(symbol, conn)
        price = await conn.get_symbol_price(resolved)
        return {
            "symbol": price.get("symbol"),
            "bid": price.get("bid"),
            "ask": price.get("ask"),
            "time": price.get("time"),
            "spread": round(price.get("ask", 0) - price.get("bid", 0), 6),
        }
    except Exception as e:
        logger.error(f"MT5 price failed for {symbol}: {e}")
        return None


async def mt5_get_trade_history(days: int = 30) -> list[dict]:
    """Get closed trade history."""
    conn = await get_metaapi_connection()
    if not conn:
        return []

    try:
        from datetime import datetime, timedelta, timezone
        start = datetime.now(timezone.utc) - timedelta(days=days)
        end = datetime.now(timezone.utc)

        result = await conn.get_deals_by_time_range(start, end)

        # MetaApi returns {"deals": [...], "synchronizing": bool}
        if isinstance(result, dict):
            deals = result.get("deals", [])
        elif isinstance(result, list):
            deals = result
        else:
            deals = []

        trades = []
        for d in deals:
            try:
                deal_type = d.get("type", "") if isinstance(d, dict) else getattr(d, "type", "")

                # Skip balance operations, only include actual trades
                if deal_type not in ("DEAL_TYPE_BUY", "DEAL_TYPE_SELL"):
                    continue

                def _g(key, default=""):
                    return d.get(key, default) if isinstance(d, dict) else getattr(d, key, default)

                trades.append({
                    "id": str(_g("id", "")),
                    "symbol": _g("symbol", ""),
                    "type": deal_type,
                    "side": "buy" if deal_type == "DEAL_TYPE_BUY" else "sell",
                    "volume": float(_g("volume", 0)),
                    "price": float(_g("price", 0)),
                    "profit": float(_g("profit", 0)),
                    "commission": float(_g("commission", 0)),
                    "swap": float(_g("swap", 0)),
                    "time": str(_g("time", "")),
                    "entry": str(_g("entryType", "")),
                    "orderId": str(_g("orderId", "")) or None,
                    "positionId": str(_g("positionId", "")) or None,
                })
            except Exception as e:
                logger.warning(f"Skipping deal: {e}")

        return trades
    except Exception as e:
        logger.error(f"MT5 trade history failed: {e}")
        return []


async def mt5_get_account_info() -> dict | None:
    """Get full account information."""
    conn = await get_metaapi_connection()
    if not conn:
        return None

    try:
        info = await conn.get_account_information()
        return {
            "broker": info.get("broker", ""),
            "server": info.get("server", ""),
            "balance": float(info.get("balance", 0)),
            "equity": float(info.get("equity", 0)),
            "margin": float(info.get("margin", 0)),
            "free_margin": float(info.get("freeMargin", 0)),
            "margin_level": float(info.get("marginLevel", 0)),
            "leverage": info.get("leverage", 0),
            "currency": info.get("currency", "USD"),
            "platform": info.get("platform", "mt5"),
            "type": info.get("type", ""),
        }
    except Exception as e:
        logger.error(f"MT5 account info failed: {e}")
        return None
