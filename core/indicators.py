"""Indikator teknikal & analisis sinyal — sumber kebenaran tunggal.

Semua fungsi di sini sebelumnya diduplikasi persis (byte-for-byte) di app.py
dan telegram_bot.py. Sekarang didefinisikan sekali di sini supaya web dan bot
Telegram selalu memakai logika yang sama persis.

Catatan: fungsi tampilan/utility yang sengaja berbeda antar permukaan
(format_idr, clamp dengan urutan argumen berbeda) TIDAK dipindah ke sini —
masing-masing file menyimpan versinya sendiri.
"""

import time

import numpy as np
import pandas as pd
import requests


def clamp(value, min_val, max_val):
    return max(min_val, min(value, max_val))


def is_entry_action(action):
    """Check if action is a genuine entry signal (not 'JANGAN BELI')."""
    action = str(action or "").upper()
    return "BELI KUAT" in action or "CICIL BELI" in action


# =============================================================================
# CANDLE FETCHING
# =============================================================================
# Cache candle ber-TTL pendek. Dalam satu siklus scan, candle koin yang sama
# sering di-fetch berkali-kali (mis. early-entry ambil 1H, lalu confluence
# ambil 1H lagi untuk koin yang sama). Tanpa cache = ratusan request HTTP
# redundan + sleep di mode agresif (80 koin). TTL pendek aman karena candle
# cuma berubah sekali tiap timeframe.
_CANDLE_CACHE: dict = {}
_CANDLE_CACHE_TTL = float(__import__("os").environ.get("CANDLE_CACHE_TTL", "45"))


def fetch_candles(pair_id, tf="60", lookback_days=21, use_cache=True):
    """Ambil candle historis dari Indodax untuk indikator teknikal.

    Hasil di-cache per (symbol, tf, lookback_days) selama _CANDLE_CACHE_TTL detik
    supaya tidak fetch berulang untuk koin yang sama dalam satu siklus.
    """
    symbol = pair_id.replace("_", "").upper()
    cache_key = (symbol, tf, lookback_days)
    now = time.time()

    if use_cache:
        cached = _CANDLE_CACHE.get(cache_key)
        if cached is not None and (now - cached[0]) < _CANDLE_CACHE_TTL:
            # Return salinan supaya caller tidak mengubah data cache bersama.
            return cached[1].copy()

    end_ts = int(now)
    start_ts = end_ts - lookback_days * 86400
    url = "https://indodax.com/tradingview/history_v2"
    try:
        resp = requests.get(
            url,
            params={"from": start_ts, "to": end_ts, "tf": tf, "symbol": symbol},
            timeout=8,
        )
        rows = resp.json()
    except Exception:
        return pd.DataFrame()
    if not isinstance(rows, list) or not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    rename = {
        "Time": "time",
        "Open": "open",
        "High": "high",
        "Low": "low",
        "Close": "close",
        "Volume": "volume",
    }
    df = df.rename(columns=rename)
    required = ["time", "open", "high", "low", "close", "volume"]
    if not all(c in df.columns for c in required):
        return pd.DataFrame()
    for c in required:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=["close"]).sort_values("time")
    result = df.tail(500).reset_index(drop=True)

    if use_cache and not result.empty:
        _CANDLE_CACHE[cache_key] = (now, result)
        # Cegah cache membengkak tanpa batas (mis. saat scan ratusan koin).
        if len(_CANDLE_CACHE) > 400:
            cutoff = now - _CANDLE_CACHE_TTL
            for k in [k for k, v in _CANDLE_CACHE.items() if v[0] < cutoff]:
                _CANDLE_CACHE.pop(k, None)

    return result.copy() if use_cache else result


# =============================================================================
# CORE INDICATORS
# =============================================================================
def compute_rsi(close, period=14):
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / period, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / period, adjust=False).mean()
    # float("nan") (bukan pd.NA) agar series tetap dtype float: hasil numerik
    # identik tapi tidak memicu FutureWarning downcasting saat .fillna.
    rs = gain / loss.replace(0, float("nan"))
    return float((100 - (100 / (1 + rs))).fillna(50).iloc[-1])


def compute_ema(close, span):
    return close.ewm(span=span, adjust=False).mean()


def _candles_with_datetime_index(candles):
    if candles.empty or "time" not in candles.columns:
        return pd.DataFrame()
    df = candles.copy()
    t = pd.to_numeric(df["time"], errors="coerce")
    if t.dropna().empty:
        return pd.DataFrame()
    unit = "ms" if float(t.dropna().median()) > 1_000_000_000_000 else "s"
    df["_dt"] = pd.to_datetime(t, unit=unit, errors="coerce", utc=True)
    return df.dropna(subset=["_dt"]).set_index("_dt").sort_index()


def _resample_candles(candles, rule):
    df = _candles_with_datetime_index(candles)
    if df.empty:
        return pd.DataFrame()
    agg = {
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
        "volume": "sum",
    }
    return df.resample(rule).agg(agg).dropna(subset=["close"]).reset_index(drop=True)


def _timeframe_bias(candles):
    if candles.empty or len(candles) < 12:
        return "NO DATA", 0
    close = candles["close"].astype(float)
    ema_fast = compute_ema(close, 5).iloc[-1]
    ema_slow = compute_ema(close, 13).iloc[-1]
    lookback = min(6, len(close) - 1)
    momentum = (
        (close.iloc[-1] / close.iloc[-1 - lookback] - 1) * 100
        if lookback > 0 and close.iloc[-1 - lookback] > 0
        else 0
    )
    gap = (ema_fast - ema_slow) / ema_slow * 100 if ema_slow > 0 else 0
    if gap > 0.15 and momentum > 0:
        return "BULLISH", 2
    if gap > 0 and momentum > -0.6:
        return "BULLISH BIAS", 1
    if gap < -0.15 and momentum < 0:
        return "BEARISH", -2
    if gap < 0 and momentum < 0.6:
        return "BEARISH BIAS", -1
    return "SIDEWAYS", 0


def compute_multi_timeframe_confirmation(candles):
    h4 = _resample_candles(candles, "4h")
    d1 = _resample_candles(candles, "1D")
    h4_label, h4_score = _timeframe_bias(h4)
    d1_label, d1_score = _timeframe_bias(d1)
    total = h4_score + d1_score
    if total >= 3:
        label, adjustment = "ALIGN BULLISH", 7
    elif total == 2:
        label, adjustment = "BULLISH BIAS", 4
    elif total <= -3:
        label, adjustment = "ALIGN BEARISH", -8
    elif total == -2:
        label, adjustment = "BEARISH BIAS", -5
    else:
        label, adjustment = "MIXED", 0
    return {
        "mtf_label": label,
        "mtf_4h": h4_label,
        "mtf_1d": d1_label,
        "mtf_score": total,
        "mtf_adjustment": adjustment,
    }


def compute_macd(close):
    if len(close) < 15:
        return "netral", 0
    macd_line = compute_ema(close, 12) - compute_ema(close, 26)
    signal_line = macd_line.ewm(span=9, adjust=False).mean()
    hist = float(macd_line.iloc[-1] - signal_line.iloc[-1])
    prev = float(macd_line.iloc[-2] - signal_line.iloc[-2]) if len(macd_line) > 1 else 0
    if hist > 0 and prev <= 0:
        return "bullish cross", hist
    elif hist > 0:
        return "bullish", hist
    elif hist < 0 and prev >= 0:
        return "bearish cross", hist
    elif hist < 0:
        return "bearish", hist
    return "netral", hist


def compute_bollinger(close):
    if len(close) < 20:
        return {"bb_signal": "netral", "bb_pct_b": 0.5}
    mid = float(close.tail(20).mean())
    std = float(close.tail(20).std())
    upper = mid + 2 * std
    lower = mid - 2 * std
    last = float(close.iloc[-1])
    pct_b = (last - lower) / (upper - lower) if upper > lower else 0.5
    if pct_b < 0.15:
        sig = "oversold"
    elif pct_b > 0.85:
        sig = "overbought"
    else:
        sig = "netral"
    return {"bb_signal": sig, "bb_pct_b": round(pct_b, 2)}


def compute_supertrend(candles):
    if candles.empty or len(candles) < 30:
        return "netral"
    high = candles["high"].astype(float)
    low = candles["low"].astype(float)
    close = candles["close"].astype(float)
    tr = pd.concat(
        [high - low, (high - close.shift(1)).abs(), (low - close.shift(1)).abs()],
        axis=1,
    ).max(axis=1)
    atr = tr.rolling(14).mean()
    ema_fast = close.ewm(span=10, adjust=False).mean()
    ema_slow = close.ewm(span=30, adjust=False).mean()
    floor = ((high + low) / 2) - (2.4 * atr)
    if (
        pd.notna(floor.iloc[-1])
        and close.iloc[-1] > floor.iloc[-1]
        and ema_fast.iloc[-1] > ema_slow.iloc[-1]
    ):
        return "bullish"
    elif pd.notna(floor.iloc[-1]):
        return "bearish"
    return "netral"


def compute_volume_analysis(candles):
    if candles.empty or len(candles) < 20:
        return "normal", 1.0
    vol = candles["volume"].astype(float)
    avg = vol.tail(20).mean()
    if avg <= 0:
        return "normal", 1.0
    ratio = float(vol.iloc[-1] / avg)
    if ratio >= 1.8:
        return "spike", ratio
    elif ratio >= 1.15:
        return "kuat", ratio
    elif ratio >= 0.7:
        return "normal", ratio
    return "tipis", ratio


def compute_adx(candles):
    """ADX: ukur kekuatan tren (bukan arah)."""
    if candles.empty or len(candles) < 28:
        return {"adx": 25, "trend": "sideways"}
    hi = candles["high"].astype(float)
    lo = candles["low"].astype(float)
    cl = candles["close"].astype(float)
    tr = pd.concat(
        [hi - lo, (hi - cl.shift(1)).abs(), (lo - cl.shift(1)).abs()], axis=1
    ).max(axis=1)
    up = hi - hi.shift(1)
    dn = lo.shift(1) - lo
    pdm = up.where((up > dn) & (up > 0), 0.0)
    ndm = dn.where((dn > up) & (dn > 0), 0.0)
    atr = tr.ewm(alpha=1 / 14, adjust=False).mean()
    pdi = (
        100 * pdm.ewm(alpha=1 / 14, adjust=False).mean() / atr.replace(0, float("nan"))
    )
    ndi = (
        100 * ndm.ewm(alpha=1 / 14, adjust=False).mean() / atr.replace(0, float("nan"))
    )
    dx = 100 * abs(pdi - ndi) / (pdi + ndi).replace(0, float("nan"))
    adx = float(dx.fillna(25).ewm(alpha=1 / 14, adjust=False).mean().iloc[-1])
    pdi_v = float(pdi.fillna(0).iloc[-1])
    ndi_v = float(ndi.fillna(0).iloc[-1])
    if adx >= 25:
        trend = (
            "bullish_strong"
            if pdi_v > ndi_v and adx >= 40
            else "bullish"
            if pdi_v > ndi_v
            else "bearish_strong"
            if adx >= 40
            else "bearish"
        )
    else:
        trend = "sideways"
    return {"adx": round(adx, 1), "trend": trend}


def _knn_predict(train_X, train_future, query_x, k):
    """Prediksi probabilitas naik (>1%) via KNN tertimbang jarak. Vektorized.

    train_X: ndarray (n, f) terstandardisasi; train_future: ndarray (n,) % depan;
    query_x: ndarray (f,) terstandardisasi. Mengembalikan prob 0..100.
    """
    if len(train_X) < k or k <= 0:
        return 50.0
    dist = np.sqrt(((train_X - query_x) ** 2).sum(axis=1))
    idx = np.argpartition(dist, k - 1)[:k]
    w = 1.0 / (dist[idx] + 0.001)
    up = (train_future[idx] > 1.0).astype(float)
    denom = w.sum()
    if denom <= 0:
        return 50.0
    return float((up * w).sum() / denom * 100)


def _walk_forward_skill(train_X, train_future, k, horizon=6, n_test=40):
    """Ukur skill KNN secara out-of-sample (walk-forward, tanpa look-ahead).

    Untuk tiap baris validasi terbaru, prediksi HANYA memakai baris yang
    outcome-nya sudah diketahui sebelum titik prediksi (q + horizon <= p).
    Mengembalikan (directional_accuracy_pct, n) atau (None, 0) bila data kurang.
    """
    n = len(train_X)
    if n < 60:
        return None, 0
    n_test = int(min(n_test, max(0, (n - 30) // 2)))
    if n_test < 15:
        return None, 0
    start = n - n_test
    hits = 0
    total = 0
    for p in range(start, n):
        usable = p - horizon  # outcome baris q diketahui di q+horizon <= p
        if usable < 30:
            continue
        kk = int(min(k, max(8, round(usable**0.5))))
        prob = _knn_predict(train_X[:usable], train_future[:usable], train_X[p], kk)
        actual_up = train_future[p] > 1.0
        pred_up = prob >= 50.0
        if pred_up == bool(actual_up):
            hits += 1
        total += 1
    if total < 15:
        return None, 0
    return round(hits / total * 100, 1), total


def compute_ml_forecast(candles):
    """KNN: prediksi probabilitas naik, DIVALIDASI walk-forward (jujur).

    Perbaikan kejujuran: probabilitas mentah KNN dikecilkan ke arah 50%
    (coin-flip) sesuai SKILL yang terbukti out-of-sample. Kalau model tidak
    punya skill (akurasi walk-forward ~50%), "72% naik" tidak lagi ditampilkan
    apa adanya — diciutkan supaya tidak menipu. Confidence juga menuntut bukti
    skill, bukan sekadar banyak data.

    Key lama (ml_prob/ml_label/ml_conf) tetap ada; tambah ml_wf_acc (akurasi
    walk-forward %), ml_wf_n (jumlah uji), ml_prob_raw (sebelum shrinkage).
    """
    default = {
        "ml_prob": 50.0,
        "ml_label": "NO DATA",
        "ml_conf": "rendah",
        "ml_wf_acc": None,
        "ml_wf_n": 0,
        "ml_prob_raw": 50.0,
    }
    if candles.empty or len(candles) < 80:
        return default
    close = candles["close"].astype(float)
    high = candles["high"].astype(float)
    low = candles["low"].astype(float)
    volume = candles["volume"].astype(float)
    ret1 = close.pct_change(1) * 100
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    rsi = 100 - (100 / (1 + gain / loss.replace(0, float("nan"))))
    feat = pd.DataFrame(
        {
            "ret1": ret1,
            "ret3": close.pct_change(3) * 100,
            "ret6": close.pct_change(6) * 100,
            "vol12": ret1.rolling(12).std(),
            "ema_gap": (
                close.ewm(span=8, adjust=False).mean()
                - close.ewm(span=21, adjust=False).mean()
            )
            / close
            * 100,
            "rsi": rsi,
            "rng": (close - low.rolling(24).min())
            / (high.rolling(24).max() - low.rolling(24).min()).replace(0, float("nan"))
            * 100,
            "vr": volume / volume.rolling(24).mean().replace(0, float("nan")),
        }
    )
    feat["future"] = close.shift(-6) / close * 100 - 100
    feat = feat.replace([float("inf"), float("-inf")], float("nan"))
    cols = ["ret1", "ret3", "ret6", "vol12", "ema_gap", "rsi", "rng", "vr"]
    current = feat[cols].dropna().tail(1).astype(float)
    train = feat.dropna(subset=cols + ["future"]).copy()
    if current.empty or len(train) < 50:
        return default
    means = train[cols].mean()
    stds = train[cols].std().replace(0, 1).fillna(1)
    train_X = ((train[cols] - means) / stds).astype(float).to_numpy()
    train_future = train["future"].astype(float).to_numpy()
    query_x = ((current.iloc[0] - means) / stds).astype(float).to_numpy()
    k = int(clamp(round(len(train) ** 0.5), 12, 35))

    prob_raw = _knn_predict(train_X, train_future, query_x, k)

    # Validasi walk-forward: seberapa akurat KNN ini out-of-sample?
    wf_acc, wf_n = _walk_forward_skill(train_X, train_future, k)

    # Shrinkage ke 50% sesuai skill terbukti. Tanpa skill -> probabilitas jujur
    # mendekati coin-flip. Dengan skill kuat -> dipertahankan apa adanya.
    if wf_acc is None:
        skill_factor = 0.5  # skill belum teruji: setengah jalan
    elif wf_acc >= 58:
        skill_factor = 1.0
    elif wf_acc >= 53:
        skill_factor = 0.75
    elif wf_acc >= 48:
        skill_factor = 0.45
    else:
        skill_factor = 0.25  # lebih buruk dari coin-flip
    prob = 50.0 + (prob_raw - 50.0) * skill_factor

    label = "BULLISH" if prob >= 62 else "BEARISH" if prob <= 42 else "NETRAL"
    edge = abs(prob - 50)
    # Confidence menuntut BUKTI skill walk-forward, bukan cuma ukuran data.
    if wf_acc is not None and wf_acc >= 58 and wf_n >= 20 and edge >= 10:
        conf = "tinggi"
    elif wf_acc is not None and wf_acc >= 53 and wf_n >= 15 and edge >= 6:
        conf = "sedang"
    else:
        conf = "rendah"
    return {
        "ml_prob": round(prob, 1),
        "ml_label": label,
        "ml_conf": conf,
        "ml_wf_acc": wf_acc,
        "ml_wf_n": wf_n,
        "ml_prob_raw": round(prob_raw, 1),
    }


def compute_backtest(candles, fee_pct_per_side=0.3, slippage_pct_per_side=0.1):
    """Uji pola sinyal di data historis — SUDAH realistis (biaya + out-of-sample).

    Perbaikan dari versi lama yang membuat winrate terlihat lebih bagus dari
    kenyataan:
      1. BIAYA NYATA: tiap trade dikurangi fee + slippage pulang-pergi
         (default Indodax taker 0.3%/sisi + slippage 0.1%/sisi = 0.8% PP).
         `bt_wr` sekarang adalah winrate BERSIH (net), bukan kotor.
      2. OUT-OF-SAMPLE: trade dibagi kronologis 70% awal / 30% akhir.
         `bt_oos_wr` = winrate net di 30% terakhir (deteksi pola yang sudah
         basi / regime decay). Kalau oos jauh < is, pola mulai tidak relevan.

    Key lama (`bt_wr`, `bt_trades`, `bt_label`) tetap ada agar build_verdict &
    UI tidak rusak; `bt_wr` kini bermakna NET (lebih jujur, lebih konservatif).
    """
    round_trip_cost = 2.0 * (fee_pct_per_side + slippage_pct_per_side)
    default = {
        "bt_wr": 0,
        "bt_trades": 0,
        "bt_label": "DATA KURANG",
        "bt_wr_gross": 0,
        "bt_oos_wr": 0,
        "bt_avg_net_pct": 0.0,
        "bt_cost_pct": round(round_trip_cost, 2),
    }
    if candles.empty or len(candles) < 90:
        return default
    close = candles["close"].astype(float)
    high = candles["high"].astype(float)
    low = candles["low"].astype(float)
    volume = candles["volume"].astype(float)
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    rsi = 100 - (100 / (1 + gain / loss.replace(0, float("nan"))))
    ema8 = close.ewm(span=8, adjust=False).mean()
    ema21 = close.ewm(span=21, adjust=False).mean()
    vr = volume / volume.rolling(24).mean().replace(0, float("nan"))
    sig = ((ema8 > ema21) & rsi.between(42, 72) & (vr >= 0.75)).fillna(False)
    gross_outcomes = []
    last_i = -6
    for i in range(35, len(candles) - 7):
        if not bool(sig.iloc[i]) or i - last_i < 6:
            continue
        entry = float(close.iloc[i])
        if entry <= 0:
            continue
        tgt = entry * 1.026
        stp = entry * 0.978
        out = None
        for j in range(i + 1, i + 7):
            if float(low.iloc[j]) <= stp:
                out = -2.2
                break
            if float(high.iloc[j]) >= tgt:
                out = 2.6
                break
        if out is None:
            out = float((close.iloc[i + 6] - entry) / entry * 100)
        gross_outcomes.append(out)
        last_i = i
    if len(gross_outcomes) < 6:
        return default
    # Biaya pulang-pergi dikurangkan dari tiap trade → return bersih
    net_outcomes = [g - round_trip_cost for g in gross_outcomes]
    wins_net = [x for x in net_outcomes if x > 0]
    wins_gross = [x for x in gross_outcomes if x > 0]
    wr = len(wins_net) / len(net_outcomes) * 100
    wr_gross = len(wins_gross) / len(gross_outcomes) * 100
    avg_net = sum(net_outcomes) / len(net_outcomes)
    # Out-of-sample: 30% trade terakhir (kronologis)
    split = int(len(net_outcomes) * 0.7)
    oos = net_outcomes[split:]
    oos_wr = (len([x for x in oos if x > 0]) / len(oos) * 100) if oos else 0.0
    label = (
        "TERUJI"
        if wr >= 58 and len(net_outcomes) >= 14
        else "CUKUP"
        if wr >= 50
        else "LEMAH"
    )
    return {
        "bt_wr": round(wr, 1),
        "bt_trades": len(net_outcomes),
        "bt_label": label,
        "bt_wr_gross": round(wr_gross, 1),
        "bt_oos_wr": round(oos_wr, 1),
        "bt_avg_net_pct": round(avg_net, 2),
        "bt_cost_pct": round(round_trip_cost, 2),
    }


def build_verdict(
    score, rsi, macd_signal, supertrend, adx_data, ml, bt, risk_level, vol_idr
):
    """Komite bull/bear sederhana: approve, approve kecil, tunggu, atau tolak."""
    bull = bear = 0
    if score >= 75:
        bull += 18
    elif score >= 65:
        bull += 10
    else:
        bear += 8
    if ml["ml_prob"] >= 62:
        bull += 12
    elif ml["ml_prob"] <= 42:
        bear += 12
    if bt["bt_trades"] >= 10 and bt["bt_wr"] >= 58:
        bull += 14
    elif bt["bt_trades"] >= 10 and bt["bt_label"] == "LEMAH":
        bear += 16
    # Out-of-sample decay: kalau winrate di 30% data terakhir jeblok jauh di
    # bawah keseluruhan, pola mulai basi (regime berubah) -> hukum.
    # Pakai .get agar kompatibel dgn pemanggil/bt lama tanpa key ini.
    bt_oos = bt.get("bt_oos_wr")
    if bt["bt_trades"] >= 12 and bt_oos is not None:
        oos_gap = bt["bt_wr"] - bt_oos
        if oos_gap >= 25:
            bear += 10  # pola jelas memburuk di periode terbaru
        elif oos_gap >= 15:
            bear += 5
        elif bt_oos >= 60 and bt["bt_wr"] >= 55:
            bull += 4  # tetap kuat termasuk out-of-sample
    if adx_data["trend"] in ("bullish_strong", "bullish"):
        bull += 7
    elif adx_data["trend"] in ("bearish_strong", "bearish"):
        bear += 9
    if supertrend == "bullish":
        bull += 7
    elif supertrend == "bearish":
        bear += 9
    if rsi >= 78:
        bear += 8
    if vol_idr < 100_000_000:
        bear += 12
    elif vol_idr >= 5_000_000_000:
        bull += 5
    net = int(clamp(50 + bull - bear, 0, 100))
    if risk_level == "TINGGI" or bear >= bull + 18:
        return "TOLAK", net, 0
    elif bear >= bull + 5 or net < 48:
        return "TUNGGU", net, 0
    elif risk_level == "SEDANG":
        return "APPROVE KECIL", net, 0.55
    return "APPROVE", net, 1.0


# =============================================================================
# CONFLUENCE SUITE
# =============================================================================
def compute_atr(candles, period=14):
    if candles.empty or len(candles) < period + 1:
        return None
    high = candles["high"].astype(float)
    low = candles["low"].astype(float)
    close = candles["close"].astype(float)
    tr = pd.concat(
        [high - low, (high - close.shift(1)).abs(), (low - close.shift(1)).abs()],
        axis=1,
    ).max(axis=1)
    return float(tr.rolling(period).mean().iloc[-1])


def compute_ema200_trend(candles):
    if candles.empty or len(candles) < 220:
        return {"ema200_ok": False, "ema200": None, "trend_side": "NO DATA"}
    close = candles["close"].astype(float)
    ema200 = close.ewm(span=200, adjust=False).mean()
    last_price = float(close.iloc[-1])
    last_ema200 = float(ema200.iloc[-1])
    if last_price > last_ema200:
        side = "BULLISH"
        ok = True
    else:
        side = "BEARISH"
        ok = False
    return {"ema200_ok": ok, "ema200": last_ema200, "trend_side": side}


def compute_volume_anomaly(candles, threshold=1.2):
    if candles.empty or len(candles) < 22:
        return {"volume_ok": False, "volume_ratio": 1.0}

    closed = candles.iloc[:-1]
    volume = closed["volume"].astype(float)

    avg20 = volume.tail(21).iloc[:-1].mean()
    last_vol = float(volume.iloc[-1])

    if avg20 <= 0:
        return {"volume_ok": False, "volume_ratio": 1.0}

    ratio = last_vol / avg20

    return {"volume_ok": ratio >= threshold, "volume_ratio": round(ratio, 2)}


def detect_bullish_pinbar(candles):
    if candles.empty or len(candles) < 3:
        return {"pinbar_ok": False, "pinbar_type": "NO DATA"}

    closed = candles.iloc[:-1]
    c = closed.iloc[-1]

    open_ = float(c["open"])
    high = float(c["high"])
    low = float(c["low"])
    close = float(c["close"])

    candle_range = high - low
    body = abs(close - open_)
    upper_shadow = high - max(open_, close)
    lower_shadow = min(open_, close) - low

    if candle_range <= 0:
        return {"pinbar_ok": False, "pinbar_type": "INVALID"}

    body_pct = body / candle_range
    lower_pct = lower_shadow / candle_range
    upper_pct = upper_shadow / candle_range

    bullish_pinbar = (
        lower_pct >= 0.45 and body_pct <= 0.35 and close > open_ and upper_pct <= 0.35
    )

    return {
        "pinbar_ok": bullish_pinbar,
        "pinbar_type": "BULLISH_PINBAR" if bullish_pinbar else "NO_REJECTION",
    }


def compute_dynamic_walls(candles, tolerance_pct=1.0):
    if candles.empty or len(candles) < 100:
        return {"dynamic_wall_ok": False, "wall_type": "NO DATA"}
    close = candles["close"].astype(float)
    last_price = float(close.iloc[-1])
    ma99 = float(close.rolling(99).mean().iloc[-1])
    mid = float(close.tail(20).mean())
    std = float(close.tail(20).std())
    upper_bb = mid + 2 * std
    lower_bb = mid - 2 * std

    def near(a, b):
        if b <= 0:
            return False
        return abs(a - b) / b * 100 <= tolerance_pct

    near_ma99 = near(last_price, ma99)
    near_lower_bb = near(last_price, lower_bb)
    near_upper_bb = near(last_price, upper_bb)
    ok = near_ma99 or near_lower_bb
    if near_lower_bb:
        wall_type = "LOWER_BB"
    elif near_ma99:
        wall_type = "MA99"
    elif near_upper_bb:
        wall_type = "UPPER_BB"
    else:
        wall_type = "NONE"
    return {
        "dynamic_wall_ok": ok,
        "wall_type": wall_type,
        "ma99": ma99,
        "lower_bb": lower_bb,
        "upper_bb": upper_bb,
    }


def compute_static_sr(candles, tolerance_pct=1.2):
    if candles.empty or len(candles) < 100:
        return {
            "sr_ok": False,
            "sr_type": "NO DATA",
            "support": None,
            "resistance": None,
        }

    closed = candles.iloc[:-1] if len(candles) > 101 else candles
    recent = closed.tail(100)

    last_price = float(recent["close"].iloc[-1])
    support = float(recent["low"].min())
    resistance = float(recent["high"].max())

    near_support = (
        abs(last_price - support) / support * 100 <= tolerance_pct
        if support > 0
        else False
    )
    near_resistance = (
        abs(last_price - resistance) / resistance * 100 <= tolerance_pct
        if resistance > 0
        else False
    )

    return {
        "sr_ok": near_support,
        "sr_type": "SUPPORT"
        if near_support
        else "RESISTANCE"
        if near_resistance
        else "NONE",
        "support": support,
        "resistance": resistance,
    }


def compute_confluence_signal(candles):
    ema200 = compute_ema200_trend(candles)
    volume = compute_volume_anomaly(candles, threshold=1.2)
    pinbar = detect_bullish_pinbar(candles)
    dynamic = compute_dynamic_walls(candles, tolerance_pct=1.0)
    sr = compute_static_sr(candles, tolerance_pct=1.2)
    checks = {
        "Trend EMA200": ema200["ema200_ok"],
        "Volume 1.2x MA20": volume["volume_ok"],
        "Bullish Pinbar": pinbar["pinbar_ok"],
        "Dynamic Wall": dynamic["dynamic_wall_ok"],
        "Static Support": sr["sr_ok"],
    }
    passed = sum(1 for v in checks.values() if v)
    total = len(checks)
    if passed == 5:
        label = "VALID 5/5"
        strength = "SANGAT KUAT"
        allow_entry = True
    elif passed == 4:
        label = "VALID 4/5"
        strength = "KUAT"
        allow_entry = True
    elif passed == 3:
        label = "VALID 3/5"
        strength = "PANTAU"
        allow_entry = False
    else:
        label = f"INVALID {passed}/5"
        strength = "TOLAK"
        allow_entry = False
    return {
        "confluence_passed": passed,
        "confluence_total": total,
        "confluence_label": label,
        "confluence_strength": strength,
        "allow_entry": allow_entry,
        "checks": checks,
        "ema200": ema200,
        "volume": volume,
        "pinbar": pinbar,
        "dynamic": dynamic,
        "sr": sr,
    }


# =============================================================================
# MARKET REGIME FILTER (kondisi BTC)
# =============================================================================
def compute_market_regime(btc_candles):
    """Klasifikasi kondisi pasar global dari candle BTC.

    Di crypto, kalau BTC ambruk hampir semua altcoin ikut turun — jadi menilai
    altcoin tanpa melihat BTC itu buta sebelah. Fungsi ini mengembalikan label
    regime + penyesuaian skor yang bisa ditambahkan ke koin lain:

      RISK_ON   : BTC sehat (di atas EMA50, momentum positif) -> boleh agresif
      NEUTRAL   : BTC sideways -> netral
      RISK_OFF  : BTC lemah (di bawah EMA50, momentum negatif) -> tahan diri
      NO DATA   : candle kurang -> netral, tidak menghukum

    `regime_adjustment` sengaja konservatif (range -8..+4): meredam, bukan
    mendikte. `allow_aggressive` dipakai untuk gate sinyal "BELI KUAT".
    """
    default = {
        "regime": "NO DATA",
        "regime_adjustment": 0,
        "allow_aggressive": True,
        "btc_momentum_pct": 0.0,
        "note": "Data BTC belum cukup; regime dianggap netral.",
    }
    if btc_candles is None or btc_candles.empty or len(btc_candles) < 55:
        return default

    close = btc_candles["close"].astype(float)
    ema50 = close.ewm(span=50, adjust=False).mean()
    price = float(close.iloc[-1])
    ema_now = float(ema50.iloc[-1])
    above_ema = price > ema_now

    lookback = min(24, len(close) - 1)
    ref = float(close.iloc[-1 - lookback])
    momentum = ((price - ref) / ref * 100) if ref > 0 else 0.0

    adx = compute_adx(btc_candles)
    trend = adx.get("trend", "sideways")

    if above_ema and momentum > 1.0 and trend not in ("bearish", "bearish_strong"):
        regime = "RISK_ON"
        adjustment = 4
        allow_aggressive = True
        note = f"BTC sehat (+{momentum:.1f}% & di atas EMA50). Boleh cari entry."
    elif (not above_ema) and momentum < -1.0:
        regime = "RISK_OFF"
        # Lebih dalam penurunannya, lebih besar peredamannya
        adjustment = -8 if (momentum < -4.0 or trend == "bearish_strong") else -5
        allow_aggressive = False
        note = f"BTC lemah ({momentum:.1f}% & di bawah EMA50). Tahan diri, entry kecil."
    else:
        regime = "NEUTRAL"
        adjustment = 0
        allow_aggressive = True
        note = "BTC sideways. Nilai tiap koin apa adanya."

    return {
        "regime": regime,
        "regime_adjustment": adjustment,
        "allow_aggressive": allow_aggressive,
        "btc_momentum_pct": round(momentum, 2),
        "note": note,
    }
