#!/usr/bin/env python3
"""AI Trading Bot — Windows Desktop Application.

Usage:
    python run_scalping.py                    # Auto-start MT5 + web dashboard + tray
    python run_scalping.py --no-gui           # Tray only (recommended for background)
    python run_scalping.py --no-tray          # Dashboard only
    python run_scalping.py --no-gui --no-tray # CLI mode
    python run_scalping.py --broker mt5 --auto-start  # Finex auto-start
    python run_scalping.py --config config_finex.json --broker mt5 --no-gui
"""

from __future__ import annotations

import argparse
import sys
import time
import webbrowser
import sys
from pathlib import Path
from threading import Event

# Jika dijalankan sebagai PyInstaller bundle (EXE)
if getattr(sys, "frozen", False):
    PROJECT_ROOT = Path(sys.executable).resolve().parent
    BUNDLE_ROOT = Path(sys._MEIPASS).resolve()
    sys.path.insert(0, str(BUNDLE_ROOT))
else:
    PROJECT_ROOT = Path(__file__).resolve().parent
    BUNDLE_ROOT = PROJECT_ROOT
    sys.path.insert(0, str(PROJECT_ROOT))

from aitrader_bot.app.engine import TradingEngine
from aitrader_bot.app.logger import setup_logging
from aitrader_bot.licensing import (
    LicenseError,
    load_license,
    save_license,
    reset_license,
    validate_serial,
)
from aitrader_bot.app.license_dialog import ask_license_gui
from aitrader_bot.version import __version__

log = setup_logging(__name__, level=20)  # INFO


def _check_update() -> None:
    """Cek versi terbaru di GitHub releases."""
    import urllib.request, json
    url = "https://api.github.com/repos/dimaslukman-rgb/ai-trading-radar/releases/latest"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": f"ai-trading-radar/{__version__}"})
        resp = urllib.request.urlopen(req, timeout=10)
        latest = json.loads(resp.read())
        tag = latest.get("tag_name", "unknown")
        if tag.lstrip("v") == __version__:
            print(f"Versi terbaru: {tag} (sudah terbaru)")
        else:
            print(f"Versi terbaru tersedia: {tag}")
            print(f"Download: {latest.get('html_url', url)}")
    except Exception as e:
        print(f"Gagal cek update: {e}")


def _enforce_license(args) -> None:
    """Cek lisensi sebelum memulai engine. Jika tidak valid, minta serial."""
    if getattr(args, "activate_serial", None):
        info = validate_serial(args.activate_serial)
        save_license(info)
        print(f"Lisensi disimpan: {info.plan_label}")
        sys.exit(0)
    if getattr(args, "reset_license", False):
        reset_license()
        print("Lisensi di-reset.")
        return

    stored = load_license()
    if stored is not None:
        return

    print("[LISENSI] Serial tidak ditemukan. Membuka dialog aktivasi...")
    try:
        info = ask_license_gui()
    except LicenseError as e:
        print(f"[ERROR] {e}")
        sys.exit(2)
    save_license(info)
    print(f"[OK] Lisensi aktif: {info.plan_label}")


