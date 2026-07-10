📋 Ringkasan Proyek: AI Trading Radar / AI Trading Bot
🎯 Tujuan
Bot trading algoritmik berbasis Python untuk XAUUSD (Gold) scalping dengan dukungan multi-broker, backtesting, dashboard web real-time, dan notifikasi Telegram.
🏗️ Struktur Proyek
ai-trading-bot/
├── aitrader_bot/              # Paket utama
│   ├── __init__.py            # v0.1.0
│   ├── config.py              # Load konfigurasi dari JSON (BotConfig, ScalpingConfig, dll)
│   ├── models.py              # Data classes: PriceBar, Signal, Trade, Position
│   ├── indicators.py          # Indikator teknikal: SMA, EMA, RSI, MACD, Bollinger Bands, Stochastic
│   ├── strategy.py            # AiMomentumStrategy (momentum sederhana)
│   ├── scalping.py            # ⭐ ScalpingStrategy dual-state + ScalpingRiskManager
│   ├── backtest.py            # Mesin backtest (momentum & scalping mode)
│   ├── risk.py                # RiskManager untuk momentum
│   ├── portfolio.py           # Portfolio tracker (cash, positions, trades)
│   ├── data.py                # Baca CSV & fetch Yahoo Finance
│   ├── ai_trader_client.py    # Client API eksternal ai4trade.ai
│   ├── cli.py                 # CLI: backtest, signal, scalp, broker
│   │
│   ├── broker/                # Abstraksi multi-broker
│   │   ├── base.py            # BaseBroker ABC + data types (Quote, Candle, dll)
│   │   ├── paper_broker.py    # Paper trading in-memory
│   │   ├── mt5_broker.py      # ⭐ MetaTrader 5 (Finex) — order_check + order_send
│   │   ├── ccxt_broker.py     # Binance via CCXT
│   │   ├── alpaca_broker.py   # Alpaca untuk US stocks
│   │   └── __init__.py        # Factory: create_broker()
│   │
│   └── app/                   # Aplikasi pendukung
│       ├── engine.py          # ⭐ TradingEngine — background loop thread
│       ├── web_dashboard.py   # HTTP server + SSE untuk dashboard browser
│       ├── dashboard_data.py  # Shared state untuk dashboard
│       ├── dashboard_template.html  # Template HTML dashboard
│       ├── gui.py             # GUI Dashboard PyQt6
│       ├── tray.py            # System tray icon (pystray)
│       ├── notifier.py        # Telegram notifier
│       ├── news_filter.py     # Filter berita high-impact
│       └── logger.py          # Logging setup
│
├── run_scalping.py            # ⭐ Entry point utama (Windows app)
├── start_bot_hybrid.py        # Start detached process
├── report_perf.py             # Laporan performa dari log + backtest
├── setup_finex.py             # Setup wizard Finex MT5
├── setup_telegram.py          # Setup wizard Telegram
├── tradingview-dashboard.html # Dashboard TradingView widget
├── open-tradingview-dashboard.bat
├── config*.json               # File konfigurasi (example & live)
├── data/                      # Sample CSV data XAUUSD
├── tests/test_core.py         # Unit tests (24 tests)
├── build_exe.bat              # Build .exe dengan PyInstaller
├── installer.iss              # Inno Setup installer
└── dist/AITradingBot.exe      # Compiled executable

⚙️ Cara Kerja Inti (ScalpingStrategy - Dual State)
State A — Momentum (ketika volume tinggi / trending):
- EMA 9/21 crossover
- MACD(12,26,9) histogram
- Trend filter timeframe lebih tinggi
- Opsional: RSI + Momentum Velocity (mode agresif M1)

State B — Mean Reversion (ketika sideways):
- Bollinger Bands (20, 2.0) — sentuhan lower/upper band
- Stochastic(14,3,3) — oversold/overbought + crossover

Risk Manager:
- Dynamic position sizing berdasarkan equity
- SL/TP dalam pips (30p/15p normal, 8p/10p agresif)
- Lock profit di +5 pips
- Timeout exit (mode agresif M1: 10 menit)
- News filter & session filter (London/NY)

🔌 Multi-Broker Architecture
4 adapter: Paper (testing), MT5 (Finex), Binance (CCXT), Alpaca (US stocks)
📊 Dashboard Web
- Server HTTP bawaan (tanpa dependensi eksternal)
- SSE (Server-Sent Events) untuk update real-time
- Port default: 9190
- Menampilkan: equity, posisi, signal, analisis, sentimen, volatilitas

📱 Integrasi
- Telegram: notifikasi START/LONG/SHORT/ERROR/STOP
- Finex (MT5): broker utama untuk XAUUSD

🧪 Testing
24 unit tests — strategy, broker paper (buy/sell/insufficient funds/quote/close), indikator, konfigurasi