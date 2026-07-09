"""Logging setup â€” rotating file handler for production use.

Log location: %APPDATA%/AITradingRadar/logs/
File: trading_bot.log (max 5MB, 5 backups)
"""

from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path


def get_log_dir() -> Path:
    """Get the application log directory (in %APPDATA%)."""
    app_data = os.environ.get("APPDATA", str(Path.home() / "AppData" / "Roaming"))
    log_dir = Path(app_data) / "AITradingRadar" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir


def setup_logging(name: str = "AITradingRadar", level: int = logging.INFO) -> logging.Logger:
    """Configure and return a logger with rotating file and console handler.

    Usage:
        from aitrader_bot.app.logger import setup_logging
        log = setup_logging()
        log.info("Trading bot started")
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)

    # Avoid duplicate handlers on re-initialization
    if logger.handlers:
        return logger

    # Format
    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # --- Rotating file handler ---
    log_dir = get_log_dir()
    log_file = log_dir / "trading_bot.log"
    file_handler = RotatingFileHandler(
        filename=str(log_file),
        maxBytes=5 * 1024 * 1024,  # 5 MB
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(level)
    logger.addHandler(file_handler)

    # --- Console handler ---
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    console_handler.setLevel(level)
    logger.addHandler(console_handler)

    logger.info(f"Logging initialized: {log_file}")
    return logger

