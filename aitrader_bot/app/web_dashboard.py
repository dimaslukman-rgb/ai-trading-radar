"""Real-time browser-based AI Trading Radar dashboard.

Starts a lightweight HTTP server (no external dependencies) that serves:
  - /          → HTML dashboard with live-updating UI
  - /api/status → JSON snapshot of current trading data
  - /api/logs   → SSE (Server-Sent Events) for streaming real-time log entries

Usage:
    from aitrader_bot.app.web_dashboard import start_web_dashboard
    start_web_dashboard(port=8080)  # non-blocking, runs in daemon thread
"""

from __future__ import annotations

import json
import logging
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from . import dashboard_data as dd

log = logging.getLogger(__name__)

# ── SSE client tracking ──────────────────────────────────────────────
_sse_clients: list[threading.Event] = []
_sse_lock = threading.Lock()

# ── Template loading ─────────────────────────────────────────────────
_TEMPLATE_PATH = os.path.join(os.path.dirname(__file__), "dashboard_template.html")
_cached_html: str | None = None


def _load_dashboard_html() -> str:
    """Load HTML from the template file (cached after first read)."""
    global _cached_html
    if _cached_html is not None:
        return _cached_html
    try:
        with open(_TEMPLATE_PATH, encoding="utf-8") as f:
            _cached_html = f.read()
    except FileNotFoundError:
        _cached_html = "<h1>Dashboard template not found</h1>"
        log.error(f"Dashboard template not found: {_TEMPLATE_PATH}")
    return _cached_html


# ── HTTP request handler ──────────────────────────────────────────────

class DashboardHandler(BaseHTTPRequestHandler):
    """Simple HTTP handler for the trading dashboard."""

    def handle(self) -> None:
        """Override handle() to catch connection-aborted errors during request reading."""
        try:
            super().handle()
        except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError, OSError):
            pass

    def log_message(self, fmt: str, *args: Any) -> None:
        """Suppress default stderr logging."""
        pass

    def _safe_write(self, data: bytes) -> bool:
        """Write bytes to client, silently handle disconnect errors."""
        try:
            self.wfile.write(data)
            self.wfile.flush()
            return True
        except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError, OSError):
            return False

    # ── Routes ────────────────────────────────────────────────────────

    def do_GET(self) -> None:
        if self.path == "/" or self.path == "/index.html":
            self._serve_html()
        elif self.path == "/api/status":
            self._serve_status()
        elif self.path == "/api/events":
            self._serve_sse()
        elif self.path == "/api/logs":
            self._serve_logs()
        elif self.path.startswith("/api/"):
            self._json_response(404, {"error": "not found"})
        else:
            self._json_response(404, {"error": "not found"})

    # ── HTML Dashboard ────────────────────────────────────────────────

    def _serve_html(self) -> None:
        html = _load_dashboard_html()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self._safe_write(html.encode("utf-8"))

    # ── JSON Status API ───────────────────────────────────────────────

    def _serve_status(self) -> None:
        data = dd.snapshot()
        self._json_response(200, data)

    # ── Logs API (for initial load) ────────────────────────────────────

    def _serve_logs(self) -> None:
        data = dd.snapshot()
        self._json_response(200, {
            "logs": data["logs"],
            "trades": data["trades"],
        })

    # ── Server-Sent Events (real-time streaming) ──────────────────────

    def _serve_sse(self) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()

        # Send initial snapshot
        snap = dd.snapshot()
        self._sse_send("init", json.dumps(snap))

        # Listen for new events
        client_event = threading.Event()
        with _sse_lock:
            _sse_clients.append(client_event)

        try:
            while not client_event.is_set():
                if client_event.wait(timeout=3):
                    # New data available — send full snapshot
                    snap = dd.snapshot()
                    self._sse_send("update", json.dumps(snap))
                    client_event.clear()
                else:
                    # Heartbeat keep-alive
                    if not self._safe_write(":\n\n".encode("utf-8")):
                        break
        except Exception:
            pass
        finally:
            with _sse_lock:
                if client_event in _sse_clients:
                    _sse_clients.remove(client_event)

    def _sse_send(self, event: str, data: str) -> bool:
        """Send an SSE event. Returns False if client disconnected."""
        return self._safe_write(f"event: {event}\ndata: {data}\n\n".encode("utf-8"))

    # ── Helpers ────────────────────────────────────────────────────────

    def _json_response(self, status: int, data: Any) -> None:
        body = json.dumps(data).encode("utf-8")
        try:
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(body)
        except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError, OSError):
            pass


# ── Notify SSE clients ────────────────────────────────────────────────

def notify_clients() -> None:
    """Wake up all SSE clients so they fetch new data."""
    with _sse_lock:
        for ev in _sse_clients:
            ev.set()


# ── Start server ──────────────────────────────────────────────────────

def start_web_dashboard(host: str = "127.0.0.1", port: int = 8080) -> ThreadingHTTPServer:
    """Start the dashboard HTTP server in a daemon thread. Returns the server object."""
    server = ThreadingHTTPServer((host, port), DashboardHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    log.info(f"Web dashboard started: http://{host}:{port}")
    print(f"[WEB] Dashboard: http://{host}:{port}")
    return server


def notify() -> None:
    """Notify all SSE clients that new data is available."""
    notify_clients()
