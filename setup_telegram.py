#!/usr/bin/env python3
"""Telegram Setup Helper â€” cari chat.id dan update config.

Jalankan:
    python setup_telegram.py

Ini akan:
  1. Minta bot token dari @BotFather
  2. Cek token valid atau tidak
  3. Cari chat.id dari pesan terakhir
  4. Kirim test message
  5. Update config_finex.json otomatis
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent

GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
CYAN = "\033[96m"
BOLD = "\033[1m"
RESET = "\033[0m"


def main():
    print(f"\n{BOLD}=== TELEGRAM SETUP ==={RESET}\n")

    # â”€â”€ Step 1: Input Token â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    print(f"{BOLD}[1] Masukkan Bot Token{RESET}")
    print(f"  Dapat dari {CYAN}@BotFather{RESET} di Telegram.")
    print(f"  Format: {YELLOW}1234567890:ABC-DEF1234ghIkl-zyx57W2v1u123ew11{RESET}")
    print()

    token = input("  Bot Token: ").strip()
    if not token:
        print(f"  {RED}Token tidak boleh kosong!{RESET}")
        return

    # â”€â”€ Step 2: Test Token â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    print(f"\n{BOLD}[2] Test Token...{RESET}")

    try:
        import requests
    except ImportError:
        print(f"  {RED}requests tidak terinstall. Jalankan: pip install requests{RESET}")
        return

    # Test token with getMe
    try:
        resp = requests.get(f"https://api.telegram.org/bot{token}/getMe", timeout=10)
        data = resp.json()
        if data.get("ok"):
            bot_name = data["result"].get("first_name", "?")
            bot_user = data["result"].get("username", "?")
            print(f"  {GREEN}Token valid!{RESET}")
            print(f"  Bot: {bot_name} (@{bot_user})")
        else:
            print(f"  {RED}Token tidak valid!{RESET}")
            print(f"  Error: {data.get('description', 'unknown')}")
            print(f"\n  {YELLOW}Coba ulang dari @BotFather â†’ /mybots â†’ API Token{RESET}")
            return
    except requests.exceptions.ConnectionError:
        print(f"  {RED}Gagal konek ke Telegram. Cek internet.{RESET}")
        return
    except Exception as e:
        print(f"  {RED}Error: {e}{RESET}")
        return

    # â”€â”€ Step 3: Cari Chat ID â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    print(f"\n{BOLD}[3] Cari Chat ID...{RESET}")

    chat_id = None
    try:
        resp = requests.get(
            f"https://api.telegram.org/bot{token}/getUpdates",
            timeout=10,
        )
        updates = resp.json()

        if updates.get("ok") and updates.get("result"):
            # Cari chat_id dari update terbaru
            for update in reversed(updates["result"]):
                # Bisa dari message, callback_query, atau my_chat_member
                msg = (
                    update.get("message")
                    or update.get("callback_query", {}).get("message")
                    or update.get("my_chat_member")
                )
                if msg and "chat" in msg:
                    chat_id = msg["chat"]["id"]
                    chat_type = msg["chat"].get("type", "?")
                    chat_title = msg["chat"].get("title") or msg["chat"].get("first_name", "?")
                    print(f"  {GREEN}Chat ID ditemukan!{RESET}")
                    print(f"  ID: {CYAN}{chat_id}{RESET}")
                    print(f"  Type: {chat_type}")
                    print(f"  Name: {chat_title}")
                    break

        if chat_id is None:
            print(f"  {YELLOW}Chat ID belum ditemukan.{RESET}")
            print(f"\n  {BOLD}Cara: {RESET}")
            print(f"  1. Buka Telegram, cari bot @{bot_user}")
            print(f"  2. Kirim pesan {CYAN}/start{RESET} atau apapun ke bot")
            print(f"  3. Kembali ke sini, tekan Enter")
            input(f"\n  {BOLD}Tekan Enter setelah kirim pesan...{RESET}")

            # Coba lagi
            resp = requests.get(
                f"https://api.telegram.org/bot{token}/getUpdates",
                timeout=10,
            )
            updates = resp.json()
            if updates.get("ok") and updates.get("result"):
                for update in reversed(updates["result"]):
                    msg = (
                        update.get("message")
                        or update.get("callback_query", {}).get("message")
                        or update.get("my_chat_member")
                    )
                    if msg and "chat" in chat:
                        chat_id = msg["chat"]["id"]
                        print(f"\n  {GREEN}Chat ID ditemukan: {CYAN}{chat_id}{RESET}")
                        break

        if chat_id is None:
            print(f"\n  {RED}Masih tidak ditemukan.{RESET}")
            print(f"  Coba manual:")
            print(f"  1. Buka browser:")
            print(f"     {CYAN}https://api.telegram.org/bot{token}/getUpdates{RESET}")
            print(f"  2. Cari angka di {YELLOW}\"chat\":{{\"id\": ANGKA_INI }}{RESET}")
            print(f"  3. Masukkan manual:")

            manual = input(f"\n  Chat ID (angka): ").strip()
            if manual and manual.lstrip("-").isdigit():
                chat_id = int(manual)
            else:
                print(f"  {RED}Chat ID tidak valid.{RESET}")
                return

    except Exception as e:
        print(f"  {RED}Error: {e}{RESET}")
        return

    # â”€â”€ Step 4: Test Kirim Pesan â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    print(f"\n{BOLD}[4] Test Kirim Pesan...{RESET}")

    try:
        resp = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data={
                "chat_id": chat_id,
                "text": "[TEST] AI Trading Radar Telegram berhasil terhubung!",
            },
            timeout=10,
        )
        result = resp.json()
        if result.get("ok"):
            print(f"  {GREEN}Pesan test terkirim! Cek Telegram Anda.{RESET}")
        else:
            print(f"  {RED}Gagal kirim: {result.get('description', '?')}{RESET}")
            return
    except Exception as e:
        print(f"  {RED}Error: {e}{RESET}")
        return

    # â”€â”€ Step 5: Update Config â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    print(f"\n{BOLD}[5] Update Config...{RESET}")

    config_path = PROJECT_ROOT / "config_finex.json"
    if not config_path.exists():
        print(f"  {YELLOW}config_finex.json tidak ditemukan, buat baru...{RESET}")
        config = {}
    else:
        config = json.loads(config_path.read_text(encoding="utf-8"))

    if "telegram" not in config:
        config["telegram"] = {}
    config["telegram"]["enabled"] = True
    config["telegram"]["bot_token"] = token
    config["telegram"]["chat_id"] = str(chat_id)

    config_path.write_text(json.dumps(config, indent=2), encoding="utf-8")
    print(f"  {GREEN}Config updated: {config_path}{RESET}")

    # â”€â”€ Done â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    print(f"\n{BOLD}{'='*50}{RESET}")
    print(f"{GREEN}  TELEGRAM SETUP BERHASIL!{RESET}")
    print(f"{BOLD}{'='*50}{RESET}")
    print(f"""
  {BOLD}Ringkasan:{RESET}
  Bot Token: {token[:15]}...{token[-5:]}
  Chat ID:   {chat_id}
  Status:    {GREEN}Active{RESET}

  {BOLD}Sekarang bot akan:{RESET}
  - Kirim {CYAN}[START]{RESET} saat engine mulai
  - Kirim {CYAN}[LONG]{RESET} / {CYAN}[SHORT]{RESET} saat sinyal buy/sell
  - Kirim {CYAN}[ERROR]{RESET} jika ada masalah
  - Kirim {CYAN}[STOP]{RESET} saat engine berhenti

  {BOLD}Jalankan scalping:{RESET}
  {CYAN}python run_scalping.py --no-gui{RESET}
""")


if __name__ == "__main__":
    main()

