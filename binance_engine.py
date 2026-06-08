"""
Binance Engine — Data Sentimen & Volume Global dari Binance
============================================================
Fetch data pasar global dari Binance REST API (public endpoints) untuk
memperkaya sinyal prediksi dan training AI.

Data yang diambil:
- Ticker 24h: volume global, change% global (spot + futures)
- Funding Rate: sentimen long vs short (futures perpetual)
- Long/Short Ratio: rasio posisi top traders
- Order Book Depth: buy wall vs sell wall ratio

Semua fungsi defensif — return default aman jika API gagal.
Tidak butuh API key untuk public endpoints.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any

import requests

logger = logging.getLogger(__name__)

# =============================================================================
# CONFIG
# =============================================================================
# Base URLs
BINANCE_SPOT_BASE = "https://api.binance.com"
BINANCE_FUTURES_BASE = "https://fapi.binance.com"

# API keys (opsional, untuk rate limit lebih tinggi)
BINANCE_API_KEY = os.environ.get("BINANCE_API_KEY", "")
BINANCE_SECRET_KEY = os.environ.get("BINANCE_SECRET_KEY", "")

# Cache sederhana in-memory (TTL-based)
_cache: dict[str, tuple[float, Any]] = {}
CACHE_TTL = 120  # 2 menit


def _get_secret(key: str, default: str = "") -> str:
    """Ambil secret dari env atau streamlit secrets."""
    val = os.environ.get(key, "")
    if val:
        return val
    try:
        import streamlit as st
        return st.secrets.get(key, default)
    except Exception:
        return default


def _cached_get(url: str, params: dict | None = None, timeout: int = 8) -> Any:
    """HTTP GET dengan simple TTL cache."""
    cache_key = f"{url}:{params}"
    now = time.time()
    if cache_key in _cache:
        ts, data = _cache[cache_key]
        if now - ts < CACHE_TTL:
            return data

    headers = {}
    api_key = _get_secret("BINANCE_API_KEY")
    if api_key:
        headers["X-MBX-APIKEY"] = api_key

    try:
        resp = requests.get(url, params=params, headers=headers, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
        _cache[cache_key] = (now, data)
        return data
    except Exception as e:
        logger.warning(f"Binance API error ({url}): {e}")
        return None


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        v = float(value)
        return default if v != v else v  # NaN check
    except (TypeError, ValueError):
        return default


# =============================================================================
# SYMBOL MAPPING: Indodax symbol → Binance symbol
# =============================================================================
# Indodax pakai "BTC" (simbol koin), Binance pakai "BTCUSDT" (pair).
# Mapping otomatis: {symbol}USDT. Override manual untuk edge case.
_SYMBOL_OVERRIDE = {
    "SHIB": "SHIBUSDT",   # 1000SHIBUSDT di Binance futures
    "LUNC": "LUNCUSDT",
    "BTTC": "BTTCUSDT",
    "PEPE": "1000PEPEUSDT",  # futures
    "FLOKI": "1000FLOKIUSDT",  # futures
}


def _to_binance_symbol(indodax_symbol: str) -> str:
    """Konversi simbol Indodax ke Binance spot pair (USDT)."""
    sym = indodax_symbol.upper().strip()
    return _SYMBOL_OVERRIDE.get(sym, f"{sym}USDT")


def _to_binance_futures_symbol(indodax_symbol: str) -> str:
    """Konversi simbol Indodax ke Binance futures pair."""
    sym = indodax_symbol.upper().strip()
    # Futures seringkali sama dengan spot kecuali beberapa koin meme
    futures_override = {
        "SHIB": "1000SHIBUSDT",
        "PEPE": "1000PEPEUSDT",
        "FLOKI": "1000FLOKIUSDT",
    }
    return futures_override.get(sym, f"{sym}USDT")


# =============================================================================
# 1. TICKER 24H — Volume & Change Global
# =============================================================================
def fetch_binance_ticker_24h(symbol: str) -> dict:
    """Fetch data ticker 24h dari Binance spot.

    Returns:
        {
            "binance_price_usdt": float,
            "binance_volume_usdt": float,  # Volume 24h dalam USDT
            "binance_change_pct": float,   # Change 24h (%)
            "binance_high_usdt": float,
            "binance_low_usdt": float,
            "binance_trades_count": int,   # Jumlah trade 24h
        }
    """
    default = {
        "binance_price_usdt": 0.0,
        "binance_volume_usdt": 0.0,
        "binance_change_pct": 0.0,
        "binance_high_usdt": 0.0,
        "binance_low_usdt": 0.0,
        "binance_trades_count": 0,
    }
    pair = _to_binance_symbol(symbol)
    url = f"{BINANCE_SPOT_BASE}/api/v3/ticker/24hr"
    data = _cached_get(url, params={"symbol": pair})
    if not data or isinstance(data, list):
        return default
    return {
        "binance_price_usdt": _safe_float(data.get("lastPrice")),
        "binance_volume_usdt": _safe_float(data.get("quoteVolume")),
        "binance_change_pct": _safe_float(data.get("priceChangePercent")),
        "binance_high_usdt": _safe_float(data.get("highPrice")),
        "binance_low_usdt": _safe_float(data.get("lowPrice")),
        "binance_trades_count": int(_safe_float(data.get("count"))),
    }


def fetch_binance_tickers_bulk() -> dict[str, dict]:
    """Fetch semua ticker 24h sekaligus (1 API call) untuk efisiensi.

    Returns:
        dict[symbol_upper, ticker_data] — simbol tanpa 'USDT' suffix.
    """
    url = f"{BINANCE_SPOT_BASE}/api/v3/ticker/24hr"
    data = _cached_get(url, timeout=12)
    if not data or not isinstance(data, list):
        return {}
    result = {}
    for item in data:
        sym = item.get("symbol", "")
        if not sym.endswith("USDT"):
            continue
        base = sym[:-4]  # strip USDT
        result[base] = {
            "binance_price_usdt": _safe_float(item.get("lastPrice")),
            "binance_volume_usdt": _safe_float(item.get("quoteVolume")),
            "binance_change_pct": _safe_float(item.get("priceChangePercent")),
            "binance_high_usdt": _safe_float(item.get("highPrice")),
            "binance_low_usdt": _safe_float(item.get("lowPrice")),
            "binance_trades_count": int(_safe_float(item.get("count"))),
        }
    return result


# =============================================================================
# 2. FUNDING RATE — Sentimen Long vs Short (Futures)
# =============================================================================
def fetch_funding_rate(symbol: str) -> dict:
    """Fetch funding rate terbaru dari Binance Futures.

    Funding Rate > 0 = mayoritas LONG (bullish sentiment, tapi bisa juga crowded)
    Funding Rate < 0 = mayoritas SHORT (bearish sentiment, tapi bisa juga squeeze)

    Returns:
        {
            "funding_rate": float,       # e.g. 0.0001 = 0.01%
            "funding_pct": float,        # persentase: 0.01
            "funding_signal": str,       # "LONG_CROWDED", "BULLISH", "NEUTRAL", "BEARISH", "SHORT_SQUEEZE"
            "funding_annualized_pct": float,  # annualisasi: rate * 3 * 365
        }
    """
    default = {
        "funding_rate": 0.0,
        "funding_pct": 0.0,
        "funding_signal": "NO DATA",
        "funding_annualized_pct": 0.0,
    }
    pair = _to_binance_futures_symbol(symbol)
    url = f"{BINANCE_FUTURES_BASE}/fapi/v1/fundingRate"
    data = _cached_get(url, params={"symbol": pair, "limit": 1})
    if not data or not isinstance(data, list) or not data:
        return default

    rate = _safe_float(data[0].get("fundingRate"))
    pct = rate * 100
    annual = rate * 3 * 365 * 100  # 3x per hari * 365 hari

    if pct > 0.05:
        signal = "LONG CROWDED"   # Terlalu banyak long, risiko likuidasi
    elif pct > 0.01:
        signal = "BULLISH"        # Sentimen long moderat
    elif pct > -0.01:
        signal = "NEUTRAL"
    elif pct > -0.05:
        signal = "BEARISH"        # Sentimen short moderat
    else:
        signal = "SHORT SQUEEZE"  # Terlalu banyak short, potensi squeeze

    return {
        "funding_rate": rate,
        "funding_pct": round(pct, 4),
        "funding_signal": signal,
        "funding_annualized_pct": round(annual, 2),
    }


# =============================================================================
# 3. LONG/SHORT RATIO — Top Traders
# =============================================================================
def fetch_long_short_ratio(symbol: str, period: str = "5m") -> dict:
    """Fetch Long/Short ratio dari Binance Futures (top traders).

    period: "5m", "15m", "30m", "1h", "2h", "4h", "6h", "12h", "1d"

    Returns:
        {
            "long_ratio": float,     # 0.0 - 1.0
            "short_ratio": float,    # 0.0 - 1.0
            "ls_ratio": float,       # long/short (>1 = lebih banyak long)
            "ls_signal": str,        # "STRONG LONG", "LONG", "NEUTRAL", "SHORT", "STRONG SHORT"
        }
    """
    default = {
        "long_ratio": 0.5,
        "short_ratio": 0.5,
        "ls_ratio": 1.0,
        "ls_signal": "NO DATA",
    }
    pair = _to_binance_futures_symbol(symbol)
    url = f"{BINANCE_FUTURES_BASE}/futures/data/topLongShortAccountRatio"
    data = _cached_get(url, params={"symbol": pair, "period": period, "limit": 1})
    if not data or not isinstance(data, list) or not data:
        return default

    entry = data[0]
    long_r = _safe_float(entry.get("longAccount"), 0.5)
    short_r = _safe_float(entry.get("shortAccount"), 0.5)
    ls = long_r / short_r if short_r > 0 else 1.0

    if ls >= 2.0:
        signal = "STRONG LONG"
    elif ls >= 1.3:
        signal = "LONG"
    elif ls >= 0.77:
        signal = "NEUTRAL"
    elif ls >= 0.5:
        signal = "SHORT"
    else:
        signal = "STRONG SHORT"

    return {
        "long_ratio": round(long_r, 4),
        "short_ratio": round(short_r, 4),
        "ls_ratio": round(ls, 3),
        "ls_signal": signal,
    }


# =============================================================================
# 4. ORDER BOOK DEPTH — Buy/Sell Wall Detection
# =============================================================================
def fetch_order_book_pressure(symbol: str, depth_limit: int = 20) -> dict:
    """Fetch order book dan hitung buy/sell pressure.

    depth_limit: 5, 10, 20, 50, 100 (semakin besar semakin akurat tapi lambat)

    Returns:
        {
            "bid_volume": float,     # Total volume bid (buy)
            "ask_volume": float,     # Total volume ask (sell)
            "book_ratio": float,     # bid/ask (>1 = buy wall lebih tebal)
            "book_signal": str,      # "STRONG BUY WALL", "BUY WALL", "BALANCED", "SELL WALL", "STRONG SELL WALL"
            "spread_pct": float,     # Spread bid-ask (%)
        }
    """
    default = {
        "bid_volume": 0.0,
        "ask_volume": 0.0,
        "book_ratio": 1.0,
        "book_signal": "NO DATA",
        "spread_pct": 0.0,
    }
    pair = _to_binance_symbol(symbol)
    url = f"{BINANCE_SPOT_BASE}/api/v3/depth"
    data = _cached_get(url, params={"symbol": pair, "limit": depth_limit})
    if not data or not isinstance(data, dict):
        return default

    bids = data.get("bids", [])
    asks = data.get("asks", [])
    if not bids or not asks:
        return default

    bid_vol = sum(_safe_float(b[0]) * _safe_float(b[1]) for b in bids)
    ask_vol = sum(_safe_float(a[0]) * _safe_float(a[1]) for a in asks)
    ratio = bid_vol / ask_vol if ask_vol > 0 else 1.0

    best_bid = _safe_float(bids[0][0])
    best_ask = _safe_float(asks[0][0])
    spread = ((best_ask - best_bid) / best_ask * 100) if best_ask > 0 else 0.0

    if ratio >= 2.0:
        signal = "STRONG BUY WALL"
    elif ratio >= 1.4:
        signal = "BUY WALL"
    elif ratio >= 0.72:
        signal = "BALANCED"
    elif ratio >= 0.5:
        signal = "SELL WALL"
    else:
        signal = "STRONG SELL WALL"

    return {
        "bid_volume": round(bid_vol, 2),
        "ask_volume": round(ask_vol, 2),
        "book_ratio": round(ratio, 3),
        "book_signal": signal,
        "spread_pct": round(spread, 4),
    }


# =============================================================================
# 5. OPEN INTEREST — Total Posisi Terbuka (Futures)
# =============================================================================
def fetch_open_interest(symbol: str) -> dict:
    """Fetch open interest dari Binance Futures.

    Returns:
        {
            "open_interest": float,        # Total OI dalam kontrak
            "open_interest_usdt": float,   # Total OI dalam USDT (approx)
            "oi_signal": str,
        }
    """
    default = {
        "open_interest": 0.0,
        "open_interest_usdt": 0.0,
        "oi_signal": "NO DATA",
    }
    pair = _to_binance_futures_symbol(symbol)
    url = f"{BINANCE_FUTURES_BASE}/fapi/v1/openInterest"
    data = _cached_get(url, params={"symbol": pair})
    if not data or not isinstance(data, dict):
        return default
    oi = _safe_float(data.get("openInterest"))
    # Approximate USDT value (butuh harga saat ini)
    ticker = fetch_binance_ticker_24h(symbol)
    price = ticker.get("binance_price_usdt", 0)
    oi_usdt = oi * price

    return {
        "open_interest": round(oi, 4),
        "open_interest_usdt": round(oi_usdt, 2),
        "oi_signal": "AKTIF" if oi > 0 else "NO DATA",
    }


# =============================================================================
# 6. AGGREGATE BINANCE SENTIMENT — Score Adjustment
# =============================================================================
def fetch_binance_sentiment(symbol: str) -> dict:
    """Gabungkan semua data Binance menjadi satu skor sentimen.

    Memanggil funding rate, long/short ratio, dan order book sekaligus,
    lalu menghasilkan adjustment score tunggal untuk scoring engine.

    Returns:
        {
            "funding": dict,
            "long_short": dict,
            "order_book": dict,
            "binance_adjustment": int,    # -10 to +10
            "binance_signal": str,        # "VERY BULLISH", "BULLISH", "NEUTRAL", "BEARISH", "VERY BEARISH"
            "binance_notes": list[str],   # Penjelasan tiap komponen
            "available": bool,
        }
    """
    funding = fetch_funding_rate(symbol)
    ls = fetch_long_short_ratio(symbol)
    book = fetch_order_book_pressure(symbol)

    adjustment = 0
    notes: list[str] = []
    available = False

    # --- Funding Rate ---
    f_signal = funding.get("funding_signal", "NO DATA")
    if f_signal != "NO DATA":
        available = True
        if f_signal == "BULLISH":
            adjustment += 2
            notes.append(f"Funding +{funding['funding_pct']:.3f}% (bullish)")
        elif f_signal == "LONG CROWDED":
            adjustment -= 2  # Terlalu banyak long = risiko likuidasi massal
            notes.append(f"⚠️ Long crowded ({funding['funding_pct']:.3f}%)")
        elif f_signal == "BEARISH":
            adjustment -= 1
            notes.append(f"Funding negatif ({funding['funding_pct']:.3f}%)")
        elif f_signal == "SHORT SQUEEZE":
            adjustment += 3  # Potensi short squeeze!
            notes.append(f"🚀 Short squeeze potential ({funding['funding_pct']:.3f}%)")

    # --- Long/Short Ratio ---
    ls_signal = ls.get("ls_signal", "NO DATA")
    if ls_signal != "NO DATA":
        available = True
        if ls_signal == "STRONG LONG":
            adjustment += 2
            notes.append(f"Top traders {ls['ls_ratio']:.2f}x long")
        elif ls_signal == "LONG":
            adjustment += 1
            notes.append(f"Top traders condong long ({ls['ls_ratio']:.2f}x)")
        elif ls_signal == "SHORT":
            adjustment -= 1
            notes.append(f"Top traders condong short ({ls['ls_ratio']:.2f}x)")
        elif ls_signal == "STRONG SHORT":
            adjustment -= 2
            notes.append(f"Top traders strong short ({ls['ls_ratio']:.2f}x)")

    # --- Order Book ---
    b_signal = book.get("book_signal", "NO DATA")
    if b_signal != "NO DATA":
        available = True
        if b_signal == "STRONG BUY WALL":
            adjustment += 3
            notes.append(f"Buy wall kuat ({book['book_ratio']:.2f}x)")
        elif b_signal == "BUY WALL":
            adjustment += 1
            notes.append(f"Buy wall ({book['book_ratio']:.2f}x)")
        elif b_signal == "SELL WALL":
            adjustment -= 2
            notes.append(f"Sell wall ({book['book_ratio']:.2f}x)")
        elif b_signal == "STRONG SELL WALL":
            adjustment -= 3
            notes.append(f"⚠️ Sell wall tebal ({book['book_ratio']:.2f}x)")

    # Clamp
    adjustment = max(-10, min(10, adjustment))

    # Overall signal
    if adjustment >= 5:
        signal = "VERY BULLISH"
    elif adjustment >= 2:
        signal = "BULLISH"
    elif adjustment >= -1:
        signal = "NEUTRAL"
    elif adjustment >= -4:
        signal = "BEARISH"
    else:
        signal = "VERY BEARISH"

    return {
        "funding": funding,
        "long_short": ls,
        "order_book": book,
        "binance_adjustment": adjustment,
        "binance_signal": signal,
        "binance_notes": notes[:5],
        "available": available,
    }


# =============================================================================
# 7. BATCH SENTIMENT — Untuk Banyak Koin Sekaligus
# =============================================================================
def fetch_binance_sentiment_batch(symbols: list[str], max_workers: int = 5) -> dict[str, dict]:
    """Fetch sentimen Binance untuk banyak koin secara paralel.

    Returns:
        dict[symbol, sentiment_dict]
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    result = {}
    unique = list(set(symbols))
    if not unique:
        return result

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(fetch_binance_sentiment, sym): sym for sym in unique}
        for future in as_completed(futures):
            sym = futures[future]
            try:
                result[sym] = future.result()
            except Exception:
                result[sym] = {
                    "funding": {},
                    "long_short": {},
                    "order_book": {},
                    "binance_adjustment": 0,
                    "binance_signal": "ERROR",
                    "binance_notes": [],
                    "available": False,
                }
    return result


