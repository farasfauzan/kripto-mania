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
from datetime import datetime, timezone, timedelta
from keep_alive import keep_alive

# === CONFIG (env var > hardcoded fallback) ===
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "8947452796:AAEyKOPuOa_JmjDfTUTybhz5H3Puec_7yYs")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "-1003878919874")
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

# === STATE ===
_last_sinyal_date = None
_last_summary_date = None
_fomo_sent_symbols = {}
_confluence_sent_symbols = {}  # track real-time confluence alerts
_active_signals = {}  # track sinyal beli aktif untuk TP/SL monitor
_daily_stats = {"tp_hit": 0, "sl_hit": 0, "signals_sent": 0}


def log(msg):
    ts = datetime.now(WIB).strftime("%H:%M:%S")
    print(f"[{ts}] {msg}")


def clamp(value, lower, upper):
    return max(lower, min(upper, value))


def is_entry_action(action):
    """Check if action is a genuine entry signal (not 'JANGAN BELI')."""
    action = str(action or "").upper()
    return "BELI KUAT" in action or "CICIL BELI" in action


# =============================================================================
# DATA FETCHING
# =============================================================================
def fetch_all_tickers():
    """Satu fetch untuk semua data dari Indodax"""
    try:
        resp = requests.get("https://indodax.com/api/tickers", timeout=10)
        data = resp.json().get("tickers", {})
        all_coins = {}
        for pair, info in data.items():
            if not pair.endswith("_idr"):
                continue
            symbol = pair.replace("_idr", "").upper()
            all_coins[symbol] = {
                "symbol": symbol, "pair": pair,
                "price": float(info["last"]),
                "change": float(info.get("change", 0) or 0),
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
        - fomo_penalty
        - micin_penalty
    )
    score = int(clamp(round(base), 0, 100))

    # Action
    if score >= 80 and momentum > 1:
        action, emoji = "BELI KUAT", "🟢"
    elif score >= 65 and momentum > 0:
        action, emoji = "CICIL BELI", "🟡"
    elif score >= 50:
        action, emoji = "WATCH", "⚪"
    elif score >= 35:
        action, emoji = "JANGAN BELI", "🔴"
    else:
        action, emoji = "HINDARI", "⛔"

    # Confluence Gate: Entry hanya diperbolehkan jika minimal 4 dari 5 indikator valid
    if not confluence["allow_entry"]:
        if action in ("BELI KUAT", "CICIL BELI"):
            action = "WATCH" if confluence["confluence_passed"] >= 3 else "JANGAN BELI"
            emoji = "⚪" if confluence["confluence_passed"] >= 3 else "🔴"

    # Anti-FOMO Filter: Jangan asal masuk jika sudah terlalu dekat harga tertinggi 24h
    if range_pos > 85 and change > 5:
        if action in ("BELI KUAT", "CICIL BELI"):
            action = "WATCH"
            emoji = "⚪"

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


