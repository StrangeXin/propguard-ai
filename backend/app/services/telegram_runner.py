"""
Telegram Bot runner — long-polling service that receives messages,
parses signals, scores them, and replies.
Also handles /start, /help, /status commands.
"""

import logging
import asyncio
import httpx

from app.config import get_settings
from app.services.telegram_bot import handle_telegram_message, format_signal_response
from app.services.alert_history import get_alert_history

logger = logging.getLogger(__name__)

BOT_COMMANDS = {
    "/start": "Welcome to PropGuard AI Bot!\n\n"
              "Forward trading signals to me and I'll score them (0-100).\n\n"
              "Commands:\n"
              "/score <signal text> — Score a signal\n"
              "/link <email> — Link your account for alert delivery\n"
              "/alerts — Recent compliance alerts\n"
              "/status — Broker connection status\n"
              "/help — Show this message",

    "/help": "PropGuard AI Bot — Commands:\n\n"
             "/score <signal text> — Score a signal\n"
             "  Example: /score BUY BTCUSD @ 65000 SL: 63000 TP: 70000\n\n"
             "/link <email> — Link your PropGuard account\n"
             "  Enables automatic compliance alerts to this chat\n\n"
             "/alerts — Recent compliance alerts\n"
             "/status — Broker connection status\n\n"
             "Or just forward any trading signal message to me!",
}


class TelegramBotRunner:
    def __init__(self):
        self._settings = get_settings()
        self._token = self._settings.telegram_bot_token
        self._base_url = f"https://api.telegram.org/bot{self._token}"
        self._offset = 0
        self._running = False

    async def send_message(self, chat_id: str | int, text: str, parse_mode: str = "Markdown"):
        """Send a message to a Telegram chat."""
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                await client.post(f"{self._base_url}/sendMessage", json={
                    "chat_id": chat_id,
                    "text": text,
                    "parse_mode": parse_mode,
                })
        except Exception as e:
            logger.error(f"Failed to send Telegram message: {e}")

    async def handle_update(self, update: dict):
        """Process a single Telegram update."""
        message = update.get("message", {})
        text = message.get("text", "")
        chat_id = message.get("chat", {}).get("id")

        if not chat_id or not text:
            return

        # Handle commands
        if text.startswith("/start"):
            await self.send_message(chat_id, BOT_COMMANDS["/start"])
            return

        if text.startswith("/help"):
            await self.send_message(chat_id, BOT_COMMANDS["/help"])
            return

        if text.startswith("/alerts"):
            alerts = get_alert_history(limit=5)
            if not alerts:
                await self.send_message(chat_id, "No recent alerts.")
            else:
                lines = ["*Recent Alerts:*\n"]
                for a in alerts:
                    emoji = {"warning": "⚠️", "critical": "🔴", "danger": "🚨", "breached": "💀"}.get(a["alert_level"], "ℹ️")
                    lines.append(f"{emoji} {a['rule_type']}: {a['message']}")
                    lines.append(f"   _{a['timestamp'][:19]}_\n")
                await self.send_message(chat_id, "\n".join(lines))
            return

        if text.startswith("/link "):
            email = text[6:].strip().lower()
            from app.services.database import db_get_user_by_email, db_update_user
            user = db_get_user_by_email(email)
            if user:
                db_update_user(user["id"], {"telegram_chat_id": str(chat_id)})
                await self.send_message(
                    chat_id,
                    f"Linked to *{user['name']}* ({email}).\n"
                    f"You'll receive compliance alerts here when limits are approached.",
                )
            else:
                await self.send_message(chat_id, f"No account found for {email}. Register at PropGuard first.")
            return

        if text.startswith("/status"):
            from app.api.routes import broker
            status_lines = [
                "*PropGuard AI Status:*\n",
                f"MetaApi (MT5): {'🟢 Connected' if broker.is_metaapi_ready else '🔴 Disconnected'}",
                f"OKX (Crypto): {'🟢 Ready' if broker.is_okx_ready else '🔴 Not configured'}",
            ]
            await self.send_message(chat_id, "\n".join(status_lines))
            return

        # Handle /score command
        if text.startswith("/score "):
            signal_text = text[7:].strip()
        else:
            # Treat any non-command message as a signal
            signal_text = text

        # Forward info from forwarded messages
        forward_from = message.get("forward_from", {}).get("first_name")
        forward_chat = message.get("forward_from_chat", {}).get("title")
        source = forward_chat or forward_from

        # Parse and score
        scored = await handle_telegram_message(
            text=signal_text,
            chat_id=str(chat_id),
            forward_from=source,
        )

        if scored is None:
            await self.send_message(
                chat_id,
                "Could not parse a trading signal from this message.\n\n"
                "Try: `BUY BTCUSD @ 65000 SL: 63000 TP: 70000`",
            )
        else:
            response = format_signal_response(scored)
            await self.send_message(chat_id, response)

    async def poll(self):
        """Long-polling loop to receive Telegram updates."""
        self._running = True
        logger.info("Telegram bot polling started")

        while self._running:
            try:
                async with httpx.AsyncClient(timeout=30) as client:
                    resp = await client.get(f"{self._base_url}/getUpdates", params={
                        "offset": self._offset,
                        "timeout": 20,
                    })
                    data = resp.json()

                if data.get("ok") and data.get("result"):
                    for update in data["result"]:
                        self._offset = update["update_id"] + 1
                        await self.handle_update(update)

            except httpx.TimeoutException:
                continue
            except Exception as e:
                logger.error(f"Telegram polling error: {e}")
                await asyncio.sleep(5)

    def stop(self):
        self._running = False
