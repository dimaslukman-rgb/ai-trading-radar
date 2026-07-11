"""HTTP contract tests for the local dashboard API."""

from __future__ import annotations

import json
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from unittest.mock import patch

from aitrader_bot.app import dashboard_data as dd
from aitrader_bot.app.web_dashboard import start_web_dashboard
from aitrader_bot.broker.base import AccountInfo, ExchangeType


class _FakeMt5Broker:
    passwords: list[str] = []

    def __init__(self, server="", login=None, password="") -> None:
        self.server = server
        self.login = login
        if password:
            type(self).passwords.append(password)

    def connect(self) -> bool:
        return True

    def disconnect(self) -> None:
        return None

    def get_account(self) -> AccountInfo:
        return AccountInfo(
            ExchangeType.MT5,
            10000.0,
            10025.0,
            margin=100.0,
            margin_free=9925.0,
            leverage=100,
            currency="USD",
        )


class DashboardApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.server = start_web_dashboard("127.0.0.1", 0)
        cls.base_url = f"http://127.0.0.1:{cls.server.server_address[1]}"

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self) -> None:
        _FakeMt5Broker.passwords.clear()
        dd.update(
            status="running",
            symbol="XAUUSD",
            equity=10000.0,
            balance=10000.0,
            logs=[],
            trades=[],
            open_positions=[],
        )
        dd.update_mt5_status(False)

    def _request(self, path: str, *, method: str = "GET", payload=None):
        body = None if payload is None else json.dumps(payload).encode("utf-8")
        request = Request(
            self.base_url + path,
            data=body,
            method=method,
            headers={"Content-Type": "application/json"},
        )
        try:
            response = urlopen(request, timeout=3)
        except HTTPError as error:
            response = error
        with response:
            raw = response.read()
            content_type = response.headers.get("Content-Type", "")
            data = json.loads(raw) if "application/json" in content_type else raw.decode("utf-8")
            return response.status, content_type, data

    def test_status_and_logs_endpoints_return_dashboard_snapshot(self) -> None:
        dd.add_log("engine ready")
        dd.add_trade("OPEN LONG", "XAUUSD", 3300.0, 0.1, "test")

        status, content_type, snapshot = self._request("/api/status?fresh=1")
        logs_status, _, logs = self._request("/api/logs")

        self.assertEqual(status, 200)
        self.assertIn("application/json", content_type)
        self.assertEqual(snapshot["symbol"], "XAUUSD")
        self.assertEqual(logs_status, 200)
        self.assertEqual(logs["logs"][-1]["msg"], "engine ready")
        self.assertEqual(logs["trades"][-1]["action"], "OPEN LONG")

    def test_html_and_unknown_api_routes_have_explicit_contracts(self) -> None:
        html_status, content_type, html = self._request("/")
        missing_status, _, missing = self._request("/api/unknown")

        self.assertEqual(html_status, 200)
        self.assertIn("text/html", content_type)
        self.assertIn("AI Trading", html)
        self.assertEqual(missing_status, 404)
        self.assertEqual(missing, {"error": "not found"})

    def test_mt5_login_validation_rejects_missing_credentials(self) -> None:
        status, _, data = self._request(
            "/api/mt5/login",
            method="POST",
            payload={"server": "", "login": None, "password": ""},
        )

        self.assertEqual(status, 400)
        self.assertFalse(data["success"])

    def test_mt5_login_status_and_logout_clear_sensitive_account_state(self) -> None:
        with patch("aitrader_bot.app.web_dashboard.Mt5Broker", _FakeMt5Broker):
            login_status, _, login = self._request(
                "/api/mt5/login",
                method="POST",
                payload={"server": "Fake-Demo", "login": "12345", "password": "secret"},
            )
            status_code, _, mt5_status = self._request("/api/mt5/status")
            logout_status, _, logout = self._request(
                "/api/mt5/logout",
                method="POST",
                payload={},
            )
            _, _, after_logout = self._request("/api/mt5/status")

        self.assertEqual(login_status, 200)
        self.assertTrue(login["success"])
        self.assertEqual(status_code, 200)
        self.assertTrue(mt5_status["connected"])
        self.assertEqual(mt5_status["login"], 12345)
        self.assertEqual(_FakeMt5Broker.passwords, ["secret"])
        self.assertEqual(logout_status, 200)
        self.assertTrue(logout["success"])
        self.assertEqual(after_logout, {
            "connected": False,
            "login": None,
            "server": "",
            "account_info": None,
            "last_error": "",
        })
        self.assertNotIn("secret", json.dumps(dd.snapshot()))


if __name__ == "__main__":
    unittest.main()
