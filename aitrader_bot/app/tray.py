"""System tray icon — background presence for the scalping bot.

Uses pystray. All text ASCII-safe for Windows terminal compatibility.
"""

from __future__ import annotations

import threading
from queue import Queue
from typing import Callable

from aitrader_bot.app.logger import setup_logging

log = setup_logging(__name__)


class TrayApp:
    """System tray icon manager — runs in its own thread."""

    def __init__(
        self,
        on_start: Callable,
        on_stop: Callable,
        on_open_dashboard: Callable,
        queue: Queue,
    ):
        self._on_start = on_start
        self._on_stop = on_stop
        self._on_open_dashboard = on_open_dashboard
        self.queue = queue
        self._icon = None
        self._thread: threading.Thread | None = None
        self._status_text = "Stopped"

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self) -> None:
        try:
            import pystray
            from PIL import Image, ImageDraw
        except ImportError:
            log.warning("pystray / Pillow not installed. Tray icon unavailable.")
            return

        # Green circle icon
        img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw.ellipse([4, 4, 60, 60], fill=(34, 197, 94, 255))

        def on_start(icon, item):
            self._on_start()
            icon.title = f"AI Bot - {self._status_text}"

        def on_stop(icon, item):
            self._on_stop()
            self._status_text = "Stopped"
            icon.title = "AI Bot - Stopped"

        def on_dashboard(icon, item):
            self._on_open_dashboard()

        def on_exit(icon, item):
            self._on_stop()
            icon.stop()

        menu = pystray.Menu(
            pystray.MenuItem("Start", on_start, default=True),
            pystray.MenuItem("Stop", on_stop),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Dashboard", on_dashboard),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Exit", on_exit),
        )

        self._icon = pystray.Icon(
            name="AITradingBot",
            icon=img,
            title=f"AI Bot - {self._status_text}",
            menu=menu,
        )

        # Background queue processor
        def check_queue():
            while self._icon and self._icon.visible:
                try:
                    msg = self.queue.get(timeout=1)
                    self._handle_message(msg)
                except Exception:
                    pass

        threading.Thread(target=check_queue, daemon=True).start()
        self._icon.run()

    def _handle_message(self, msg: str) -> None:
        if msg.startswith("status:"):
            status = msg.split(":", 1)[1]
            self._status_text = status.title()
            if self._icon:
                self._icon.title = f"AI Bot - {status.title()}"
            if status in ("running", "buy", "sell"):
                self._notify("AI Bot", status.title())

        elif msg.startswith("signal:"):
            info = msg.split(":", 1)[1]
            if "BOUGHT" in info:
                self._notify("Buy Signal", info[:60])
            elif "SOLD" in info:
                self._notify("Sell Signal", info[:60])

        elif msg.startswith("error:"):
            err = msg.split(":", 1)[1]
            self._notify("Error", err[:60])

        elif msg.startswith("account:"):
            eq = msg.split(":", 1)[1]
            self._status_text = f"Equity: ${eq}"

    def _notify(self, title: str, message: str) -> None:
        try:
            from win10toast import ToastNotifier
            ToastNotifier().show_toast(title, message, duration=5, threaded=True)
        except ImportError:
            log.info(f"[{title}] {message}")
        except Exception:
            pass

    def stop(self) -> None:
        if self._icon:
            try:
                self._icon.stop()
            except Exception:
                pass
