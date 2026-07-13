#!/usr/bin/env python3
"""🧪 Setup Helper — Finex MT5 Connection Test + Config Generator.

Jalankan:
    python setup_finex.py

Ini akan:
  1. Cek apakah MetaTrader 5 terminal terinstall dan running
  2. Minta login/server/password Finex dari dashboard Anda
  3. Test koneksi ke Finex
  4. Cek "Allow Automated Trading" sudah aktif
  5. Tampilkan daftar simbol yang tersedia & pilih simbol trading
  6. Generate file config_finex.json + run-finex-scalp.bat
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

# ── Terminal color support ───────────────────────────────────────────
_USE_COLOR = sys.stdout.isatty() and os.environ.get("TERM") not in ("", None)


def _c(code: int, text: str) -> str:
    return f"\033[{code}m{text}\033[0m" if _USE_COLOR else text


GREEN = lambda t: _c(92, t)
YELLOW = lambda t: _c(93, t)
RED = lambda t: _c(91, t)
CYAN = lambda t: _c(96, t)
BOLD = lambda t: _c(1, t)


def print_step(num: int, msg: str):
    print(f"\n{BOLD(f'[{num}] {msg}')}")
    print("─" * 50)


def print_ok(msg: str):
    print(f"  {GREEN('✅')} {msg}")


def print_warn(msg: str):
    print(f"  {YELLOW('⚠️')}  {msg}")


def print_fail(msg: str):
    print(f"  {RED('❌')} {msg}")


def main():
    print(f"\n{BOLD('='*50)}")
    print(f"{BOLD('   AI TRADING BOT — SETUP FINEZ (Finex MT5)')}")
    print(f"{BOLD('='*50)}")

    # ═══════════════════════════════════════════════════════════════════
    # STEP 1: Check Python + MetaTrader5 package
    # ═══════════════════════════════════════════════════════════════════
    print_step(1, "Cek Python & MetaTrader5 package")

    print(f"  Python: {sys.version}")
    try:
        import MetaTrader5 as mt5  # noqa: F401
        import MetaTrader5
        print_ok(f"MetaTrader5 package: {MetaTrader5.__version__}")
    except ImportError:
        print_fail("MetaTrader5 package belum terinstall.")
        print("  Jalankan: pip install MetaTrader5")
        return

    # ═══════════════════════════════════════════════════════════════════
    # STEP 2: Check MT5 Terminal
    # ═══════════════════════════════════════════════════════════════════
    print_step(2, "Cek MetaTrader 5 Terminal")

    mt5_paths = [
        "C:\\Program Files\\MetaTrader 5\\terminal64.exe",
        "C:\\Program Files (x86)\\MetaTrader 5\\terminal64.exe",
    ]

    found = False
    for p in mt5_paths:
        if os.path.exists(p):
            print_ok(f"MT5 terminal ditemukan: {p}")
            found = True
            break

    if not found:
        print_warn("MT5 terminal tidak ditemukan di lokasi default.")
        print("  Pastikan MetaTrader 5 sudah terinstall.")
        print("  Download dari Finex: https://finex.co.id/trading/platform-windows-mt5")
        print("  Atau dari MetaQuotes: https://www.metatrader5.com/")
        proceed = input("\n  Lanjutkan setup tanpa terminal? (y/n): ").strip().lower()
        if proceed != "y":
            print("  Setup dibatalkan. Install MT5 dulu, lalu jalankan ulang.")
            return
    else:
        # Check if terminal is running
        try:
            result = subprocess.run(
                ["tasklist", "/FI", "IMAGENAME eq terminal64.exe"],
                capture_output=True, text=True, timeout=5,
            )
            if "terminal64.exe" in result.stdout:
                print_ok("MT5 Terminal sedang running")
            else:
                print_warn("MT5 Terminal belum running!")
                print("  Jalankan MetaTrader 5 dan login ke akun Finex Anda.")
                print("  Shortcut biasanya ada di Start Menu atau Desktop.")
                proceed = input("\n  Lanjutkan? (y/n): ").strip().lower()
                if proceed != "y":
                    print("  Setup dibatalkan.")
                    return
        except Exception:
            print_warn("Tidak bisa cek status MT5 — lanjutkan...")

    # ═══════════════════════════════════════════════════════════════════
    # STEP 3: Login Credentials
    # ═══════════════════════════════════════════════════════════════════
    print_step(3, "Kredensial Finex")

    print(f"  {YELLOW('Cara mendapatkan:')}")
    print("  1. Buka https://finex.co.id → Login ke dashboard")
    print("  2. Klik akun trading Anda → pilih menu 'Detail'")
    print("  3. Catat: Server, Login ID, dan Password")
    print()

    server = input("  Server (contoh: FinexAsia-Real / FinexAsia-Demo): ").strip()
    login_str = input("  Login ID (angka): ").strip()
    password = input("  Password: ").strip()

    try:
        login = int(login_str)
    except ValueError:
        print_fail("Login ID harus berupa angka!")
        return

    if not server or not password:
        print_fail("Server dan password tidak boleh kosong!")
        return

    # ═══════════════════════════════════════════════════════════════════
    # STEP 4: Test Connection
    # ═══════════════════════════════════════════════════════════════════
    print_step(4, "Test Koneksi ke Finex")

    import MetaTrader5 as mt5

    if not mt5.initialize():
        err = mt5.last_error()
        print_fail(f"MT5 initialize gagal: {err}")
        print("\n  Kemungkinan penyebab:")
        print("  - MT5 terminal belum diinstall atau belum dibuka")
        print(f"  - Atau jalankan langsung: \"{mt5_paths[0] if found else 'C:\\...\\terminal64.exe'}\"")
        mt5.shutdown()
        return

    print_ok("MT5 initialize berhasil")

    authorized = mt5.login(login, password=password, server=server)
    if not authorized:
        err = mt5.last_error()
        print_fail(f"Login gagal: {err}")
        print("\n  Kemungkinan penyebab:")
        print(f"  - Server '{server}' salah (cek di dashboard Finex)")
        print(f"  - Login ID '{login}' atau password salah")
        print("  - Akun belum aktif / terkunci")
        mt5.shutdown()
        return

    print_ok(f"Login berhasil ke {server}!")

    # Account info
    acct = mt5.account_info()
    if acct:
        print(f"\n  {BOLD('Informasi Akun:')}")
        print(f"    Balance:     {acct.balance:.2f} {acct.currency}")
        print(f"    Equity:      {acct.equity:.2f} {acct.currency}")
        print(f"    Margin Free: {acct.margin_free:.2f} {acct.currency}")
        print(f"    Leverage:    1:{acct.leverage}")
        print(f"    Server:      {acct.server}")

    # ═══════════════════════════════════════════════════════════════════
    # CHECK: Allow Automated Trading
    # ═══════════════════════════════════════════════════════════════════
    print_step("CHECK", "Allow Automated Trading")

    try:
        term_info = mt5.terminal_info()
        if term_info:
            if term_info.trade_allowed:
                print_ok("Algorithmic trading sudah diizinkan ✅")
            else:
                print_fail("Algorithmic trading BELUM diizinkan!")
                print(f"\n  {YELLOW('Cara mengaktifkan:')}")
                print("  1. Buka MetaTrader 5")
                print("  2. Klik menu Tools → Options")
                print("  3. Pilih tab 'Expert Advisors'")
                print("  4. Centang ☑ 'Allow automated trading'")
                print("  5. Klik OK")
                print("\n  Setelah itu, jalankan ulang setup ini.")
        else:
            print_warn("Tidak bisa cek trade_allowed")
    except Exception:
        print_warn("Tidak bisa verifikasi trade_allowed")

    # ═══════════════════════════════════════════════════════════════════
    # STEP 5: Discover & Select Symbols
    # ═══════════════════════════════════════════════════════════════════
    print_step(5, "Pilih Simbol Trading")

    symbols = mt5.symbols_get()
    if not symbols:
        print_warn("Tidak ada simbol ditemukan. Cek Market Watch di MT5.")
        chosen_symbol = "XAUUSD"
        print(f"  Default: {chosen_symbol}")
    else:
        # Group symbols by category
        all_names = [s.name for s in symbols]
        forex = sorted([s for s in all_names if len(s) == 6 and s.isalpha() and s[3:6] in ["USD", "JPY", "GBP", "EUR", "AUD", "CHF", "CAD", "NZD"]])
        gold = sorted([s for s in all_names if "XAU" in s.upper() or "GOLD" in s.upper()])
        silver = sorted([s for s in all_names if "XAG" in s.upper() or "SILV" in s.upper()])
        oil = sorted([s for s in all_names if "WTI" in s.upper() or "OIL" in s.upper() or "BRENT" in s.upper() or "XBR" in s.upper()])
        indices = sorted([s for s in all_names if any(x in s.upper() for x in ["DJI", "SPX", "NAS", "HSI", "NK", "IDX", "FTSE", "DAX"])])
        crypto_tokens = sorted([s for s in all_names if any(x in s.upper() for x in ["BTC", "ETH", "XRP", "LTC", "BCH", "SOL"])])
        stocks = sorted([s for s in all_names if "#" in s or s.endswith(".US")])

        print(f"  Total simbol tersedia: {len(symbols)}")
        if forex: print(f"\n  {BOLD('Forex:')}          {', '.join(forex[:8])}{'...' if len(forex) > 8 else ''}")
        if gold: print(f"  {BOLD('Emas:')}           {', '.join(gold[:3])}")
        if silver: print(f"  {BOLD('Perak:')}          {', '.join(silver[:2])}")
        if oil: print(f"  {BOLD('Minyak:')}         {', '.join(oil[:3])}")
        if indices: print(f"  {BOLD('Indeks:')}         {', '.join(indices[:5])}")
        if crypto_tokens: print(f"  {BOLD('Crypto:')}         {', '.join(crypto_tokens[:5])}")
        if stocks: print(f"  {BOLD('Saham:')}          {', '.join(stocks[:5])}")

        # Let user choose
        print()
        default_sym = (gold[0] if gold else forex[0] if forex else "XAUUSD")
        chosen = input(f"  Pilih simbol [default: {default_sym}]: ").strip().upper()
        chosen_symbol = chosen if chosen else default_sym
        print_ok(f"Simbol dipilih: {chosen_symbol}")

    mt5.shutdown()

    # ═══════════════════════════════════════════════════════════════════
    # STEP 6: Generate Config File
    # ═══════════════════════════════════════════════════════════════════
    print_step(6, "Generate Konfigurasi Finex")

    config_content = f'''{{
  "symbol": "{chosen_symbol}",
  "market": "forex",
  "scalping": {{
    "ema_fast": 5,
    "ema_slow": 20,
    "rsi_window": 7,
    "rsi_oversold": 30,
    "rsi_overbought": 70,
    "macd_fast": 12,
    "macd_slow": 26,
    "macd_signal": 9,
    "bb_window": 20,
    "bb_std": 2.0,
    "volume_threshold": 1.5,
    "max_spread_pct": 0.005,
    "min_buy_score": 0.30,
    "min_sell_score": -0.20,
    "stop_loss_pct": 0.003,
    "take_profit_pct": 0.005,
    "max_trade_pct": 0.05
  }},
  "risk": {{
    "initial_cash": 10000,
    "max_position_pct": 0.25,
    "max_trade_pct": 0.10,
    "stop_loss_pct": 0.05,
    "take_profit_pct": 0.10,
    "min_cash": 50
  }},
  "brokers": {{
    "default": {{
      "backend": "paper",
      "initial_cash": 10000
    }},
    "mt5": {{
      "backend": "mt5",
      "server": "{server}",
      "login": {login},
      "password": "{password}"
    }}
  }}
}}
'''

    config_path = PROJECT_ROOT / "config_finex.json"
    config_path.write_text(config_content, encoding="utf-8")
    print_ok(f"Config file: {config_path}")

    print(f"\n  {YELLOW('⚠️  Password disimpan dalam file config.')}")
    print(f"  {YELLOW('   Jangan bagikan file config_finex.json ke siapa pun!')}")

    # ═══════════════════════════════════════════════════════════════════
    # Generate Batch File
    # ═══════════════════════════════════════════════════════════════════
    python_exe = sys.executable
    bat_content = f"""@echo off
