"""
Intelligence Engine
===================
Lapisan cerdas tambahan di atas indikator teknikal dasar.

Fitur:
- Real swing-based Support/Resistance (bukan persentase hardcoded)
- Fibonacci retracement otomatis dari swing terdekat
- RSI divergence detection (bullish/bearish, regular & hidden)
- Candlestick pattern detection (engulfing, hammer, shooting star, doji)
- Choppiness Index untuk regime detection (trending vs ranging)
- VWAP rolling untuk acuan fair value
- Risk-adjusted score (normalisasi ke volatilitas via ATR%)
- Kelly Criterion allocation berdasarkan winrate historis
- Aggregate intelligence score ke adjustment & confidence label

Modul ini pure-pandas/numpy, tidak menambah dependency baru.
Semua fungsi defensif — kembalikan default aman jika data kurang.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd


# =============================================================================
# UTIL
# =============================================================================
def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        v = float(value)
        if math.isnan(v) or math.isinf(v):
            return default
        return v
    except (TypeError, ValueError):
        return default


# =============================================================================
# SWING-BASED SUPPORT / RESISTANCE
# =============================================================================
def _find_swing_points(highs: pd.Series, lows: pd.Series, lookback: int = 3) -> tuple[list[int], list[int]]:
    """Cari indeks swing high & swing low menggunakan window simetris.

    Sebuah candle dianggap swing high jika high-nya lebih tinggi dari
    `lookback` candle di kiri & kanan. Swing low kebalikannya.
    """
    swing_highs: list[int] = []
    swing_lows: list[int] = []
    n = len(highs)
    if n < (2 * lookback + 1):
        return swing_highs, swing_lows
    for i in range(lookback, n - lookback):
        h = highs.iloc[i]
        l = lows.iloc[i]
        left_h = highs.iloc[i - lookback : i]
        right_h = highs.iloc[i + 1 : i + 1 + lookback]
        left_l = lows.iloc[i - lookback : i]
        right_l = lows.iloc[i + 1 : i + 1 + lookback]
        if h >= left_h.max() and h >= right_h.max():
            swing_highs.append(i)
        if l <= left_l.min() and l <= right_l.min():
            swing_lows.append(i)
    return swing_highs, swing_lows


def compute_swing_levels(candles: pd.DataFrame, price: float, lookback: int = 3, max_levels: int = 3) -> dict:
    """Bangun support/resistance riil dari swing high/low terdekat.

    Returns:
        dict berisi support1/2 (di bawah harga), resistance1/2 (di atas harga),
        plus jarak ke level terdekat (%).
    """
    default = {
        "swing_support_1": None,
        "swing_support_2": None,
        "swing_resistance_1": None,
        "swing_resistance_2": None,
        "nearest_support_pct": None,
        "nearest_resistance_pct": None,
        "swing_quality": "DATA KURANG",
    }
    if candles is None or candles.empty or len(candles) < 30:
        return default
    try:
        high = candles["high"].astype(float)
        low = candles["low"].astype(float)
    except (KeyError, ValueError, TypeError):
        return default

    sh_idx, sl_idx = _find_swing_points(high, low, lookback=lookback)
    if not sh_idx and not sl_idx:
        return default

    swing_high_prices = sorted({float(high.iloc[i]) for i in sh_idx}, reverse=True)
    swing_low_prices = sorted({float(low.iloc[i]) for i in sl_idx})

    # Resistance = swing high yang masih di atas harga sekarang
    resistances = sorted([p for p in swing_high_prices if p > price])
    supports = sorted([p for p in swing_low_prices if p < price], reverse=True)

    r1 = resistances[0] if len(resistances) >= 1 else None
    r2 = resistances[1] if len(resistances) >= 2 else None
    s1 = supports[0] if len(supports) >= 1 else None
    s2 = supports[1] if len(supports) >= 2 else None

    nearest_sup_pct = ((price - s1) / price * 100) if s1 else None
    nearest_res_pct = ((r1 - price) / price * 100) if r1 else None

    swings_total = len(sh_idx) + len(sl_idx)
    if swings_total >= 8:
        quality = "KAYA"
    elif swings_total >= 4:
        quality = "CUKUP"
    else:
        quality = "TIPIS"

    return {
        "swing_support_1": s1,
        "swing_support_2": s2,
        "swing_resistance_1": r1,
        "swing_resistance_2": r2,
        "nearest_support_pct": round(nearest_sup_pct, 2) if nearest_sup_pct is not None else None,
        "nearest_resistance_pct": round(nearest_res_pct, 2) if nearest_res_pct is not None else None,
        "swing_quality": quality,
    }


# =============================================================================
# FIBONACCI RETRACEMENT
# =============================================================================
def compute_fibonacci_levels(candles: pd.DataFrame, lookback_bars: int = 120) -> dict:
    """Hitung Fibonacci retracement dari swing terakhir (high terendah → low tertinggi).

    Fokus pada level 0.382, 0.5, 0.618, 0.786 sebagai zona buy potensial saat retrace.
    """
    default = {
        "fib_low": None,
        "fib_high": None,
        "fib_382": None,
        "fib_500": None,
        "fib_618": None,
        "fib_786": None,
        "fib_zone": "NO DATA",
    }
    if candles is None or candles.empty or len(candles) < 30:
        return default
    try:
        recent = candles.tail(lookback_bars)
        high = recent["high"].astype(float).max()
        low = recent["low"].astype(float).min()
        last_price = float(recent["close"].astype(float).iloc[-1])
    except (KeyError, ValueError, TypeError):
        return default
    if high <= low:
        return default
    diff = high - low
    fib_382 = high - diff * 0.382
    fib_500 = high - diff * 0.5
    fib_618 = high - diff * 0.618
    fib_786 = high - diff * 0.786

    # Zona berdasarkan posisi harga
    if last_price >= high * 0.99:
        zone = "DI HIGH"
    elif last_price >= fib_382:
        zone = "ATAS 0.382"
    elif last_price >= fib_500:
        zone = "GOLDEN 0.5"
    elif last_price >= fib_618:
        zone = "GOLDEN 0.618"
    elif last_price >= fib_786:
        zone = "DEEP 0.786"
    else:
        zone = "DI LOW"

    return {
        "fib_low": low,
        "fib_high": high,
        "fib_382": fib_382,
        "fib_500": fib_500,
        "fib_618": fib_618,
        "fib_786": fib_786,
        "fib_zone": zone,
    }


# =============================================================================
# RSI DIVERGENCE
# =============================================================================
def _rsi_series(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / period, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / period, adjust=False).mean()
    rs = gain / loss.replace(0, np.nan)
    return (100 - (100 / (1 + rs))).fillna(50)


def detect_rsi_divergence(candles: pd.DataFrame, lookback: int = 60) -> dict:
    """Deteksi RSI divergence sederhana.

    - Bullish regular divergence: harga lower low, RSI higher low → potensi reversal naik
    - Bearish regular divergence: harga higher high, RSI lower high → potensi reversal turun
    """
    default = {"divergence": "NONE", "divergence_strength": 0}
    if candles is None or candles.empty or len(candles) < max(30, lookback):
        return default
    try:
        close = candles["close"].astype(float)
        high = candles["high"].astype(float)
        low = candles["low"].astype(float)
    except (KeyError, ValueError, TypeError):
        return default

    rsi = _rsi_series(close)
    window = candles.tail(lookback)
    if len(window) < 20:
        return default

    rsi_window = rsi.tail(lookback)
    high_window = high.tail(lookback)
    low_window = low.tail(lookback)

    # Cari 2 swing low harga terakhir (window 3 candle)
    sh_idx, sl_idx = _find_swing_points(high_window, low_window, lookback=3)
    if len(sl_idx) >= 2:
        last_low_idx = sl_idx[-1]
        prev_low_idx = sl_idx[-2]
        price_now = float(low_window.iloc[last_low_idx])
        price_prev = float(low_window.iloc[prev_low_idx])
        rsi_now = float(rsi_window.iloc[last_low_idx])
        rsi_prev = float(rsi_window.iloc[prev_low_idx])
        # Bullish regular: price LL + RSI HL
        if price_now < price_prev and rsi_now > rsi_prev and rsi_now < 45:
            strength = int(_clamp((rsi_now - rsi_prev) * 2 + (price_prev - price_now) / max(price_prev, 1) * 100, 1, 8))
            return {"divergence": "BULLISH", "divergence_strength": strength}

    if len(sh_idx) >= 2:
        last_high_idx = sh_idx[-1]
        prev_high_idx = sh_idx[-2]
        price_now = float(high_window.iloc[last_high_idx])
        price_prev = float(high_window.iloc[prev_high_idx])
        rsi_now = float(rsi_window.iloc[last_high_idx])
        rsi_prev = float(rsi_window.iloc[prev_high_idx])
        # Bearish regular: price HH + RSI LH
        if price_now > price_prev and rsi_now < rsi_prev and rsi_now > 55:
            strength = int(_clamp((rsi_prev - rsi_now) * 2 + (price_now - price_prev) / max(price_prev, 1) * 100, 1, 8))
            return {"divergence": "BEARISH", "divergence_strength": strength}

    return default


# =============================================================================
# CANDLESTICK PATTERNS
# =============================================================================
def detect_candlestick_patterns(candles: pd.DataFrame) -> dict:
    """Deteksi pola candle penting di candle terakhir yang sudah close.

    Returns label tunggal yang paling kuat + arah bias-nya.
    """
    default = {"candle_pattern": "NONE", "candle_bias": "neutral"}
    if candles is None or candles.empty or len(candles) < 4:
        return default
    try:
        # Candle terakhir yang sudah close
        recent = candles.iloc[:-1] if len(candles) > 4 else candles
        prev = recent.iloc[-2]
        last = recent.iloc[-1]
        o = float(last["open"])
        c = float(last["close"])
        h = float(last["high"])
        l = float(last["low"])
        po = float(prev["open"])
        pc = float(prev["close"])
    except (KeyError, ValueError, TypeError, IndexError):
        return default

    body = abs(c - o)
    rng = h - l
    if rng <= 0:
        return default
    body_pct = body / rng
    upper = h - max(o, c)
    lower = min(o, c) - l

    # Bullish engulfing: prev red, current green, body fully engulfs prev body
    if pc < po and c > o and c >= po and o <= pc and body > abs(pc - po):
        return {"candle_pattern": "BULLISH ENGULFING", "candle_bias": "bullish"}
    # Bearish engulfing
    if pc > po and c < o and c <= po and o >= pc and body > abs(pc - po):
        return {"candle_pattern": "BEARISH ENGULFING", "candle_bias": "bearish"}
    # Hammer: small body, long lower shadow ≥ 2x body, close near high, after downtrend
    if lower >= 2 * body and upper <= body * 0.6 and body_pct <= 0.35 and c >= o:
        return {"candle_pattern": "HAMMER", "candle_bias": "bullish"}
    # Shooting star: small body, long upper shadow ≥ 2x body, close near low
    if upper >= 2 * body and lower <= body * 0.6 and body_pct <= 0.35 and c <= o:
        return {"candle_pattern": "SHOOTING STAR", "candle_bias": "bearish"}
    # Doji: body sangat kecil
    if body_pct <= 0.1 and rng > 0:
        return {"candle_pattern": "DOJI", "candle_bias": "neutral"}
    # Marubozu bullish (body dominan, hampir tidak ada shadow)
    if body_pct >= 0.85 and c > o:
        return {"candle_pattern": "MARUBOZU BULL", "candle_bias": "bullish"}
    if body_pct >= 0.85 and c < o:
        return {"candle_pattern": "MARUBOZU BEAR", "candle_bias": "bearish"}
    return default


# =============================================================================
# CHOPPINESS INDEX (REGIME DETECTION)
# =============================================================================
def compute_choppiness_index(candles: pd.DataFrame, period: int = 14) -> dict:
    """Choppiness Index 0-100. >61.8 = ranging (sideways), <38.2 = trending kuat.

    Trending market = sinyal momentum lebih dipercaya.
    Ranging market = sinyal mean-reversion lebih dipercaya.
    """
    default = {"choppiness": 50.0, "regime": "MIXED"}
    if candles is None or candles.empty or len(candles) < period + 5:
        return default
    try:
        high = candles["high"].astype(float)
        low = candles["low"].astype(float)
        close = candles["close"].astype(float)
    except (KeyError, ValueError, TypeError):
        return default
    tr = pd.concat(
        [high - low, (high - close.shift(1)).abs(), (low - close.shift(1)).abs()],
        axis=1,
    ).max(axis=1)
    atr_sum = tr.rolling(period).sum()
    high_max = high.rolling(period).max()
    low_min = low.rolling(period).min()
    rng = (high_max - low_min).replace(0, np.nan)
    ci_series = 100 * np.log10(atr_sum / rng) / np.log10(period)
    ci_series = ci_series.replace([np.inf, -np.inf], np.nan).dropna()
    if ci_series.empty:
        return default
    ci = float(ci_series.iloc[-1])
    if ci >= 61.8:
        regime = "RANGING"
    elif ci <= 38.2:
        regime = "TRENDING KUAT"
    elif ci <= 50:
        regime = "TRENDING"
    else:
        regime = "MIXED"
    return {"choppiness": round(ci, 1), "regime": regime}


# =============================================================================
# VWAP
# =============================================================================
def compute_vwap(candles: pd.DataFrame, lookback: int = 50) -> dict:
    """Volume Weighted Average Price (rolling, bukan session-based)."""
    default = {"vwap": None, "vwap_bias": "neutral", "vwap_distance_pct": 0.0}
    if candles is None or candles.empty or len(candles) < 10:
        return default
    try:
        recent = candles.tail(lookback)
        typical = (recent["high"].astype(float) + recent["low"].astype(float) + recent["close"].astype(float)) / 3
        volume = recent["volume"].astype(float)
        if volume.sum() <= 0:
            return default
        vwap = float((typical * volume).sum() / volume.sum())
        last = float(recent["close"].iloc[-1])
        dist_pct = (last - vwap) / vwap * 100 if vwap > 0 else 0.0
        if dist_pct > 1.5:
            bias = "above"  # harga premium di atas vwap
        elif dist_pct < -1.5:
            bias = "below"  # diskon
        else:
            bias = "neutral"
        return {"vwap": vwap, "vwap_bias": bias, "vwap_distance_pct": round(dist_pct, 2)}
    except (KeyError, ValueError, TypeError, ZeroDivisionError):
        return default


# =============================================================================
# RISK-ADJUSTED SCORE & KELLY ALLOCATION
# =============================================================================
def compute_risk_adjusted_score(score: float, atr_pct: float) -> dict:
    """Normalisasi score terhadap volatilitas (ATR%).

    Coin dengan score tinggi tapi volatilitas ekstrem dipotong.
    """
    score = _safe_float(score, 50)
    atr_pct = _safe_float(atr_pct, 3.0)
    if atr_pct <= 0:
        return {"risk_adjusted_score": score, "vol_label": "low", "vol_penalty": 0}
    # ATR% 3% dianggap normal. >8% = sangat volatil.
    if atr_pct >= 10:
        penalty = 12
        label = "ekstrem"
    elif atr_pct >= 7:
        penalty = 7
        label = "tinggi"
    elif atr_pct >= 4.5:
        penalty = 3
        label = "sedang"
    elif atr_pct <= 1.2:
        # terlalu sepi / iliquid juga risiko
        penalty = 2
        label = "sangat sepi"
    else:
        penalty = 0
        label = "normal"
    adjusted = _clamp(score - penalty, 0, 100)
    return {"risk_adjusted_score": round(adjusted, 1), "vol_label": label, "vol_penalty": penalty}


def compute_kelly_allocation(winrate_pct: float, avg_win_pct: float, avg_loss_pct: float, max_alloc: float = 10.0) -> dict:
    """Kelly fraction untuk position sizing.

    f* = W - (1-W) / R, dengan R = avg_win/avg_loss.
    Kita pakai HALF Kelly demi safety, lalu di-cap ke `max_alloc` % modal.
    """
    default = {"kelly_pct": None, "kelly_label": "BUTUH DATA", "kelly_edge": 0.0}
    if winrate_pct is None:
        return default
    w = _safe_float(winrate_pct, 0) / 100
    if w <= 0 or w >= 1:
        return default
    avg_win = _safe_float(avg_win_pct, 0)
    avg_loss = abs(_safe_float(avg_loss_pct, 0))
    if avg_win <= 0 or avg_loss <= 0:
        # fallback: gunakan asumsi RR 1.5
        ratio = 1.5
    else:
        ratio = avg_win / avg_loss
    if ratio <= 0:
        return default
    kelly = w - (1 - w) / ratio
    if kelly <= 0:
        return {"kelly_pct": 0.0, "kelly_label": "EDGE NEGATIF", "kelly_edge": round(kelly * 100, 2)}
    half_kelly = kelly * 0.5
    pct = _clamp(half_kelly * 100, 0, max_alloc)
    if pct >= 6:
        label = "EDGE KUAT"
    elif pct >= 3:
        label = "EDGE SEHAT"
    elif pct >= 1:
        label = "EDGE TIPIS"
    else:
        label = "EDGE LEMAH"
    return {"kelly_pct": round(pct, 1), "kelly_label": label, "kelly_edge": round(kelly * 100, 2)}


# =============================================================================
# AGGREGATE INTELLIGENCE BUNDLE
# =============================================================================
def build_intelligence_bundle(candles: pd.DataFrame, price: float, atr_pct: float = 3.0) -> dict:
    """Bundle semua signal cerdas + agregat skor adjustment & confidence label."""
    swings = compute_swing_levels(candles, price)
    fib = compute_fibonacci_levels(candles)
    div = detect_rsi_divergence(candles)
    candle = detect_candlestick_patterns(candles)
    chop = compute_choppiness_index(candles)
    vwap = compute_vwap(candles)

    intel_adjust = 0
    notes: list[str] = []

    # Divergence
    if div["divergence"] == "BULLISH":
        intel_adjust += 5 + min(3, div["divergence_strength"])
        notes.append(f"Bullish divergence (+{5 + min(3, div['divergence_strength'])})")
    elif div["divergence"] == "BEARISH":
        intel_adjust -= 6 + min(3, div["divergence_strength"])
        notes.append(f"Bearish divergence (-{6 + min(3, div['divergence_strength'])})")

    # Candle pattern
    if candle["candle_bias"] == "bullish":
        intel_adjust += 4
        notes.append(f"{candle['candle_pattern']} (+4)")
    elif candle["candle_bias"] == "bearish":
        intel_adjust -= 5
        notes.append(f"{candle['candle_pattern']} (-5)")

    # Regime
    if chop["regime"] == "TRENDING KUAT":
        intel_adjust += 3
        notes.append("Tren kuat (+3)")
    elif chop["regime"] == "RANGING":
        intel_adjust -= 2
        notes.append("Sideways (-2)")

    # VWAP — diskon di bawah VWAP saat tren naik adalah peluang, premium tinggi adalah risiko fomo
    if vwap["vwap_bias"] == "below" and chop["regime"] in {"TRENDING", "TRENDING KUAT"}:
        intel_adjust += 2
        notes.append("Harga di bawah VWAP (+2)")
    elif vwap["vwap_bias"] == "above" and vwap.get("vwap_distance_pct", 0) > 5:
        intel_adjust -= 3
        notes.append("Premium >5% di atas VWAP (-3)")

    # Fib zone — golden zone 0.5–0.618 saat retrace adalah area entry klasik
    if fib["fib_zone"] in {"GOLDEN 0.5", "GOLDEN 0.618"}:
        intel_adjust += 3
        notes.append(f"Retrace di {fib['fib_zone']} (+3)")
    elif fib["fib_zone"] == "DEEP 0.786":
        intel_adjust += 1
        notes.append("Deep retrace 0.786 (+1)")
    elif fib["fib_zone"] == "DI HIGH":
        intel_adjust -= 2
        notes.append("Sudah di area high (-2)")

    # Risk adjustment via volatilitas
    risk_adj_score = compute_risk_adjusted_score(50 + intel_adjust, atr_pct)
    intel_adjust -= risk_adj_score.get("vol_penalty", 0)
    if risk_adj_score.get("vol_label") in {"tinggi", "ekstrem"}:
        notes.append(f"Volatilitas {risk_adj_score['vol_label']} (-{risk_adj_score['vol_penalty']})")

    # Confidence label dari magnitudo agregat
    abs_adj = abs(intel_adjust)
    if abs_adj >= 12:
        confidence_label = "SANGAT TINGGI"
    elif abs_adj >= 7:
        confidence_label = "TINGGI"
    elif abs_adj >= 3:
        confidence_label = "SEDANG"
    else:
        confidence_label = "LEMAH"

    intel_adjust = int(_clamp(intel_adjust, -18, 14))

    return {
        "swings": swings,
        "fib": fib,
        "divergence": div,
        "candle": candle,
        "regime": chop,
        "vwap": vwap,
        "vol": {"vol_label": risk_adj_score.get("vol_label"), "vol_penalty": risk_adj_score.get("vol_penalty")},
        "intel_adjustment": intel_adjust,
        "intel_notes": notes[:5],
        "intel_confidence": confidence_label,
    }


# =============================================================================
# REALISTIC TWO STEPS AHEAD (pakai S/R riil + ATR)
# =============================================================================
def build_two_steps_ahead(price: float, action: str, swings: dict, atr: float | None) -> dict:
    """Skenario realistis pakai swing S/R yang riil. Fallback ke ATR-based jika swing kosong."""
    atr_val = _safe_float(atr, 0)
    if atr_val <= 0 or atr_val > price * 0.5:
        atr_val = price * 0.03  # fallback 3%

    s1 = swings.get("swing_support_1") or (price - 1.5 * atr_val)
    s2 = swings.get("swing_support_2") or (price - 3 * atr_val)
    r1 = swings.get("swing_resistance_1") or (price + 1.8 * atr_val)
    r2 = swings.get("swing_resistance_2") or (price + 3.5 * atr_val)

    # Sanity guard
    if s1 >= price:
        s1 = price - 1.5 * atr_val
    if s2 >= s1:
        s2 = s1 - 1.5 * atr_val
    if r1 <= price:
        r1 = price + 1.8 * atr_val
    if r2 <= r1:
        r2 = r1 + 1.8 * atr_val

    is_buy = "BELI" in str(action).upper() and "JANGAN" not in str(action).upper()
    is_watch = "WATCH" in str(action).upper()

    if is_buy:
        step1 = {
            "label": "Naik tes resistance terdekat",
            "price": r1,
            "delta_pct": (r1 - price) / price * 100,
        }
        step2 = {
            "label": "Tembus R1, lanjut ke R2",
            "price": r2,
            "delta_pct": (r2 - price) / price * 100,
        }
        fail = {
            "label": "Gagal momentum, retest support",
            "price": s1,
            "delta_pct": (s1 - price) / price * 100,
        }
    elif is_watch:
        step1 = {
            "label": "Pantau support — bertahan = sinyal lebih bersih",
            "price": s1,
            "delta_pct": (s1 - price) / price * 100,
        }
        step2 = {
            "label": "Jika S1 jadi pantulan, target R1",
            "price": r1,
            "delta_pct": (r1 - price) / price * 100,
        }
        fail = {
            "label": "Jebol S1, lanjut ke S2",
            "price": s2,
            "delta_pct": (s2 - price) / price * 100,
        }
    else:
        step1 = {"label": "Hindari dulu — tunggu reversal valid", "price": 0, "delta_pct": 0}
        step2 = {"label": "Pantau dari jauh", "price": 0, "delta_pct": 0}
        fail = {"label": "Tidak direkomendasikan", "price": 0, "delta_pct": 0}

    return {
        "step1_action": step1["label"],
        "step1_price": step1["price"],
        "step1_gain": round(step1["delta_pct"], 2),
        "step2_action": step2["label"],
        "step2_price": step2["price"],
        "step2_gain": round(step2["delta_pct"], 2),
        "fail_action": fail["label"],
        "fail_price": fail["price"],
        "fail_loss": round(abs(fail["delta_pct"]), 2),
        "support_s1": s1,
        "support_s2": s2,
        "resistance_r1": r1,
        "resistance_r2": r2,
    }


# =============================================================================
# KELLY-BASED ALLOCATION ADJUSTMENT
# =============================================================================
def apply_kelly_to_allocation(item: dict, learning_profile: dict | None) -> dict:
    """Sesuaikan alokasi item berdasarkan Kelly fraction dari winrate per-symbol.

    Tetap dibatasi 0–10% dan dikalikan terhadap alokasi awal (tidak menggandakan).
    """
    if not learning_profile:
        item["kelly_pct"] = None
        item["kelly_label"] = "BUTUH DATA"
        return item
    by_symbol = learning_profile.get("by_symbol", {})
    stats = by_symbol.get(item.get("symbol"), {})
    closed = stats.get("closed", 0)
    if closed < 5:
        item["kelly_pct"] = None
        item["kelly_label"] = "BUTUH RIWAYAT"
        return item
    winrate = stats.get("winrate", 0)
    avg_max_gain = stats.get("avg_max_gain", 0)
    # asumsi avg loss ~ -3% jika tidak tersedia (ATR-based SL biasa)
    kelly = compute_kelly_allocation(winrate, avg_max_gain, 3.0)
    item["kelly_pct"] = kelly.get("kelly_pct")
    item["kelly_label"] = kelly.get("kelly_label")
    if kelly.get("kelly_pct") is not None and item.get("allocation_pct", 0) > 0:
        # blend 60% original + 40% kelly recommendation
        original = float(item.get("allocation_pct", 0) or 0)
        blended = original * 0.6 + kelly["kelly_pct"] * 0.4
        item["allocation_pct"] = round(_clamp(blended, 0, 10), 1)
    return item
