import pytest
from datetime import date, timedelta
from aitrader_bot.licensing import (
    issue_serial_key,
    validate_serial,
    LicenseError,
    load_license,
    save_license,
    reset_license,
    _sign_serial,
)

def test_serial_roundtrip():
    info = issue_serial_key("1m")
    valid = validate_serial(info.serial)
    assert valid.plan_label == "1m"
    assert valid.license_id == info.license_id
    assert valid.expires_on == date.today() + timedelta(days=30)

def test_lifetime_serial():
    info = issue_serial_key("lifetime")
    valid = validate_serial(info.serial)
    assert valid.expires_on is None

def test_expired_serial():
    past = date.today() - timedelta(days=10)
    info = issue_serial_key("1m", issued_on=past - timedelta(days=30), expires_on=past)
    with pytest.raises(LicenseError, match="expired"):
        validate_serial(info.serial)

def test_tampered_signature():
    info = issue_serial_key("1m")
    parts = info.serial.split("|")
    parts[-1] = "0000000000000000000000000000000000000000000000000000000000000000"
    tampered = "|".join(parts)
    with pytest.raises(LicenseError, match="signature mismatch"):
        validate_serial(tampered)

def test_storage(monkeypatch, tmp_path):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    reset_license()
    assert load_license() is None

    info = issue_serial_key("1m")
    save_license(info)

    loaded = load_license()
    assert loaded is not None
    assert loaded.serial == info.serial

    reset_license()
    assert load_license() is None