def main():
    # Cari config default secara berurutan
    default_config = PROJECT_ROOT / "config_finex_ultra_m1.json"
    if not default_config.exists():
        default_config = PROJECT_ROOT / "config.json"
    if not default_config.exists():
        default_config = BUNDLE_ROOT / "config_finex_ultra_m1.json"

    parser = argparse.ArgumentParser(description="AI Trading Bot - Windows App")
    parser.add_argument("--config", default=str(default_config),
                        help="Path ke config file. (default: config_finex_ultra_m1.json)")
    parser.add_argument("--broker", default="mt5",
                        help="Nama broker config (default/mt5/binance/alpaca)")
    parser.add_argument("--no-gui", action="store_true",
                        help="Jangan gunakan dashboard desktop PyQt6")
    parser.add_argument("--show-gui", action="store_true",
                        help="Tampilkan dashboard desktop saat startup (default: tray)")
    parser.add_argument("--no-tray", action="store_true",
                        help="Jalankan tanpa system tray icon")
    parser.add_argument("--auto-start", dest="auto_start", action="store_true",
                        help="Auto-start scalping engine (default)")
    parser.add_argument("--no-auto-start", dest="auto_start", action="store_false",
                        help="Jalankan dashboard tanpa menghubungkan engine trading")
    parser.add_argument("--version", action="version", version=f"AI Trading Radar v{__version__}")
    parser.add_argument("--reset-license", action="store_true", dest="reset_license",
                        help="Reset lisensi tersimpan")
    parser.add_argument("--activate-serial", metavar="SERIAL",
                        help="Aktivasi lisensi via command line tanpa GUI")
    parser.add_argument("--check-update", action="store_true",
                        help="Cek versi terbaru di GitHub releases")
    parser.set_defaults(auto_start=True)
    args = parser.parse_args()

    if getattr(args, "check_update", False):
        _check_update()
        return

    _enforce_license(args)

    config_path = Path(args.config)
    if not config_path.is_absolute():
        # Cari di folder program/executable
        config_path = (PROJECT_ROOT / config_path).resolve()

    if not config_path.exists():
        # Fallback ke template internal jika benar-benar tidak ketemu
        config_path = (BUNDLE_ROOT / Path(args.config).name).resolve()

    if not config_path.exists():
        log.error(f"Config file not found: {config_path}")
        print(f"[ERROR] Config file not found: {config_path}")
        sys.exit(1)

    log.info("=== AI Trading Bot Starting ===")
    log.info(f"Config: {config_path}")
    log.info(f"Broker: {args.broker}")

    # ── Initialize Engine ──────────────────────────────────────────────
    engine = TradingEngine(str(config_path), args.broker)
    quit_requested = Event()

    # ── Start Web Dashboard (always, browser-based) ────────────────────
    from aitrader_bot.app.web_dashboard import start_web_dashboard
    web_server = None
    dashboard_url = None
    for port in list(range(9190, 9200)) + list(range(9090, 9100)):
        try:
            web_server = start_web_dashboard(port=port)
            dashboard_url = f"http://127.0.0.1:{web_server.server_address[1]}/"
            break
        except OSError:
            continue
    if web_server is None:
        log.warning("Web dashboard: no available port (tried 8080-8083)")

    # ── Start GUI Dashboard (optional, PyQt6) ──────────────────────────
    dashboard = None
    show_gui = not args.no_gui and (args.show_gui or args.no_tray)
    if show_gui:
        try:
            from aitrader_bot.app.gui import DashboardWindow
            dashboard = DashboardWindow(engine.queue)
            dashboard.set_callbacks(on_start=engine.start, on_stop=engine.stop)
            dashboard.show()
            log.info("Dashboard GUI initialized (PyQt6)")
        except Exception as e:
            log.warning(f"Dashboard GUI failed: {e}")
            dashboard = None

    # ── Start System Tray (optional) ───────────────────────────────────
    tray = None
    if not args.no_tray:
        try:
            from aitrader_bot.app.tray import TrayApp
            def open_dashboard():
                if dashboard_url:
                    webbrowser.open(dashboard_url)
                    log.info("Web dashboard opened: %s", dashboard_url)
                elif dashboard is not None:
                    engine.queue.put("dashboard:focus")
                else:
                    log.warning("Dashboard URL is unavailable")

            def request_exit():
                quit_requested.set()
                if dashboard is not None and hasattr(dashboard, "_app"):
                    dashboard._app.quit()

            tray = TrayApp(
                on_start=engine.start,
                on_stop=engine.stop,
                on_open_dashboard=open_dashboard,
                on_exit=request_exit,
                queue=engine.queue,
            )
            tray.start()
            log.info("System tray initialized (pystray)")
        except Exception as e:
            log.warning(f"System tray failed: {e}")
            tray = None

    # ── Auto-start if requested ────────────────────────────────────────
    if args.auto_start:
        log.info("Auto-start enabled - launching MT5 and starting engine")
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
        while not quit_requested.wait(1):
            pass

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
