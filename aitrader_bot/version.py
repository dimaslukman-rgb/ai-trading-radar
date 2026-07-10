"""Application version information for AI Trading Radar.

This is the single source of truth for version numbers across the
entire project — used by the updater, installer, build scripts,
and dashboard display.
"""

from __future__ import annotations

import sys

__version__ = "1.2.0"

# Parsed version tuple for numeric comparison
VERSION_TUPLE = tuple(int(x) for x in __version__.split("."))
VERSION_MAJOR = VERSION_TUPLE[0]
VERSION_MINOR = VERSION_TUPLE[1]
VERSION_PATCH = VERSION_TUPLE[2]

APP_NAME = "AI Trading Radar"
APP_SHORT_NAME = "AITradingRadar"


def version_info_text() -> str:
    """Return multi-line version string suitable for --version."""
    lines = [
        f"{APP_NAME} v{__version__}",
        f"Python {sys.version.split()[0]} on {sys.platform}",
        "",
    ]
    return "\n".join(lines)
