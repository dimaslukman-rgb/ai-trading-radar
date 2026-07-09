AI Trading Radar - PANDUAN INSTALL DAN CATATAN PENTING
====================================================

Ringkasan penting
-----------------
Saat pertama kali dijalankan, aplikasi akan meminta SERIAL KEY NUMBER.
Minta serial key dari pembuat aplikasi. Aplikasi tidak akan lanjut jika serial
belum diisi, salah, atau sudah expired.

Paket ini default memakai broker paper supaya aman saat pertama dibuka.
Mode paper tidak mengirim order uang real.

Untuk live auto-trading XAUUSD via MT5/Finex, install dulu aplikasinya,
lalu edit file konfigurasi:

  %LOCALAPPDATA%\AITradingRadar\config.json

Isi bagian berikut:

  brokers.mt5.login
  brokers.mt5.password
  brokers.mt5.server

Pastikan juga:

  1. MetaTrader 5 sudah terinstall di komputer target.
  2. Akun Finex/MT5 sudah bisa login di MetaTrader 5.
  3. Symbol XAUUSD tersedia di Market Watch MT5.
  4. AutoTrading/Algo Trading di MT5 aktif.
  5. Komputer punya koneksi internet stabil.
  6. Windows Firewall/antivirus tidak memblokir aplikasi.

Setelah konfigurasi benar, jalankan shortcut:

  AI Trading Radar MT5 AutoTrading

Saya tidak bisa menjamin live trading 100% tanpa error di komputer lain
tanpa syarat di atas, karena MT5, broker login, koneksi internet, market
quote, dan izin Windows/antivirus tetap faktor eksternal.


Cara install dengan installer
-----------------------------
1. Jalankan file:

   AITradingRadar_Setup.exe

2. Tunggu proses install selesai.

3. Aplikasi akan dipasang ke:

   %LOCALAPPDATA%\AITradingRadar

4. Shortcut akan dibuat di Desktop dan Start Menu.

5. Buka aplikasi lewat shortcut:

   AI Trading Radar

   Shortcut ini akan meminta serial key lebih dulu, lalu membuka dashboard
   dalam mode aman/default.

6. Untuk live MT5, edit dulu:

   %LOCALAPPDATA%\AITradingRadar\config.json

7. Setelah kredensial MT5 benar, jalankan:

   AI Trading Radar MT5 AutoTrading


Cara pakai versi portable ZIP
-----------------------------
1. Extract:

   AITradingRadar_Portable.zip

2. Buka folder:

   AITradingRadar

3. Jalankan:

   Start_AITradingRadar.bat

4. Untuk live MT5, edit file:

   config.json

5. Setelah konfigurasi benar, jalankan:

   Start_MT5_AutoTrading.bat


Dashboard dan log
-----------------
Dashboard web biasanya tersedia di:

  http://127.0.0.1:9190

Jika port 9190 terpakai, aplikasi akan mencoba port berikutnya.

Log aplikasi tersimpan di:

  %APPDATA%\AITradingRadar\logs\trading_bot.log


Mode aman untuk tes
-------------------
Untuk mengetes aplikasi tanpa broker real, gunakan:

  Start_Paper_AutoTest.bat

Mode ini memakai broker paper dan tidak mengirim order ke MT5.


Serial key
----------
Cek status lisensi:

  AITradingRadar.exe --license-info

Aktivasi serial lewat command:

  AITradingRadar.exe --license-key "AIB-XXXXX-XXXXX-XXXXX-XXXXX-XXXXX-XXXXX-X"

Reset serial tersimpan:

  AITradingRadar.exe --reset-license


Checklist sebelum live trading
------------------------------
1. Cek config.json sudah berisi login/password/server MT5 yang benar.
2. Cek MT5 sudah login ke akun yang benar.
3. Cek XAUUSD bisa dilihat di MT5.
4. Cek AutoTrading/Algo Trading aktif.
5. Mulai dari lot kecil dan akun demo terlebih dahulu.
6. Pantau dashboard dan log saat pertama kali jalan.

