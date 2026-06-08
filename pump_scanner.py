"""
Pump Scanner — Deteksi koin yang akan pump dari 500+ aset Indodax.

4-layer filter:
  Layer 1: Ticker Filter (cepat, dari /api/summaries)
  Layer 2: Candle 15m Quick Scan (EMA, RSI, Volume, MACD, BB)
  Layer 3: Candle 1H Deep Analysis (full technical analysis)
  Layer 4: Pump Probability Scoring (0-100)

Output: daftar koin dengan pump_probability, grade, entry zone, TP/SL.
"""

from __future__ import annotations

import logging
import time
import math
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

logger = logging.getLogger(__name__)

import numpy as np
import pandas as pd
import requests

# Binance global data
try:
    import binance_engine
    BINANCE_AVAILABLE = True
except ImportError:
    binance_engine = None  # type: ignore
    BINANCE_AVAILABLE = False


# =============================================================================
# UTILITY
# =============================================================================
def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def _safe_float(v: Any, d: float = 0.0) -> float:
    try:
        if v is None:
            return d
        f = float(v)
        return d if math.isnan(f) or math.isinf(f) else f
    except (TypeError, ValueError):
        return d


# =============================================================================
# TECHNICAL INDICATORS (self-contained, no imports from app.py)
# =============================================================================
def _compute_rsi(close: pd.Series, period: int = 14) -> float:
    if len(close) < period + 2:
        return 50.0
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / period, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / period, adjust=False).mean()
    rs = gain / loss.replace(0, np.nan)
    rsi = (100 - (100 / (1 + rs))).fillna(50)
    return float(rsi.iloc[-1])


def _compute_ema(close: pd.Series, span: int) -> pd.Series:
    return close.ewm(span=span, adjust=False).mean()


def _compute_macd(close: pd.Series) -> tuple[str, float]:
    if len(close) < 15:
        return "netral", 0.0
    macd_line = _compute_ema(close, 12) - _compute_ema(close, 26)
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


def _compute_bollinger(close: pd.Series) -> dict:
    if len(close) < 20:
        return {"bb_signal": "netral", "bb_pct_b": 0.5}
    mid = float(close.tail(20).mean())
    std = float(close.tail(20).std())
    upper = mid + 2 * std
    lower = mid - 2 * std
    last = float(close.iloc[-1])
    pct_b = (last - lower) / (upper - lower) if upper > lower else 0.5
    sig = "oversold" if pct_b < 0.15 else "overbought" if pct_b > 0.85 else "netral"
    return {"bb_signal": sig, "bb_pct_b": round(pct_b, 2)}


def _compute_atr(candles: pd.DataFrame, period: int = 14) -> float:
    if candles.empty or len(candles) < period + 2:
        return 0.0
    h = candles["high"].astype(float)
    lo = candles["low"].astype(float)
    c = candles["close"].astype(float)
    tr = pd.concat([h - lo, (h - c.shift(1)).abs(), (lo - c.shift(1)).abs()], axis=1).max(axis=1)
    atr = tr.rolling(period).mean()
    val = atr.iloc[-1]
    return float(val) if pd.notna(val) else 0.0


def _compute_supertrend(candles: pd.DataFrame) -> str:
    if candles.empty or len(candles) < 30:
        return "netral"
    h = candles["high"].astype(float)
    lo = candles["low"].astype(float)
    c = candles["close"].astype(float)
    tr = pd.concat([h - lo, (h - c.shift(1)).abs(), (lo - c.shift(1)).abs()], axis=1).max(axis=1)
    atr = tr.rolling(14).mean()
    ema_f = c.ewm(span=10, adjust=False).mean()
    ema_s = c.ewm(span=30, adjust=False).mean()
    floor = ((h + lo) / 2) - (2.4 * atr)
    if pd.notna(floor.iloc[-1]) and c.iloc[-1] > floor.iloc[-1] and ema_f.iloc[-1] > ema_s.iloc[-1]:
        return "bullish"
    return "bearish" if pd.notna(floor.iloc[-1]) else "netral"


