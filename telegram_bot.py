#!/usr/bin/env python3
"""
DAEMON 24/7 — Auto sinyal ULTRA SMART ke Telegram.
Fitur: RSI, EMA, MACD, Bollinger, Supertrend, ADX, ML/KNN, Backtest, Agentic Verdict.
- Sinyal harian: tiap jam 8 pagi WIB
- FOMO check: tiap 2 menit
- TP/SL monitor: tiap siklus
- Daily summary: jam 21:00 WIB
"""

import os
import time
import requests
import pandas as pd
import json
from datetime import datetime, timezone, timedelta
from keep_alive import keep_alive
from learning_engine import apply_learning_adjustments, record_signal, train_from_prices
from news_engine import apply_news_adjustments, build_news_profile
from ai_pilot import generate_signal_insight

# === CONFIG ===
def _get_api_key(key_name):
    val = os.environ.get(key_name)
    if val: return val
    try:
        with open(".streamlit/secrets.toml", "r") as f:
            for line in f:
                if line.startswith(key_name):
                    return line.split("=")[1].strip().strip('"').strip("'")
    except:
        pass
    return ""

GEMINI_API_KEY = _get_api_key("GEMINI_API_KEY")
DEEPSEEK_API_KEY = _get_api_key("DEEPSEEK_API_KEY")

BOT_TOKEN = _get_api_key("TELEGRAM_BOT_TOKEN")
CHAT_ID = _get_api_key("TELEGRAM_CHAT_ID")
INDODAX_REF = "narwanpratanta"
WIB = timezone(timedelta(hours=7))

MAIN_ASSETS = {
    "BTC": "btc_idr", "ETH": "eth_idr", "SOL": "sol_idr",
    "XRP": "xrp_idr", "BNB": "bnb_idr", "ADA": "ada_idr",
    "DOGE": "doge_idr",
}

BLUE_CHIPS = {"BTC", "ETH", "BNB", "SOL", "XRP", "ADA"}
MICIN_COINS = {"DOGE", "PEPE", "SHIB", "BONK", "FLOKI", "LUNC", "BTT"}

TELEGRAM_CHANNEL = "https://t.me/+VPlOcY2wFGA0NWU1"

def env_bool(name, default=False):
    return str(os.environ.get(name, str(default))).lower() in {"1","true","yes","on"}

ENABLE_FOMO_ALERTS = env_bool("ENABLE_FOMO_ALERTS", True)
ENABLE_CONFLUENCE_ALERTS = env_bool("ENABLE_CONFLUENCE_ALERTS", True)
ENABLE_EARLY_ALERTS = env_bool("ENABLE_EARLY_ALERTS", True)

# === ANTI-SPAM CONTROL ===
# Default 60s biar scan 3x lebih cepet daripada 180s lama.
LOOP_SLEEP_SECONDS = int(os.environ.get("LOOP_SLEEP_SECONDS", "60"))

FOMO_GLOBAL_COOLDOWN_SEC = int(os.environ.get("FOMO_GLOBAL_COOLDOWN_SEC", "1800"))
FOMO_SYMBOL_COOLDOWN_SEC = int(os.environ.get("FOMO_SYMBOL_COOLDOWN_SEC", str(24 * 3600)))

CONFLUENCE_SYMBOL_COOLDOWN_SEC = int(os.environ.get("CONFLUENCE_SYMBOL_COOLDOWN_SEC", str(24 * 3600)))
CONFLUENCE_MAX_ALERTS_PER_CYCLE = int(os.environ.get("CONFLUENCE_MAX_ALERTS_PER_CYCLE", "1"))

# Early-entry punya cooldown sendiri supaya nggak nabrak alert konfirmasi.
EARLY_SYMBOL_COOLDOWN_SEC = int(os.environ.get("EARLY_SYMBOL_COOLDOWN_SEC", str(4 * 3600)))
EARLY_MAX_ALERTS_PER_CYCLE = int(os.environ.get("EARLY_MAX_ALERTS_PER_CYCLE", "2"))

MESSAGE_DUPLICATE_TTL_SEC = int(os.environ.get("MESSAGE_DUPLICATE_TTL_SEC", str(12 * 3600)))
ACTIVE_SIGNAL_TTL_SEC = int(os.environ.get("ACTIVE_SIGNAL_TTL_SEC", str(72 * 3600)))
NEWS_REFRESH_SECONDS = int(os.environ.get("NEWS_REFRESH_SECONDS", "900"))

MIN_ALERT_SCORE = int(os.environ.get("MIN_ALERT_SCORE", "68"))
MIN_ALERT_VOLUME_IDR = float(os.environ.get("MIN_ALERT_VOLUME_IDR", "500000000"))
MAX_ALERT_RANGE_POS = float(os.environ.get("MAX_ALERT_RANGE_POS", "88"))

# Threshold khusus EARLY ENTRY: dilonggarin biar masuk sebelum pump meledak.
EARLY_MIN_SCORE = int(os.environ.get("EARLY_MIN_SCORE", "58"))
EARLY_MIN_VOLUME_IDR = float(os.environ.get("EARLY_MIN_VOLUME_IDR", "300000000"))
EARLY_MAX_RANGE_POS = float(os.environ.get("EARLY_MAX_RANGE_POS", "70"))  # harus masih di paruh bawah range 24h
EARLY_MIN_SETUP_STRENGTH = int(os.environ.get("EARLY_MIN_SETUP_STRENGTH", "3"))  # min checklist setup terpenuhi


# === STATE ===
_last_sinyal_date = None
_last_summary_date = None
_fomo_sent_symbols = {}
_confluence_sent_symbols = {}  # track real-time confluence alerts
_early_sent_symbols = {}  # track EARLY entry alerts (pre-pump)
_active_signals = {}  # track sinyal beli aktif untuk TP/SL monitor
_daily_stats = {"tp_hit": 0, "sl_hit": 0, "signals_sent": 0}
_last_fomo_alert_time = 0  # track last global FOMO alert to prevent spamming
_message_fingerprints = {}  # Anti-duplicate message fingerprint cache
_last_news_profile = None
_last_news_profile_at = 0


STATE_FILE = "bot_state.json"

def load_bot_state():
    global _last_sinyal_date, _last_summary_date, _fomo_sent_symbols, _confluence_sent_symbols, _early_sent_symbols, _active_signals, _daily_stats, _last_fomo_alert_time, _message_fingerprints
    if not os.path.exists(STATE_FILE):
        log("No state file found. Starting fresh.")
        return
    try:
        with open(STATE_FILE, "r") as f:
            data = json.load(f)
        _last_sinyal_date = data.get("last_sinyal_date", _last_sinyal_date)
        _last_summary_date = data.get("last_summary_date", _last_summary_date)
        _fomo_sent_symbols = data.get("fomo_sent_symbols", _fomo_sent_symbols)
        _confluence_sent_symbols = data.get("confluence_sent_symbols", _confluence_sent_symbols)
        _early_sent_symbols = data.get("early_sent_symbols", _early_sent_symbols)
        _active_signals = data.get("active_signals", _active_signals)
        _daily_stats = data.get("daily_stats", _daily_stats)
        _last_fomo_alert_time = data.get("last_fomo_alert_time", _last_fomo_alert_time)
        _message_fingerprints = data.get("message_fingerprints", _message_fingerprints)

        
        # Convert _active_signals hit back to set (JSON arrays become lists)
        for sym in _active_signals:
            if "hit" in _active_signals[sym] and isinstance(_active_signals[sym]["hit"], list):
                _active_signals[sym]["hit"] = set(_active_signals[sym]["hit"])
                
        log("Bot state successfully loaded from bot_state.json")
    except Exception as e:
        log(f"Error loading bot state: {e}")

def save_bot_state():
    global _last_sinyal_date, _last_summary_date, _fomo_sent_symbols, _confluence_sent_symbols, _early_sent_symbols, _active_signals, _daily_stats, _last_fomo_alert_time, _message_fingerprints
    try:
        # Convert set to list for JSON serialization
        active_signals_copy = {}
        for sym, sig in _active_signals.items():
            sig_copy = sig.copy()
            if "hit" in sig_copy and isinstance(sig_copy["hit"], set):
                sig_copy["hit"] = list(sig_copy["hit"])
            active_signals_copy[sym] = sig_copy
            
        data = {
            "last_sinyal_date": _last_sinyal_date,
            "last_summary_date": _last_summary_date,
            "fomo_sent_symbols": _fomo_sent_symbols,
            "confluence_sent_symbols": _confluence_sent_symbols,
            "early_sent_symbols": _early_sent_symbols,
            "active_signals": active_signals_copy,
            "daily_stats": _daily_stats,
            "last_fomo_alert_time": _last_fomo_alert_time,
            "message_fingerprints": _message_fingerprints,
            "early_sent_symbols": _early_sent_symbols
        }

        tmp_path = f"{STATE_FILE}.tmp"
        with open(tmp_path, "w") as f:
            json.dump(data, f, indent=4)
        os.replace(tmp_path, STATE_FILE)
    except Exception as e:
        log(f"Error saving bot state: {e}")


def log(msg):
    ts = datetime.now(WIB).strftime("%H:%M:%S")
    print(f"[{ts}] {msg}")


def clamp(value, lower, upper):
    return max(lower, min(upper, value))


def is_entry_action(action):
    """Check if action is a genuine entry signal (not 'JANGAN BELI')."""
    action = str(action or "").upper()
    return "BELI KUAT" in action or "CICIL BELI" in action


def apply_bot_learning(result):
    """Adjust score/allocation from historical signal outcomes."""
    apply_learning_adjustments([result])
    return result


def get_bot_news_profile(force=False):
    global _last_news_profile, _last_news_profile_at
    now_ts = time.time()
    if force or _last_news_profile is None or now_ts - _last_news_profile_at >= NEWS_REFRESH_SECONDS:
        _last_news_profile = build_news_profile(symbols=list(MAIN_ASSETS.keys()) + list(MICIN_COINS))
        _last_news_profile_at = now_ts
    return _last_news_profile


def apply_bot_intelligence(result):
    apply_news_adjustments([result], get_bot_news_profile())
    apply_learning_adjustments([result])
    return result


def record_bot_learning_signal(result, pair=None, source="bot"):
    payload = dict(result)
    payload["pair"] = pair or payload.get("pair")
    payload["target"] = payload.get("target", payload.get("tp3"))
    payload["allocation_pct"] = payload.get("allocation_pct", payload.get("alloc_pct", 0))
    payload["source"] = source
    return record_signal(payload, is_entry_action)


