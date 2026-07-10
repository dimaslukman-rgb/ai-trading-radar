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

# ── Updater bridge ───────────────────────────────────────────────────
_update_state_snapshot: dict | None = None
_update_lock = threading.Lock()


def _pull_update_state() -> dict:
    """Pull latest state from the updater module and cache it in dashboard_data."""
    try:
        from aitrader_bot.updater import get_state
        st = get_state()
        data = st.to_dict()
        dd.update_update_state(data)
        return data
    except Exception:
        return {}

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
        elif self.path == "/api/update/status":
            self._serve_update_status()
        elif self.path.startswith("/api/"):
            self._json_response(404, {"error": "not found"})
        else:
            self._json_response(404, {"error": "not found"})

    def do_POST(self) -> None:
        if self.path == "/api/update/check":
            self._handle_update_check()
        elif self.path == "/api/update/download":
            self._handle_update_download()
        elif self.path == "/api/update/apply":
            self._handle_update_apply()
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
        _pull_update_state()
        data = dd.snapshot()
        self._json_response(200, data)

    # ── Logs API (for initial load) ────────────────────────────────────

    def _serve_logs(self) -> None:
        data = dd.snapshot()
        self._json_response(200, {
            "logs": data["logs"],
            "trades": data["trades"],
        })

    # ── Update API ─────────────────────────────────────────────────────

    def _serve_update_status(self) -> None:
        """Return latest update state as JSON."""
        _pull_update_state()
        data = dd.snapshot()
        self._json_response(200, data.get("update", {}))

    def _handle_update_check(self) -> None:
        """Force an immediate update check."""
        try:
            from aitrader_bot.updater import check_for_update
            info = check_for_update()
            _pull_update_state()
            if info:
                self._json_response(200, {"success": True, "update_available": True,
                    "latest_version": info.latest_version, "current_version": info.current_version})
            else:
                self._json_response(200, {"success": True, "update_available": False})
        except Exception as e:
            self._json_response(500, {"success": False, "error": str(e)})

    def _handle_update_download(self) -> None:
        """Start downloading the update installer."""
        try:
            from aitrader_bot.updater import get_state, download_update, UpdateInfo
            state = get_state()
            if not state.update_available:
                self._json_response(400, {"success": False, "error": "No update available"})
                return
            # Build UpdateInfo from current state
            import threading as _thr
            info = UpdateInfo(
                latest_version=state.latest_version,
                current_version=state.current_version,
                download_url=state.download_url,
                release_notes=state.release_notes,
                release_date=state.release_date,
                asset_name=state.asset_name,
                asset_size=state.asset_size,
            )

            def _bg_dl():
                download_update(info, progress_callback=lambda p: _pull_update_state())
                _pull_update_state()
                notify_clients()

            _thr.Thread(target=_bg_dl, daemon=True).start()
            self._json_response(200, {"success": True, "message": "Download started"})
        except Exception as e:
            self._json_response(500, {"success": False, "error": str(e)})

    def _handle_update_apply(self) -> None:
        """Launch the downloaded installer to apply the update."""
        try:
            from aitrader_bot.updater import get_state, apply_update
            state = get_state()
            if not state.download_path:
                self._json_response(400, {"success": False, "error": "No download available"})
                return
            ok = apply_update(state.download_path)
            self._json_response(200, {"success": ok})
        except Exception as e:
            self._json_response(500, {"success": False, "error": str(e)})

    # ── Server-Sent Events (real-time streaming) ──────────────────────

    def _serve_sse(self) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()

        # Send initial snapshot (with update state pulled)
        _pull_update_state()
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
                    _pull_update_state()
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