def _compute_adx(candles: pd.DataFrame) -> dict:
    default = {"adx": 0, "trend": "neutral"}
    if candles.empty or len(candles) < 30:
        return default
    try:
        h = candles["high"].astype(float)
        lo = candles["low"].astype(float)
        c = candles["close"].astype(float)
        tr = pd.concat([h - lo, (h - c.shift(1)).abs(), (lo - c.shift(1)).abs()], axis=1).max(axis=1)
        plus_dm = (h - h.shift(1)).clip(lower=0)
        minus_dm = (lo.shift(1) - lo).clip(lower=0)
        plus_dm = plus_dm.where(plus_dm > minus_dm, 0)
        minus_dm = minus_dm.where(minus_dm > plus_dm, 0)
        atr14 = tr.rolling(14).mean()
        plus_di = 100 * plus_dm.rolling(14).mean() / atr14.replace(0, np.nan)
        minus_di = 100 * minus_dm.rolling(14).mean() / atr14.replace(0, np.nan)
        dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di).replace(0, np.nan)
        adx = dx.rolling(14).mean()
        adx_val = float(adx.iloc[-1]) if pd.notna(adx.iloc[-1]) else 0
        plus_val = float(plus_di.iloc[-1]) if pd.notna(plus_di.iloc[-1]) else 0
        minus_val = float(minus_di.iloc[-1]) if pd.notna(minus_di.iloc[-1]) else 0
        if plus_val > minus_val:
            trend = "bullish_strong" if adx_val > 25 else "bullish"
        elif minus_val > plus_val:
            trend = "bearish_strong" if adx_val > 25 else "bearish"
        else:
            trend = "neutral"
        return {"adx": round(adx_val, 1), "trend": trend}
    except Exception:
        return default


# =============================================================================
# CANDLE FETCHING
# =============================================================================
def _fetch_candles(pair_id: str, tf: str = "60", lookback_days: int = 21) -> pd.DataFrame:
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
# LAYER 1: TICKER FILTER (cepat, dari API /summaries)
# =============================================================================
MIN_VOLUME_IDR = 500_000_000      # 500M IDR minimum
MIN_CHANGE = -2.0                  # Jangan terlalu bearish
MAX_CHANGE = 12.0                  # Belum pump terlalu jauh
MAX_RANGE_POS = 80.0               # Belum di puncak range 24h


def layer1_ticker_filter(tickers: dict, prices_24h: dict) -> list[dict]:
    """Filter cepat dari data ticker. Return list koin yang lolos."""
    candidates = []
    for pair, info in tickers.items():
        if not pair.endswith("_idr"):
            continue
        try:
            symbol = pair.replace("_idr", "").upper()
            price = float(info.get("last", 0))
            if price <= 0:
                continue
            high = float(info.get("high", price))
            low = float(info.get("low", price))
            vol_idr = float(info.get("vol_idr", 0))

            # Change 24h
            pair_key = pair.replace("_", "")
            ref_price = float((prices_24h or {}).get(pair_key, 0))
            change = ((price - ref_price) / ref_price * 100) if ref_price > 0 else 0.0

            # Range position
            range_w = high - low
            range_pos = ((price - low) / range_w * 100) if range_w > 0 else 50

            # Filter
            if vol_idr < MIN_VOLUME_IDR:
                continue
            if change < MIN_CHANGE or change > MAX_CHANGE:
                continue
            if range_pos > MAX_RANGE_POS:
                continue

            candidates.append({
                "symbol": symbol,
                "pair": pair,
                "price": price,
                "high": high,
                "low": low,
                "vol_idr": vol_idr,
                "change": round(change, 2),
                "range_pos": round(range_pos, 1),
            })
        except (ValueError, TypeError, KeyError):
            continue

    # Sort by volume descending (prioritas koin liquid)
    candidates.sort(key=lambda x: x["vol_idr"], reverse=True)
    return candidates[:100]  # Cap ke top 100 volume


