"""Offline serial-key licensing for AI Trading Radar.

This module uses compact HMAC-signed serial keys. It is designed for simple
offline distribution where the app verifies serials locally on every launch.

Important: because this is offline licensing, a determined attacker can still
patch or reverse engineer the executable. For strong licensing, use an online
activation server.
"""

from __future__ import annotations

import base64
import calendar
import hmac
import hashlib
import json
import os
import secrets
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path


APP_NAME = "AITradingRadar"
SERIAL_PREFIX = "AIB"
_VERSION = 1
_PRODUCT_ID = 0xA1
_EXPIRY_LIFETIME = 0xFFFFFF
_RANDOM_BYTES = 5
_SIGNATURE_BYTES = 8
_PAYLOAD_BYTES = 1 + 1 + 1 + 3 + _RANDOM_BYTES
_SERIAL_BYTES = _PAYLOAD_BYTES + _SIGNATURE_BYTES
_SERIAL_CHARS = (_SERIAL_BYTES * 8 + 4) // 5
_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
_SECRET = base64.b64decode("2PqlNlLN8SLE9XRmk85HfO4daFC3XHIv7yxsFLLfggM=")

PLAN_LABELS = {
    1: "1 bulan",
    3: "3 bulan",
    6: "6 bulan",
    12: "1 tahun",
    255: "Lifetime",
}

PLAN_ALIASES = {
    "1": 1,
    "1m": 1,
    "1mo": 1,
    "1month": 1,
    "1bulan": 1,
    "3": 3,
    "3m": 3,
    "3mo": 3,
    "3month": 3,
    "3bulan": 3,
    "6": 6,
    "6m": 6,
    "6mo": 6,
    "6month": 6,
    "6bulan": 6,
    "12": 12,
    "12m": 12,
    "1y": 12,
    "1yr": 12,
    "1year": 12,
    "1tahun": 12,
    "life": 255,
    "lifetime": 255,
    "permanent": 255,
}


class LicenseError(ValueError):
    """Raised when a license key is missing, invalid, or expired."""


@dataclass(frozen=True)
class LicenseInfo:
    serial: str
    plan_code: int
    plan_label: str
    expires_on: date | None
    license_id: str

    @property
    def is_lifetime(self) -> bool:
        return self.expires_on is None

    @property
    def expires_label(self) -> str:
        if self.is_lifetime:
            return "Lifetime"
        return self.expires_on.isoformat()


def app_data_dir() -> Path:
    app_data = os.environ.get("APPDATA", str(Path.home() / "AppData" / "Roaming"))
    path = Path(app_data) / APP_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def license_file_path() -> Path:
    return app_data_dir() / "license.json"


def issue_serial_key(
    plan: str,
    *,
    issued_on: date | None = None,
    expires_on: date | None = None,
    random_bytes: bytes | None = None,
) -> LicenseInfo:
    """Create a signed serial key for the given plan.

    ``plan`` accepts: 1m, 3m, 6m, 1y, lifetime.
    """
    plan_code = _parse_plan(plan)
    issued = issued_on or date.today()

    if plan_code == 255:
        expiry_days = _EXPIRY_LIFETIME
        expiry_date = None
    else:
        expiry_date = expires_on or _add_months(issued, plan_code)
        expiry_days = _date_to_days(expiry_date)
        if not 0 <= expiry_days < _EXPIRY_LIFETIME:
            raise LicenseError(f"Tanggal expiry tidak valid: {expiry_date}")

    rnd = random_bytes if random_bytes is not None else secrets.token_bytes(_RANDOM_BYTES)
    if len(rnd) != _RANDOM_BYTES:
        raise LicenseError(f"random_bytes harus {_RANDOM_BYTES} byte")

    payload = (
        bytes([_VERSION, _PRODUCT_ID, plan_code])
        + expiry_days.to_bytes(3, "big")
        + rnd
    )
    token = payload + _signature(payload)
    serial = _format_serial(_base32_encode(token))
    return LicenseInfo(
        serial=serial,
        plan_code=plan_code,
        plan_label=PLAN_LABELS[plan_code],
        expires_on=expiry_date,
        license_id=_base32_encode(rnd),
    )


def validate_serial_key(serial: str, *, today: date | None = None) -> LicenseInfo:
    token_text = _normalize_serial(serial)
    if len(token_text) != _SERIAL_CHARS:
        raise LicenseError("Format serial key tidak valid")

    token = _base32_decode(token_text, expected_bytes=_SERIAL_BYTES)
    if _base32_encode(token) != token_text:
        raise LicenseError("Format serial key tidak valid")

    payload = token[:_PAYLOAD_BYTES]
    signature = token[_PAYLOAD_BYTES:]
    if not hmac.compare_digest(signature, _signature(payload)):
        raise LicenseError("Serial key tidak valid")

    version = payload[0]
    product_id = payload[1]
    plan_code = payload[2]
    expiry_days = int.from_bytes(payload[3:6], "big")
    rnd = payload[6:]

    if version != _VERSION or product_id != _PRODUCT_ID:
        raise LicenseError("Serial key bukan untuk aplikasi ini")
    if plan_code not in PLAN_LABELS:
        raise LicenseError("Tipe serial key tidak dikenal")

    expiry_date = None
    if expiry_days != _EXPIRY_LIFETIME:
        expiry_date = _days_to_date(expiry_days)
        now = today or date.today()
        if expiry_date < now:
            raise LicenseError(f"Serial key expired pada {expiry_date.isoformat()}")

    return LicenseInfo(
        serial=_format_serial(token_text),
        plan_code=plan_code,
        plan_label=PLAN_LABELS[plan_code],
        expires_on=expiry_date,
        license_id=_base32_encode(rnd),
    )


