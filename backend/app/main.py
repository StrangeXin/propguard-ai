"""
PropGuard AI — Prop Firm Risk Management + Signal Intelligence
Main FastAPI application.
"""

import asyncio
import logging

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router, broker
from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: connect broker + start Telegram bot in background
    broker_task = asyncio.create_task(_connect_broker_background())
    bot_task = asyncio.create_task(_start_telegram_bot())
    yield
    # Shutdown
    broker_task.cancel()
    bot_task.cancel()


async def _connect_broker_background():
    """Connect to MetaApi/OKX in background."""
    try:
        await asyncio.sleep(1)  # let the server start first
        logger.info("Connecting broker in background...")
        await broker.connect()
        logger.info(f"Broker ready: MetaApi={broker.is_metaapi_ready}, OKX={broker.is_okx_ready}")
    except Exception as e:
        logger.warning(f"Background broker connection failed: {e}")


async def _start_telegram_bot():
    """Start Telegram bot polling in background."""
    try:
        await asyncio.sleep(2)
        if not settings.telegram_bot_token:
            logger.info("Telegram bot token not configured, skipping")
            return
        from app.services.telegram_runner import TelegramBotRunner
        bot = TelegramBotRunner()
        logger.info("Telegram bot starting...")
        await bot.poll()
    except asyncio.CancelledError:
        logger.info("Telegram bot stopped")
    except Exception as e:
        logger.warning(f"Telegram bot failed: {e}")


app = FastAPI(
    title="PropGuard AI",
    description="AI-powered prop firm compliance monitoring and signal intelligence",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:3001", "http://localhost:3002", "https://*.vercel.app"],
    allow_origin_regex=r"https://.*\.vercel\.app",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
