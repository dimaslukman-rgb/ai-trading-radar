"""PyQt6 Login Dialog — popup untuk memasukkan kredensial server MT5.

Muncul sebelum engine start, meminta:
  - Server (text)
  - Login (text)
  - Password (password field)
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from typing import Callable

from aitrader_bot.app.logger import setup_logging

log = setup_logging(__name__)


@dataclass
class LoginCredentials:
    server: str = ""
    login: str = ""
    password: str = ""
    confirmed: bool = False


def ask_credentials_console() -> LoginCredentials:
    """Fallback: minta kredensial via console (stdin) jika PyQt6 tidak tersedia."""
    print("\n=== MT5 Login ===")
    server = input("Server: ").strip()
    login = input("Login: ").strip()
    password = input("Password: ").strip()
    return LoginCredentials(server=server, login=login, password=password, confirmed=True)


def ask_credentials_gui(on_result: Callable[[LoginCredentials], None]) -> None:
    """Tampilkan popup login PyQt6.

    Args:
        on_result: Callback yang dipanggil dengan LoginCredentials setelah user klik Connect / Cancel.
    """
    try:
        from PyQt6.QtCore import Qt
        from PyQt6.QtGui import QFont
        from PyQt6.QtWidgets import (
            QApplication,
            QDialog,
            QDialogButtonBox,
            QFormLayout,
            QLabel,
            QLineEdit,
            QPushButton,
            QVBoxLayout,
        )
    except ImportError as e:
        log.warning(f"PyQt6 tidak terinstall, fallback ke console: {e}")
        result = ask_credentials_console()
        on_result(result)
        return

    app = QApplication.instance() or QApplication(sys.argv)

    dialog = QDialog()
    dialog.setWindowTitle("MT5 Login — AI Trading Bot")
    dialog.setFixedSize(380, 220)
    dialog.setWindowFlags(dialog.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)

    layout = QVBoxLayout(dialog)
    layout.setSpacing(10)

    title = QLabel("Masukkan kredensial MT5")
    title.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
    layout.addWidget(title)

    form = QFormLayout()
    form.setSpacing(8)

    server_input = QLineEdit()
    server_input.setPlaceholderText("Contoh: FinexAsia-Demo")
    form.addRow("Server:", server_input)

    login_input = QLineEdit()
    login_input.setPlaceholderText("MT5 login ID")
    form.addRow("Login:", login_input)

    password_input = QLineEdit()
    password_input.setPlaceholderText("Password MT5")
    password_input.setEchoMode(QLineEdit.EchoMode.Password)
    form.addRow("Password:", password_input)

    layout.addLayout(form)

    # Button box
    btn_box = QDialogButtonBox()
    connect_btn = QPushButton("Connect")
    connect_btn.setDefault(True)
    cancel_btn = QPushButton("Cancel")
    btn_box.addButton(connect_btn, QDialogButtonBox.ButtonRole.AcceptRole)
    btn_box.addButton(cancel_btn, QDialogButtonBox.ButtonRole.RejectRole)
    layout.addWidget(btn_box)

    def on_accept():
        creds = LoginCredentials(
            server=server_input.text().strip(),
            login=login_input.text().strip(),
            password=password_input.text(),
            confirmed=True,
        )
        dialog.accept()
        on_result(creds)

    def on_reject():
        creds = LoginCredentials(confirmed=False)
        dialog.reject()
        on_result(creds)

    connect_btn.clicked.connect(on_accept)
    cancel_btn.clicked.connect(on_reject)

    # Enter key triggers connect
    password_input.returnPressed.connect(on_accept)

    dialog.exec()