def load_stored_license(*, today: date | None = None) -> LicenseInfo | None:
    path = license_file_path()
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        serial = str(data.get("serial", ""))
        return validate_serial_key(serial, today=today)
    except Exception:
        return None


def save_license(info: LicenseInfo) -> None:
    path = license_file_path()
    payload = {
        "serial": info.serial,
        "plan": info.plan_label,
        "expires_on": info.expires_on.isoformat() if info.expires_on else None,
        "license_id": info.license_id,
        "activated_at": datetime.now(timezone.utc).isoformat(),
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def reset_stored_license() -> bool:
    path = license_file_path()
    if path.exists():
        path.unlink()
        return True
    return False


def ensure_license(
    *,
    provided_key: str | None = None,
    allow_prompt: bool = True,
    use_gui_prompt: bool = True,
) -> LicenseInfo:
    if provided_key:
        info = validate_serial_key(provided_key)
        save_license(info)
        return info

    stored = load_stored_license()
    if stored:
        return stored

    if not allow_prompt:
        raise LicenseError("Serial key belum diaktivasi")

    last_error = ""
    for _ in range(3):
        entered = _prompt_for_serial(last_error, use_gui_prompt=use_gui_prompt)
        if not entered:
            raise LicenseError("Serial key wajib diisi untuk menjalankan aplikasi")
        try:
            info = validate_serial_key(entered)
            save_license(info)
            _show_message(
                "Lisensi aktif",
                f"Serial key aktif: {info.plan_label}\nBerlaku sampai: {info.expires_label}",
                use_gui_prompt=use_gui_prompt,
            )
            return info
        except LicenseError as exc:
            last_error = str(exc)

    raise LicenseError(last_error or "Serial key tidak valid")


def license_status_text() -> str:
    info = load_stored_license()
    if not info:
        return "License: belum aktif"
    return (
        f"License: aktif\n"
        f"Plan: {info.plan_label}\n"
        f"Expires: {info.expires_label}\n"
        f"License ID: {info.license_id}\n"
        f"File: {license_file_path()}"
    )


def _parse_plan(plan: str) -> int:
    key = plan.strip().lower().replace("-", "").replace("_", "")
    try:
        return PLAN_ALIASES[key]
    except KeyError as exc:
        raise LicenseError("Plan harus salah satu: 1m, 3m, 6m, 1y, lifetime") from exc


def _signature(payload: bytes) -> bytes:
    return hmac.new(_SECRET, payload, hashlib.sha256).digest()[:_SIGNATURE_BYTES]


def _date_to_days(value: date) -> int:
    return value.toordinal() - date(1970, 1, 1).toordinal()


def _days_to_date(days: int) -> date:
    return date.fromordinal(date(1970, 1, 1).toordinal() + days)


def _add_months(value: date, months: int) -> date:
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def _base32_encode(data: bytes) -> str:
    bits = "".join(f"{byte:08b}" for byte in data)
    pad = (-len(bits)) % 5
    if pad:
        bits += "0" * pad
    return "".join(_ALPHABET[int(bits[i:i + 5], 2)] for i in range(0, len(bits), 5))


def _base32_decode(text: str, *, expected_bytes: int) -> bytes:
    decode_map = {ch: i for i, ch in enumerate(_ALPHABET)}
    decode_map.update({"O": 0, "I": 1, "L": 1})
    try:
        bits = "".join(f"{decode_map[ch]:05b}" for ch in text)
    except KeyError as exc:
        raise LicenseError("Serial key berisi karakter tidak valid") from exc
    needed_bits = expected_bytes * 8
    if len(bits) < needed_bits:
        raise LicenseError("Format serial key tidak valid")
    return int(bits[:needed_bits], 2).to_bytes(expected_bytes, "big")


def _normalize_serial(serial: str) -> str:
    cleaned = "".join(ch for ch in serial.upper() if ch.isalnum())
    if cleaned.startswith(SERIAL_PREFIX):
        cleaned = cleaned[len(SERIAL_PREFIX):]
    return cleaned


def _format_serial(token_text: str) -> str:
    groups = [token_text[i:i + 5] for i in range(0, len(token_text), 5)]
    return SERIAL_PREFIX + "-" + "-".join(groups)


def _prompt_for_serial(last_error: str, *, use_gui_prompt: bool) -> str:
    prompt = "Masukkan SERIAL KEY NUMBER untuk menjalankan AI Trading Radar:"
    if last_error:
        prompt = f"{last_error}\n\n{prompt}"

    if use_gui_prompt:
        try:
            import tkinter as tk
            from tkinter import simpledialog

            root = tk.Tk()
            root.withdraw()
            root.attributes("-topmost", True)
            value = simpledialog.askstring("AI Trading Radar License", prompt, parent=root)
            root.destroy()
            return value or ""
        except Exception:
            pass

    if last_error:
        print(f"[LICENSE] {last_error}")
    try:
        return input("Masukkan SERIAL KEY NUMBER: ").strip()
    except EOFError:
        return ""


def _show_message(title: str, message: str, *, use_gui_prompt: bool) -> None:
    if use_gui_prompt:
        try:
            import tkinter as tk
            from tkinter import messagebox

            root = tk.Tk()
            root.withdraw()
            root.attributes("-topmost", True)
            messagebox.showinfo(title, message, parent=root)
            root.destroy()
            return
        except Exception:
            pass
    print(f"[LICENSE] {message.replace(chr(10), ' | ')}")