# =============================================================================
# LAYER 2: 15-MINUTE QUICK SCAN
# =============================================================================
def layer2_15m_scan(candidate: dict) -> dict | None:
    """Scan candle 15m untuk deteksi setup pre-pump.

    Return candidate dict + setup info jika lolos, None jika tidak.
    """
    pair = candidate["pair"]
    try:
        candles_15m = _fetch_candles(pair, tf="15", lookback_days=5)
        time.sleep(0.15)  # rate limit
        if candles_15m.empty or len(candles_15m) < 30:
            return None

        close = candles_15m["close"].astype(float)
        vol = candles_15m["volume"].astype(float)

        # EMA cross + slope
        ema8 = _compute_ema(close, 8)
        ema21 = _compute_ema(close, 21)
        ema_cross_up = bool(ema8.iloc[-1] > ema21.iloc[-1])
        ema8_slope_up = bool(ema8.iloc[-1] > ema8.iloc[-3]) if len(ema8) >= 3 else False
        ema_check = ema_cross_up and ema8_slope_up

        # RSI bangun
        rsi_now = _compute_rsi(close)
        rsi_prev = _compute_rsi(close.iloc[:-1]) if len(close) >= 16 else rsi_now
        rsi_check = (35 <= rsi_now <= 70) and (rsi_now > rsi_prev + 1.0)

        # Volume spike (15m)
        avg_vol_20 = float(vol.tail(21).iloc[:-1].mean()) if len(vol) >= 21 else float(vol.tail(20).mean())
        last_vol = float(vol.iloc[-1])
        vol_ratio = (last_vol / avg_vol_20) if avg_vol_20 > 0 else 1.0
        vol_check = vol_ratio >= 1.3

        # MACD bullish
        macd_state, macd_hist = _compute_macd(close)
        macd_check = macd_state in ("bullish cross", "bullish") and macd_hist > 0

        # Bollinger squeeze release
        bb_now = _compute_bollinger(close)
        bb_prev = _compute_bollinger(close.iloc[:-1]) if len(close) >= 21 else bb_now
        pct_b_now = bb_now.get("bb_pct_b", 0.5)
        pct_b_prev = bb_prev.get("bb_pct_b", pct_b_now)
        bb_check = pct_b_prev < 0.45 and pct_b_now >= 0.48

        checks = {
            "EMA8>EMA21 + slope naik": ema_check,
            "RSI bangun (35-70 & naik)": rsi_check,
            "Volume ≥1.3x MA20 (15m)": vol_check,
            "MACD bullish (15m)": macd_check,
            "BB squeeze release": bb_check,
        }
        passed = sum(1 for v in checks.values() if v)

        # Minimal 3/5 checklist terpenuhi
        if passed < 3:
            return None

        # Build trigger labels
        triggers = []
        if ema_check:
            triggers.append("EMA↑")
        if rsi_check:
            triggers.append(f"RSI {rsi_prev:.0f}→{rsi_now:.0f}")
        if vol_check:
            triggers.append(f"Vol {vol_ratio:.1f}x")
        if macd_check:
            triggers.append("MACD+")
        if bb_check:
            triggers.append("BB release")

        result = {**candidate}
        result["setup_15m"] = {
            "passed": passed,
            "checks": checks,
            "triggers": triggers,
            "rsi_15m": round(rsi_now, 1),
            "rsi_prev_15m": round(rsi_prev, 1),
            "vol_ratio_15m": round(vol_ratio, 2),
            "macd_state_15m": macd_state,
            "ema_state_15m": "bullish" if ema_check else "warming" if ema_cross_up else "bearish",
            "bb_pct_b": round(pct_b_now, 2),
        }
        return result

    except Exception:
        return None


