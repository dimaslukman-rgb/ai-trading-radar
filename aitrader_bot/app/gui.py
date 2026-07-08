"""PyQt6 Dashboard — real-time status window for the scalping bot.

Shows:
  - Connection status (green/red indicator)
  - Account balance & equity
  - Open positions
  - Last signal with reason
  - Live log viewer
"""

from __future__ import annotations

import sys
from datetime import datetime
from queue import Queue
from typing import Callable

from aitrader_bot.app.logger import setup_logging

log = setup_logging(__name__)


class DashboardWindow:
    """PyQt6 dashboard — opens in a separate window."""

    def __init__(self, queue: Queue, on_close: Callable | None = None):
        self.queue = queue
        self._on_close = on_close
        self._window = None
        self._running = False

        # State
        self._status = "Stopped"
        self._equity = "0.00"
        self._balance = "0.00"
        self._last_signal = "-"
        self._positions: list[str] = []
        self._log_lines: list[str] = []

    def show(self) -> None:
        """Open or unhide the dashboard window."""
        if self._window:
            # Window exists but is hidden — unhide it
            self._window.show()
            self._window.raise_()
            self._window.activateWindow()
            self._running = True
            self._timer.start(500)
            return
        try:
            from PyQt6.QtCore import QTimer
            from PyQt6.QtGui import QColor, QFont, QIcon, QTextCursor
            from PyQt6.QtWidgets import (
                QApplication,
                QFrame,
                QHBoxLayout,
                QLabel,
                QMainWindow,
                QPlainTextEdit,
                QPushButton,
                QSizePolicy,
                QTableWidget,
                QTableWidgetItem,
                QVBoxLayout,
                QWidget,
            )
        except ImportError as e:
            log.warning(f"PyQt6 tidak terinstall. Dashboard tidak tersedia: {e}")
            self._fallback_console()
            return

        # Create QApplication if not exists
        self._app = QApplication.instance() or QApplication(sys.argv)
        self._app.setStyle("Fusion")

        # Main window
        self._window = QMainWindow()
        self._window.setWindowTitle("AI Trading Bot — Dashboard")
        self._window.setMinimumSize(700, 500)
        self._window.resize(800, 600)

        # Central widget
        central = QWidget()
        self._window.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setSpacing(8)
        layout.setContentsMargins(12, 12, 12, 12)

        # ── Status bar ────────────────────────────────────────────────
        status_frame = QFrame()
        status_frame.setFrameShape(QFrame.Shape.StyledPanel)
        status_layout = QHBoxLayout(status_frame)

        self._status_indicator = QLabel("●")
        self._status_indicator.setStyleSheet("color: gray; font-size: 18px;")
        status_layout.addWidget(self._status_indicator)

        self._status_label = QLabel("Status: Stopped")
        self._status_label.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        status_layout.addWidget(self._status_label)

        status_layout.addStretch()

        self._equity_label = QLabel("Equity: $0.00")
        self._equity_label.setFont(QFont("Consolas", 10))
        status_layout.addWidget(self._equity_label)

        layout.addWidget(status_frame)

        # ── Controls ──────────────────────────────────────────────────
        controls = QHBoxLayout()
        self._start_btn = QPushButton("▶ Start")
        self._start_btn.clicked.connect(self._on_start_click)
        controls.addWidget(self._start_btn)

        self._stop_btn = QPushButton("⏹ Stop")
        self._stop_btn.setEnabled(False)
        self._stop_btn.clicked.connect(self._on_stop_click)
        controls.addWidget(self._stop_btn)

        controls.addStretch()
        layout.addLayout(controls)

        # ── Positions table ───────────────────────────────────────────
        self._pos_table = QTableWidget(0, 4)
        self._pos_table.setHorizontalHeaderLabels(["Symbol", "Qty", "Entry", "P&L"])
        self._pos_table.setMaximumHeight(120)
        self._pos_table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(QLabel("Open Positions:"))
        layout.addWidget(self._pos_table)

        # ── Last signal ────────────────────────────────────────────────
        self._signal_label = QLabel("Last Signal: --")
        self._signal_label.setWordWrap(True)
        self._signal_label.setStyleSheet(
            "background: #1a1a2e; color: #22c55e; padding: 6px; border-radius: 4px; font-family: Consolas;"
        )
        layout.addWidget(self._signal_label)

        # ── Log viewer ─────────────────────────────────────────────────
        self._log_view = QPlainTextEdit()
        self._log_view.setReadOnly(True)
        self._log_view.setMaximumBlockCount(500)
        self._log_view.setFont(QFont("Consolas", 9))
        self._log_view.setStyleSheet(
            "background: #0d1117; color: #c9d1d9; padding: 6px;"
        )
        layout.addWidget(QLabel("Log:"))
        layout.addWidget(self._log_view)

        # ── Timer to poll queue ────────────────────────────────────────
        self._timer = QTimer()
        self._timer.timeout.connect(self._poll_queue)
        self._timer.start(500)  # every 500ms

        self._window.show()
        self._running = True

        def on_close_event(event):
            """Hide window instead of closing — keeps engine alive in background."""
            event.ignore()
            self._window.hide()
            self._running = False
            self._timer.stop()
            log.info("Dashboard window hidden (engine continues running)")

        self._window.closeEvent = on_close_event  # type: ignore

    def _on_start_click(self):
        if hasattr(self, '_on_start_cb'):
            self._on_start_cb()
        self._start_btn.setEnabled(False)
        self._stop_btn.setEnabled(True)

    def _on_stop_click(self):
        if hasattr(self, '_on_stop_cb'):
            self._on_stop_cb()
        self._start_btn.setEnabled(True)
        self._stop_btn.setEnabled(False)

    def set_callbacks(self, on_start: Callable, on_stop: Callable):
        self._on_start_cb = on_start
        self._on_stop_cb = on_stop

    def _poll_queue(self):
        """Called by QTimer — processes engine messages."""
        try:
            while True:
                msg = self.queue.get_nowait()
                self._handle_message(msg)
        except Exception:
            pass

    def _handle_message(self, msg: str):
        """Handle a message from the trading engine queue."""
        # Log it
        timestamp = datetime.now().strftime("%H:%M:%S")
        self._log_lines.append(f"[{timestamp}] {msg}")
        if self._log_view:
            self._log_view.appendPlainText(f"[{timestamp}] {msg}")
            cursor = self._log_view.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.End)
            self._log_view.setTextCursor(cursor)

        if msg.startswith("status:"):
            status = msg.split(":", 1)[1]
            self._status = status
            self._status_label.setText(f"Status: {status.title()}")
            if status == "running":
                self._status_indicator.setStyleSheet("color: #22c55e; font-size: 18px;")
                self._start_btn.setEnabled(False)
                self._stop_btn.setEnabled(True)
            elif status == "stopped":
                self._status_indicator.setStyleSheet("color: gray; font-size: 18px;")
                self._start_btn.setEnabled(True)
                self._stop_btn.setEnabled(False)
            else:
                self._status_indicator.setStyleSheet("color: orange; font-size: 18px;")

        elif msg.startswith("account:"):
            eq = msg.split(":", 1)[1]
            self._equity = eq
            self._equity_label.setText(f"Equity: ${eq}")

        elif msg.startswith("signal:"):
            signal_info = msg.split(":", 1)[1]
            self._last_signal = signal_info
            self._signal_label.setText(f"Signal: {signal_info}")

        elif msg == "dashboard:focus":
            self.focus()

        elif msg.startswith("error:"):
            err = msg.split(":", 1)[1]
            self._signal_label.setText(f"⚠ Error: {err}")
            self._signal_label.setStyleSheet(
                "background: #1a1a2e; color: #ef4444; padding: 6px; border-radius: 4px; font-family: Consolas;"
            )

    def focus(self) -> None:
        """Bring dashboard window to front — show if hidden."""
        if self._window:
            if not self._window.isVisible():
                self.show()
            else:
                self._window.raise_()
                self._window.activateWindow()

    def close(self):
        """Close the dashboard window."""
        if self._window:
            self._window.close()
        self._running = False

    def _fallback_console(self):
        """Fallback: print to console if PyQt6 not available."""
        log.info("Dashboard tidak tersedia (PyQt6 belum diinstall).")
        log.info("Jalankan: pip install PyQt6")
        print("\n[DASHBOARD] PyQt6 not installed. Install with: pip install PyQt6")
