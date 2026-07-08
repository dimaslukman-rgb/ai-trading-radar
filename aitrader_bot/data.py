from __future__ import annotations

import csv
import json
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from .models import PriceBar


def read_csv_prices(path: str | Path) -> list[PriceBar]:
    bars: list[PriceBar] = []
    with Path(path).open("r", encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            bars.append(
                PriceBar(
                    date=_parse_date(row["date"]),
                    open=float(row["open"]),
                    high=float(row["high"]),
                    low=float(row["low"]),
                    close=float(row["close"]),
                    volume=float(row.get("volume") or 0),
                )
            )
    return bars


def fetch_yahoo_chart(symbol: str, range_: str = "6mo", interval: str = "1d") -> list[PriceBar]:
    query = urllib.parse.urlencode(
        {
            "range": range_,
            "interval": interval,
            "includePrePost": "false",
            "events": "div,splits",
        }
    )
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(symbol)}?{query}"
    request = urllib.request.Request(url, headers={"User-Agent": "ai-trading-bot/0.1"})
    with urllib.request.urlopen(request, timeout=20) as response:
        payload = json.loads(response.read().decode("utf-8"))

    result = payload["chart"]["result"][0]
    timestamps = result["timestamp"]
    quote = result["indicators"]["quote"][0]
    bars: list[PriceBar] = []
    for index, ts in enumerate(timestamps):
        close = quote["close"][index]
        if close is None:
            continue
        bars.append(
            PriceBar(
                date=datetime.fromtimestamp(ts, tz=timezone.utc),
                open=float(quote["open"][index] or close),
                high=float(quote["high"][index] or close),
                low=float(quote["low"][index] or close),
                close=float(close),
                volume=float(quote["volume"][index] or 0),
            )
        )
    return bars


def _parse_date(value: str) -> datetime:
    value = value.strip()
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed
