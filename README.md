---
title: Kripto Mania
emoji: 🤖
colorFrom: blue
colorTo: indigo
sdk: docker
app_port: 7860
pinned: false
---

# 🤖 Kripto Mania: Pro-Trader Auto Bot (Indodax)

**Kripto Mania** adalah robot *trading cryptocurrency* cerdas yang dirancang khusus untuk memantau pasar **Indodax** selama 24 jam nonstop. Menggunakan perpaduan Indikator Teknikal klasik dan algoritma **Machine Learning (KNN)**, bot ini dapat belajar dari pengalaman (Live Adaptive Learning) dan melakukan **Auto-Trade** layaknya seorang *Pro-Trader*.

---

## 🔥 Fitur Utama

- 🧠 **Machine Learning (KNN) & Self-Learning Engine:** Bot mencatat riwayat kemenangannya sendiri (`signal_journal.db`) dan beradaptasi dengan kondisi pasar secara *live*. Ia tahu pola mana yang terbukti cuan dan pola mana yang merupakan *Fake Pump*.
- ⚔️ **Sistem "Confluence" Multi-Indikator:** Tidak cuma asal tebak. Keputusan "Beli Kuat" mensyaratkan pertemuan dari EMA-200 (Tren Utama), RSI (Oversold), MACD (Crossover), Bollinger Bands, dan ADX.
- 🛡️ **Pertahanan Tingkat Dewa (Trailing Stop & Auto-Cutloss):** Modal Anda dilindungi secara ekstrem. Profit akan dikunci dengan menggeser titik *Take Profit* (Trailing Stop) secara otomatis saat harga naik. Jika harga anjlok menembus *Support*, bot langsung melakukan *Cutloss* tanpa emosi.
- 💸 **Auto-Trade di Indodax:** Tidak perlu repot klik beli. Mesin `indodax_trade.py` secara khusus mengeksekusi order instan (*Limit-to-Market emulation*) untuk menghindari slippage (nyangkut) di orderbook Indodax.
- 🌐 **Binance Cross-Validation (Opsional):** Bot mengecek buku order dari *market* dunia (Binance) untuk menghindari pompom bandar lokal.
- 📱 **Notifikasi Telegram *Real-Time*:** Laporan hasil trading langsung masuk ke HP Anda.

---

## 🛠️ Cara Kerja "Sang Pro-Trader"

Bot mengeksekusi logika yang terinspirasi dari strategi *Pro-Trader* (seperti `NarwanStrategy`), namun dengan *timeframe* ganda:
1. **Trend Filter (1H):** Harga koin harus berada di atas **EMA-200** (Uptrend).
2. **Timing Entry (15m & 60s loop):** Masuk saat **RSI** menyentuh angka oversold dan garis **MACD** melakukan *bullish crossover* dari bawah.
3. **Volume Confirmation:** Dikonfirmasi oleh lonjakan volume (*Volume Ratio* > rata-rata).

---

## 🚀 Panduan Instalasi (Hugging Face Spaces)

Proyek ini sangat disarankan untuk di-*deploy* di **Hugging Face Spaces (Docker)** agar bot dapat hidup 24/7 di server awan secara gratis tanpa membebani laptop Anda.

### Langkah-Langkah:
1. Buka [huggingface.co/spaces](https://huggingface.co/spaces) dan buat Space baru (Pilih SDK: **Docker** > Blank).
2. Upload seluruh folder proyek ini (termasuk `Dockerfile`, `app.py`, `telegram_bot.py`).
3. Masuk ke **Settings** > **Variables and secrets**.
4. Tambahkan seluruh *Secrets* wajib di bawah ini.

### 🔑 Kunci Rahasia (Secrets) yang Dibutuhkan

Pastikan kunci-kunci ini diisi **HANYA** pada bagian *Secrets* (bukan di bagian *Variables* agar tidak terjadi `Collision`):

```env
# 1. API Indodax (Wajib untuk fitur Auto-Trade)
INDODAX_API_KEY="CEPOF8F8-..."
INDODAX_SECRET_KEY="f318776a..."

# 2. Telegram Bot (Wajib untuk notifikasi)
TELEGRAM_BOT_TOKEN="8947452796:..."
TELEGRAM_CHAT_ID="-100..."

# 3. API Binance (Opsional, untuk validasi silang data global)
# Gunakan fitur "Unrestricted IP" dan "Enable Reading Only" di pengaturan API Binance.
BINANCE_API_KEY="vraM..."
BINANCE_SECRET_KEY="9scL..."

# 4. API Eksternal AI & Berita (Opsional)
DEEPSEEK_API_KEY="sk-..."
GEMINI_API_KEY="AIza..."
```

---

## 💻 Panduan Menjalankan Secara Lokal (Di Laptop)

Jika Anda ingin menjalankan bot secara lokal untuk bereksperimen:

1. Buat *virtual environment*:
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # Di Mac/Linux
   ```
2. Install dependensi:
   ```bash
   pip install -r requirements.txt
   ```
3. Buat file `.streamlit/secrets.toml` dan masukkan kunci Anda (format sama seperti *Secrets* di atas).
4. Nyalakan Bot Telegram (Background Worker):
   ```bash
   python telegram_bot.py
   ```
5. Nyalakan Web Dashboard (Frontend):
   ```bash
   streamlit run app.py
   ```

---
*Dikembangkan dengan 🩵 untuk mengubah Rp 881k menjadi Rp 10 Juta!*