# =============================================================================
# 8. BINANCE VOLUME COMPARISON — Deteksi Volume Anomaly
# =============================================================================
def compare_volume_global(symbol: str, indodax_vol_idr: float) -> dict:
    """Bandingkan volume Indodax vs volume global Binance.

    Jika volume Indodax tiba-tiba spike tanpa diikuti volume global,
    kemungkinan besar itu manipulasi lokal (fake pump).

    Returns:
        {
            "global_vol_usdt": float,
            "local_vol_usd_approx": float,  # Indodax vol konversi ke USD
            "vol_ratio_local_global": float, # Rasio lokal/global
            "vol_anomaly": bool,             # True jika lokal spike tanpa global
            "vol_note": str,
        }
    """
    # Asumsi USD/IDR ≈ 16,500
    USD_IDR = 16_500
    local_usd = indodax_vol_idr / USD_IDR

    ticker = fetch_binance_ticker_24h(symbol)
    global_vol = ticker.get("binance_volume_usdt", 0)

    if global_vol <= 0:
        return {
            "global_vol_usdt": 0,
            "local_vol_usd_approx": round(local_usd, 2),
            "vol_ratio_local_global": 0,
            "vol_anomaly": False,
            "vol_note": "Data Binance tidak tersedia",
        }

    ratio = local_usd / global_vol if global_vol > 0 else 0

    # Anomaly detection: jika volume lokal > 5% dari volume global,
    # itu sangat tidak normal (Indodax biasanya < 1% volume Binance)
    anomaly = ratio > 0.05 and local_usd > 50_000

    note = ""
    if anomaly:
        note = f"⚠️ Volume lokal anomali ({ratio*100:.1f}% dari global)"
    elif global_vol > 100_000_000:
        note = f"Volume global tinggi (${global_vol/1e6:.1f}M)"
    elif global_vol > 10_000_000:
        note = f"Volume global moderat (${global_vol/1e6:.1f}M)"
    else:
        note = f"Volume global rendah (${global_vol/1e6:.2f}M)"

    return {
        "global_vol_usdt": round(global_vol, 2),
        "local_vol_usd_approx": round(local_usd, 2),
        "vol_ratio_local_global": round(ratio, 6),
        "vol_anomaly": anomaly,
        "vol_note": note,
    }


