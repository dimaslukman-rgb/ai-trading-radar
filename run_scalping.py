#!/usr/bin/env python3
"""AI Trading Radar â€” Windows Desktop Application.

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

def _app_dir() -> Path:
    """Return the external app directory, not PyInstaller's temp folder."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


APP_DIR = _app_dir()
BUNDLE_DIR = Path(getattr(sys, "_MEIPASS", APP_DIR))
PROJECT_ROOT = APP_DIR
if not getattr(sys, "frozen", False):
    sys.path.insert(0, str(PROJECT_ROOT))


def _default_config_path() -> Path:
    """Prefer editable config next to the executable."""
    for candidate in (
        APP_DIR / "config.json",
        APP_DIR / "config_finex.json",
        APP_DIR / "config.example.json",
    ):
        if candidate.exists():
            return candidate

    for bundled_name in ("config.json", "config.example.json"):
        bundled = BUNDLE_DIR / bundled_name
        if bundled.exists():
            target = APP_DIR / "config.json"
            try:
                shutil.copyfile(bundled, target)
                return target
            except OSError:
                return bundled

    return APP_DIR / "config.json"

def main():
    parser = argparse.ArgumentParser(description="AI Trading Radar - Windows App")
    parser.add_argument("--config", default=str(_default_config_path()),
                        help="Path ke config file. Gunakan config_finex_aggressive_1m.json untuk mode agresif M1 (default: config_finex.json)")
    parser.add_argument("--broker", default="default",
                        help="Nama broker config (default/mt5/binance/alpaca)")
    parser.add_argument("--no-gui", action="store_true",
                        help="Jalankan tanpa dashboard GUI")
    parser.add_argument("--no-tray", action="store_true",
                        help="Jalankan tanpa system tray icon")
    parser.add_argument("--auto-start", action="store_true",
                        help="Auto-start scalping engine")
    parser.add_argument("--license-key",
                        help="Aktivasi serial key tanpa prompt")
    parser.add_argument("--license-info", action="store_true",
                        help="Tampilkan status serial key lalu keluar")
    parser.add_argument("--reset-license", action="store_true",
                        help="Hapus serial key tersimpan lalu keluar")
    args = parser.parse_args()

    from aitrader_bot.licensing import (
        LicenseError,
        ensure_license,
        license_status_text,
        reset_stored_license,
    )

    if args.reset_license:
        removed = reset_stored_license()
        print("[LICENSE] Serial key tersimpan dihapus." if removed else "[LICENSE] Tidak ada serial key tersimpan.")
        if not args.license_key:
            return

    if args.license_info:
        print(license_status_text())
        return

    try:
        license_info = ensure_license(
            provided_key=args.license_key,
            use_gui_prompt=not (args.no_gui and args.no_tray),
        )
    except LicenseError as e:
        print(f"[LICENSE ERROR] {e}")
        sys.exit(2)

    from aitrader_bot.app.engine import TradingEngine
    from aitrader_bot.app.logger import setup_logging

    log = setup_logging(__name__, level=20)  # INFO

    config_path = Path(args.config)
    if not config_path.is_absolute() and not config_path.exists():
        app_relative = APP_DIR / config_path
        if app_relative.exists():
            config_path = app_relative
    if not config_path.exists():
        log.error(f"Config file not found: {config_path}")
        print(f"[ERROR] Config file not found: {config_path}")
        sys.exit(1)

    log.info("=== AI Trading Radar Starting ===")
    log.info(f"Config: {config_path}")
    log.info(f"Broker: {args.broker}")
    log.info(f"License: {license_info.plan_label}, expires {license_info.expires_label}, id {license_info.license_id}")

    # â”€â”€ Initialize Engine â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    engine = TradingEngine(str(config_path), args.broker)

    # â”€â”€ Start Web Dashboard (always, browser-based) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
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

    # â”€â”€ Start GUI Dashboard (optional, PyQt6) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
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

    # â”€â”€ Start System Tray (optional) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
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

    # â”€â”€ Auto-start if requested â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    if args.auto_start:
        log.info("Auto-start enabled - starting engine")
        engine.start()

    # â”€â”€ CLI mode (no GUI, no tray) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    if args.no_gui and args.no_tray:
        print("AI Trading Radar - CLI Mode")
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

    # â”€â”€ Normal mode â€” keep alive â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    try:
        if dashboard and hasattr(dashboard, "_app"):
            # Prevent Qt from quitting when window is hidden (close â†’ hide)
            dashboard._app.setQuitOnLastWindowClosed(False)
            # Run Qt event loop â€” blocks until QApplication.quit() is called
            # Does NOT sys.exit() â€” program keeps running
            dashboard._app.exec()
            log.info("Dashboard PyQt event loop ended â€” engine continues")

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
        log.info("=== AI Trading Radar Stopped ===")


if __name__ == "__main__":
    main()

