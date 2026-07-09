# AI Trading Radar Windows Package

File utama:

- `AITradingRadar.exe` - aplikasi Windows hasil PyInstaller.
- `config.json` - konfigurasi yang bisa diedit.
- `Start_AITradingRadar.bat` - buka dashboard tanpa auto-start live trading.
- `Start_MT5_AutoTrading.bat` - jalankan auto-trading MT5 setelah `config.json` diisi.
- `Start_Paper_AutoTest.bat` - mode paper untuk cek aplikasi tanpa broker real.

Lisensi:

- Aplikasi wajib memakai SERIAL KEY NUMBER saat pertama dibuka.
- Serial disimpan di `%APPDATA%\AITradingRadar\license.json`.
- Jika serial expired, aplikasi akan meminta serial baru.
- Tool pembuat serial ada di source project: `tools\make_serial.py`.
- Jangan ikutkan folder `tools` atau source code ke customer.

Syarat live trading MT5/Finex:

1. MetaTrader 5 sudah terinstall di komputer target.
2. Akun Finex/MT5 sudah valid dan AutoTrading di MT5 aktif.
3. Isi `brokers.mt5.login`, `brokers.mt5.password`, dan `brokers.mt5.server` di `config.json`.
4. Jalankan `Start_MT5_AutoTrading.bat`.

Default paket ini memakai broker `default`/paper supaya aplikasi bisa dibuka tanpa kredensial real.

