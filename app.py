import os
import threading
import json
from textwrap import dedent

import time
from datetime import datetime, timedelta, timezone

import pandas as pd
import requests
import streamlit as st
import streamlit.components.v1 as components
from news_engine import apply_news_adjustments, build_news_profile
from intelligence_engine import (
    apply_kelly_to_allocation,
    build_intelligence_bundle,
    build_two_steps_ahead,
    compute_multi_horizon_forecast,
)
import journal_store
import smart_engine
import ai_pilot
import pump_scanner

# Binance global data (graceful import)
try:
    import binance_engine
    BINANCE_ENGINE_AVAILABLE = True
except ImportError:
    binance_engine = None  # type: ignore
    BINANCE_ENGINE_AVAILABLE = False

# =============================================================================
# CONFIG & CONSTANTS
# =============================================================================
MAIN_ASSETS = {
    "BTC": ("btc_idr", "bitcoin"),
    "ETH": ("eth_idr", "ethereum"),
    "SOL": ("sol_idr", "solana"),
    "XRP": ("xrp_idr", "ripple"),
    "BNB": ("bnb_idr", "binancecoin"),
    "ADA": ("ada_idr", "cardano"),
    "DOT": ("dot_idr", "polkadot"),
    "MATIC": ("matic_idr", "polygon"),
    "AVAX": ("avax_idr", "avalanche"),
    "LINK": ("link_idr", "chainlink"),
}

MICIN_ASSETS = {
    "PEPE": ("pepe_idr", "pepe"),
    "DOGE": ("doge_idr", "dogecoin"),
    "SHIB": ("shib_idr", "shiba-inu"),
    "BONK": ("bonk_idr", "bonk"),
    "FLOKI": ("floki_idr", "floki"),
    "LUNC": ("lunc_idr", "terra-luna"),
    "BTT": ("btt_idr", "bittorrent"),
    "JASMY": ("jasmy_idr", "jasmy"),
}

ALL_ASSETS = {**MAIN_ASSETS, **MICIN_ASSETS}
MICIN_SYMBOLS = set(MICIN_ASSETS.keys())

# --- KATEGORI COIN ---
COIN_CATEGORIES = {
    "BTC": "Layer1", "ETH": "Layer1", "SOL": "Layer1", "BNB": "Layer1", "ADA": "Layer1",
    "DOT": "Layer1", "AVAX": "Layer1", "NEAR": "Layer1", "ATOM": "Layer1", "APT": "Layer1",
    "SUI": "Layer1", "SEI": "Layer1", "TIA": "Layer1", "INJ": "Layer1", "ALGO": "Layer1",
    "HBAR": "Layer1", "ICP": "Layer1", "EGLD": "Layer1", "FTM": "Layer1", "MINA": "Layer1",
    "ROSE": "Layer1", "ZIL": "Layer1", "KDA": "Layer1", "XRD": "Layer1", "MULTI": "Layer1",
    "OSMO": "Layer1", "KUJI": "Layer1", "LUNA": "Layer1", "LUNC": "Layer1", "KSM": "Layer1",
    "KAVA": "Layer1", "IRIS": "Layer1", "DUSK": "Layer1", "ETC": "Layer1", "BCH": "Layer1",
    "LTC": "Layer1", "XLM": "Layer1", "TRX": "Layer1", "WAVES": "Layer1", "XTZ": "Layer1",
    "EOS": "Layer1", "NEO": "Layer1", "VET": "Layer1", "IOTA": "Layer1", "QTUM": "Layer1",
    "ONT": "Layer1", "ICX": "Layer1", "NANO": "Layer1", "HNT": "Layer1", "FLOW": "Layer1",
    "CKB": "Layer1", "ONE": "Layer1", "TON": "Layer1", "XRP": "Layer1",
    "MATIC": "Layer2", "ARB": "Layer2", "OP": "Layer2", "LRC": "Layer2",
    "MANTA": "Layer2", "STRK": "Layer2", "METIS": "Layer2", "SKL": "Layer2", "CELO": "Layer2",
    "BOBA": "Layer2", "ZKSYNC": "Layer2", "SCROLL": "Layer2", "LINEA": "Layer2", "BLAST": "Layer2",
    "MODE": "Layer2", "ZORA": "Layer2", "FUEL": "Layer2", "ALT": "Layer1", "ALTLAYER": "Layer1",
    "LINK": "DeFi", "UNI": "DeFi", "AAVE": "DeFi", "CRV": "DeFi",
    "COMP": "DeFi", "SUSHI": "DeFi", "YFI": "DeFi", "1INCH": "DeFi",
    "BAL": "DeFi", "CAKE": "DeFi", "GMX": "DeFi", "DYDX": "DeFi", "LDO": "DeFi",
    "FXS": "DeFi", "CVX": "DeFi", "STG": "DeFi", "JUP": "DeFi",
    "RAY": "DeFi", "ORCA": "DeFi", "VELO": "DeFi", "JOE": "DeFi", "ZRX": "DeFi",
    "RUNE": "DeFi", "THORCHAIN": "DeFi", "BAND": "DeFi", "UMA": "DeFi", "REN": "DeFi",
    "API3": "DeFi", "RSR": "DeFi", "CTSI": "DeFi", "RLC": "DeFi", "CELR": "DeFi", "BNT": "DeFi",
    "KNC": "DeFi", "BADGER": "DeFi", "PERP": "DeFi", "IDEX": "DeFi",
    "GNS": "DeFi", "PEPE": "Meme", "FLOKI": "Meme", "WIF": "Meme", "BONK": "Meme",
    "BOME": "Meme", "POPCAT": "Meme", "MEW": "Meme", "MYRO": "Meme", "SLERF": "Meme",
    "SAMO": "Meme", "TOSHI": "Meme", "MOG": "Meme", "PONKE": "Meme", "PUMP": "Meme",
    "FWOG": "Meme", "GIGA": "Meme", "MICHI": "Meme", "MOTHER": "Meme", "TURBO": "Meme",
    "FET": "AI", "RNDR": "AI", "TAO": "AI", "GRT": "AI", "AKT": "AI",
    "WLD": "AI", "AGIX": "AI", "OCEAN": "AI", "AIOZ": "AI",
    "ARKM": "AI", "AITECH": "AI", "PAAL": "AI", "AGI": "AI", "OLAS": "AI",
    "NMR": "AI", "CTXC": "AI", "MDT": "AI", "VAI": "AI", "VIRTUALS": "AI",
    "AI": "AI", "AIXBT": "AI", "NFP": "AI", "CGPT": "AI", "IDX": "AI",
    "IMX": "Gaming", "GALA": "Gaming", "AXS": "Gaming", "SAND": "Gaming", "MANA": "Gaming",
    "ENJ": "Gaming", "ILV": "Gaming", "MAGIC": "Gaming", "APE": "Gaming", "YGG": "Gaming",
    "PRIME": "Gaming", "PIXEL": "Gaming", "PORTAL": "Gaming", "BIGTIME": "Gaming", "WEMIX": "Gaming",
    "TLM": "Gaming", "VOXEL": "Gaming", "DAR": "Gaming", "SHRAP": "Gaming", "MYRIA": "Gaming",
    "NAKA": "Gaming", "BEAM": "Gaming", "RON": "Gaming", "SUPER": "Gaming", "MAVIA": "Gaming",
    "XAI": "Gaming", "ACE": "Gaming", "NYAN": "Gaming", "GAMEE": "Gaming", "PLYA": "Gaming",
    "ONDO": "RWA", "MKR": "RWA", "CFG": "RWA", "PENDLE": "RWA", "RIO": "RWA",
    "TRU": "RWA", "SNX": "RWA", "MPL": "RWA", "GFI": "RWA", "PRO": "RWA",
    "FACTR": "RWA", "DOVA": "RWA", "CHEX": "RWA", "LAND": "RWA", "TOKEN": "RWA",
    "USDT": "Stablecoin", "USDC": "Stablecoin", "DAI": "Stablecoin", "TUSD": "Stablecoin",
    "XAUT": "RWA", "PAXG": "RWA",
}
CATEGORY_COLORS = {
    "Layer1": "#3b82f6", "Layer2": "#8b5cf6", "DeFi": "#22c55e", "Meme": "#f59e0b",
    "AI": "#ec4899", "Gaming": "#f97316", "RWA": "#14b8a6", "Stablecoin": "#6b7280",
}
CATEGORY_ORDER = ["Layer1", "Layer2", "DeFi", "Meme", "AI", "Gaming", "RWA", "Stablecoin"]

INDODAX_REF = "https://indodax.com/ref/narwanpratanta/1"
# Satu sumber kebenaran untuk kode referral Indodax (dipakai di semua link beli).
# Ganti di sini saja kalau kode referral berubah — tidak perlu berburu ke banyak tempat.
REFERRAL_CODE = "narwanpratanta"
TELEGRAM_COMMUNITY = "https://t.me/+VPlOcY2wFGA0NWU1"
SIGNAL_JOURNAL_FILE = os.environ.get("SIGNAL_JOURNAL_FILE", "signal_journal.json")
SIGNAL_LEARNING_ENABLED = str(os.environ.get("ENABLE_SIGNAL_LEARNING", "true")).lower() in {"1", "true", "yes", "on"}
SIGNAL_LEARNING_TTL_HOURS = int(os.environ.get("SIGNAL_LEARNING_TTL_HOURS", "72"))
SIGNAL_LEARNING_DEDUPE_HOURS = int(os.environ.get("SIGNAL_LEARNING_DEDUPE_HOURS", "6"))

DONATION_WALLETS = {
    "BTC": "bc1qxy2kgdygjrsqtzq2n0yrf2493p83kkfjhx0wlh",
    "ETH": "0x71C7656EC7ab88b098defB751B7401B5f6d8976F",
    "USDT_TRC20": "TXeK7qvZNDFK7zFgmhMRPivJ7rWtLqvm8d",
}

MARKET_MODE_RULES = {
    "aggressive": {
        "label": "🚀 AGRESIF",
        "description": "Mayoritas market hijau. Boleh cari entry, tetap disiplin TP.",
        "color": "#22c55e",
        "allocation_multiplier": 1.15,
        "score_adjustment": 6,
    },
    "normal": {
        "label": "⚖️ NORMAL",
        "description": "Market campuran. Pilih coin ber-volume kuat dan jangan mengejar candle.",
        "color": "#f59e0b",
        "allocation_multiplier": 1.0,
        "score_adjustment": 0,
    },
    "defensive": {
        "label": "🛡️ DEFENSIF",
        "description": "Market lemah. Fokus watchlist, entry kecil, dan stop loss ketat.",
        "color": "#ef4444",
        "allocation_multiplier": 0.45,
        "score_adjustment": -10,
    },
}

VALUE_BLUE_CHIPS = {"BTC", "ETH", "BNB", "SOL", "XRP", "ADA", "DOT", "AVAX", "LINK", "MATIC"}
VALUE_HIGH_RISK = {"PEPE", "SHIB", "BONK", "FLOKI", "LUNC", "BTT"}

