# Arsitektur Kripto Mania

Dokumen ini menjelaskan arsitektur paket `core/` — otak bersama (shared brain) dari Kripto Mania. Tujuannya supaya siapa pun yang ngoprek proyek ini (termasuk kamu sendiri 6 bulan lagi) bisa paham struktur kodenya tanpa harus baca semua file satu per satu.

## Apa itu Kripto Mania?

Kripto Mania adalah bot trading crypto untuk pasar **Indodax** yang punya dua "permukaan" (surface):

- **Web dashboard** (`app.py`) — aplikasi Streamlit untuk analisis interaktif, watchlist, portfolio, panel learning/news, dan AI advisor.
- **Bot Telegram** (`telegram_bot.py`) — daemon 24/7 yang mengirim sinyal harian, alert FOMO, alert confluence real-time, dan monitor TP/SL otomatis.

Keduanya menganalisis koin yang sama dari sumber data yang sama (Indodax). Masalah klasiknya: kalau logika sinyal diduplikasi di dua tempat, web bisa bilang "CICIL BELI" sementara Telegram bilang "JANGAN BELI" untuk koin yang sama persis. Itu bikin bingung dan merusak kepercayaan.

Solusinya: **paket `core/`** — satu sumber kebenaran (single source of truth) yang dipakai bareng oleh web dan bot.

## Struktur modul `core/`

```
core/
├── __init__.py        # Deklarasi paket + alasan keberadaan core/
├── indicators.py      # Indikator teknikal + fetch candle + regime + ATR + ML + backtest
├── analysis.py        # Logika keputusan terpadu (scoring, action, risk, TP/SL, alokasi) + THRESHOLDS
├── calibration.py     # Pengukur kejujuran probabilitas (Brier, ECE, reliability)
└── applog.py          # Logging terstruktur terpusat (level + timezone WIB)
```

### Tanggung jawab tiap file

| File | Tanggung jawab |
| --- | --- |
| `indicators.py` | Semua **perhitungan teknikal mentah**: ambil candle dari Indodax, RSI/EMA/MACD/Bollinger/Supertrend/ADX, volume analysis, multi-timeframe, confluence suite (EMA200/pinbar/dynamic walls/static S&R), ML forecast (KNN + walk-forward shrinkage), backtest realistis (fee + slippage + out-of-sample), market regime BTC, ATR, dan committee `build_verdict`. |
| `analysis.py` | **Logika keputusan terpadu**: mengubah angka-angka indikator jadi keputusan. Berisi `compute_base_score`, `decide_action`, `compute_risk_level`, `compute_trade_levels`, `compute_allocation`, dan kamus `THRESHOLDS` (semua ambang batas keputusan di satu tempat). |
| `calibration.py` | **Pengukur kejujuran ramalan**: Brier score, ECE (Expected Calibration Error), reliability buckets, grade kalibrasi, dan ekstraksi pasangan (probabilitas, hasil) dari journal. Tidak memprediksi apa pun — hanya menilai apakah probabilitas yang sudah dibuat itu jujur. |
| `applog.py` | **Logging terstruktur**: logger terpusat dengan level (INFO/WARNING/ERROR), timestamp zona WIB, output ke stdout (yang ditangkap Hugging Face Spaces). Mengganti `print()` polos. |

## Prinsip inti: Single Source of Truth

Aturannya sederhana: **web (`app.py`) dan bot (`telegram_bot.py`) memanggil fungsi `core/` yang sama persis.** Karena keputusan akhir lahir dari fungsi yang identik, sinyal untuk koin yang sama **tidak akan pernah kontradiktif** antar permukaan.

Dulu, `analyze_coin_advanced` (web) dan `analyze_coin` (bot) punya threshold action dan gate yang berbeda. Sekarang keduanya:

1. Memanggil indikator dari `core.indicators`.
2. Menghitung skor dasar lewat `core.analysis.compute_base_score` (identik).
3. Mengambil keputusan lewat `core.analysis.decide_action` (identik, termasuk semua gate).

Satu-satunya perbedaan yang **diizinkan** adalah `extra_adjustment`: web menambahkan konteks ekstra (intelligence engine, smart engine, multi-horizon forecast, market mode, regime BTC) ke skor dasar, sementara bot mengirim 0. Sifatnya menambah konteks, **bukan mengubah aturan keputusan**. Threshold dan gate tetap identik.

### Alur analisis (dari candle ke keputusan)

```
fetch_candles(pair)                     # core.indicators — ambil OHLCV dari Indodax
        │
        ▼
indikator teknikal                      # core.indicators
  compute_rsi / compute_ema / compute_macd / compute_bollinger
  compute_supertrend / compute_volume_analysis / compute_adx
  compute_ml_forecast / compute_backtest
  compute_multi_timeframe_confirmation / compute_confluence_signal
  compute_market_regime(btc_candles) / compute_atr
        │
        ▼
compute_base_score(...)                 # core.analysis — skor 0..100 (sebelum extra)
        │
        ├─ (web) + extra_adjustment: intel/smart/forecast/mode/regime
        │
        ▼
compute_risk_level(...)                 # core.analysis — RENDAH/SEDANG/TINGGI
        │
        ▼
build_verdict(...)                      # core.indicators — committee approve/tunggu/tolak
        │
        ▼
decide_action(score, ...gate...)        # core.analysis — action final + emoji
  gate: threshold → confluence → anti-FOMO → MTF → regime → verdict
        │
        ▼
compute_trade_levels(...)  +  compute_allocation(...)   # core.analysis — TP/SL & % modal
```

Inti yang perlu diingat: **candle → indikator → compute_base_score → build_verdict → decide_action → compute_trade_levels / compute_allocation.** Web dan bot menjalankan rantai yang sama.

## Daftar fungsi publik penting

Deskripsi diambil dari docstring/perilaku nyata di kode.

### `core/indicators.py`

**Utility & fetch**

- `clamp(value, min_val, max_val)` — batasi nilai ke rentang [min, max].
- `is_entry_action(action)` — `True` kalau action adalah sinyal entry asli ("BELI KUAT" / "CICIL BELI"), bukan "JANGAN BELI".
- `fetch_candles(pair_id, tf="60", lookback_days=21)` — ambil candle historis dari Indodax untuk indikator teknikal.

**Indikator inti**

- `compute_rsi(close, period=14)` — RSI berbasis EMA, dikembalikan sebagai float terakhir 0..100.
- `compute_ema(close, span)` — exponential moving average.
- `compute_macd(close)` — label MACD (bullish cross/bullish/bearish cross/bearish/netral) + histogram.
- `compute_bollinger(close)` — sinyal Bollinger (oversold/overbought/netral) + %B.
- `compute_supertrend(candles)` — arah supertrend (bullish/bearish/netral).
- `compute_volume_analysis(candles)` — label volume (spike/kuat/normal/tipis) + rasio terhadap MA20.
- `compute_adx(candles)` — ADX: ukur kekuatan tren (bukan arah); kembalikan {adx, trend}.
- `compute_multi_timeframe_confirmation(candles)` — konfirmasi tren 4H + 1D, kembalikan label + penyesuaian skor.
- `compute_atr(candles, period=14)` — Average True Range (ukuran volatilitas) untuk TP/SL adaptif.
- `compute_ema200_trend(candles)` — sisi tren terhadap EMA200 (bullish/bearish).

**ML & backtest (bagian kejujuran model)**

- `compute_ml_forecast(candles)` — KNN prediksi probabilitas naik, **divalidasi walk-forward** lalu probabilitas mentah diciutkan (shrinkage) ke arah 50% sesuai skill yang terbukti out-of-sample. Kembalikan `ml_prob`, `ml_label`, `ml_conf`, plus `ml_wf_acc`, `ml_wf_n`, `ml_prob_raw`.
- `compute_backtest(candles, fee_pct_per_side=0.3, slippage_pct_per_side=0.1)` — uji pola sinyal di data historis, **sudah realistis**: tiap trade dikurangi fee + slippage pulang-pergi, dan dibagi kronologis 70%/30% untuk winrate out-of-sample (`bt_oos_wr`). `bt_wr` bermakna winrate **net**.

**Confluence suite (5 cek setup entry)**

- `compute_volume_anomaly(candles, threshold=1.2)` — apakah volume terakhir ≥ 1.2x MA20.
- `detect_bullish_pinbar(candles)` — deteksi pola pinbar bullish (rejection di bawah).
- `compute_dynamic_walls(candles, tolerance_pct=1.0)` — kedekatan harga ke MA99 / Bollinger band.
- `compute_static_sr(candles, tolerance_pct=1.2)` — kedekatan ke support/resistance statis 100 candle.
- `compute_confluence_signal(candles)` — gabungkan 5 cek jadi skor confluence (passed/total), label, strength, dan flag `allow_entry`.

**Keputusan tingkat committee & regime**

- `build_verdict(score, rsi, macd_signal, supertrend, adx_data, ml, bt, risk_level, vol_idr)` — komite bull/bear sederhana: APPROVE / APPROVE KECIL / TUNGGU / TOLAK + skor net + pengali size.
- `compute_market_regime(btc_candles)` — klasifikasi kondisi pasar global dari candle BTC (RISK_ON/NEUTRAL/RISK_OFF/NO DATA) + penyesuaian skor konservatif + flag `allow_aggressive`.

### `core/analysis.py`

- `THRESHOLDS` — kamus berisi semua ambang keputusan (score BELI KUAT/CICIL/WATCH/JANGAN, plus gate confluence, anti-FOMO, MTF). Satu definisi, dipakai web & bot.
- `compute_base_score(...)` — skor teknikal dasar 0..100 (sebelum extra). Identik web & bot. Kembalikan `(score_base_float, komponen)` agar pemanggil bisa menambah `extra_adjustment` dulu.
- `decide_action(score, change, confluence, range_pos, mtf_adjustment, regime_allow_aggressive=True, verdict=None)` — tentukan action + emoji dari skor & semua gate. Identik web & bot. Urutan gate: threshold dasar → confluence → anti-FOMO → MTF guard → regime guard → verdict committee.
- `compute_risk_level(change, vol_idr, rsi, macd_signal, supertrend, range_pos, ml, bt)` — risk level RENDAH/SEDANG/TINGGI. Identik web & bot.
- `compute_trade_levels(price, change, score, risk_level, atr=None)` — TP/SL terpadu (ATR-adaptif + fallback momentum). Kembalikan dict kanonik: `tp1`, `tp2`, `target` (=tp3), `stop_loss`, `trailing_pct`.
- `compute_allocation(score, risk_level, confluence, action, size_mult=1.0, market_mult=1.0)` — alokasi modal % terpadu (Kelly-ish gate). Hanya memberi alokasi untuk sinyal entry yang lolos confluence.

### `core/calibration.py`

- `brier_score(pairs)` — rata-rata `(prediksi - hasil)^2`. 0 = sempurna, 0.25 = setara nebak 50%, makin kecil makin baik. `None` bila kosong.
- `reliability_buckets(pairs, n_bins=10)` — bagi prediksi ke bin, bandingkan rata-rata prediksi vs frekuensi aktual naik per bin (dengan gap).
- `expected_calibration_error(pairs, n_bins=10)` — ECE: rata-rata `|prediksi - aktual|` tertimbang jumlah sampel per bin. 0 = terkalibrasi sempurna.
- `calibration_grade(brier, ece, sample_count)` — terjemahkan metrik jadi label manusiawi (TERKALIBRASI BAIK / CUKUP / BELUM TERKALIBRASI / DATA KURANG) + tingkat kepercayaan + catatan.
- `build_calibration_report(pairs, n_bins=10)` — laporan lengkap dari list `(predicted_prob, outcome)`.
- `extract_pairs_from_journal(journal, prob_keys=(...))` — ambil pasangan `(probabilitas, hasil)` dari sinyal tertutup di journal untuk dievaluasi.

### `core/applog.py`

- `get_logger(name="app")` — kembalikan logger child di bawah namespace `kripto`, dengan format konsisten + level + timestamp WIB. Level bisa diatur lewat env `LOG_LEVEL` (default INFO).

## Cara menjalankan test

Test ditulis dengan gaya assert polos + exit code (tanpa pytest), jadi cukup jalankan langsung dengan `python3`:

