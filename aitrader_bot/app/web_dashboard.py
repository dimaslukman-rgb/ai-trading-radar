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

# Import the MT5 broker to handle account operations
try:
    from aitrader_bot.broker.mt5_broker import Mt5Broker
except ImportError:
    Mt5Broker = None
    log.warning("MT5 broker not available - account management features disabled")

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
        elif self.path == "/api/mt5/status":
            self._serve_mt5_status()
        elif self.path.startswith("/api/"):
            self._json_response(404, {"error": "not found"})
        else:
            self._json_response(404, {"error": "not found"})

    def do_POST(self) -> None:
        if self.path == "/api/mt5/login":
            self._handle_mt5_login()
        elif self.path == "/api/mt5/logout":
            self._handle_mt5_logout()
        elif self.path == "/api/mt5/forgot_password":
            self._handle_mt5_forgot_password()
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

    def _read_post_data(self) -> dict:
        """Read and parse JSON POST data."""
        content_length = int(self.headers.get("Content-Length", 0))
        if content_length == 0:
            return {}
        try:
            post_data = self.rfile.read(content_length)
            return json.loads(post_data.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError, ConnectionError):
            return {}

    # ── MT5 Account Management ─────────────────────────────────────────

    def _serve_mt5_status(self) -> None:
        """Serve current MT5 connection status."""
        data = dd.snapshot()
        mt5_status = {
            "connected": data["mt5_connected"],
            "login": data["mt5_login"],
            "server": data["mt5_server"],
            "account_info": data["mt5_account_info"],
            "last_error": data["mt5_last_error"]
        }
        self._json_response(200, mt5_status)

    def _handle_mt5_login(self) -> None:
        """Handle MT5 login request."""
        if Mt5Broker is None:
            self._json_response(500, {"success": False, "error": "MT5 broker not available"})
            return

        post_data = self._read_post_data()
        server = post_data.get("server", "")
        login = post_data.get("login")
        password = post_data.get("password", "")

        if not server or login is None or not password:
            self._json_response(400, {"success": False, "error": "Missing server, login, or password"})
            return

        try:
            # Convert login to int if it's a string
            if isinstance(login, str):
                login = int(login)

            # Create new MT5 broker instance and connect
            broker = Mt5Broker(server=server, login=login, password=password)
            success = broker.connect()

            if success:
                # Get account info
                account_info = broker.get_account()
                account_info_dict = {
                    "balance": account_info.balance,
                    "equity": account_info.equity,
                    "margin": account_info.margin,
                    "margin_free": account_info.margin_free,
                    "leverage": account_info.leverage,
                    "currency": account_info.currency
                }

                # Update dashboard data
                dd.update_mt5_status(
                    connected=True,
                    login=login,
                    server=server,
                    account_info=account_info_dict
                )
                dd.add_log(f"MT5 login successful: {login} on {server}")
                self._json_response(200, {"success": True, "account_info": account_info_dict})
            else:
                error_msg = "MT5 connection failed"
                dd.update_mt5_status(connected=False, last_error=error_msg)
                dd.add_log(f"MT5 login failed: {error_msg}")
                self._json_response(500, {"success": False, "error": error_msg})

        except Exception as e:
            error_msg = f"MT5 login error: {str(e)}"
            dd.update_mt5_status(connected=False, last_error=error_msg)
            dd.add_log(f"MT5 login error: {error_msg}")
            self._json_response(500, {"success": False, "error": error_msg})

    def _handle_mt5_logout(self) -> None:
        """Handle MT5 logout request."""
        if Mt5Broker is None:
            self._json_response(500, {"success": False, "error": "MT5 broker not available"})
            return

        try:
            # Create a temporary broker instance to disconnect
            broker = Mt5Broker()
            broker.disconnect()

            # Update dashboard data
            dd.update_mt5_status(
                connected=False,
                login=None,
                server="",
                account_info=None,
                last_error=""
            )
            dd.add_log("MT5 logout successful")
            self._json_response(200, {"success": True})

        except Exception as e:
            error_msg = f"MT5 logout error: {str(e)}"
            dd.update_mt5_status(connected=False, last_error=error_msg)
            dd.add_log(f"MT5 logout error: {error_msg}")
            self._json_response(500, {"success": False, "error": error_msg})

    def _handle_mt5_forgot_password(self) -> None:
        """Handle MT5 password reset request."""
        if Mt5Broker is None:
            self._json_response(500, {"success": False, "error": "MT5 broker not available"})
            return

        post_data = self._read_post_data()
        email = post_data.get("email", "")
        login = post_data.get("login")

        if not email or login is None:
            self._json_response(400, {"success": False, "error": "Missing email or login"})
            return

        try:
            # Note: In a real implementation, this would connect to the broker's
            # password reset API. For this demo, we'll simulate a success response.
            # Actual MT5 password reset would require broker-specific implementation.

            # Simulate password reset request
            dd.add_log(f"Password reset requested for login {login}")
            self._json_response(200, {
                "success": True,
                "message": "If the email and login match our records, a password reset link has been sent."
            })

        except Exception as e:
            error_msg = f"Password reset error: {str(e)}"
            dd.add_log(f"Password reset error: {error_msg}")
            self._json_response(500, {"success": False, "error": error_msg})


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
