from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # App
    app_name: str = "PropGuard AI"
    debug: bool = False

    # Broker API (provided by partner)
    broker_api_url: str = ""
    broker_api_key: str = ""
    broker_api_secret: str = ""

    # MetaApi (MT4/MT5 cloud connection)
    metaapi_token: str = ""
    metaapi_account_id: str = ""
    mt5_server: str = ""
    mt5_login: str = ""
    mt5_password: str = ""

    # Claude API
    anthropic_api_key: str = ""
    ai_model: str = "claude-haiku-4-5-20251001"

    # Telegram Bot
    telegram_bot_token: str = ""

    # Supabase
    supabase_url: str = ""
    supabase_key: str = ""

    # OKX Account API
    okx_api_key: str = ""
    okx_secret_key: str = ""
    okx_passphrase: str = ""
    okx_demo: bool = False  # True for demo trading, False for live

    # Stripe (payments)
    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""
    stripe_price_pro: str = ""  # Stripe Price ID for Pro plan
    stripe_price_premium: str = ""  # Stripe Price ID for Premium plan

    # Twelve Data (free forex/stock OHLCV, get key at twelvedata.com)
    twelvedata_api_key: str = ""

    # WebSocket
    ws_reconnect_base_delay: float = 1.0
    ws_reconnect_max_delay: float = 30.0

    # Risk thresholds (percentage of limit remaining to trigger alert)
    alert_threshold_warning: float = 30.0  # 30% remaining
    alert_threshold_critical: float = 15.0  # 15% remaining
    alert_threshold_danger: float = 5.0  # 5% remaining

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
