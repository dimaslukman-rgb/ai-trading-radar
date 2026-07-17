"""PyQt6 License Dialog — popup untuk aktivasi serial number."""
from __future__ import annotations
import sys
from aitrader_bot.licensing import LicenseInfo, LicenseError, validate_serial
from aitrader_bot.app.logger import setup_logging

log = setup_logging(__name__)

def ask_license_console() -> LicenseInfo:
    print("\n=== Aktivasi Lisensi AI Trading Radar ===")
    print("Masukkan Serial Number:")
    serial = input("> ").strip()
    return validate_serial(serial)

def ask_license_gui() -> LicenseInfo:
    try:
        from PyQt6.QtCore import Qt
        from PyQt6.QtGui import QFont
        from PyQt6.QtWidgets import (
            QApplication, QDialog, QDialogButtonBox, QVBoxLayout,
            QLabel, QLineEdit, QMessageBox, QFormLayout
        )
    except ImportError:
        log.warning("PyQt6 tidak ditemukan, fallback ke console.")
        return ask_license_console()

    app = QApplication.instance() or QApplication(sys.argv)
    dialog = QDialog()
    dialog.setWindowTitle("Aktivasi Lisensi")
    dialog.setFixedSize(400, 180)

    layout = QVBoxLayout(dialog)
    layout.addWidget(QLabel("Masukkan Serial Number untuk aktivasi:"))

    serial_input = QLineEdit()
    serial_input.setPlaceholderText("XXXXX-XXXXX-XXXXX-XXXXX-XXXXX")
    layout.addWidget(serial_input)

    btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
    layout.addWidget(btns)

    valid_info: LicenseInfo | None = None

    def on_accept():
        nonlocal valid_info
        try:
            valid_info = validate_serial(serial_input.text().strip())
            dialog.accept()
        except LicenseError as e:
            QMessageBox.critical(dialog, "Error", str(e))

    btns.accepted.connect(on_accept)
    btns.rejected.connect(dialog.reject)

    if dialog.exec() == QDialog.DialogCode.Accepted and valid_info:
        return valid_info

    sys.exit(2) # Exit jika batal