# =============================================================================
# LAYER 3: 1-HOUR DEEP ANALYSIS
# =============================================================================
def layer3_deep_analysis(candidate: dict) -> dict | None:
    """Analisis teknikal penuh di TF 1H. Return enriched dict atau None."""
    pair = candidate["pair"]
    symbol = candidate["symbol"]
    try:
        candles = _fetch_candles(pair, tf="60", lookback_days=21)
        time.sleep(0.15)
        if candles.empty or len(candles) < 30:
            return None

        close = candles["close"].astype(float)
        high = candles["high"].astype(float)
        low = candles["low"].astype(float)
        vol = candles["volume"].astype(float)
        price = candidate["price"]
        change = candidate["change"]

        # Core indicators
        rsi = _compute_rsi(close)
        ema5 = _compute_ema(close, 5).iloc[-1]
        ema12 = _compute_ema(close, 12).iloc[-1]
        ema21 = _compute_ema(close, 21).iloc[-1]
        ema_trend_pct = ((ema5 - ema12) / ema12 * 100) if ema12 > 0 else 0
        ema_bias = "bullish" if ema5 > ema12 > ema21 else "bullish" if ema5 > ema12 else "bearish"
        macd_signal, macd_hist = _compute_macd(close)
        bb = _compute_bollinger(close)
        supertrend = _compute_supertrend(candles)
        adx_data = _compute_adx(candles)
        atr = _compute_atr(candles)

        # Volume analysis
        vol_avg = float(vol.tail(20).mean())
        vol_ratio_1h = float(vol.iloc[-1] / vol_avg) if vol_avg > 0 else 1.0

        # Buy pressure (close position within bar)
        rng = high - low
        cp = (close - low) / rng.replace(0, np.nan)
        buy_pressure = float(cp.tail(5).mean() * 100) if not cp.tail(5).isna().all() else 50

        # Multi-timeframe (simplified)
        ema_fast_4h = close.tail(48).mean() if len(close) >= 48 else close.mean()
        ema_slow_4h = close.tail(96).mean() if len(close) >= 96 else close.mean()
        mtf_bullish = ema_fast_4h > ema_slow_4h

        # Score (simplified from analyze_coin_advanced)
        tech_score = 0
        tech_score += _clamp(ema_trend_pct * 3, -12, 12)
        tech_score += 8 if macd_signal == "bullish cross" else 5 if macd_signal == "bullish" else -8 if macd_signal == "bearish cross" else -5 if macd_signal == "bearish" else 0
        tech_score += 6 if 45 <= rsi <= 68 else -7 if rsi > 78 else -4 if rsi < 30 else 0
        tech_score += 5 if supertrend == "bullish" else -6 if supertrend == "bearish" else 0
        tech_score += 4 if vol_ratio_1h >= 1.5 else 2 if vol_ratio_1h >= 1.15 else -3 if vol_ratio_1h < 0.7 else 0
        bb_bonus = 7 if bb["bb_signal"] == "oversold" else -5 if bb["bb_signal"] == "overbought" else 0
        adx_bonus = 5 if adx_data["trend"] in ("bullish_strong", "bullish") else -5 if adx_data["trend"] in ("bearish_strong", "bearish") else 0
        mtf_bonus = 4 if mtf_bullish else -3

        base = 50 + change * 3.5 + tech_score * 0.65 + bb_bonus + adx_bonus + mtf_bonus
        score = int(_clamp(round(base), 0, 100))

        # Filter: minimal score 58 dan tidak bearish kuat
        if score < 58:
            return None
        if adx_data["trend"] in ("bearish_strong",) and adx_data["adx"] > 25:
            return None
        if rsi > 78:
            return None

        # TP/SL dari ATR
        if atr > 0 and atr < price * 0.25:
            stop_loss = price - (1.5 * atr)
            tp1 = price + (0.7 * atr)
            tp2 = price + (1.4 * atr)
            tp3 = price + (2.2 * atr)
            target = price + (2.0 * atr)
        else:
            pct = max(3, change * 0.5 + 3)
            stop_loss = price * 0.97
            tp1 = price * (1 + pct * 0.35 / 100)
            tp2 = price * (1 + pct * 0.7 / 100)
            tp3 = price * (1 + pct / 100)
            target = tp3

        # Entry zone
        entry_zone_low = price * 0.995  # sedikit di bawah harga sekarang
        entry_zone_high = price * 1.005  # sedikit di atas

        # Risk-reward ratio
        risk = price - stop_loss
        reward = target - price
        rr = round(reward / risk, 1) if risk > 0 else 0

        result = {**candidate}
        result["deep_analysis"] = {
            "score": score,
            "rsi_1h": round(rsi, 1),
            "ema_bias": ema_bias,
            "ema_trend_pct": round(ema_trend_pct, 2),
            "macd_signal": macd_signal,
            "macd_hist": round(macd_hist, 6),
            "bb_signal": bb["bb_signal"],
            "bb_pct_b": bb["bb_pct_b"],
            "supertrend": supertrend,
            "adx": adx_data["adx"],
            "adx_trend": adx_data["trend"],
            "atr": round(atr, 6) if atr else 0,
            "vol_ratio_1h": round(vol_ratio_1h, 2),
            "buy_pressure": round(buy_pressure, 1),
            "mtf_bullish": mtf_bullish,
            "tp1": tp1,
            "tp2": tp2,
            "tp3": tp3,
            "target": target,
            "stop_loss": stop_loss,
            "entry_zone_low": entry_zone_low,
            "entry_zone_high": entry_zone_high,
            "risk_reward": f"1:{rr}",
            "rr_value": rr,
        }
        return result

    except Exception:
        return None


