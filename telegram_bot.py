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
import threading
import concurrent.futures
import requests
import pandas as pd
import json
from datetime import datetime, timezone, timedelta


# ─────────────────────────────────────────────────────────────────────────────
# AGGRESSIVE PRESET (terpusat)
# ─────────────────────────────────────────────────────────────────────────────
# Set AGGRESSIVE_PRESET=high untuk nyalain mode cari-cuan agresif. Preset ini
# memakai os.environ.setdefault, jadi env var yang sudah kamu set manual TETAP
# menang (preset tidak menimpa). HARUS dijalankan SEBELUM import modul lain
# (ml_engine, portfolio_manager) karena mereka baca env saat import.
#
# Catatan keamanan: preset TIDAK menyalakan real-money. Default tetap PAPER.
# Untuk real-money kamu wajib set AUTO_TRADE_ENABLED=true + PAPER_TRADING_MODE=false
# secara eksplisit.
def _apply_aggressive_preset():
    preset = str(os.environ.get("AGGRESSIVE_PRESET", "")).strip().lower()
    if preset not in {"high", "tinggi", "max", "ultra"}:
        return
    defaults = {
        # Sinyal scalp XGBoost: aktif + boost skor lebih besar
        "AGGRESSIVE_MODE": "1",
        "AGGRESSIVE_BOOST": "35",
        # Threshold ML diturunin → lebih banyak sinyal lolos
        "ML_PROB_THRESHOLD": "58",
        "ML_ADAPTIVE_BASE": "60",
        "ML_ADAPTIVE_MIN": "50",
        # Scan lebih luas + lebih sering
        "MAX_SCAN_COINS": "80",
        "MIN_VOLUME_IDR": "100000000",
        "LOOP_SLEEP_SECONDS": "20",
        # Lebih banyak posisi bareng
        "MAX_ACTIVE_TRADES": "12",
        "MAX_OPEN_POSITIONS": "12",
        # Scan paralel lebih kencang (hati-hati rate-limit)
        "SCAN_WORKERS": "8",
        # Alert/entry threshold dilonggarin
        "MIN_ALERT_SCORE": "60",
        "EARLY_MIN_SCORE": "50",
        # Guardrail tetap ON biar agresif tapi gak bunuh diri
        "MAX_DAILY_LOSS_IDR": os.environ.get("MAX_DAILY_LOSS_IDR", "150000"),
        "TRADE_COOLDOWN_SEC": os.environ.get("TRADE_COOLDOWN_SEC", "120"),
        # Keamanan: tetap PAPER kecuali user override eksplisit
        "PAPER_TRADING_MODE": "true",
    }
    for key, val in defaults.items():
        os.environ.setdefault(key, str(val))


_apply_aggressive_preset()

from keep_alive import keep_alive

from learning_engine import (
    apply_learning_adjustments,
    record_signal,
    train_from_prices,
    record_paper_signal,
)
from news_engine import apply_news_adjustments, build_news_profile
from ai_pilot import generate_signal_insight, generate_custom_explain
from core.applog import get_logger
from core.committee import build_committee, committee_summary_line
from core import command_router, execution_engine, portfolio_manager
from core.persistence import file_lock, atomic_write_json, read_json_safe

try:
    from ml_engine import predict_aggressive_scalp
except ImportError:
    predict_aggressive_scalp = None

# Binance global data (graceful import)
try:
    import binance_engine

    _BINANCE_OK = True
except ImportError:
    binance_engine = None  # type: ignore
    _BINANCE_OK = False

_LOGGER = get_logger("bot")


# === CONFIG ===
def _get_api_key(key_name):
    val = os.environ.get(key_name)
    if val:
        return val
    try:
        with open(".streamlit/secrets.toml", "r") as f:
            for line in f:
                if line.startswith(key_name):
                    return line.split("=")[1].strip().strip('"').strip("'")
    except (OSError, IndexError):
        pass
    return ""


GEMINI_API_KEY = _get_api_key("GEMINI_API_KEY")
DEEPSEEK_API_KEY = _get_api_key("DEEPSEEK_API_KEY")
OPENROUTER_API_KEY = _get_api_key("OPENROUTER_API_KEY")

BOT_TOKEN = _get_api_key("TELEGRAM_BOT_TOKEN")
CHAT_ID = _get_api_key("TELEGRAM_CHAT_ID")
INDODAX_REF = "narwanpratanta"
WIB = timezone(timedelta(hours=7))


def env_bool(name, default=False):
    return str(os.environ.get(name, str(default))).lower() in {"1", "true", "yes", "on"}


# Auto Trade Settings
AUTO_TRADE_ENABLED = env_bool("AUTO_TRADE_ENABLED", False)
PAPER_TRADING_MODE = env_bool("PAPER_TRADING_MODE", True)
CONFIRM_BEFORE_TRADE = env_bool("CONFIRM_BEFORE_TRADE", True)
MAX_TRADE_IDR = float(os.environ.get("MAX_TRADE_IDR", "50000"))


def _get_trade_amount(alloc_pct):
    if str(os.environ.get("DYNAMIC_POSITION_SIZING", "True")).lower() in {
        "1",
        "true",
        "yes",
        "on",
    }:
        # alloc_pct ranges from 0.0 to 10.0 (max 10% allocation)
        factor = max(0.0, min(10.0, float(alloc_pct or 0))) / 10.0
        amount = MAX_TRADE_IDR * factor
        # Indodax minimum order size is 10,000 IDR
        if amount > 0 and amount < 10000:
            amount = 10000.0
        return round(amount, 0)
    return MAX_TRADE_IDR


BLUE_CHIPS = {"BTC", "ETH", "BNB", "SOL", "XRP", "ADA"}
MICIN_COINS = {"DOGE", "PEPE", "SHIB", "BONK", "FLOKI", "LUNC", "BTT", "JASMY"}
STABLECOINS = {"USDC", "USDT", "DAI", "BUSD", "TUSD", "USDP", "PYUSD", "FDUSD"}

# Maks koin yang di-scan tiap siklus. Dynamic by volume.
MAX_SCAN_COINS = int(os.environ.get("MAX_SCAN_COINS", "40"))
MIN_VOLUME_IDR = float(os.environ.get("MIN_VOLUME_IDR", "200000000"))  # 200jt minimal


def get_scan_coins(all_coins_dict, count=None):
    """Ambil top N koin by volume dari semua pair yg ada."""
    if count is None:
        count = MAX_SCAN_COINS
    sorted_coins = sorted(
        all_coins_dict.values(), key=lambda x: x.get("vol_idr", 0), reverse=True
    )
    filtered = [c for c in sorted_coins if c.get("vol_idr", 0) >= MIN_VOLUME_IDR]
    if not filtered:
        filtered = sorted_coins[:count]  # fallback kalo semua volume kecil
    return {c["symbol"]: c["pair"] for c in filtered[:count]}


TELEGRAM_CHANNEL = "https://t.me/+VPlOcY2wFGA0NWU1"

ENABLE_FOMO_ALERTS = env_bool("ENABLE_FOMO_ALERTS", True)
ENABLE_CONFLUENCE_ALERTS = env_bool("ENABLE_CONFLUENCE_ALERTS", True)
ENABLE_EARLY_ALERTS = env_bool("ENABLE_EARLY_ALERTS", True)

# === ANTI-SPAM CONTROL ===
# Default 60s biar scan 3x lebih cepet daripada 180s lama.
LOOP_SLEEP_SECONDS = int(os.environ.get("LOOP_SLEEP_SECONDS", "60"))

FOMO_GLOBAL_COOLDOWN_SEC = int(os.environ.get("FOMO_GLOBAL_COOLDOWN_SEC", "1800"))
FOMO_SYMBOL_COOLDOWN_SEC = int(
    os.environ.get("FOMO_SYMBOL_COOLDOWN_SEC", str(24 * 3600))
)

CONFLUENCE_SYMBOL_COOLDOWN_SEC = int(
    os.environ.get("CONFLUENCE_SYMBOL_COOLDOWN_SEC", str(24 * 3600))
)
CONFLUENCE_MAX_ALERTS_PER_CYCLE = int(
    os.environ.get("CONFLUENCE_MAX_ALERTS_PER_CYCLE", "1")
)

# Early-entry punya cooldown sendiri supaya nggak nabrak alert konfirmasi.
EARLY_SYMBOL_COOLDOWN_SEC = int(
    os.environ.get("EARLY_SYMBOL_COOLDOWN_SEC", str(4 * 3600))
)
EARLY_MAX_ALERTS_PER_CYCLE = int(os.environ.get("EARLY_MAX_ALERTS_PER_CYCLE", "2"))

MESSAGE_DUPLICATE_TTL_SEC = int(
    os.environ.get("MESSAGE_DUPLICATE_TTL_SEC", str(12 * 3600))
)
ACTIVE_SIGNAL_TTL_SEC = int(os.environ.get("ACTIVE_SIGNAL_TTL_SEC", str(72 * 3600)))
NEWS_REFRESH_SECONDS = int(os.environ.get("NEWS_REFRESH_SECONDS", "900"))

MIN_ALERT_SCORE = int(os.environ.get("MIN_ALERT_SCORE", "68"))
MIN_ALERT_VOLUME_IDR = float(os.environ.get("MIN_ALERT_VOLUME_IDR", "500000000"))
MAX_ALERT_RANGE_POS = float(os.environ.get("MAX_ALERT_RANGE_POS", "88"))

# Threshold khusus EARLY ENTRY: dilonggarin biar masuk sebelum pump meledak.
EARLY_MIN_SCORE = int(os.environ.get("EARLY_MIN_SCORE", "58"))
EARLY_MIN_VOLUME_IDR = float(os.environ.get("EARLY_MIN_VOLUME_IDR", "300000000"))
EARLY_MAX_RANGE_POS = float(
    os.environ.get("EARLY_MAX_RANGE_POS", "70")
)  # harus masih di paruh bawah range 24h
EARLY_MIN_SETUP_STRENGTH = int(
    os.environ.get("EARLY_MIN_SETUP_STRENGTH", "3")
)  # min checklist setup terpenuhi


# === STATE ===
_BOT_START_TS = time.time()  # buat /ping uptime
_CYCLE_COUNT = 0  # diupdate tiap siklus loop utama
_LISTENER_STARTED = False  # guard supaya listener thread cuma sekali
_last_sinyal_date = None

_last_summary_date = None
_fomo_sent_symbols = {}
_confluence_sent_symbols = {}  # track real-time confluence alerts
_early_sent_symbols = {}  # track EARLY entry alerts (pre-pump)
_active_signals = {}  # track sinyal beli aktif untuk TP/SL monitor
_last_fomo_alert_time = 0  # track last global FOMO alert to prevent spamming
_message_fingerprints = {}  # Anti-duplicate message fingerprint cache
_last_news_profile = None
_last_news_profile_at = 0


def _default_daily_stats():
    return {
        "tp_hit": 0,
        "sl_hit": 0,
        "signals_sent": 0,
        "daily_loss_pct": 0.0,
        "consecutive_losses": 0,
    }


_daily_stats = _default_daily_stats()


def _ensure_daily_stats_fields():
    global _daily_stats
    if not isinstance(_daily_stats, dict):
        _daily_stats = _default_daily_stats()
    defaults = _default_daily_stats()
    for key, value in defaults.items():
        _daily_stats.setdefault(key, value)
    return _daily_stats


def _safe_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _record_trade_close_for_risk(pnl_pct):
    stats = _ensure_daily_stats_fields()
    pnl = _safe_float(pnl_pct, 0.0)
    if pnl < 0:
        stats["daily_loss_pct"] = max(
            0.0, _safe_float(stats.get("daily_loss_pct"), 0.0)
        ) + abs(pnl)
        stats["consecutive_losses"] = (
            int(max(0, _safe_float(stats.get("consecutive_losses"), 0))) + 1
        )
    else:
        stats["consecutive_losses"] = 0


def _total_capital_hint():
    return os.environ.get("TOTAL_CAPITAL_IDR")


def _trade_risk_metadata(source, risk_tag=None, market_state=None):
    return {
        "source": source,
        "portfolio_state": portfolio_manager._load_portfolio(),
        "daily_stats": _ensure_daily_stats_fields(),
        "total_capital_idr": _total_capital_hint(),
        "market_state": market_state,
        "risk_tag": risk_tag,
    }