def send_message(text, notify=False):
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
        result = analyze_coin(sym, all_coins[sym], candles)
        signals.append(result)

    if not signals:
        log("Gagal ambil data untuk sinyal harian")
        return False

    # Sort: BELI KUAT > CICIL BELI > WATCH > JANGAN BELI > HINDARI
    priority = {"BELI KUAT": 0, "CICIL BELI": 1, "WATCH": 2, "JANGAN BELI": 3, "HINDARI": 4}
    signals.sort(key=lambda x: priority.get(x["action"], 5))

    # Format message
    now = datetime.now(WIB)
    lines = [
        f"*SINYAL CRYPTO HARI INI*",
        f"{now.strftime('%d %B %Y')} | Market: {mode_emoji}",
        f"_{mode_desc}_",
        "------",
        "",
    ]

    buy_count = sum(1 for s in signals if is_entry_action(s["action"]))

    for s in signals:
        pair_url = MAIN_ASSETS[s["symbol"]].upper().replace("_", "")
        link = f"https://indodax.com/market/{pair_url}?ref={INDODAX_REF}"
        ch = f"+{s['change']:.2f}" if s["change"] >= 0 else f"{s['change']:.2f}"

        lines.append(f"{s['emoji']} *{s['symbol']}* -- {s['action']} (Score: {s['score']}/100)")
        lines.append(f"   Harga: {format_idr(s['price'])} ({ch}%)")
        lines.append(f"   RSI: {s['rsi']} | EMA: {s['ema_bias']} | MACD: {s['macd_signal']}")
        lines.append(f"   Supertrend: {s['supertrend']} | BB: {s['bb_signal']}")
        lines.append(f"   ADX: {s['adx']} ({s['adx_trend']})")
        lines.append(f"   ML: {s['ml_label']} ({s['ml_prob']}%, {s['ml_conf']})")
        if s['bt_trades'] >= 6:
            lines.append(f"   Backtest: {s['bt_label']} (WR {s['bt_wr']}%, {s['bt_trades']} trades)")
        lines.append(f"   Risiko: {s['risk_level']} | Verdict: {s['verdict']} ({s['verdict_net']}/100)")

        if is_entry_action(s["action"]):
            lines.append(f"   TP1/TP2/TP3: {format_idr(s['tp1'])} / {format_idr(s['tp2'])} / {format_idr(s['tp3'])}")
            lines.append(f"   SL: {format_idr(s['stop_loss'])} | Trailing: {s['trailing_pct']}%")
            lines.append(f"   Alokasi: {s['alloc_pct']}% modal")
            lines.append(f"   [BELI DI INDODAX]({link})")
            # Track for TP/SL monitoring
            _active_signals[s['symbol']] = {
                'entry': s['price'], 'tp1': s['tp1'], 'tp2': s['tp2'], 'tp3': s['tp3'],
                'sl': s['stop_loss'], 'hit': set(), 'time': datetime.now(WIB).isoformat(),
            }
        else:
            lines.append(f"   [PANTAU DI INDODAX]({link})")
        lines.append("")

    lines.append("------")
    if mode == "defensif":
        lines.append("Market defensif. Kalau entry, 1 koin saja size kecil.")
    elif buy_count == 0:
        lines.append("Belum ada sinyal beli bersih. Simpan modal.")
    else:
        lines.append(f"{buy_count} koin layak beli. Pilih 1-2 terbaik, jangan serakah.")
    lines.append("Bukan saran keuangan. DYOR.")
    lines.append(f"Gabung: {TELEGRAM_CHANNEL}")

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
        # Cegah spam koin micin tak ber-volume: minimal 2 Miliar (kecuali Blue Chips)
        if vol < 2_000_000_000 and sym not in BLUE_CHIPS:
            continue
        item = {
            "symbol": sym, "pair": data["pair"],
            "price": data["price"], "change": round(change, 2),
            "vol_idr": vol, "high": data["high"], "low": data["low"],
        }
        if change > 15:
            fomo_gila.append(item)
        elif change > 8:
            fomo.append(item)
        elif change > 5:
            pumping.append(item)
    for lst in [fomo_gila, fomo, pumping]:
        lst.sort(key=lambda x: x["change"], reverse=True)
    return fomo_gila, fomo, pumping


def format_fomo_alert(fomo_gila, fomo, pumping, all_coins):
    if not fomo_gila and not fomo and not pumping:
        return None

    lines = ["*FOMO ALERT -- KOIN NAIK TAJAM!*", "------", ""]

    def _add_coins(lst, label):
        if not lst:
            return
        lines.append(f"*{label}:*")
        for coin in lst[:5]:
            pair_url = coin["pair"].upper().replace("_", "")
            link = f"https://indodax.com/market/{pair_url}?ref={INDODAX_REF}"

            # Quick RSI check untuk warning
            warning = ""
            rp = coin["high"] - coin["low"]
            if rp > 0:
                pos = (coin["price"] - coin["low"]) / rp * 100
                if pos > 90:
                    warning = " (DEKAT PUNCAK)"

            lines.append(f"   {coin['symbol']} -- *+{coin['change']}%*{warning}")
            lines.append(f"   {format_idr(coin['price'])} | Vol: {format_idr(coin['vol_idr'])}")
            lines.append(f"   [BELI]({link})")
            lines.append("")

    _add_coins(fomo_gila, "FOMO GILA (>15%)")
    _add_coins(fomo, "FOMO (>8%)")
    _add_coins(pumping, "PUMPING (>5%)")

    lines.append("------")
    lines.append("Hati-hati FOMO! Bisa koreksi kapan aja. DYOR.")
    lines.append(f"Gabung: {TELEGRAM_CHANNEL}")
    return "\n".join(lines)


