"""News filter — pause trading near high-impact economic events.

Pauses all trading 15 minutes before and 15 minutes after:
  - NFP (Non-Farm Payrolls) — First Friday every month, 19:30 WIB (8:30 AM ET)
  - FOMC (Federal Reserve meetings) — 8 scheduled meetings per year
  - CPI (Consumer Price Index) — Monthly, typically 19:30 WIB (8:30 AM ET)

Times are in WIB (UTC+7), adjusted for daylight saving where applicable.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

# ── 2026 High-Impact News Schedule (WIB = UTC+7) ─────────────────────
# Format: (month, day, hour, minute, name)
# NFP: First Friday of each month, 19:30 WIB
# CPI: Monthly release, 19:30 WIB (typically same week as NFP)
# FOMC: 8 scheduled meetings per year

_NEWS_EVENTS_2026: list[tuple[int, int, int, int, str]] = [
    # ── January 2026 ─────────────────────────────────────────────────
    (1, 14, 19, 30, "CPI Jan"),
    (1, 16, 19, 30, "NFP Jan"),
    (1, 28, 19, 30, "FOMC Jan"),

    # ── February 2026 ────────────────────────────────────────────────
    (2, 6, 19, 30, "NFP Feb"),
    (2, 12, 19, 30, "CPI Feb"),
    (2, 18, 19, 30, "FOMC Feb"),

    # ── March 2026 ───────────────────────────────────────────────────
    (3, 6, 19, 30, "NFP Mar"),
    (3, 11, 19, 30, "CPI Mar"),
    (3, 18, 19, 30, "FOMC Mar"),

    # ── April 2026 ───────────────────────────────────────────────────
    (4, 3, 19, 30, "NFP Apr"),
    (4, 10, 19, 30, "CPI Apr"),
    (4, 29, 19, 30, "FOMC Apr"),

    # ── May 2026 ─────────────────────────────────────────────────────
    (5, 1, 19, 30, "NFP May"),
    (5, 8, 19, 30, "CPI May"),
    (5, 13, 19, 30, "FOMC May"),

    # ── June 2026 ────────────────────────────────────────────────────
    (6, 5, 19, 30, "NFP Jun"),
    (6, 10, 19, 30, "CPI Jun"),
    (6, 17, 19, 30, "FOMC Jun"),

    # ── July 2026 ────────────────────────────────────────────────────
    (7, 3, 19, 30, "NFP Jul"),
    (7, 10, 19, 30, "CPI Jul"),
    (7, 29, 19, 30, "FOMC Jul"),

    # ── August 2026 ──────────────────────────────────────────────────
    (8, 7, 19, 30, "NFP Aug"),
    (8, 12, 19, 30, "CPI Aug"),

    # ── September 2026 ───────────────────────────────────────────────
    (9, 4, 19, 30, "NFP Sep"),
    (9, 11, 19, 30, "CPI Sep"),
    (9, 16, 19, 30, "FOMC Sep"),

    # ── October 2026 ─────────────────────────────────────────────────
    (10, 2, 19, 30, "NFP Oct"),
    (10, 9, 19, 30, "CPI Oct"),
    (10, 28, 19, 30, "FOMC Oct"),

    # ── November 2026 ────────────────────────────────────────────────
    (11, 6, 19, 30, "NFP Nov"),
    (11, 13, 19, 30, "CPI Nov"),

    # ── December 2026 ────────────────────────────────────────────────
    (12, 4, 19, 30, "NFP Dec"),
    (12, 11, 19, 30, "CPI Dec"),
    (12, 16, 19, 30, "FOMC Dec"),
]


def _get_events_for_year(year: int) -> list[tuple[int, int, int, int, str]]:
    """Return news events for a given year. Currently supports 2026."""
    if year == 2026:
        return _NEWS_EVENTS_2026
    # For future years, return empty list (no filter)
    return []


def get_upcoming_event(
    dt: datetime | None = None,
    buffer_minutes: int = 15,
) -> dict[str, Any] | None:
    """Check if current time is near a high-impact news event.

    Returns event info dict if within buffer_minutes of an event, else None.

    Example return:
      {"name": "NFP Jan", "event_time": datetime(2026,1,16,19,30),
       "seconds_until": 720, "phase": "before"}
    """
    if dt is None:
        dt = datetime.now()

    events = _get_events_for_year(dt.year)
    buffer = timedelta(minutes=buffer_minutes)

    for month, day, hour, minute, name in events:
        try:
            event_dt = datetime(dt.year, month, day, hour, minute)
        except (ValueError, OverflowError):
            continue

        diff = event_dt - dt
        abs_diff = abs(diff)

        if abs_diff <= buffer:
            phase = "before" if diff.total_seconds() > 0 else "after"
            return {
                "name": name,
                "event_time": event_dt,
                "seconds_until": int(diff.total_seconds()),
                "phase": phase,
                "is_paused": True,
            }

    return None


def get_upcoming_events(
    dt: datetime | None = None,
    limit: int = 5,
) -> list[dict[str, Any]]:
    """Return upcoming high-impact events for dashboard display."""
    if dt is None:
        dt = datetime.now()

    events: list[dict[str, Any]] = []
    for month, day, hour, minute, name in _get_events_for_year(dt.year):
        try:
            event_dt = datetime(dt.year, month, day, hour, minute)
        except (ValueError, OverflowError):
            continue
        if event_dt < dt:
            continue

        diff = event_dt - dt
        days = diff.days
        hours = diff.seconds // 3600
        minutes = (diff.seconds % 3600) // 60
        if days > 0:
            countdown = f"{days}d {hours}h"
        elif hours > 0:
            countdown = f"{hours}h {minutes}m"
        else:
            countdown = f"{minutes}m"

        events.append({
            "time": event_dt.strftime("%d %b %H:%M"),
            "impact": "HIGH",
            "currency": "USD",
            "name": name,
            "countdown": countdown,
        })

    return events[:limit]


def is_near_news(dt: datetime | None = None, buffer_minutes: int = 15) -> bool:
    """Returns True if within buffer_minutes of a high-impact news event."""
    return get_upcoming_event(dt, buffer_minutes) is not None