def _save_executed_buy_position(result, symbol, tp1, tp2, sl, trade_type):
    saved = portfolio_manager.save_position(
        symbol=symbol.lower(),
        buy_price=result["avg_price"],
        amount_coin=result["received_coin"],
        tp1=tp1,
        tp2=tp2,
        sl=sl,
        trade_type=trade_type,
        mode=result.get("mode", "paper"),
        entry_features=result.get("metadata", {}).get("entry_features"),
    )
    if saved:
        return True
    error = "Order executed but portfolio position could not be saved"
    if result.get("mode") == "real":
        portfolio_manager.record_order_recovery(
            symbol.lower(),
            "buy",
            result.get("spent_idr"),
            result.get("avg_price"),
            result,
            trade_type,
            error,
        )
    _LOGGER.error(f"{error}: {symbol.upper()}")
    return False


def _format_trade_proposal_message(
    symbol, action_label, amount_idr, price, tp1, tp2, sl, risk_level, reason
):
    try:
        ttl = int(os.environ.get("PENDING_TRADE_TTL_MINUTES", "10"))
    except (TypeError, ValueError):
        ttl = 10
    if ttl <= 0:
        ttl = 10
    return (
        f"{symbol.upper()} memberi sinyal {action_label}.\n"
        f"Alokasi aman: Rp{amount_idr:,.0f}\n"
        f"Risk: {risk_level or '-'}\n"
        f"Entry estimasi: {format_idr(price)}\n"
        f"TP1: {format_idr(tp1)}\n"
        f"TP2: {format_idr(tp2)}\n"
        f"SL: {format_idr(sl)}\n"
        f"Alasan: {reason or '-'}\n"
        f"Balas: BUY {symbol.upper()} {int(amount_idr)} untuk eksekusi.\n"
        f"Balas: CANCEL {symbol.upper()} untuk membatalkan.\n"
        f"Proposal berlaku {ttl} menit."
    )


def _telegram_router_context(symbol=None):
    context = {
        "portfolio_state": portfolio_manager._load_portfolio(),
        "daily_stats": _ensure_daily_stats_fields(),
        "total_capital_idr": _total_capital_hint(),
    }
    clean_symbol = str(symbol or "").strip().upper()
    if clean_symbol:
        try:
            all_coins = fetch_all_tickers()
            ticker = (
                all_coins.get(clean_symbol) if isinstance(all_coins, dict) else None
            )
            if isinstance(ticker, dict):
                context["price"] = ticker.get("price")
            elif ticker:
                context["price"] = ticker
        except Exception as e:
            log(f"Gagal ambil harga untuk command {clean_symbol}: {e}", "warning")
    return context


def _format_router_response(result: dict) -> str:
    if not isinstance(result, dict):
        return "Command diproses."
    if result.get("command", {}).get("type") == "RISK" and isinstance(
        result.get("risk"), dict
    ):
        risk = result["risk"]
        return (
            "*RISK STATUS*\n"
            f"Status: {risk.get('status')}\n"
            f"Risk level: {risk.get('risk_level')}\n"
            f"Open positions: {risk.get('open_positions')}\n"
            f"Daily loss: {risk.get('daily_loss_pct', 0):.2f}%\n"
            f"Consecutive losses: {risk.get('consecutive_losses', 0)}"
        )
    if result.get("command", {}).get("type") == "STATUS":
        pending = [p for p in result.get("pending", []) if p.get("status") == "PENDING"]
        return f"Bot aktif. Pending proposal: {len(pending)}"
    trade_result = result.get("result")
    if isinstance(trade_result, dict):
        status = "SUKSES" if trade_result.get("success") else "DIBLOKIR/GAGAL"
        mode = trade_result.get("mode", "-")
        action = trade_result.get("action", "-").upper()
        symbol = trade_result.get("symbol", "-").upper()
        detail = trade_result.get("error") or trade_result.get("reason", "")
        return f"{status}: {action} {symbol} ({mode})\n{detail}"
    return result.get("message", "Command diproses.")


def _state_file_path():
    """Simpan bot_state di direktori persisten kalau ada (HF /data), supaya
    state bot tidak hilang tiap restart. Fallback ke working dir."""
    override = os.environ.get("SIGNAL_JOURNAL_DIR")
    for base in (override, "/data"):
        if not base:
            continue
        try:
            if os.path.isdir(base) and os.access(base, os.W_OK):
                return os.path.join(base, "bot_state.json")
        except OSError:
            pass
    return "bot_state.json"


STATE_FILE = _state_file_path()


def load_bot_state():
    global \
        _last_sinyal_date, \
        _last_summary_date, \
        _fomo_sent_symbols, \
        _confluence_sent_symbols, \
        _early_sent_symbols, \
        _active_signals, \
        _daily_stats, \
        _last_fomo_alert_time, \
        _message_fingerprints
    if not os.path.exists(STATE_FILE):
        log("No state file found. Starting fresh.")
        return
    try:
        with file_lock(STATE_FILE):
            data = read_json_safe(STATE_FILE, {})
        if not data:
            log("No state loaded or empty state file.")
            return
        _last_sinyal_date = data.get("last_sinyal_date", _last_sinyal_date)
        _last_summary_date = data.get("last_summary_date", _last_summary_date)
        _fomo_sent_symbols = data.get("fomo_sent_symbols", _fomo_sent_symbols)
        _confluence_sent_symbols = data.get(
            "confluence_sent_symbols", _confluence_sent_symbols
        )
        _early_sent_symbols = data.get("early_sent_symbols", _early_sent_symbols)
        _active_signals = data.get("active_signals", _active_signals)
        _daily_stats = data.get("daily_stats", _daily_stats)
        _ensure_daily_stats_fields()
        _last_fomo_alert_time = data.get("last_fomo_alert_time", _last_fomo_alert_time)
        _message_fingerprints = data.get("message_fingerprints", _message_fingerprints)

        # Convert _active_signals hit back to set (JSON arrays become lists)
        for sym in _active_signals:
            if "hit" in _active_signals[sym] and isinstance(
                _active_signals[sym]["hit"], list
            ):
                _active_signals[sym]["hit"] = set(_active_signals[sym]["hit"])

        log("Bot state successfully loaded from bot_state.json")
    except Exception as e:
        log(f"Error loading bot state: {e}")


def save_bot_state():
    global \
        _last_sinyal_date, \
        _last_summary_date, \
        _fomo_sent_symbols, \
        _confluence_sent_symbols, \
        _early_sent_symbols, \
        _active_signals, \
        _daily_stats, \
        _last_fomo_alert_time, \
        _message_fingerprints
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
        }

        with file_lock(STATE_FILE):
            atomic_write_json(STATE_FILE, data)
    except Exception as e:
        log(f"Error saving bot state: {e}")


def log(msg, level="info"):
    """Log terstruktur (default INFO). Kompatibel: pemanggilan lama log(msg)
    tetap jalan; bisa juga log(msg, "warning") / log(msg, "error")."""
    getattr(_LOGGER, level, _LOGGER.info)(msg)


def clamp(value, lower, upper):
    return max(lower, min(upper, value))


# Indikator teknikal & analisis sinyal: sumber kebenaran tunggal di core.indicators
# (sebelumnya diduplikasi byte-for-byte di app.py & telegram_bot.py).
from core.indicators import (
    build_verdict,
    compute_adx,
    compute_atr,
    compute_backtest,
    compute_bollinger,
    compute_confluence_signal,
    compute_dynamic_walls,
    compute_ema,
    compute_ema200_trend,
    compute_macd,
    compute_ml_forecast,
    compute_multi_timeframe_confirmation,
    compute_rsi,
    compute_static_sr,
    compute_supertrend,
    compute_volume_analysis,
    compute_volume_anomaly,
    detect_bullish_pinbar,
    fetch_candles,
    is_entry_action,
)
from core.analysis import (
    compute_allocation,
    compute_base_score,
    compute_risk_level,
    compute_trade_levels,
    decide_action,
)


def apply_bot_learning(result):
    """Adjust score/allocation from historical signal outcomes."""
    apply_learning_adjustments([result])
    return result


def get_bot_news_profile(force=False):
    global _last_news_profile, _last_news_profile_at
    now_ts = time.time()
    if (
        force
        or _last_news_profile is None
        or now_ts - _last_news_profile_at >= NEWS_REFRESH_SECONDS
    ):
        _last_news_profile = build_news_profile(
            symbols=[s for s in get_scan_coins({}).keys()] + list(MICIN_COINS)
        )
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
    payload["allocation_pct"] = payload.get(
        "allocation_pct", payload.get("alloc_pct", 0)
    )
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
                "symbol": symbol,
                "pair": pair,
                "price": price,
                "change": round(change, 2),
                "vol_idr": float(info.get("vol_idr", 0)),
                "high": float(info.get("high", 0)),
                "low": float(info.get("low", 0)),
            }
        return all_coins
    except Exception as e:
        log(f"Fetch error: {e}", "error")
        return {}


