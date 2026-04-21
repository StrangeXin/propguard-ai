"""
Live Trading via MetaApi — places real orders on the connected MT5 account.
Currently connected to MT5 Demo (MetaQuotes-Demo), so all trades are simulated
by the broker. Switch to a live account to trade with real money.
"""

import logging
import time
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


async def resolve_symbol(symbol: str, conn=None, account_conn=None) -> str:
    """Resolve symbol name for the connected broker.
    FTMO uses .sim suffix (e.g. EURUSD.sim), other brokers use plain names.
    Cached on the account-level MetaApiConnection wrapper so different
    broker accounts don't share each other's (wrong) resolutions.
    """
    # Pull the per-account wrapper from the api broker if caller didn't pass it
    if account_conn is None:
        try:
            from app.api.routes import broker as api_broker
            account_conn = api_broker._get_connection("ftmo") or api_broker._default_conn
        except Exception:
            account_conn = None

    if account_conn is not None and symbol in account_conn.symbol_resolved:
        return account_conn.symbol_resolved[symbol]

    if not conn:
        conn = await get_metaapi_connection()
    if not conn:
        return symbol

    candidates = [symbol, f"{symbol}.sim", f"{symbol}.pro", f"{symbol}.raw",
                  f"{symbol}.m", f"{symbol}.z"]
    for cand in candidates:
        try:
            await conn.get_symbol_price(cand)
            if account_conn is not None:
                account_conn.symbol_resolved[symbol] = cand
            return cand
        except Exception:
            continue

    # Couldn't resolve — don't poison the cache; next call can re-probe.
    return symbol


# Spec cache — specifications (digits, min_volume, etc.) never change at
# runtime. Cache for 60s so we don't hit MetaApi on every price tick.
_SYMBOL_SPEC_CACHE: dict[str, tuple[float, dict]] = {}
_SPEC_TTL_SECONDS = 60.0


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
                "time": str(p.get("time", "")) or None,
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
                "time": str(o.get("time", "")) or None,
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
    """Get symbol specification (spread, contract size, min lot, etc.).
    Cached for _SPEC_TTL_SECONDS since MetaApi specs don't change at runtime.
    """
    cached = _SYMBOL_SPEC_CACHE.get(symbol)
    if cached and (time.time() - cached[0]) < _SPEC_TTL_SECONDS:
        return cached[1]

    conn = await get_metaapi_connection()
    if not conn:
        return None

    try:
        resolved = await resolve_symbol(symbol, conn)
        spec = await conn.get_symbol_specification(resolved)
        out = {
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
        _SYMBOL_SPEC_CACHE[symbol] = (time.time(), out)
        return out
    except Exception as e:
        logger.error(f"MT5 symbol spec failed for {symbol}: {e}")
        return None


# Short-TTL price cache + in-flight deduplication.
# Multiple concurrent clients polling /api/trading/symbol/BTCUSD at the same
# instant will share a single MetaApi round-trip instead of stacking them up.
# 1.5s is tight enough that bid/ask still feels live (< one polling interval)
# but loose enough to cut N redundant requests to 1.
import asyncio as _asyncio
import time as _time

_PRICE_CACHE: dict[str, tuple[float, dict]] = {}
_PRICE_INFLIGHT: dict[str, _asyncio.Future] = {}
_PRICE_TTL_SECONDS = 1.5


async def mt5_get_symbol_price(symbol: str) -> dict | None:
    """Get real-time bid/ask price for a symbol.

    Uses a 1.5s in-memory cache with single-flight deduplication — if 10
    clients ask for BTCUSD within 1.5s, only the first one actually hits
    MetaApi; the other nine await the same future and get the same answer.
    """
    cached = _PRICE_CACHE.get(symbol)
    if cached and (_time.time() - cached[0]) < _PRICE_TTL_SECONDS:
        return cached[1]

    # Single-flight: if a fetch is already in flight for this symbol, wait
    # for it instead of firing a second one.
    inflight = _PRICE_INFLIGHT.get(symbol)
    if inflight is not None:
        try:
            return await inflight
        except Exception:
            return None

    loop = _asyncio.get_event_loop()
    fut: _asyncio.Future = loop.create_future()
    _PRICE_INFLIGHT[symbol] = fut

    try:
        conn = await get_metaapi_connection()
        if not conn:
            fut.set_result(None)
            return None
        resolved = await resolve_symbol(symbol, conn)
        raw = await conn.get_symbol_price(resolved)
        out = {
            "symbol": raw.get("symbol"),
            "bid": raw.get("bid"),
            "ask": raw.get("ask"),
            "time": raw.get("time"),
            "spread": round(raw.get("ask", 0) - raw.get("bid", 0), 6),
        }
        _PRICE_CACHE[symbol] = (_time.time(), out)
        fut.set_result(out)
        return out
    except Exception as e:
        logger.error(f"MT5 price failed for {symbol}: {e}")
        fut.set_result(None)
        return None
    finally:
        _PRICE_INFLIGHT.pop(symbol, None)


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
