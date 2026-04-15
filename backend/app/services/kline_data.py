"""
K-line / candlestick data provider.
Uses public APIs for real market data:
  - Binance: crypto (BTCUSDT, ETHUSDT, SOLUSDT, etc.) — free, no key
  - ExchangeRate + fallback: forex pairs
Falls back to mock data if API calls fail.
"""

import logging
import random
from datetime import datetime, timedelta

import httpx

logger = logging.getLogger(__name__)

# Binance symbol mapping (our symbol → Binance symbol)
BINANCE_SYMBOLS = {
    "BTCUSD": "BTCUSDT",
    "ETHUSD": "ETHUSDT",
    "SOLUSD": "SOLUSDT",
    "XRPUSD": "XRPUSDT",
    "DOGEUSD": "DOGEUSDT",
    "ADAUSD": "ADAUSDT",
    "LINKUSD": "LINKUSDT",
    "AVAXUSD": "AVAXUSDT",
    "BTCUSDT": "BTCUSDT",
    "ETHUSDT": "ETHUSDT",
}

# Binance kline interval mapping
BINANCE_INTERVALS = {
    "1m": "1m", "5m": "5m", "15m": "15m", "30m": "30m",
    "1h": "1h", "4h": "4h", "1d": "1d", "1w": "1w",
}

# Forex / commodity symbols that need a different source
FOREX_SYMBOLS = {"EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD", "NZDUSD", "USDCHF", "GBPJPY", "EURJPY"}
COMMODITY_SYMBOLS = {"XAUUSD"}
INDEX_SYMBOLS = {"NAS100", "US30", "SPX500"}


async def fetch_crypto_klines(symbol: str, interval: str, limit: int) -> list[dict] | None:
    """
    Fetch crypto K-line data. Tries multiple public APIs in order:
    1. OKX (no geo-restriction)
    2. Binance (may be blocked in some regions)
    """
    # OKX symbol mapping
    okx_symbols = {
        "BTCUSD": "BTC-USDT", "BTCUSDT": "BTC-USDT",
        "ETHUSD": "ETH-USDT", "ETHUSDT": "ETH-USDT",
        "SOLUSD": "SOL-USDT", "SOLUSDT": "SOL-USDT",
        "XRPUSD": "XRP-USDT", "XRPUSDT": "XRP-USDT",
        "DOGEUSD": "DOGE-USDT", "DOGEUSDT": "DOGE-USDT",
        "ADAUSD": "ADA-USDT", "ADAUSDT": "ADA-USDT",
        "LINKUSD": "LINK-USDT", "LINKUSDT": "LINK-USDT",
        "AVAXUSD": "AVAX-USDT", "AVAXUSDT": "AVAX-USDT",
    }
    okx_intervals = {
        "1m": "1m", "5m": "5m", "15m": "15m", "30m": "30m",
        "1h": "1H", "4h": "4H", "1d": "1D", "1w": "1W",
    }

    sym = symbol.upper()

    # Try OKX first
    okx_sym = okx_symbols.get(sym)
    okx_bar = okx_intervals.get(interval)
    if okx_sym and okx_bar:
        try:
            url = "https://www.okx.com/api/v5/market/candles"
            params = {"instId": okx_sym, "bar": okx_bar, "limit": str(min(limit, 300))}
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(url, params=params)
                resp.raise_for_status()
                data = resp.json()

            if data.get("code") == "0" and data.get("data"):
                bars = []
                for k in reversed(data["data"]):  # OKX returns newest first
                    bars.append({
                        "timestamp": int(k[0]),
                        "open": float(k[1]),
                        "high": float(k[2]),
                        "low": float(k[3]),
                        "close": float(k[4]),
                        "volume": float(k[5]),
                    })
                if bars:
                    logger.info(f"OKX: {sym} {interval} → {len(bars)} bars")
                    return bars
        except Exception as e:
            logger.warning(f"OKX API failed for {sym}: {e}")

    # Fallback: try Binance
    binance_symbol = BINANCE_SYMBOLS.get(sym)
    binance_interval = BINANCE_INTERVALS.get(interval)
    if binance_symbol and binance_interval:
        try:
            url = "https://api.binance.com/api/v3/klines"
            params = {"symbol": binance_symbol, "interval": binance_interval, "limit": min(limit, 1000)}
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(url, params=params)
                resp.raise_for_status()
                raw = resp.json()

            bars = [
                {
                    "timestamp": int(k[0]),
                    "open": float(k[1]),
                    "high": float(k[2]),
                    "low": float(k[3]),
                    "close": float(k[4]),
                    "volume": float(k[5]),
                }
                for k in raw
            ]
            if bars:
                logger.info(f"Binance: {sym} {interval} → {len(bars)} bars")
                return bars
        except Exception as e:
            logger.warning(f"Binance API failed for {sym}: {e}")

    return None


