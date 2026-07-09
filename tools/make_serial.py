#!/usr/bin/env python3
"""Generate AI Trading Radar serial keys for customers.

Examples:
    python tools/make_serial.py --plan 1m
    python tools/make_serial.py --plan 3m --customer "Budi"
    python tools/make_serial.py --plan lifetime
    python tools/make_serial.py --plan 1y --expires 2027-12-31
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from aitrader_bot.licensing import LicenseError, issue_serial_key  # noqa: E402

SERIAL_LOG_PATH = PROJECT_ROOT / "generated_serial_keys.txt"


def _parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("Gunakan format tanggal YYYY-MM-DD") from exc


def _append_serial_log(payload: dict[str, str]) -> None:
    lines = [
        "AI Trading Radar Serial Key",
        "=========================",
    ]
    if payload["customer"]:
        lines.append(f"Customer : {payload['customer']}")
    lines.extend(
        [
            f"Serial   : {payload['serial']}",
            f"Plan     : {payload['plan']}",
            f"Issued   : {payload['issued_on']}",
            f"Expires  : {payload['expires_on']}",
            f"ID       : {payload['license_id']}",
            "",
        ]
    )
    with SERIAL_LOG_PATH.open("a", encoding="utf-8") as file:
        file.write("\n".join(lines))


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate AI Trading Radar serial key")
    parser.add_argument(
        "--plan",
        required=True,
        help="Pilihan: 1m, 3m, 6m, 1y, lifetime",
    )
    parser.add_argument("--issued", type=_parse_date, default=date.today())
    parser.add_argument("--expires", type=_parse_date, help="Override tanggal expiry YYYY-MM-DD")
    parser.add_argument("--customer", default="", help="Nama customer untuk catatan output")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    args = parser.parse_args()

    try:
        info = issue_serial_key(args.plan, issued_on=args.issued, expires_on=args.expires)
    except LicenseError as exc:
        raise SystemExit(f"ERROR: {exc}") from exc

    payload = {
        "customer": args.customer,
        "serial": info.serial,
        "plan": info.plan_label,
        "issued_on": args.issued.isoformat(),
        "expires_on": info.expires_on.isoformat() if info.expires_on else "Lifetime",
        "license_id": info.license_id,
    }
    _append_serial_log(payload)

    if args.json:
        print(json.dumps(payload, indent=2))
        print(f"Saved to : {SERIAL_LOG_PATH}")
        return

    print("AI Trading Radar Serial Key")
    print("=========================")
    if args.customer:
        print(f"Customer : {args.customer}")
    print(f"Serial   : {info.serial}")
    print(f"Plan     : {info.plan_label}")
    print(f"Issued   : {args.issued.isoformat()}")
    print(f"Expires  : {payload['expires_on']}")
    print(f"ID       : {info.license_id}")
    print(f"Saved to : {SERIAL_LOG_PATH}")


if __name__ == "__main__":
    main()