def check_fomo_and_alert(all_coins):
    global _fomo_sent_symbols
    fomo_gila, fomo, pumping = detect_fomo(all_coins)
    total = len(fomo_gila) + len(fomo) + len(pumping)
    if total == 0:
        return

    now_ts = time.time()
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

    # Cooldown 12 jam (43200 detik) per koin
    _fomo_sent_symbols = {k: v for k, v in _fomo_sent_symbols.items() if now_ts - v.get("_sent_at", 0) < 43200}

    if not new_alerts:
        return

    new_gila = [v for v in new_alerts.values() if v["change"] > 15]
    new_fomo = [v for v in new_alerts.values() if 8 < v["change"] <= 15]
    new_pump = [v for v in new_alerts.values() if 5 < v["change"] <= 8]
    for lst in [new_gila, new_fomo, new_pump]:
        lst.sort(key=lambda x: x["change"], reverse=True)

    msg = format_fomo_alert(new_gila, new_fomo, new_pump, all_coins)
    if msg:
        send_message(msg, notify=True)
        log(f"FOMO ALERT terkirim! ({len(new_alerts)} koin)")
        for sym, coin in new_alerts.items():
            coin["_sent_at"] = now_ts
            _fomo_sent_symbols[sym] = coin


def check_realtime_confluence_alerts(all_coins):
    global _confluence_sent_symbols
    now_ts = time.time()

    # Bersihkan cache alert yang sudah lebih dari 12 jam (43200 detik)
    _confluence_sent_symbols = {k: v for k, v in _confluence_sent_symbols.items() if now_ts - v["sent_at"] < 43200}

    for sym, pair in MAIN_ASSETS.items():
        if sym not in all_coins:
            continue

        # Hindari spam: jika baru dikirim dalam 12 jam terakhir, lewati
        if sym in _confluence_sent_symbols:
            continue

        try:
            candles = fetch_candles(pair)
            time.sleep(0.3)  # rate limit safety
            if candles.empty:
                continue

            res = analyze_coin(sym, all_coins[sym], candles)
            
            # Cek apakah masuk kriteria 4/5 atau 5/5 dengan aksi BELI
            if is_entry_action(res["action"]) and res["confluence_passed"] >= 4:
                # Kirim alert instan!
                pair_url = pair.upper().replace("_", "")
                link = f"https://indodax.com/market/{pair_url}?ref={INDODAX_REF}"
                ch_sign = "+" if res["change"] >= 0 else ""
                
                # Buat daftar checklist confluence
                valid_checks = []
                for name, ok in res["confluence_checks"].items():
                    if ok:
                        valid_checks.append(f"   🟢 {name}: VALID")
                    else:
                        valid_checks.append(f"   🔴 {name}: TIDAK")
                valid_checks_text = "\n".join(valid_checks)

                msg = (
                    f"🚨 *SINYAL MASUK INSTAN (CONFLUENCE {res['confluence_passed']}/5)* 🚨\n"
                    f"🔥 *{sym}* — {res['action']} (Score: {res['score']}/100)\n"
                    f"──────────────────────\n"
                    f"💵 Harga: {format_idr(res['price'])} ({ch_sign}{res['change']:.2f}%)\n"
                    f"🛡️ Confluence: *{res['confluence_label']}* ({res['confluence_strength']})\n\n"
                    f"✅ *Status Gerbang Konfluensi:*\n"
                    f"{valid_checks_text}\n\n"
                    f"🧠 ML Forecast: *{res['ml_label']}* ({res['ml_prob']}%, {res['ml_conf']})\n"
                    f"📊 Backtest: *{res['bt_label']}* (WR {res['bt_wr']}%, {res['bt_trades']} trades)\n"
                    f"──────────────────────\n"
                    f"🎯 TP1 / TP2 / TP3: {format_idr(res['tp1'])} / {format_idr(res['tp2'])} / {format_idr(res['tp3'])}\n"
                    f"🛑 Stop Loss: {format_idr(res['stop_loss'])} | Trailing: {res['trailing_pct']}%\n"
                    f"💰 Alokasi Modal: *{res['alloc_pct']}%*\n\n"
                    f"[🔥 EKSEKUSI DI INDODAX]({link})\n"
                    f"──────────────────────\n"
                    f"⚠️ *Bukan saran keuangan. Selalu gunakan uang dingin (DYOR).* \n"
                    f"💎 *Gabung Premium:* {TELEGRAM_CHANNEL}"
                )
                
                send_message(msg, notify=True)
                log(f"REAL-TIME CONFLUENCE ALERT TERKIRIM untuk {sym} ({res['confluence_label']})")
                
                # Masukkan ke list monitor TP/SL bot jika belum ada
                if sym not in _active_signals:
                    _active_signals[sym] = {
                        'entry': res['price'], 'tp1': res['tp1'], 'tp2': res['tp2'], 'tp3': res['tp3'],
                        'sl': res['stop_loss'], 'hit': set(), 'time': datetime.now(WIB).isoformat(),
                    }
                    _daily_stats['signals_sent'] += 1
                
                # Catat ke cache agar tidak spam
                _confluence_sent_symbols[sym] = {
                    "sent_at": now_ts,
                    "price": res["price"],
                }
        except Exception as e:
            log(f"Gagal memproses real-time alert untuk {sym}: {e}")