# =============================================================================
# DATA FETCHING
# =============================================================================
def fetch_all_tickers():
    """Satu fetch untuk semua data dari Indodax menggunakan summaries API"""
    try:
        resp = requests.get("https://indodax.com/api/summaries", timeout=10)
        data = resp.json()
        tickers = data.get("tickers", {})
        prices_24h = data.get("prices_24h", {})
        all_coins = {}
        for pair, info in tickers.items():
            if not pair.endswith("_idr"):
                continue
            symbol = pair.replace("_idr", "").upper()
            price = float(info["last"])
            pair_key = pair.replace("_", "")
            ref_price = float((prices_24h or {}).get(pair_key, 0))
            if ref_price > 0:
                change = ((price - ref_price) / ref_price) * 100
            else:
                change = 0.0

            all_coins[symbol] = {
                "symbol": symbol, "pair": pair,
                "price": price,
                "change": round(change, 2),
                "vol_idr": float(info.get("vol_idr", 0)),
                "high": float(info.get("high", 0)),
                "low": float(info.get("low", 0)),
            }
        return all_coins
    except Exception as e:
        log(f"Fetch error: {e}")
        return {}


def fetch_candles(pair_id, tf="60", lookback_days=21):
    """Ambil candle historis dari Indodax untuk indikator teknikal."""
    end_ts = int(time.time())
    start_ts = end_ts - lookback_days * 86400
    symbol = pair_id.replace("_", "").upper()
    url = "https://indodax.com/tradingview/history_v2"
    try:
        resp = requests.get(url, params={"from": start_ts, "to": end_ts, "tf": tf, "symbol": symbol}, timeout=8)
        rows = resp.json()
    except Exception:
        return pd.DataFrame()
    if not isinstance(rows, list) or not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    rename = {"Time": "time", "Open": "open", "High": "high", "Low": "low", "Close": "close", "Volume": "volume"}
    df = df.rename(columns=rename)
    required = ["time", "open", "high", "low", "close", "volume"]
    if not all(c in df.columns for c in required):
        return pd.DataFrame()
    for c in required:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=["close"]).sort_values("time")
    return df.tail(500).reset_index(drop=True)


