"""Licensing system — offline serial validation with HMAC signature."""
from __future__ import annotations
import hashlib
import hmac
import json
import os
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

# Constant secret embedded in binary — change for production releases
SECRET_KEY = b"xauusd-ultra-scalper-2026-v3-secret"

@dataclass(frozen=True)
class LicenseInfo:
    serial: str
    plan_label: str
    issued_on: date
    expires_on: Optional[date]
    license_id: str

class LicenseError(Exception):
    pass

def _license_storage_path() -> Path:
    app_data = Path(os.environ.get("APPDATA", Path.home() / ".config")) / "AITradingRadar"
    app_data.mkdir(parents=True, exist_ok=True)
    return app_data / "license.json"

def _sign_serial(serial_data: str) -> str:
    return hmac.new(SECRET_KEY, serial_data.encode(), hashlib.sha256).hexdigest()

def issue_serial_key(plan: str, issued_on: Optional[date] = None, expires_on: Optional[date] = None) -> LicenseInfo:
    plans = {"1m": 30, "3m": 90, "6m": 180, "1y": 365, "lifetime": None}
    if plan not in plans:
        raise LicenseError(f"Plan tidak valid: {plan}")

    issued = issued_on or date.today()
    expires = expires_on or (issued + timedelta(days=plans[plan]) if plans[plan] else None)

    license_id = os.urandom(8).hex()
    serial_data = f"{license_id}|{plan}|{issued.isoformat()}|{expires.isoformat() if expires else 'lifetime'}"
    signature = _sign_serial(serial_data)
    serial = f"{serial_data}|{signature}"

    return LicenseInfo(serial, plan, issued, expires, license_id)

def validate_serial(serial: str) -> LicenseInfo:
    # 1. Cek format lama (AIB-...)
    if serial.startswith("AIB-"):
        return _validate_legacy_serial(serial)

    # 2. Cek format baru (HMAC)
    return _validate_modern_serial(serial)

def _validate_legacy_serial(serial: str) -> LicenseInfo:
    # Accept any AIB- prefixed serial without full validation for backward compatibility.
    return LicenseInfo(serial, "Legacy", date.today(), None, "legacy")

def _validate_modern_serial(serial: str) -> LicenseInfo:
    parts = serial.split("|")
    if len(parts) != 5:
        raise LicenseError("Serial invalid format")

    serial_data = "|".join(parts[:4])
    signature = parts[4]

    if not hmac.compare_digest(_sign_serial(serial_data), signature):
        raise LicenseError("Serial signature mismatch")

    license_id, plan, issued_str, expires_str = parts[:4]

    if expires_str != "lifetime":
        expires = date.fromisoformat(expires_str)
        if date.today() > expires:
            raise LicenseError("Serial expired")
    else:
        expires = None

    return LicenseInfo(serial, plan, date.fromisoformat(issued_str), expires, license_id)

def load_license() -> Optional[LicenseInfo]:
    path = _license_storage_path()
    if not path.exists(): return None
    try:
        data = json.loads(path.read_text())
        return validate_serial(data["serial"])
    except (json.JSONDecodeError, LicenseError, KeyError):
        return None

def save_license(info: LicenseInfo) -> None:
    _license_storage_path().write_text(json.dumps({"serial": info.serial}, indent=2))

def reset_license() -> None:
    path = _license_storage_path()
    if path.exists(): path.unlink()
