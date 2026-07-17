import json
import logging
import sys
import threading
import time
import urllib.request

logging.disable(logging.CRITICAL)
for name in list(logging.root.manager.loggerDict):
    logging.getLogger(name).disabled = True
logging.basicConfig(handlers=[logging.NullHandler()], level=logging.CRITICAL)

from aitrader_bot.app.engine import TradingEngine
from aitrader_bot.app import dashboard_data as dd
from aitrader_bot.app.web_dashboard import start_web_dashboard

s = start_web_dashboard(port=9190)
e = TradingEngine("config_finex.json", "mt5")

t = threading.Thread(target=e._run, daemon=True)
e._stop.clear()
t.start()

time.sleep(12)
snap = json.load(urllib.request.urlopen("http://127.0.0.1:9190/api/status"))
print("=== DASHBOARD SNAPSHOT ===")
for k in ("status", "broker", "symbol", "price", "equity", "balance",
         "pnl_pct", "drawdown_pct", "active_symbols", "started_at", "telegram"):
    print(f"{k:18} = {snap.get(k)}")
print("mt5 block          =", snap.get("mt5"))
print("logs tail          =", (snap.get("logs") or [])[-5:])
print("trades tail        =", (snap.get("trades") or [])[-3:])
print("positions          =", snap.get("positions"))
print("signal             =", snap.get("signal"))

e._stop.set()
t.join(timeout=5)
try:
    if e.broker:
        e.broker.disconnect()
except Exception:
    pass
s.shutdown()
sys.stdout.flush()
