"""Logging setup — rotating file handler for production use.

Log location: %APPDATA%/AITradingBot/logs/
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
    log_dir = Path(app_data) / "AITradingBot" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir


def setup_logging(name: str = "AITradingBot", level: int = logging.INFO) -> logging.Logger:
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
    # A locked profile directory must not prevent a trading process from
    # starting.  Console logging remains available and the next launch can
    # retry the normal file location.
    log_file: Path | None = None
    try:
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
    except OSError:
        # Deliberately avoid logging here: the console handler is not added
        # until below and the failed path may itself be unavailable.
        pass

    # --- Console handler ---
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    console_handler.setLevel(level)
    logger.addHandler(console_handler)

    if log_file is not None:
        logger.info(f"Logging initialized: {log_file}")
    else:
        logger.warning("File logging unavailable; using console logging only")
    return logger
