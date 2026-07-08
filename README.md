AI Trading Bot

Bot ini dibuat dengan inspirasi dari HKUDS AI-Trader.
Fokusnya adalah bot mandiri untuk backtest, paper trading, sinyal, dan publikasi sinyal ke AI-Trader.

Fitur utama:

- Backtest dari file CSV.
- Sinyal buy, sell, hold dengan skor momentum, RSI, tren, dan volatilitas.
- Risk manager dengan max posisi, max trade, stop loss, dan take profit.
- Paper execution. Tidak ada order uang nyata.
- Adapter publish sinyal ke AI-Trader lewat AI_TRADER_TOKEN.
- Tanpa dependensi berat. Cukup Python standar.

Struktur:

- aitrader_bot/config.py untuk konfigurasi.
- aitrader_bot/strategy.py untuk model sinyal.
- aitrader_bot/risk.py untuk kontrol risiko.
- aitrader_bot/backtest.py untuk simulasi.
- aitrader_bot/ai_trader_client.py untuk integrasi AI-Trader.
- data/sample_prices.csv untuk contoh data.

Cara pakai:

1. Masuk ke folder project.

cd outputs/ai-trading-bot

2. Jalankan backtest contoh.

python -m aitrader_bot.cli backtest --config config.example.json --data data/sample_prices.csv

3. Ambil sinyal dari data contoh.

python -m aitrader_bot.cli signal --config config.example.json --data data/sample_prices.csv

4. Ambil sinyal dari Yahoo Finance.

python -m aitrader_bot.cli signal --config config.example.json --range 6mo --interval 1d

5. Publish sinyal ke AI-Trader.

set AI_TRADER_TOKEN=token_kamu
python -m aitrader_bot.cli signal --config config.example.json --data data/sample_prices.csv --publish

TradingView dashboard:

Double click file ini:

open-tradingview-dashboard.bat

Atau buka langsung:

tradingview-dashboard.html

Dashboard ini memakai TradingView Advanced Chart Widget.
Fungsinya untuk melihat chart real-time.
Bot Python belum membaca data langsung dari TradingView.

Untuk instruksi lengkap, baca:

TRADINGVIEW_SETUP.txt

Format CSV:

date,open,high,low,close,volume
2026-01-01,42000,43000,41500,42800,1000

Parameter penting:

- min_buy_score: makin tinggi, bot makin selektif untuk buy.
- min_sell_score: makin dekat ke 0, bot makin cepat sell.
- max_position_pct: batas nilai posisi dari total equity.
- max_trade_pct: batas nilai 1 trade dari total equity.
- stop_loss_pct: batas rugi per posisi.
- take_profit_pct: target profit per posisi.

Referensi:

https://github.com/HKUDS/AI-Trader
https://ai4trade.ai