cd /d "%~dp0"
echo AI Trading Bot — Finex Scalping ({chosen_symbol})
echo ================================================
echo.
echo Starting scalping on Finex MT5...
echo Symbol: {chosen_symbol}
echo.
"{python_exe}" run_scalping.py --config config_finex.json --broker mt5 --auto-start
pause
"""
    bat_path = PROJECT_ROOT / "run-finex-scalp.bat"
    bat_path.write_text(bat_content, encoding="utf-8")
    print_ok(f"Batch file: {bat_path}")

    # ═══════════════════════════════════════════════════════════════════
    # SUMMARY
    # ═══════════════════════════════════════════════════════════════════
    print(f"\n{BOLD('='*50)}")
    print(f"{BOLD('   ✅ SETUP SELESAI!')}")
    print(f"{BOLD('='*50)}")
    print(f"""
  {GREEN('Koneksi Finex berhasil!')}

  {BOLD('🎯 Simbol trading:')}    {chosen_symbol}
  {BOLD('🔗 Server:')}          {server}
  {BOLD('💰 Balance:')}         {acct.balance:.2f} {acct.currency if acct else 'USD'}

  {BOLD('CARA SCALPING REAL-TIME:')}

  1. Buka MetaTrader 5 terminal
     - Pastikan sudah login ke akun Finex
     - Pastikan ☑ 'Allow Automated Trading' aktif

  2. Jalankan bot:
     {CYAN('Double-click: run-finex-scalp.bat')}
     atau
     {CYAN(f'\"{python_exe}\" run_scalping.py --config config_finex.json --broker mt5 --auto-start')}

  3. Atau test dulu:
     {CYAN(f'\"{python_exe}\" -m aitrader_bot.cli broker --config config_finex.json --broker mt5 --action info')}
     {CYAN(f'\"{python_exe}\" -m aitrader_bot.cli broker --config config_finex.json --broker mt5 --action quote')}
""")

    input(f"\n{BOLD('Tekan Enter untuk keluar...')}")


if __name__ == "__main__":
    main()