```bash
python3 test_indicators.py     # core/indicators.py
python3 test_analysis.py       # core/analysis.py
python3 test_calibration.py    # core/calibration.py + backtest realistis
python3 test_learning.py       # learning_engine + journal_store
```

Tiap file mencetak `PASS:` / `FAIL:` per cek dan ringkasan `=== X/Y tests passed ===`, lalu keluar dengan kode 0 kalau semua lolos (1 kalau ada yang gagal).

Jumlah test per file (hasil run terakhir, semua lolos):

| File | Jumlah test | Fokus |
| --- | --- | --- |
| `test_indicators.py` | **74** | Kontrak nilai (RSI/prob/score 0..100), penanganan data kosong, invariant confluence & verdict, regime BTC, shrinkage ML jujur |
| `test_analysis.py` | **36** | Scoring dasar, semua gate `decide_action`, risk level, TP/SL, alokasi, konsistensi web==bot |
| `test_calibration.py` | **36** | Brier/ECE/reliability, grade kalibrasi, ekstraksi journal, backtest realistis (fee + OOS) |
| `test_learning.py` | **30** | Pencatatan sinyal, dedupe, penutupan TP/SL, profil winrate, Kelly allocation |

Total: **176 test** di empat file.

## Catatan kejujuran model

Ini bagian penting yang membedakan Kripto Mania dari kebanyakan "bot ramalan". Tiga lapis kejujuran dibangun langsung ke dalam `core/`:

1. **Backtest sudah realistis** (`compute_backtest`). Tiap trade dikurangi fee + slippage pulang-pergi (default Indodax taker 0.3%/sisi + slippage 0.1%/sisi = 0.8% pulang-pergi), jadi `bt_wr` adalah winrate **bersih (net)**, bukan kotor. Trade juga dibagi kronologis 70%/30% — `bt_oos_wr` mengukur winrate di 30% data terakhir untuk mendeteksi pola yang sudah basi (regime decay).

2. **ML forecast pakai walk-forward shrinkage** (`compute_ml_forecast`). Probabilitas mentah KNN divalidasi out-of-sample (walk-forward, tanpa look-ahead), lalu diciutkan ke arah 50% (coin-flip) sesuai skill yang benar-benar terbukti. Kalau model tidak punya skill, "72% naik" tidak ditampilkan apa adanya — diciutkan supaya tidak menipu.

3. **Panel kalibrasi mengukur kejujuran probabilitas** (`core/calibration.py`). Saat model bilang "70% naik", apakah dari semua sinyal berlabel ~70% itu benar-benar ~70% yang naik? Brier score dan ECE menjawab itu secara kuantitatif, dibandingkan langsung dengan hasil aktual di journal.

**Tegas: ini BUKAN alat ramalan pasti.** Pasar crypto tidak bisa diprediksi dengan kepastian. Semua angka di sini adalah probabilitas yang sudah diukur kejujurannya — alat bantu pengambilan keputusan, bukan jaminan. Selalu DYOR (Do Your Own Research) dan pakai stop loss.

## Cara menambah indikator/agen baru

Karena `core/` adalah otak bersama, menambah kemampuan baru cukup di satu tempat dan web + bot otomatis ikut:

1. **Tambah fungsi indikator** di `core/indicators.py` (ikuti pola fungsi yang ada: terima `candles`, kembalikan default aman saat data kurang/kosong, jangan crash).
2. **Sambungkan ke keputusan** kalau perlu memengaruhi skor: tambahkan di `compute_base_score` (`core/analysis.py`) supaya pengaruhnya identik di web & bot. Kalau cuma konteks ekstra khusus web, masukkan lewat jalur `extra_adjustment` di `app.py`.
3. **Tulis test** di `test_indicators.py` atau `test_analysis.py` — minimal cek kontrak nilai dan perilaku saat DataFrame kosong/kurang.
4. **Jalankan test** (`python3 test_indicators.py` dst). Kalau hijau, web (`app.py`) dan bot (`telegram_bot.py`) langsung memakai logika baru tanpa perlu diubah dua kali.

Aturan emas: **jangan duplikasi logika keputusan di `app.py` atau `telegram_bot.py`.** Kalau ada logika yang dipakai dua permukaan, tempatnya di `core/`.
