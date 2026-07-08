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

_EVENT_PROFILES: dict[str, dict[str, str]] = {
    "FOMC": {
        "category": "Fed / FOMC",
        "impact": "HIGH",
        "currency": "USD",
        "bias": "VOLATILITY",
        "note": "Hawkish Fed tends to pressure XAUUSD; dovish Fed tends to support gold.",
    },
    "CPI": {
        "category": "US Inflation",
        "impact": "HIGH",
        "currency": "USD",
        "bias": "VOLATILITY",
        "note": "Hot inflation can lift USD/yields and weigh on gold; soft inflation can support gold.",
    },
    "PCE": {
        "category": "US Inflation",
        "impact": "HIGH",
        "currency": "USD",
        "bias": "VOLATILITY",
        "note": "Fed-preferred inflation data. Softer prints are usually gold supportive.",
    },
    "NFP": {
        "category": "US Labor",
        "impact": "HIGH",
        "currency": "USD",
        "bias": "VOLATILITY",
        "note": "Strong labor data can support USD/yields; weak labor data can support XAUUSD.",
    },
}


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


def _event_profile(name: str) -> dict[str, str]:
    upper_name = name.upper()
    for key, profile in _EVENT_PROFILES.items():
        if key in upper_name:
            return profile
    return {
        "category": "Macro",
        "impact": "MEDIUM",
        "currency": "USD",
        "bias": "WATCH",
        "note": "Monitor USD reaction, yields, and risk sentiment for XAUUSD impact.",
    }


def _format_countdown(seconds_until: int) -> str:
    if seconds_until < 0:
        seconds_until = abs(seconds_until)
        suffix = "ago"
    else:
        suffix = "left"
    minutes = seconds_until // 60
    if minutes < 60:
        return f"{minutes}m {suffix}"
    hours = minutes // 60
    rem_minutes = minutes % 60
    if hours < 24:
        return f"{hours}h {rem_minutes}m {suffix}"
    days = hours // 24
    rem_hours = hours % 24
    return f"{days}d {rem_hours}h {suffix}"


def get_upcoming_events(
    dt: datetime | None = None,
    hours_ahead: int = 168,
    hours_after: int = 2,
    limit: int = 8,
) -> list[dict[str, Any]]:
    """Return upcoming/recent high-impact macro events for the dashboard."""
    if dt is None:
        dt = datetime.now()

    rows: list[dict[str, Any]] = []
    horizon = timedelta(hours=hours_ahead)
    after_window = timedelta(hours=hours_after)

    for month, day, hour, minute, name in _get_events_for_year(dt.year):
        try:
            event_dt = datetime(dt.year, month, day, hour, minute)
        except (ValueError, OverflowError):
            continue

        diff = event_dt - dt
        if diff < -after_window or diff > horizon:
            continue

        seconds_until = int(diff.total_seconds())
        profile = _event_profile(name)
        rows.append({
            "name": name,
            "category": profile["category"],
            "impact": profile["impact"],
            "currency": profile["currency"],
            "bias": profile["bias"],
            "note": profile["note"],
            "time": event_dt.strftime("%d %b %H:%M"),
            "event_time": event_dt.isoformat(),
            "seconds_until": seconds_until,
            "countdown": _format_countdown(seconds_until),
            "phase": "upcoming" if seconds_until >= 0 else "recent",
        })

    rows.sort(key=lambda item: item["seconds_until"])
    return rows[:limit]


def get_macro_sentiment(dt: datetime | None = None) -> dict[str, Any]:
    """Build an XAUUSD macro sentiment snapshot for the dashboard.

    This is a scheduled-catalyst risk model, not a live news scraper. It
    highlights catalysts that typically move gold through USD, real yields,
    Fed expectations, and risk-off flows.
    """
    if dt is None:
        dt = datetime.now()

    events = get_upcoming_events(dt=dt, hours_ahead=168, hours_after=2, limit=8)
    upcoming = [e for e in events if e["seconds_until"] >= 0]
    nearest = upcoming[0] if upcoming else None

    risk_score = 25
    bias = "NEUTRAL"
    summary = "No major scheduled USD catalyst inside the next 7 days. Watch DXY, US yields, and risk sentiment."

    if nearest:
        hours = nearest["seconds_until"] / 3600
        if hours <= 6:
            risk_score = 90
            bias = "HIGH VOLATILITY"
            summary = f"{nearest['category']} event within 6h: expect wider XAUUSD spreads and two-way volatility."
        elif hours <= 24:
            risk_score = 80
            bias = "VOLATILITY WATCH"
            summary = f"{nearest['category']} event within 24h: XAUUSD may react sharply to USD/yield repricing."
        elif hours <= 72:
            risk_score = 65
            bias = "EVENT RISK"
            summary = f"{nearest['category']} event in {nearest['countdown']}: reduce confidence in clean technical signals."
        else:
            risk_score = 45
            bias = "MACRO WATCH"
            summary = f"Next scheduled catalyst: {nearest['name']} in {nearest['countdown']}."

    driver_cards = _build_macro_drivers(events)
    return {
        "bias": bias,
        "risk_score": risk_score,
        "summary": summary,
        "updated_at": dt.strftime("%H:%M:%S"),
        "drivers": driver_cards,
        "events": events,
    }


def _build_macro_drivers(events: list[dict[str, Any]]) -> list[dict[str, str]]:
    def active_event(category: str) -> dict[str, Any] | None:
        for event in events:
            if event["category"] == category and event["seconds_until"] >= 0:
                return event
        return None

    fed = active_event("Fed / FOMC")
    inflation = active_event("US Inflation")
    labor = active_event("US Labor")

    return [
        {
            "name": "Fed / FOMC",
            "status": "ACTIVE WATCH" if fed else "MONITOR",
            "impact": "HIGH",
            "bias": "Two-way volatility" if fed else "Neutral",
            "note": fed["note"] if fed else "Track rate-cut/hike expectations and Fed speaker tone.",
        },
        {
            "name": "Inflation (CPI/PCE)",
            "status": "ACTIVE WATCH" if inflation else "MONITOR",
            "impact": "HIGH",
            "bias": "Hot bearish, cool bullish" if inflation else "Neutral",
            "note": inflation["note"] if inflation else "Gold is sensitive to real-yield repricing after inflation data.",
        },
        {
            "name": "Labor (NFP/jobs)",
            "status": "ACTIVE WATCH" if labor else "MONITOR",
            "impact": "HIGH",
            "bias": "Strong bearish, weak bullish" if labor else "Neutral",
            "note": labor["note"] if labor else "Labor surprises can move USD and Fed expectations quickly.",
        },
        {
            "name": "DXY / US Yields",
            "status": "MANUAL WATCH",
            "impact": "HIGH",
            "bias": "USD up bearish, yields down bullish",
            "note": "Dashboard does not fetch DXY/yields live; confirm externally before trading around macro moves.",
        },
        {
            "name": "Risk-off / Geopolitics",
            "status": "MANUAL WATCH",
            "impact": "MEDIUM",
            "bias": "Risk-off usually bullish gold",
            "note": "Gold can rise on safe-haven demand even when technical signals are mixed.",
        },
    ]


def is_near_news(dt: datetime | None = None, buffer_minutes: int = 15) -> bool:
    """Returns True if within buffer_minutes of a high-impact news event."""
    return get_upcoming_event(dt, buffer_minutes) is not None