async def fetch_forex_klines(symbol: str, interval: str, limit: int) -> tuple[list[dict] | None, str]:
    """
    Fetch forex K-line data.
    1. Twelve Data (real OHLCV, requires free API key)
    2. ExchangeRate API fallback (real current rate + simulated history)
    Returns (bars, source_label) or (None, "").
    """
    from app.config import get_settings
    settings = get_settings()

    # --- Try Twelve Data first (real historical OHLCV) ---
    if settings.twelvedata_api_key:
        td_intervals = {
            "1m": "1min", "5m": "5min", "15m": "15min", "30m": "30min",
            "1h": "1h", "4h": "4h", "1d": "1day", "1w": "1week",
        }
        td_interval = td_intervals.get(interval)
        # Twelve Data wants "EUR/USD" format
        td_symbol = f"{symbol[:3]}/{symbol[3:]}" if len(symbol) == 6 else symbol

        if td_interval:
            try:
                url = "https://api.twelvedata.com/time_series"
                params = {
                    "symbol": td_symbol,
                    "interval": td_interval,
                    "outputsize": str(min(limit, 500)),
                    "apikey": settings.twelvedata_api_key,
                }
                async with httpx.AsyncClient(timeout=15) as client:
                    resp = await client.get(url, params=params)
                    resp.raise_for_status()
                    data = resp.json()

                if data.get("status") == "ok" and data.get("values"):
                    bars = []
                    for v in reversed(data["values"]):  # oldest first
                        from datetime import datetime as dt
                        ts = int(dt.strptime(v["datetime"], "%Y-%m-%d %H:%M:%S").timestamp() * 1000) if " " in v["datetime"] else int(dt.strptime(v["datetime"], "%Y-%m-%d").timestamp() * 1000)
                        bars.append({
                            "timestamp": ts,
                            "open": float(v["open"]),
                            "high": float(v["high"]),
                            "low": float(v["low"]),
                            "close": float(v["close"]),
                            "volume": float(v.get("volume", 0)),
                        })
                    if bars:
                        logger.info(f"TwelveData: {symbol} {interval} → {len(bars)} bars")
                        return bars, "twelvedata"

            except Exception as e:
                logger.warning(f"Twelve Data failed for {symbol}: {e}")

    # --- Fallback: ExchangeRate API (real current rate + simulated candles) ---
    if len(symbol) != 6:
        return None, ""

    base = symbol[:3]
    quote = symbol[3:]

    try:
        url = f"https://open.er-api.com/v6/latest/{base}"
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            data = resp.json()

        if data.get("result") != "success":
            return None, ""

        rate = data["rates"].get(quote)
        if not rate:
            return None, ""

        bars = _generate_realistic_bars(rate, symbol, interval, limit)
        return bars, "exchangerate+simulated"

    except Exception as e:
        logger.warning(f"ExchangeRate API failed for {symbol}: {e}")
        return None, ""