# =============================================================================
# LAYER 4: PUMP PROBABILITY SCORING (+ Binance Global Sentiment)
# =============================================================================
def layer4_pump_score(candidate: dict, binance_data: dict | None = None) -> dict:
    """Hitung pump probability (0-100) dan grade (A/B/C/D).

    Sekarang termasuk komponen Binance global sentiment (funding rate,
    long/short ratio, order book depth) untuk akurasi lebih tinggi.
    """
    setup = candidate.get("setup_15m", {})
    deep = candidate.get("deep_analysis", {})
    change = candidate.get("change", 0)

    # === Momentum Score (0-22) ===
    momentum = 0
    # Change trend positif
    if change > 3:
        momentum += 8
    elif change > 1:
        momentum += 5
    elif change > 0:
        momentum += 3

    # EMA alignment
    if deep.get("ema_bias") == "bullish":
        momentum += 6
    if deep.get("ema_trend_pct", 0) > 0.5:
        momentum += 4
    if setup.get("ema_state_15m") == "bullish":
        momentum += 4
    momentum = min(22, momentum)

    # === Volume Score (0-22) ===
    volume = 0
    vol_15m = setup.get("vol_ratio_15m", 1.0)
    vol_1h = deep.get("vol_ratio_1h", 1.0)
    if vol_15m >= 2.0:
        volume += 9
    elif vol_15m >= 1.5:
        volume += 6
    elif vol_15m >= 1.3:
        volume += 3
    if vol_1h >= 1.8:
        volume += 7
    elif vol_1h >= 1.2:
        volume += 4
    # Buy pressure
    bp = deep.get("buy_pressure", 50)
    if bp > 65:
        volume += 6
    elif bp > 55:
        volume += 3
    volume = min(22, volume)

    # === Technical Score (0-22) ===
    technical = 0
    rsi = deep.get("rsi_1h", 50)
    # RSI sweet spot (45-65 = momentum tapi belum overbought)
    if 45 <= rsi <= 65:
        technical += 6
    elif 35 <= rsi <= 45:
        technical += 4  # oversold recovery
    # MACD
    if deep.get("macd_signal") == "bullish cross":
        technical += 5
    elif deep.get("macd_signal") == "bullish":
        technical += 3
    # Supertrend
    if deep.get("supertrend") == "bullish":
        technical += 4
    # ADX trend bullish
    if deep.get("adx_trend") in ("bullish_strong", "bullish"):
        technical += 4
    # BB oversold (potensi bounce)
    if deep.get("bb_signal") == "oversold":
        technical += 3
    technical = min(22, technical)

    # === Forecast/Setup Score (0-19) ===
    forecast = 0
    # 15m setup strength
    passed = setup.get("passed", 0)
    forecast += passed * 3  # maks 15 dari 5 check
    # MTF confirmation
    if deep.get("mtf_bullish"):
        forecast += 4
    forecast = min(19, forecast)

    # === Binance Global Sentiment Score (0-15) ===
    binance_score = 0
    binance_notes_pump: list[str] = []
    bn = binance_data or candidate.get("binance_sentiment", {})
    if bn and bn.get("available"):
        bn_adj = bn.get("binance_adjustment", 0)
        # Skala adjustment (-10..+10) ke skor (0..15)
        binance_score = int(_clamp(round(bn_adj * 1.2 + 3), 0, 15))

        # Volume anomaly check: fake pump di lokal tanpa dukungan global
        vol_comp = candidate.get("binance_vol_compare", {})
        if vol_comp.get("vol_anomaly"):
            binance_score = max(0, binance_score - 5)
            binance_notes_pump.append("⚠️ Anomali volume lokal")

        # Funding rate signal
        f_sig = bn.get("funding", {}).get("funding_signal", "")
        if f_sig == "SHORT SQUEEZE":
            binance_score = min(15, binance_score + 3)
            binance_notes_pump.append("🚀 Short squeeze potential")
        elif f_sig == "LONG CROWDED":
            binance_score = max(0, binance_score - 3)
            binance_notes_pump.append("⚠️ Long crowded")

        # Order book signal
        b_sig = bn.get("order_book", {}).get("book_signal", "")
        if b_sig == "STRONG BUY WALL":
            binance_notes_pump.append(f"Buy wall {bn['order_book']['book_ratio']:.1f}x")
        elif b_sig == "STRONG SELL WALL":
            binance_notes_pump.append(f"Sell wall {bn['order_book']['book_ratio']:.1f}x")
    binance_score = int(_clamp(binance_score, 0, 15))

    # === Total Pump Probability ===
    pump_prob = momentum + volume + technical + forecast + binance_score
    pump_prob = int(_clamp(pump_prob, 0, 100))

    # Grade
    if pump_prob >= 75:
        grade = "A"
    elif pump_prob >= 60:
        grade = "B"
    elif pump_prob >= 45:
        grade = "C"
    else:
        grade = "D"

    # Estimated timeframe
    if pump_prob >= 75 and vol_15m >= 1.8:
        timeframe = "1-6 jam"
    elif pump_prob >= 60:
        timeframe = "6-24 jam"
    else:
        timeframe = "24-48 jam"

    candidate["pump_probability"] = pump_prob
    candidate["pump_grade"] = grade
    candidate["pump_timeframe"] = timeframe
    candidate["pump_scores"] = {
        "momentum": momentum,
        "volume": volume,
        "technical": technical,
        "forecast": forecast,
        "binance_global": binance_score,
    }
    candidate["binance_pump_notes"] = binance_notes_pump
    return candidate


