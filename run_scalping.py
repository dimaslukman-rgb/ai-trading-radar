#!/usr/bin/env python3
"""AI Trading Bot — Windows Desktop Application.

Usage:
    python run_scalping.py                    # Tray + Dashboard mode
    python run_scalping.py --no-gui           # Tray only (recommended for background)
    python run_scalping.py --no-tray          # Dashboard only
    python run_scalping.py --no-gui --no-tray # CLI mode
    python run_scalping.py --broker mt5 --auto-start  # Finex auto-start
    python run_scalping.py --config config_finex.json --broker mt5 --no-gui
"""

from __future__ import annotations

import argparse
import shutil
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
APP_ROOT = (
    Path(sys.executable).resolve().parent
    if getattr(sys, "frozen", False)
    else PROJECT_ROOT
)
RESOURCE_ROOT = Path(getattr(sys, "_MEIPASS", PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT))

from aitrader_bot.app.engine import TradingEngine
from aitrader_bot.app.logger import setup_logging
from aitrader_bot.app.login_dialog import LoginCredentials, ask_credentials_console, ask_credentials_gui

log = setup_logging(__name__, level=20)  # INFO


def resolve_config_path(config_arg: str | None, app_root: Path | None = None) -> Path:
    """Resolve config paths outside PyInstaller's temporary _MEI directory."""
    root = app_root or APP_ROOT
    if config_arg:
        requested = Path(config_arg)
        return requested if requested.is_absolute() else root / requested

    for name in ("config_finex.json", "config.json"):
        candidate = root / name
        if candidate.exists():
            return candidate
    return root / "config_finex.json"


def ensure_default_config(config_path: Path) -> bool:
    """Create the Finex config for a first run when a template is available."""
    if config_path.exists():
        return True

    templates = (
        APP_ROOT / "config_finex.example.json",
        RESOURCE_ROOT / "config_finex.example.json",
    )
    for template in templates:
        if not template.exists():
            continue
        try:
            config_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(template, config_path)
            log.info("Created default configuration: %s", config_path)
            return True
        except OSError as exc:
            log.warning("Could not create default configuration at %s: %s", config_path, exc)
    return False