def _generate_realistic_bars(
    current_price: float, symbol: str, interval: str, count: int
) -> list[dict]:
    """Generate realistic-looking bars around a known current price."""
    period_minutes = {
        "1m": 1, "5m": 5, "15m": 15, "30m": 30,
        "1h": 60, "4h": 240, "1d": 1440, "1w": 10080,
    }
    mins = period_minutes.get(interval, 60)
    now = datetime.now()

    # Forex volatility is much smaller than crypto
    is_forex = current_price < 200
    vol = current_price * 0.0003 if is_forex else current_price * 0.002

    bars = []
    price = current_price * (1 + random.uniform(-0.01, 0.01))

    for i in range(count):
        ts = now - timedelta(minutes=mins * (count - i))
        change = random.gauss(0, vol)
        price = max(price + change, current_price * 0.9)

        o = price
        h = o + abs(random.gauss(0, vol))
        low = o - abs(random.gauss(0, vol))
        c = o + random.gauss(0, vol * 0.8)
        c = max(min(c, h), low)
        v = random.uniform(1000, 50000)
        price = c

        decimals = 5 if is_forex else 2
        bars.append({
            "timestamp": int(ts.timestamp() * 1000),
            "open": round(o, decimals),
            "high": round(h, decimals),
            "low": round(low, decimals),
            "close": round(c, decimals),
            "volume": round(v, 2),
        })

    return bars


async def _fetch_twelvedata_direct(symbol: str, interval: str, limit: int) -> tuple[list[dict] | None, str]:
    """Fetch data from Twelve Data using the symbol directly (for commodities/indices)."""
    from app.config import get_settings
    settings = get_settings()
    if not settings.twelvedata_api_key:
        return None, ""

    td_intervals = {
        "1m": "1min", "5m": "5min", "15m": "15min", "30m": "30min",
        "1h": "1h", "4h": "4h", "1d": "1day", "1w": "1week",
    }
    td_interval = td_intervals.get(interval)
    if not td_interval:
        return None, ""

    try:
        url = "https://api.twelvedata.com/time_series"
        params = {
            "symbol": symbol,
            "interval": td_interval,
            "outputsize": str(min(limit, 500)),
            "apikey": settings.twelvedata_api_key,
        }
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()

        if data.get("status") == "ok" and data.get("values"):
            bars = []
            for v in reversed(data["values"]):
                from datetime import datetime as dt
                ts = int(dt.strptime(v["datetime"], "%Y-%m-%d %H:%M:%S").timestamp() * 1000) if " " in v["datetime"] else int(dt.strptime(v["datetime"], "%Y-%m-%d").timestamp() * 1000)
                bars.append({
                    "timestamp": ts,
                    "open": float(v["open"]),
                    "high": float(v["high"]),
                    "low": float(v["low"]),
                    "close": float(v["close"]),
                    "volume": float(v.get("volume", 0)),
                })
            if bars:
                logger.info(f"TwelveData direct: {symbol} {interval} → {len(bars)} bars")
                return bars, "twelvedata"
    except Exception as e:
        logger.warning(f"TwelveData direct failed for {symbol}: {e}")

    return None, ""


async def get_kline_data(
    symbol: str = "BTCUSD",
    period: str = "1h",
    count: int = 200,
) -> tuple[list[dict], str]:
    """
    Get K-line data from the best available source.
    Returns (bars, source) where source is 'binance', 'forex_api', or 'mock'.
    """
    sym = symbol.upper()

    # Try crypto APIs (OKX → Binance fallback)
    if sym in BINANCE_SYMBOLS:
        bars = await fetch_crypto_klines(sym, period, count)
        if bars:
            return bars, "okx/binance"

    # Try forex APIs (Twelve Data → ExchangeRate fallback)
    if sym in FOREX_SYMBOLS:
        bars, source = await fetch_forex_klines(sym, period, count)
        if bars:
            return bars, source

    # Commodity / index: try Twelve Data first, then estimated
    commodity_td_map = {"XAUUSD": "XAU/USD", "NAS100": "IXIC", "US30": "DJI", "SPX500": "SPX"}
    if sym in commodity_td_map:
        from app.config import get_settings
        if get_settings().twelvedata_api_key:
            bars, source = await fetch_forex_klines(commodity_td_map[sym].replace("/", ""), period, count)
            if not bars:
                # Try with the mapped symbol directly via Twelve Data
                bars, source = await _fetch_twelvedata_direct(commodity_td_map[sym], period, count)
            if bars:
                return bars, source

    known_prices = {"XAUUSD": 2350, "NAS100": 18500, "US30": 39000, "SPX500": 5200}
    if sym in known_prices:
        bars = _generate_realistic_bars(known_prices[sym], sym, period, count)
        return bars, "estimated"

    # Final fallback: mock
    bars = _generate_realistic_bars(100, sym, period, count)
    return bars, "mock"
