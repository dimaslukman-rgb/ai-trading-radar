"""Telegram notifier — sends trading signals to your phone via Telegram Bot API.

Setup:
  1. Open Telegram, search @BotFather, send /newbot
  2. Get API token (e.g. 123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11)
  3. Message your bot, then visit:
     https://api.telegram.org/bot<TOKEN>/getUpdates
  4. Copy your chat_id from the response
  5. Add to config_finex.json:
     "telegram": {
       "enabled": true,
       "bot_token": "123456:ABC-DEF...",
       "chat_id": "123456789"
     }

Usage:
    from aitrader_bot.app.notifier import TelegramNotifier
    tg = TelegramNotifier(bot_token="...", chat_id="...")
    tg.send("BUY signal XAUUSD @ 4127.50")
"""

from __future__ import annotations

import logging

log = logging.getLogger(__name__)


class TelegramNotifier:
    """Send messages to Telegram via Bot API."""

    def __init__(self, bot_token: str = "", chat_id: str = ""):
        self._token = bot_token
        self._chat_id = chat_id
        self._enabled = bool(bot_token and chat_id)

    @property
    def enabled(self) -> bool:
        return self._enabled

    def send(self, message: str) -> bool:
        """Send a plain-text message to Telegram. Returns True on success."""
        if not self._enabled:
            log.debug(f"Telegram disabled, would send: {message[:60]}")
            return False
        try:
            import requests
            url = f"https://api.telegram.org/bot{self._token}/sendMessage"
            resp = requests.post(
                url,
                data={"chat_id": self._chat_id, "text": message},
                timeout=10,
            )
            result = resp.json()
            if result.get("ok"):
                log.info(f"Telegram sent: {message[:60]}")
                return True
            else:
                log.warning(f"Telegram error: {result.get('description', 'unknown')}")
                return False
        except ImportError:
            log.warning("requests not installed. Install: pip install requests")
            return False
        except Exception as e:
            log.warning(f"Telegram send failed: {e}")
            return False

    def send_signal(self, action: str, symbol: str, price: float, reason: str, equity: float | None = None, pnl: float | None = None) -> None:
        """Send a formatted trading signal notification."""
        icon = {"buy": "LONG", "sell": "SHORT", "hold": "HOLD", "hodl": "HOLD"}.get(action.lower(), action.upper())
        msg = (
            f"[{icon}] {symbol}\n"
            f"Price: ${price:.2f}\n"
            f"Reason: {reason}"
        )
        if pnl is not None:
            sign = "+" if pnl >= 0 else ""
            msg += f"\nP&L: {sign}${pnl:.2f}"
        if equity is not None:
            msg += f"\nEquity: ${equity:.2f}"
        self.send(msg)

    def send_error(self, error_msg: str) -> None:
        """Send an error notification."""
        self.send(f"[ERROR] {error_msg}")

    def send_startup(self, symbol: str, broker: str, equity: float) -> None:
        """Send a startup notification."""
        self.send(
            f"[START] AI Trading Bot\n"
            f"Symbol: {symbol}\n"
            f"Broker: {broker}\n"
            f"Equity: ${equity:.2f}"
        )

    def send_shutdown(self, reason: str = "user stopped") -> None:
        """Send a shutdown notification."""
        self.send(f"[STOP] Bot stopped ({reason})")
