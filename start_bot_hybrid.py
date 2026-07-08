"""Start bot with Hybrid parameters — detached, no console window."""
import subprocess, sys, time, json, os

cwd = r"C:\Users\ASUS\Documents\Codex\2026-07-06\sa\outputs\ai-trading-bot"

# Verify config
with open(os.path.join(cwd, "config_finex.json")) as f:
    cfg = json.load(f)
sc = cfg["scalping"]
print(f"PARAMS: EMA {sc['ema_fast']}/{sc['ema_slow']} MACD({sc['macd_fast']},{sc['macd_slow']},{sc['macd_signal']})")
print(f"        Lock={sc['trailing_stop_pips']}p TP={sc['take_profit_pips']}p min_buy={sc['min_buy_score']}")
print()

# Kill port zombies
os.system(f'for /f "tokens=5" %p in (\'netstat -ano ^| findstr :9190\') do taskkill /F /PID %p 2>nul')
time.sleep(1)

# Start bot
p = subprocess.Popen(
    [sys.executable, "run_scalping.py", "--no-gui", "--auto-start"],
    cwd=cwd,
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL,
    creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
    close_fds=True,
)
print(f"Bot PID: {p.pid}")

# Wait and check dashboard
for i in range(10):
    time.sleep(1.5)
    try:
        import urllib.request
        r = urllib.request.urlopen("http://127.0.0.1:9190/api/status", timeout=2)
        d = json.loads(r.read())
        print(f"DASHBOARD LIVE! Status: {d['status']}")
        print(f"  Equity: ${float(d.get('equity',0)):,.2f}")
        print(f"  Signal: {d.get('last_signal','waiting')}")
        sys.exit(0)
    except:
        if i == 9:
            print("Dashboard not responding after 15s")
