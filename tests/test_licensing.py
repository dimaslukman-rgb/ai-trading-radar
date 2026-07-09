import unittest
from datetime import date

from aitrader_bot.licensing import LicenseError, issue_serial_key, validate_serial_key


class LicensingTests(unittest.TestCase):
    def test_issued_monthly_key_valid_until_expiry(self) -> None:
        info = issue_serial_key("1m", issued_on=date(2026, 1, 31), random_bytes=b"abcde")
        self.assertEqual(info.expires_on, date(2026, 2, 28))

        validated = validate_serial_key(info.serial, today=date(2026, 2, 28))
        self.assertEqual(validated.plan_label, "1 bulan")
        self.assertEqual(validated.expires_on, date(2026, 2, 28))

    def test_expired_key_is_rejected(self) -> None:
        info = issue_serial_key("1m", issued_on=date(2026, 1, 1), random_bytes=b"12345")
        with self.assertRaises(LicenseError):
            validate_serial_key(info.serial, today=date(2026, 2, 2))

    def test_lifetime_key_has_no_expiry(self) -> None:
        info = issue_serial_key("lifetime", issued_on=date(2026, 1, 1), random_bytes=b"zzzzz")
        validated = validate_serial_key(info.serial, today=date(2099, 1, 1))
        self.assertTrue(validated.is_lifetime)
        self.assertIsNone(validated.expires_on)

    def test_tampered_key_is_rejected(self) -> None:
        info = issue_serial_key("3m", issued_on=date(2026, 1, 1), random_bytes=b"qqqqq")
        tampered = info.serial[:-1] + ("A" if info.serial[-1] != "A" else "B")
        with self.assertRaises(LicenseError):
            validate_serial_key(tampered, today=date(2026, 1, 2))


if __name__ == "__main__":
    unittest.main()