# =============================================================================
# ORCHESTRATOR — Run Full Pump Scan
# =============================================================================
def run_pump_scan(tickers: dict, prices_24h: dict, progress_callback=None) -> list[dict]:
    """Scan seluruh koin Indodax untuk mendeteksi pump.

    Sekarang termasuk Layer 4.5: Binance global sentiment enrichment.

    Args:
        tickers: dict dari /api/summaries
        prices_24h: dict harga 24h lalu
        progress_callback: callable(current, total, message) untuk progress bar

    Returns:
        list of dicts sorted by pump_probability descending
    """
    # Layer 1: Ticker filter
    if progress_callback:
        progress_callback(0, 100, "🔍 Layer 1: Menyaring koin berdasarkan volume & momentum...")
    candidates = layer1_ticker_filter(tickers, prices_24h)
    total_l1 = len(candidates)
    if not candidates:
        return []

    # Layer 2: 15m Quick Scan (paralel)
    if progress_callback:
        progress_callback(10, 100, f"⚡ Layer 2: Scanning {total_l1} koin di TF 15m...")

    layer2_results = []
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {executor.submit(layer2_15m_scan, c): c for c in candidates}
        done = 0
        for future in as_completed(futures):
            done += 1
            if progress_callback and done % 10 == 0:
                pct = 10 + int(done / total_l1 * 40)
                progress_callback(pct, 100, f"⚡ Layer 2: {done}/{total_l1} koin di-scan...")
            result = future.result()
            if result is not None:
                layer2_results.append(result)

    total_l2 = len(layer2_results)
    if not layer2_results:
        return []

    # Layer 3: 1H Deep Analysis (paralel)
    if progress_callback:
        progress_callback(55, 100, f"🔬 Layer 3: Analisis mendalam {total_l2} koin di TF 1H...")

    layer3_results = []
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {executor.submit(layer3_deep_analysis, c): c for c in layer2_results}
        done = 0
        for future in as_completed(futures):
            done += 1
            if progress_callback and done % 5 == 0:
                pct = 55 + int(done / total_l2 * 30)
                progress_callback(pct, 100, f"🔬 Layer 3: {done}/{total_l2} koin dianalisis...")
            result = future.result()
            if result is not None:
                layer3_results.append(result)

    if not layer3_results:
        return []

    # Layer 4 prep: Fetch Binance global sentiment (paralel, batch)
    binance_sentiments: dict[str, dict] = {}
    if BINANCE_AVAILABLE:
        if progress_callback:
            progress_callback(86, 100, "🌐 Mengambil data sentimen Binance global...")
        try:
            symbols = [c["symbol"] for c in layer3_results]
            binance_sentiments = binance_engine.fetch_binance_sentiment_batch(symbols, max_workers=5)
            # Volume comparison untuk deteksi fake pump
            for c in layer3_results:
                sym = c["symbol"]
                if sym in binance_sentiments:
                    c["binance_sentiment"] = binance_sentiments[sym]
                    vol_idr = c.get("vol_idr", 0)
                    c["binance_vol_compare"] = binance_engine.compare_volume_global(sym, vol_idr)
        except Exception as e:
            logger.warning(f"Binance sentiment fetch failed: {e}")

    # Layer 4: Pump Probability Scoring (+ Binance global)
    if progress_callback:
        progress_callback(92, 100, "🎯 Layer 4: Menghitung probabilitas pump + sentimen global...")

    final_results = []
    for candidate in layer3_results:
        bn_data = binance_sentiments.get(candidate["symbol"])
        scored = layer4_pump_score(candidate, binance_data=bn_data)
        # Hanya tampilkan grade C ke atas
        if scored["pump_grade"] in ("A", "B", "C"):
            final_results.append(scored)

    # Sort by pump_probability descending
    final_results.sort(key=lambda x: x["pump_probability"], reverse=True)

    if progress_callback:
        progress_callback(100, 100, f"✅ Scan selesai! {len(final_results)} koin terdeteksi (+ Binance).")

    return final_results