def should_send_sinyal():
    global _last_sinyal_date
    now = datetime.now(WIB)
    today = now.strftime("%Y-%m-%d")
    return 8 <= now.hour <= 9 and _last_sinyal_date != today


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
        price = all_coins[sym]["price"]
        entry = sig["entry"]
        pnl_pct = (price - entry) / entry * 100

        if price <= sig["sl"] and "SL" not in sig["hit"]:
            sig["hit"].add("SL")
            _daily_stats["sl_hit"] += 1
            send_message(f"*STOP LOSS HIT*\n{sym} kena SL di {format_idr(price)}\nEntry: {format_idr(entry)} | PnL: {pnl_pct:+.2f}%\nPotong rugi, disiplin!", notify=True)
            to_remove.append(sym)
            continue

        if price >= sig["tp3"] and "TP3" not in sig["hit"]:
            sig["hit"].add("TP3")
            _daily_stats["tp_hit"] += 1
            send_message(f"*TARGET HIT - TP3*\n{sym} capai TP3 di {format_idr(price)}\nEntry: {format_idr(entry)} | PnL: {pnl_pct:+.2f}%\nSelamat! Take profit semua.", notify=True)
            to_remove.append(sym)
        elif price >= sig["tp2"] and "TP2" not in sig["hit"]:
            sig["hit"].add("TP2")
            _daily_stats["tp_hit"] += 1
            send_message(f"*TARGET HIT - TP2*\n{sym} capai TP2 di {format_idr(price)}\nEntry: {format_idr(entry)} | PnL: {pnl_pct:+.2f}%\nJual 30%, sisanya trailing.", notify=True)
        elif price >= sig["tp1"] and "TP1" not in sig["hit"]:
            sig["hit"].add("TP1")
            _daily_stats["tp_hit"] += 1
            send_message(f"*TARGET HIT - TP1*\n{sym} capai TP1 di {format_idr(price)}\nEntry: {format_idr(entry)} | PnL: {pnl_pct:+.2f}%\nJual 30%, pantau TP2.", notify=True)

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
# MAIN DAEMON LOOP
# =============================================================================
if __name__ == "__main__":
    if os.environ.get("RUN_KEEP_ALIVE") == "true":
        keep_alive()

    log("BOT DAEMON ULTRA SMART -- 24/7")
    log("   Sinyal: 08:00 WIB (RSI+EMA+MACD+BB+Supertrend+ADX+ML+Backtest)")
    log("   FOMO check: setiap 2 menit")
    log("   TP/SL monitor: setiap 2 menit")
    log("   Daily summary: 21:00 WIB")
    log(f"   Channel: {TELEGRAM_CHANNEL}")
    log("=" * 40)

    send_message("*Bot Radar ULTRA SMART Aktif (24/7)*\nRSI, EMA, MACD, Bollinger, Supertrend, ADX, ML/KNN, Backtest, Agentic Verdict", notify=False)

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

            if cycle_count % 10 == 1:
                log(f"Heartbeat -- {coin_count} koin | {now.strftime('%H:%M WIB')}")

            # 1. Sinyal harian (jam 8-9 pagi)
            if should_send_sinyal():
                send_sinyal_harian(all_coins)

            # 2. Real-time Confluence Alert 4/5+ (setiap siklus)
            check_realtime_confluence_alerts(all_coins)

            # 3. FOMO detection (setiap siklus)
            check_fomo_and_alert(all_coins)

            # 4. TP/SL price monitor
            check_tp_sl_alerts(all_coins)

            # 5. Daily summary (jam 21:00 WIB)
            send_daily_summary()

            time.sleep(120)

        except KeyboardInterrupt:
            log("Shutdown by user.")
            break
        except Exception as e:
            consecutive_errors += 1
            log(f"Crash: {e} -- restarting in 10s...")
            time.sleep(10)