# =============================================================================
# TECHNICAL INDICATORS
# =============================================================================
def compute_rsi(close, period=14):
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1/period, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1/period, adjust=False).mean()
    rs = gain / loss.replace(0, pd.NA)
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
    agg = {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
    return df.resample(rule).agg(agg).dropna(subset=["close"]).reset_index(drop=True)


def _timeframe_bias(candles):
    if candles.empty or len(candles) < 12:
        return "NO DATA", 0
    close = candles["close"].astype(float)
    ema_fast = compute_ema(close, 5).iloc[-1]
    ema_slow = compute_ema(close, 13).iloc[-1]
    lookback = min(6, len(close) - 1)
    momentum = (close.iloc[-1] / close.iloc[-1 - lookback] - 1) * 100 if lookback > 0 and close.iloc[-1 - lookback] > 0 else 0
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
    tr = pd.concat([high - low, (high - close.shift(1)).abs(), (low - close.shift(1)).abs()], axis=1).max(axis=1)
    atr = tr.rolling(14).mean()
    ema_fast = close.ewm(span=10, adjust=False).mean()
    ema_slow = close.ewm(span=30, adjust=False).mean()
    floor = ((high + low) / 2) - (2.4 * atr)
    if pd.notna(floor.iloc[-1]) and close.iloc[-1] > floor.iloc[-1] and ema_fast.iloc[-1] > ema_slow.iloc[-1]:
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
    tr = pd.concat([hi - lo, (hi - cl.shift(1)).abs(), (lo - cl.shift(1)).abs()], axis=1).max(axis=1)
    up = hi - hi.shift(1)
    dn = lo.shift(1) - lo
    pdm = up.where((up > dn) & (up > 0), 0.0)
    ndm = dn.where((dn > up) & (dn > 0), 0.0)
    atr = tr.ewm(alpha=1/14, adjust=False).mean()
    pdi = 100 * pdm.ewm(alpha=1/14, adjust=False).mean() / atr.replace(0, float('nan'))
    ndi = 100 * ndm.ewm(alpha=1/14, adjust=False).mean() / atr.replace(0, float('nan'))
    dx = 100 * abs(pdi - ndi) / (pdi + ndi).replace(0, float('nan'))
    adx = float(dx.fillna(25).ewm(alpha=1/14, adjust=False).mean().iloc[-1])
    pdi_v = float(pdi.fillna(0).iloc[-1])
    ndi_v = float(ndi.fillna(0).iloc[-1])
    if adx >= 25:
        trend = "bullish_strong" if pdi_v > ndi_v and adx >= 40 else "bullish" if pdi_v > ndi_v else "bearish_strong" if adx >= 40 else "bearish"
    else:
        trend = "sideways"
    return {"adx": round(adx, 1), "trend": trend}


def compute_ml_forecast(candles):
    """KNN sederhana: prediksi probabilitas naik dari pola historis."""
    default = {"ml_prob": 50.0, "ml_label": "NO DATA", "ml_conf": "rendah"}
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
    rsi = 100 - (100 / (1 + gain / loss.replace(0, pd.NA)))
    feat = pd.DataFrame({
        "ret1": ret1, "ret3": close.pct_change(3)*100, "ret6": close.pct_change(6)*100,
        "vol12": ret1.rolling(12).std(),
        "ema_gap": (close.ewm(span=8,adjust=False).mean() - close.ewm(span=21,adjust=False).mean()) / close * 100,
        "rsi": rsi,
        "rng": (close - low.rolling(24).min()) / (high.rolling(24).max() - low.rolling(24).min()).replace(0, pd.NA) * 100,
        "vr": volume / volume.rolling(24).mean().replace(0, pd.NA),
    })
    feat["future"] = close.shift(-6) / close * 100 - 100
    feat = feat.replace([float('inf'), float('-inf')], pd.NA)
    cols = ["ret1","ret3","ret6","vol12","ema_gap","rsi","rng","vr"]
    current = feat[cols].dropna().tail(1).astype(float)
    train = feat.dropna(subset=cols+["future"]).copy()
    if current.empty or len(train) < 50:
        return default
    means = train[cols].mean()
    stds = train[cols].std().replace(0,1).fillna(1)
    tx = ((train[cols]-means)/stds).astype(float)
    cx = ((current.iloc[0]-means)/stds).astype(float)
    dist = tx.sub(cx, axis=1).pow(2).sum(axis=1).pow(0.5)
    dist = pd.to_numeric(dist, errors='coerce').dropna()
    if dist.empty:
        return default
    k = int(clamp(round(len(train)**0.5), 12, 35))
    nearest = train.loc[dist.nsmallest(k).index]
    w = 1 / (dist.loc[nearest.index] + 0.001)
    prob = float(((nearest["future"] > 1.0).astype(float) * w).sum() / w.sum() * 100)
    label = "BULLISH" if prob >= 62 else "BEARISH" if prob <= 42 else "NETRAL"
    edge = abs(prob - 50)
    conf = "tinggi" if len(train) >= 180 and edge >= 14 else "sedang" if len(train) >= 90 and edge >= 8 else "rendah"
    return {"ml_prob": round(prob,1), "ml_label": label, "ml_conf": conf}


def compute_backtest(candles):
    """Test sinyal serupa di data historis: berhasil atau gagal?"""
    default = {"bt_wr": 0, "bt_trades": 0, "bt_label": "DATA KURANG"}
    if candles.empty or len(candles) < 90:
        return default
    close = candles["close"].astype(float)
    high = candles["high"].astype(float)
    low = candles["low"].astype(float)
    volume = candles["volume"].astype(float)
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    rsi = 100 - (100 / (1 + gain / loss.replace(0, pd.NA)))
    ema8 = close.ewm(span=8, adjust=False).mean()
    ema21 = close.ewm(span=21, adjust=False).mean()
    vr = volume / volume.rolling(24).mean().replace(0, pd.NA)
    sig = ((ema8>ema21) & rsi.between(42,72) & (vr>=0.75)).fillna(False)
    outcomes = []
    last_i = -6
    for i in range(35, len(candles)-7):
        if not bool(sig.iloc[i]) or i - last_i < 6:
            continue
        entry = float(close.iloc[i])
        if entry <= 0: continue
        tgt = entry * 1.026
        stp = entry * 0.978
        out = None
        for j in range(i+1, i+7):
            if float(low.iloc[j]) <= stp: out = -2.2; break
            if float(high.iloc[j]) >= tgt: out = 2.6; break
        if out is None:
            out = float((close.iloc[i+6]-entry)/entry*100)
        outcomes.append(out)
        last_i = i
    if len(outcomes) < 6:
        return default
    wins = [x for x in outcomes if x > 0]
    wr = len(wins)/len(outcomes)*100
    label = "TERUJI" if wr >= 58 and len(outcomes) >= 14 else "CUKUP" if wr >= 50 else "LEMAH"
    return {"bt_wr": round(wr,1), "bt_trades": len(outcomes), "bt_label": label}


def build_verdict(score, rsi, macd_signal, supertrend, adx_data, ml, bt, risk_level, vol_idr):
    """Komite bull/bear sederhana: approve, approve kecil, tunggu, atau tolak."""
    bull = bear = 0
    if score >= 75: bull += 18
    elif score >= 65: bull += 10
    else: bear += 8
    if ml["ml_prob"] >= 62: bull += 12
    elif ml["ml_prob"] <= 42: bear += 12
    if bt["bt_trades"] >= 10 and bt["bt_wr"] >= 58: bull += 14
    elif bt["bt_trades"] >= 10 and bt["bt_label"] == "LEMAH": bear += 16
    if adx_data["trend"] in ("bullish_strong","bullish"): bull += 7
    elif adx_data["trend"] in ("bearish_strong","bearish"): bear += 9
    if supertrend == "bullish": bull += 7
    elif supertrend == "bearish": bear += 9
    if rsi >= 78: bear += 8
    if vol_idr < 100_000_000: bear += 12
    elif vol_idr >= 5_000_000_000: bull += 5
    net = int(clamp(50 + bull - bear, 0, 100))
    if risk_level == "TINGGI" or bear >= bull + 18:
        return "TOLAK", net, 0
    elif bear >= bull + 5 or net < 48:
        return "TUNGGU", net, 0
    elif risk_level == "SEDANG":
        return "APPROVE KECIL", net, 0.55
    return "APPROVE", net, 1.0


def compute_ema200_trend(candles):
    if candles.empty or len(candles) < 220:
        return {
            "ema200_ok": False,
            "ema200": None,
            "trend_side": "NO DATA"
        }
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
    return {
        "ema200_ok": ok,
        "ema200": last_ema200,
        "trend_side": side
    }


def compute_volume_anomaly(candles, threshold=1.2):
    if candles.empty or len(candles) < 22:
        return {
            "volume_ok": False,
            "volume_ratio": 1.0
        }

    closed = candles.iloc[:-1]
    volume = closed["volume"].astype(float)

    avg20 = volume.tail(21).iloc[:-1].mean()
    last_vol = float(volume.iloc[-1])

    if avg20 <= 0:
        return {
            "volume_ok": False,
            "volume_ratio": 1.0
        }

    ratio = last_vol / avg20

    return {
        "volume_ok": ratio >= threshold,
        "volume_ratio": round(ratio, 2)
    }


def detect_bullish_pinbar(candles):
    if candles.empty or len(candles) < 3:
        return {
            "pinbar_ok": False,
            "pinbar_type": "NO DATA"
        }

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
        return {
            "pinbar_ok": False,
            "pinbar_type": "INVALID"
        }

    body_pct = body / candle_range
    lower_pct = lower_shadow / candle_range
    upper_pct = upper_shadow / candle_range

    bullish_pinbar = (
        lower_pct >= 0.45 and
        body_pct <= 0.35 and
        close > open_ and
        upper_pct <= 0.35
    )

    return {
        "pinbar_ok": bullish_pinbar,
        "pinbar_type": "BULLISH_PINBAR" if bullish_pinbar else "NO_REJECTION"
    }


def compute_dynamic_walls(candles, tolerance_pct=1.0):
    if candles.empty or len(candles) < 100:
        return {
            "dynamic_wall_ok": False,
            "wall_type": "NO DATA"
        }
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
        "upper_bb": upper_bb
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

    near_support = abs(last_price - support) / support * 100 <= tolerance_pct if support > 0 else False
    near_resistance = abs(last_price - resistance) / resistance * 100 <= tolerance_pct if resistance > 0 else False

    return {
        "sr_ok": near_support,
        "sr_type": "SUPPORT" if near_support else "RESISTANCE" if near_resistance else "NONE",
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


def analyze_coin(symbol, data, candles):
    """Analisis lengkap satu koin menggunakan semua indikator."""
    price = data["price"]
    change = data["change"]
    vol_idr = data["vol_idr"]
    high_24h = data["high"]
    low_24h = data["low"]
    range_w = high_24h - low_24h
    range_pos = ((price - low_24h) / range_w * 100) if range_w > 0 else 50

    # Defaults jika candle kosong
    rsi = 50
    ema_bias = "netral"
    macd_signal = "netral"
    bb = {"bb_signal": "netral", "bb_pct_b": 0.5}
    supertrend = "netral"
    vol_label, vol_ratio = "normal", 1.0
    ema_trend_pct = 0

    if not candles.empty and len(candles) >= 8:
        close = candles["close"].astype(float)
        rsi = compute_rsi(close) if len(close) >= 14 else 50
        ema5 = compute_ema(close, 5).iloc[-1]
        ema12 = compute_ema(close, 12).iloc[-1]
        ema_trend_pct = ((ema5 - ema12) / ema12 * 100) if ema12 > 0 else 0
        ema_bias = "bullish" if ema5 > ema12 else "bearish"
        macd_signal, _ = compute_macd(close)
        bb = compute_bollinger(close)
        supertrend = compute_supertrend(candles)
        vol_label, vol_ratio = compute_volume_analysis(candles)

    # Advanced analysis
    adx_data = compute_adx(candles)
    ml = compute_ml_forecast(candles)
    bt = compute_backtest(candles)
    confluence = compute_confluence_signal(candles)
    mtf = compute_multi_timeframe_confirmation(candles)

    # --- SCORING ---
    liquidity_bonus = min(16, vol_idr / 1_000_000_000)
    fomo_penalty = 9 if range_pos > 88 and change > 8 else 0
    micin_penalty = 6 if symbol in MICIN_COINS else 0

    tech_score = 0
    tech_score += clamp(ema_trend_pct * 3, -12, 12)
    tech_score += 8 if macd_signal == "bullish cross" else 5 if macd_signal == "bullish" else -8 if macd_signal == "bearish cross" else -5 if macd_signal == "bearish" else 0
    tech_score += 6 if 45 <= rsi <= 68 else -7 if rsi > 78 else -4 if rsi < 30 else 0
    tech_score += 5 if supertrend == "bullish" else -6 if supertrend == "bearish" else 0
    tech_score += 4 if vol_label in ("spike", "kuat") else -3 if vol_label == "tipis" else 0

    bb_bonus = 7 if bb["bb_signal"] == "oversold" else -5 if bb["bb_signal"] == "overbought" else 0

    # ADX bonus
    adx_bonus = 5 if adx_data["trend"] in ("bullish_strong","bullish") else -5 if adx_data["trend"] in ("bearish_strong","bearish") else 0

    # ML adjustment
    ml_adj = (ml["ml_prob"] - 50) * 0.28
    if ml["ml_conf"] == "rendah": ml_adj *= 0.45
    elif ml["ml_conf"] == "sedang": ml_adj *= 0.75

    # Backtest adjustment
    bt_adj = 0
    if bt["bt_trades"] >= 6:
        bt_adj = (bt["bt_wr"] - 50) * 0.12

    momentum = change
    base = (
        50
        + momentum * 4.2
        + liquidity_bonus
        + tech_score * 0.65
        + bb_bonus
        + adx_bonus
        + ml_adj
        + bt_adj
        + mtf["mtf_adjustment"]
        - fomo_penalty
        - micin_penalty
    )
    score = int(clamp(round(base), 0, 100))

    # Action — threshold yang realistis agar sinyal bisa lolos
    if score >= 78 and momentum > 1.0:
        action, emoji = "BELI KUAT", "🟢"
    elif score >= 62 and momentum > 0:
        action, emoji = "CICIL BELI", "🟡"
    elif score >= 50:
        action, emoji = "WATCH", "⚪"
    elif score >= 35:
        action, emoji = "JANGAN BELI", "🔴"
    else:
        action, emoji = "HINDARI", "⛔"

    # Confluence Gate: Entry hanya diperbolehkan jika minimal 3 dari 5 indikator valid
    # (sebelumnya 4/5 — terlalu ketat, hampir mustahil terpenuhi bersamaan)
    if confluence["confluence_passed"] < 3:
        if action in ("BELI KUAT", "CICIL BELI"):
            action = "JANGAN BELI"
            emoji = "🔴"
    elif confluence["confluence_passed"] < 4:
        if action == "BELI KUAT":
            action, emoji = "CICIL BELI", "🟡"

    # Anti-FOMO Filter: Jangan asal masuk jika sudah sangat dekat harga tertinggi 24h
    # (threshold dinaikkan dari 85/5% ke 92/8% agar tidak terlalu agresif memblokir)
    if range_pos > 92 and change > 8:
        if action in ("BELI KUAT", "CICIL BELI"):
            action = "WATCH"
            emoji = "⚪"

    # Multi-timeframe guard: jangan agresif jika 4H/1D kompak bearish KUAT.
    # (threshold dari -5 ke -8, agar sinyal bearish ringan tidak langsung blokir)
    if mtf["mtf_adjustment"] <= -8 and action == "BELI KUAT":
        action, emoji = "CICIL BELI", "🟡"

    # Risk level
    risk_pts = 0
    if abs(change) >= 10: risk_pts += 2
    elif abs(change) >= 5: risk_pts += 1
    if vol_idr < 100_000_000: risk_pts += 2
    elif vol_idr < 1_000_000_000: risk_pts += 1
    if rsi > 78: risk_pts += 1
    if macd_signal == "bearish cross": risk_pts += 1
    if supertrend == "bearish": risk_pts += 1
    if range_pos > 85: risk_pts += 1
    if ml["ml_label"] == "BEARISH" and ml["ml_conf"] != "rendah": risk_pts += 1
    if bt["bt_label"] == "LEMAH" and bt["bt_trades"] >= 10: risk_pts += 1

    risk_level = "TINGGI" if risk_pts >= 4 else "SEDANG" if risk_pts >= 2 else "RENDAH"

    # Verdict
    verdict, verdict_net, size_mult = build_verdict(score, rsi, macd_signal, supertrend, adx_data, ml, bt, risk_level, vol_idr)

    # Dynamic TP/SL
    gain_pct = clamp(3 + max(momentum, 0) * 0.75 + (score - 60) * 0.22, 2, 18)
    stop_pct = clamp(2.6 + abs(momentum) * 0.35 + (1 if risk_level == "TINGGI" else 0), 2.5, 9)
    tp1 = price * (1 + gain_pct * 0.35 / 100)
    tp2 = price * (1 + gain_pct * 0.7 / 100)
    tp3 = price * (1 + gain_pct / 100)
    sl = price * (1 - stop_pct / 100)
    trailing = clamp(stop_pct * 0.55, 1.5, 5)

    # Allocation (adjusted by verdict, confluence and conf strength)
    risk_mod = {"RENDAH": 1.0, "SEDANG": 0.65, "TINGGI": 0.35}[risk_level]
    conf_size_mult = 1.0 if confluence["confluence_passed"] == 5 else 0.5 if confluence["confluence_passed"] == 4 else 0
    alloc = clamp(7 * (score / 100) * risk_mod * size_mult * conf_size_mult, 0, 10) if is_entry_action(action) and confluence["allow_entry"] else 0

    return {
        "symbol": symbol, "price": price, "change": change, "vol_idr": vol_idr,
        "score": score, "action": action, "emoji": emoji,
        "rsi": round(rsi, 1), "ema_bias": ema_bias, "macd_signal": macd_signal,
        "bb_signal": bb["bb_signal"], "supertrend": supertrend,
        "adx": adx_data["adx"], "adx_trend": adx_data["trend"],
        "ml_prob": ml["ml_prob"], "ml_label": ml["ml_label"], "ml_conf": ml["ml_conf"],
        "bt_wr": bt["bt_wr"], "bt_trades": bt["bt_trades"], "bt_label": bt["bt_label"],
        "verdict": verdict, "verdict_net": verdict_net,
        "vol_label": vol_label, "risk_level": risk_level,
        "tp1": tp1, "tp2": tp2, "tp3": tp3, "stop_loss": sl,
        "trailing_pct": round(trailing, 1), "alloc_pct": round(alloc, 1),
        "range_pos": round(range_pos, 1),
        "mtf_label": mtf["mtf_label"],
        "mtf_4h": mtf["mtf_4h"],
        "mtf_1d": mtf["mtf_1d"],
        "mtf_score": mtf["mtf_score"],
        "mtf_adjustment": mtf["mtf_adjustment"],
        # Confluence
        "confluence_passed": confluence["confluence_passed"],
        "confluence_total": confluence["confluence_total"],
        "confluence_label": confluence["confluence_label"],
        "confluence_strength": confluence["confluence_strength"],
        "confluence_checks": confluence["checks"],
    }


# =============================================================================
# MARKET MODE
# =============================================================================
def detect_market_mode(all_coins):
    """Deteksi kondisi pasar global: agresif/normal/defensif."""
    changes = [c["change"] for c in all_coins.values() if c["vol_idr"] >= 100_000_000]
    if not changes:
        return "normal", "Data tidak cukup"
    green = sum(1 for c in changes if c > 0)
    pct_green = green / len(changes) * 100
    avg_change = sum(changes) / len(changes)

    if pct_green >= 62 and avg_change > 1:
        return "agresif", f"{pct_green:.0f}% koin hijau, avg +{avg_change:.1f}%"
    elif pct_green <= 38 or avg_change < -2:
        return "defensif", f"{pct_green:.0f}% koin hijau, avg {avg_change:.1f}%"
    return "normal", f"{pct_green:.0f}% koin hijau, avg {avg_change:+.1f}%"


# =============================================================================
# TELEGRAM MESSAGING
# =============================================================================
def format_idr(value):
    if value is None: return "-"
    if value >= 1_000_000_000: return f"Rp{value/1_000_000_000:,.2f}M"
    if value >= 1_000_000: return f"Rp{value/1_000_000:,.1f}JT"
    if value >= 1_000: return f"Rp{value:,.0f}"
    return f"Rp{value:,.2f}"


import hashlib
import re

def _message_fingerprint(text):
    normalized = re.sub(r"\d+(?:[.,]\d+)?", "#", str(text))
    normalized = re.sub(r"\s+", " ", normalized).strip().lower()
    return hashlib.sha256(normalized.encode()).hexdigest()


def send_message(text, notify=False, force=False):
    global _message_fingerprints

    if not BOT_TOKEN or not CHAT_ID:
        return False

    now_ts = time.time()

    if not force:
        fp = _message_fingerprint(text)

        # cleanup cache
        _message_fingerprints = {
            k: v for k, v in _message_fingerprints.items()
            if now_ts - v < MESSAGE_DUPLICATE_TTL_SEC
        }

        if fp in _message_fingerprints:
            return False

        _message_fingerprints[fp] = now_ts

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    # Split panjang
    chunks = [text] if len(text) <= 4096 else _split_text(text)
    for i, chunk in enumerate(chunks):
        payload = {"chat_id": CHAT_ID, "text": chunk, "parse_mode": "Markdown", "disable_notification": not notify}
        try:
            resp = requests.post(url, json=payload, timeout=10)
            result = resp.json()
            if not result.get("ok") and "parse" in str(result.get("description", "")).lower():
                payload["parse_mode"] = None
                resp2 = requests.post(url, json=payload, timeout=10)
                result = resp2.json()
            if not result.get("ok"):
                log(f"Telegram error: {result}")
        except Exception as e:
            log(f"Send error: {e}")
        if i < len(chunks) - 1:
            time.sleep(0.3)
    return True


def _split_text(text, max_len=4096):
    chunks = []
    while len(text) > max_len:
        sp = text.rfind("\n\n", 0, max_len)
        if sp < max_len // 2:
            sp = text.rfind("\n", 0, max_len)
        if sp < max_len // 2:
            sp = max_len
        chunks.append(text[:sp].strip())
        text = text[sp:].strip()
    if text:
        chunks.append(text)
    return chunks


# =============================================================================
# SINYAL HARIAN (UPGRADED)
# =============================================================================
def send_sinyal_harian(all_coins):
    global _last_sinyal_date
    today = datetime.now(WIB).strftime("%Y-%m-%d")
    if _last_sinyal_date == today:
        return False

    # Detect market mode
    mode, mode_desc = detect_market_mode(all_coins)
    mode_emoji = {"agresif": "🟢 AGRESIF", "normal": "🟡 NORMAL", "defensif": "🔴 DEFENSIF"}[mode]

    # Fetch candles + analyze each main asset
    signals = []
    for sym, pair in MAIN_ASSETS.items():
        if sym not in all_coins:
            continue
        candles = fetch_candles(pair)
        time.sleep(0.3)  # rate limit
        result = apply_bot_intelligence(analyze_coin(sym, all_coins[sym], candles))
        signals.append(result)

    if not signals:
        log("Gagal ambil data untuk sinyal harian")
        return False

    # Sort: BELI KUAT > CICIL BELI > WATCH > JANGAN BELI > HINDARI
    priority = {"BELI KUAT": 0, "CICIL BELI": 1, "WATCH": 2, "JANGAN BELI": 3, "HINDARI": 4}
    signals.sort(key=lambda x: priority.get(x["action"], 5))

    # Pisahkan sinyal beli vs pantauan biar pesan gampang dibaca
    buy_signals = [s for s in signals if is_entry_action(s["action"])]
    watch_signals = [s for s in signals if not is_entry_action(s["action"])]
    buy_count = len(buy_signals)

    # Format message — ringkas, fokus ke aksi (entry/TP/SL) dulu, alasan teknikal jadi 1 baris
    now = datetime.now(WIB)
    lines = [
        "💰 *SINYAL CRYPTO HARI INI*",
        f"📅 {now.strftime('%d %B %Y')}  ·  Market: {mode_emoji}",
        f"_{mode_desc}_",
    ]
    if buy_count > 0:
        lines.append(f"✅ *{buy_count} koin layak beli* — pilih 1-2 terbaik, jangan serakah.")
    else:
        lines.append("⏸️ *Belum ada sinyal beli bersih hari ini.*")
    lines.append("━━━━━━━━━━━━━━━━━━")
    lines.append("")

    def _why_line(s):
        """Satu baris alasan singkat, bahasa manusia."""
        bits = []
        if s.get("ml_label") in ("BULLISH", "BEARISH"):
            bits.append(f"ML {s['ml_label'].lower()} {s['ml_prob']}%")
        if s.get("bt_trades", 0) >= 6 and s.get("bt_label") not in ("DATA KURANG",):
            bits.append(f"backtest {s['bt_label'].lower()} (WR {s['bt_wr']}%)")
        if s.get("mtf_label") in ("ALIGN BULLISH", "BULLISH BIAS"):
            bits.append("tren 4H+1D searah naik")
        elif s.get("mtf_label") in ("ALIGN BEARISH", "BEARISH BIAS"):
            bits.append("tren 4H+1D masih turun")
        if s.get("news_label") and s.get("news_label") != "NO DATA":
            bits.append(f"berita {str(s['news_label']).lower()}")
        return " · ".join(bits[:3]) if bits else "momentum + likuiditas"

    # --- BAGIAN 1: SINYAL BELI (detail lengkap tapi rapi) ---
    if buy_signals:
        for s in buy_signals:
            pair_url = MAIN_ASSETS[s["symbol"]].upper().replace("_", "")
            link = f"https://indodax.com/market/{pair_url}?ref={INDODAX_REF}"
            ch = f"+{s['change']:.2f}" if s["change"] >= 0 else f"{s['change']:.2f}"

            lines.append(f"{s['emoji']} *{s['symbol']} — {s['action']}*  ·  Skor {s['score']}/100")
            lines.append(f"   💵 Harga {format_idr(s['price'])} ({ch}%)  ·  Risiko {s['risk_level']}")
            lines.append(f"   🎯 Entry sekarang → TP {format_idr(s['tp1'])} / {format_idr(s['tp2'])} / {format_idr(s['tp3'])}")
            lines.append(f"   🛑 Stop loss {format_idr(s['stop_loss'])}  ·  trailing {s['trailing_pct']}%")
            lines.append(f"   💰 Alokasi {s['alloc_pct']}% modal")
            lines.append(f"   📋 Kenapa: {_why_line(s)}")
            lines.append(f"   👉 [BELI DI INDODAX]({link})")
            lines.append("")
            # Track for TP/SL monitoring
            _active_signals[s['symbol']] = {
                'entry': s['price'], 'tp1': s['tp1'], 'tp2': s['tp2'], 'tp3': s['tp3'],
                'sl': s['stop_loss'], 'hit': set(), 'time': datetime.now(WIB).isoformat(),
            }
            record_bot_learning_signal(s, MAIN_ASSETS[s["symbol"]], source="daily")

    # --- BAGIAN 2: PANTAUAN (ringkas, 1 baris per koin) ---
    if watch_signals:
        lines.append("👀 *Belum entry — pantau dulu:*")
        for s in watch_signals:
            ch = f"+{s['change']:.2f}" if s["change"] >= 0 else f"{s['change']:.2f}"
            lines.append(f"   {s['emoji']} *{s['symbol']}* {s['action']} · skor {s['score']} · {format_idr(s['price'])} ({ch}%)")
        lines.append("")

    lines.append("━━━━━━━━━━━━━━━━━━")
    if mode == "defensif":
        lines.append("🛡️ Market defensif. Kalau entry, 1 koin saja & size kecil.")
    elif buy_count == 0:
        lines.append("💡 Simpan modal dulu, tunggu setup lebih bersih.")
    else:
        lines.append("💡 Disiplin TP/SL. Bot akan kabari otomatis saat TP/SL kena.")
    lines.append("⚠️ Bukan saran keuangan. DYOR.")
    lines.append(f"💎 Gabung: {TELEGRAM_CHANNEL}")


    result = send_message("\n".join(lines), notify=False)
    if result:
        _last_sinyal_date = today
        _daily_stats['signals_sent'] += buy_count
        log(f"Sinyal harian TERKIRIM! ({len(signals)} koin, {buy_count} beli)")
        return True
    return False


# =============================================================================
# FOMO DETECTION (UPGRADED)
# =============================================================================
def detect_fomo(all_coins):
    fomo_gila, fomo, pumping = [], [], []
    for sym, data in all_coins.items():
        change = data["change"]
        vol = data["vol_idr"]
        # Batas volume dinamis berdasarkan persentase kenaikan harga (kecuali Blue Chips)
        if sym not in BLUE_CHIPS:
            if change > 30:
                min_vol = 1_000_000_000  # Kejadian sangat luar biasa -> minimal 1 Miliar
            elif change > 20:
                min_vol = 1_500_000_000  # Luar biasa -> minimal 1.5 Miliar
            elif change > 12:
                min_vol = 2_000_000_000  # Signifikan -> minimal 2 Miliar
            else:
                min_vol = 3_000_000_000  # Normal pumping -> minimal 3 Miliar
            if vol < min_vol:
                continue

        item = {
            "symbol": sym, "pair": data["pair"],
            "price": data["price"], "change": round(change, 2),
            "vol_idr": vol, "high": data["high"], "low": data["low"],
        }
        if change > 20:
            fomo_gila.append(item)
        elif change > 12:
            fomo.append(item)
        elif change > 8:
            pumping.append(item)
    for lst in [fomo_gila, fomo, pumping]:
        lst.sort(key=lambda x: x["change"], reverse=True)
    return fomo_gila, fomo, pumping


def format_fomo_alert(fomo_gila, fomo, pumping, all_coins):
    if not fomo_gila and not fomo and not pumping:
        return None

    lines = ["🚨 *PUNCAK FOMO -- PUMP DETECTED!* 🚨", "──────────────────────", ""]

    def _add_coins(lst, label):
        if not lst:
            return
        lines.append(f"🔥 *{label}:*")
        for coin in lst[:3]:  # Batasi 3 teratas per kategori agar pesan tidak terlalu panjang
            sym = coin["symbol"]
            pair_url = coin["pair"].upper().replace("_", "")
            link = f"https://indodax.com/market/{pair_url}?ref={INDODAX_REF}"

            warning = ""
            rp = coin["high"] - coin["low"]
            if rp > 0:
                pos = (coin["price"] - coin["low"]) / rp * 100
                if pos > 85:
                    warning = " ⚠️ *DEKAT PUNCAK (RAWAN KOREKSI)*"

            lines.append(f"📈 *{sym}* -- *+{coin['change']}%*{warning}")
            lines.append(f"   Harga: {format_idr(coin['price'])} | Vol: {format_idr(coin['vol_idr'])}")
            
            # Dynamic Technical Intelligence
            try:
                candles = fetch_candles(coin["pair"])
                if not candles.empty:
                    ticker_info = all_coins.get(sym, coin)
                    res = apply_bot_intelligence(analyze_coin(sym, ticker_info, candles))
                    lines.append(f"   🧠 Intel Score: *{res['score']}/100* | Sinyal: *{res['action']}*")
                    lines.append(f"   📊 RSI: {res['rsi']} | EMA: {res['ema_bias']} | ST: *{res['supertrend']}*")
                    lines.append(f"   🤖 ML Predict: *{res['ml_label']}* ({res['ml_prob']}%)")
                    lines.append(f"   🎯 Target TP1: {format_idr(res['tp1'])} | SL: {format_idr(res['stop_loss'])}")
            except Exception as e:
                log(f"Dynamic analysis failed for {sym}: {e}")
                
            lines.append(f"   🔗 [Masuk Market Indodax]({link})")
            lines.append("")

    _add_coins(fomo_gila, "FOMO GILA (>20%)")
    _add_coins(fomo, "FOMO (>12%)")
    _add_coins(pumping, "PUMPING (>8%)")

    lines.append("──────────────────────")
    lines.append("⚠️ *Himbauan:* Selalu DYOR dan jangan FOMO secara asal. Gunakan stop loss!")
    lines.append(f"Gabung: {TELEGRAM_CHANNEL}")
    return "\n".join(lines)


def check_fomo_and_alert(all_coins):
    if not ENABLE_FOMO_ALERTS:
        return

    global _fomo_sent_symbols, _last_fomo_alert_time
    
    now_ts = time.time()
    # Cooldown global
    if now_ts - _last_fomo_alert_time < FOMO_GLOBAL_COOLDOWN_SEC:
        return

    fomo_gila, fomo, pumping = detect_fomo(all_coins)
    total = len(fomo_gila) + len(fomo) + len(pumping)
    if total == 0:
        return

    new_alerts = {}
    for lst in [fomo_gila, fomo, pumping]:
        for coin in lst:
            sym = coin["symbol"]
            change = coin["change"]
            if sym in _fomo_sent_symbols:
                # Agar tidak spam, butuh lonjakan tambahan +10% untuk alert ulang di hari yang sama
                if change >= _fomo_sent_symbols[sym]["change"] + 10.0:
                    new_alerts[sym] = coin
            else:
                new_alerts[sym] = coin

    # Cooldown per koin
    _fomo_sent_symbols = {k: v for k, v in _fomo_sent_symbols.items() if now_ts - v.get("_sent_at", 0) < FOMO_SYMBOL_COOLDOWN_SEC}

    if not new_alerts:
        return

    new_gila = [v for v in new_alerts.values() if v["change"] > 20]
    new_fomo = [v for v in new_alerts.values() if 12 < v["change"] <= 20]
    new_pump = [v for v in new_alerts.values() if 8 < v["change"] <= 12]
    for lst in [new_gila, new_fomo, new_pump]:
        lst.sort(key=lambda x: x["change"], reverse=True)

    msg = format_fomo_alert(new_gila, new_fomo, new_pump, all_coins)
    if msg:
        send_message(msg, notify=False)  # Completely silent for FOMO alerts
        log(f"FOMO ALERT terkirim! ({len(new_alerts)} koin)")
        _last_fomo_alert_time = now_ts  # update last global alert time
        for sym, coin in new_alerts.items():
            coin["_sent_at"] = now_ts
            _fomo_sent_symbols[sym] = coin


def check_realtime_confluence_alerts(all_coins):
    if not ENABLE_CONFLUENCE_ALERTS:
        return

    global _confluence_sent_symbols
    now_ts = time.time()
    sent = 0

    # Bersihkan cache alert
    _confluence_sent_symbols = {k: v for k, v in _confluence_sent_symbols.items() if now_ts - v["sent_at"] < CONFLUENCE_SYMBOL_COOLDOWN_SEC}

    for sym, pair in MAIN_ASSETS.items():
        if sym not in all_coins:
            continue

        # Hindari spam: jika baru dikirim dalam cooldown terakhir, lewati
        if sym in _confluence_sent_symbols:
            continue

        try:
            candles = fetch_candles(pair)
            time.sleep(0.3)  # rate limit safety
            if candles.empty:
                continue

            res = apply_bot_intelligence(analyze_coin(sym, all_coins[sym], candles))

            # Filtering to prevent noise / unwanted risk
            if res["score"] < MIN_ALERT_SCORE:
                continue

            if res["vol_idr"] < MIN_ALERT_VOLUME_IDR:
                continue

            if res["range_pos"] > MAX_ALERT_RANGE_POS:
                continue

            if res["risk_level"] == "TINGGI":
                continue

            # Confluence logic — dilonggarkan agar sinyal bisa lolos
            strong = res["confluence_passed"] >= 4
            smart = (
                res["confluence_passed"] >= 3 and
                res["ml_label"] in ("BULLISH", "NETRAL") and
                res["bt_label"] != "LEMAH"
            )

            if not is_entry_action(res["action"]) or not (strong or smart):
                continue
            
            # Kirim alert instan!
            pair_url = pair.upper().replace("_", "")
            link = f"https://indodax.com/market/{pair_url}?ref={INDODAX_REF}"
            link_tv = f"https://www.tradingview.com/chart/?symbol=INDODAX:{pair_url}"
            ch_sign = "+" if res["change"] >= 0 else ""
            
            insight_res = generate_signal_insight(res, GEMINI_API_KEY, DEEPSEEK_API_KEY)
            ai_insight = insight_res.get("insight", "📊 *ANALYTICS & INSIGHT:*\nAI Insight tidak tersedia saat ini.\n\n🟢 *INSTRUKSI:*\nIkuti sinyal teknikal di atas dengan manajemen risiko.")

            msg = (
                f"*[ RADAR SINYAL OTOMATIS ]*\n"
                f"🚨 *CEX OUTFLOW ALERT:* [${sym}]({link})\n"
                f"\n"
                f"🔥 *{res['action']} DETECTED!* Score: {res['score']}/100\n"
                f"──────────────────────\n"
                f"💵 Harga: {format_idr(res['price'])} ({ch_sign}{res['change']:.2f}%)\n"
                f"🛡️ Confluence: *{res['confluence_label']}* ({res['confluence_strength']})\n"
                f"🧠 ML Forecast: *{res['ml_label']}* ({res['ml_prob']}%, {res['ml_conf']})\n"
                f"📊 Backtest WR: *{res['bt_wr']}%* ({res['bt_trades']} trades)\n"
                f"\n"
                f"{ai_insight}\n"
                f"\n"
                f"🎯 TP1/TP2/TP3: {format_idr(res['tp1'])} / {format_idr(res['tp2'])} / {format_idr(res['tp3'])}\n"
                f"🛑 Stop Loss: {format_idr(res['stop_loss'])} | Trailing: {res['trailing_pct']}%\n"
                f"💰 Alokasi Modal: *{res['alloc_pct']}%*\n"
                f"\n"
                f"📈 *On-Chain Tracker:*\n"
                f"[Indodax]({link}) | [TradingView]({link_tv})\n"
                f"──────────────────────\n"
                f"⚠️ _Bukan saran keuangan. Selalu gunakan uang dingin (DYOR)._\n"
                f"💎 *Gabung Premium:* {TELEGRAM_CHANNEL}"
            )
            
            # Only notify (vibrate) for Strong Buy (BELI KUAT) to prevent phone vibration spam
            is_strong = "BELI KUAT" in res["action"]
            send_message(msg, notify=is_strong)
            log(f"REAL-TIME CONFLUENCE ALERT TERKIRIM untuk {sym} ({res['confluence_label']})")
            
            # Masukkan ke list monitor TP/SL bot jika belum ada
            if sym not in _active_signals:
                _active_signals[sym] = {
                    'entry': res['price'], 'tp1': res['tp1'], 'tp2': res['tp2'], 'tp3': res['tp3'],
                    'sl': res['stop_loss'], 'hit': set(), 'time': datetime.now(WIB).isoformat(),
                }
                _daily_stats['signals_sent'] += 1
                record_bot_learning_signal(res, pair, source="realtime")
            
            # Catat ke cache agar tidak spam
            _confluence_sent_symbols[sym] = {
                "sent_at": now_ts,
                "price": res["price"],
            }

            sent += 1
            if sent >= CONFLUENCE_MAX_ALERTS_PER_CYCLE:
                break
        except Exception as e:
            log(f"Gagal memproses real-time alert untuk {sym}: {e}")


# =============================================================================
# EARLY ENTRY (PRE-PUMP) DETECTION
# =============================================================================
# Tujuan: kasih alert lebih cepet di candle 15m sebelum pump 1H/4H ngeluarin
# konfirmasi. Pakai checklist sederhana yang fokus ke "early signs":
#   - EMA8 > EMA21 di 15m + slope EMA8 mulai naik
#   - RSI(14) bangun dari area oversold/netral (38..62) + naik vs candle lalu
#   - Volume spike: volume bar terakhir > 1.4x rata-rata 20 bar
#   - Bollinger Squeeze release: pct_b naik dari <0.4 menuju >0.5
#   - MACD histogram balik positif atau bullish cross di 15m
# Setup butuh minimal EARLY_MIN_SETUP_STRENGTH dari 5 checklist.
def detect_early_setup_15m(candles_15m):
    """Cari early entry di TF 15 menit. Return dict dengan checklist+score."""
    default = {
        "early_ok": False,
        "passed": 0,
        "checks": {},
        "rsi": None,
        "rsi_prev": None,
        "vol_ratio": 1.0,
        "macd_state": "netral",
        "ema_state": "neutral",
        "bb_pct_b": 0.5,
        "bb_pct_b_prev": 0.5,
        "trigger": "NO DATA",
    }
    if candles_15m is None or candles_15m.empty or len(candles_15m) < 30:
        return default

    close = candles_15m["close"].astype(float)
    vol = candles_15m["volume"].astype(float)

    # EMA cross + slope
    ema8 = compute_ema(close, 8)
    ema21 = compute_ema(close, 21)
    ema_cross_up = bool(ema8.iloc[-1] > ema21.iloc[-1])
    ema8_slope_up = bool(ema8.iloc[-1] > ema8.iloc[-3]) if len(ema8) >= 3 else False
    ema_state = "bullish" if ema_cross_up and ema8_slope_up else ("warming" if ema_cross_up else "bearish")
    ema_check = ema_cross_up and ema8_slope_up

    # RSI bangun
    rsi_now = compute_rsi(close) if len(close) >= 14 else 50
    rsi_prev = compute_rsi(close.iloc[:-1]) if len(close) >= 16 else rsi_now
    rsi_check = (38 <= rsi_now <= 68) and (rsi_now > rsi_prev + 1.5)

    # Volume spike (15m)
    avg_vol_20 = float(vol.tail(21).iloc[:-1].mean()) if len(vol) >= 21 else float(vol.tail(20).mean())
    last_vol = float(vol.iloc[-1])
    vol_ratio = (last_vol / avg_vol_20) if avg_vol_20 > 0 else 1.0
    vol_check = vol_ratio >= 1.4

    # MACD bullish-ish
    macd_state, macd_hist = compute_macd(close)
    macd_check = macd_state in ("bullish cross", "bullish") and macd_hist > 0

    # Bollinger squeeze release
    bb_now = compute_bollinger(close)
    bb_prev = compute_bollinger(close.iloc[:-1]) if len(close) >= 21 else bb_now
    pct_b_now = bb_now.get("bb_pct_b", 0.5)
    pct_b_prev = bb_prev.get("bb_pct_b", pct_b_now)
    bb_check = pct_b_prev < 0.4 and pct_b_now >= 0.5

    checks = {
        "EMA8>EMA21 + slope naik": ema_check,
        "RSI bangun (38-68 & naik)": rsi_check,
        "Volume 1.4x MA20 (15m)": vol_check,
        "MACD bullish (15m)": macd_check,
        "BB squeeze release": bb_check,
    }
    passed = sum(1 for v in checks.values() if v)

    # Trigger label utk pesan
    triggers = []
    if ema_check: triggers.append("EMA up")
    if rsi_check: triggers.append(f"RSI {rsi_prev:.0f}->{rsi_now:.0f}")
    if vol_check: triggers.append(f"Vol {vol_ratio:.1f}x")
    if macd_check: triggers.append("MACD+")
    if bb_check: triggers.append("BB release")
    trigger_label = " | ".join(triggers) if triggers else "no trigger"

    return {
        "early_ok": passed >= EARLY_MIN_SETUP_STRENGTH,
        "passed": passed,
        "checks": checks,
        "rsi": round(rsi_now, 1),
        "rsi_prev": round(rsi_prev, 1),
        "vol_ratio": round(vol_ratio, 2),
        "macd_state": macd_state,
        "ema_state": ema_state,
        "bb_pct_b": round(pct_b_now, 2),
        "bb_pct_b_prev": round(pct_b_prev, 2),
        "trigger": trigger_label,
    }


def check_early_entry_alerts(all_coins):
    """Scan candle 15m utk deteksi setup pre-pump. Lebih cepat dari 1H confluence."""
    if not ENABLE_EARLY_ALERTS:
        return

    global _early_sent_symbols
    now_ts = time.time()
    sent = 0

    # Bersihin cache
    _early_sent_symbols = {
        k: v for k, v in _early_sent_symbols.items()
        if now_ts - v.get("sent_at", 0) < EARLY_SYMBOL_COOLDOWN_SEC
    }

    for sym, pair in MAIN_ASSETS.items():
        if sym not in all_coins:
            continue
        if sym in _early_sent_symbols:
            continue
        # Kalau symbol udah keluar di confluence alert, skip biar tidak dobel
        if sym in _confluence_sent_symbols:
            continue

        try:
            ticker = all_coins[sym]

            # Filter dasar dari ticker dulu (cepat, tanpa fetch candle)
            if ticker["vol_idr"] < EARLY_MIN_VOLUME_IDR:
                continue
            high_24h = ticker.get("high", 0)
            low_24h = ticker.get("low", 0)
            range_w = high_24h - low_24h
            range_pos = ((ticker["price"] - low_24h) / range_w * 100) if range_w > 0 else 50
            if range_pos > EARLY_MAX_RANGE_POS:
                continue  # udah terlalu deket puncak, bukan early
            if ticker["change"] > 8:
                continue  # udah pump ngegas, ini ranah FOMO/Confluence

            # Fetch 15m candles
            candles_15m = fetch_candles(pair, tf="15", lookback_days=5)
            time.sleep(0.25)
            setup = detect_early_setup_15m(candles_15m)
            if not setup["early_ok"]:
                continue

            # Konfirmasi dengan analisa 1H supaya nggak nge-fire di downtrend yg dalem
            candles_1h = fetch_candles(pair, tf="60")
            time.sleep(0.25)
            if candles_1h.empty:
                continue
            res = apply_bot_intelligence(analyze_coin(sym, ticker, candles_1h))

            # Filter konteks 1H: minimal score early & jangan kontra trend bearish
            if res["score"] < EARLY_MIN_SCORE:
                continue
            if res["mtf_adjustment"] <= -5:
                continue  # 4H/1D kompak bearish, skip
            if res["risk_level"] == "TINGGI":
                continue
            if res["adx_trend"] in ("bearish_strong",):
                continue

            # Susun alert
            pair_url = pair.upper().replace("_", "")
            link = f"https://indodax.com/market/{pair_url}?ref={INDODAX_REF}"
            ch_sign = "+" if res["change"] >= 0 else ""

            # Suggested entry zone: harga sekarang ± 0.4%
            entry_lo = res["price"] * 0.996
            entry_hi = res["price"] * 1.004
            # Early SL agak lebih ketat krn entry awal: 2.5% di bawah harga
            early_sl = res["price"] * 0.975
            # Early TP1/TP2: 1.8% & 3.5%
            early_tp1 = res["price"] * 1.018
            early_tp2 = res["price"] * 1.035

            checks_text = "\n".join(
                f"   {'🟢' if ok else '⚪'} {name}"
                for name, ok in setup["checks"].items()
            )

            msg = (
                f"⚡ *EARLY ENTRY -- PRE-PUMP SETUP* ⚡\n"
                f"🚀 *{sym}* — Setup {setup['passed']}/5 (15m)\n"
                f"──────────────────────\n"
                f"💵 Harga: {format_idr(res['price'])} ({ch_sign}{res['change']:.2f}%)\n"
                f"🧭 Range 24h: {res['range_pos']:.0f}% (paruh bawah)\n"
                f"📍 Trigger: _{setup['trigger']}_\n"
                f"📊 RSI 15m: {setup['rsi_prev']} → *{setup['rsi']}* | Vol 15m: *{setup['vol_ratio']}x*\n"
                f"📈 EMA 15m: {setup['ema_state']} | MACD 15m: {setup['macd_state']}\n"
                f"🛡️ Konteks 1H: Score *{res['score']}/100* | {res['action']}\n"
                f"🧠 ML: {res['ml_label']} ({res['ml_prob']}%) | MTF: {res['mtf_label']}\n\n"
                f"✅ *Checklist Setup 15m:*\n"
                f"{checks_text}\n\n"
                f"🎯 Entry zone: {format_idr(entry_lo)} – {format_idr(entry_hi)}\n"
                f"🎯 TP1 / TP2: {format_idr(early_tp1)} / {format_idr(early_tp2)}\n"
                f"🛑 SL ketat (early): {format_idr(early_sl)} (-2.5%)\n"
                f"💰 Saran size: kecil dulu (1-3% modal), tambah saat konfirmasi 1H\n\n"
                f"[⚡ MASUK DI INDODAX]({link})\n"
                f"──────────────────────\n"
                f"⚠️ *Early signal = lebih cepat tapi lebih rawan false-break.* "
                f"Pakai SL ketat & ukuran kecil. DYOR.\n"
                f"💎 *Gabung Premium:* {TELEGRAM_CHANNEL}"
            )

            # Notifikasi getar utk early karena ini intinya kecepatan
            send_message(msg, notify=True)
            log(f"EARLY ENTRY ALERT terkirim untuk {sym} (setup {setup['passed']}/5, score 1H {res['score']})")

            _early_sent_symbols[sym] = {
                "sent_at": now_ts,
                "price": res["price"],
                "passed": setup["passed"],
            }

            sent += 1
            if sent >= EARLY_MAX_ALERTS_PER_CYCLE:
                break
        except Exception as e:
            log(f"Gagal early-entry scan utk {sym}: {e}")


def should_send_sinyal():
    global _last_sinyal_date
    now = datetime.now(WIB)
    today = now.strftime("%Y-%m-%d")
    # Window diperluas dari 8-9 ke 7-12 WIB supaya ada retry kalau gagal
    return 7 <= now.hour <= 12 and _last_sinyal_date != today



# =============================================================================
# TP/SL PRICE MONITOR
# =============================================================================
def check_tp_sl_alerts(all_coins):
    """Cek apakah harga sudah kena TP1/TP2/TP3 atau SL dari sinyal aktif."""
    global _active_signals, _daily_stats
    to_remove = []
    for sym, sig in _active_signals.items():
        if sym not in all_coins:
            continue

        # Clean old signal tracking if it exceeds ACTIVE_SIGNAL_TTL_SEC
        now_ts = time.time()
        _sig_dt = datetime.fromisoformat(sig["time"])
        if _sig_dt.tzinfo is None:
            _sig_dt = _sig_dt.replace(tzinfo=WIB)
        created_ts = _sig_dt.timestamp()
        if now_ts - created_ts > ACTIVE_SIGNAL_TTL_SEC:
            to_remove.append(sym)
            continue

        price = all_coins[sym]["price"]
        entry = sig["entry"]
        pnl_pct = (price - entry) / entry * 100

        if price <= sig["sl"] and "SL" not in sig["hit"]:
            sig["hit"].add("SL")
            _daily_stats["sl_hit"] += 1
            send_message(f"*STOP LOSS HIT*\n{sym} kena SL di {format_idr(price)}\nEntry: {format_idr(entry)} | PnL: {pnl_pct:+.2f}%\nPotong rugi, disiplin!", notify=True, force=True)
            to_remove.append(sym)
            continue

        if price >= sig["tp3"] and "TP3" not in sig["hit"]:
            sig["hit"].add("TP3")
            _daily_stats["tp_hit"] += 1
            send_message(f"*TARGET HIT - TP3*\n{sym} capai TP3 di {format_idr(price)}\nEntry: {format_idr(entry)} | PnL: {pnl_pct:+.2f}%\nSelamat! Take profit semua.", notify=True, force=True)
            to_remove.append(sym)
        elif price >= sig["tp2"] and "TP2" not in sig["hit"]:
            sig["hit"].add("TP2")
            _daily_stats["tp_hit"] += 1
            send_message(f"*TARGET HIT - TP2*\n{sym} capai TP2 di {format_idr(price)}\nEntry: {format_idr(entry)} | PnL: {pnl_pct:+.2f}%\nJual 30%, sisanya trailing.", notify=True, force=True)
        elif price >= sig["tp1"] and "TP1" not in sig["hit"]:
            sig["hit"].add("TP1")
            _daily_stats["tp_hit"] += 1
            send_message(f"*TARGET HIT - TP1*\n{sym} capai TP1 di {format_idr(price)}\nEntry: {format_idr(entry)} | PnL: {pnl_pct:+.2f}%\nJual 30%, pantau TP2.", notify=True, force=True)

    for sym in to_remove:
        del _active_signals[sym]


# =============================================================================
# DAILY SUMMARY (jam 21:00 WIB)
# =============================================================================
def send_daily_summary():
    global _last_summary_date, _daily_stats
    now = datetime.now(WIB)
    today = now.strftime("%Y-%m-%d")
    if now.hour != 21 or _last_summary_date == today:
        return
    _last_summary_date = today
    active = len(_active_signals)
    lines = [
        "*RINGKASAN HARI INI*",
        f"{now.strftime('%d %B %Y')}",
        "------",
        f"Sinyal beli dikirim: {_daily_stats['signals_sent']}",
        f"Target tercapai (TP): {_daily_stats['tp_hit']}",
        f"Stop loss kena (SL): {_daily_stats['sl_hit']}",
        f"Posisi masih aktif: {active}",
        "------",
    ]
    if _daily_stats['tp_hit'] > _daily_stats['sl_hit']:
        lines.append("Hari yang bagus! Lebih banyak TP daripada SL.")
    elif _daily_stats['sl_hit'] > 0:
        lines.append("Ada SL hari ini. Evaluasi dan jangan balas dendam.")
    else:
        lines.append("Market tenang hari ini. Sabar menunggu setup.")
    lines.append(f"Gabung: {TELEGRAM_CHANNEL}")
    send_message("\n".join(lines), notify=False)
    _daily_stats = {"tp_hit": 0, "sl_hit": 0, "signals_sent": 0}
    log("Daily summary terkirim")


# =============================================================================
# TELEGRAM COMMAND HANDLER
# =============================================================================
def _get_last_update_id():
    """Simpan last_update_id di file supaya tidak baca pesan lama berulang."""
    path = "last_update_id.txt"
    if os.path.exists(path):
        try:
            with open(path, "r") as f:
                return int(f.read().strip())
        except:
            pass
    return 0


def _save_last_update_id(uid):
    with open("last_update_id.txt", "w") as f:
        f.write(str(uid))


def _format_idr(value):
    if value is None or value == 0:
        return "-"
    if value >= 1_000_000_000:
        return f"Rp{value/1_000_000_000:.2f}M"
    if value >= 1_000_000:
        return f"Rp{value/1_000_000:.1f}JT"
    if value >= 1_000:
        return f"Rp{value:,.0f}"
    return f"Rp{value:,.2f}"


def handle_telegram_command(update_data):
    """Handle incoming Telegram commands. Returns True if a command was processed."""
    global _message_fingerprints

    if not update_data or not BOT_TOKEN or not CHAT_ID:
        return False

    # Extract message
    message = None
    if "message" in update_data:
        message = update_data["message"]
    elif "callback_query" in update_data:
        # Handle inline query (button clicks)
        message = update_data["callback_query"].get("message")
        if not message:
            return False

    if not message:
        return False

    # Check if message is from our chat
    msg_chat_id = str(message.get("chat", {}).get("id", ""))
    if str(msg_chat_id) != str(CHAT_ID):
        return False

    # Update last update id
    uid = message.get("message_id", 0)
    _save_last_update_id(uid)

    # Get text/command
    text = message.get("text", "").strip()
    if not text.startswith("/"):
        return False

    parts = text.split()
    cmd = parts[0].lower()
    args = parts[1:] if len(parts) > 1 else []

    # Check for duplicate messages (avoid re-processing on restart)
    now_ts = time.time()
    msg_key = f"{msg_chat_id}:{uid}"
    if msg_key in _message_fingerprints:
        if now_ts - _message_fingerprints[msg_key] < 30:  # 30s dedupe
            return False
    _message_fingerprints[msg_key] = now_ts

    # === /help ===
    if cmd == "/help":
        help_text = (
            f"*⚙️ DAFTAR COMMAND TELEGRAM*\n"
            f"──────────────────────\n"
            f"📊 */scan* — Scan semua koin utama sekarang\n"
            f"🎯 */top* — Lihat 5 koin terbaik saat ini\n"
            f"💼 */portfolio* — Cek posisi terbuka + P/L\n"
            f"📜 */journal* — Riwayat sinyal + winrate\n"
            f"📈 */stats* — Statistik performa bot\n"
            f"🔔 */alert on/off* — Aktifkan/nonaktifkan alert\n"
            f"🌤 */weather* — Cek market mode saat ini\n"
            f"──────────────────────\n"
            f"💡 Bot juga otomatis push sinyal:\n"
            f"• 08:00 WIB — Sinyal harian\n"
            f"• Setiap 60s — Early entry + confluence\n"
            f"• Realtime — TP/SL alert\n"
            f"• 21:00 WIB — Daily summary"
        )
        send_message(help_text, notify=True)
        return True

    # === /scan ===
    if cmd == "/scan":
        send_message("⏳ *Memulai scan...*_", notify=False)
        try:
            all_coins = fetch_all_tickers()
            if not all_coins:
                send_message("❌ Gagal fetch data dari Indodax.", notify=True)
                return True

            # Scan main assets
            signals = []
            for sym, pair in MAIN_ASSETS.items():
                if sym not in all_coins:
                    continue
                candles = fetch_candles(pair)
                time.sleep(0.3)
                res = apply_bot_intelligence(analyze_coin(sym, all_coins[sym], candles))
                signals.append(res)

            if not signals:
                send_message("❌ Tidak ada sinyal.", notify=True)
                return True

            # Sort: BELI KUAT > CICIL BELI > WATCH > JANGAN BELI > HINDARI
            priority = {"BELI KUAT": 0, "CICIL BELI": 1, "WATCH": 2, "JANGAN BELI": 3, "HINDARI": 4}
            signals.sort(key=lambda x: priority.get(x["action"], 5))

            # Format response
            mode, _ = detect_market_mode(all_coins)
            mode_emoji = {"agresif": "🟢", "normal": "🟡", "defensif": "🔴"}[mode]

            lines = [
                f"*📊 HASIL SCAN — {mode_emoji} {mode.upper()}*",
                f"{datetime.now(WIB).strftime('%d/%m %H:%M WIB')}",
                "──────────────────────",
                "",
            ]

            buy_count = 0
            for s in signals[:8]:  # Max 8 koin
                ch = f"+{s['change']:.2f}" if s["change"] >= 0 else f"{s['change']:.2f}"
                lines.append(f"{s['emoji']} *{s['symbol']}* -- {s['action']}")
                lines.append(f"   💰 {format_idr(s['price'])} ({ch}%) | Score: {s['score']}/100")
                lines.append(f"   📊 RSI: {s['rsi']} | MACD: {s['macd_signal']} | ST: {s['supertrend']}")
                lines.append(f"   🧠 ML: {s['ml_label']} ({s['ml_prob']}%) | MTF: {s['mtf_label']}")

                if is_entry_action(s["action"]):
                    buy_count += 1
                    lines.append(f"   🎯 TP1: {format_idr(s['tp1'])} | SL: {format_idr(s['stop_loss'])}")
                    lines.append(f"   💰 Alokasi: {s['alloc_pct']}%")
                lines.append("")

            lines.append("──────────────────────")
            lines.append(f"*{buy_count} koin layak beli* dari {len(signals)} koin")
            lines.append(f"⚠️ Bukan saran keuangan. DYOR.")

            send_message("\n".join(lines), notify=True)
            log(f"/scan command executed — {buy_count} buy signals found")

        except Exception as e:
            log(f"Error /scan: {e}")
            send_message(f"❌ Error scan: {str(e)[:100]}", notify=True)
        return True

    # === /top ===
    if cmd == "/top":
        try:
            all_coins = fetch_all_tickers()
            if not all_coins:
                send_message("❌ Gagal fetch data.", notify=True)
                return True

            signals = []
            for sym, pair in MAIN_ASSETS.items():
                if sym not in all_coins:
                    continue
                candles = fetch_candles(pair)
                time.sleep(0.3)
                res = apply_bot_intelligence(analyze_coin(sym, all_coins[sym], candles))
                signals.append(res)

            if not signals:
                send_message("❌ Tidak ada data.", notify=True)
                return True

            # Sort by score descending
            signals.sort(key=lambda x: x["score"], reverse=True)
            top5 = signals[:5]

            lines = [
                "*🎯 TOP 5 COIN TERBAIK*",
                f"{datetime.now(WIB).strftime('%d/%m %H:%M WIB')}",
                "──────────────────────",
                "",
            ]

            for i, s in enumerate(top5, 1):
                ch = f"+{s['change']:.2f}" if s["change"] >= 0 else f"{s['change']:.2f}"
                lines.append(f"*{i}. {s['emoji']} {s['symbol']}*")
                lines.append(f"   Score: {s['score']}/100 | Action: {s['action']}")
                lines.append(f"   Harga: {format_idr(s['price'])} ({ch}%)")
                lines.append(f"   RSI: {s['rsi']} | MACD: {s['macd_signal']}")
                lines.append(f"   ML: {s['ml_label']} ({s['ml_prob']}%) | MTF: {s['mtf_label']}")
                lines.append(f"   Confluence: {s['confluence_label']}")

                if is_entry_action(s["action"]):
                    lines.append(f"   🎯 Entry → TP1: {format_idr(s['tp1'])} | TP2: {format_idr(s['tp2'])} | SL: {format_idr(s['stop_loss'])}")
                    lines.append(f"   💰 Alokasi: {s['alloc_pct']}%")
                lines.append("")

            lines.append("──────────────────────")
            lines.append("⚠️ Bukan saran keuangan. DYOR.")

            send_message("\n".join(lines), notify=True)
            log(f"/top command executed")

        except Exception as e:
            log(f"Error /top: {e}")
            send_message(f"❌ Error: {str(e)[:100]}", notify=True)
        return True

    # === /portfolio ===
    if cmd == "/portfolio":
        try:
            # Check active signals as proxy for portfolio
            if not _active_signals:
                send_message(
                    "💼 *PORTFOLIO*\n\nTidak ada posisi terbuka saat ini.\n\n"
                    "💡 Tips: Buka /scan untuk cari entry baru.",
                    notify=True
                )
                return True

            lines = [
                "💼 *PORTFOLIO TERBUKA*",
                f"{datetime.now(WIB).strftime('%d/%m %H:%M WIB')}",
                "──────────────────────",
                "",
            ]

            total_pnl = 0
            all_coins = fetch_all_tickers()

            for sym, sig in _active_signals.items():
                if sym not in all_coins:
                    continue
                price = all_coins[sym]["price"]
                entry = sig["entry"]
                pnl = (price - entry) / entry * 100
                total_pnl += pnl

                emoji = "🟢" if pnl >= 0 else "🔴"
                hit_status = ", ".join(sig.get("hit", [])) if sig.get("hit") else "Aktif"

                lines.append(f"{emoji} *{sym}*")
                lines.append(f"   Entry: {format_idr(entry)} → Sekarang: {format_idr(price)}")
                lines.append(f"   P/L: {pnl:+.2f}% | Status: {hit_status}")

                if "TP1" in sig.get("hit", []):
                    lines.append(f"   ✅ TP1 TERCAPAI!")
                if "TP2" in sig.get("hit", []):
                    lines.append(f"   ✅ TP2 TERCAPAI!")
                if "TP3" in sig.get("hit", []):
                    lines.append(f"   ✅ TP3 TERCAPAI!")
                if "SL" in sig.get("hit", []):
                    lines.append(f"   🛑 STOP LOSS KENA")
                lines.append("")

            lines.append("──────────────────────")
            lines.append(f"Total P/L: {total_pnl:+.2f}%")
            lines.append(f"Posisi aktif: {len(_active_signals)}")
            lines.append("")
            lines.append("📌 Monitor: bot akan notif otomatis saat TP/SL kena.")

            send_message("\n".join(lines), notify=True)
            log(f"/portfolio command executed — {len(_active_signals)} active positions")

        except Exception as e:
            log(f"Error /portfolio: {e}")
            send_message(f"❌ Error: {str(e)[:100]}", notify=True)
        return True

    # === /journal ===
    if cmd == "/journal":
        try:
            from learning_engine import build_profile
            profile = build_profile()

            lines = [
                "📜 *RIWAYAT SINYAL*",
                f"{datetime.now(WIB).strftime('%d/%m %Y')}",
                "──────────────────────",
                "",
            ]

            total = profile.get("closed", 0)
            wins = profile.get("wins", 0)
            losses = profile.get("losses", 0)
            wr = profile.get("winrate", 0)

            lines.append(f"Total sinyal: {profile.get('total_signals', 0)}")
            lines.append(f"Selesai: {total} | Win: {wins} | Loss: {losses}")
            lines.append(f"*Winrate: {wr:.1f}%*")
            lines.append("")

            # Best symbols
            best = profile.get("best_symbols", [])
            if best:
                lines.append("*Top Performer:*\n")
                for sym, stats in best:
                    lines.append(f"🏆 {sym}: {stats.get('winrate', 0):.1f}% WR ({stats.get('closed', 0)} trades)")
                lines.append("")

            # Active signals
            active = profile.get("active", 0)
            if active > 0:
                lines.append(f"Posisi aktif: {active}")

            lines.append("")
            lines.append("──────────────────────")
            lines.append("📊 Data dari semua sinyal yang tercatat.")
            lines.append("⚠️ Bukan saran keuangan. DYOR.")

            send_message("\n".join(lines), notify=True)
            log(f"/journal command executed — WR: {wr:.1f}%")

        except Exception as e:
            log(f"Error /journal: {e}")
            send_message(f"❌ Error: {str(e)[:100]}", notify=True)
        return True

    # === /stats ===
    if cmd == "/stats":
        try:
            from learning_engine import build_profile
            profile = build_profile()

            total = profile.get("closed", 0)
            wr = profile.get("winrate", 0)

            lines = [
                "📈 *STATISTIK BOT*",
                f"{datetime.now(WIB).strftime('%d/%m %Y')}",
                "──────────────────────",
                "",
            ]

            lines.append(f"Total sinyal tercatat: {profile.get('total_signals', 0)}")
            lines.append(f"Trade selesai: {total}")
            lines.append(f"Win: {profile.get('wins', 0)} | Loss: {profile.get('losses', 0)}")
            lines.append(f"*Winrate: {wr:.1f}%*")
            lines.append("")

            # Daily stats
            lines.append("*Hari Ini:*\n")
            lines.append(f"  Sinyal dikirim: {_daily_stats['signals_sent']}")
            lines.append(f"  TP hit: {_daily_stats['tp_hit']}")
            lines.append(f"  SL hit: {_daily_stats['sl_hit']}")
            lines.append(f"  Posisi aktif: {len(_active_signals)}")
            lines.append("")

            # Best symbols
            best = profile.get("best_symbols", [])
            if best:
                lines.append("*Top Performer:*\n")
                for sym, stats in best:
                    lines.append(f"  🏆 {sym}: {stats.get('winrate', 0):.1f}% WR ({stats.get('closed', 0)} trades)")
                lines.append("")

            lines.append("──────────────────────")
            lines.append("🤖 Bot belajar otomatis dari setiap trade.")
            lines.append("💡 Semakin banyak data, semakin akurat.")

            send_message("\n".join(lines), notify=True)
            log(f"/stats command executed")

        except Exception as e:
            log(f"Error /stats: {e}")
            send_message(f"❌ Error: {str(e)[:100]}", notify=True)
        return True

    # === /alert on/off ===
    if cmd == "/alert":
        if not args or args[0] not in ("on", "off"):
            send_message(
                "🔔 *ALERT SETTINGS*\n\n"
                "Gunakan:\n"
                "*/alert on* — Aktifkan semua alert\n"
                "*/alert off* — Nonaktifkan semua alert",
                notify=True
            )
            return True

        if args[0] == "on":
            global ENABLE_FOMO_ALERTS, ENABLE_CONFLUENCE_ALERTS, ENABLE_EARLY_ALERTS
            ENABLE_FOMO_ALERTS = True
            ENABLE_CONFLUENCE_ALERTS = True
            ENABLE_EARLY_ALERTS = True
            send_message("🔔 *Alert AKTIF* — Semua notifikasi on.", notify=True)
        else:
            ENABLE_FOMO_ALERTS = False
            ENABLE_CONFLUENCE_ALERTS = False
            ENABLE_EARLY_ALERTS = False
            send_message("🔕 *Alert NONAKTIF* — Semua notifikasi off.", notify=True)
        return True

    # === /weather (market mode) ===
    if cmd == "/weather":
        try:
            all_coins = fetch_all_tickers()
            if not all_coins:
                send_message("❌ Gagal fetch data.", notify=True)
                return True

            mode, mode_desc = detect_market_mode(all_coins)
            mode_emoji = {"agresif": "🟢 AGRESIF", "normal": "🟡 NORMAL", "defensif": "🔴 DEFENSIF"}[mode]

            changes = [c["change"] for c in all_coins.values() if c["vol_idr"] >= 100_000_000]
            green = sum(1 for c in changes if c > 0)
            pct_green = green / len(changes) * 100 if changes else 0
            avg_change = sum(changes) / len(changes) if changes else 0

            lines = [
                f"🌤 *OUTLOOK PASAR*",
                f"{datetime.now(WIB).strftime('%d/%m %H:%M WIB')}",
                "──────────────────────",
                "",
                f"Mode: *{mode_emoji}*",
                f"Koin hijau: *{pct_green:.0f}%*",
                f"Rata-rata change: *{avg_change:+.2f}%*",
                "",
            ]

            # Top movers
            sorted_coins = sorted(all_coins.values(), key=lambda x: x["change"], reverse=True)[:5]
            if sorted_coins:
                lines.append("*Top Gainer:*\n")
                for c in sorted_coins:
                    lines.append(f"  📈 {c['symbol']}: +{c['change']:.1f}%")
                lines.append("")

                bottom = sorted(all_coins.values(), key=lambda x: x["change"])[:5]
                lines.append("*Top Loser:*\n")
                for c in bottom:
                    lines.append(f"  📉 {c['symbol']}: {c['change']:.1f}%")
                lines.append("")

            lines.append("──────────────────────")
            lines.append(f"Total koin: {len(all_coins)}")

            send_message("\n".join(lines), notify=True)
            log(f"/weather command executed — mode: {mode}")

        except Exception as e:
            log(f"Error /weather: {e}")
            send_message(f"❌ Error: {str(e)[:100]}", notify=True)
        return True

    return False


# =============================================================================
# TELEGRAM COMMAND POLLING
# =============================================================================
def poll_telegram_commands():
    """Ambil pesan command terbaru via getUpdates lalu proses (/scan, /top, dst)."""
    global _last_update_offset
    if not BOT_TOKEN or not CHAT_ID:
        return
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates"
    params = {"timeout": 0, "offset": _last_update_offset + 1 if _last_update_offset else None}
    try:
        resp = requests.get(url, params=params, timeout=15)
        data = resp.json()
    except Exception as e:
        log(f"poll getUpdates error: {e}")
        return
    if not data.get("ok"):
        return
    for update in data.get("result", []):
        _last_update_offset = max(_last_update_offset, update.get("update_id", 0))
        try:
            handle_telegram_command(update)
        except Exception as e:
            log(f"handle command error: {e}")


_last_update_offset = 0


# =============================================================================
# MAIN DAEMON LOOP
# =============================================================================
if __name__ == "__main__":
    if os.environ.get("RUN_KEEP_ALIVE") == "true":
        keep_alive()

    log("BOT DAEMON ULTRA SMART -- 24/7")
    log("   Sinyal harian: 08:00 WIB (1H multi-indikator)")
    log(f"   Loop scan: setiap {LOOP_SLEEP_SECONDS}s")
    log("   Early entry (15m pre-pump): tiap loop")
    log("   Confluence 1H + FOMO + TP/SL: tiap loop")
    log("   Daily summary: 21:00 WIB")
    log(f"   Channel: {TELEGRAM_CHANNEL}")
    log("=" * 40)
    if not BOT_TOKEN or not CHAT_ID:
        log("CRITICAL: TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID belum diset!")
        log(f"  BOT_TOKEN: {'OK (' + BOT_TOKEN[:8] + '...)' if BOT_TOKEN else 'KOSONG'}")
        log(f"  CHAT_ID: {'OK (' + str(CHAT_ID) + ')' if CHAT_ID else 'KOSONG'}")
        log("  Cek environment variables ATAU .streamlit/secrets.toml")
    else:
        log(f"  BOT_TOKEN: OK ({BOT_TOKEN[:8]}...)")
        log(f"  CHAT_ID: OK ({CHAT_ID})")

    # Load previously saved bot state to avoid duplicate alerts and preserve active trades
    load_bot_state()

    consecutive_errors = 0
    cycle_count = 0

    while True:
        try:
            cycle_count += 1
            all_coins = fetch_all_tickers()

            if not all_coins:
                consecutive_errors += 1
                wait = min(30, consecutive_errors * 5)
                log(f"Fetch gagal ({consecutive_errors}x). Retry in {wait}s...")
                time.sleep(wait)
                continue

            consecutive_errors = 0
            coin_count = len(all_coins)
            now = datetime.now(WIB)
            learning_profile = train_from_prices(all_coins)
            news_profile = get_bot_news_profile()

            if cycle_count % 10 == 1:
                wr = learning_profile.get("winrate")
                wr_text = f"{wr:.1f}%" if wr is not None else "belum ada"
                log(f"Heartbeat -- {coin_count} koin | {now.strftime('%H:%M WIB')} | Learning WR: {wr_text} | News: {news_profile.get('global_label', 'NO DATA')}")

            # 0. Proses command Telegram masuk (/scan, /top, /portfolio, dst)
            poll_telegram_commands()

            # 1. Sinyal harian (jam 7-12 pagi)
            if should_send_sinyal():
                send_sinyal_harian(all_coins)

            # 2. Early Entry (15m pre-pump) -- paling cepet, dijalanin duluan
            check_early_entry_alerts(all_coins)

            # 3. Real-time Confluence Alert (1H, sebagai konfirmasi)
            check_realtime_confluence_alerts(all_coins)

            # 4. FOMO detection (setiap siklus)
            check_fomo_and_alert(all_coins)

            # 5. TP/SL price monitor
            check_tp_sl_alerts(all_coins)

            # 6. Daily summary (jam 21:00 WIB)
            send_daily_summary()

            # Save state at the end of each successful cycle
            save_bot_state()

            time.sleep(LOOP_SLEEP_SECONDS)

        except KeyboardInterrupt:
            log("Shutdown by user.")
            break
        except Exception as e:
            consecutive_errors += 1
            log(f"Crash: {e} -- restarting in 10s...")
            time.sleep(10)