# =============================================================================
# TECHNICAL INDICATORS
# =============================================================================


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

    # --- Binance global sentiment ---
    binance_data = {}
    binance_adj = 0
    if _BINANCE_OK:
        try:
            binance_data = binance_engine.fetch_binance_sentiment(symbol)
            if binance_data.get("available"):
                binance_adj = binance_data.get("binance_adjustment", 0)
        except Exception:
            pass

    # --- SCORING & KEPUTUSAN (terpadu via core.analysis: identik dgn web) ---
    base, _components = compute_base_score(
        change=change,
        ema_trend_pct=ema_trend_pct,
        macd_signal=macd_signal,
        rsi=rsi,
        supertrend=supertrend,
        vol_label=vol_label,
        bb_signal=bb["bb_signal"],
        adx_trend=adx_data["trend"],
        ml=ml,
        bt=bt,
        mtf_adjustment=mtf["mtf_adjustment"],
        vol_idr=vol_idr,
        symbol=symbol,
        is_micin=(symbol in MICIN_COINS),
        range_pos=range_pos,
    )
    # Tambahkan Binance adjustment ke base score (identik dgn web)
    base += binance_adj

    # Aggressive Scalp (XGBoost) — BOOST dari 15 jadi 25
    xgb_prob = 0.0
    xgb_label = "NO DATA"
    entry_feats = {}
    boost_mult = float(os.environ.get("AGGRESSIVE_BOOST", "25"))
    if predict_aggressive_scalp and os.environ.get("AGGRESSIVE_MODE") == "1":
        xgb_scalp = predict_aggressive_scalp(candles)
        entry_feats = xgb_scalp.get("entry_features", {})
        if xgb_scalp.get("is_scalp_valid"):
            base += boost_mult
            xgb_prob = xgb_scalp.get("prob_up_pct", 0)
            xgb_label = "SCALP BUY"
            # Ensemble detail log
            detail = xgb_scalp.get("ensemble_detail")
            if detail:
                base += min(5, detail.get("n_models", 0) * 2)  # +2 per model tambahan
                wf1 = detail.get("walk_f1")
                if wf1 and wf1 > 0.6:
                    base += 5  # Walk-forward F1 > 60% → extra boost

    momentum = change
    score = int(clamp(round(base), 0, 100))

    # Risk level (sebelum verdict, dibutuhkan committee)
    risk_level = compute_risk_level(
        change, vol_idr, rsi, macd_signal, supertrend, range_pos, ml, bt, symbol=symbol
    )

    # Verdict committee
    verdict, verdict_net, size_mult = build_verdict(
        score, rsi, macd_signal, supertrend, adx_data, ml, bt, risk_level, vol_idr
    )

    # Keputusan action + semua gate (threshold, confluence, anti-FOMO, MTF, verdict)
    # IDENTIK dengan web — tidak akan ada lagi sinyal bertentangan utk koin yg sama.
    action, emoji, score = decide_action(
        score=score,
        change=change,
        confluence=confluence,
        range_pos=range_pos,
        mtf_adjustment=mtf["mtf_adjustment"],
        regime_allow_aggressive=True,
        verdict=verdict,
    )

    # Dynamic TP/SL & alokasi terpadu via core.analysis (ATR-adaptif, IDENTIK web).
    atr = compute_atr(candles)
    levels = compute_trade_levels(price, change, score, risk_level, atr=atr)
    tp1 = levels["tp1"]
    tp2 = levels["tp2"]
    tp3 = levels["target"]
    sl = levels["stop_loss"]
    trailing = levels["trailing_pct"]
    alloc = compute_allocation(
        score, risk_level, confluence, action, size_mult=size_mult, market_mult=1.0
    )

    return {
        "symbol": symbol,
        "price": price,
        "change": change,
        "vol_idr": vol_idr,
        "score": score,
        "action": action,
        "emoji": emoji,
        "rsi": round(rsi, 1),
        "ema_bias": ema_bias,
        "macd_signal": macd_signal,
        "bb_signal": bb["bb_signal"],
        "supertrend": supertrend,
        "adx": adx_data["adx"],
        "adx_trend": adx_data["trend"],
        "ml_prob": xgb_prob if xgb_prob > 0 else ml["ml_prob"],
        "ml_label": xgb_label if xgb_label != "NO DATA" else ml["ml_label"],
        "ml_conf": ml["ml_conf"],
        "bt_wr": bt["bt_wr"],
        "bt_trades": bt["bt_trades"],
        "bt_label": bt["bt_label"],
        "verdict": verdict,
        "verdict_net": verdict_net,
        "vol_label": vol_label,
        "risk_level": risk_level,
        "tp1": tp1,
        "tp2": tp2,
        "tp3": tp3,
        "stop_loss": sl,
        "trailing_pct": round(trailing, 1),
        "alloc_pct": round(alloc, 1),
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
        # Binance global sentiment
        "binance_signal": binance_data.get("binance_signal", "NO DATA"),
        "binance_adjustment": binance_data.get("binance_adjustment", 0),
        "binance_notes": binance_data.get("binance_notes", []),
        "binance_funding_signal": binance_data.get("funding", {}).get(
            "funding_signal", "NO DATA"
        ),
        "binance_funding_pct": binance_data.get("funding", {}).get("funding_pct", 0),
        "binance_ls_signal": binance_data.get("long_short", {}).get(
            "ls_signal", "NO DATA"
        ),
        "binance_ls_ratio": binance_data.get("long_short", {}).get("ls_ratio", 0),
        "binance_book_signal": binance_data.get("order_book", {}).get(
            "book_signal", "NO DATA"
        ),
        "binance_book_ratio": binance_data.get("order_book", {}).get("book_ratio", 0),
        "binance_available": binance_data.get("available", False),
        "entry_features": entry_feats,
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
    if value is None:
        return "-"
    if value >= 1_000_000_000:
        return f"Rp{value / 1_000_000_000:,.2f}M"
    if value >= 1_000_000:
        return f"Rp{value / 1_000_000:,.1f}JT"
    if value >= 1_000:
        return f"Rp{value:,.0f}"
    return f"Rp{value:,.2f}"


import hashlib
import re



def _message_fingerprint(text):
    normalized = re.sub(r"\d+(?:[.,]\d+)?", "#", str(text))
    normalized = re.sub(r"\s+", " ", normalized).strip().lower()
    return hashlib.sha256(normalized.encode()).hexdigest()


_reply_context = threading.local()


import queue as _queue_mod
import subprocess

# ── ASYNC SEND QUEUE ────────────────────────────────────────────────────────
# Semua pesan Telegram dikirim lewat background thread supaya TIDAK PERNAH
# memblokir bot loop / listener, bahkan kalau network HF → Telegram lambat.
_send_queue: _queue_mod.Queue = _queue_mod.Queue(maxsize=200)
_SEND_WORKER_STARTED = False


def _tg_send_worker():
    """Background worker: ambil pesan dari queue, kirim ke Telegram."""
    while True:
        try:
            item = _send_queue.get(timeout=60)
        except _queue_mod.Empty:
            continue
        if item is None:
            break
        url, payload = item
        _do_send_with_fallback(url, payload)
        _send_queue.task_done()
        time.sleep(0.3)  # rate-limit


def _do_send_with_fallback(url, payload):
    """Kirim pesan: coba http.client (stdlib) → curl → requests."""
    import json as _json
    import http.client
    import ssl
    import urllib.parse

    parsed = urllib.parse.urlparse(url)
    path = parsed.path

    body = _json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json", "Content-Length": str(len(body))}

    # ── Attempt 1: http.client (stdlib) — completely different SSL stack ──
    for attempt in range(3):
        try:
            ctx = ssl.create_default_context()
            conn = http.client.HTTPSConnection(
                parsed.hostname, timeout=60, context=ctx
            )
            conn.request("POST", path, body=body, headers=headers)
            resp = conn.getresponse()
            resp_body = resp.read().decode("utf-8")
            conn.close()
            resp_data = _json.loads(resp_body)
            if resp_data.get("ok"):
                log("TG send OK (http.client)")
                return True
            if "parse" in str(resp_data.get("description", "")).lower():
                payload.pop("parse_mode", None)
                body = _json.dumps(payload).encode("utf-8")
                headers["Content-Length"] = str(len(body))
                continue
            log(f"TG http.client fail: {resp_data.get('description', '?')}")
        except Exception as e:
            log(f"http.client attempt {attempt+1}: {e}", "warning")
        time.sleep(2 * (attempt + 1))

    # ── Attempt 2: curl (system binary) ──
    for attempt in range(2):
        try:
            curl_result = subprocess.run(
                [
                    "curl", "-s", "-X", "POST", url,
                    "-H", "Content-Type: application/json",
                    "-d", _json.dumps(payload),
                    "--connect-timeout", "10",
                    "--max-time", "60",
                ],
                capture_output=True, text=True, timeout=65,
            )
            if curl_result.returncode == 0:
                resp_data = _json.loads(curl_result.stdout)
                if resp_data.get("ok"):
                    log("TG send OK (curl)")
                    return True
                if "parse" in str(resp_data.get("description", "")).lower():
                    payload.pop("parse_mode", None)
                    continue
        except FileNotFoundError:
            break  # curl not installed, skip
        except Exception as e:
            log(f"curl attempt {attempt+1}: {e}", "warning")
        time.sleep(3)

    # ── Attempt 3: Python requests ──
    for attempt in range(2):
        try:
            resp = requests.post(url, json=payload, timeout=60)
            result = resp.json()
            if result.get("ok"):
                log("TG send OK (requests)")
                return True
            if "parse" in str(result.get("description", "")).lower():
                payload.pop("parse_mode", None)
                continue
        except Exception as e:
            log(f"requests attempt {attempt+1}: {e}", "warning")
        time.sleep(3)

    log("Send GAGAL setelah semua percobaan (http.client + curl + requests)", "error")
    return False


def _start_send_worker():
    global _SEND_WORKER_STARTED
    if _SEND_WORKER_STARTED:
        return
    t = threading.Thread(target=_tg_send_worker, name="tg-sender", daemon=True)
    t.start()
    _SEND_WORKER_STARTED = True
    log("Telegram send worker thread aktif.")


def send_message(text, notify=False, force=False):
    global _message_fingerprints

    target_chat_id = getattr(_reply_context, "chat_id", None) or CHAT_ID

    if not BOT_TOKEN or not target_chat_id:
        return False

    now_ts = time.time()

    if not force:
        fp = _message_fingerprint(text)

        # cleanup cache
        _message_fingerprints = {
            k: v
            for k, v in _message_fingerprints.items()
            if now_ts - v < MESSAGE_DUPLICATE_TTL_SEC
        }

        if fp in _message_fingerprints:
            return False

        _message_fingerprints[fp] = now_ts

    _start_send_worker()

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    # Split panjang
    chunks = [text] if len(text) <= 4096 else _split_text(text)
    for chunk in chunks:
        payload = {
            "chat_id": target_chat_id,
            "text": chunk,
            "parse_mode": "Markdown",
            "disable_notification": not notify,
        }
        try:
            _send_queue.put_nowait((url, payload))
        except _queue_mod.Full:
            log("Send queue penuh, drop message", "warning")
            return False
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
    mode_emoji = {
        "agresif": "🟢 AGRESIF",
        "normal": "🟡 NORMAL",
        "defensif": "🔴 DEFENSIF",
    }[mode]

    # Fetch candles + analyze all scan coins
    scan_coins = get_scan_coins(all_coins)
    signals = []
    for sym, pair in scan_coins.items():
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
    priority = {
        "BELI KUAT": 0,
        "CICIL BELI": 1,
        "WATCH": 2,
        "JANGAN BELI": 3,
        "HINDARI": 4,
    }
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
        lines.append(
            f"✅ *{buy_count} koin layak beli* — pilih 1-2 terbaik, jangan serakah."
        )
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
        if s.get("binance_available") and s.get("binance_signal") not in (
            "NO DATA",
            "NEUTRAL",
        ):
            bits.append(f"Binance {str(s['binance_signal']).lower()}")
        if s.get("news_label") and s.get("news_label") != "NO DATA":
            bits.append(f"berita {str(s['news_label']).lower()}")
        return " · ".join(bits[:4]) if bits else "momentum + likuiditas"

    # --- BAGIAN 1: SINYAL BELI (detail lengkap tapi rapi) ---
    if buy_signals:
        for s in buy_signals:
            pair_url = (
                (
                    scan_coins.get(s["symbol"])
                    or s.get("pair", s["symbol"].lower() + "_idr")
                )
                .upper()
                .replace("_", "")
            )
            link = f"https://indodax.com/market/{pair_url}?ref={INDODAX_REF}"
            ch = f"+{s['change']:.2f}" if s["change"] >= 0 else f"{s['change']:.2f}"

            lines.append(
                f"{s['emoji']} *{s['symbol']} — {s['action']}*  ·  Skor {s['score']}/100"
            )
            lines.append(
                f"   💵 Harga {format_idr(s['price'])} ({ch}%)  ·  Risiko {s['risk_level']}"
            )
            lines.append(
                f"   🎯 Entry sekarang → TP {format_idr(s['tp1'])} / {format_idr(s['tp2'])} / {format_idr(s['tp3'])}"
            )
            lines.append(
                f"   🛑 Stop loss {format_idr(s['stop_loss'])}  ·  trailing {s['trailing_pct']}%"
            )
            lines.append(f"   💰 Alokasi {s['alloc_pct']}% modal")
            lines.append(f"   📋 Kenapa: {_why_line(s)}")
            _com = build_committee(s)
            lines.append(f"   🧑‍⚖️ {committee_summary_line(_com)}")
            # Binance global data
            if s.get("binance_available"):
                bn_emoji = (
                    "🟢"
                    if s.get("binance_adjustment", 0) > 0
                    else "🔴"
                    if s.get("binance_adjustment", 0) < 0
                    else "⚪"
                )
                lines.append(
                    f"   {bn_emoji} Binance: {s.get('binance_signal', 'NO DATA')} (adj {s['binance_adjustment']:+d})"
                )
            lines.append(f"   👉 [BELI DI INDODAX]({link})")
            lines.append("")

            # Trade execution for BELI KUAT. Defaults to paper mode unless real trade is explicitly enabled.
            if (AUTO_TRADE_ENABLED or PAPER_TRADING_MODE) and s[
                "action"
            ] == "BELI KUAT":
                trade_amount = _get_trade_amount(s.get("alloc_pct", 10.0))
                try:
                    if trade_amount <= 0:
                        lines.append("🤖 *TRADE DIBLOKIR:* Alokasi 0% (Dilarang AI karena riwayat coin ini sering loss / Winrate buruk).")
                    elif CONFIRM_BEFORE_TRADE:
                        command_router.create_buy_confirmation_proposal(
                            s["symbol"].lower(),
                            trade_amount,
                            float(s["price"]),
                            tp1=s["tp1"],
                            tp2=s["tp2"],
                            sl=s["stop_loss"],
                            risk_level=s.get("risk_level"),
                            reason="BELI KUAT",
                            metadata=_trade_risk_metadata(
                                "daily_signal",
                                risk_tag=s.get("risk_level"),
                                market_state={"risk_level": s.get("risk_level")},
                            ),
                        )
                        lines.append("*PROPOSAL TRADE MENUNGGU KONFIRMASI*")
                        lines.append(
                            _format_trade_proposal_message(
                                s["symbol"],
                                "BELI KUAT",
                                trade_amount,
                                float(s["price"]),
                                s["tp1"],
                                s["tp2"],
                                s["stop_loss"],
                                s.get("risk_level"),
                                "BELI KUAT",
                            )
                        )
                    else:
                        res_buy = execution_engine.execute_buy(
                            s["symbol"].lower(),
                            trade_amount,
                            float(s["price"]),
                            reason="BELI KUAT",
                            metadata={
                                **_trade_risk_metadata(
                                    "daily_signal",
                                    risk_tag=s.get("risk_level"),
                                    market_state={"risk_level": s.get("risk_level")},
                                ),
                                "entry_features": s.get("entry_features"),
                            },
                        )
                        if res_buy.get("success"):
                            received = res_buy["received_coin"]
                            avg_price = res_buy["avg_price"]
                            spent = res_buy.get("spent_idr", trade_amount)
                            saved = _save_executed_buy_position(
                                res_buy,
                                s["symbol"],
                                tp1=s["tp1"],
                                tp2=s["tp2"],
                                sl=s["stop_loss"],
                                trade_type="BELI KUAT",
                            )
                            if saved:
                                trade_label = (
                                    "PAPER-TRADE SIMULASI"
                                    if res_buy.get("mode") == "paper"
                                    else "AUTO-TRADE SUKSES"
                                )
                                lines.append(f"🤖 *{trade_label}!*")
                                lines.append(
                                    f"   Beli: {received} {s['symbol']} (Rp{spent:,.0f})"
                                )
                                lines.append(f"   Harga Rata-rata: Rp{avg_price:,.0f}")
                                lines.append(f"   Mode Kawal TP/SL diaktifkan 🛡️")
                            else:
                                lines.append(
                                    "🤖 *ORDER TERJADI, PENCATATAN PORTFOLIO GAGAL. CEK RECOVERY JOURNAL.*"
                                )
                        else:
                            lines.append(
                                f"🤖 *TRADE DIBLOKIR/GAGAL:* {res_buy.get('error')}"
                            )
                except Exception as e:
                    _LOGGER.error(f"Auto-trade failed: {e}")
                    lines.append(f"🤖 *AUTO-TRADE ERROR:* {e}")

            # Track for TP/SL monitoring
            _active_signals[s["symbol"]] = {
                "entry": s["price"],
                "tp1": s["tp1"],
                "tp2": s["tp2"],
                "tp3": s["tp3"],
                "sl": s["stop_loss"],
                "hit": set(),
                "time": datetime.now(WIB).isoformat(),
            }
            record_bot_learning_signal(s, scan_coins.get(s["symbol"]), source="daily")

    # --- BAGIAN 2: PANTAUAN (ringkas, 1 baris per koin) ---
    if watch_signals:
        lines.append("👀 *Belum entry — pantau dulu:*")
        for s in watch_signals:
            ch = f"+{s['change']:.2f}" if s["change"] >= 0 else f"{s['change']:.2f}"
            lines.append(
                f"   {s['emoji']} *{s['symbol']}* {s['action']} · skor {s['score']} · {format_idr(s['price'])} ({ch}%)"
            )
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
        _daily_stats["signals_sent"] += buy_count
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
                min_vol = (
                    1_000_000_000  # Kejadian sangat luar biasa -> minimal 1 Miliar
                )
            elif change > 20:
                min_vol = 1_500_000_000  # Luar biasa -> minimal 1.5 Miliar
            elif change > 12:
                min_vol = 2_000_000_000  # Signifikan -> minimal 2 Miliar
            else:
                min_vol = 3_000_000_000  # Normal pumping -> minimal 3 Miliar
            if vol < min_vol:
                continue

        item = {
            "symbol": sym,
            "pair": data["pair"],
            "price": data["price"],
            "change": round(change, 2),
            "vol_idr": vol,
            "high": data["high"],
            "low": data["low"],
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
        for coin in lst[
            :3
        ]:  # Batasi 3 teratas per kategori agar pesan tidak terlalu panjang
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
            lines.append(
                f"   Harga: {format_idr(coin['price'])} | Vol: {format_idr(coin['vol_idr'])}"
            )

            # Dynamic Technical Intelligence
            try:
                candles = fetch_candles(coin["pair"])
                if not candles.empty:
                    ticker_info = all_coins.get(sym, coin)
                    res = apply_bot_intelligence(
                        analyze_coin(sym, ticker_info, candles)
                    )
                    lines.append(
                        f"   🧠 Intel Score: *{res['score']}/100* | Sinyal: *{res['action']}*"
                    )
                    lines.append(
                        f"   📊 RSI: {res['rsi']} | EMA: {res['ema_bias']} | ST: *{res['supertrend']}*"
                    )
                    lines.append(
                        f"   🤖 ML Predict: *{res['ml_label']}* ({res['ml_prob']}%)"
                    )
                    lines.append(
                        f"   🎯 Target TP1: {format_idr(res['tp1'])} | SL: {format_idr(res['stop_loss'])}"
                    )
            except Exception as e:
                log(f"Dynamic analysis failed for {sym}: {e}")

            lines.append(f"   🔗 [Masuk Market Indodax]({link})")
            lines.append("")

    _add_coins(fomo_gila, "FOMO GILA (>20%)")
    _add_coins(fomo, "FOMO (>12%)")
    _add_coins(pumping, "PUMPING (>8%)")

    lines.append("──────────────────────")
    lines.append(
        "⚠️ *Himbauan:* Selalu DYOR dan jangan FOMO secara asal. Gunakan stop loss!"
    )
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
    _fomo_sent_symbols = {
        k: v
        for k, v in _fomo_sent_symbols.items()
        if now_ts - v.get("_sent_at", 0) < FOMO_SYMBOL_COOLDOWN_SEC
    }

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
    _confluence_sent_symbols = {
        k: v
        for k, v in _confluence_sent_symbols.items()
        if now_ts - v["sent_at"] < CONFLUENCE_SYMBOL_COOLDOWN_SEC
    }

    scan_coins = get_scan_coins(all_coins)
    for sym, pair in scan_coins.items():
        if sym not in all_coins:
            continue
        if sym in STABLECOINS:
            continue  # Stablecoin tidak relevan untuk pump/confluence signals

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
                res["confluence_passed"] >= 3
                and res["ml_label"] in ("BULLISH", "NETRAL")
                and res["bt_label"] != "LEMAH"
            )

            if not is_entry_action(res["action"]) or not (strong or smart):
                continue

            # Kirim alert instan!
            pair_url = pair.upper().replace("_", "")
            link = f"https://indodax.com/market/{pair_url}?ref={INDODAX_REF}"
            link_tv = f"https://www.tradingview.com/chart/?symbol=INDODAX:{pair_url}"
            ch_sign = "+" if res["change"] >= 0 else ""

            insight_res = generate_signal_insight(res, GEMINI_API_KEY, DEEPSEEK_API_KEY, OPENROUTER_API_KEY)
            ai_insight = insight_res.get(
                "insight",
                "📊 *ANALYTICS & INSIGHT:*\nAI Insight tidak tersedia saat ini.\n\n🟢 *INSTRUKSI:*\nIkuti sinyal teknikal di atas dengan manajemen risiko.",
            )

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
            )
            # Tambahkan Binance data jika tersedia
            if res.get("binance_available"):
                msg += (
                    f"\n🌐 *Binance Global:* {res.get('binance_signal', 'NO DATA')} (adj {res.get('binance_adjustment', 0):+d})\n"
                    f"   Funding: {res.get('binance_funding_signal', '-')} | "
                    f"L/S: {res.get('binance_ls_signal', '-')} ({res.get('binance_ls_ratio', 0):.2f}x) | "
                    f"Book: {res.get('binance_book_signal', '-')}\n"
                )
            msg += (
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
            log(
                f"REAL-TIME CONFLUENCE ALERT TERKIRIM untuk {sym} ({res['confluence_label']})"
            )

            # Masukkan ke list monitor TP/SL bot jika belum ada
            if sym not in _active_signals:
                _active_signals[sym] = {
                    "entry": res["price"],
                    "tp1": res["tp1"],
                    "tp2": res["tp2"],
                    "tp3": res["tp3"],
                    "sl": res["stop_loss"],
                    "hit": set(),
                    "time": datetime.now(WIB).isoformat(),
                }
                _daily_stats["signals_sent"] += 1
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
    ema_state = (
        "bullish"
        if ema_cross_up and ema8_slope_up
        else ("warming" if ema_cross_up else "bearish")
    )
    ema_check = ema_cross_up and ema8_slope_up

    # RSI bangun
    rsi_now = compute_rsi(close) if len(close) >= 14 else 50
    rsi_prev = compute_rsi(close.iloc[:-1]) if len(close) >= 16 else rsi_now
    rsi_check = (38 <= rsi_now <= 68) and (rsi_now > rsi_prev + 1.5)

    # Volume spike (15m)
    avg_vol_20 = (
        float(vol.tail(21).iloc[:-1].mean())
        if len(vol) >= 21
        else float(vol.tail(20).mean())
    )
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
    if ema_check:
        triggers.append("EMA up")
    if rsi_check:
        triggers.append(f"RSI {rsi_prev:.0f}->{rsi_now:.0f}")
    if vol_check:
        triggers.append(f"Vol {vol_ratio:.1f}x")
    if macd_check:
        triggers.append("MACD+")
    if bb_check:
        triggers.append("BB release")
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
        k: v
        for k, v in _early_sent_symbols.items()
        if now_ts - v.get("sent_at", 0) < EARLY_SYMBOL_COOLDOWN_SEC
    }

    scan_coins = get_scan_coins(all_coins)
    for sym, pair in scan_coins.items():
        if sym not in all_coins:
            continue
        if sym in STABLECOINS:
            continue  # Stablecoin tidak relevan untuk pump detection
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
            range_pos = (
                ((ticker["price"] - low_24h) / range_w * 100) if range_w > 0 else 50
            )
            if range_pos > EARLY_MAX_RANGE_POS:
                continue  # udah terlalu deket puncak, bukan early
            if ticker["change"] > 8:
                continue  # udah pump ngegas, ini ranah FOMO/Confluence

            # Range anomaly check: wide range tapi no momentum = wick/spread, bukan trend
            range_pct = ((high_24h - low_24h) / low_24h * 100) if low_24h > 0 else 0
            if range_pct > 8 and ticker["change"] < 2:
                continue  # wide range tanpa momentum = anomaly, skip

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

            # HARD GATE: kalau 1H action jelas bearish, jangan fire early entry
            if res["action"] in ("JANGAN BELI", "HINDARI"):
                continue

            # HARD GATE: ML bearish dengan confidence bukan rendah = skip
            if res["ml_label"] == "BEARISH" and res["ml_conf"] != "rendah":
                continue

            # Binance turbo-boost: kalau sentimen Binance kuat, turunkan threshold entry
            binance_boost = False
            bn_data = res.get("binance_signal", "NO DATA")
            bn_adj = res.get("binance_adjustment", 0)
            if bn_adj >= 3 and setup["passed"] >= (EARLY_MIN_SETUP_STRENGTH - 1):
                binance_boost = (
                    True  # Binance konfirmasi strong → relaksasi setup threshold
                )
            # Binance boost ada floor — tidak bisa bypass score terlalu rendah
            absolute_min_score = max(35, EARLY_MIN_SCORE - 15)
            if res["score"] < absolute_min_score:
                continue  # Score terlalu rendah bahkan untuk Binance boost
            if not binance_boost and res["score"] < EARLY_MIN_SCORE:
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
            # ATR-based TP/SL untuk R:R >= 1.2:1. Fallback fixed % kalau ATR
            # tidak valid (terlalu besar atau data kurang).
            atr_early = compute_atr(candles_15m)
            if atr_early and atr_early > 0 and atr_early < res["price"] * 0.10:
                early_sl = res["price"] - (1.5 * atr_early)
                early_tp1 = res["price"] + (2.0 * atr_early)   # R:R = 1.33:1
                early_tp2 = res["price"] + (3.0 * atr_early)
            else:
                # Fixed fallback: SL -2.5%, TP1 +3.0% → R:R = 1.2:1
                early_sl = res["price"] * 0.975
                early_tp1 = res["price"] * 1.030
                early_tp2 = res["price"] * 1.050

            checks_text = "\n".join(
                f"   {'🟢' if ok else '⚪'} {name}"
                for name, ok in setup["checks"].items()
            )

            # Binance data line
            bn_line = ""
            if res.get("binance_available"):
                bn_emoji = "🟢" if bn_adj > 0 else "🔴" if bn_adj < 0 else "⚪"
                bn_notes_str = ", ".join(res.get("binance_notes", [])[:2]) or "-"
                bn_line = (
                    f"🌐 Binance: {bn_emoji} *{res.get('binance_signal', 'NO DATA')}* (adj {bn_adj:+d})\n"
                    f"   {bn_notes_str}\n"
                )

            boost_label = "⚡🌐 *BINANCE-BOOSTED* " if binance_boost else ""
            msg = (
                f"⚡ *EARLY ENTRY — PRE-PUMP SETUP* ⚡\n"
                f"{boost_label}🚀 *{sym}* — Setup {setup['passed']}/5 (15m)\n"
                f"──────────────────────\n"
                f"💵 Harga: {format_idr(res['price'])} ({ch_sign}{res['change']:.2f}%)\n"
                f"🧭 Range 24h: {res['range_pos']:.0f}% (paruh bawah)\n"
                f"📍 Trigger: _{setup['trigger']}_\n"
                f"📊 RSI 15m: {setup['rsi_prev']} → *{setup['rsi']}* | Vol 15m: *{setup['vol_ratio']}x*\n"
                f"📈 EMA 15m: {setup['ema_state']} | MACD 15m: {setup['macd_state']}\n"
                f"🛡️ Konteks 1H: Score *{res['score']}/100* | {res['action']}\n"
                f"🧠 ML: {res['ml_label']} ({res['ml_prob']:.1f}% prob naik) | MTF: {res['mtf_label']}\n"
                f"{bn_line}"
                f"\n✅ *Checklist Setup 15m:*\n"
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

            # Trade execution for EARLY ENTRY. Defaults to paper mode unless real trade is explicitly enabled.
            if AUTO_TRADE_ENABLED or PAPER_TRADING_MODE:
                trade_amount = _get_trade_amount(res.get("alloc_pct", 10.0))
                try:
                    if trade_amount <= 0:
                        msg += "\n\n🤖 *TRADE DIBLOKIR:* Alokasi 0% (Dilarang AI karena riwayat coin ini sering loss / Winrate buruk)."
                    elif CONFIRM_BEFORE_TRADE:
                        command_router.create_buy_confirmation_proposal(
                            sym.lower(),
                            trade_amount,
                            float(res["price"]),
                            tp1=early_tp1,
                            tp2=early_tp2,
                            sl=early_sl,
                            risk_level=res.get("risk_level"),
                            reason="EARLY",
                            metadata=_trade_risk_metadata(
                                "early_entry",
                                risk_tag=res.get("risk_level"),
                                market_state={"risk_level": res.get("risk_level")},
                            ),
                        )
                        msg += (
                            "\n\n*PROPOSAL TRADE MENUNGGU KONFIRMASI*\n"
                            + _format_trade_proposal_message(
                                sym,
                                "CICIL BELI",
                                trade_amount,
                                float(res["price"]),
                                early_tp1,
                                early_tp2,
                                early_sl,
                                res.get("risk_level"),
                                "EARLY",
                            )
                        )
                    else:
                        res_buy = execution_engine.execute_buy(
                            sym.lower(),
                            trade_amount,
                            float(res["price"]),
                            reason="EARLY",
                            metadata={
                                **_trade_risk_metadata(
                                    "early_entry",
                                    risk_tag=res.get("risk_level"),
                                    market_state={"risk_level": res.get("risk_level")},
                                ),
                                "entry_features": res.get("entry_features"),
                            },
                        )
                        if res_buy.get("success"):
                            received = res_buy["received_coin"]
                            avg_price = res_buy["avg_price"]
                            spent = res_buy.get("spent_idr", trade_amount)
                            saved = _save_executed_buy_position(
                                res_buy,
                                sym,
                                tp1=early_tp1,
                                tp2=early_tp2,
                                sl=early_sl,
                                trade_type="EARLY",
                            )
                            if saved:
                                trade_label = (
                                    "PAPER-TRADE SIMULASI"
                                    if res_buy.get("mode") == "paper"
                                    else "AUTO-TRADE SUKSES"
                                )
                                msg += (
                                    f"\n\n🤖 *{trade_label}!*\n"
                                    f"Beli: {received} {sym} (Rp{spent:,.0f})\n"
                                    f"Harga: Rp{avg_price:,.0f}\n"
                                    f"Mode Kawal TP/SL aktif 🛡️"
                                )
                            else:
                                msg += "\n\n🤖 *ORDER TERJADI, PENCATATAN PORTFOLIO GAGAL. CEK RECOVERY JOURNAL.*"
                        else:
                            msg += (
                                f"\n\n🤖 *TRADE DIBLOKIR/GAGAL:* {res_buy.get('error')}"
                            )
                except Exception as e:
                    _LOGGER.error(f"Auto-trade early failed: {e}")

            send_message(msg, notify=True)
            log(
                f"EARLY ENTRY ALERT terkirim untuk {sym} (setup {setup['passed']}/5, score 1H {res['score']})"
            )

            # Catat sebagai paper-trade ("andai beli") — terpisah dari learning
            # sinyal nyata. Bot akan kabari otomatis kalau kena TP/SL.
            try:
                record_paper_signal(
                    {
                        "symbol": sym,
                        "pair": pair,
                        "action": "EARLY",
                        "price": res["price"],
                        "score": res["score"],
                        "tp1": early_tp1,
                        "tp2": early_tp2,
                        "target": early_tp2,
                        "stop_loss": early_sl,
                        "forecast_step1_prob": res.get("ml_prob"),
                    }
                )
            except Exception as e:
                log(f"Gagal catat paper-trade early {sym}: {e}", "warning")

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
def _announce_paper_results(closed_papers):
    """Kabari hasil paper-trade ("andai beli") dari early signal yg baru ditutup.

    Ini yang bikin user bisa "berandai-andai": bot bilang seandainya beli koin
    early tadi, sekarang kena TP (cuan) atau SL (rugi) — tanpa uang asli.
    """
    if not closed_papers:
        return
    for p in closed_papers:
        sym = p.get("symbol", "?")
        outcome = p.get("outcome")
        pnl = p.get("pnl_pct", 0.0)
        status = p.get("status", "")
        if outcome == "WIN":
            head = "✅ *ANDAI BELI — CUAN* (paper)"
            tail = "Seandainya kamu masuk di sinyal early tadi, sudah kena target."
        else:
            head = "❌ *ANDAI BELI — RUGI* (paper)"
            tail = "Seandainya masuk tadi, kena stop loss. Bagus tidak FOMO."
        msg = (
            f"{head}\n"
            f"🪙 *{sym}* — hasil simulasi (bukan transaksi nyata)\n"
            f"──────────────────────\n"
            f"Entry early: {format_idr(p.get('entry', 0))}\n"
            f"Harga keluar: {format_idr(p.get('exit', 0))}  ·  status {status}\n"
            f"P/L andai beli: *{pnl:+.2f}%*  (puncak +{p.get('max_gain_pct', 0):.2f}%)\n"
            f"──────────────────────\n"
            f"_{tail}_ Ini paper-trade untuk belajar, bukan saran beli. DYOR."
        )
        send_message(msg, notify=False)
    log(f"Lapor {len(closed_papers)} hasil paper-trade (andai beli)")


def check_tp_sl_alerts(all_coins):
    """Cek apakah harga sudah kena TP1/TP2/TP3 atau SL dari sinyal aktif."""
    global _active_signals, _daily_stats
    _ensure_daily_stats_fields()

    # Check trade TP/SL if real auto-trade or paper-trading is enabled.
    if AUTO_TRADE_ENABLED or PAPER_TRADING_MODE:
        sell_reports = portfolio_manager.check_tp_sl(all_coins)
        for report in sell_reports:
            _record_trade_close_for_risk(report.get("profit_pct"))
            sell_title = (
                "PAPER-SELL SIMULASI"
                if report.get("mode") == "paper"
                else "AUTO-SELL EKSEKUSI"
            )
            msg = (
                f"🤖 *{sell_title}!* 🤖\n\n"
                f"💰 Koin: *{report['symbol']}*\n"
                f"Status: {report['reason']}\n"
                f"Harga Beli: Rp{report['buy_price']:,.0f}\n"
                f"Harga Jual: Rp{report['sell_price']:,.0f}\n"
                f"Profit/Rugi: *{report['profit_pct']:+.2f}%* (Rp{report['profit_idr']:+,.0f})\n\n"
                f"Posisi otomatis dihapus dari radar. 🛡️"
            )
            send_message(msg, notify=True, force=True)

    # ── Circuit breaker: consecutive losses > 3 → pause all new trades ──
    consec_losses = _ensure_daily_stats_fields().get("consecutive_losses", 0)
    _circuit_broken = consec_losses >= 3
    if _circuit_broken:
        log(
            f"CIRCUIT BREAKER: {consec_losses} consecutive losses. Pausing new trade proposals."
        )
        # Kirim peringatan 1x
        if not _daily_stats.get("_cb_notified"):
            send_message(
                f"🚨 *CIRCUIT BREAKER AKTIF*\n"
                f"{consec_losses} loss berturut-turut. Trade baru dihentikan sementara.\n"
                f"Bot akan kembali aktif setelah reset harian (21:00 WIB).",
                notify=True,
                force=True,
            )
            _daily_stats["_cb_notified"] = True

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

        # ── Trailing SL: setelah TP1 kena, SL naik mengikuti harga ──
        if "TP1" in sig["hit"] and sig.get("trailing_sl"):
            trail = sig.get("trail_pct", 0.5)  # default trail 0.5%
            # Trailing: SL = harga sekarang minus trail%, tapi minimal breakeven + 0.5%
            min_sl = entry * (1 + 0.005)  # breakeven + 0.5%
            trail_sl = price * (1 - trail / 100)  # harga sekarang minus trail%
            new_sl = max(min_sl, trail_sl)
            # Hanya naikkan SL, jangan turunkan
            if new_sl > sig.get("sl", 0):
                sig["sl"] = new_sl
                log(f"Trailing SL {sym}: naik ke {format_idr(new_sl)}")

        if price <= sig["sl"] and "SL" not in sig["hit"]:
            sig["hit"].add("SL")
            _daily_stats["sl_hit"] += 1
            _record_trade_close_for_risk(pnl_pct)
            send_message(
                f"*STOP LOSS HIT*\n{sym} kena SL di {format_idr(price)}\nEntry: {format_idr(entry)} | PnL: {pnl_pct:+.2f}%\nPotong rugi, disiplin!",
                notify=True,
                force=True,
            )
            to_remove.append(sym)
            continue

        if price >= sig["tp3"] and "TP3" not in sig["hit"]:
            sig["hit"].add("TP3")
            _daily_stats["tp_hit"] += 1
            _record_trade_close_for_risk(pnl_pct)
            # Compound: catat profit untuk reinvest
            if pnl_pct > 0:
                _daily_stats["compounded_profit"] = (
                    _daily_stats.get("compounded_profit", 0) + pnl_pct
                )
            send_message(
                f"*TARGET HIT - TP3*\n{sym} capai TP3 di {format_idr(price)}\nEntry: {format_idr(entry)} | PnL: {pnl_pct:+.2f}%\nSelamat! Take profit semua. Modal +{pnl_pct:.1f}% ready compounding.",
                notify=True,
                force=True,
            )
            to_remove.append(sym)
        elif price >= sig["tp2"] and "TP2" not in sig["hit"]:
            sig["hit"].add("TP2")
            _daily_stats["tp_hit"] += 1
            send_message(
                f"*TARGET HIT - TP2*\n{sym} capai TP2 di {format_idr(price)}\nEntry: {format_idr(entry)} | PnL: {pnl_pct:+.2f}%\nJual 30%, sisanya trailing SL aktif.",
                notify=True,
                force=True,
            )
        elif price >= sig["tp1"] and "TP1" not in sig["hit"]:
            sig["hit"].add("TP1")
            _daily_stats["tp_hit"] += 1
            # Aktifkan trailing SL: naik ke breakeven + 0.5%
            sig["trailing_sl"] = True
            sig["trail_pct"] = 0.5
            sig["sl"] = max(sig.get("sl", 0), entry * 1.005)  # break-even + 0.5%
            send_message(
                f"*TARGET HIT - TP1*\n{sym} capai TP1 di {format_idr(price)}\nEntry: {format_idr(entry)} | PnL: {pnl_pct:+.2f}%\nSL trailing aktif di {format_idr(sig['sl'])}. Jual 30%, pantau TP2.",
                notify=True,
                force=True,
            )

    for sym in to_remove:
        del _active_signals[sym]


# =============================================================================
# DAILY SUMMARY (jam 21:00 WIB)
# =============================================================================
def send_daily_summary():
    global _last_summary_date, _daily_stats
    _ensure_daily_stats_fields()
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
    if _daily_stats["tp_hit"] > _daily_stats["sl_hit"]:
        lines.append("Hari yang bagus! Lebih banyak TP daripada SL.")
    elif _daily_stats["sl_hit"] > 0:
        lines.append("Ada SL hari ini. Evaluasi dan jangan balas dendam.")
    else:
        lines.append("Market tenang hari ini. Sabar menunggu setup.")
    lines.append(f"Gabung: {TELEGRAM_CHANNEL}")
    send_message("\n".join(lines), notify=False)
    _daily_stats = _default_daily_stats()
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
        except (OSError, ValueError):
            pass
    return 0


def _save_last_update_id(uid):
    with open("last_update_id.txt", "w") as f:
        f.write(str(uid))


def _format_idr(value):
    if value is None or value == 0:
        return "-"
    if value >= 1_000_000_000:
        return f"Rp{value / 1_000_000_000:.2f}M"
    if value >= 1_000_000:
        return f"Rp{value / 1_000_000:.1f}JT"
    if value >= 1_000:
        return f"Rp{value:,.0f}"
    return f"Rp{value:,.2f}"


def handle_telegram_command(update_data):
    """Wrapper to route Telegram responses back to the originating chat ID."""
    message = None
    if not update_data:
        return False
    if "message" in update_data:
        message = update_data["message"]
    elif "channel_post" in update_data:
        message = update_data["channel_post"]
    elif "callback_query" in update_data:
        message = update_data["callback_query"].get("message")

    if message:
        chat_info = message.get("chat", {})
        msg_chat_id = str(chat_info.get("id", ""))
        _reply_context.chat_id = msg_chat_id

    try:
        return _handle_telegram_command_inner(update_data)
    finally:
        _reply_context.chat_id = None


def _handle_telegram_command_inner(update_data):
    """Handle incoming Telegram commands. Returns True if a command was processed."""
    global _message_fingerprints
    global AUTO_TRADE_ENABLED, PAPER_TRADING_MODE
    global ENABLE_FOMO_ALERTS, ENABLE_CONFLUENCE_ALERTS, ENABLE_EARLY_ALERTS


    if not update_data or not BOT_TOKEN or not CHAT_ID:
        return False

    # Extract message
    message = None
    if "message" in update_data:
        message = update_data["message"]
    elif "channel_post" in update_data:
        message = update_data["channel_post"]
    elif "callback_query" in update_data:
        # Handle inline query (button clicks)
        message = update_data["callback_query"].get("message")
        if not message:
            return False

    if not message:
        return False

    sender = (
        update_data.get("callback_query", {}).get("from")
        if "callback_query" in update_data
        else message.get("from")
    )
    auth_message = dict(message)
    auth_message["from"] = sender or {}
    allowed_user_id = str(os.environ.get("TELEGRAM_ALLOWED_USER_ID", "")).strip()

    # Log incoming message info for debugging
    chat_info = message.get("chat", {})
    msg_chat_id = str(chat_info.get("id", ""))
    chat_type = str(chat_info.get("type", "")).lower()
    sender_id = str(auth_message.get("from", {}).get("id", ""))
    text_log = message.get("text", "")
    log(f"Incoming TG message: chat_id={msg_chat_id} ({chat_type}), sender_id={sender_id}, text={text_log!r}")

    # Check if message is from our chat or if it's an authorized private DM
    is_authorized_dm = False
    if chat_type == "private" and allowed_user_id and sender_id == allowed_user_id:
        is_authorized_dm = True

    if str(msg_chat_id) != str(CHAT_ID) and not is_authorized_dm:
        if chat_type == "private":
            send_message(
                f"⚠️ *Akses Ditolak*\n"
                f"Chat ID ({msg_chat_id}) tidak sesuai dengan CHAT_ID bot ({CHAT_ID}).\n"
                f"User ID Anda: `{sender_id}`\n"
                f"Konfigurasikan `TELEGRAM_ALLOWED_USER_ID` dengan ID tersebut di env var Hugging Face Anda untuk memberikan akses via DM.",
                notify=True,
                force=True,
            )
        return False

    if (
        chat_type != "channel"
        and allowed_user_id
        and str(auth_message.get("from", {}).get("id", "")) != allowed_user_id
    ):
        return False

    # Update last update id
    uid = message.get("message_id", 0)
    _save_last_update_id(uid)

    # Get text/command
    text = message.get("text", "").strip()
    if not text:
        return False

    # Check for duplicate messages (avoid re-processing on restart)
    now_ts = time.time()
    msg_key = f"{msg_chat_id}:{uid}"
    if msg_key in _message_fingerprints:
        if now_ts - _message_fingerprints[msg_key] < 30:  # 30s dedupe
            return False
    _message_fingerprints[msg_key] = now_ts

    router_command = command_router.parse_command(text)
    if router_command.get("type") != "UNKNOWN":
        authorization = command_router.authorize_telegram_command(
            auth_message,
            router_command,
            configured_chat_id=CHAT_ID,
            allowed_user_id=allowed_user_id,
        )
        if not authorization.get("allowed"):
            send_message(
                f"Command ditolak: {authorization.get('reason')}",
                notify=True,
                force=True,
            )
            return True
        context_symbol = (
            router_command.get("symbol")
            if router_command.get("type") in ("BUY", "SELL")
            else None
        )
        result = command_router.handle_command(
            text, context=_telegram_router_context(context_symbol)
        )
        send_message(_format_router_response(result), notify=True, force=True)
        return True

    if not text.startswith("/"):
        return False

    parts = text.split()
    cmd = parts[0].lower()
    args = parts[1:] if len(parts) > 1 else []

    # === /help ===
    if cmd == "/help":
        help_text = (
            f"*⚙️ DAFTAR COMMAND TELEGRAM*\n"
            f"──────────────────────\n"
            f"🏓 */ping* — Cek bot hidup + uptime\n"
            f"🤖 */status* — Kondisi bot (mode, agresif, posisi)\n"
            f"🔥 */agresif on|off* — Toggle mode agresif\n"
            f"💸 */autotrade paper|real|off* — Atur eksekusi auto-trade\n"
            f"🧠 */brain* — Status belajar ML (data, versi model)\n"
            f"🧠 */explain <koin>* — Analisis koin berbasis AI/LLM\n"

            f"🏋️ */train* — Paksa latih ulang model ML sekarang\n"
            f"📊 */scan* — Scan semua koin utama sekarang\n"

            f"🎯 */top* — Lihat 5 koin terbaik saat ini\n"
            f"💼 */portfolio* — Cek posisi terbuka + P/L\n"
            f"📜 */journal* — Riwayat sinyal + winrate\n"
            f"📈 */stats* — Statistik performa bot\n"
            f"🔔 */alert on/off* — Aktifkan/nonaktifkan alert\n"
            f"🌤 */weather* — Cek market mode saat ini\n"
            f"✅ */buy BTC 50000* — Manual buy / konfirmasi proposal\n"
            f"🛑 */sell BTC ALL* — Manual sell / konfirmasi\n"
            f"❌ */cancel BTC* — Batalkan proposal pending\n"
            f"🧯 */kill* / */resume* — Risk off/on runtime\n"
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

            # Scan top coins by volume
            scan_coins = get_scan_coins(all_coins)
            signals = []
            for sym, pair in scan_coins.items():
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
            priority = {
                "BELI KUAT": 0,
                "CICIL BELI": 1,
                "WATCH": 2,
                "JANGAN BELI": 3,
                "HINDARI": 4,
            }
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
                lines.append(
                    f"   💰 {format_idr(s['price'])} ({ch}%) | Score: {s['score']}/100"
                )
                lines.append(
                    f"   📊 RSI: {s['rsi']} | MACD: {s['macd_signal']} | ST: {s['supertrend']}"
                )
                lines.append(
                    f"   🧠 ML: {s['ml_label']} ({s['ml_prob']}%) | MTF: {s['mtf_label']}"
                )

                if is_entry_action(s["action"]):
                    buy_count += 1
                    lines.append(
                        f"   🎯 TP1: {format_idr(s['tp1'])} | SL: {format_idr(s['stop_loss'])}"
                    )
                    lines.append(f"   💰 Alokasi: {s['alloc_pct']}%")
                lines.append("")

            lines.append("──────────────────────")
            lines.append(f"*{buy_count} koin layak beli* dari {len(signals)} koin")
            lines.append(f"⚠️ Bukan saran keuangan. DYOR.")

            send_message("\n".join(lines), notify=True, force=True)
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

            scan_coins = get_scan_coins(all_coins)
            signals = []
            for sym, pair in scan_coins.items():
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
                lines.append(
                    f"   ML: {s['ml_label']} ({s['ml_prob']}%) | MTF: {s['mtf_label']}"
                )
                lines.append(f"   Confluence: {s['confluence_label']}")

                if is_entry_action(s["action"]):
                    lines.append(
                        f"   🎯 Entry → TP1: {format_idr(s['tp1'])} | TP2: {format_idr(s['tp2'])} | SL: {format_idr(s['stop_loss'])}"
                    )
                    lines.append(f"   💰 Alokasi: {s['alloc_pct']}%")
                lines.append("")

            lines.append("──────────────────────")
            lines.append("⚠️ Bukan saran keuangan. DYOR.")

            send_message("\n".join(lines), notify=True, force=True)
            log(f"/top command executed")

        except Exception as e:
            log(f"Error /top: {e}")
            send_message(f"❌ Error: {str(e)[:100]}", notify=True)
        return True

    # === /explain ===
    if cmd == "/explain":
        if not args:
            send_message(
                "⚠️ *Format Salah*\nGunakan: `/explain <SYMBOL>` (contoh: `/explain BTC` atau `/explain ETH`)",
                notify=True,
                force=True,
            )
            return True
            
        symbol = args[0].upper().strip()
        send_message(
            f"⏳ *Menganalisis ${symbol}...* _AI sedang merangkum indikator teknikal & pasar._",
            notify=False,
        )
        
        try:
            all_coins = fetch_all_tickers()
            if not all_coins or symbol not in all_coins:
                send_message(
                    f"❌ Koin *{symbol}* tidak ditemukan di pasar IDR IndodaxSummaries.",
                    notify=True,
                    force=True,
                )
                return True
                
            coin_data = all_coins[symbol]
            pair = coin_data["pair"]
            
            candles = fetch_candles(pair)
            if candles.empty:
                send_message(
                    f"❌ Gagal mengambil data grafik (candles) untuk {symbol}.",
                    notify=True,
                    force=True,
                )
                return True
                
            # Jalankan analisis teknikal lengkap
            res = apply_bot_intelligence(analyze_coin(symbol, coin_data, candles))
            
            # Generate AI custom explanation
            analysis_text = generate_custom_explain(res, GEMINI_API_KEY, DEEPSEEK_API_KEY, OPENROUTER_API_KEY)
            
            # Send message
            header = (
                f"🧠 *AI ANALYSIS — {symbol}*\n"
                f"💵 Harga: {format_idr(res['price'])} ({'+' if res['change'] >= 0 else ''}{res['change']:.2f}%)\n"
                f"🤖 Rekomendasi Bot: *{res['action']}* (Score: {res['score']}/100)\n"
                f"──────────────────────\n\n"
            )
            
            send_message(header + analysis_text, notify=True, force=True)
            log(f"/explain command executed for {symbol}")
            
        except Exception as e:
            log(f"Error /explain: {e}")
            send_message(f"❌ Error saat menganalisis koin: {str(e)[:100]}", notify=True, force=True)
        return True

    # === /portfolio ===
    if cmd == "/portfolio":
        try:
            portfolio = portfolio_manager._load_portfolio()
            open_positions = {
                sym: pos
                for sym, pos in portfolio.items()
                if str(pos.get("status", "OPEN")).strip().upper() == "OPEN"
            }

            if not open_positions:
                send_message(
                    "💼 *PORTFOLIO*\n\nTidak ada posisi terbuka saat ini.\n\n"
                    "💡 Tips: Buka /scan untuk cari entry baru.",
                    notify=True,
                    force=True,
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

            for sym, pos in open_positions.items():
                sym_upper = sym.upper()
                ticker = all_coins.get(sym_upper) if isinstance(all_coins, dict) else None
                if isinstance(ticker, dict):
                    price = ticker.get("price")
                elif isinstance(ticker, (int, float)):
                    price = ticker
                else:
                    price = pos.get("buy_price")  # fallback

                entry = pos.get("buy_price", 1)
                pnl = ((price - entry) / entry * 100) if entry else 0.0
                total_pnl += pnl

                mode_str = "REAL 💸" if pos.get("mode") == "real" else "PAPER 🧻"
                emoji = "🟢" if pnl >= 0 else "🔴"

                lines.append(f"{emoji} *{sym_upper}* ({mode_str})")
                lines.append(
                    f"   Beli: {format_idr(entry)} → Sekarang: {format_idr(price)}"
                )
                lines.append(
                    f"   P/L: {pnl:+.2f}% | SL: {format_idr(pos.get('sl'))} | TP1/TP2: {format_idr(pos.get('tp1'))}/{format_idr(pos.get('tp2'))}"
                )
                lines.append("")

            lines.append("──────────────────────")
            lines.append(f"Total P/L: {total_pnl:+.2f}%")
            lines.append(f"Posisi aktif: {len(open_positions)}")
            lines.append("")
            lines.append("📌 Monitor: bot akan notif otomatis saat TP/SL kena.")

            send_message("\n".join(lines), notify=True, force=True)
            log(
                f"/portfolio command executed — {len(open_positions)} active positions loaded from active_trades.json"
            )

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
            wr = profile.get("winrate")
            wr_text = f"{wr:.1f}%" if wr is not None else "belum ada"

            lines.append(f"Total sinyal: {profile.get('total_signals', 0)}")
            lines.append(f"Selesai: {total} | Win: {wins} | Loss: {losses}")
            lines.append(f"*Winrate: {wr_text}*")
            lines.append("")

            # Best symbols
            best = profile.get("best_symbols", [])
            if best:
                lines.append("*Top Performer:*\n")
                for sym, stats in best:
                    lines.append(
                        f"🏆 {sym}: {stats.get('winrate', 0):.1f}% WR ({stats.get('closed', 0)} trades)"
                    )
                lines.append("")

            # Active signals
            active = profile.get("active", 0)
            if active > 0:
                lines.append(f"Posisi aktif: {active}")

            lines.append("")
            lines.append("──────────────────────")
            lines.append("📊 Data dari semua sinyal yang tercatat.")
            lines.append("⚠️ Bukan saran keuangan. DYOR.")

            send_message("\n".join(lines), notify=True, force=True)
            log(f"/journal command executed — WR: {wr_text}")

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
            wr = profile.get("winrate")
            wr_text = f"{wr:.1f}%" if wr is not None else "belum ada"

            lines = [
                "📈 *STATISTIK BOT*",
                f"{datetime.now(WIB).strftime('%d/%m %Y')}",
                "──────────────────────",
                "",
            ]

            lines.append(f"Total sinyal tercatat: {profile.get('total_signals', 0)}")
            lines.append(f"Trade selesai: {total}")
            lines.append(
                f"Win: {profile.get('wins', 0)} | Loss: {profile.get('losses', 0)}"
            )
            lines.append(f"*Winrate: {wr_text}*")
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
                    lines.append(
                        f"  🏆 {sym}: {stats.get('winrate', 0):.1f}% WR ({stats.get('closed', 0)} trades)"
                    )
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
                notify=True,
            )
            return True

        if args[0] == "on":
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
            mode_emoji = {
                "agresif": "🟢 AGRESIF",
                "normal": "🟡 NORMAL",
                "defensif": "🔴 DEFENSIF",
            }[mode]

            changes = [
                c["change"] for c in all_coins.values() if c["vol_idr"] >= 100_000_000
            ]
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
            sorted_coins = sorted(
                all_coins.values(), key=lambda x: x["change"], reverse=True
            )[:5]
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

    # === /ping — cek bot hidup + responsif ===
    if cmd in ("/ping", "/start"):
        up = time.time() - _BOT_START_TS
        hours = int(up // 3600)
        mins = int((up % 3600) // 60)
        send_message(
            f"🏓 *PONG — bot hidup & responsif!*\n"
            f"Uptime: {hours}j {mins}m\n"
            f"Cycle ke-{_CYCLE_COUNT}\n"
            f"Posisi aktif: {len(_active_signals)}\n"
            f"Ketik /help buat lihat semua command.",
            notify=True,
            force=True,
        )
        return True

    # === /status — ringkasan kondisi bot sekarang ===
    if cmd == "/status":
        aggressive = os.environ.get("AGGRESSIVE_MODE") == "1"
        preset = os.environ.get("AGGRESSIVE_PRESET", "-")
        mode_real = AUTO_TRADE_ENABLED and not PAPER_TRADING_MODE
        send_message(
            "🤖 *STATUS BOT*\n"
            "──────────────────────\n"
            f"Mode trading: *{'REAL 💸' if mode_real else 'PAPER 🧻'}*\n"
            f"Agresif: *{'ON 🔥' if aggressive else 'OFF 🛡️'}* (preset: {preset})\n"
            f"Konfirmasi sebelum trade: {'Ya' if CONFIRM_BEFORE_TRADE else 'Tidak'}\n"
            f"Max posisi bareng: {os.environ.get('MAX_ACTIVE_TRADES', '5')}\n"
            f"Scan: {MAX_SCAN_COINS} koin tiap {LOOP_SLEEP_SECONDS}s\n"
            f"Limit per trade: Rp{MAX_TRADE_IDR:,.0f}\n"
            f"Alert: FOMO {'on' if ENABLE_FOMO_ALERTS else 'off'} · "
            f"Confluence {'on' if ENABLE_CONFLUENCE_ALERTS else 'off'} · "
            f"Early {'on' if ENABLE_EARLY_ALERTS else 'off'}\n"
            f"Posisi aktif: {len(_active_signals)}\n"
            "──────────────────────\n"
            "Ubah agresif: /agresif on|off",
            notify=True,
            force=True,
        )
        return True

    # === /agresif on|off — toggle mode agresif runtime ===
    if cmd in ("/agresif", "/aggressive"):
        if not args or args[0].lower() not in ("on", "off"):
            current = "ON 🔥" if os.environ.get("AGGRESSIVE_MODE") == "1" else "OFF 🛡️"
            send_message(
                f"🔥 *MODE AGRESIF*\nSekarang: *{current}*\n\n"
                "Gunakan:\n/agresif on — cari sinyal scalp cepat (boost ML)\n"
                "/agresif off — kembali normal/swing",
                notify=True,
                force=True,
            )
            return True
        if args[0].lower() == "on":
            os.environ["AGGRESSIVE_MODE"] = "1"
            send_message(
                "🔥 *MODE AGRESIF AKTIF* — bot cari sinyal scalp cepat pakai XGBoost. "
                "Lebih banyak entry, lebih sering. Pantau /portfolio & /stats.",
                notify=True,
                force=True,
            )
        else:
            os.environ["AGGRESSIVE_MODE"] = "0"
            send_message(
                "🛡️ *MODE AGRESIF NONAKTIF* — bot kembali ke mode swing/normal.",
                notify=True,
                force=True,
            )
        return True

    # === /autotrade — kontrol eksekusi trade (paper/real/off) ===
    if cmd in ("/autotrade", "/auto"):
        sub = args[0].lower() if args else ""


        def _mode_now():
            if AUTO_TRADE_ENABLED and not PAPER_TRADING_MODE:
                return "REAL 💸 (uang asli)"
            if PAPER_TRADING_MODE:
                return "PAPER 🧻 (simulasi)"
            return "OFF ⛔ (cuma sinyal, tidak eksekusi)"

        if sub == "off":
            AUTO_TRADE_ENABLED = False
            PAPER_TRADING_MODE = False
            os.environ["AUTO_TRADE_ENABLED"] = "false"
            os.environ["PAPER_TRADING_MODE"] = "false"
            send_message(
                "⛔ *AUTO-TRADE OFF* — bot cuma kirim sinyal, tidak eksekusi order. "
                "Kamu eksekusi manual sendiri.",
                notify=True,
                force=True,
            )
            return True
        if sub == "paper":
            AUTO_TRADE_ENABLED = False
            PAPER_TRADING_MODE = True
            os.environ["AUTO_TRADE_ENABLED"] = "false"
            os.environ["PAPER_TRADING_MODE"] = "true"
            send_message(
                "🧻 *AUTO-TRADE PAPER ON* — bot eksekusi SIMULASI (tanpa uang asli). "
                "Aman buat uji strategi. Cek hasil di /portfolio & /stats.",
                notify=True,
                force=True,
            )
            return True
        if sub == "real":
            # Wajib konfirmasi eksplisit "real yes" supaya tidak kepencet.
            if len(args) < 2 or args[1].lower() != "yes":
                send_message(
                    "⚠️ *KONFIRMASI UANG ASLI* ⚠️\n"
                    "Ini akan eksekusi order BENERAN di Indodax pakai uang asli.\n"
                    f"Limit per trade: Rp{MAX_TRADE_IDR:,.0f}\n"
                    f"Konfirmasi sebelum tiap order: {'Ya' if CONFIRM_BEFORE_TRADE else 'TIDAK (langsung beli!)'}\n\n"
                    "Kalau yakin, ketik: */autotrade real yes*",
                    notify=True,
                    force=True,
                )
                return True
            AUTO_TRADE_ENABLED = True
            PAPER_TRADING_MODE = False
            os.environ["AUTO_TRADE_ENABLED"] = "true"
            os.environ["PAPER_TRADING_MODE"] = "false"
            send_message(
                "💸 *AUTO-TRADE REAL ON!* — bot mulai eksekusi order pakai UANG ASLI.\n"
                f"Limit per trade: Rp{MAX_TRADE_IDR:,.0f}\n"
                f"Konfirmasi tiap order: {'Ya' if CONFIRM_BEFORE_TRADE else 'TIDAK'}\n"
                "Pantau ketat /portfolio. Matikan kapan saja: /autotrade off",
                notify=True,
                force=True,
            )
            return True

        # Tanpa argumen valid → tampilkan status + bantuan
        send_message(
            "🤖 *AUTO-TRADE*\n"
            f"Sekarang: *{_mode_now()}*\n"
            "──────────────────────\n"
            "/autotrade paper — eksekusi simulasi (aman)\n"
            "/autotrade real — eksekusi uang asli (perlu konfirmasi)\n"
            "/autotrade off — cuma sinyal, tanpa eksekusi",
            notify=True,
            force=True,
        )
        return True

    # === /brain — status proses belajar bot ===
    if cmd == "/brain":

        try:
            from ml_engine import get_learning_status

            st = get_learning_status()
            metrics = st.get("latest_metrics") or {}
            wf = metrics.get("walk_f1_mean")
            wf_txt = f"{wf:.2f}" if isinstance(wf, (int, float)) else "-"
            latest_samples = st.get("latest_samples")
            samp_txt = f"{latest_samples}" if latest_samples else "belum ada"
            
            send_message(
                "🧠 *STATUS OTAK BOT (ML LEARNING)*\n"
                "──────────────────────\n"
                f"Online learning: {'ON ✅' if st['online_enabled'] else 'OFF ❌'}\n"
                f"Buffer Live: *{st['buffer_samples']}/{st['min_samples_needed']}* sampel\n"
                f"(data nunggu buat retrain berikutnya)\n"
                f"Model aktif: {'Ya' if st['model_exists'] else 'Belum'}\n"
                f"Versi model: v{st['latest_version'] or '-'} (dilatih dari {samp_txt} sampel)\n"
                f"Walk-forward F1: {wf_txt}\n"
                f"Retrain terakhir: {st['last_retrain']}\n"
                f"Auto-retrain tiap: {st['retrain_interval_h']} jam\n"
                f"Win streak: {st['consecutive_wins']} · Loss streak: {st['consecutive_losses']}\n"
                f"Threshold sekarang: {st['current_threshold']:.0f}%\n"
                "──────────────────────\n"
                "Latih sekarang (manual): /train",
                notify=True,
                force=True,
            )
        except Exception as e:
            log(f"Error /brain: {e}")
            send_message(f"❌ Error: {str(e)[:100]}", notify=True, force=True)
        return True

    # === /train — paksa latih ulang model ML sekarang ===
    if cmd == "/train":
        send_message(
            "🏋️ *Mulai latih ulang model ML...* (bisa makan waktu)",
            notify=False,
            force=True,
        )
        try:
            from ml_engine import force_online_retrain, bootstrap_train_from_history

            res = force_online_retrain()

            # Cold-start: kalau buffer feedback live belum cukup (mis. deploy baru
            # di HuggingFace yang mulai dari nol), bootstrap dari candle historis
            # banyak koin sekaligus supaya model bisa langsung kepakai tanpa nunggu
            # berminggu-minggu ngumpulin hasil trade satu per satu.
            if not res.get("success"):
                send_message(
                    "📚 *Buffer live belum cukup* — bootstrap dari data historis "
                    "banyak koin...",
                    notify=False,
                    force=True,
                )
                try:
                    all_coins = fetch_all_tickers()
                    scan_coins = get_scan_coins(all_coins)
                    pairs = list(scan_coins.values())
                    res = bootstrap_train_from_history(
                        fetch_candles, pairs, tf="60", lookback_days=60
                    )
                except Exception as be:
                    log(f"Bootstrap train error: {be}")
                    res = {"success": False, "reason": str(be)[:120]}

            if res.get("success"):
                m = res.get("metrics", {})
                extra = ""
                if res.get("coins_used"):
                    extra = f"\nSumber: {res.get('coins_used')} koin (historis)"
                send_message(
                    "✅ *TRAINING SELESAI!*\n"
                    f"Versi model baru: *v{res.get('version')}*\n"
                    f"Dilatih dari: {res.get('n_samples')} sampel{extra}\n"
                    f"Akurasi: {m.get('accuracy', '-')} · F1: {m.get('f1', '-')} · "
                    f"Walk-F1: {m.get('walk_f1_mean', '-')}\n"
                    "Model baru langsung dipakai buat prediksi berikutnya. 🧠",
                    notify=True,
                    force=True,
                )
            else:
                send_message(
                    f"⚠️ *Belum bisa latih:* {res.get('reason')}\n"
                    f"(sampel sekarang: {res.get('n_samples', 0)})\n"
                    "Bot tetap belajar otomatis sambil ngumpulin data.",
                    notify=True,
                    force=True,
                )
        except Exception as e:

            log(f"Error /train: {e}")
            send_message(f"❌ Error training: {str(e)[:100]}", notify=True, force=True)
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
    params = {
        "timeout": 0,
        "offset": _last_update_offset + 1 if _last_update_offset else None,
    }
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


SCAN_WORKERS = int(os.environ.get("SCAN_WORKERS", "1"))


def _prefetch_candles_parallel(scan_coins, timeframes=(("60", 21), ("15", 5))):
    """Warm-up cache candle secara PARALEL untuk semua koin scan.

    Loop alert (early/confluence) tetap jalan serial seperti biasa, TAPI karena
    candle-nya sudah ada di cache (di-fetch paralel di sini), pemanggilan
    fetch_candles di dalam loop jadi cache-hit instan — tidak ada lagi ratusan
    request HTTP berurutan yang menahan siklus.

    Aman dari sisi thread: requests independen per koin, dan cache fetch_candles
    cuma assign ke dict (atomic di CPython). Worker dibatasi biar tidak kena
    rate-limit Indodax (default 1 = serial/tidak berubah; set SCAN_WORKERS>1
    untuk paralel, mis. preset agresif pakai 8).
    """
    if SCAN_WORKERS <= 1 or not scan_coins:
        return
    pairs = list(scan_coins.values())

    def _warm(pair):
        for tf, lookback in timeframes:
            try:
                fetch_candles(pair, tf=tf, lookback_days=lookback)
            except Exception:
                pass

    try:
        with concurrent.futures.ThreadPoolExecutor(
            max_workers=min(SCAN_WORKERS, max(1, len(pairs)))
        ) as ex:
            list(ex.map(_warm, pairs))
    except Exception as e:
        log(f"Prefetch candle paralel gagal (lanjut serial): {e}", "warning")


def _command_listener_loop():
    """Long-polling listener di thread terpisah supaya bot SELALU responsif,
    bahkan saat loop utama lagi sibuk scan 80 koin (yang bisa makan menit).

    Pakai getUpdates dengan long-poll timeout 25s — hemat request tapi balasan
    command (/ping, /scan, /agresif, dst) terasa instan."""
    global _last_update_offset
    if not BOT_TOKEN or not CHAT_ID:
        log("Listener tidak jalan: BOT_TOKEN/CHAT_ID kosong.", "warning")
        return
    import json as _json
    import http.client
    import ssl

    path_base = f"/bot{BOT_TOKEN}/getUpdates"
    log("Command listener thread aktif (http.client long-poll 25s).")

    while True:
        try:
            offset_param = f"&offset={_last_update_offset + 1}" if _last_update_offset else ""
            path = f"{path_base}?timeout=25{offset_param}"

            # http.client: timeout 60s (must be > 25s Telegram hold time)
            ctx = ssl.create_default_context()
            conn = http.client.HTTPSConnection("api.telegram.org", timeout=60, context=ctx)
            conn.request("GET", path)
            resp = conn.getresponse()
            raw = resp.read().decode("utf-8")
            conn.close()

            data = _json.loads(raw)
            if not data.get("ok"):
                time.sleep(2)
                continue
            for update in data.get("result", []):
                _last_update_offset = max(
                    _last_update_offset, update.get("update_id", 0)
                )
                try:
                    handle_telegram_command(update)
                except Exception as e:
                    log(f"listener handle error: {e}", "warning")
        except (TimeoutError, OSError) as e:
            # Timeout is normal for long-poll, just retry
            continue
        except _json.JSONDecodeError:
            time.sleep(2)
        except Exception as e:
            log(f"listener error: {e}", "warning")
            time.sleep(3)


def _start_command_listener():
    """Start listener thread sekali aja (idempotent)."""
    global _LISTENER_STARTED
    if _LISTENER_STARTED:
        return
    t = threading.Thread(target=_command_listener_loop, name="tg-listener", daemon=True)
    t.start()
    _LISTENER_STARTED = True


# =============================================================================
# MAIN DAEMON LOOP
# =============================================================================
if __name__ == "__main__":
    if os.environ.get("RUN_KEEP_ALIVE") == "true":
        keep_alive()

    log("BOT DAEMON ULTRA SMART -- 24/7")
    log("   Sinyal harian: 08:00 WIB (1H multi-indikator)")
    log(f"   Loop scan: setiap {LOOP_SLEEP_SECONDS}s")
    log("   Early entry (15m pre-pump + Binance turbo): tiap loop")
    log("   Confluence 1H + FOMO + TP/SL: tiap loop")
    log("   Daily summary: 21:00 WIB")
    log(f"   Binance engine: {'✅ AKTIF' if _BINANCE_OK else '❌ TIDAK TERSEDIA'}")
    auto_trade_status = (
        f"✅ REAL AKTIF (Limit: Rp{MAX_TRADE_IDR:,.0f})"
        if AUTO_TRADE_ENABLED and not PAPER_TRADING_MODE
        else "❌ REAL OFF"
    )
    log(f"   Auto-Trade Indodax: {auto_trade_status}")
    log(f"   Paper Trading: {'✅ AKTIF' if PAPER_TRADING_MODE else '❌ OFF'}")
    log(f"   Confirm Before Trade: {'✅ AKTIF' if CONFIRM_BEFORE_TRADE else '❌ OFF'}")
    log(f"   Channel: {TELEGRAM_CHANNEL}")
    log("=" * 40)
    if not BOT_TOKEN or not CHAT_ID:
        log("CRITICAL: TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID belum diset!")
        log(
            f"  BOT_TOKEN: {'OK (' + BOT_TOKEN[:8] + '...)' if BOT_TOKEN else 'KOSONG'}"
        )
        log(f"  CHAT_ID: {'OK (' + str(CHAT_ID) + ')' if CHAT_ID else 'KOSONG'}")
        log("  Cek environment variables ATAU .streamlit/secrets.toml")
    else:
        log(f"  BOT_TOKEN: OK ({BOT_TOKEN[:8]}...)")
        log(f"  CHAT_ID: OK ({CHAT_ID})")

    # Load previously saved bot state to avoid duplicate alerts and preserve active trades
    load_bot_state()

    # Listener thread: bikin bot SELALU responsif ke command (instan), terpisah
    # dari loop scan yang bisa lama. Kalau token ada → jalan di background.
    _start_command_listener()
    if BOT_TOKEN and CHAT_ID:
        log("Bot interaktif: command dibalas instan via listener thread.")

    # ── AUTO-BOOTSTRAP ML MODEL ─────────────────────────────────────────────
    # Jalankan di background thread supaya bot LANGSUNG mulai scan + dengar
    # perintah Telegram, tanpa menunggu training selesai (bisa 5-10 menit).
    def _bootstrap_background():
        try:
            from ml_engine import get_learning_status, bootstrap_train_from_history
            _ml_status = get_learning_status()
            if not _ml_status.get("model_exists"):
                log("⚡ AUTO-BOOTSTRAP: Model belum ada, mulai training di background...")
                send_message(
                    "⚡ *AUTO-BOOTSTRAP ML*\n"
                    "Model belum ada di server ini.\n"
                    "Training otomatis berjalan di background...\n"
                    "Bot sudah aktif scan & dengar perintah!",
                    notify=False,
                    force=True,
                )
                _boot_coins = fetch_all_tickers()
                if _boot_coins:
                    _boot_scan = get_scan_coins(_boot_coins)
                    _boot_pairs = list(_boot_scan.values())
                    _boot_res = bootstrap_train_from_history(
                        fetch_candles, _boot_pairs, tf="60", lookback_days=60, max_pairs=100
                    )
                    if _boot_res.get("success"):
                        log(
                            f"✅ AUTO-BOOTSTRAP SELESAI: v{_boot_res.get('version')} — "
                            f"{_boot_res.get('n_samples')} sampel dari "
                            f"{_boot_res.get('coins_used')} koin"
                        )
                        send_message(
                            f"✅ *AUTO-BOOTSTRAP SELESAI!*\n"
                            f"Model v{_boot_res.get('version')} — "
                            f"{_boot_res.get('n_samples')} sampel dari "
                            f"{_boot_res.get('coins_used')} koin.\n"
                            f"Bot siap tempur! 🚀",
                            notify=True,
                            force=True,
                        )
                    else:
                        log(f"⚠️ AUTO-BOOTSTRAP gagal: {_boot_res.get('reason', 'unknown')}")
                else:
                    log("⚠️ AUTO-BOOTSTRAP: Gagal fetch tickers, skip bootstrap.")
            else:
                log(f"✅ Model sudah ada (v{_ml_status.get('latest_version')}), skip bootstrap.")
        except Exception as e:
            log(f"⚠️ AUTO-BOOTSTRAP error (bot tetap jalan): {e}", "warning")

    threading.Thread(target=_bootstrap_background, name="ml-bootstrap", daemon=True).start()
    # ── END AUTO-BOOTSTRAP ──────────────────────────────────────────────────

    consecutive_errors = 0
    cycle_count = 0

    if SCAN_WORKERS > 1:
        log(f"   Scan paralel: {SCAN_WORKERS} worker (prefetch candle)")

    while True:
        try:
            cycle_count += 1
            _CYCLE_COUNT = cycle_count  # sinkron buat /ping & /status
            _cycle_start = time.time()  # ukur durasi siklus
            all_coins = fetch_all_tickers()

            if not all_coins:
                consecutive_errors += 1
                wait = min(30, consecutive_errors * 5)
                log(f"Fetch gagal ({consecutive_errors}x). Retry in {wait}s...")
                if consecutive_errors == 5:
                    try:
                        send_message(
                            "⚠️ *ALERT: BOT FETCH FAILED* ⚠️\n\n"
                            "Bot gagal melakukan fetch data tickers dari Indodax sebanyak *5x berturut-turut*.\n"
                            "Ada kemungkinan API Indodax sedang gangguan atau koneksi terhambat.\n\n"
                            "Bot tetap mencoba recovery otomatis...",
                            notify=True,
                            force=True,
                        )
                    except Exception as tg_err:
                        log(f"Gagal mengirim telegram alert: {tg_err}", "error")
                time.sleep(wait)
                continue

            consecutive_errors = 0
            coin_count = len(all_coins)
            now = datetime.now(WIB)

            # Prefetch candle 1H paralel buat semua koin scan → warm cache,
            # jadi loop early/confluence di bawah jadi cache-hit instan.
            try:
                _prefetch_candles_parallel(get_scan_coins(all_coins))
            except Exception as e:
                log(f"Prefetch error (lanjut): {e}", "warning")

            _paper_closed = []
            learning_profile = train_from_prices(
                all_coins, closed_collector=_paper_closed
            )
            _announce_paper_results(_paper_closed)
            news_profile = get_bot_news_profile()

            if cycle_count % 10 == 1:
                wr = learning_profile.get("winrate")
                wr_text = f"{wr:.1f}%" if wr is not None else "belum ada"
                log(
                    f"Heartbeat -- {coin_count} koin | {now.strftime('%H:%M WIB')} | Learning WR: {wr_text} | News: {news_profile.get('global_label', 'NO DATA')}"
                )

            # 0. Command Telegram ditangani listener thread terpisah (instan),
            #    jadi tidak perlu poll di sini lagi (hindari race offset getUpdates).

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

            # Ukur & log durasi siklus (buat lihat dampak optimasi performa).
            _cycle_dur = time.time() - _cycle_start
            if cycle_count % 10 == 1 or _cycle_dur > LOOP_SLEEP_SECONDS:
                log(
                    f"Siklus #{cycle_count} selesai dalam {_cycle_dur:.1f}s "
                    f"(target loop {LOOP_SLEEP_SECONDS}s, workers={SCAN_WORKERS})"
                )

            time.sleep(LOOP_SLEEP_SECONDS)

        except KeyboardInterrupt:
            log("Shutdown by user.")
            break
        except Exception as e:
            consecutive_errors += 1
            log(f"Crash: {e} -- restarting in 10s...", "error")
            if consecutive_errors == 5:
                try:
                    send_message(
                        f"🚨 *CRITICAL ALERT: BOT CRASH LOOP* 🚨\n\n"
                        f"Bot telah mengalami *{consecutive_errors}* error/crash beruntun.\n"
                        f"Detail error terakhir:\n`{str(e)[:500]}`\n\n"
                        f"⚠️ Bot akan terus mencoba restart otomatis setiap 10s.",
                        notify=True,
                        force=True,
                    )
                except Exception as tg_err:
                    log(f"Gagal mengirim telegram alert: {tg_err}", "error")
            time.sleep(10)