# =============================================================================
# PAGE CONFIG
# =============================================================================
st.set_page_config(
    page_title="Kripto Mania - Dashboard Trading Cerdas",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# =============================================================================
# HCI PRINCIPLES IMPLEMENTATION (Norman & Nielsen Heuristics)
# =============================================================================
# 
# PRINSIP HCI YANG DIIMPLEMENTASIKAN:
# 
# 1. VISIBILITY OF SYSTEM STATUS (Nielsen #1)
#    - Freshness badge dengan indikator live/stale/offline
#    - Progress bar saat analisis berjalan
#    - Status loading screen dengan animasi
#    - Auto-refresh indicator
#    - Market mode banner yang selalu terlihat
# 
# 2. MATCH BETWEEN SYSTEM AND REAL WORLD (Nielsen #2)
#    - Bahasa Indonesia untuk semua label dan pesan
#    - Simbol yang familiar (🟢 hijau = bagus, 🔴 merah = bahaya)
#    - Format mata uang Rupiah (IDR)
#    - Zona waktu WIB (Asia/Jakarta)
#    - Kategori coin yang familiar (Layer1, DeFi, Meme, AI, Gaming)
# 
# 3. USER CONTROL AND FREEDOM (Nielsen #3)
#    - Toggle auto-refresh ON/OFF
#    - Manual refresh button
#    - Scan koin mandiri (user bisa pilih koin apapun)
#    - Portfolio management (edit, close, delete posisi)
#    - Tab navigation untuk berbagai fitur
#    - Quick prompt buttons untuk AI Advisor
# 
# 4. CONSISTENCY AND STANDARDS (Nielsen #4)
#    - Warna konsisten: hijau = profit/bullish, merah = loss/bearish
#    - Badge styling konsisten di seluruh halaman
#    - Font Plus Jakarta Sans untuk semua elemen
#    - Card design konsisten dengan hover effects
#    - Metric chips dengan format yang sama
# 
# 5. ERROR PREVENTION (Nielsen #5)
#    - Confluence gate mencegah entry saat sinyal lemah
#    - Anti-FOMO filter mencegah entry di pucuk
#    - Multi-timeframe guard untuk konfirmasi
#    - Validasi input form (qty > 0, harga > 0)
#    - Fallback data saat API gagal
#    - Deduplikasi sinyal berulang
# 
# 6. RECOGNITION RATHER THAN RECALL (Nielsen #6)
#    - Tooltip dan label untuk setiap metric
#    - Color-coded signals (tidak perlu hafal arti angka)
#    - Visual indicators (emoji, badges, progress bars)
#    - Category labels untuk setiap coin
#    - Learning notes yang menjelaskan alasan adjustment
# 
# 7. FLEXIBILITY AND EFFICIENCY OF USE (Nielsen #7)
#    - Quick-add dari rekomendasi langsung ke portfolio
#    - Quick-scan untuk analisis koin spesifik
#    - Tab navigation untuk akses cepat
#    - Auto-refresh untuk user yang ingin real-time
#    - Cached data untuk performa cepat
# 
# 8. AESTHETIC AND MINIMALIST DESIGN (Nielsen #8)
#    - Clean dark theme dengan accent colors
#    - Card-based layout yang rapi
#    - Whitespace yang cukup
#    - Typography hierarchy yang jelas
#    - Gradient backgrounds untuk visual interest
# 
# 9. HELP USERS RECOGNIZE, DIAGNOSE, AND RECOVER FROM ERRORS (Nielsen #9)
#    - Error messages yang jelas dan informatif
#    - Fallback mechanisms (cache, shared data)
#    - Loading states yang menunjukkan progress
#    - Status indicators (live/stale/offline)
#    - Warning messages untuk kondisi risiko
# 
# 10. HELP AND DOCUMENTATION (Nielsen #10)
#     - Tab "Cara Baca Sinyal" dengan edukasi lengkap
#     - Tooltips dan help text di setiap form
#     - Disclaimer yang jelas
#     - AI Advisor untuk pertanyaan interaktif
#     - Learning engine notes yang menjelaskan adjustment
# =============================================================================

# =============================================================================
# SESSION STATE INIT
# =============================================================================
def init_state():
    defaults = {
        "price_history": pd.DataFrame(),
        "last_snapshot": {},
        "last_grouped_data": {"main": {}, "micin": {}},
        "last_all_tickers": {},
        "last_market_stats": None,
        "data_status": {"source": "loading", "server_time": None, "error": None},
        "fetch_timestamp": None,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value

init_state()

def get_secret(name, default=None):
    """Ambil secret dari Streamlit secrets atau environment variable."""
    try:
        return st.secrets.get(name, os.getenv(name, default))
    except (FileNotFoundError, KeyError, AttributeError):
        return os.getenv(name, default)

# =============================================================================
# SHARED TICKER DATA — ditulis oleh bot daemon thread, dibaca oleh UI
# =============================================================================
_TICKERS_LOCK = threading.Lock()
_SHARED_TICKERS = {
    "tickers": None,
    "fetched_at": None,
    "error": None,
}

def _write_shared_tickers(tickers):
    """Thread-safe write dari bot daemon."""
    with _TICKERS_LOCK:
        _SHARED_TICKERS["tickers"] = tickers
        _SHARED_TICKERS["fetched_at"] = datetime.now()
        _SHARED_TICKERS["error"] = None

def _read_shared_tickers():
    """Thread-safe read oleh UI main thread."""
    with _TICKERS_LOCK:
        return (
            _SHARED_TICKERS["tickers"],
            _SHARED_TICKERS["fetched_at"],
            _SHARED_TICKERS["error"],
        )

# =============================================================================
# TELEGRAM BOT DAEMON
# =============================================================================
BOT_TOKEN = get_secret("TELEGRAM_BOT_TOKEN", "")
BOT_CHAT_ID = get_secret("TELEGRAM_CHAT_ID", "")
BOT_ENABLED = str(get_secret("ENABLE_TELEGRAM_BOT", "false")).lower() in {"1", "true", "yes", "on"}
BOT_INDODAX_REF = REFERRAL_CODE
BOT_WIB = timezone(timedelta(hours=7))
BOT_MAIN_ASSETS = {
    "BTC": "btc_idr", "ETH": "eth_idr", "SOL": "sol_idr",
    "XRP": "xrp_idr", "BNB": "bnb_idr", "ADA": "ada_idr",
    "DOT": "dot_idr", "MATIC": "matic_idr", "AVAX": "avax_idr", "LINK": "link_idr",
    "PEPE": "pepe_idr", "DOGE": "doge_idr", "SHIB": "shib_idr", "BONK": "bonk_idr",
    "FLOKI": "floki_idr", "LUNC": "lunc_idr", "BTT": "btt_idr", "JASMY": "jasmy_idr",
}

TELEGRAM_MAX_LENGTH = 4096

def clamp(value, min_val, max_val):
    return max(min_val, min(value, max_val))


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
    compute_market_regime,
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
from core.analysis import compute_allocation, compute_risk_level, compute_trade_levels, decide_action
from core import calibration as calibration_engine
from core.committee import build_committee


def _bot_split_text(text, max_len=TELEGRAM_MAX_LENGTH):
    if len(text) <= max_len:
        return [text]
    chunks = []
    while len(text) > max_len:
        split_at = text.rfind("\n\n", 0, max_len)
        if split_at == -1 or split_at < max_len // 2:
            split_at = text.rfind("\n", 0, max_len)
        if split_at == -1 or split_at < max_len // 2:
            split_at = max_len
        chunks.append(text[:split_at].strip())
        text = text[split_at:].strip()
    if text:
        chunks.append(text)
    return chunks

def _bot_send_message(text, alert=True):
    if not BOT_TOKEN or not BOT_CHAT_ID:
        return False
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    chunks = _bot_split_text(text)
    all_ok = True
    for i, chunk in enumerate(chunks):
        payload = {
            "chat_id": BOT_CHAT_ID,
            "text": chunk,
            "parse_mode": "Markdown",
            "disable_notification": not alert,
        }
        try:
            resp = requests.post(url, json=payload, timeout=10)
            result = resp.json()
            if not result.get("ok") and "parse" in str(result.get("description", "")).lower():
                payload.pop("parse_mode", None)
                resp2 = requests.post(url, json=payload, timeout=10)
                result = resp2.json()
            if not result.get("ok"):
                all_ok = False
        except Exception:
            all_ok = False
        if i < len(chunks) - 1:
            time.sleep(0.3)
    return all_ok

def _bot_format_idr(value):
    if value is None:
        return "-"
    if value >= 1_000_000:
        return f"Rp{value/1_000_000:,.1f}JT"
    if value >= 1_000:
        return f"Rp{value:,.0f}"
    return f"Rp{value:,.2f}"

def _bot_format_sinyal_harian(signals):
    buy_signals = [s for s in signals if is_entry_action(s.get("action", ""))]
    if not buy_signals:
        return None
    now = datetime.now(BOT_WIB)
    date_str = now.strftime("%d %B %Y")
    lines = [
        "💰 *SINYAL CRYPTO HARI INI* 💰",
        f"📅 {date_str}",
        "──────────────────────",
        "",
    ]
    for s in buy_signals:
        pair_raw = BOT_MAIN_ASSETS.get(s["symbol"]) or s.get("pair") or f"{s['symbol'].lower()}_idr"
        pair = pair_raw.upper().replace("_", "")
        link = f"https://indodax.com/market/{pair}?ref={BOT_INDODAX_REF}"
        change_sign = "+" if s["change"] >= 0 else ""
        lines.append(f"{s['emoji']} *{s['symbol']}* — {s['action']}")
        lines.append(f"   💵 Harga: {_bot_format_idr(s['price'])}  ({change_sign}{s['change']:.2f}%)")
        lines.append(f"   🧠 Score: {s['score']}/100 | Risk: {s['risk_level']} | Alokasi: {s['allocation_pct']:.1f}% modal")
        lines.append(f"   🎯 TP1/TP2/TP3: {_bot_format_idr(s['tp1'])} / {_bot_format_idr(s['tp2'])} / {_bot_format_idr(s['target'])}")
        lines.append(f"   🛑 Stop Loss: {_bot_format_idr(s['stop_loss'])} | Trailing: {s['trailing_stop_pct']:.1f}%")
        lines.append(f"   📌 Exit: {s['exit_rule']}")
        if s["allocation_pct"] > 0:
            lines.append(f"   [🔥 BELI DI INDODAX]({link})")
        else:
            lines.append(f"   [👀 PANTAU DI INDODAX]({link})")
        lines.append("")
    lines.append("──────────────────────")
    lines.append("⚠️ *Bukan saran keuangan. DYOR.*")
    lines.append(f"💎 *Gabung Premium:* {TELEGRAM_COMMUNITY}")
    return "\n".join(lines)

def _bot_generate_signal(prices):
    signals = []
    for sym, data in prices.items():
        change = data["change"]
        price = data["price"]
        vol_idr = data.get("vol_idr", 0)
        high = data.get("high", price)
        low = data.get("low", price)
        range_width = high - low
        range_position = ((price - low) / range_width * 100) if range_width > 0 else 50
        liquidity_bonus = min(16, vol_idr / 1_000_000_000)
        fomo_penalty = 10 if range_position > 88 and change > 8 else 0
        score = int(clamp(55 + change * 4 + liquidity_bonus - fomo_penalty, 0, 100))
        if score >= 80 and change > 1:
            action, emoji = "🟢 BELI KUAT", "🔥"
        elif score >= 65 and change > 0:
            action, emoji = "🟡 CICIL BELI", "📈"
        elif score >= 50:
            action, emoji = "⚪ WATCH", "⏸️"
        elif score >= 35:
            action, emoji = "🔴 JANGAN BELI", "📉"
        else:
            action, emoji = "⛔ HINDARI", "💀"
        risk_level = "TINGGI" if abs(change) >= 10 or vol_idr < 100_000_000 else "SEDANG" if abs(change) >= 5 or vol_idr < 1_000_000_000 else "RENDAH"
        risk_modifier = {"RENDAH": 1.0, "SEDANG": 0.65, "TINGGI": 0.35}[risk_level]
        allocation_pct = 0
        if is_entry_action(action):
            allocation_pct = clamp(7 * (score / 100) * risk_modifier, 1, 10)
        gain_pct = clamp(3 + max(change, 0) * 0.85 + (score - 60) * 0.12, 2, 16)
        stop_pct = clamp(2.6 + abs(change) * 0.35 + (1 if risk_level == "TINGGI" else 0), 2.5, 9)
        target = price * (1 + gain_pct / 100)
        tp1 = price * (1 + gain_pct * 0.35 / 100)
        tp2 = price * (1 + gain_pct * 0.7 / 100)
        stop_loss = price * (1 - stop_pct / 100)
        trailing_stop_pct = clamp(stop_pct * 0.55, 1.5, 5)
        exit_rule = "TP 30/30/40 lalu trailing" if allocation_pct > 0 else "watch saja, belum entry"
        signals.append({
            "symbol": sym, "price": price, "change": change,
            "action": action, "emoji": emoji,
            "score": score,
            "risk_level": risk_level,
            "allocation_pct": allocation_pct,
            "target": target,
            "tp1": tp1,
            "tp2": tp2,
            "stop_loss": stop_loss,
            "trailing_stop_pct": trailing_stop_pct,
            "exit_rule": exit_rule,
        })
    priority = {
        "🟢 BELI KUAT": 0, "🟡 CICIL BELI": 1, "⚪ WATCH": 2,
        "🔴 JANGAN BELI": 3, "⛔ HINDARI": 4,
    }
    signals.sort(key=lambda x: priority.get(x["action"], 5))
    return signals

def _bot_format_fomo_alert(fomo_gila, fomo, pumping):
    if not fomo_gila and not fomo and not pumping:
        return None
    lines = ["🚨 *FOMO ALERT — KOIN NAIK TAJAM!* 🚨", "──────────────────────", ""]
    if fomo_gila:
        lines.append("🚀 *FOMO GILA (>15%):*")
        for coin in fomo_gila:
            pair = coin["pair"].upper().replace("_", "")
            link = f"https://indodax.com/market/{pair}?ref={BOT_INDODAX_REF}"
            lines.append(f"   {coin['symbol']} — *+{coin['change']}%*")
            lines.append(f"   💵 {_bot_format_idr(coin['price'])} | 📊 Vol: {_bot_format_idr(coin['vol_idr'])}")
            lines.append(f"   [🔥 BELI SEKARANG]({link})")
            lines.append("")
    if fomo:
        lines.append("🔥 *FOMO (>8%):*")
        for coin in fomo:
            pair = coin["pair"].upper().replace("_", "")
            link = f"https://indodax.com/market/{pair}?ref={BOT_INDODAX_REF}"
            lines.append(f"   {coin['symbol']} — *+{coin['change']}%*")
            lines.append(f"   💵 {_bot_format_idr(coin['price'])} | 📊 Vol: {_bot_format_idr(coin['vol_idr'])}")
            lines.append(f"   [🔥 BELI SEKARANG]({link})")
            lines.append("")
    if pumping:
        lines.append("📈 *PUMPING (>5%):*")
        for coin in pumping[:5]:
            pair = coin["pair"].upper().replace("_", "")
            link = f"https://indodax.com/market/{pair}?ref={BOT_INDODAX_REF}"
            lines.append(f"   {coin['symbol']} — *+{coin['change']}%* — [🔥 BELI]({link})")
        lines.append("")
    lines.append("──────────────────────")
    lines.append("⚠️ Hati-hati FOMO! Bisa koreksi kapan aja. DYOR.")
    lines.append(f"💎 *Gabung Premium:* {TELEGRAM_COMMUNITY}")
    return "\n".join(lines)

def _bot_detect_fomo(raw_tickers, prices_24h=None):
    fomo_gila, fomo, pumping = [], [], []
    prices_24h = prices_24h or {}

    for pair, info in raw_tickers.items():
        if not pair.endswith("_idr"):
            continue

        try:
            price = float(info["last"])
            vol = float(info.get("vol_idr", 0))
            change = calculate_24h_change(price, pair, prices_24h)

        except (KeyError, ValueError, TypeError):
            continue

        if vol < 100_000_000:
            continue

        item = {
            "symbol": pair.replace("_idr", "").upper(),
            "pair": pair,
            "price": price,
            "change": round(change, 2),
            "vol_idr": vol,
        }

        if change > 15:
            fomo_gila.append(item)
        elif change > 8:
            fomo.append(item)
        elif change > 5:
            pumping.append(item)

    fomo_gila.sort(key=lambda x: x["change"], reverse=True)
    fomo.sort(key=lambda x: x["change"], reverse=True)
    pumping.sort(key=lambda x: x["change"], reverse=True)

    return fomo_gila, fomo, pumping

# Telegram bot daemon is disabled in app.py to prevent duplication.
# It runs standalone via telegram_bot.py in the Docker container.

# =============================================================================
# STYLING
# =============================================================================
st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800;900&display=swap');
    @import url('https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css');

    /* =========================================================================
       DESIGN SYSTEM — single source of truth (premium light fintech theme).
       Semua warna, radius, shadow, dan motion didefinisikan sekali di sini.
       ========================================================================= */
    :root {
        /* Surfaces & ink */
        --bg-app: #f4f6fb;
        --bg-tint-a: rgba(16, 185, 129, 0.05);
        --bg-tint-b: rgba(59, 130, 246, 0.05);
        --surface: #ffffff;
        --surface-muted: #f7f9fc;
        --surface-inset: #f1f5f9;
        --ink: #0b1220;
        --ink-soft: #475569;
        --ink-faint: #7c889b;
        --hairline: #e7ecf3;
        --hairline-strong: #dbe3ee;

        /* Brand & semantic */
        --brand: #0f9d76;
        --brand-strong: #047857;
        --brand-deep: #065f46;
        --brand-tint: #ecfdf5;
        --brand-tint-border: #bbf7d0;
        --up: #16a34a;
        --down: #e11d48;
        --warn: #d97706;
        --info: #2563eb;
        --accent-gold: #f59e0b;

        /* Radius scale */
        --r-xs: 8px;
        --r-sm: 10px;
        --r-md: 14px;
        --r-lg: 18px;
        --r-pill: 999px;

        /* Shadow scale — soft, layered, "expensive" depth */
        --sh-xs: 0 1px 2px rgba(15, 23, 42, 0.04);
        --sh-sm: 0 1px 2px rgba(15, 23, 42, 0.04), 0 4px 12px rgba(15, 23, 42, 0.05);
        --sh-md: 0 2px 6px rgba(15, 23, 42, 0.05), 0 12px 28px rgba(15, 23, 42, 0.07);
        --sh-lg: 0 8px 24px rgba(15, 23, 42, 0.08), 0 24px 60px rgba(15, 23, 42, 0.10);
        --sh-brand: 0 8px 24px rgba(4, 120, 87, 0.20);

        /* Motion */
        --ease: cubic-bezier(0.22, 1, 0.36, 1);
        --t-fast: 0.16s var(--ease);
        --t-base: 0.24s var(--ease);
    }

    body, .stApp, [data-testid="stAppViewContainer"], [data-testid="stSidebar"],
    p, div, button, input, textarea, label {
        font-family: 'Plus Jakarta Sans', sans-serif;
        -webkit-font-smoothing: antialiased;
        -moz-osx-font-smoothing: grayscale;
    }
    .material-icons, .material-symbols-rounded, .material-symbols-outlined,
    [class*="material-icons"], [class*="material-symbols"] {
        font-family: 'Material Symbols Rounded', 'Material Icons' !important;
        font-weight: normal !important;
        font-style: normal !important;
        letter-spacing: normal !important;
        text-transform: none !important;
        white-space: nowrap !important;
        word-wrap: normal !important;
        direction: ltr !important;
        -webkit-font-feature-settings: 'liga' !important;
        -webkit-font-smoothing: antialiased !important;
    }

    /* App canvas: airy near-white with whisper-soft brand auras */
    .stApp {
        background:
            radial-gradient(1200px 600px at 12% -5%, var(--bg-tint-a), transparent 55%),
            radial-gradient(1000px 560px at 92% 0%, var(--bg-tint-b), transparent 50%),
            var(--bg-app) !important;
        color: var(--ink);
    }
    .block-container {
        max-width: 1240px;
        padding-top: 1.4rem !important;
        padding-bottom: 2.4rem !important;
    }

    h1 { font-size: 2.4rem !important; font-weight: 900 !important; letter-spacing: -0.02em; }
    h2 { font-weight: 800 !important; letter-spacing: -0.015em; }
    h3 { font-weight: 700 !important; letter-spacing: -0.01em; }
    [data-testid="stMetricValue"] { font-weight: 900 !important; }
    hr { border-color: var(--hairline) !important; }

    /* ---- Primary buy CTA ---- */
    .buy-button {
        display: inline-block;
        background: linear-gradient(180deg, var(--brand), var(--brand-strong));
        color: #fff !important;
        text-decoration: none;
        padding: 15px 44px;
        border-radius: var(--r-md);
        font-weight: 800;
        font-size: 1.12rem;
        letter-spacing: 0.01em;
        border: none;
        box-shadow: var(--sh-brand);
        transition: transform var(--t-base), box-shadow var(--t-base);
    }
    .buy-button:hover {
        transform: translateY(-2px);
        box-shadow: 0 14px 36px rgba(4, 120, 87, 0.30);
    }
    .buy-button-sm {
        display: inline-block;
        background: var(--brand-strong);
        color: #fff !important;
        text-decoration: none;
        padding: 0.62rem 1rem;
        border-radius: var(--r-xs);
        font-weight: 800;
        font-size: 0.9rem;
        box-shadow: var(--sh-xs);
        transition: transform var(--t-fast), background var(--t-fast), box-shadow var(--t-fast);
    }
    .buy-button-sm:hover {
        background: var(--brand-deep);
        transform: translateY(-1px);
        box-shadow: var(--sh-sm);
    }
    .buy-button-sm.neutral {
        background: var(--surface-muted);
        border: 1px solid var(--hairline-strong);
        color: var(--ink-soft) !important;
        box-shadow: none;
    }
    .buy-button-sm.neutral:hover { background: var(--surface-inset); color: var(--ink) !important; }

    /* ---- App header (premium glass-light bar) ---- */
    .app-shell-header {
        background: linear-gradient(180deg, rgba(255,255,255,0.92), rgba(255,255,255,0.78));
        backdrop-filter: blur(14px);
        -webkit-backdrop-filter: blur(14px);
        border: 1px solid var(--hairline);
        border-radius: var(--r-lg);
        padding: 1.5rem 1.6rem;
        margin-bottom: 1rem;
        box-shadow: var(--sh-md);
    }
    .app-brand-row {
        display: flex;
        justify-content: space-between;
        align-items: flex-start;
        gap: 1rem;
        flex-wrap: wrap;
    }
    .app-kicker {
        color: var(--brand-strong) !important;
        font-size: 0.72rem;
        font-weight: 900;
        text-transform: uppercase;
        letter-spacing: 0.16em;
        margin-bottom: 0.4rem;
    }
    .app-title {
        color: var(--ink) !important;
        font-size: 2.2rem;
        line-height: 1.04;
        font-weight: 900;
        letter-spacing: -0.025em;
        margin: 0;
    }
    .app-subtitle {
        color: var(--ink-soft) !important;
        font-size: 0.96rem;
        font-weight: 500;
        margin: 0.5rem 0 0;
        max-width: 720px;
        line-height: 1.5;
    }
    .quick-links {
        display: flex;
        gap: 0.5rem;
        align-items: center;
        flex-wrap: wrap;
        justify-content: flex-end;
    }
    .quick-link {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        min-height: 38px;
        border-radius: var(--r-sm);
        padding: 0.5rem 0.9rem;
        background: var(--surface);
        border: 1px solid var(--hairline-strong);
        color: var(--brand-strong) !important;
        font-size: 0.82rem;
        font-weight: 800;
        text-decoration: none !important;
        box-shadow: var(--sh-xs);
        transition: transform var(--t-fast), box-shadow var(--t-fast), background var(--t-fast);
    }
    .quick-link:hover { transform: translateY(-1px); box-shadow: var(--sh-sm); }
    .quick-link.primary {
        background: linear-gradient(180deg, var(--brand), var(--brand-strong));
        border-color: transparent;
        color: #fff !important;
        box-shadow: var(--sh-brand);
    }

    /* ---- Market mode banner ---- */
    .mode-banner {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 0.9rem;
        flex-wrap: wrap;
        background: var(--surface);
        border: 1px solid var(--hairline);
        border-left: 4px solid var(--mode-color);
        border-radius: var(--r-md);
        padding: 0.95rem 1.1rem;
        margin: 0.7rem 0 1rem;
        box-shadow: var(--sh-sm);
    }
    .mode-title { color: var(--mode-color); font-weight: 900; font-size: 1rem; }
    .mode-desc { color: var(--ink-soft); font-size: 0.9rem; font-weight: 500; }

    /* ---- Stat cards ---- */
    .stat-card {
        background: var(--surface);
        border: 1px solid var(--hairline);
        border-radius: var(--r-md);
        padding: 1rem 0.85rem;
        text-align: center;
        box-shadow: var(--sh-sm);
        transition: transform var(--t-base), box-shadow var(--t-base);
    }
    .stat-card:hover { transform: translateY(-2px); box-shadow: var(--sh-md); }
    .stat-value {
        font-size: clamp(1.05rem, 1.8vw, 1.5rem);
        font-weight: 900;
        white-space: nowrap;
        line-height: 1.15;
        letter-spacing: -0.01em;
    }
    .stat-label {
        font-size: 0.72rem;
        color: var(--ink-faint);
        text-transform: uppercase;
        letter-spacing: 0.1em;
        font-weight: 800;
        margin-top: 5px;
    }

    /* ---- Hero (rich emerald accent panel; intentional dark-on-light contrast) ---- */
    .rekomendasi-hero {
        position: relative;
        overflow: hidden;
        background: linear-gradient(135deg, #043b30 0%, #065f46 55%, #047857 100%);
        border: 1px solid rgba(16, 185, 129, 0.35);
        border-radius: var(--r-lg);
        padding: 1.4rem 1.5rem;
        text-align: left;
        margin: 1rem 0 0.85rem;
        box-shadow: 0 18px 44px rgba(4, 59, 48, 0.28);
    }
    .rekomendasi-hero::before {
        content: '';
        position: absolute;
        top: -60%;
        right: -20%;
        width: 60%;
        height: 220%;
        background: radial-gradient(circle, rgba(255,255,255,0.10) 0%, transparent 65%);
        animation: heroGlow 7s ease-in-out infinite;
        pointer-events: none;
    }
    @keyframes heroGlow {
        0%, 100% { transform: translate(0, 0); opacity: 0.7; }
        50% { transform: translate(-16px, 14px); opacity: 1; }
    }
    .hero-title {
        position: relative;
        color: #fff;
        font-size: 1.4rem;
        line-height: 1.18;
        margin: 0;
        font-weight: 900;
        letter-spacing: -0.015em;
    }
    .hero-meta {
        position: relative;
        color: #a7f3d0;
        margin: 0.3rem 0 0;
        font-weight: 700;
        font-size: 0.9rem;
    }

    /* ---- Recommendation card ---- */
    .rekomendasi-card {
        background: var(--surface);
        border: 1px solid var(--hairline);
        border-radius: var(--r-md);
        padding: 1.15rem;
        text-align: left;
        box-shadow: var(--sh-sm);
        transition: transform var(--t-base), box-shadow var(--t-base), border-color var(--t-base);
    }
    .rekomendasi-card:hover {
        border-color: rgba(15, 157, 118, 0.45);
        box-shadow: var(--sh-lg);
        transform: translateY(-3px);
    }
    .coin-card-head {
        display: flex;
        align-items: flex-start;
        justify-content: space-between;
        gap: 1rem;
        flex-wrap: wrap;
    }
    .coin-left { display: flex; align-items: center; gap: 0.8rem; min-width: 220px; }
    .coin-avatar {
        width: 46px;
        height: 46px;
        border-radius: var(--r-sm);
        display: grid;
        place-items: center;
        background: linear-gradient(135deg, var(--brand-tint), #d1fae5);
        border: 1px solid var(--brand-tint-border);
        color: var(--brand-strong);
        font-weight: 900;
        font-size: 0.9rem;
    }
    .coin-symbol { color: var(--ink); font-weight: 900; font-size: 1.26rem; line-height: 1; letter-spacing: -0.01em; }
    .coin-category { color: var(--ink-faint); font-size: 0.78rem; font-weight: 700; margin-top: 0.22rem; }
    .coin-price-wrap {
        display: flex;
        align-items: center;
        justify-content: flex-end;
        gap: 0.55rem;
        flex-wrap: wrap;
    }
    .price-tag {
        color: var(--ink) !important;
        background: none !important;
        -webkit-text-fill-color: initial !important;
        font-size: 1.55rem !important;
        line-height: 1.05;
        font-weight: 900;
        letter-spacing: -0.02em;
    }

    /* ---- Badges & signal pills ---- */
    .profit-badge, .loss-badge, .neutral-badge {
        display: inline-block;
        border-radius: var(--r-pill);
        padding: 0.32rem 0.7rem;
        font-weight: 800;
        font-size: 0.8rem;
        box-shadow: none;
    }
    .profit-badge { background: var(--brand-tint); color: var(--brand-strong); border: 1px solid var(--brand-tint-border); }
    .loss-badge { background: #fff1f2; color: var(--down); border: 1px solid #fecdd3; }
    .neutral-badge { background: var(--surface-inset); color: var(--ink-soft); border: 1px solid var(--hairline-strong); }
    .signal-pill {
        display: inline-flex;
        align-items: center;
        border-radius: var(--r-pill);
        padding: 0.34rem 0.7rem;
        font-size: 0.76rem;
        font-weight: 900;
        letter-spacing: 0.01em;
        margin-top: 0.6rem;
    }
    .signal-buy { color: var(--brand-strong); background: var(--brand-tint); border: 1px solid var(--brand-tint-border); }
    .signal-watch { color: var(--warn); background: #fffbeb; border: 1px solid #fde68a; }
    .signal-avoid { color: #be123c; background: #fff1f2; border: 1px solid #fecdd3; }

    /* ---- Metric chips ---- */
    .metrics-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(118px, 1fr));
        gap: 0.55rem;
        margin-top: 0.95rem;
    }
    .metric-chip {
        background: var(--surface-muted);
        border: 1px solid var(--hairline);
        border-radius: var(--r-sm);
        padding: 0.6rem 0.7rem;
        min-height: 64px;
        transition: background var(--t-fast), border-color var(--t-fast);
    }
    .metric-chip:hover { background: var(--surface-inset); border-color: var(--hairline-strong); }
    .metric-label {
        color: var(--ink-faint);
        display: block;
        font-size: 0.65rem;
        font-weight: 900;
        letter-spacing: 0.08em;
        text-transform: uppercase;
    }
    .metric-value {
        color: var(--ink);
        display: block;
        font-size: 0.95rem;
        font-weight: 900;
        margin-top: 0.24rem;
        word-break: break-word;
    }

    /* ---- Sections inside cards ---- */
    .card-section {
        margin-top: 0.78rem;
        padding: 0.8rem;
        border-radius: var(--r-sm);
        background: var(--surface-muted);
        border: 1px solid var(--hairline);
    }
    .section-row { display: flex; justify-content: space-between; align-items: center; gap: 0.7rem; flex-wrap: wrap; }
    .section-label {
        color: var(--ink-faint);
        font-size: 0.67rem;
        font-weight: 900;
        letter-spacing: 0.08em;
        text-transform: uppercase;
    }
    .section-strong { color: var(--ink); font-size: 0.86rem; font-weight: 900; }

    /* ---- Scenario boxes ---- */
    .scenario-grid {
        display: grid;
        grid-template-columns: repeat(2, minmax(0, 1fr));
        gap: 0.6rem;
        margin-top: 0.78rem;
    }
    .scenario-grid.scenario-grid-3 { grid-template-columns: repeat(3, minmax(0, 1fr)); }
    .scenario-box {
        border-radius: var(--r-sm);
        padding: 0.75rem;
        border: 1px solid var(--hairline);
        min-height: 108px;
        transition: transform var(--t-fast), box-shadow var(--t-fast);
    }
    .scenario-box:hover { transform: translateY(-2px); box-shadow: var(--sh-sm); }
    .scenario-title { font-size: 0.67rem; font-weight: 900; letter-spacing: 0.08em; text-transform: uppercase; }
    .scenario-action { color: var(--ink-soft); font-size: 0.8rem; font-weight: 700; margin-top: 0.35rem; min-height: 34px; }
    .scenario-price { font-size: 0.95rem; font-weight: 900; margin-top: 0.25rem; letter-spacing: -0.01em; }

    /* ---- Confluence checklist ---- */
    .check-list {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
        gap: 0.4rem;
        margin-top: 0.5rem;
    }
    .check-row {
        display: flex;
        justify-content: space-between;
        align-items: center;
        gap: 0.5rem;
        background: var(--surface);
        border: 1px solid var(--hairline);
        border-radius: var(--r-xs);
        padding: 0.42rem 0.55rem;
        font-size: 0.75rem;
        font-weight: 800;
    }
    .check-ok { color: var(--brand-strong); }
    .check-no { color: var(--ink-faint); }

    /* ---- Learning panel ---- */
    .learning-panel {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 1rem;
        flex-wrap: wrap;
        background: var(--surface);
        border: 1px solid var(--hairline);
        border-left: 4px solid var(--info);
        border-radius: var(--r-md);
        padding: 0.95rem 1.1rem;
        margin: 0.8rem 0 1rem;
        box-shadow: var(--sh-sm);
    }
    .learning-title { color: var(--ink); font-size: 1rem; font-weight: 900; margin-top: 0.18rem; letter-spacing: -0.01em; }
    .learning-note { color: var(--ink-soft); font-size: 0.84rem; font-weight: 600; margin-top: 0.25rem; }
    .learning-stats {
        display: grid;
        grid-template-columns: repeat(3, minmax(76px, 1fr));
        gap: 0.55rem;
        min-width: min(360px, 100%);
    }
    .learning-stats div {
        background: #eff6ff;
        border: 1px solid #dbeafe;
        border-radius: var(--r-sm);
        padding: 0.6rem 0.65rem;
        text-align: center;
    }
    .learning-stats span { display: block; color: #1d4ed8; font-size: 1.05rem; font-weight: 900; line-height: 1.1; }
    .learning-stats small {
        display: block;
        color: var(--ink-faint);
        font-size: 0.65rem;
        font-weight: 900;
        letter-spacing: 0.08em;
        text-transform: uppercase;
        margin-top: 0.2rem;
    }

    /* ---- News panel ---- */
    .news-panel {
        background: var(--surface);
        border: 1px solid var(--hairline);
        border-left: 4px solid var(--accent-gold);
        border-radius: var(--r-md);
        padding: 0.95rem 1.1rem;
        margin: 0.8rem 0 1rem;
        box-shadow: var(--sh-sm);
    }
    .news-list {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
        gap: 0.55rem;
        margin-top: 0.7rem;
    }
    .news-headline {
        display: block;
        color: var(--ink) !important;
        background: #fffaf2;
        border: 1px solid #fde7c8;
        border-radius: var(--r-xs);
        padding: 0.6rem 0.7rem;
        font-size: 0.8rem;
        font-weight: 700;
        text-decoration: none !important;
        line-height: 1.4;
        transition: transform var(--t-fast), box-shadow var(--t-fast);
    }
    .news-headline:hover { transform: translateY(-1px); box-shadow: var(--sh-sm); }
    .news-headline span {
        display: block;
        color: #c2410c;
        font-size: 0.64rem;
        font-weight: 900;
        letter-spacing: 0.08em;
        text-transform: uppercase;
        margin-bottom: 0.18rem;
    }

    /* ---- Sidebar ---- */
    section[data-testid="stSidebar"] {
        background: var(--surface) !important;
        border-right: 1px solid var(--hairline);
    }

    /* ---- Promo / pro cards ---- */
    .ad-banner {
        background: linear-gradient(135deg, #0f172a, #1e293b);
        border: 1px solid #243047;
        border-radius: var(--r-md);
        padding: 1rem 1.5rem;
        text-align: center;
    }
    .pro-card {
        background: linear-gradient(135deg, #1e1b4b, #312e81);
        border: 1px solid #4338ca;
        border-radius: var(--r-lg);
        padding: 2rem;
        text-align: center;
        box-shadow: var(--sh-md);
    }

    /* ---- Tabs ---- */
    .stDataFrame { border: 1px solid var(--hairline) !important; border-radius: var(--r-md) !important; }
    .stTabs [data-baseweb="tab-list"] { gap: 8px; background-color: transparent; }
    .stTabs [data-baseweb="tab"] {
        background: var(--surface);
        border: 1px solid var(--hairline);
        border-radius: var(--r-sm) var(--r-sm) 0 0;
        padding: 11px 26px;
        color: var(--ink-soft);
        font-weight: 700;
        transition: color var(--t-fast), background var(--t-fast);
    }
    .stTabs [data-baseweb="tab"]:hover { color: var(--ink); background: var(--surface-muted); }
    .stTabs [aria-selected="true"] {
        background: linear-gradient(135deg, var(--brand), var(--brand-strong)) !important;
        color: #fff !important;
        border-color: transparent !important;
    }

    /* ---- Primary Streamlit buttons ---- */
    div.stButton > button[kind="primary"] {
        background: linear-gradient(180deg, var(--brand), var(--brand-strong)) !important;
        border: 1px solid transparent !important;
        color: #fff !important;
        border-radius: var(--r-sm) !important;
        font-weight: 900 !important;
        min-height: 44px;
        box-shadow: var(--sh-brand);
        transition: transform var(--t-fast), box-shadow var(--t-fast);
    }
    div.stButton > button[kind="primary"]:hover {
        transform: translateY(-1px);
        box-shadow: 0 12px 30px rgba(4, 120, 87, 0.28) !important;
    }

    /* ---- Misc chips ---- */
    .wallet-text { font-family: 'SFMono-Regular', 'Courier New', monospace; font-size: 0.66rem; word-break: break-all; color: var(--ink-faint); }
    .freshness-badge {
        display: inline-flex;
        align-items: center;
        gap: 7px;
        background: var(--surface);
        color: var(--ink-soft);
        border: 1px solid var(--hairline-strong);
        border-radius: var(--r-pill);
        padding: 6px 14px;
        font-size: 0.8rem;
        font-weight: 700;
        box-shadow: var(--sh-xs);
    }
    .freshness-dot { width: 8px; height: 8px; border-radius: 50%; display: inline-block; }
    .freshness-dot.live { background: var(--up); animation: pulse 2s infinite; }
    .freshness-dot.stale { background: var(--accent-gold); }
    .freshness-dot.offline { background: var(--down); }

    .fomo-card {
        background: var(--surface);
        border-radius: var(--r-md);
        border: 1px solid #fde68a;
        padding: 1.2rem 0.85rem;
        text-align: center;
        margin-bottom: 0.5rem;
        box-shadow: var(--sh-sm);
    }

    /* ---- Loading screen ---- */
    .app-loading-screen {
        position: fixed;
        inset: 0;
        z-index: 999999;
        display: flex;
        align-items: center;
        justify-content: center;
        padding: 1.25rem;
        background:
            radial-gradient(900px 480px at 15% 0%, var(--bg-tint-a), transparent 55%),
            radial-gradient(800px 460px at 90% 10%, var(--bg-tint-b), transparent 50%),
            var(--bg-app);
    }
    .app-loading-panel {
        width: min(460px, 92vw);
        background: var(--surface);
        border: 1px solid var(--hairline);
        border-radius: var(--r-lg);
        padding: 1.5rem;
        box-shadow: var(--sh-lg);
    }
    .app-loading-top { display: grid; grid-template-columns: 74px 1fr; gap: 1rem; align-items: center; }
    .app-loading-symbol { position: relative; width: 64px; height: 64px; display: grid; place-items: center; }
    .app-loading-ring {
        position: absolute;
        inset: 0;
        border-radius: 50%;
        border: 4px solid var(--surface-inset);
        border-top-color: var(--brand);
        border-right-color: var(--accent-gold);
        animation: loaderSpin 0.9s linear infinite;
    }
    .app-loading-coin {
        width: 42px;
        height: 42px;
        border-radius: 50%;
        display: grid;
        place-items: center;
        background: linear-gradient(135deg, var(--accent-gold), var(--brand));
        color: #fff;
        font-size: 1.4rem;
        font-weight: 900;
        box-shadow: var(--sh-brand);
    }
    .app-loading-kicker { margin: 0 0 0.2rem 0; color: var(--brand-strong); font-size: 0.72rem; font-weight: 900; letter-spacing: 0.14em; }
    .app-loading-title { margin: 0; color: var(--ink); font-size: 1.2rem; line-height: 1.25; font-weight: 900; letter-spacing: -0.01em; }
    .app-loading-detail { margin: 0.35rem 0 0 0; color: var(--ink-soft); font-size: 0.88rem; line-height: 1.45; font-weight: 500; }
    .app-loading-bars { display: grid; grid-template-columns: 1.2fr 0.8fr 1fr; gap: 0.45rem; margin-top: 1.15rem; }
    .app-loading-bars span {
        height: 8px;
        border-radius: 999px;
        background: linear-gradient(90deg, var(--brand), var(--accent-gold), var(--info));
        background-size: 220% 100%;
        animation: loaderBar 1.15s ease-in-out infinite;
    }
    .app-loading-bars span:nth-child(2) { animation-delay: 0.13s; }
    .app-loading-bars span:nth-child(3) { animation-delay: 0.26s; }

    @keyframes loaderSpin { to { transform: rotate(360deg); } }
    @keyframes loaderBar {
        0%, 100% { opacity: 0.35; background-position: 0% 50%; transform: scaleX(0.82); }
        50% { opacity: 1; background-position: 100% 50%; transform: scaleX(1); }
    }
    @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.4; } }

    /* ---- Responsive ---- */
    @media (max-width: 768px) {
        h1 { font-size: 1.7rem !important; }
        .app-title { font-size: 1.7rem; }
        .app-shell-header { padding: 1.1rem; }
        .quick-links { justify-content: flex-start; }
        .coin-price-wrap { justify-content: flex-start; }
        .scenario-grid { grid-template-columns: 1fr; }
        .price-tag { font-size: 1.3rem !important; }
        .buy-button { padding: 12px 28px; font-size: 1rem; }
        .rekomendasi-hero { padding: 1.2rem; }
    }
    @media (max-width: 480px) {
        .app-loading-panel { padding: 1.1rem; }
        .app-loading-top { grid-template-columns: 58px 1fr; gap: 0.8rem; }
        .app-loading-symbol { width: 52px; height: 52px; }
        .app-loading-coin { width: 34px; height: 34px; font-size: 1.1rem; }
        .app-loading-title { font-size: 1rem; }
    }
    @media (prefers-reduced-motion: reduce) {
        .app-loading-ring, .app-loading-bars span, .rekomendasi-hero::before,
        .freshness-dot.live { animation: none !important; }
        .buy-button, .quick-link, .stat-card, .rekomendasi-card, .scenario-box,
        .buy-button-sm, .news-headline { transition: none !important; }
    }
    button[title="View fullscreen"] { display: none !important; }
    </style>
    """,
    unsafe_allow_html=True,
)


def loading_markup(title="Membaca market crypto...", detail="Mengambil harga Indodax dan menyiapkan rekomendasi terbaru."):
    return f"""
    <div class="app-loading-screen" role="status" aria-live="polite">
        <div class="app-loading-panel">
            <div class="app-loading-top">
                <div class="app-loading-symbol" aria-hidden="true">
                    <div class="app-loading-ring"></div>
                    <div class="app-loading-coin">₿</div>
                </div>
                <div>
                    <p class="app-loading-kicker">LIVE MARKET</p>
                    <h2 class="app-loading-title">{title}</h2>
                    <p class="app-loading-detail">{detail}</p>
                </div>
            </div>
            <div class="app-loading-bars" aria-hidden="true">
                <span></span><span></span><span></span>
            </div>
        </div>
    </div>
    """


# =============================================================================
# DATA FETCHING
# =============================================================================
@st.cache_data(ttl=60, show_spinner=False)
def fetch_indodax_tickers():
    """Fetch all tickers and 24h reference prices from Indodax Summaries API."""
    try:
        resp = requests.get("https://indodax.com/api/summaries", timeout=10)
        data = resp.json()
        tickers = data.get("tickers", {})
        prices_24h = data.get("prices_24h", {})
        
        server_time = None
        if tickers:
            # Extract server time from the first available ticker
            first_ticker = list(tickers.values())[0]
            server_time = first_ticker.get("server_time")
            
        if server_time:
            try:
                server_dt = datetime.fromtimestamp(int(server_time), tz=timezone.utc)
            except (ValueError, OSError):
                server_dt = datetime.now(timezone.utc)
        else:
            server_dt = datetime.now(timezone.utc)
        return tickers, prices_24h, server_dt, None
    except requests.RequestException as e:
        return None, None, None, str(e)
    except (KeyError, ValueError, TypeError) as e:
        return None, None, None, str(e)


def fetch_all_ticker_data():
    """Main fetch function — tries live Summaries API first, fallback to shared tickers."""
    shared_tickers, shared_at, shared_err = _read_shared_tickers()
    tickers, prices_24h, server_time, error = fetch_indodax_tickers()
    if tickers:
        _write_shared_tickers(tickers)
        return tickers, prices_24h, server_time, None
    if shared_tickers:
        return shared_tickers, {}, shared_at, "⚠️ Data dari cache (API timeout)"
    return {}, {}, datetime.now(), "❌ Gagal ambil data"


@st.cache_data(ttl=900, show_spinner=False)
def fetch_cached_news_profile(symbols):
    return build_news_profile(symbols=list(symbols))


def calculate_24h_change(price, pair, prices_24h):
    """
    Hitung change 24h pakai prices_24h dari /api/summaries.
    Jangan fallback ke low karena bikin bias bullish.
    """
    try:
        pair_key = pair.replace("_", "")
        ref_price = float((prices_24h or {}).get(pair_key, 0))

        if ref_price <= 0:
            return 0.0

        return ((float(price) - ref_price) / ref_price) * 100
    except (TypeError, ValueError, ZeroDivisionError):
        return 0.0


def extract_asset_data(tickers, prices_24h, asset_dict):
    """Extract price data with accurate 24h change from prices_24h."""
    result = {}

    for symbol, (pair, _) in asset_dict.items():
        if pair not in tickers:
            continue

        try:
            info = tickers[pair]
            price = float(info["last"])
            high = float(info.get("high", 0))
            low = float(info.get("low", 0))
            vol_idr = float(info.get("vol_idr", 0))

            change = calculate_24h_change(price, pair, prices_24h)

            result[symbol] = {
                "symbol": symbol,
                "pair": pair,
                "price": price,
                "high": high,
                "low": low,
                "vol_idr": vol_idr,
                "change": round(change, 2),
            }

        except (KeyError, ValueError, TypeError):
            continue

    return result


def format_idr(value):
    if value is None or value == 0:
        return "Rp0"
    if value >= 1_000_000_000:
        return f"Rp{value/1_000_000_000:.2f}B"
    if value >= 1_000_000:
        return f"Rp{value/1_000_000:.2f}JT"
    if value >= 1_000:
        return f"Rp{value:,.0f}"
    return f"Rp{value:,.0f}"


def format_price(value):
    if value is None:
        return "-"
    if value >= 1_000_000:
        return f"Rp{value/1_000_000:,.2f}JT"
    if value >= 1_000:
        return f"Rp{value:,.0f}"
    if value >= 1:
        return f"Rp{value:,.2f}"
    return f"Rp{value:,.8f}"


# =============================================================================
# TECHNICAL INDICATORS (dari telegram_bot.py asli)
# =============================================================================


# =============================================================================
# CANDLE FETCHING
# =============================================================================


# =============================================================================
# MARKET ANALYSIS (UPGRADED dengan indikator teknikal)
# =============================================================================
def compute_market_stats(tickers, prices_24h):
    """Compute market statistics using real 24h reference price."""
    idr_pairs = {k: v for k, v in tickers.items() if k.endswith("_idr")}

    if not idr_pairs:
        return None

    changes = []
    volumes = []
    green_count = 0
    red_count = 0

    for pair, info in idr_pairs.items():
        try:
            price = float(info["last"])
            vol = float(info.get("vol_idr", 0))
            change = calculate_24h_change(price, pair, prices_24h)

            changes.append(change)
            volumes.append(vol)

            if change > 0:
                green_count += 1
            elif change < 0:
                red_count += 1

        except (ValueError, TypeError, KeyError):
            continue

    if not changes:
        return None

    total = len(changes)
    green_pct = (green_count / total) * 100
    avg_change = sum(changes) / len(changes)
    total_vol = sum(volumes)

    if green_pct >= 70:
        mode = "aggressive"
    elif green_pct >= 40:
        mode = "normal"
    else:
        mode = "defensive"

    return {
        "total_pairs": total,
        "green_count": green_count,
        "red_count": red_count,
        "green_pct": round(green_pct, 1),
        "avg_change": round(avg_change, 2),
        "total_vol": total_vol,
        "mode": mode,
    }


def analyze_coin_advanced(symbol, data, candles, market_stats, market_regime=None):
    """Analisis lengkap satu koin menggunakan semua indikator teknikal."""
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

    # Intelligence layer (swing S/R, Fib, divergence, candle patterns, regime, VWAP)
    atr_for_intel = compute_atr(candles)
    atr_pct = (atr_for_intel / price * 100) if (atr_for_intel and price > 0) else 3.0
    intel = build_intelligence_bundle(candles, price, atr_pct=atr_pct)

    # Smart engine (pandas-ta: Ichimoku, Squeeze, OBV, MFI). No-op kalau pandas-ta belum install.
    smart = smart_engine.build_smart_indicators_bundle(candles)

    # Multi-horizon forecast: ramalan probabilistik 6 jam (step1) & 24 jam (step2)
    forecast = compute_multi_horizon_forecast(candles, price)

    # Binance global sentiment (funding rate, long/short, order book)
    binance_data = {}
    if BINANCE_ENGINE_AVAILABLE:
        try:
            binance_data = binance_engine.fetch_binance_sentiment(symbol)
        except Exception:
            pass
    binance_adj = binance_data.get("binance_adjustment", 0) if binance_data.get("available") else 0

    # Forecast adjustment: boost score saat probabilitas tinggi & confidence baik.
    # Kombinasi step1 + step2 supaya horizon menengah & pendek selaras.
    f1_prob = forecast["step1"]["prob_up_pct"]
    f2_prob = forecast["step2"]["prob_up_pct"]
    f1_conf = forecast["step1"]["confidence"]
    f2_conf = forecast["step2"]["confidence"]
    f_conf_mult = {"tinggi": 1.0, "sedang": 0.6, "rendah": 0.3}
    forecast_adj = (
        (f1_prob - 50) * 0.10 * f_conf_mult.get(f1_conf, 0.3)
        + (f2_prob - 50) * 0.08 * f_conf_mult.get(f2_conf, 0.3)
    )
    forecast_adj = clamp(forecast_adj, -10, 8)

    # --- SCORING (UPGRADED) ---
    liquidity_bonus = min(16, vol_idr / 1_000_000_000)
    fomo_penalty = 9 if range_pos > 88 and change > 8 else 0
    micin_penalty = 6 if symbol in MICIN_SYMBOLS else 0

    tech_score = 0
    tech_score += clamp(ema_trend_pct * 3, -12, 12)
    tech_score += 8 if macd_signal == "bullish cross" else 5 if macd_signal == "bullish" else -8 if macd_signal == "bearish cross" else -5 if macd_signal == "bearish" else 0
    tech_score += 6 if 45 <= rsi <= 68 else -7 if rsi > 78 else -4 if rsi < 30 else 0
    tech_score += 5 if supertrend == "bullish" else -6 if supertrend == "bearish" else 0
    tech_score += 4 if vol_label in ("spike", "kuat") else -3 if vol_label == "tipis" else 0

    bb_bonus = 7 if bb["bb_signal"] == "oversold" else -5 if bb["bb_signal"] == "overbought" else 0
    adx_bonus = 5 if adx_data["trend"] in ("bullish_strong","bullish") else -5 if adx_data["trend"] in ("bearish_strong","bearish") else 0

    # ML adjustment
    ml_adj = (ml["ml_prob"] - 50) * 0.28
    if ml["ml_conf"] == "rendah": ml_adj *= 0.45
    elif ml["ml_conf"] == "sedang": ml_adj *= 0.75

    # Backtest adjustment
    bt_adj = 0
    if bt["bt_trades"] >= 6:
        bt_adj = (bt["bt_wr"] - 50) * 0.12

    # Market mode adjustment
    mode = market_stats.get("mode", "normal") if market_stats else "normal"
    mode_rules = MARKET_MODE_RULES.get(mode, MARKET_MODE_RULES["normal"])
    # Regime BTC: peredam global. Default netral kalau tidak disuplai.
    regime = market_regime or {"regime": "NO DATA", "regime_adjustment": 0, "allow_aggressive": True}
    regime_adj = regime.get("regime_adjustment", 0)
    base = (
        50
        + change * 4.2
        + liquidity_bonus
        + tech_score * 0.65
        + bb_bonus
        + adx_bonus
        + ml_adj
        + bt_adj
        + mtf["mtf_adjustment"]
        + intel.get("intel_adjustment", 0)
        + smart.get("smart_adjustment", 0)
        + forecast_adj
        + binance_adj
        - fomo_penalty
        - micin_penalty
        + mode_rules.get("score_adjustment", 0)
        + regime_adj
    )
    score = int(clamp(round(base), 0, 100))

    # Risk level (dibutuhkan committee verdict)
    risk_level = compute_risk_level(change, vol_idr, rsi, macd_signal, supertrend, range_pos, ml, bt)

    # Verdict committee
    verdict, verdict_net, size_mult = build_verdict(score, rsi, macd_signal, supertrend, adx_data, ml, bt, risk_level, vol_idr)

    # Keputusan action + semua gate (threshold, confluence, anti-FOMO, MTF,
    # regime, verdict) — terpadu via core.analysis, IDENTIK dengan bot Telegram.
    action, emoji = decide_action(
        score=score, change=change, confluence=confluence, range_pos=range_pos,
        mtf_adjustment=mtf["mtf_adjustment"],
        regime_allow_aggressive=regime.get("allow_aggressive", True),
        verdict=verdict,
    )

    # --- ENTRY ZONE & TWO STEPS AHEAD (adaptive: pakai swing S/R + ATR riil) ---
    # Two Steps Ahead pakai swing high/low riil dari intel; fallback otomatis ke ATR jika swing kosong
    atr_for_steps = atr_for_intel
    steps = build_two_steps_ahead(price, action, intel.get("swings", {}), atr_for_steps)
    step1_action = steps["step1_action"]
    step1_price = steps["step1_price"]
    step1_gain = steps["step1_gain"]
    step2_action = steps["step2_action"]
    step2_price = steps["step2_price"]
    step2_gain = steps["step2_gain"]
    fail_action = steps["fail_action"]
    fail_price = steps["fail_price"]
    fail_loss = steps["fail_loss"]
    support_s1 = steps["support_s1"]
    support_s2 = steps["support_s2"]
    resistance_r1 = steps["resistance_r1"]
    resistance_r2 = steps["resistance_r2"]

    # Entry Zone: dari Fibonacci golden zone bila tersedia, fallback ke S1 zone
    fib_data = intel.get("fib", {})
    fib_zone = fib_data.get("fib_zone", "NO DATA")
    fib_500 = fib_data.get("fib_500")
    fib_618 = fib_data.get("fib_618")
    if fib_500 and fib_618 and fib_500 > 0 and fib_618 > 0 and fib_618 < price:
        entry_zone_low = fib_618
        entry_zone_high = min(price * 1.005, fib_500)
        if entry_zone_high <= entry_zone_low:
            entry_zone_high = entry_zone_low * 1.01
        entry_zone_label = f"Golden zone {fib_zone}" if "GOLDEN" in fib_zone else "Tarik mundur ke 0.618"
    else:
        # fallback dari swing support kalau tidak ada fib valid
        entry_zone_low = support_s1 if support_s1 > 0 else price * 0.97
        entry_zone_high = price * 1.005
        entry_zone_label = "Koreksi" if range_pos > 70 else "Saat ini" if range_pos < 30 else "Netral"

    # TP/SL & alokasi terpadu via core.analysis (ATR-adaptif, IDENTIK dgn bot).
    atr = atr_for_intel
    levels = compute_trade_levels(price, change, score, risk_level, atr=atr)
    tp1 = levels["tp1"]
    tp2 = levels["tp2"]
    target = levels["target"]
    stop_loss = levels["stop_loss"]
    trailing = levels["trailing_pct"]

    market_mult = mode_rules.get("allocation_multiplier", 1.0)
    alloc = compute_allocation(score, risk_level, confluence, action,
                               size_mult=size_mult, market_mult=market_mult)

    category = COIN_CATEGORIES.get(symbol, "Lainnya")
    category_color = CATEGORY_COLORS.get(category, "#6b7280")

    return {
        "symbol": symbol, "pair": data["pair"],
        "price": price, "change": change, "vol_idr": vol_idr,
        "score": score, "action": action, "emoji": emoji,
        "rsi": round(rsi, 1), "ema_bias": ema_bias, "macd_signal": macd_signal,
        "bb_signal": bb["bb_signal"], "supertrend": supertrend,
        "adx": adx_data["adx"], "adx_trend": adx_data["trend"],
        "ml_prob": ml["ml_prob"], "ml_label": ml["ml_label"], "ml_conf": ml["ml_conf"],
        "bt_wr": bt["bt_wr"], "bt_trades": bt["bt_trades"], "bt_label": bt["bt_label"],
        "bt_oos_wr": bt.get("bt_oos_wr"), "bt_avg_net_pct": bt.get("bt_avg_net_pct"),
        "bt_cost_pct": bt.get("bt_cost_pct"),
        "btc_regime": regime.get("regime"), "btc_regime_adjustment": regime.get("regime_adjustment", 0),
        "verdict": verdict, "verdict_net": verdict_net,
        "vol_label": vol_label, "risk_level": risk_level,
        "tp1": tp1, "tp2": tp2, "target": target, "stop_loss": stop_loss,
        "trailing_stop_pct": round(trailing, 1), "allocation_pct": round(alloc, 1),
        "range_pos": round(range_pos, 1),
        "mtf_label": mtf["mtf_label"],
        "mtf_4h": mtf["mtf_4h"],
        "mtf_1d": mtf["mtf_1d"],
        "mtf_score": mtf["mtf_score"],
        "mtf_adjustment": mtf["mtf_adjustment"],
        "category": category, "category_color": category_color,
        # Entry Zone
        "entry_zone_low": entry_zone_low,
        "entry_zone_high": entry_zone_high,
        "entry_zone_label": entry_zone_label,
        # Two Steps Ahead
        "step1_action": step1_action,
        "step1_price": step1_price,
        "step1_gain": step1_gain,
        "step2_action": step2_action,
        "step2_price": step2_price,
        "step2_gain": step2_gain,
        "fail_action": fail_action,
        "fail_price": fail_price,
        "fail_loss": fail_loss,
        # Support & Resistance
        "support_s1": support_s1,
        "support_s2": support_s2,
        "resistance_r1": resistance_r1,
        "resistance_r2": resistance_r2,
        # Confluence Gate
        "confluence_passed": confluence["confluence_passed"],
        "confluence_total": confluence["confluence_total"],
        "confluence_label": confluence["confluence_label"],
        "confluence_strength": confluence["confluence_strength"],
        "confluence_checks": confluence["checks"],
        # Intelligence layer
        "intel_adjustment": intel.get("intel_adjustment", 0),
        "intel_confidence": intel.get("intel_confidence", "LEMAH"),
        "intel_notes": intel.get("intel_notes", []),
        "divergence": intel.get("divergence", {}).get("divergence", "NONE"),
        "candle_pattern": intel.get("candle", {}).get("candle_pattern", "NONE"),
        "candle_bias": intel.get("candle", {}).get("candle_bias", "neutral"),
        "regime": intel.get("regime", {}).get("regime", "MIXED"),
        "choppiness": intel.get("regime", {}).get("choppiness", 50.0),
        "vwap": intel.get("vwap", {}).get("vwap"),
        "vwap_bias": intel.get("vwap", {}).get("vwap_bias", "neutral"),
        "vwap_distance_pct": intel.get("vwap", {}).get("vwap_distance_pct", 0.0),
        "fib_zone": intel.get("fib", {}).get("fib_zone", "NO DATA"),
        "fib_618": intel.get("fib", {}).get("fib_618"),
        "fib_500": intel.get("fib", {}).get("fib_500"),
        "swing_quality": intel.get("swings", {}).get("swing_quality", "DATA KURANG"),
        "vol_label_ext": intel.get("vol", {}).get("vol_label", "normal"),
        # Smart engine layer (pandas-ta)
        "smart_adjustment": smart.get("smart_adjustment", 0),
        "smart_notes": smart.get("smart_notes", []),
        "ichimoku_signal": smart.get("ichimoku", {}).get("ichimoku_signal", "NO DATA"),
        "squeeze": smart.get("squeeze", {}).get("squeeze", "NO DATA"),
        "obv_signal": smart.get("obv", {}).get("obv_signal", "NO DATA"),
        "mfi": smart.get("mfi", {}).get("mfi", 50.0),
        "mfi_signal": smart.get("mfi", {}).get("mfi_signal", "NEUTRAL"),
        # Multi-horizon forecast (ramalan 2 langkah ke depan)
        "forecast_step1_horizon": forecast["step1"]["horizon"],
        "forecast_step1_prob": forecast["step1"]["prob_up_pct"],
        "forecast_step1_strong": forecast["step1"]["prob_strong_pct"],
        "forecast_step1_low": forecast["step1"]["price_low"],
        "forecast_step1_high": forecast["step1"]["price_high"],
        "forecast_step1_median": forecast["step1"]["price_median"],
        "forecast_step1_low_pct": forecast["step1"]["range_low_pct"],
        "forecast_step1_high_pct": forecast["step1"]["range_high_pct"],
        "forecast_step1_median_pct": forecast["step1"]["range_median_pct"],
        "forecast_step1_conf": forecast["step1"]["confidence"],
        "forecast_step2_horizon": forecast["step2"]["horizon"],
        "forecast_step2_prob": forecast["step2"]["prob_up_pct"],
        "forecast_step2_strong": forecast["step2"]["prob_strong_pct"],
        "forecast_step2_low": forecast["step2"]["price_low"],
        "forecast_step2_high": forecast["step2"]["price_high"],
        "forecast_step2_median": forecast["step2"]["price_median"],
        "forecast_step2_low_pct": forecast["step2"]["range_low_pct"],
        "forecast_step2_high_pct": forecast["step2"]["range_high_pct"],
        "forecast_step2_median_pct": forecast["step2"]["range_median_pct"],
        "forecast_step2_conf": forecast["step2"]["confidence"],
        # Binance global sentiment
        "binance_signal": binance_data.get("binance_signal", "NO DATA"),
        "binance_adjustment": binance_data.get("binance_adjustment", 0),
        "binance_notes": binance_data.get("binance_notes", []),
        "binance_funding_signal": binance_data.get("funding", {}).get("funding_signal", "NO DATA"),
        "binance_funding_pct": binance_data.get("funding", {}).get("funding_pct", 0),
        "binance_ls_ratio": binance_data.get("long_short", {}).get("ls_ratio", 0),
        "binance_ls_signal": binance_data.get("long_short", {}).get("ls_signal", "NO DATA"),
        "binance_book_ratio": binance_data.get("order_book", {}).get("book_ratio", 0),
        "binance_book_signal": binance_data.get("order_book", {}).get("book_signal", "NO DATA"),
        "binance_available": binance_data.get("available", False),
    }


@st.cache_data(ttl=300, show_spinner=False)
def _cached_fetch_candles_parallel(pairs_list):
    """Fetch candles for all pairs in parallel to save time (cache 5 menit)."""
    from concurrent.futures import ThreadPoolExecutor
    unique_pairs = list(set(pairs_list))
    results_map = {}
    
    def fetch_one(p):
        try:
            return p, fetch_candles(p)
        except Exception:
            return p, pd.DataFrame()
            
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(fetch_one, p) for p in unique_pairs]
        for fut in futures:
            p, df = fut.result()
            results_map[p] = df
            
    return results_map


def _empty_learning_journal():
    return {"version": 1, "signals": [], "updated_at": None}


def load_learning_journal():
    """Delegate ke journal_store. Backend SQLite dengan auto-migrate dari JSON,
    fallback otomatis ke JSON kalau filesystem read-only."""
    if not SIGNAL_LEARNING_ENABLED:
        return _empty_learning_journal()
    return journal_store.load_journal()


def save_learning_journal(journal):
    """Delegate ke journal_store. Tetap silent-fail seperti sebelumnya."""
    if not SIGNAL_LEARNING_ENABLED:
        return
    journal_store.save_journal(journal)


def _parse_iso_datetime(value):
    try:
        return datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


def build_learning_profile(journal):
    all_signals = journal.get("signals", [])
    # Pisahkan paper-trade (source=early) dari sinyal nyata agar stats learning
    # web tidak tercemar simulasi "andai beli".
    signals = [s for s in all_signals if s.get("source") != "early"]
    paper = [s for s in all_signals if s.get("source") == "early"]
    closed = [s for s in signals if s.get("status") in {"TARGET", "TP", "SL", "EXPIRED"}]
    wins = [s for s in closed if s.get("outcome") == "WIN"]
    losses = [s for s in closed if s.get("outcome") == "LOSS"]
    active = [s for s in signals if s.get("status") == "OPEN"]

    by_symbol = {}
    for sig in closed:
        symbol = sig.get("symbol")
        if not symbol:
            continue
        stats = by_symbol.setdefault(symbol, {"closed": 0, "wins": 0, "losses": 0, "max_gain_sum": 0.0})
        stats["closed"] += 1
        stats["wins"] += 1 if sig.get("outcome") == "WIN" else 0
        stats["losses"] += 1 if sig.get("outcome") == "LOSS" else 0
        stats["max_gain_sum"] += float(sig.get("max_gain_pct", 0) or 0)

    for stats in by_symbol.values():
        stats["winrate"] = round(stats["wins"] / stats["closed"] * 100, 1) if stats["closed"] else 0.0
        stats["avg_max_gain"] = round(stats["max_gain_sum"] / stats["closed"], 2) if stats["closed"] else 0.0

    winrate = round(len(wins) / len(closed) * 100, 1) if closed else None
    best_symbols = sorted(
        ((sym, stats) for sym, stats in by_symbol.items() if stats["closed"] >= 2),
        key=lambda item: (item[1]["winrate"], item[1]["closed"]),
        reverse=True,
    )[:3]

    paper_closed = [s for s in paper if s.get("status") in {"TARGET", "TP", "SL", "EXPIRED"}]
    paper_wins = [s for s in paper_closed if s.get("outcome") == "WIN"]

    return {
        "enabled": SIGNAL_LEARNING_ENABLED,
        "total_signals": len(signals),
        "closed": len(closed),
        "wins": len(wins),
        "losses": len(losses),
        "active": len(active),
        "winrate": winrate,
        "by_symbol": by_symbol,
        "best_symbols": best_symbols,
        "paper_active": len([s for s in paper if s.get("status") == "OPEN"]),
        "paper_closed": len(paper_closed),
        "paper_wins": len(paper_wins),
        "paper_winrate": round(len(paper_wins) / len(paper_closed) * 100, 1) if paper_closed else None,
        "updated_at": journal.get("updated_at"),
    }


def apply_learning_adjustments(results, profile):
    by_symbol = profile.get("by_symbol", {})
    for item in results:
        stats = by_symbol.get(item.get("symbol"), {})
        closed = stats.get("closed", 0)
        adjustment = 0
        note = "Mengumpulkan data"
        if closed >= 3:
            winrate = stats.get("winrate", 0)
            if winrate >= 70:
                adjustment = 5
                note = f"Riwayat kuat ({winrate:.0f}% WR)"
            elif winrate >= 58:
                adjustment = 2
                note = f"Riwayat positif ({winrate:.0f}% WR)"
            elif winrate <= 38:
                adjustment = -6
                note = f"Riwayat lemah ({winrate:.0f}% WR)"
            elif winrate <= 48:
                adjustment = -3
                note = f"Riwayat hati-hati ({winrate:.0f}% WR)"
            else:
                note = f"Riwayat netral ({winrate:.0f}% WR)"

        original_score = int(item.get("score", 0))
        item["learning_adjustment"] = adjustment
        item["learning_note"] = note
        item["learning_trades"] = closed
        if adjustment:
            item["score"] = int(clamp(original_score + adjustment, 0, 100))
            if item.get("allocation_pct", 0) > 0:
                item["allocation_pct"] = round(clamp(item["allocation_pct"] * (1 + adjustment / 25), 0, 10), 1)
        # Kelly Criterion: blend allocation dengan winrate historis (jika cukup riwayat)
        apply_kelly_to_allocation(item, profile)
    return results


def update_learning_journal(results):
    journal = load_learning_journal()
    if not SIGNAL_LEARNING_ENABLED:
        return build_learning_profile(journal)

    now = datetime.now(BOT_WIB)
    changed = False
    price_map = {item["symbol"]: float(item.get("price", 0) or 0) for item in results}

    for sig in journal.get("signals", []):
        if sig.get("status") != "OPEN":
            continue
        symbol = sig.get("symbol")
        price = price_map.get(symbol)
        if not price:
            continue
        entry = float(sig.get("entry", price) or price)
        sig["last_price"] = price
        
        old_max = float(sig.get("max_price", entry) or entry)
        old_min = float(sig.get("min_price", entry) or entry)
        old_tp1_hit = sig.get("tp1_hit", False)

        new_max = max(old_max, price)
        new_min = min(old_min, price)

        sig["max_price"] = new_max
        sig["min_price"] = new_min
        sig["max_gain_pct"] = round((new_max - entry) / entry * 100, 2) if entry > 0 else 0
        sig["max_drawdown_pct"] = round((new_min - entry) / entry * 100, 2) if entry > 0 else 0

        if new_max != old_max or new_min != old_min:
            changed = True

        opened_at = _parse_iso_datetime(sig.get("opened_at")) or now
        age_hours = (now - opened_at).total_seconds() / 3600
        stop_loss = float(sig.get("stop_loss", 0) or 0)
        tp1 = float(sig.get("tp1", 0) or 0)
        target = float(sig.get("target", 0) or 0)

        if tp1 > 0 and price >= tp1 and not old_tp1_hit:
            sig["tp1_hit"] = True
            changed = True

        if target > 0 and price >= target:
            sig["status"] = "TARGET"
            sig["outcome"] = "WIN"
            sig["closed_at"] = now.isoformat()
            changed = True
        elif stop_loss > 0 and price <= stop_loss:
            sig["status"] = "SL"
            sig["outcome"] = "WIN" if sig.get("tp1_hit") else "LOSS"
            sig["closed_at"] = now.isoformat()
            changed = True
        elif age_hours >= SIGNAL_LEARNING_TTL_HOURS:
            sig["status"] = "TP" if sig.get("tp1_hit") else "EXPIRED"
            sig["outcome"] = "WIN" if sig.get("tp1_hit") else "LOSS"
            sig["closed_at"] = now.isoformat()
            changed = True

    open_symbols = {s.get("symbol") for s in journal.get("signals", []) if s.get("status") == "OPEN"}
    for item in results:
        if not (
            is_entry_action(item.get("action", ""))
            and item.get("allocation_pct", 0) > 0
            and item.get("confluence_passed", 0) >= 4
        ):
            continue
        symbol = item["symbol"]
        if symbol in open_symbols:
            continue
        last_same = next((s for s in reversed(journal.get("signals", [])) if s.get("symbol") == symbol), None)
        if last_same:
            opened_at = _parse_iso_datetime(last_same.get("opened_at"))
            if opened_at and (now - opened_at).total_seconds() < SIGNAL_LEARNING_DEDUPE_HOURS * 3600:
                continue
        journal["signals"].append({
            "symbol": symbol,
            "pair": item.get("pair"),
            "action": item.get("action"),
            "entry": float(item.get("price", 0) or 0),
            "score": int(item.get("score", 0) or 0),
            "allocation_pct": float(item.get("allocation_pct", 0) or 0),
            "tp1": float(item.get("tp1", 0) or 0),
            "tp2": float(item.get("tp2", 0) or 0),
            "target": float(item.get("target", 0) or 0),
            "stop_loss": float(item.get("stop_loss", 0) or 0),
            "opened_at": now.isoformat(),
            "status": "OPEN",
            "outcome": None,
            "tp1_hit": False,
            "max_price": float(item.get("price", 0) or 0),
            "min_price": float(item.get("price", 0) or 0),
            "max_gain_pct": 0.0,
            "max_drawdown_pct": 0.0,
        })
        open_symbols.add(symbol)
        changed = True

    if changed:
        save_learning_journal(journal)
    return build_learning_profile(journal)


def analyze_assets(assets_data, market_stats, tickers=None):
    """Analyze all assets with advanced technical indicators in parallel."""
    results = []
    total = len(assets_data)
    
    if total > 0:
        progress_bar = st.progress(0, text="🔍 Menganalisis aset...")
    
    # Fetch all candles in parallel to prevent 15-second loading delay
    pairs_list = [data["pair"] for data in assets_data.values()]
    candles_map = _cached_fetch_candles_parallel(tuple(pairs_list))

    # Regime pasar global dari BTC, dihitung SEKALI lalu dipakai semua koin.
    # Kalau BTC ambruk, altcoin diberi peredam skor (hindari beli saat market jatuh).
    btc_pair = MAIN_ASSETS.get("BTC", ("btc_idr",))[0]
    btc_candles = candles_map.get(btc_pair, pd.DataFrame())
    market_regime = compute_market_regime(btc_candles)

    for idx, (symbol, data) in enumerate(assets_data.items()):
        pair = data["pair"]
        candles = candles_map.get(pair, pd.DataFrame())
        result = analyze_coin_advanced(symbol, data, candles, market_stats, market_regime)
        results.append(result)
        if total > 0:
            progress_bar.progress((idx + 1) / total, text=f"📊 {symbol} ({idx+1}/{total})")
    
    if total > 0:
        progress_bar.empty()
    
    priority = {"BELI KUAT": 0, "CICIL BELI": 1, "WATCH": 2, "JANGAN BELI": 3, "HINDARI": 4}
    results.sort(key=lambda x: (priority.get(x["action"], 5), -x["score"]))
    return results


def render_learning_panel(profile):
    if not profile.get("enabled"):
        return
    winrate = profile.get("winrate")
    winrate_text = f"{winrate:.1f}%" if winrate is not None else "Belum ada"
    best_symbols = profile.get("best_symbols", [])
    if best_symbols:
        best_text = " · ".join(
            f"{sym} {stats['winrate']:.0f}%/{stats['closed']}x"
            for sym, stats in best_symbols
        )
    else:
        best_text = "Mengumpulkan data sinyal valid"
    # Paper-trade ("andai beli") dari early signal bot — info terpisah.
    paper_closed = profile.get("paper_closed", 0)
    paper_active = profile.get("paper_active", 0)
    paper_wr = profile.get("paper_winrate")
    if paper_closed or paper_active:
        paper_wr_text = f"{paper_wr:.0f}%" if paper_wr is not None else "—"
        paper_note = (
            f"🔮 Andai beli (early): {paper_active} aktif · {paper_closed} selesai · WR {paper_wr_text} "
            f"— simulasi, bukan transaksi nyata"
        )
    else:
        paper_note = "🔮 Andai beli (early): belum ada sinyal dini tercatat"
    st.markdown(
        f"""
        <div class="learning-panel">
            <div>
                <div class="section-label">Learning engine</div>
                <div class="learning-title">Web mulai belajar dari hasil sinyal</div>
                <div class="learning-note">{best_text}</div>
                <div class="learning-note" style="margin-top:0.2rem;color:#0369a1">{paper_note}</div>
            </div>
            <div class="learning-stats">
                <div><span>{profile.get('active', 0)}</span><small>Aktif</small></div>
                <div><span>{profile.get('closed', 0)}</span><small>Selesai</small></div>
                <div><span>{winrate_text}</span><small>Winrate</small></div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_news_panel(profile):
    if not profile.get("enabled"):
        return
    articles = profile.get("articles", [])
    label = profile.get("global_label", "NO DATA")
    score = profile.get("global_score", 0)
    color = "#047857" if score > 0 else "#b91c1c" if score < 0 else "#64748b"
    top_items = articles[:3]
    headlines = ""
    for article in top_items:
        title = article.get("title", "-")
        source = article.get("source", "News")
        link = article.get("link", "#")
        headlines += (
            f'<a href="{link}" target="_blank" class="news-headline">'
            f'<span>{source}</span>{title}</a>'
        )
    if not headlines:
        headlines = '<div class="learning-note">Belum ada headline terbaru yang terbaca.</div>'
    st.markdown(
        f"""
        <div class="news-panel">
            <div class="section-row">
                <div>
                    <div class="section-label">News sentiment</div>
                    <div class="learning-title">RSS market news check</div>
                </div>
                <div style="color:{color};font-weight:900;text-align:right">{label}<br><span style="font-size:0.78rem">Score {score:+.2f}</span></div>
            </div>
            <div class="news-list">{headlines}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# =============================================================================
# UI COMPONENTS
# =============================================================================
def render_header():
    st.markdown(
        f"""
        <div class="app-shell-header">
            <div class="app-brand-row">
                <div>
                    <div class="app-kicker">Indodax market radar</div>
                    <h1 class="app-title">Rekomendasi Beli Crypto</h1>
                    <p class="app-subtitle">
                        Dashboard real-time untuk membaca momentum, risiko, entry zone, dan target. Informasi ini bukan saran keuangan.
                    </p>
                </div>
                <div class="quick-links">
                    <a class="quick-link primary" href="{INDODAX_REF}" target="_blank">Daftar Indodax</a>
                    <a class="quick-link" href="{TELEGRAM_COMMUNITY}" target="_blank">Telegram Premium</a>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_market_mode_banner(market_stats):
    if not market_stats:
        return
    mode = market_stats["mode"]
    rules = MARKET_MODE_RULES[mode]
    st.markdown(
        f"""
        <div class="mode-banner" style="--mode-color:{rules['color']}">
            <div>
                <div class="section-label">Mode pasar</div>
                <div class="mode-title">{rules['label']}</div>
            </div>
            <div class="mode-desc">{rules['description']}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def fetch_fear_greed():
    """Fetch Fear & Greed Index from alternative.me API."""
    try:
        resp = requests.get("https://api.alternative.me/fng/?limit=1", timeout=5)
        data = resp.json()["data"][0]
        return {"value": int(data["value"]), "label": data["value_classification"]}
    except Exception:
        return None


def render_fear_greed(fg_data):
    """Render Fear & Greed Index gauge widget."""
    if not fg_data:
        return
    val = fg_data["value"]
    label = fg_data["label"]
    if val <= 25:
        color, emoji = "#ef4444", "😱"
    elif val <= 45:
        color, emoji = "#f97316", "😰"
    elif val <= 55:
        color, emoji = "#eab308", "😐"
    elif val <= 75:
        color, emoji = "#22c55e", "😊"
    else:
        color, emoji = "#16a34a", "🤑"
    st.markdown(
        f"""
        <div style="background:#ffffff;border:1px solid #dbe7f3;border-radius:8px;padding:0.9rem 1rem;
                    margin:0.5rem 0;box-shadow:0 10px 26px rgba(15,23,42,0.06)">
            <div style="display:flex;justify-content:space-between;align-items:center;gap:0.8rem">
                <div>
                    <div class="section-label">Fear & Greed Index</div>
                    <div style="color:{color};font-size:1.85rem;font-weight:900;line-height:1">{val}</div>
                </div>
                <div style="color:{color};font-size:0.85rem;font-weight:900;text-transform:uppercase;text-align:right">{label}</div>
            </div>
            <div style="margin-top:0.65rem;background:#e2e8f0;border-radius:999px;height:8px;overflow:hidden">
                <div style="width:{val}%;height:100%;background:linear-gradient(90deg,#ef4444,#f97316,#eab308,#22c55e);border-radius:999px"></div>
            </div>
        </div>""",
        unsafe_allow_html=True,
    )


def render_sidebar(market_stats, fg_data, all_results):
    """Render sidebar with referral CTA, market summary, and bot status."""
    with st.sidebar:
        st.markdown(
            f"""
            <div style="padding:0.8rem 0 0.4rem">
                <div style="color:#0f172a;font-size:1.15rem;font-weight:900">Kripto Mania</div>
                <div style="color:#64748b;font-size:0.78rem;font-weight:700;margin-top:0.15rem">Trading dashboard</div>
            </div>
            <div style="background:#ecfdf5;border:1px solid #bbf7d0;border-radius:8px;padding:0.9rem;margin:0.7rem 0">
                <div style="color:#065f46;font-size:0.95rem;font-weight:900">Mulai trading di Indodax</div>
                <div style="color:#047857;font-size:0.75rem;font-weight:700;margin:0.25rem 0 0.65rem">Gunakan link referral resmi dashboard.</div>
                <a href="{INDODAX_REF}" target="_blank" style="display:inline-flex;align-items:center;justify-content:center;background:#047857;color:white;
                   font-weight:900;padding:0.48rem 0.8rem;border-radius:8px;text-decoration:none;font-size:0.82rem">Daftar sekarang</a>
            </div>
            """,
            unsafe_allow_html=True,
        )
        if fg_data:
            render_fear_greed(fg_data)
        st.markdown("#### Ringkasan Market")
        if market_stats:
            mode_rules = MARKET_MODE_RULES[market_stats['mode']]
            st.markdown(f"**Status:** {mode_rules['label']}")
            st.markdown(f"**Hijau/Merah:** {market_stats['green_count']}/{market_stats['red_count']}")
            st.markdown(f"**Volume:** {format_idr(market_stats['total_vol'])}")
        buy_picks = [r for r in all_results if is_entry_action(r.get("action", ""))][:3]
        if buy_picks:
            st.markdown("#### Top Picks")
            for p in buy_picks:
                st.markdown(f"**{p['symbol']}** · Score {p['score']}/100 · {p['change']:+.1f}%")
        st.markdown("#### Status")
        st.markdown("Telegram Bot: **Aktif**" if BOT_ENABLED else "Telegram Bot: **Nonaktif**")
        if not BOT_ENABLED or not BOT_TOKEN or not BOT_CHAT_ID:
            st.sidebar.warning(
                "⚠️ **Config Telegram Belum Lengkap**\n\n"
                "Telegram Bot tidak aktif di Hugging Face. Hubungkan dengan cara:\n\n"
                "1. Buka tab **Settings** -> **Variables and Secrets** di Space Anda.\n"
                "2. Tambahkan **Secrets**:\n"
                "   • `TELEGRAM_BOT_TOKEN` = `8947452796:AAEyKOPuOa_JmjDfTUTybhz5H3Puec_7yYs`\n"
                "   • `TELEGRAM_CHAT_ID` = `-1003878919874`\n"
                "   • `GEMINI_API_KEY` = (dari secrets.toml Anda)\n"
                "   • `DEEPSEEK_API_KEY` = (dari secrets.toml Anda)\n"
                "3. Tambahkan **Variables**:\n"
                "   • `ENABLE_TELEGRAM_BOT` = `true`\n"
                "   • `TELEGRAM_ALLOWED_USER_ID` = `1206494871`\n\n"
                "Setelah itu Space akan me-restart otomatis dan bot akan mulai menjawab perintah Anda."
            )
        auto_state = "ON (60 detik)" if st.session_state.get("auto_refresh_enabled") else "OFF (manual)"
        st.markdown(f"Auto-refresh: **{auto_state}**")

        st.markdown(
            f"""<a href="{TELEGRAM_COMMUNITY}" target="_blank" style="color:#2563eb;font-weight:900;text-decoration:none">Gabung Telegram Premium</a>""",
            unsafe_allow_html=True,
        )


def render_market_stats(market_stats):
    if not market_stats:
        return
    cols = st.columns(5)
    with cols[0]:
        st.markdown(
            f"""<div class="stat-card"><div class="stat-value" style="color:#22c55e">{market_stats['green_count']}</div>
            <div class="stat-label">Hijau</div></div>""",
            unsafe_allow_html=True,
        )
    with cols[1]:
        st.markdown(
            f"""<div class="stat-card"><div class="stat-value" style="color:#ef4444">{market_stats['red_count']}</div>
            <div class="stat-label">Merah</div></div>""",
            unsafe_allow_html=True,
        )
    with cols[2]:
        color = "#22c55e" if market_stats['green_pct'] >= 50 else "#ef4444"
        st.markdown(
            f"""<div class="stat-card"><div class="stat-value" style="color:{color}">{market_stats['green_pct']}%</div>
            <div class="stat-label">Hijau</div></div>""",
            unsafe_allow_html=True,
        )
    with cols[3]:
        color = "#22c55e" if market_stats['avg_change'] >= 0 else "#ef4444"
        st.markdown(
            f"""<div class="stat-card"><div class="stat-value" style="color:{color}">{market_stats['avg_change']:+.2f}%</div>
            <div class="stat-label">Rata-rata</div></div>""",
            unsafe_allow_html=True,
        )
    with cols[4]:
        st.markdown(
            f"""<div class="stat-card"><div class="stat-value" style="color:#f59e0b">{format_idr(market_stats['total_vol'])}</div>
            <div class="stat-label">Volume</div></div>""",
            unsafe_allow_html=True,
        )


def render_rekomendasi_card(item, idx, key_prefix=""):
    change_sign = "+" if item["change"] >= 0 else ""
    change_color = "#22c55e" if item["change"] >= 0 else "#ef4444"
    pair_upper = item["pair"].upper().replace("_", "")
    buy_link = f"https://indodax.com/market/{pair_upper}?ref={REFERRAL_CODE}"

    def clean_ui_text(value):
        text = str(value or "")
        for token in ("🟢", "🟡", "⚪", "🔴", "⛔", "⬇️", "⬆️", "⚖️", "🚀", "📉", "⏳", "✅", "❌", "🔥"):
            text = text.replace(token, "")
        return " ".join(text.split())

    def visible_price(value):
        try:
            value = float(value)
        except (TypeError, ValueError):
            return "-"
        return format_price(value) if value > 0 else "-"

    action_text = clean_ui_text(item.get("action", ""))
    step2_action = clean_ui_text(item.get("step2_action", "Pantau"))
    is_buy_signal = (
        is_entry_action(item.get("action", "")) and
        item.get("allocation_pct", 0) > 0 and
        item.get("confluence_passed", 0) >= 4 and
        item.get("verdict", "") not in ("TOLAK", "TUNGGU")
    )
    if is_buy_signal:
        cta_text = "Entry Valid" if item.get("confluence_passed", 0) == 5 else "Entry Kecil"
        cta_class = "buy-button-sm"
        signal_class = "signal-buy"
    elif "WATCH" in str(item.get("action", "")):
        cta_text = "Pantau di Indodax"
        cta_class = "buy-button-sm neutral"
        signal_class = "signal-watch"
    else:
        cta_text = "Pantau di Indodax"
        cta_class = "buy-button-sm neutral"
        signal_class = "signal-avoid"

    risk_color = "#b91c1c" if item["risk_level"] == "TINGGI" else "#b45309" if item["risk_level"] == "SEDANG" else "#047857"
    entry_label = clean_ui_text(item.get("entry_zone_label", "Netral"))
    step_action = clean_ui_text(item.get("step1_action", "Pantau"))
    fail_action = clean_ui_text(item.get("fail_action", "Tidak direkomendasikan"))
    confluence_label = item.get("confluence_label", "INVALID 0/5")
    confluence_checks = item.get("confluence_checks", {})
    learning_adjustment = int(item.get("learning_adjustment", 0) or 0)
    learning_note = item.get("learning_note", "Mengumpulkan data")
    learning_trades = int(item.get("learning_trades", 0) or 0)
    learning_color = "#047857" if learning_adjustment > 0 else "#b91c1c" if learning_adjustment < 0 else "#64748b"
    learning_delta = f"{learning_adjustment:+d}" if learning_adjustment else "0"
    mtf_adjustment = int(item.get("mtf_adjustment", 0) or 0)
    mtf_label = item.get("mtf_label", "MIXED")
    mtf_color = "#047857" if mtf_adjustment > 0 else "#b91c1c" if mtf_adjustment < 0 else "#64748b"
    mtf_detail = f"4H {item.get('mtf_4h', 'NO DATA')} · 1D {item.get('mtf_1d', 'NO DATA')}"
    news_adjustment = int(item.get("news_adjustment", 0) or 0)
    news_label = item.get("news_label", "NO DATA")
    news_color = "#047857" if news_adjustment > 0 else "#b91c1c" if news_adjustment < 0 else "#64748b"
    news_delta = f"{news_adjustment:+d}" if news_adjustment else "0"
    news_headline = item.get("news_headline") or "Tidak ada headline spesifik coin"

    # Intelligence layer fields
    intel_adjustment = int(item.get("intel_adjustment", 0) or 0)
    intel_confidence = item.get("intel_confidence", "LEMAH")
    intel_color = "#047857" if intel_adjustment > 0 else "#b91c1c" if intel_adjustment < 0 else "#64748b"
    intel_delta = f"{intel_adjustment:+d}" if intel_adjustment else "0"
    intel_notes = item.get("intel_notes", []) or []
    intel_notes_text = " · ".join(intel_notes) if intel_notes else "Belum ada catatan kuat"
    divergence_label = item.get("divergence", "NONE")
    divergence_color = "#047857" if divergence_label == "BULLISH" else "#b91c1c" if divergence_label == "BEARISH" else "#64748b"
    candle_pattern = clean_ui_text(item.get("candle_pattern", "NONE"))
    candle_bias = item.get("candle_bias", "neutral")
    candle_color = "#047857" if candle_bias == "bullish" else "#b91c1c" if candle_bias == "bearish" else "#64748b"
    regime_label = item.get("regime", "MIXED")
    regime_color = "#047857" if "TRENDING" in regime_label else "#b45309" if regime_label == "RANGING" else "#64748b"
    vwap_bias = item.get("vwap_bias", "neutral")
    vwap_dist = float(item.get("vwap_distance_pct", 0) or 0)
    vwap_label = f"{vwap_bias.upper()} {vwap_dist:+.1f}%" if vwap_bias != "neutral" else "DI VWAP"
    vwap_color = "#b45309" if vwap_bias == "above" else "#047857" if vwap_bias == "below" else "#64748b"
    fib_zone = item.get("fib_zone", "NO DATA")
    fib_color = "#047857" if "GOLDEN" in str(fib_zone) or "DEEP" in str(fib_zone) else "#b91c1c" if "DI HIGH" in str(fib_zone) else "#64748b"
    kelly_pct = item.get("kelly_pct")
    kelly_label = item.get("kelly_label", "BUTUH DATA")
    if kelly_pct is not None:
        kelly_value = f"{kelly_pct:.1f}%"
    else:
        kelly_value = "—"
    kelly_color = "#047857" if (kelly_pct or 0) >= 3 else "#b45309" if (kelly_pct or 0) >= 1 else "#64748b"

    # Advanced algorithms fields
    adv_adjustment = int(item.get("advanced_adjustment", 0) or 0)
    adv_notes = item.get("advanced_notes", []) or []
    adv_notes_text = " · ".join(adv_notes) if adv_notes else "Tidak ada sinyal advanced"
    adv_color = "#047857" if adv_adjustment > 0 else "#b91c1c" if adv_adjustment < 0 else "#64748b"
    combined_adj = int(item.get("combined_adjustment", 0) or 0)
    combined_notes = item.get("combined_notes", []) or []
    combined_text = " · ".join(combined_notes[:4]) if combined_notes else "Belum ada catatan"
    combined_color = "#047857" if combined_adj > 0 else "#b91c1c" if combined_adj < 0 else "#64748b"
    ichimoku_sig = item.get("ichimoku_signal", "NO DATA")
    ichimoku_color = "#047857" if "BULL" in str(ichimoku_sig) else "#b91c1c" if "BEAR" in str(ichimoku_sig) else "#64748b"
    squeeze_sig = item.get("squeeze", "NO DATA")
    squeeze_color = "#047857" if "RELEASED" in str(squeeze_sig) else "#b45309" if "SQUEEZED" in str(squeeze_sig) else "#64748b"
    mfi_val = item.get("mfi", 50.0)
    mfi_sig = item.get("mfi_signal", "NEUTRAL")
    mfi_color = "#047857" if mfi_sig in ("OVERSOLD", "STRONG") else "#b91c1c" if mfi_sig == "OVERBOUGHT" else "#64748b"
    stoch_rsi_sig = item.get("stoch_rsi_signal", "NEUTRAL")
    stoch_rsi_color = "#047857" if "BULL" in str(stoch_rsi_sig) else "#b91c1c" if "BEAR" in str(stoch_rsi_sig) else "#64748b"
    cci_sig = item.get("cci_signal", "NEUTRAL")
    cci_color = "#047857" if "BULL" in str(cci_sig) else "#b91c1c" if "BEAR" in str(cci_sig) else "#64748b"
    breakout_sig = item.get("breakout", "NONE")
    breakout_color = "#047857" if "UP" in str(breakout_sig) else "#b91c1c" if "DOWN" in str(breakout_sig) else "#64748b"
    trend_str = item.get("trend_strength", 0)
    trend_dir = item.get("trend_direction", "NEUTRAL")
    trend_qual = item.get("trend_quality", "LOW")
    trend_color = "#047857" if trend_dir == "BULLISH" else "#b91c1c" if trend_dir == "BEARISH" else "#64748b"
    wyckoff_phase = item.get("wyckoff_phase", "UNKNOWN")
    wyckoff_color = "#047857" if "ACCUM" in str(wyckoff_phase) else "#b91c1c" if "DISTRIB" in str(wyckoff_phase) else "#64748b"
    vp_shape = item.get("vp_shape", "UNKNOWN")
    vp_color = "#047857" if "BULL" in str(vp_shape) else "#b91c1c" if "BEAR" in str(vp_shape) else "#64748b"
    sr_nearest = item.get("sr_nearest", None)
    sr_color = "#047857" if sr_nearest and "DEMAND" in str(sr_nearest) else "#b91c1c" if sr_nearest and "SUPPLY" in str(sr_nearest) else "#64748b"
    mean_rev_sig = item.get("mean_reversion_signal", "NEUTRAL")
    mean_rev_color = "#047857" if "UP" in str(mean_rev_sig) else "#b91c1c" if "DOWN" in str(mean_rev_sig) else "#64748b"
    money_flow_sig = item.get("money_flow_signal", "NEUTRAL")
    money_flow_color = "#047857" if "BUY" in str(money_flow_sig) else "#b91c1c" if "SELL" in str(money_flow_sig) else "#64748b"
    order_flow_net = item.get("order_flow_net", 0)
    order_flow_color = "#047857" if float(order_flow_net) > 10 else "#b91c1c" if float(order_flow_net) < -10 else "#64748b"
    fib_zone_ext = item.get("fib_extension_zone", "NO DATA")
    fib_ext_color = "#047857" if "WITHIN" in str(fib_zone_ext) else "#b91c1c" if "BELOW" in str(fib_zone_ext) else "#64748b"
    vol_regime = item.get("vol_regime", "MEDIUM")
    vol_regime_color = "#047857" if "HIGH" in str(vol_regime) else "#b91c1c" if "EXTREME" in str(vol_regime) else "#64748b"
    price_action = item.get("price_action_pattern", "NONE")
    price_action_color = "#047857" if "CONSOLIDATION" in str(price_action) else "#b45309" if "EXPANSION" in str(price_action) else "#64748b"

    check_rows = ""

    for label, ok in confluence_checks.items():
        row_class = "check-ok" if ok else "check-no"
        status = "Valid" if ok else "Belum"
        check_rows += (
            f'<div class="check-row {row_class}">'
            f'<span>{label}</span><span>{status}</span>'
            f'</div>'
        )

    # Komite agen: lapisan penjelas transparan (tidak mengubah keputusan).
    committee = build_committee(item)
    _vote_color = {"BULLISH": "#047857", "BEARISH": "#b91c1c", "NETRAL": "#64748b"}
    _vote_icon = {"BULLISH": "▲", "BEARISH": "▼", "NETRAL": "•"}
    committee_rows = ""
    for ag in committee["agents"]:
        c = _vote_color.get(ag["vote"], "#64748b")
        ic = _vote_icon.get(ag["vote"], "•")
        committee_rows += (
            f'<div class="check-row" style="display:block">'
            f'<div style="display:flex;justify-content:space-between;align-items:center">'
            f'<span>{ag["name"]}</span>'
            f'<span style="color:{c};font-weight:900">{ic} {ag["vote"]}</span></div>'
            f'<div style="color:#64748b;font-weight:600;font-size:0.68rem;margin-top:0.15rem">{ag["reason"]}</div>'
            f'</div>'
        )
    _cons = committee["consensus"]
    committee_color = "#047857" if _cons == "SETUJU NAIK" else "#b91c1c" if _cons == "SETUJU TURUN" else "#b45309"
    committee_meta = (
        f"{committee['bull_votes']} naik · {committee['bear_votes']} turun · "
        f"{committee['neutral_votes']} netral"
    )

    st.markdown(
        dedent(f"""
        <div class="rekomendasi-card" style="margin-bottom:0.8rem">
            <div class="coin-card-head">
                <div class="coin-left">
                    <div class="coin-avatar">{item['symbol'][:3]}</div>
                    <div>
                        <div class="coin-symbol">{item['symbol']}</div>
                        <div class="coin-category">{item['category']} · {pair_upper}</div>
                        <span class="signal-pill {signal_class}">{action_text}</span>
                    </div>
                </div>
                <div class="coin-price-wrap">
                    <span class="price-tag">{format_price(item['price'])}</span>
                    <span class="{'profit-badge' if item['change'] >= 0 else 'loss-badge'}">{change_sign}{item['change']:.2f}%</span>
                </div>
            </div>

            <div class="metrics-grid">
                <div class="metric-chip"><span class="metric-label">Score</span><span class="metric-value" style="color:#047857">{item['score']}/100</span></div>
                <div class="metric-chip"><span class="metric-label">Risk</span><span class="metric-value" style="color:{risk_color}">{item['risk_level']}</span></div>
                <div class="metric-chip"><span class="metric-label">Alokasi</span><span class="metric-value" style="color:#b45309">{item['allocation_pct']:.1f}%</span></div>
                <div class="metric-chip"><span class="metric-label">Volume</span><span class="metric-value">{format_idr(item['vol_idr'])}</span></div>
                <div class="metric-chip"><span class="metric-label">RSI</span><span class="metric-value">{item['rsi']}</span></div>
                <div class="metric-chip"><span class="metric-label">ML</span><span class="metric-value">{item['ml_label']} {item['ml_prob']}%</span></div>
                <div class="metric-chip"><span class="metric-label">MTF</span><span class="metric-value" style="color:{mtf_color}">{mtf_label}</span></div>
                <div class="metric-chip"><span class="metric-label">News</span><span class="metric-value" style="color:{news_color}">{news_label} {news_delta}</span></div>
                <div class="metric-chip"><span class="metric-label">Learning</span><span class="metric-value" style="color:{learning_color}">{learning_delta} · {learning_trades}x</span></div>
            </div>

            <div class="metrics-grid">
                <div class="metric-chip"><span class="metric-label">TP1</span><span class="metric-value" style="color:#047857">{format_price(item['tp1'])}</span></div>
                <div class="metric-chip"><span class="metric-label">TP2</span><span class="metric-value" style="color:#047857">{format_price(item['tp2'])}</span></div>
                <div class="metric-chip"><span class="metric-label">Target</span><span class="metric-value" style="color:#047857">{format_price(item['target'])}</span></div>
                <div class="metric-chip"><span class="metric-label">Stop Loss</span><span class="metric-value" style="color:#b91c1c">{format_price(item['stop_loss'])}</span></div>
            </div>

            <div class="metrics-grid">
                <div class="metric-chip"><span class="metric-label">Smart adj</span><span class="metric-value" style="color:{intel_color}">{intel_delta} · {intel_confidence}</span></div>
                <div class="metric-chip"><span class="metric-label">Divergence</span><span class="metric-value" style="color:{divergence_color}">{divergence_label}</span></div>
                <div class="metric-chip"><span class="metric-label">Candle</span><span class="metric-value" style="color:{candle_color}">{candle_pattern or 'NONE'}</span></div>
                <div class="metric-chip"><span class="metric-label">Regime</span><span class="metric-value" style="color:{regime_color}">{regime_label}</span></div>
                <div class="metric-chip"><span class="metric-label">VWAP</span><span class="metric-value" style="color:{vwap_color}">{vwap_label}</span></div>
                <div class="metric-chip"><span class="metric-label">Fib zone</span><span class="metric-value" style="color:{fib_color}">{fib_zone}</span></div>
                <div class="metric-chip"><span class="metric-label">Kelly</span><span class="metric-value" style="color:{kelly_color}">{kelly_value} · {kelly_label}</span></div>
            </div>

            <div class="metrics-grid">
                <div class="metric-chip"><span class="metric-label">Combined adj</span><span class="metric-value" style="color:{combined_color}">{combined_adj:+d}</span></div>
                <div class="metric-chip"><span class="metric-label">Ichimoku</span><span class="metric-value" style="color:{ichimoku_color}">{ichimoku_sig}</span></div>
                <div class="metric-chip"><span class="metric-label">Squeeze</span><span class="metric-value" style="color:{squeeze_color}">{squeeze_sig}</span></div>
                <div class="metric-chip"><span class="metric-label">MFI</span><span class="metric-value" style="color:{mfi_color}">{mfi_val:.0f} {mfi_sig}</span></div>
                <div class="metric-chip"><span class="metric-label">StochRSI</span><span class="metric-value" style="color:{stoch_rsi_color}">{stoch_rsi_sig}</span></div>
                <div class="metric-chip"><span class="metric-label">CCI</span><span class="metric-value" style="color:{cci_color}">{cci_sig}</span></div>
                <div class="metric-chip"><span class="metric-label">Breakout</span><span class="metric-value" style="color:{breakout_color}">{breakout_sig}</span></div>
                <div class="metric-chip"><span class="metric-label">Trend</span><span class="metric-value" style="color:{trend_color}">{trend_dir} {trend_qual}</span></div>
            </div>

            <div class="metrics-grid">
                <div class="metric-chip"><span class="metric-label">Wyckoff</span><span class="metric-value" style="color:{wyckoff_color}">{wyckoff_phase}</span></div>
                <div class="metric-chip"><span class="metric-label">VP Shape</span><span class="metric-value" style="color:{vp_color}">{vp_shape}</span></div>
                <div class="metric-chip"><span class="metric-label">S/R Zone</span><span class="metric-value" style="color:{sr_color}">{sr_nearest or 'NONE'}</span></div>
                <div class="metric-chip"><span class="metric-label">Mean Rev</span><span class="metric-value" style="color:{mean_rev_color}">{mean_rev_sig}</span></div>
                <div class="metric-chip"><span class="metric-label">Money Flow</span><span class="metric-value" style="color:{money_flow_color}">{money_flow_sig}</span></div>
                <div class="metric-chip"><span class="metric-label">Order Flow</span><span class="metric-value" style="color:{order_flow_color}">{order_flow_net:+.0f}%</span></div>
                <div class="metric-chip"><span class="metric-label">Fib Ext</span><span class="metric-value" style="color:{fib_ext_color}">{fib_zone_ext}</span></div>
                <div class="metric-chip"><span class="metric-label">Vol Regime</span><span class="metric-value" style="color:{vol_regime_color}">{vol_regime}</span></div>
            </div>

            <div class="card-section">
                <div class="section-row">
                    <span class="section-label">Advanced insight</span>
                    <span class="section-strong" style="color:{adv_color}">Advanced adj {adv_adjustment:+d}</span>
                </div>
                <div class="section-row" style="margin-top:0.35rem">
                    <span class="section-label">Catatan advanced</span>
                    <span class="section-strong" style="color:#334155;text-align:right;flex:1">{adv_notes_text}</span>
                </div>
            </div>

            <div class="card-section" style="background:linear-gradient(180deg, #f0fdf4, #dcfce7);border-color:#86efac">
                <div class="section-row">
                    <span class="section-label" style="color:#166534">🧮 Combined Score</span>
                    <span class="section-strong" style="color:{combined_color};font-size:1.1rem">{combined_adj:+d}</span>
                </div>
                <div class="section-row" style="margin-top:0.35rem">
                    <span class="section-label">Catatan gabungan</span>
                    <span class="section-strong" style="color:#334155;text-align:right;flex:1">{combined_text}</span>
                </div>
            </div>

            <div class="card-section">
                <div class="section-row">
                    <span class="section-label">Smart insight</span>
                    <span class="section-strong" style="color:{intel_color}">Confidence {intel_confidence}</span>
                </div>
                <div class="section-row" style="margin-top:0.35rem">
                    <span class="section-label">Catatan</span>
                    <span class="section-strong" style="color:#334155;text-align:right;flex:1">{intel_notes_text}</span>
                </div>
            </div>

            <div class="card-section">
                <div class="section-row">
                    <span class="section-label">Entry zone</span>
                    <span class="section-strong">{entry_label}</span>
                </div>
                <div class="section-row" style="margin-top:0.35rem">
                    <span style="color:#047857;font-weight:800">{format_price(item.get('entry_zone_low', 0))}</span>
                    <span style="color:#64748b;font-weight:800">sampai</span>
                    <span style="color:#b91c1c;font-weight:800">{format_price(item.get('entry_zone_high', 0))}</span>
                </div>
            </div>

            <div class="card-section" style="background:linear-gradient(180deg, #f0f9ff, #e0f2fe);border-color:#7dd3fc">
                <div class="section-row">
                    <span class="section-label" style="color:#0369a1">🔮 Ramalan 2 Langkah ke Depan (probabilistik)</span>
                    <span class="section-strong" style="color:#0c4a6e;font-size:0.72rem">KNN dari pola historis</span>
                </div>
                <div class="scenario-grid">
                    <div class="scenario-box" style="background:#ffffff;border-color:#7dd3fc">
                        <div class="scenario-title" style="color:#0369a1">Step 1 · {item.get('forecast_step1_horizon', '6 jam')}</div>
                        <div style="font-size:1.45rem;font-weight:900;color:{'#047857' if item.get('forecast_step1_prob', 50) >= 55 else '#b91c1c' if item.get('forecast_step1_prob', 50) <= 45 else '#0369a1'};margin-top:0.3rem">{item.get('forecast_step1_prob', 50):.0f}%</div>
                        <div style="font-size:0.7rem;color:#64748b;font-weight:800">probabilitas naik &gt;1%</div>
                        <div style="margin-top:0.45rem;font-size:0.78rem;color:#334155;font-weight:700">
                            Range: <span style="color:#b91c1c">{format_price(item.get('forecast_step1_low', 0))}</span> – <span style="color:#047857">{format_price(item.get('forecast_step1_high', 0))}</span>
                        </div>
                        <div style="font-size:0.7rem;color:#64748b;margin-top:0.15rem;font-weight:800">Median {item.get('forecast_step1_median_pct', 0):+.2f}% · Conf {item.get('forecast_step1_conf', 'rendah')}</div>
                    </div>
                    <div class="scenario-box" style="background:#ffffff;border-color:#0ea5e9">
                        <div class="scenario-title" style="color:#0369a1">Step 2 · {item.get('forecast_step2_horizon', '24 jam')}</div>
                        <div style="font-size:1.45rem;font-weight:900;color:{'#047857' if item.get('forecast_step2_prob', 50) >= 55 else '#b91c1c' if item.get('forecast_step2_prob', 50) <= 45 else '#0369a1'};margin-top:0.3rem">{item.get('forecast_step2_prob', 50):.0f}%</div>
                        <div style="font-size:0.7rem;color:#64748b;font-weight:800">probabilitas naik &gt;2%</div>
                        <div style="margin-top:0.45rem;font-size:0.78rem;color:#334155;font-weight:700">
                            Range: <span style="color:#b91c1c">{format_price(item.get('forecast_step2_low', 0))}</span> – <span style="color:#047857">{format_price(item.get('forecast_step2_high', 0))}</span>
                        </div>
                        <div style="font-size:0.7rem;color:#64748b;margin-top:0.15rem;font-weight:800">Median {item.get('forecast_step2_median_pct', 0):+.2f}% · Conf {item.get('forecast_step2_conf', 'rendah')}</div>
                    </div>
                </div>
            </div>

            <div class="scenario-grid scenario-grid-3">
                <div class="scenario-box" style="background:#ecfdf5;border-color:#bbf7d0">
                    <div class="scenario-title" style="color:#047857">Step 1 · Target swing R1</div>
                    <div class="scenario-action">{step_action}</div>
                    <div class="scenario-price" style="color:#047857">{visible_price(item.get('step1_price', 0))}</div>
                    <div style="font-size:0.7rem;color:#64748b;margin-top:0.18rem;font-weight:800">{item.get('step1_gain', 0):+.2f}%</div>
                </div>
                <div class="scenario-box" style="background:#dcfce7;border-color:#86efac">
                    <div class="scenario-title" style="color:#047857">Step 2 · Target swing R2</div>
                    <div class="scenario-action">{step2_action}</div>
                    <div class="scenario-price" style="color:#047857">{visible_price(item.get('step2_price', 0))}</div>
                    <div style="font-size:0.7rem;color:#64748b;margin-top:0.18rem;font-weight:800">{item.get('step2_gain', 0):+.2f}%</div>
                </div>
                <div class="scenario-box" style="background:#fef2f2;border-color:#fecaca">
                    <div class="scenario-title" style="color:#b91c1c">Skenario gagal</div>
                    <div class="scenario-action">{fail_action}</div>
                    <div class="scenario-price" style="color:#b91c1c">{visible_price(item.get('fail_price', 0))}</div>
                    <div style="font-size:0.7rem;color:#64748b;margin-top:0.18rem;font-weight:800">-{item.get('fail_loss', 0):.2f}%</div>
                </div>
            </div>

            <div class="card-section">
                <div class="section-row">
                    <span class="section-label">🧑‍⚖️ Komite agen (penjelas keputusan)</span>
                    <span class="section-strong" style="color:{committee_color}">{_cons} · {committee_meta}</span>
                </div>
                <div class="check-list" style="margin-top:0.5rem">{committee_rows}</div>
                <div style="color:#94a3b8;font-size:0.66rem;font-weight:700;margin-top:0.4rem">
                    Suara agen ini menjelaskan alasan, bukan menggantikan keputusan akhir (action di atas).
                </div>
            </div>

            <div class="card-section">
                <div class="section-row">
                    <span class="section-label">Confluence gate</span>
                    <span class="section-strong">{confluence_label}</span>
                </div>
                <div class="check-list">{check_rows}</div>
            </div>

            <div class="card-section">
                <div class="section-row">
                    <span class="section-label">Learning note</span>
                    <span class="section-strong" style="color:{learning_color}">{learning_note}</span>
                </div>
                <div class="section-row" style="margin-top:0.35rem">
                    <span class="section-label">Multi-timeframe</span>
                    <span class="section-strong" style="color:{mtf_color}">{mtf_detail}</span>
                </div>
                <div class="section-row" style="margin-top:0.35rem">
                    <span class="section-label">News check</span>
                    <span class="section-strong" style="color:{news_color}">{news_headline}</span>
                </div>
            </div>

            <div style="margin-top:0.8rem;text-align:right">
                <a href="{buy_link}" target="_blank" class="{cta_class}">{cta_text}</a>
            </div>
        </div>
        """).strip().replace("\n", ""),
        unsafe_allow_html=True,
    )
    
    # AI Insight Button underneath the card
    btn_key = f"insight_btn_{key_prefix}_{item['symbol']}_{idx}_{id(item)}"
    if st.button(f"🧠 Minta AI Insight untuk {item['symbol']}", key=btn_key, use_container_width=True):
        with st.spinner(f"Menghubungi AI untuk {item['symbol']}..."):
            gemini_key = get_secret("GEMINI_API_KEY", "")
            deepseek_key = get_secret("DEEPSEEK_API_KEY", "")
            if not gemini_key and not deepseek_key:
                st.error("API Key Gemini atau Deepseek belum dikonfigurasi di secrets.toml")
            else:
                try:
                    insight_res = ai_pilot.generate_signal_insight(item, gemini_key, deepseek_key)
                    insight_text = insight_res.get("insight", "AI gagal memberikan insight.")
                    st.info(insight_text)
                except Exception as e:
                    st.error(f"Gagal menghubungi AI: {e}")


def render_rekomendasi_list(results, title, max_items=10):
    buy_results = [r for r in results if is_entry_action(r.get("action", ""))]
    watch_results = [r for r in results if "WATCH" in r["action"]]
    st.markdown(
        f"""<div class="rekomendasi-hero">
            <h2 class="hero-title">{title}</h2>
            <p class="hero-meta">{len(buy_results)} rekomendasi beli · {len(watch_results)} pantauan</p>
        </div>""",
        unsafe_allow_html=True,
    )
    if not results:
        st.info("Belum ada data untuk ditampilkan.")
        return
    for i, item in enumerate(results[:max_items]):
        render_rekomendasi_card(item, i, key_prefix=title)


def render_fomo_alerts(tickers, prices_24h, market_stats, news_profile, learning_profile):
    fomo_gila, fomo, pumping = _bot_detect_fomo(tickers, prices_24h)
    if not fomo_gila and not fomo and not pumping:
        return
        
    st.markdown("## 🚨 FOMO Alert")
    
    # Inisialisasi session state jika belum ada
    if "fomo_analyzed_symbol" not in st.session_state:
        st.session_state["fomo_analyzed_symbol"] = None
        st.session_state["fomo_analyzed_coin_data"] = None
        
    def _render_section(coin_list, title, color):
        if not coin_list:
            return
        st.markdown(f"### {title}")
        cols = st.columns(min(len(coin_list), 4))
        for i, coin in enumerate(coin_list[:4]):
            with cols[i]:
                pair_upper = coin["pair"].upper().replace("_", "")
                link = f"https://indodax.com/market/{pair_upper}?ref={REFERRAL_CODE}"
                st.markdown(
                    f"""<div class="fomo-card" style="border-color:{color};background:{color}10;margin-bottom:0.5rem;padding:0.75rem;border-radius:10px;border:1px solid">
                        <div style="font-size:1.4rem;font-weight:900;color:{color}">+{coin['change']}%</div>
                        <div style="font-weight:800;font-size:1.05rem">{coin['symbol']}</div>
                        <div style="font-size:0.8rem;color:#888">{format_price(coin['price'])}</div>
                        <div style="font-size:0.7rem;color:#666;margin-bottom:0.4rem">Vol: {format_idr(coin['vol_idr'])}</div>
                    </div>""",
                    unsafe_allow_html=True,
                )
                
                # Sisi tombol streamlit
                btn_cols = st.columns(2)
                with btn_cols[0]:
                    st.link_button("🌐 Pantau", link, use_container_width=True)
                with btn_cols[1]:
                    if st.button("🔍 Analisis", key=f"fomo_btn_{coin['symbol']}", use_container_width=True):
                        st.session_state["fomo_analyzed_symbol"] = coin["symbol"]
                        st.session_state["fomo_analyzed_coin_data"] = coin

    _render_section(fomo_gila, "🚀 FOMO Gila (>15%)", "#ef4444")
    _render_section(fomo, "🔥 FOMO (>8%)", "#f59e0b")
    _render_section(pumping, "📈 PUMPING (>5%)", "#10b981")
    
    # Tampilkan kartu analisis instan jika dipilih
    analyzed_sym = st.session_state.get("fomo_analyzed_symbol")
    if analyzed_sym:
        st.markdown(f"### 🧠 Analisis Instan Koin Pump: {analyzed_sym}")
        coin = st.session_state.get("fomo_analyzed_coin_data")
        if coin:
            with st.spinner(f"Sedang menarik candle dan menganalisis {analyzed_sym}..."):
                candles = fetch_candles(coin["pair"])
                if not candles.empty:
                    data = {
                        "symbol": analyzed_sym,
                        "pair": coin["pair"],
                        "price": coin["price"],
                        "high": coin["price"],  # default fallback
                        "low": coin["price"],   # default fallback
                        "vol_idr": coin["vol_idr"],
                        "change": coin["change"]
                    }
                    # Ambil high/low 24h riil jika tersedia
                    raw_info = tickers.get(coin["pair"], {})
                    data["high"] = float(raw_info.get("high", coin["price"]))
                    data["low"] = float(raw_info.get("low", coin["price"]))
                    
                    res = analyze_coin_advanced(analyzed_sym, data, candles, market_stats)
                    # Apply news and learning
                    adj_results = apply_news_adjustments([res], news_profile)
                    adj_results = apply_learning_adjustments(adj_results, learning_profile)
                    
                    render_rekomendasi_card(adj_results[0], 999)
                else:
                    st.error(f"Gagal memuat candle untuk {analyzed_sym}. Silakan coba lagi.")


# =============================================================================
# AI AUTO-PILOT UI
# =============================================================================
def render_pilot_tab(market_stats, all_results, news_profile, learning_profile, tickers, prices_24h):
    """Tab AI Auto-Pilot: playbook harian dari AI berdasarkan semua data engine."""
    st.markdown("## 🤖 AI Auto-Pilot — Playbook Hari Ini")
    st.markdown(
        "AI baca semua data web (sinyal, ramalan probabilistik, portofolio, news, market mode), "
        "lalu kasih perintah ringkas yang tinggal kamu eksekusi manual. AI **tidak** trade otomatis."
    )

    gemini_key = get_secret("GEMINI_API_KEY", "")
    deepseek_key = get_secret("DEEPSEEK_API_KEY", "")
    if not gemini_key and not deepseek_key:
        st.warning(
            "⚠️ AI Auto-Pilot butuh API key. Pasang `GEMINI_API_KEY` atau `DEEPSEEK_API_KEY` di secrets."
        )
        return

    buy_picks = [r for r in all_results if is_entry_action(r.get("action", ""))][:5]
    portfolio_positions = journal_store.list_positions(status="OPEN") if journal_store.get_backend() == "sqlite" else []
    capital_idr = float(journal_store.get_setting("capital_idr", "0") or 0) if journal_store.get_backend() == "sqlite" else 0

    # Cache di session state — playbook tidak regen tiap auto-refresh, hemat quota
    if "pilot_cache" not in st.session_state:
        st.session_state["pilot_cache"] = {"signature": None, "playbook": None, "generated_at": 0}

    ctx = ai_pilot.build_pilot_context(
        market_stats, buy_picks, portfolio_positions, capital_idr,
        news_profile, learning_profile, tickers,
    )
    sig = ai_pilot._hash_context(ctx)

    cache = st.session_state["pilot_cache"]
    age_min = (time.time() - cache.get("generated_at", 0)) / 60
    cached_text = cache.get("playbook") or ""
    # Anggap cache invalid kalau isinya error message (italic markdown atau kata kunci error)
    is_error_cache = (
        cached_text.startswith("_")
        or "Gagal hubungi" in cached_text
        or "RateLimitError" in cached_text
        or "quota" in cached_text.lower()[:200]
    )
    cache_valid = (
        cache.get("signature") == sig
        and cached_text
        and not is_error_cache
        and age_min < 5  # max 5 menit
    )

    btn_cols = st.columns([1, 1, 4])
    with btn_cols[0]:
        regen = st.button("🔄 Regen", use_container_width=True, type="primary",
                          help="Force regenerate playbook (pakai quota AI)")
    with btn_cols[1]:
        if cache_valid:
            st.markdown(
                f"<div style='padding-top:6px;color:#64748b;font-size:0.8rem;font-weight:700'>"
                f"Cached {age_min:.1f} menit lalu</div>",
                unsafe_allow_html=True,
            )

    if regen or not cache_valid:
        with st.spinner("AI sedang menyusun playbook hari ini..."):
            result = ai_pilot.generate_playbook(
                market_stats, buy_picks, portfolio_positions, capital_idr,
                news_profile, learning_profile, tickers,
                gemini_key=gemini_key, deepseek_key=deepseek_key,
            )
            st.session_state["pilot_cache"] = {
                "signature": result["signature"],
                "playbook": result["playbook"],
                "generated_at": result["generated_at"],
                "context_summary": result.get("context_summary", {}),
            }

    cache = st.session_state["pilot_cache"]
    playbook = cache.get("playbook") or "_Playbook belum tersedia. Klik Regen._"
    summary = cache.get("context_summary", {})

    # Render playbook: pakai container streamlit dengan border supaya markdown beneran ke-render
    with st.container(border=True):
        st.markdown(playbook)

    # Footer dengan context summary
    st.caption(
        f"Konteks: {summary.get('n_picks', 0)} top picks · "
        f"{summary.get('n_positions', 0)} posisi portfolio · "
        f"market mode: {summary.get('market_mode', 'normal')}"
    )


# =============================================================================
# PORTFOLIO TRACKER UI
# =============================================================================
def render_portfolio_tab(tickers, all_results):
    """Tab Portfolio: input modal, posisi terbuka, P/L live, exposure breakdown."""
    st.markdown("## Portofolio Saya")
    st.markdown(
        "Input modal & posisi yang sudah Anda beli untuk lihat P/L real-time, "
        "exposure per kategori, dan peringatan konsentrasi. Data tersimpan lokal di SQLite."
    )

    backend = journal_store.get_backend()
    if backend != "sqlite":
        st.warning(
            "Portfolio tracker butuh backend SQLite. Saat ini fallback JSON aktif "
            "(filesystem read-only). Fitur ini disable di environment ini."
        )
        return

    # --- CAPITAL SETTINGS ---
    saved_capital = float(journal_store.get_setting("capital_idr", "0") or 0)
    cap_cols = st.columns([2, 1])
    with cap_cols[0]:
        capital = st.number_input(
            "Modal total (IDR)",
            min_value=0.0,
            value=saved_capital,
            step=100_000.0,
            format="%.0f",
            help="Total modal yang Anda alokasikan untuk crypto. Dipakai untuk hitung exposure %.",
        )
    with cap_cols[1]:
        st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
        if st.button("Simpan modal", use_container_width=True, key="btn_save_capital"):
            journal_store.set_setting("capital_idr", str(capital))
            st.success("Modal tersimpan")
            st.rerun()

    # --- ADD POSITION FORM ---
    st.markdown("### Tambah Posisi Baru")
    idr_pairs = sorted([p.replace("_idr", "").upper() for p in tickers.keys() if p.endswith("_idr")])
    if not idr_pairs:
        st.info("Daftar koin belum siap. Refresh halaman.")
        return
    add_cols = st.columns([1.2, 1, 1, 1.6, 0.8])
    with add_cols[0]:
        new_sym = st.selectbox("Koin", idr_pairs, key="new_pos_sym",
                               index=idr_pairs.index("BTC") if "BTC" in idr_pairs else 0)
    with add_cols[1]:
        new_qty = st.number_input("Qty (jumlah koin)", min_value=0.0, value=0.0,
                                  step=0.0001, format="%.8f", key="new_pos_qty")
    with add_cols[2]:
        # Pre-fill avg buy dari harga sekarang sebagai reference
        cur_pair = f"{new_sym.lower()}_idr"
        cur_price = float(tickers.get(cur_pair, {}).get("last", 0) or 0)
        new_avg = st.number_input(
            "Harga rata-rata beli (IDR)",
            min_value=0.0, value=cur_price, step=1.0, format="%.2f",
            key="new_pos_avg",
            help=f"Harga sekarang: {format_price(cur_price)}",
        )
    with add_cols[3]:
        new_notes = st.text_input("Catatan (opsional)", key="new_pos_notes",
                                  placeholder="mis. DCA round 1, swing trade")
    with add_cols[4]:
        st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
        if st.button("Tambah", use_container_width=True, type="primary", key="btn_add_pos"):
            if new_qty <= 0 or new_avg <= 0:
                st.error("Qty dan harga rata-rata harus > 0")
            else:
                pos_id = journal_store.add_position(
                    symbol=new_sym, pair=cur_pair, qty=new_qty,
                    avg_buy_price=new_avg, notes=new_notes,
                )
                if pos_id:
                    st.success(f"Posisi {new_sym} ditambahkan (id #{pos_id})")
                    st.rerun()
                else:
                    st.error("Gagal menyimpan posisi")

    # --- 1-CLICK IMPORT FROM REKOMENDASI ---
    buy_picks = [r for r in all_results if is_entry_action(r.get("action", ""))][:5]
    if buy_picks:
        with st.expander(f"🎯 Quick-add dari rekomendasi beli teratas ({len(buy_picks)})", expanded=False):
            st.caption("Klik untuk salin harga sekarang ke form atas. Qty masih perlu kamu isi manual.")
            qa_cols = st.columns(min(len(buy_picks), 5))
            for i, pick in enumerate(buy_picks):
                with qa_cols[i]:
                    if st.button(
                        f"{pick['symbol']}\n{format_price(pick['price'])}",
                        key=f"qa_pick_{pick['symbol']}",
                        use_container_width=True,
                    ):
                        # Streamlit tidak punya "fill form" langsung — tampilkan instruksi
                        st.session_state["new_pos_sym"] = pick["symbol"]
                        st.rerun()

    # --- POSITIONS TABLE ---
    st.markdown("### Posisi Aktif")
    positions = journal_store.list_positions(status="OPEN")
    if not positions:
        st.info("Belum ada posisi terbuka. Tambahkan posisi pertama di form atas.")
    else:
        total_value = 0.0
        total_cost = 0.0
        rows_data = []
        for pos in positions:
            pair = pos.get("pair") or f"{pos['symbol'].lower()}_idr"
            cur_price = float(tickers.get(pair, {}).get("last", 0) or 0)
            qty = float(pos["qty"])
            avg_buy = float(pos["avg_buy_price"])
            cost = qty * avg_buy
            value_now = qty * cur_price
            pnl = value_now - cost
            pnl_pct = (pnl / cost * 100) if cost > 0 else 0
            total_cost += cost
            total_value += value_now
            rec = next((r for r in all_results if r["symbol"] == pos["symbol"]), None)
            current_action = rec["action"] if rec else "—"
            current_score = rec["score"] if rec else None
            cat = COIN_CATEGORIES.get(pos["symbol"], "Lainnya")
            rows_data.append({
                "id": pos["id"],
                "symbol": pos["symbol"],
                "category": cat,
                "qty": qty,
                "avg_buy": avg_buy,
                "cur_price": cur_price,
                "cost": cost,
                "value_now": value_now,
                "pnl": pnl,
                "pnl_pct": pnl_pct,
                "action": current_action,
                "score": current_score,
                "notes": pos.get("notes") or "",
            })

        # --- KPI ROW ---
        total_pnl = total_value - total_cost
        total_pnl_pct = (total_pnl / total_cost * 100) if total_cost > 0 else 0
        kpi_cols = st.columns(4)
        kpi_color = "#047857" if total_pnl >= 0 else "#b91c1c"
        with kpi_cols[0]:
            st.markdown(
                f"""<div class="stat-card"><div class="stat-value">{format_idr(total_cost)}</div>
                <div class="stat-label">Total cost</div></div>""",
                unsafe_allow_html=True,
            )
        with kpi_cols[1]:
            st.markdown(
                f"""<div class="stat-card"><div class="stat-value">{format_idr(total_value)}</div>
                <div class="stat-label">Nilai sekarang</div></div>""",
                unsafe_allow_html=True,
            )
        with kpi_cols[2]:
            st.markdown(
                f"""<div class="stat-card"><div class="stat-value" style="color:{kpi_color}">{total_pnl:+,.0f}</div>
                <div class="stat-label">P/L (IDR)</div></div>""",
                unsafe_allow_html=True,
            )
        with kpi_cols[3]:
            st.markdown(
                f"""<div class="stat-card"><div class="stat-value" style="color:{kpi_color}">{total_pnl_pct:+.2f}%</div>
                <div class="stat-label">P/L %</div></div>""",
                unsafe_allow_html=True,
            )

        # --- EXPOSURE WARNINGS ---
        warnings = []
        if capital > 0:
            exposure_pct = total_cost / capital * 100
            if exposure_pct > 100:
                warnings.append(
                    f"⚠️ Exposure {exposure_pct:.0f}% — total cost melebihi modal yang di-set (cek input)."
                )
            elif exposure_pct > 80:
                warnings.append(
                    f"⚠️ Exposure tinggi {exposure_pct:.0f}% dari modal — kurangi posisi atau tambah modal."
                )
            # Concentration per symbol
            for r in rows_data:
                sym_pct = r["cost"] / capital * 100
                if sym_pct > 30:
                    warnings.append(
                        f"⚠️ {r['symbol']} ambil {sym_pct:.0f}% modal — konsentrasi tinggi, pertimbangkan diversifikasi."
                    )
        # Action mismatch — coin yang dipegang ternyata sekarang JANGAN BELI / HINDARI
        for r in rows_data:
            if r["action"] in ("JANGAN BELI", "HINDARI"):
                warnings.append(
                    f"⚠️ {r['symbol']} sekarang sinyal **{r['action']}** — pertimbangkan exit di TP terdekat."
                )
        if warnings:
            for w in warnings[:5]:  # cap supaya tidak banjir
                st.warning(w)

        # --- TABLE OF POSITIONS ---
        st.markdown("#### Detail")
        df = pd.DataFrame([
            {
                "Koin": f"{r['symbol']} ({r['category']})",
                "Qty": f"{r['qty']:.6f}".rstrip("0").rstrip("."),
                "Avg buy": format_price(r["avg_buy"]),
                "Harga sekarang": format_price(r["cur_price"]),
                "Cost": format_idr(r["cost"]),
                "Nilai": format_idr(r["value_now"]),
                "P/L": f"{r['pnl']:+,.0f}",
                "P/L %": f"{r['pnl_pct']:+.2f}%",
                "Sinyal": r["action"],
                "Score": f"{r['score']}/100" if r["score"] is not None else "—",
                "Notes": r["notes"] or "—",
            }
            for r in rows_data
        ])
        st.dataframe(df, use_container_width=True, hide_index=True)

        # --- EXPOSURE BREAKDOWN PER KATEGORI ---
        if total_value > 0:
            st.markdown("#### Exposure per kategori")
            cat_map: dict[str, float] = {}
            for r in rows_data:
                cat_map[r["category"]] = cat_map.get(r["category"], 0) + r["value_now"]
            cat_df = pd.DataFrame([
                {"Kategori": cat, "Nilai (IDR)": format_idr(val), "Bobot": f"{val/total_value*100:.1f}%"}
                for cat, val in sorted(cat_map.items(), key=lambda x: -x[1])
            ])
            st.dataframe(cat_df, use_container_width=True, hide_index=True)

        # --- EDIT / CLOSE POSITIONS ---
        st.markdown("#### Kelola posisi")
        st.caption("Pilih posisi untuk edit qty/avg buy atau tutup posisi (simpan history) atau hapus permanen.")
        for r in rows_data:
            with st.expander(f"#{r['id']} · {r['symbol']} · qty {r['qty']} @ {format_price(r['avg_buy'])} · P/L {r['pnl_pct']:+.2f}%"):
                edit_cols = st.columns([1, 1, 2, 1, 1])
                with edit_cols[0]:
                    new_q = st.number_input(
                        "Qty baru", min_value=0.0, value=float(r["qty"]),
                        step=0.0001, format="%.8f", key=f"edit_qty_{r['id']}",
                    )
                with edit_cols[1]:
                    new_a = st.number_input(
                        "Avg buy baru", min_value=0.0, value=float(r["avg_buy"]),
                        step=1.0, format="%.2f", key=f"edit_avg_{r['id']}",
                    )
                with edit_cols[2]:
                    new_n = st.text_input(
                        "Catatan", value=r["notes"], key=f"edit_notes_{r['id']}",
                    )
                with edit_cols[3]:
                    st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
                    if st.button("Update", key=f"upd_{r['id']}", use_container_width=True):
                        ok = journal_store.update_position(
                            r["id"], qty=new_q, avg_buy_price=new_a, notes=new_n,
                        )
                        if ok:
                            st.success("Posisi diupdate")
                            st.rerun()
                        else:
                            st.error("Gagal update")
                with edit_cols[4]:
                    st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
                    close_btn, del_btn = st.columns(2)
                    with close_btn:
                        if st.button("Tutup", key=f"close_{r['id']}", use_container_width=True,
                                     help="Tandai CLOSED (tetap simpan history)"):
                            journal_store.close_position(r["id"])
                            st.success(f"{r['symbol']} ditutup")
                            st.rerun()
                    with del_btn:
                        if st.button("Hapus", key=f"del_{r['id']}", use_container_width=True,
                                     help="Hapus permanen (kalau salah input)"):
                            journal_store.delete_position(r["id"])
                            st.warning(f"#{r['id']} dihapus")
                            st.rerun()

    # --- HISTORY ---
    closed = journal_store.list_positions(status="CLOSED")
    if closed:
        with st.expander(f"📜 Riwayat posisi tertutup ({len(closed)})"):
            hist_df = pd.DataFrame([
                {
                    "Koin": p["symbol"],
                    "Qty": p["qty"],
                    "Avg buy": format_price(p["avg_buy_price"]),
                    "Dibuka": p.get("opened_at", "")[:10],
                    "Ditutup": (p.get("closed_at") or "—")[:10],
                    "Notes": p.get("notes") or "",
                }
                for p in closed
            ])
            st.dataframe(hist_df, use_container_width=True, hide_index=True)


# =============================================================================
# KALIBRASI PROBABILITAS — apakah ramalan jujur?
# =============================================================================
def render_calibration_panel():
    """Bandingkan probabilitas ramalan vs hasil aktual dari signal journal.

    Menjawab: saat web bilang '70% naik', apakah benar ~70% yang naik?
    Ini yang membedakan model yang pintar beneran vs yang cuma terlihat pintar.
    """
    journal = load_learning_journal()
    pairs = calibration_engine.extract_pairs_from_journal(journal)
    report = calibration_engine.build_calibration_report(pairs)

    st.markdown("### Kalibrasi ramalan (kejujuran probabilitas)")
    st.caption(
        "Membandingkan probabilitas yang diramalkan saat sinyal dibuat dengan hasil "
        "nyatanya. Tujuannya menilai apakah angka persen bisa dipercaya — bukan klaim akurasi."
    )

    if report["sample_count"] < 20:
        st.info(
            f"Butuh minimal 20 sinyal tertutup yang menyimpan probabilitas ramalan untuk "
            f"menilai kalibrasi. Saat ini baru {report['sample_count']}. Panel ini akan terisi "
            "otomatis seiring sinyal baru ditutup (TP/SL/expired)."
        )
        return

    grade_color = {
        "tinggi": "#047857",
        "sedang": "#b45309",
        "rendah": "#b91c1c",
    }.get(report["confidence"], "#64748b")

    cols = st.columns(3)
    with cols[0]:
        st.markdown(
            f"""<div class="stat-card"><div class="stat-value" style="color:{grade_color};font-size:1rem">{report['grade']}</div>
            <div class="stat-label">Status kalibrasi</div></div>""",
            unsafe_allow_html=True,
        )
    with cols[1]:
        brier = report["brier_score"]
        # Brier: <0.20 baik, 0.25 = nebak. Makin kecil makin baik.
        bcolor = "#047857" if brier is not None and brier <= 0.20 else "#b45309" if brier is not None and brier <= 0.25 else "#b91c1c"
        st.markdown(
            f"""<div class="stat-card"><div class="stat-value" style="color:{bcolor}">{brier if brier is not None else '—'}</div>
            <div class="stat-label">Brier score (↓ baik)</div></div>""",
            unsafe_allow_html=True,
        )
    with cols[2]:
        ece = report["ece"]
        ece_pct = f"{ece*100:.1f}%" if ece is not None else "—"
        ecolor = "#047857" if ece is not None and ece <= 0.05 else "#b45309" if ece is not None and ece <= 0.12 else "#b91c1c"
        st.markdown(
            f"""<div class="stat-card"><div class="stat-value" style="color:{ecolor}">{ece_pct}</div>
            <div class="stat-label">Calib. error (↓ baik)</div></div>""",
            unsafe_allow_html=True,
        )

    st.markdown(
        f"""<div style="background:#ffffff;border:1px solid #e2e8f0;border-left:4px solid {grade_color};
                    border-radius:8px;padding:0.75rem 1rem;margin:0.6rem 0;color:#334155;
                    font-size:0.86rem;font-weight:600">{report['note']}</div>""",
        unsafe_allow_html=True,
    )

    # Reliability table: prediksi vs aktual per bucket
    buckets = report["buckets"]
    if buckets:
        st.markdown("#### Reliability per bucket probabilitas")
        st.caption(
            "Kolom 'Diramalkan' vs 'Aktual naik' idealnya berdekatan. Selisih besar = "
            "ramalan di rentang itu kurang bisa dipercaya."
        )
        df_buckets = pd.DataFrame([
            {
                "Rentang": f"{int(b['bin_low']*100)}–{int(b['bin_high']*100)}%",
                "Jumlah sinyal": b["count"],
                "Diramalkan (rata2)": f"{b['avg_predicted']:.0f}%",
                "Aktual naik": f"{b['actual_freq']:.0f}%",
                "Selisih": f"{b['gap']:+.0f}%",
            }
            for b in buckets
        ])
        st.dataframe(df_buckets, use_container_width=True, hide_index=True)

        # Chart: prediksi vs aktual (garis ideal = diagonal)
        chart_df = pd.DataFrame({
            "Diramalkan": [b["avg_predicted"] for b in buckets],
            "Aktual": [b["actual_freq"] for b in buckets],
        })
        st.line_chart(chart_df, x="Diramalkan", y="Aktual", use_container_width=True, height=240)


# =============================================================================
# STATISTIK BOT TAB (quantstats metrics dari signal journal)
# =============================================================================
def render_stats_tab():
    """Tab Statistik Bot: Sharpe, Sortino, max DD, equity curve dari signal journal."""
    st.markdown("## Statistik Performa Bot")
    st.markdown(
        "Metrik performance dihitung dari `signal_journal` (closed signals). "
        "Dipakai untuk evaluasi apakah strategi web ini benar-benar profitable atau cuma keberuntungan."
    )

    journal = load_learning_journal()
    metrics = smart_engine.compute_journal_metrics(journal)

    if metrics["trades"] == 0:
        st.info(
            "Belum ada sinyal yang sudah closed. Statistik akan muncul setelah ada beberapa "
            "trade yang TP/SL/Expired. Sabar — ini bagian dari proses learning engine."
        )
        return

    # KPI cards
    cols = st.columns(4)
    with cols[0]:
        st.markdown(
            f"""<div class="stat-card"><div class="stat-value">{metrics['trades']}</div>
            <div class="stat-label">Total trades</div></div>""",
            unsafe_allow_html=True,
        )
    with cols[1]:
        wr = metrics.get("winrate")
        wr_color = "#047857" if wr and wr >= 55 else "#b45309" if wr and wr >= 45 else "#b91c1c"
        wr_text = f"{wr:.1f}%" if wr is not None else "—"
        st.markdown(
            f"""<div class="stat-card"><div class="stat-value" style="color:{wr_color}">{wr_text}</div>
            <div class="stat-label">Winrate</div></div>""",
            unsafe_allow_html=True,
        )
    with cols[2]:
        avg = metrics.get("avg_return_pct", 0)
        avg_color = "#047857" if avg > 0 else "#b91c1c"
        st.markdown(
            f"""<div class="stat-card"><div class="stat-value" style="color:{avg_color}">{avg:+.2f}%</div>
            <div class="stat-label">Avg return/trade</div></div>""",
            unsafe_allow_html=True,
        )
    with cols[3]:
        pf = metrics.get("profit_factor")
        pf_text = f"{pf:.2f}" if pf is not None else "—"
        pf_color = "#047857" if pf and pf >= 1.5 else "#b45309" if pf and pf >= 1.0 else "#b91c1c"
        st.markdown(
            f"""<div class="stat-card"><div class="stat-value" style="color:{pf_color}">{pf_text}</div>
            <div class="stat-label">Profit factor</div></div>""",
            unsafe_allow_html=True,
        )

    # Risk metrics row
    cols2 = st.columns(4)
    with cols2[0]:
        sh = metrics.get("sharpe")
        sh_text = f"{sh:.2f}" if sh is not None else "—"
        sh_color = "#047857" if sh and sh >= 1.0 else "#b45309" if sh and sh >= 0 else "#b91c1c"
        st.markdown(
            f"""<div class="stat-card"><div class="stat-value" style="color:{sh_color}">{sh_text}</div>
            <div class="stat-label">Sharpe ratio</div></div>""",
            unsafe_allow_html=True,
        )
    with cols2[1]:
        so = metrics.get("sortino")
        so_text = f"{so:.2f}" if so is not None else "—"
        so_color = "#047857" if so and so >= 1.0 else "#b45309" if so and so >= 0 else "#b91c1c"
        st.markdown(
            f"""<div class="stat-card"><div class="stat-value" style="color:{so_color}">{so_text}</div>
            <div class="stat-label">Sortino ratio</div></div>""",
            unsafe_allow_html=True,
        )
    with cols2[2]:
        dd = metrics.get("max_drawdown_pct")
        dd_text = f"{dd:.2f}%" if dd is not None else "—"
        st.markdown(
            f"""<div class="stat-card"><div class="stat-value" style="color:#b91c1c">{dd_text}</div>
            <div class="stat-label">Max drawdown</div></div>""",
            unsafe_allow_html=True,
        )
    with cols2[3]:
        best = metrics.get("best_trade_pct", 0)
        worst = metrics.get("worst_trade_pct", 0)
        st.markdown(
            f"""<div class="stat-card">
            <div class="stat-value" style="color:#047857;font-size:0.95rem">{best:+.1f}% / <span style="color:#b91c1c">{worst:+.1f}%</span></div>
            <div class="stat-label">Best / worst trade</div></div>""",
            unsafe_allow_html=True,
        )

    # Equity curve
    eq = metrics.get("equity_curve", [])
    if len(eq) >= 2:
        st.markdown("### Equity curve")
        st.caption("Asumsi 1 unit modal di-compounding setiap trade. Datar = belum profit, naik kanan = healthy.")
        df_eq = pd.DataFrame({"trade": list(range(len(eq))), "equity": eq})
        st.line_chart(df_eq, x="trade", y="equity", use_container_width=True, height=280)

    # Kalibrasi probabilitas: seberapa jujur ramalan?
    render_calibration_panel()

    # Library status
    avail = smart_engine.is_available()
    st.markdown("### Diagnostik library")
    diag_cols = st.columns(3)
    for i, (name, ok) in enumerate(avail.items()):
        with diag_cols[i]:
            status_icon = "✅" if ok else "⚪"
            status_text = "Aktif" if ok else "Belum install"
            color = "#047857" if ok else "#94a3b8"
            st.markdown(
                f"""<div class="stat-card">
                <div class="stat-value" style="color:{color};font-size:1rem">{status_icon} {status_text}</div>
                <div class="stat-label">{name}</div></div>""",
                unsafe_allow_html=True,
            )


# =============================================================================
# EDUCATION TAB — cara baca sinyal
# =============================================================================
def render_education_tab():
    """Halaman edukasi singkat: horizon prediksi, cara baca tiap chip, dan contoh."""
    st.markdown("## Cara Baca Sinyal")
    st.markdown(
        "Halaman ini ngebantu kamu paham apa sebenarnya yang dashboard ini hitung, "
        "dan apa yang **bukan** dilakukan. Baca pelan-pelan biar tidak salah ekspektasi."
    )

    # --- HEADLINE: HORIZON PREDIKSI ---
    st.markdown(
        """
        <div style="background:#fff7ed;border:1px solid #fed7aa;border-left:5px solid #f97316;
                    border-radius:8px;padding:1rem 1.2rem;margin:0.6rem 0 1rem;
                    box-shadow:0 12px 34px rgba(15, 23, 42, 0.06)">
            <div style="color:#c2410c;font-size:0.74rem;font-weight:900;
                        text-transform:uppercase;letter-spacing:0.12em;margin-bottom:0.3rem">
                Horizon prediksi
            </div>
            <div style="color:#0f172a;font-size:1.05rem;font-weight:900;line-height:1.35">
                Web ini memberi sinyal untuk <u>6–24 jam ke depan</u>, bukan ramalan jangka panjang
            </div>
            <div style="color:#64748b;font-size:0.9rem;font-weight:600;margin-top:0.4rem;line-height:1.5">
                Tidak ada model di dunia yang bisa konsisten meramal harga crypto berhari-hari ke depan —
                volatilitas terlalu tinggi dan banyak black swan event. Yang web ini lakukan adalah
                membaca <strong>kondisi sekarang</strong> lalu kalkulasi probabilitas pola lanjut naik
                dalam 6 candle (1H) ke depan, plus skenario kalau retrace ke support terdekat.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # --- ALUR KEPUTUSAN ---
    st.markdown("### 🧭 Alur keputusan yang bot pakai")
    st.markdown(
        """
        Setiap candle (sekitar 60 detik refresh), bot jalanin pipeline ini per coin:

        1. **Tarik harga & 24h change** dari Indodax `/api/summaries`
        2. **Hitung 30+ indikator teknikal**: RSI, EMA, MACD, Bollinger, Supertrend, ADX, Ichimoku, Squeeze, OBV, MFI, VWAP
        3. **Confluence Gate 5/5**: cek 5 syarat valid (Trend EMA200, Volume, Pinbar, Dynamic Wall, Static Support).
           Kalau cuma lulus 3/5, sinyal otomatis dikecilkan jadi WATCH
        4. **Multi-timeframe check**: bias 4H + 1D harus selaras, kalau bearish kompak → tolak entry
        5. **ML KNN forecast**: cari 12-35 pola historis paling mirip kondisi sekarang, hitung berapa persen yang berakhir naik dalam 6 jam
        6. **Backtest**: simulasi sinyal serupa di 90 candle historis, ukur winrate
        7. **Intelligence layer**: cari swing S/R riil, deteksi divergence, kenali pola candle (engulfing/hammer/dll)
        8. **News sentiment**: baca RSS CoinDesk/Cointelegraph/Decrypt + X feed, kasih bias positif/negatif
        9. **Learning engine**: cek riwayat sinyal coin ini — kalau pernah 70%+ winrate, score naik; kalau lemah, dipotong
        10. **Final action**: BELI KUAT / CICIL BELI / WATCH / JANGAN BELI / HINDARI + alokasi 0-10% modal via Kelly Criterion
        """
    )

    # --- TIPS BACA KARTU ---
    st.markdown("### 📇 Cara baca kartu rekomendasi")
    with st.expander("Score, Risk, Alokasi, Volume", expanded=True):
        st.markdown(
            """
            - **Score 0–100**: gabungan momentum + tech + ML + backtest + news + learning. **>=80 = BELI KUAT**, 65-79 = CICIL BELI
            - **Risk**: dihitung dari volatilitas 24h, RSI overbought, posisi di range, dan kekuatan sinyal bearish. **TINGGI = entry kecil saja**
            - **Alokasi %**: porsi modal yang disarankan untuk coin ini, sudah dibobot Kelly Criterion + risk multiplier. Maksimal 10%
            - **Volume**: makin besar makin likuid, makin aman exit. Coin <Rp100JT/24h biasanya pump-dump
            """
        )

    with st.expander("RSI, ML, MTF, News, Learning"):
        st.markdown(
            """
            - **RSI 30-70**: zona normal. <30 oversold (peluang beli), >70 overbought (jangan kejar)
            - **ML BULLISH 65%**: dari 12-35 pola historis paling mirip, 65% berakhir naik 1%+ dalam 6 jam. **Bukan jaminan**
            - **MTF ALIGN BULLISH**: 4H + 1D kompak naik. **MIXED = arah belum jelas**, lebih baik tunggu
            - **News +2 / -3**: bias sentimen dari headline 36 jam terakhir. Cuma adjustment kecil, jangan jadi alasan utama
            - **Learning +5**: coin ini di riwayat 70%+ winrate, dapat boost. -6 = sebaliknya, hati-hati
            """
        )

    with st.expander("Smart adj, Divergence, Candle, Regime, VWAP, Fib zone"):
        st.markdown(
            """
            - **Smart adj** (-18 sampai +14): agregat dari intelligence layer. Confidence label TINGGI = sinyal jelas
            - **Divergence BULLISH**: harga lower low tapi RSI higher low → potensi reversal naik. Sinyal kuat untuk entry
            - **Candle pattern**: engulfing/hammer = bullish, shooting star/bearish engulfing = sebaliknya
            - **Regime TRENDING KUAT** (Choppiness <38): momentum sinyal lebih akurat. **RANGING (>62)**: lebih cocok mean-reversion
            - **VWAP ABOVE +5%**: harga premium, fomo zone. **BELOW -2%**: diskon, peluang akumulasi saat tren naik
            - **Fib zone GOLDEN 0.5/0.618**: zona klasik untuk entry saat retrace. DI HIGH = sudah mahal
            - **Kelly %**: alokasi optimal dari winrate historis coin ini (di-cap ke 10%)
            """
        )

    with st.expander("Two Steps Ahead — bukan ramalan, tapi roadmap"):
        st.markdown(
            """
            Bagian ini menjawab "**kalau saya entry sekarang, ke mana harga nanti**?":

            - **Step 1**: target terdekat = swing resistance R1 dari ~3 minggu terakhir
            - **Step 2**: kalau R1 tembus, lanjut ke R2 (bisa terjadi dalam beberapa jam atau beberapa hari, **tidak ada timeline**)
            - **Skenario gagal**: kalau momentum hilang, harga retrace ke swing support S1

            **Penting**: ini skenario, bukan jadwal. Salah satu dari step 1, step 2, atau gagal akan terjadi.
            Disiplin TP/SL kamu yang menentukan apakah kamu profit di step 1, step 2, atau cut loss di skenario gagal.
            """
        )

    with st.expander("TP1, TP2, Target, Stop Loss, Trailing"):
        st.markdown(
            """
            - **TP1**: ambil 30% posisi di sini (locking profit awal)
            - **TP2**: ambil 30% lagi
            - **Target**: ambil 40% sisanya, sekaligus geser SL ke breakeven
            - **Stop Loss**: cut loss otomatis kalau harga jebol. **Kalau SL kena, jangan rata-ratakan posisi**
            - **Trailing %**: setelah TP1 hit, trailing stop melindungi profit kalau harga reversal
            """
        )

    # --- CONTOH SKENARIO ---
    st.markdown("### 📊 Contoh skenario nyata")
    st.markdown(
        """
        **Skenario A — sinyal valid 5/5:**
        - BTC score 85, MTF ALIGN BULLISH, ML BULLISH 70%, Confluence 5/5
        - Entry → TP1 +1.5% (ambil 30%) → TP2 +3% (ambil 30%) → Target +5% (ambil 40%)
        - Total profit ~3% dalam 12-24 jam. Disiplin > greedy.

        **Skenario B — sinyal valid 4/5:**
        - ETH score 70, Confluence 4/5, Risk SEDANG
        - Entry kecil (2-3% modal saja) — alokasi otomatis dipotong 50%
        - Bersiap jika retrace ke support, cut loss kalau jebol

        **Skenario C — JANGAN BELI:**
        - Coin micin score 35, RSI 85 (overbought), MTF MIXED, vol <Rp100JT
        - Skip dulu, tunggu retrace + sinyal lebih bersih. Banyak yang menggoda, tapi disiplin.
        """
    )

    # --- DISCLAIMER PENUTUP ---
    st.markdown(
        """
        <div style="background:#fef2f2;border:1px solid #fecaca;border-left:5px solid #b91c1c;
                    border-radius:8px;padding:0.9rem 1.1rem;margin:1.2rem 0;
                    color:#7f1d1d;font-size:0.88rem;line-height:1.55;font-weight:600">
            <strong>Disclaimer keras:</strong> Ini bukan saran keuangan. Web ini cuma alat bantu analisis statistik
            yang punya tingkat error nyata. Pasar crypto berisiko tinggi, kamu bisa kehilangan seluruh modal dalam
            hitungan menit. Selalu lakukan riset sendiri (DYOR), gunakan modal yang siap kamu hilangkan, dan
            <strong>jangan pernah leverage</strong> sampai kamu paham 100% mekanismenya.
        </div>
        """,
        unsafe_allow_html=True,
    )


# =============================================================================
# PUMP DETECTOR TAB
# =============================================================================
def render_pump_detector_tab(tickers, prices_24h):
    """Tab Pump Detector: scan seluruh koin Indodax untuk mendeteksi pump."""
    st.markdown("## 🔥 Pump Detector Scanner")
    st.markdown(
        "Scan otomatis **500+ koin Indodax** untuk mendeteksi koin yang menunjukkan "
        "tanda-tanda **akan pump** (pre-pump setup). Gunakan sebagai radar awal, "
        "selalu konfirmasi dengan analisis mandiri."
    )

    col_btn, col_info = st.columns([1, 2])
    with col_btn:
        run_scan = st.button(
            "🔍 Scan Pump Sekarang",
            use_container_width=True,
            type="primary",
            key="btn_pump_scan",
            help="Scan seluruh koin di Indodax (estimasi 1-2 menit)"
        )
    with col_info:
        st.markdown(
            '<div style="padding:0.6rem 1rem;background:#1e293b;border-radius:10px;'
            'border:1px solid #334155;font-size:0.8rem;color:#94a3b8">'
            '⚡ <strong>4-Layer Filter:</strong> Ticker → 15m Setup → 1H Deep Analysis → Pump Score<br>'
            '🎯 Hanya koin dengan <strong>Grade A/B/C</strong> yang ditampilkan'
            '</div>',
            unsafe_allow_html=True,
        )

    # Cek apakah ada hasil di session state (cache)
    if "pump_results" not in st.session_state:
        st.session_state["pump_results"] = None
        st.session_state["pump_scan_time"] = None

    if run_scan:
        progress = st.progress(0, text="🔍 Memulai scan pump...")
        def progress_cb(current, total, message):
            progress.progress(current / total, text=message)

        with st.spinner("Scanning..."):
            results = pump_scanner.run_pump_scan(tickers, prices_24h, progress_callback=progress_cb)

        st.session_state["pump_results"] = results
        from datetime import datetime, timezone, timedelta
        WIB = timezone(timedelta(hours=7))
        st.session_state["pump_scan_time"] = datetime.now(WIB).strftime("%H:%M:%S WIB")
        progress.empty()
        st.rerun()

    results = st.session_state.get("pump_results")
    scan_time = st.session_state.get("pump_scan_time")

    if results is None:
        st.info("👆 Klik tombol di atas untuk memulai scan pump. Proses memakan waktu ~1-2 menit.")
        return

    if not results:
        st.warning("Tidak ditemukan koin dengan setup pump yang valid saat ini. Coba scan lagi nanti.")
        return

    # Header hasil
    st.markdown(
        f'<div style="text-align:center;margin:1rem 0">'
        f'<span style="background:#047857;color:white;padding:0.35rem 1rem;border-radius:20px;'
        f'font-size:0.85rem;font-weight:700">'
        f'🔥 {len(results)} koin terdeteksi · Scan {scan_time}</span></div>',
        unsafe_allow_html=True,
    )

    # Render each pump result card
    for idx, item in enumerate(results):
        render_pump_card(item, idx)

    # Summary table
    st.markdown("### 📊 Ringkasan Hasil Scan")
    table_data = []
    for r in results:
        deep = r.get("deep_analysis", {})
        setup = r.get("setup_15m", {})
        table_data.append({
            "Symbol": r["symbol"],
            "Pump %": r["pump_probability"],
            "Grade": r["pump_grade"],
            "Timeframe": r["pump_timeframe"],
            "Harga": format_price(r["price"]),
            "Chg 24h": f"{r['change']:+.2f}%",
            "Volume": format_idr(r["vol_idr"]),
            "Score": deep.get("score", 0),
            "RSI": deep.get("rsi_1h", 50),
            "R:R": deep.get("risk_reward", "-"),
            "Trigger": " · ".join(setup.get("triggers", [])),
        })
    df = pd.DataFrame(table_data)
    st.dataframe(df, use_container_width=True, hide_index=True)


def render_pump_card(item: dict, idx: int):
    """Render satu card hasil pump scan."""
    deep = item.get("deep_analysis", {})
    setup = item.get("setup_15m", {})
    scores = item.get("pump_scores", {})
    symbol = item["symbol"]
    pump_prob = item["pump_probability"]
    grade = item["pump_grade"]
    timeframe = item["pump_timeframe"]
    price = item["price"]
    change = item["change"]
    vol_idr = item["vol_idr"]

    # Colors based on grade
    grade_colors = {
        "A": ("#dc2626", "#fef2f2", "linear-gradient(135deg, #fef2f2 0%, #fee2e2 100%)", "🔥🔥🔥"),
        "B": ("#ea580c", "#fff7ed", "linear-gradient(135deg, #fff7ed 0%, #ffedd5 100%)", "🔥🔥"),
        "C": ("#ca8a04", "#fefce8", "linear-gradient(135deg, #fefce8 0%, #fef9c3 100%)", "🔥"),
        "D": ("#64748b", "#f8fafc", "linear-gradient(135deg, #f8fafc 0%, #f1f5f9 100%)", ""),
    }
    gc, gbg, ggr, gfire = grade_colors.get(grade, grade_colors["D"])

    # Pump probability bar
    bar_color = "#dc2626" if pump_prob >= 75 else "#ea580c" if pump_prob >= 60 else "#ca8a04"

    # Trigger pills
    triggers = setup.get("triggers", [])
    trigger_pills = "".join(
        f'<span style="display:inline-block;background:#e2e8f0;color:#334155;padding:2px 8px;'
        f'border-radius:10px;font-size:0.7rem;font-weight:700;margin:2px">{t}</span>'
        for t in triggers
    )

    # Score breakdown
    score_items = ""
    for label, val in [("Momentum", scores.get("momentum", 0)), ("Volume", scores.get("volume", 0)),
                       ("Technical", scores.get("technical", 0)), ("Forecast", scores.get("forecast", 0))]:
        bar_w = val * 4  # scale to 100
        score_items += (
            f'<div style="display:flex;align-items:center;gap:6px;margin:2px 0">'
            f'<span style="font-size:0.65rem;color:#64748b;width:60px">{label}</span>'
            f'<div style="flex:1;background:#e2e8f0;border-radius:4px;height:6px">'
            f'<div style="width:{bar_w}%;background:{bar_color};border-radius:4px;height:6px"></div>'
            f'</div>'
            f'<span style="font-size:0.65rem;color:#334155;font-weight:700;width:25px">{val}</span>'
            f'</div>'
        )

    pair_upper = item.get("pair", "").upper().replace("_", "")
    buy_link = f"https://indodax.com/market/{pair_upper}?ref={REFERRAL_CODE}"
    ch_sign = "+" if change >= 0 else ""
    ch_color = "#047857" if change >= 0 else "#b91c1c"

    # Category
    category = COIN_CATEGORIES.get(symbol, "Lainnya")
    cat_color = CATEGORY_COLORS.get(category, "#6b7280")

    st.markdown(
        f"""
        <div style="background:{ggr};border:2px solid {gc}22;border-radius:16px;
                    padding:1.2rem;margin-bottom:1rem;position:relative;overflow:hidden">
            <!-- Grade Badge -->
            <div style="position:absolute;top:12px;right:12px;background:{gc};
                        color:white;padding:4px 14px;border-radius:20px;
                        font-size:0.8rem;font-weight:900;letter-spacing:1px">
                {gfire} GRADE {grade}
            </div>

            <!-- Header -->
            <div style="display:flex;align-items:center;gap:12px;margin-bottom:0.8rem">
                <div style="font-size:1.5rem;font-weight:900;color:#0f172a">{symbol}</div>
                <span style="background:{cat_color}22;color:{cat_color};padding:2px 10px;
                             border-radius:8px;font-size:0.7rem;font-weight:700">{category}</span>
            </div>

            <!-- Price & Change -->
            <div style="display:flex;align-items:baseline;gap:10px;margin-bottom:0.6rem">
                <span style="font-size:1.1rem;font-weight:800;color:#0f172a">{format_price(price)}</span>
                <span style="font-size:0.9rem;font-weight:700;color:{ch_color}">{ch_sign}{change:.2f}%</span>
                <span style="font-size:0.75rem;color:#64748b">Vol {format_idr(vol_idr)}</span>
            </div>

            <!-- Pump Probability Bar -->
            <div style="margin-bottom:0.8rem">
                <div style="display:flex;justify-content:space-between;margin-bottom:4px">
                    <span style="font-size:0.75rem;font-weight:700;color:#334155">Pump Probability</span>
                    <span style="font-size:0.9rem;font-weight:900;color:{gc}">{pump_prob}%</span>
                </div>
                <div style="background:#e2e8f0;border-radius:8px;height:10px;overflow:hidden">
                    <div style="width:{pump_prob}%;background:linear-gradient(90deg,{bar_color},{gc});
                                border-radius:8px;height:10px;transition:width 0.5s ease"></div>
                </div>
                <div style="text-align:right;font-size:0.7rem;color:#64748b;margin-top:2px">
                    Est. pump dalam {timeframe}
                </div>
            </div>

            <!-- Trigger Pills -->
            <div style="margin-bottom:0.8rem">
                <span style="font-size:0.7rem;color:#64748b;font-weight:700">TRIGGER:</span>
                {trigger_pills}
            </div>

            <!-- Score Breakdown -->
            <div style="background:white;border-radius:10px;padding:0.6rem;margin-bottom:0.8rem;
                        border:1px solid #e2e8f0">
                <div style="font-size:0.7rem;font-weight:700;color:#334155;margin-bottom:4px">
                    Score Breakdown (maks 25 per kategori)
                </div>
                {score_items}
            </div>

            <!-- Entry & TP/SL -->
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:0.5rem">
                <div style="background:#f0fdf4;border:1px solid #86efac;border-radius:10px;padding:0.5rem;text-align:center">
                    <div style="font-size:0.65rem;color:#166534;font-weight:700">🎯 ENTRY ZONE</div>
                    <div style="font-size:0.8rem;font-weight:800;color:#047857">
                        {format_price(deep.get('entry_zone_low'))} – {format_price(deep.get('entry_zone_high'))}
                    </div>
                </div>
                <div style="background:#fef2f2;border:1px solid #fca5a5;border-radius:10px;padding:0.5rem;text-align:center">
                    <div style="font-size:0.65rem;color:#991b1b;font-weight:700">🛑 STOP LOSS</div>
                    <div style="font-size:0.8rem;font-weight:800;color:#b91c1c">
                        {format_price(deep.get('stop_loss'))}
                    </div>
                </div>
            </div>

            <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:6px;margin-bottom:0.5rem">
                <div style="background:white;border:1px solid #e2e8f0;border-radius:8px;padding:0.4rem;text-align:center">
                    <div style="font-size:0.6rem;color:#64748b;font-weight:700">TP1</div>
                    <div style="font-size:0.75rem;font-weight:700;color:#047857">{format_price(deep.get('tp1'))}</div>
                </div>
                <div style="background:white;border:1px solid #e2e8f0;border-radius:8px;padding:0.4rem;text-align:center">
                    <div style="font-size:0.6rem;color:#64748b;font-weight:700">TP2</div>
                    <div style="font-size:0.75rem;font-weight:700;color:#047857">{format_price(deep.get('tp2'))}</div>
                </div>
                <div style="background:white;border:1px solid #e2e8f0;border-radius:8px;padding:0.4rem;text-align:center">
                    <div style="font-size:0.6rem;color:#64748b;font-weight:700">TP3</div>
                    <div style="font-size:0.75rem;font-weight:700;color:#047857">{format_price(deep.get('tp3'))}</div>
                </div>
            </div>

            <!-- Technical Summary -->
            <div style="display:flex;flex-wrap:wrap;gap:4px;margin-bottom:0.5rem">
                <span class="metric-chip"><span class="metric-label">Score</span>
                    <span class="metric-value">{deep.get('score', 0)}</span></span>
                <span class="metric-chip"><span class="metric-label">RSI</span>
                    <span class="metric-value">{deep.get('rsi_1h', 50):.0f}</span></span>
                <span class="metric-chip"><span class="metric-label">MACD</span>
                    <span class="metric-value">{deep.get('macd_signal', 'netral')}</span></span>
                <span class="metric-chip"><span class="metric-label">SuperT</span>
                    <span class="metric-value">{deep.get('supertrend', 'netral')}</span></span>
                <span class="metric-chip"><span class="metric-label">ADX</span>
                    <span class="metric-value">{deep.get('adx', 0):.0f} {deep.get('adx_trend', '')}</span></span>
                <span class="metric-chip"><span class="metric-label">R:R</span>
                    <span class="metric-value" style="color:#047857;font-weight:900">{deep.get('risk_reward', '-')}</span></span>
            </div>

            <!-- CTA Button -->
            <a href="{buy_link}" target="_blank" style="display:block;text-align:center;
                      background:{gc};color:white;padding:0.6rem;border-radius:10px;
                      font-weight:800;font-size:0.85rem;text-decoration:none;
                      margin-top:0.5rem">Entry di Indodax →</a>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_donation():
    with st.expander("💖 Dukung Project Ini (Donasi)"):
        st.markdown("Bantu saya terus mengembangkan tools ini:")
        for wallet, address in DONATION_WALLETS.items():
            st.markdown(f"**{wallet}:**")
            st.code(address, language=None)


def render_footer():
    st.markdown("---")
    cols = st.columns([1, 2, 1])
    with cols[1]:
        st.markdown(
            f"""
            <div style="text-align:center;color:#94a3b8;font-size:0.8rem">
                <p>⚠️ <strong>Bukan Saran Keuangan.</strong> Semua analisis bersifat informatif. Lakukan riset sendiri sebelum bertransaksi.</p>
                <p>🔗 <a href="{INDODAX_REF}" target="_blank" style="color:#10b981">Daftar Indodax</a>
                 · 💬 <a href="{TELEGRAM_COMMUNITY}" target="_blank" style="color:#3b82f6">Telegram Premium</a></p>
                <p>© 2025–2026 Rekomendasi Beli Crypto · Data dari Indodax</p>
            </div>
            """,
            unsafe_allow_html=True,
        )


# =============================================================================
# MAIN APP
# =============================================================================
def main():
    # --- AUTO REFRESH (toggleable) ---
    # Default OFF biar nggak ganggu pas mantau. User bisa nyalain manual.
    # Kalau ON, kita pakai soft-refresh: reload halaman cuma DI BACKGROUND saat tab masih
    # aktif, tanpa flicker splash skeleton.
    if "auto_refresh_enabled" not in st.session_state:
        st.session_state["auto_refresh_enabled"] = False

    if st.session_state["auto_refresh_enabled"]:
        # Soft refresh: cuma trigger reload kalau tab visible & user nggak lagi ngetik /
        # interact. Lebih halus dari meta-refresh murni.
        components.html(
            """
            <script>
            (function() {
              if (window.__autoRefreshScheduled) return;
              window.__autoRefreshScheduled = true;
              const REFRESH_MS = 60000;
              const tick = () => {
                if (document.hidden) {
                  setTimeout(tick, 5000);
                  return;
                }
                const active = document.activeElement;
                const tag = active ? active.tagName : '';
                if (tag === 'INPUT' || tag === 'TEXTAREA' || (active && active.isContentEditable)) {
                  // user lagi ngetik, jangan reload
                  setTimeout(tick, 10000);
                  return;
                }
                window.parent.location.reload();
              };
              setTimeout(tick, REFRESH_MS);
            })();
            </script>
            """,
            height=0,
        )

    render_header()

    # --- REFRESH BUTTON & TOGGLE ---
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        btn_cols = st.columns([2, 1])
        with btn_cols[0]:
            if st.button("Refresh Data Sekarang", use_container_width=True, type="primary"):
                st.cache_data.clear()
                st.rerun()
        with btn_cols[1]:
            current = st.session_state["auto_refresh_enabled"]
            label = "Auto: ON" if current else "Auto: OFF"
            if st.button(label, use_container_width=True, key="toggle_auto_refresh",
                         help="Default OFF supaya halaman nggak reload sendiri pas lagi mantau. Nyalakan kalau ingin update otomatis tiap 60 detik."):
                st.session_state["auto_refresh_enabled"] = not current
                st.rerun()

    # Skeleton splash hanya muncul saat first-load (belum ada cache di session).
    # Kalau data sudah pernah ada, langsung pake yang lama biar nggak flicker.
    has_prior_data = bool(st.session_state.get("last_all_tickers"))
    loading_placeholder = st.empty()
    if not has_prior_data:
        loading_placeholder.markdown(loading_markup(), unsafe_allow_html=True)
    tickers, prices_24h, server_time, error = fetch_all_ticker_data()
    if tickers:
        st.session_state["last_all_tickers"] = tickers

    if error and not tickers:
        loading_placeholder.empty()
        st.error(f"❌ {error}")
        st.info("🔄 Coba refresh halaman dalam beberapa saat.")
        render_footer()
        return
    market_stats = compute_market_stats(tickers, prices_24h)
    if market_stats is None:
        market_stats = {
            "mode": "normal",
            "green_pct": 0,
            "green_count": 0,
            "red_count": 0,
            "avg_change": 0,
            "total_vol": 0,
            "total_pairs": 0,
        }
    main_data = extract_asset_data(tickers, prices_24h, MAIN_ASSETS)
    micin_data = extract_asset_data(tickers, prices_24h, MICIN_ASSETS)
    all_data = {**main_data, **micin_data}
    all_results = analyze_assets(all_data, market_stats)
    news_profile = fetch_cached_news_profile(tuple(sorted(all_data.keys())))
    all_results = apply_news_adjustments(all_results, news_profile)
    learning_profile = update_learning_journal(all_results)
    all_results = apply_learning_adjustments(all_results, learning_profile)
    priority = {"BELI KUAT": 0, "CICIL BELI": 1, "WATCH": 2, "JANGAN BELI": 3, "HINDARI": 4}
    all_results.sort(key=lambda x: (priority.get(x["action"], 5), -x["score"]))
    main_results = [r for r in all_results if r["symbol"] in MAIN_ASSETS]
    micin_results = [r for r in all_results if r["symbol"] in MICIN_ASSETS]
    loading_placeholder.empty()
    if error:
        st.warning(error)
    freshness = "live" if not error else "stale"
    freshness_text = "Live dari Indodax" if not error else "Data cache"
    
    WIB = timezone(timedelta(hours=7))
    if server_time:
        time_str = server_time.astimezone(WIB).strftime("%H:%M:%S WIB")
    else:
        time_str = datetime.now(WIB).strftime("%H:%M:%S WIB")
    auto_state_text = "Auto-refresh tiap 60 detik" if st.session_state["auto_refresh_enabled"] else "Auto-refresh OFF"
    auto_state_color = "#666" if st.session_state["auto_refresh_enabled"] else "#b45309"
    st.markdown(
        f"""<div style="display:flex;justify-content:center;margin-bottom:0.5rem">
            <div class="freshness-badge">
                <span class="freshness-dot {freshness}"></span>
                <span>{freshness_text} · {time_str}</span>
                <span style="margin-left:8px;font-size:0.7rem;color:{auto_state_color}">{auto_state_text}</span>
            </div>
        </div>""",
        unsafe_allow_html=True,
    )
    fg_data = fetch_fear_greed()
    render_sidebar(market_stats, fg_data, all_results)
    render_market_mode_banner(market_stats)
    col_stats, col_fg = st.columns([3, 1])
    with col_stats:
        render_market_stats(market_stats)
    with col_fg:
        render_fear_greed(fg_data)
    render_news_panel(news_profile)
    render_learning_panel(learning_profile)
    render_fomo_alerts(tickers, prices_24h, market_stats, news_profile, learning_profile)

    tab_pilot, tab_pump, tab1, tab_pf, tab_st, tab2, tab3, tab4, tab5, tab6, tab_edu = st.tabs([
        "🤖 AI Auto-Pilot", "🔥 Pump Detector", "Rekomendasi Beli", "Portofolio Saya", "Statistik Bot",
        "Semua Aset", "Micin/Meme", "Analisis Detail", "Scan Koin Lain", "Tanya AI Advisor",
        "Cara Baca Sinyal",
    ])
    with tab_pilot:
        render_pilot_tab(market_stats, all_results, news_profile, learning_profile, tickers, prices_24h)
    with tab_pump:
        render_pump_detector_tab(tickers, prices_24h)
    with tab1:
        render_rekomendasi_list(all_results, "Rekomendasi Beli Hari Ini", max_items=20)
    with tab_pf:
        render_portfolio_tab(tickers, all_results)
    with tab_st:
        render_stats_tab()
    with tab2:
        render_rekomendasi_list(main_results, "Main Assets", max_items=15)
    with tab3:
        render_rekomendasi_list(micin_results, "Micin / Meme Coin", max_items=15)
    with tab4:
        st.markdown("## Analisis Detail Semua Aset")
        if all_results:
            df_data = []
            for r in all_results:
                df_data.append({
                    "Symbol": r["symbol"],
                    "Harga": format_price(r["price"]),
                    "Change": f"{r['change']:+.2f}%",
                    "Volume": format_idr(r["vol_idr"]),
                    "Score": r["score"],
                    "Aksi": r["action"],
                    "Risk": r["risk_level"],
                    "Alokasi": f"{r['allocation_pct']:.1f}%",
                    "TP1": format_price(r["tp1"]),
                    "TP2": format_price(r["tp2"]),
                    "Target": format_price(r["target"]),
                    "SL": format_price(r["stop_loss"]),
                    "Kategori": r["category"],
                })
            df = pd.DataFrame(df_data)
            st.dataframe(df, use_container_width=True, hide_index=True)
        else:
            st.info("Belum ada data.")
    with tab5:
        st.markdown("## 🔍 Scan Aset Indodax Secara Mandiri")
        st.markdown("Pilih koin apa saja dari 500+ aset yang tersedia di Indodax untuk dianalisis indikator teknikal, prediksi ML, dan analisis confluence secara real-time.")
        
        # Ambil daftar semua koin berpasangan IDR
        idr_pairs = sorted([pair.replace("_idr", "").upper() for pair in tickers.keys() if pair.endswith("_idr")])
        
        col_select, col_btn = st.columns([3, 1])
        with col_select:
            selected_sym = st.selectbox("Pilih Koin untuk Di-scan:", idr_pairs, index=idr_pairs.index("BTC") if "BTC" in idr_pairs else 0)
        with col_btn:
            st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
            run_scan = st.button("Jalankan Analisis Cerdas", use_container_width=True, type="primary", key="btn_run_scan")
            
        if run_scan:
            with st.spinner(f"Sedang menarik candle dan menganalisis koin {selected_sym}..."):
                pair = f"{selected_sym.lower()}_idr"
                if pair in tickers:
                    info = tickers[pair]
                    price = float(info["last"])
                    high = float(info.get("high", price))
                    low = float(info.get("low", price))
                    vol_idr = float(info.get("vol_idr", 0))
                    change = calculate_24h_change(price, pair, prices_24h)
                    
                    data = {
                        "symbol": selected_sym,
                        "pair": pair,
                        "price": price,
                        "high": high,
                        "low": low,
                        "vol_idr": vol_idr,
                        "change": change
                    }
                    
                    # Fetch candles
                    candles = fetch_candles(pair)
                    if not candles.empty:
                        # Analyze
                        res = analyze_coin_advanced(selected_sym, data, candles, market_stats)
                        
                        # Apply news and learning adjustments
                        adj_results = apply_news_adjustments([res], news_profile)
                        adj_results = apply_learning_adjustments(adj_results, learning_profile)
                        scanned_res = adj_results[0]
                        
                        st.markdown("### 📊 Hasil Analisis Real-Time")
                        render_rekomendasi_card(scanned_res, 888)
                    else:
                        st.error(f"Gagal mengambil data candle historis untuk {selected_sym}. Silakan coba lagi.")
                else:
                    st.error(f"Koin {selected_sym} tidak terdaftar di Indodax.")
    with tab6:
        st.markdown("## Tanya AI Market Advisor")
        st.markdown(
            "Konsultasikan kondisi portofolio, analisis koin, atau tanyakan pergerakan market Indodax hari ini secara cerdas bersama asisten AI khusus Kripto Mania."
        )
        
        # Quick prompt buttons
        quick_prompts = [
            "Koin mana yang paling potensial naik hari ini?",
            "Berapa alokasi ideal untuk pemula modal 1 juta?",
            "Analisis BTC dan ETH untuk minggu ini",
            "Koin mana yang harus dihindari saat ini?",
        ]
        qp_cols = st.columns(2)
        selected_prompt = None
        for i, qp in enumerate(quick_prompts):
            with qp_cols[i % 2]:
                if st.button(qp, key=f"qp_{i}", use_container_width=True):
                    selected_prompt = qp
        
        # Ambil API key
        gemini_api_key = get_secret("GEMINI_API_KEY", "")
        deepseek_api_key = get_secret("DEEPSEEK_API_KEY", "")
        api_key = gemini_api_key or deepseek_api_key
        
        if not api_key:
            st.warning("⚠️ **API Key tidak ditemukan.** Pastikan Anda telah memasang GEMINI_API_KEY atau DEEPSEEK_API_KEY di secrets Anda.")
        else:
            # Setup session state untuk chat history
            if "messages" not in st.session_state:
                st.session_state.messages = []
                
            # Render chat messages dari session state
            for message in st.session_state.messages:
                with st.chat_message(message["role"]):
                    st.markdown(message["content"])
            
            # Handle quick prompt or chat input
            chat_input = st.chat_input("Tanyakan analisis market di sini...")
            prompt = selected_prompt or chat_input
            if prompt:
                # Tampilkan pesan user
                with st.chat_message("user"):
                    st.markdown(prompt)
                st.session_state.messages.append({"role": "user", "content": prompt})
                
                # Panggil AI API dengan context market
                with st.chat_message("assistant"):
                    with st.spinner("AI sedang berpikir..."):
                        try:
                            # Ringkasan data market saat ini untuk diumpankan sebagai context
                            market_context = []
                            # Ambil 5 koin dengan score beli tertinggi
                            buy_results = [r for r in all_results if is_entry_action(r.get("action", ""))]
                            top_picks = buy_results[:5]
                            
                            context_str = "Kondisi Market Real-time Indodax:\n"
                            if market_stats:
                                context_str += f"- Status Pasar: {market_stats['mode'].upper()} (Hijau: {market_stats['green_pct']}%, Volume: {format_idr(market_stats['total_vol'])})\n"
                            
                            context_str += "- Rekomendasi Teratas (dengan ramalan probabilistik):\n"
                            for c in top_picks:
                                f1_prob = c.get("forecast_step1_prob", 50)
                                f2_prob = c.get("forecast_step2_prob", 50)
                                f1_conf = c.get("forecast_step1_conf", "rendah")
                                context_str += (
                                    f"  * {c['symbol']}: Harga {format_price(c['price'])} ({c['change']:+.2f}%), "
                                    f"Score: {c['score']}/100, Rekomendasi: {c['action']}, "
                                    f"Target: {format_price(c['target'])}, SL: {format_price(c['stop_loss'])}, "
                                    f"Ramalan 6h: {f1_prob:.0f}% naik (conf {f1_conf}), 24h: {f2_prob:.0f}% naik\n"
                                )
                            
                            # Tambahkan konteks sentimen berita dan pembelajaran (learning)
                            if news_profile:
                                context_str += f"- Sentimen Berita Global: {news_profile.get('global_label', 'NEUTRAL')} (Score: {news_profile.get('global_score', 0.0)})\n"
                            if learning_profile:
                                context_str += f"- Performa Sinyal Historis: Winrate {learning_profile.get('winrate', 0.0)}% dari {learning_profile.get('closed', 0)} transaksi selesai.\n"
                                best_syms = learning_profile.get("best_symbols", [])
                                if best_syms:
                                    context_str += f"  * Koin Performa Terbaik: " + ", ".join([f"{sym} ({stats['winrate']:.0f}% WR)" for sym, stats in best_syms]) + "\n"
                            
                            # Buat system prompt khusus
                            system_prompt = (
                                "Anda adalah Kripto Mania AI, asisten trading premium berbahasa Indonesia yang ahli, ramah, dan jujur. "
                                "Gunakan data real-time berikut untuk memberikan wawasan analisis koin atau pasar yang sangat akurat:\n"
                                f"{context_str}\n"
                                "Berikan analisis teknikal/fundamental singkat, ingatkan manajemen risiko (TP/SL/Alokasi), "
                                "dan jawablah dengan bahasa Indonesia yang santun, profesional, serta menyemangati. Selalu ingatkan bahwa ini bukan saran keuangan mutlak (DYOR)."
                            )
                             
                            # Siapkan messages payload
                            api_messages = [{"role": "system", "content": system_prompt}]
                            # Sertakan history (batasi 10 pesan terakhir agar hemat token)
                            for msg in st.session_state.messages[-10:]:
                                api_messages.append({"role": msg["role"], "content": msg["content"]})
                                
                            from openai import OpenAI

                            def _call_provider(api_key, base_url, model_name):
                                client = OpenAI(api_key=api_key, base_url=base_url)
                                resp = client.chat.completions.create(
                                    model=model_name,
                                    messages=api_messages,
                                    temperature=0.7,
                                    max_tokens=1000,
                                )
                                return resp.choices[0].message.content

                            ai_response = None
                            fallback_note = ""
                            quota_keywords = ("ratelimit", "quota", "429", "exceeded", "resource exhausted")

                            # Coba Gemini dulu
                            if gemini_api_key:
                                try:
                                    ai_response = _call_provider(
                                        gemini_api_key,
                                        "https://generativelanguage.googleapis.com/v1beta/openai/",
                                        "gemini-2.5-flash",
                                    )
                                except Exception as gemini_err:
                                    err_text = str(gemini_err).lower() + type(gemini_err).__name__.lower()
                                    is_quota = any(k in err_text for k in quota_keywords)
                                    # Kalau quota habis & ada deepseek, fallback. Kalau bukan quota & no deepseek, bubble up.
                                    if not (is_quota and deepseek_api_key):
                                        if not deepseek_api_key:
                                            raise
                                    else:
                                        fallback_note = "ℹ️ _Gemini quota habis, otomatis fallback ke Deepseek_\n\n"

                            # Fallback ke Deepseek (kalau Gemini gagal quota, atau cuma ada deepseek key)
                            if ai_response is None and deepseek_api_key:
                                ai_response = _call_provider(
                                    deepseek_api_key,
                                    "https://api.deepseek.com",
                                    "deepseek-chat",
                                )

                            if ai_response:
                                full_response = fallback_note + ai_response
                                st.markdown(full_response)
                                st.session_state.messages.append({"role": "assistant", "content": full_response})
                            else:
                                st.error("Tidak ada API key yang valid untuk AI Advisor.")

                        except Exception as e:
                            st.error(f"Gagal menghubungi AI Advisor: {type(e).__name__}: {str(e)[:300]}")
    with tab_edu:
        render_education_tab()
    render_donation()
    render_footer()


if __name__ == "__main__":
    main()