def main():
    parser = argparse.ArgumentParser(description="AI Trading Bot - Windows App")
    parser.add_argument("--config", default=None,
                        help="Path ke config file (default: config_finex.json di folder aplikasi)")
    parser.add_argument("--broker", default="mt5",
                        help="Nama broker config (default/mt5/binance/alpaca)")
    parser.add_argument("--no-gui", action="store_true",
                        help="Jalankan tanpa dashboard GUI")
    parser.add_argument("--no-tray", action="store_true",
                        help="Jalankan tanpa system tray icon")
    parser.add_argument("--auto-start", action="store_true",
                        help="Auto-start scalping engine")
    parser.add_argument("--skip-login", action="store_true",
                        help="Skip popup login, pakai kredensial dari config file")
    parser.add_argument("--check-update", action="store_true",
                        help="Cek update dari GitHub Releases")
    parser.add_argument("--version", action="store_true",
                        help="Tampilkan versi aplikasi")
    args = parser.parse_args()

    if args.version:
        from aitrader_bot.version import __version__
        print(f"AI Trading Radar v{__version__}")
        sys.exit(0)

    if args.check_update:
        from aitrader_bot.updater import check_text
        print(check_text())
        sys.exit(0)

    config_path = resolve_config_path(args.config)
    if not ensure_default_config(config_path):
        log.error(f"Config file not found: {config_path}")
        print(f"[ERROR] Config file not found: {config_path}")
        sys.exit(1)

    log.info("=== AI Trading Bot Starting ===")
    log.info(f"Config: {config_path}")
    log.info(f"Broker: {args.broker}")

    # ── Login Dialog (minta kredensial MT5) ──────────────────────────
    credentials: LoginCredentials | None = None

    if not args.skip_login:
        def _on_login(creds: LoginCredentials) -> None:
            nonlocal credentials
            credentials = creds

        if args.no_gui and args.no_tray:
            # CLI mode — pakai console input
            creds = ask_credentials_console()
            _on_login(creds)
        else:
            # GUI mode — tampilkan popup PyQt6
            ask_credentials_gui(_on_login)

        if credentials is None or not credentials.confirmed:
            log.info("Login dibatalkan oleh user")
            print("[INFO] Login dibatalkan. Bot tidak dijalankan.")
            return

        log.info(f"Login credentials received — Server: {credentials.server}, Login: {credentials.login}")
        # Auto-start engine setelah login berhasil
        _auto_start = True
    else:
        log.info("Skip login — menggunakan kredensial dari config file")
        _auto_start = args.auto_start

    # ── Initialize Engine ──────────────────────────────────────────────
    engine = TradingEngine(str(config_path), args.broker, credentials=credentials)

    # ── Start Web Dashboard (always, browser-based) ────────────────────
    from aitrader_bot.app.web_dashboard import start_web_dashboard
    web_server = None
    for port in list(range(9190, 9200)) + list(range(9090, 9100)):
        try:
            web_server = start_web_dashboard(port=port)
            print(f"[WEB] Dashboard: http://127.0.0.1:{port}")
            break
        except OSError:
            continue
    if web_server is None:
        log.warning("Web dashboard: no available port (tried 8080-8083)")

    # ── Start GUI Dashboard (optional, PyQt6) ──────────────────────────
    dashboard = None
    if not args.no_gui:
        try:
            from aitrader_bot.app.gui import DashboardWindow
            dashboard = DashboardWindow(engine.queue)
            dashboard.set_callbacks(on_start=engine.start, on_stop=engine.stop)
            dashboard.show()
            log.info("Dashboard GUI initialized (PyQt6)")
        except Exception as e:
            log.warning(f"Dashboard GUI failed: {e}")
            dashboard = None

    # Tentukan apakah dashboard bisa dibuat ulang dari tray
    _dashboard_enabled = not args.no_gui

    # ── Start System Tray (optional) ───────────────────────────────────
    tray = None
    if not args.no_tray:
        try:
            from aitrader_bot.app.tray import TrayApp
            from aitrader_bot.app.gui import DashboardWindow

            def open_dashboard():
                nonlocal dashboard
                if dashboard is not None and dashboard._window:
                    # Use queue to handle Qt calls from main thread (safe)
                    engine.queue.put("dashboard:focus")
                    log.info("Dashboard focus requested")
                elif _dashboard_enabled:
                    # Create new dashboard window
                    try:
                        new_dash = DashboardWindow(engine.queue)
                        new_dash.set_callbacks(on_start=engine.start, on_stop=engine.stop)
                        new_dash.show()
                        dashboard = new_dash
                        log.info("Dashboard window created (from tray)")
                    except Exception as e:
                        log.warning(f"Failed to create dashboard: {e}")
                else:
                    log.info("Dashboard not available (--no-gui mode)")

            tray = TrayApp(
                on_start=engine.start,
                on_stop=engine.stop,
                on_open_dashboard=open_dashboard,
                queue=engine.queue,
            )
            tray.start()
            log.info("System tray initialized (pystray)")
        except Exception as e:
            log.warning(f"System tray failed: {e}")
            tray = None

    # ── Auto-start engine ──────────────────────────────────────────────
    if _auto_start:
        log.info("Auto-start engine")
        engine.start()

    # ── CLI mode (no GUI, no tray) ─────────────────────────────────────
    if args.no_gui and args.no_tray:
        print("AI Trading Bot - CLI Mode")
        print(f"  Config: {config_path}")
        print(f"  Broker: {args.broker}")
        print("\nCommands: start, stop, status, exit")
        try:
            while True:
                try:
                    cmd = input("> ").strip().lower()
                except EOFError:
                    # stdin tidak tersedia (background/redirected mode)
                    # Bot tetap jalan, print queue messages periodically
                    time.sleep(1)
                    continue
                if cmd == "start":
                    engine.start()
                    print("[OK] Engine started")
                elif cmd == "stop":
                    engine.stop()
                    print("[OK] Engine stopped")
                elif cmd == "status":
                    print(f"  Status: {engine.status}")
                elif cmd in ("exit", "quit"):
                    engine.stop()
                    break
                # Print queue messages
                try:
                    while True:
                        msg = engine.queue.get_nowait()
                        print(f"  [{msg.split(':')[0]}] {msg}")
                except Exception:
                    pass
        except KeyboardInterrupt:
            print("\nShutting down...")
        finally:
            engine.stop()
        return

    # ── Normal mode — keep alive ───────────────────────────────────────
    try:
        if dashboard and hasattr(dashboard, "_app"):
            # Prevent Qt from quitting when window is hidden (close → hide)
            dashboard._app.setQuitOnLastWindowClosed(False)
            # Run Qt event loop — blocks until QApplication.quit() is called
            # Does NOT sys.exit() — program keeps running
            dashboard._app.exec()
            log.info("Dashboard PyQt event loop ended — engine continues")

        # Keep-alive loop
        while True:
            time.sleep(1)

    except KeyboardInterrupt:
        log.info("Shutdown by user")
    finally:
        engine.stop()
        if tray:
            tray.stop()
        if web_server:
            web_server.shutdown()
        log.info("=== AI Trading Bot Stopped ===")


if __name__ == "__main__":
    main()