# =============================================================================
# 9. BINANCE KLINE (OHLCV) — Data candlestick dari Binance
# =============================================================================
def fetch_binance_klines(symbol: str, interval: str = "1h", limit: int = 100) -> list[dict]:
    """Fetch candlestick data dari Binance spot.

    interval: "1m", "3m", "5m", "15m", "30m", "1h", "2h", "4h", "6h", "8h",
              "12h", "1d", "3d", "1w", "1M"

    Returns:
        list of {time, open, high, low, close, volume}
    """
    pair = _to_binance_symbol(symbol)
    url = f"{BINANCE_SPOT_BASE}/api/v3/klines"
    data = _cached_get(url, params={"symbol": pair, "interval": interval, "limit": limit})
    if not data or not isinstance(data, list):
        return []

    result = []
    for k in data:
        if len(k) < 6:
            continue
        result.append({
            "time": int(k[0]) // 1000,
            "open": _safe_float(k[1]),
            "high": _safe_float(k[2]),
            "low": _safe_float(k[3]),
            "close": _safe_float(k[4]),
            "volume": _safe_float(k[5]),
        })
    return result


# =============================================================================
# 10. DIAGNOSTICS
# =============================================================================
def check_binance_connectivity() -> dict:
    """Test koneksi ke Binance API.

    Returns:
        {"spot_ok": bool, "futures_ok": bool, "latency_ms": int}
    """
    spot_ok = False
    futures_ok = False
    latency = 0

    try:
        t0 = time.time()
        resp = requests.get(f"{BINANCE_SPOT_BASE}/api/v3/ping", timeout=5)
        latency = int((time.time() - t0) * 1000)
        spot_ok = resp.status_code == 200
    except Exception:
        pass

    try:
        resp = requests.get(f"{BINANCE_FUTURES_BASE}/fapi/v1/ping", timeout=5)
        futures_ok = resp.status_code == 200
    except Exception:
        pass

    return {
        "spot_ok": spot_ok,
        "futures_ok": futures_ok,
        "latency_ms": latency,
    }
