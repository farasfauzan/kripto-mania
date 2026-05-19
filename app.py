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
    "MATIC": "Layer2", "ARB": "Layer2", "OP": "Layer2", "IMX": "Layer2", "LRC": "Layer2",
    "MANTA": "Layer2", "STRK": "Layer2", "METIS": "Layer2", "SKL": "Layer2", "CELO": "Layer2",
    "BOBA": "Layer2", "ZKSYNC": "Layer2", "SCROLL": "Layer2", "LINEA": "Layer2", "BLAST": "Layer2",
    "MODE": "Layer2", "ZORA": "Layer2", "FUEL": "Layer2", "ALT": "Layer1", "ALTLAYER": "Layer1",
    "LINK": "DeFi", "UNI": "DeFi", "AAVE": "DeFi", "MKR": "DeFi", "CRV": "DeFi",
    "COMP": "DeFi", "SUSHI": "DeFi", "SNX": "DeFi", "YFI": "DeFi", "1INCH": "DeFi",
    "BAL": "DeFi", "CAKE": "DeFi", "GMX": "DeFi", "DYDX": "DeFi", "LDO": "DeFi",
    "FXS": "DeFi", "CVX": "DeFi", "STG": "DeFi", "PENDLE": "DeFi", "JUP": "DeFi",
    "RAY": "DeFi", "ORCA": "DeFi", "VELO": "DeFi", "JOE": "DeFi", "ZRX": "DeFi",
    "RUNE": "DeFi", "THORCHAIN": "DeFi", "BAND": "DeFi", "UMA": "DeFi", "REN": "DeFi",
    "API3": "DeFi", "AKT": "DeFi", "RSR": "DeFi", "OCEAN": "DeFi", "FET": "DeFi",
    "AGIX": "DeFi", "CTSI": "DeFi", "RLC": "DeFi", "CELR": "DeFi", "BNT": "DeFi",
    "KNC": "DeFi", "BADGER": "DeFi", "PERP": "DeFi", "IDEX": "DeFi", "INJ": "DeFi",
    "GNS": "DeFi", "PEPE": "Meme", "FLOKI": "Meme", "WIF": "Meme", "BONK": "Meme",
    "BOME": "Meme", "POPCAT": "Meme", "MEW": "Meme", "MYRO": "Meme", "SLERF": "Meme",
    "SAMO": "Meme", "TOSHI": "Meme", "MOG": "Meme", "PONKE": "Meme", "PUMP": "Meme",
    "FWOG": "Meme", "GIGA": "Meme", "MICHI": "Meme", "MOTHER": "Meme", "TURBO": "Meme",
    "FET": "AI", "RNDR": "AI", "TAO": "AI", "GRT": "AI", "AKT": "AI",
    "WLD": "AI", "AGIX": "AI", "OCEAN": "AI", "PRIME": "AI", "AIOZ": "AI",
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
    page_title="Rekomendasi Beli Crypto Hari Ini",
    page_icon="💰",
    layout="wide",
    initial_sidebar_state="collapsed",
)

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
BOT_INDODAX_REF = "narwanpratanta"
BOT_WIB = timezone(timedelta(hours=7))
BOT_MAIN_ASSETS = {
    "BTC": "btc_idr", "ETH": "eth_idr", "SOL": "sol_idr",
    "XRP": "xrp_idr", "BNB": "bnb_idr", "ADA": "ada_idr",
    "DOGE": "doge_idr",
}

TELEGRAM_MAX_LENGTH = 4096

def clamp(value, min_val, max_val):
    return max(min_val, min(value, max_val))


def is_entry_action(action):
    """Check if action is a genuine entry signal (not 'JANGAN BELI')."""
    action = str(action or "").upper()
    return "BELI KUAT" in action or "CICIL BELI" in action


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
                payload["parse_mode"] = None
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
        pair = BOT_MAIN_ASSETS[s["symbol"]].upper().replace("_", "")
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
    body, .stApp, [data-testid="stAppViewContainer"], [data-testid="stSidebar"], p, div, button, input, textarea, label {
        font-family: 'Plus Jakarta Sans', sans-serif;
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
    .stApp {
        background: linear-gradient(180deg, #f8fafc 0%, #eef4ff 48%, #e8f7ef 100%);
        color: #0f172a;
    }
    .block-container { padding-top: 1.4rem; }
    .buy-button {
        display: inline-block;
        background: linear-gradient(180deg, #22c55e, #16a34a);
        color: white !important;
        text-decoration: none;
        padding: 16px 48px;
        border-radius: 16px;
        font-weight: 800;
        font-size: 1.2rem;
        transition: all 0.25s ease;
        border: none;
        box-shadow: 0 4px 24px rgba(34, 197, 94, 0.45);
        letter-spacing: 0.02em;
    }
    .buy-button:hover {
        transform: translateY(-2px) scale(1.03);
        box-shadow: 0 8px 36px rgba(34, 197, 94, 0.65);
    }
    .buy-button-sm {
        display: inline-block;
        background: #22c55e;
        color: white !important;
        text-decoration: none;
        padding: 10px 24px;
        border-radius: 12px;
        font-weight: 700;
        font-size: 0.9rem;
        transition: all 0.2s ease;
    }
    .buy-button-sm:hover { background: #16a34a; transform: scale(1.04); }
    .buy-button-sm.neutral {
        background: rgba(255, 255, 255, 0.08);
        border: 1px solid rgba(255, 255, 255, 0.15);
        color: #bbb !important;
    }
    .buy-button-sm.neutral:hover {
        background: rgba(255, 255, 255, 0.12);
        color: white !important;
    }
    .rekomendasi-hero {
        background: linear-gradient(135deg, #022c22, #064e3b, #065f46);
        border: 2px solid #10b981;
        border-radius: 28px;
        padding: 2.5rem 2rem;
        text-align: center;
        margin: 1rem 0;
        position: relative;
        overflow: hidden;
    }
    .rekomendasi-hero::before {
        content: '';
        position: absolute;
        top: -50%;
        left: -50%;
        width: 200%;
        height: 200%;
        background: radial-gradient(circle, rgba(16,185,129,0.08) 0%, transparent 60%);
        animation: heroGlow 4s ease-in-out infinite;
    }
    @keyframes heroGlow {
        0%, 100% { transform: translate(0, 0); }
        50% { transform: translate(10px, -10px); }
    }
    .rekomendasi-card {
        background: linear-gradient(180deg, #1a1a1a, #111111);
        border: 2px solid #222;
        border-radius: 20px;
        padding: 1.5rem 1rem;
        text-align: center;
        transition: all 0.3s ease;
        position: relative;
    }
    .rekomendasi-card:hover {
        border-color: #10b981;
        box-shadow: 0 0 30px rgba(16, 185, 129, 0.18);
        transform: translateY(-3px);
    }
    .profit-badge {
        background: linear-gradient(135deg, #22c55e, #16a34a);
        color: white;
        padding: 6px 18px;
        border-radius: 99px;
        font-weight: 800;
        display: inline-block;
        font-size: 0.9rem;
        box-shadow: 0 2px 12px rgba(34,197,94,0.3);
    }
    .loss-badge {
        background: linear-gradient(135deg, #ef4444, #dc2626);
        color: white;
        padding: 6px 18px;
        border-radius: 99px;
        font-weight: 800;
        display: inline-block;
        font-size: 0.9rem;
        box-shadow: 0 2px 12px rgba(239,68,68,0.3);
    }
    .neutral-badge {
        background: linear-gradient(135deg, #6b7280, #4b5563);
        color: white;
        padding: 6px 18px;
        border-radius: 99px;
        font-weight: 800;
        display: inline-block;
        font-size: 0.9rem;
    }
    .price-tag {
        font-size: 2.2rem;
        font-weight: 900;
        background: linear-gradient(135deg, #fbbf24, #f59e0b);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
    }
    section[data-testid="stSidebar"] {
        background-color: #ffffff !important;
        border-right: 1px solid #dbeafe;
    }
    h1 { font-size: 2.6rem !important; font-weight: 900 !important; text-align: center; }
    h2 { font-weight: 800 !important; }
    h3 { font-weight: 700 !important; }
    .stat-card {
        background: #111;
        border: 1px solid #222;
        border-radius: 16px;
        padding: 1rem;
        text-align: center;
    }
    .stat-value {
        font-size: clamp(1.05rem, 1.8vw, 1.5rem);
        font-weight: 900;
        white-space: nowrap;
        overflow-wrap: normal;
        line-height: 1.15;
    }
    .stat-label {
        font-size: 0.75rem;
        color: #888;
        text-transform: uppercase;
        letter-spacing: 0.1em;
        margin-top: 4px;
    }
    .ad-banner {
        background: linear-gradient(135deg, #1a1a2e, #16213e);
        border: 1px solid #2a2a4a;
        border-radius: 16px;
        padding: 1rem 1.5rem;
        text-align: center;
    }
    .pro-card {
        background: linear-gradient(135deg, #1e1b4b, #312e81);
        border: 2px solid #6366f1;
        border-radius: 20px;
        padding: 2rem;
        text-align: center;
    }
    .stDataFrame { border: 1px solid #dbeafe !important; border-radius: 14px !important; }
    .stTabs [data-baseweb="tab-list"] { gap: 8px; background-color: transparent; }
    .stTabs [data-baseweb="tab"] {
        background-color: #ffffff;
        border: 1px solid #dbeafe;
        border-radius: 12px 12px 0 0;
        padding: 12px 28px;
        color: #475569;
        font-weight: 600;
    }
    .stTabs [aria-selected="true"] {
        background: linear-gradient(135deg, #10b981, #059669) !important;
        color: white !important;
    }
    [data-testid="stMetricValue"] { font-weight: 900 !important; }
    hr { border-color: #dbeafe !important; }
    .wallet-text {
        font-family: 'Courier New', monospace;
        font-size: 0.65rem;
        word-break: break-all;
        color: #666;
    }
    .freshness-badge {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        background: #111;
        border: 1px solid #333;
        border-radius: 99px;
        padding: 6px 16px;
        font-size: 0.8rem;
        color: #888;
    }
    .freshness-dot {
        width: 8px;
        height: 8px;
        border-radius: 50%;
        display: inline-block;
    }
    .freshness-dot.live { background: #22c55e; animation: pulse 2s infinite; }
    .freshness-dot.stale { background: #f59e0b; }
    .freshness-dot.offline { background: #ef4444; }
    .app-loading-screen {
        position: fixed;
        inset: 0;
        z-index: 999999;
        display: flex;
        align-items: center;
        justify-content: center;
        padding: 1.25rem;
        background:
            linear-gradient(180deg, rgba(248, 250, 252, 0.96), rgba(232, 247, 239, 0.96)),
            linear-gradient(135deg, #f8fafc, #dbeafe 48%, #dcfce7);
    }
    .app-loading-panel {
        width: min(460px, 92vw);
        background: #ffffff;
        border: 1px solid #dbeafe;
        border-radius: 18px;
        padding: 1.4rem;
        box-shadow: 0 24px 70px rgba(15, 23, 42, 0.16);
    }
    .app-loading-top {
        display: grid;
        grid-template-columns: 74px 1fr;
        gap: 1rem;
        align-items: center;
    }
    .app-loading-symbol {
        position: relative;
        width: 64px;
        height: 64px;
        display: grid;
        place-items: center;
    }
    .app-loading-ring {
        position: absolute;
        inset: 0;
        border-radius: 50%;
        border: 4px solid #dbeafe;
        border-top-color: #22c55e;
        border-right-color: #fbbf24;
        animation: loaderSpin 0.9s linear infinite;
    }
    .app-loading-coin {
        width: 42px;
        height: 42px;
        border-radius: 50%;
        display: grid;
        place-items: center;
        background: linear-gradient(135deg, #fbbf24, #22c55e);
        color: #ffffff;
        font-size: 1.4rem;
        font-weight: 900;
        box-shadow: 0 8px 24px rgba(34, 197, 94, 0.22);
    }
    .app-loading-kicker {
        margin: 0 0 0.2rem 0;
        color: #059669;
        font-size: 0.72rem;
        font-weight: 900;
        letter-spacing: 0.12em;
    }
    .app-loading-title {
        margin: 0;
        color: #0f172a;
        font-size: 1.2rem;
        line-height: 1.25;
        font-weight: 900;
    }
    .app-loading-detail {
        margin: 0.35rem 0 0 0;
        color: #64748b;
        font-size: 0.88rem;
        line-height: 1.45;
        font-weight: 600;
    }
    .app-loading-bars {
        display: grid;
        grid-template-columns: 1.2fr 0.8fr 1fr;
        gap: 0.45rem;
        margin-top: 1.15rem;
    }
    .app-loading-bars span {
        height: 8px;
        border-radius: 999px;
        background: linear-gradient(90deg, #22c55e, #fbbf24, #3b82f6);
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
    @media (max-width: 480px) {
        .app-loading-panel { padding: 1rem; }
        .app-loading-top { grid-template-columns: 58px 1fr; gap: 0.8rem; }
        .app-loading-symbol { width: 52px; height: 52px; }
        .app-loading-coin { width: 34px; height: 34px; font-size: 1.1rem; }
        .app-loading-title { font-size: 1rem; }
    }
    @media (prefers-reduced-motion: reduce) {
        .app-loading-ring, .app-loading-bars span { animation: none; }
    }
    @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.4; } }
    .fomo-card {
        border-radius: 16px;
        padding: 1.2rem 0.8rem;
        text-align: center;
        margin-bottom: 0.5rem;
        border: 2px solid #fbbf24;
    }
    @media (max-width: 768px) {
        h1 { font-size: 1.6rem !important; }
        .price-tag { font-size: 1.5rem; }
        .buy-button { padding: 12px 28px; font-size: 1rem; }
        .rekomendasi-hero { padding: 1.5rem 1rem; }
    }
    /* Premium clean dashboard layer */
    .stApp {
        background:
            radial-gradient(circle at top left, rgba(34, 197, 94, 0.10), transparent 30rem),
            radial-gradient(circle at top right, rgba(59, 130, 246, 0.10), transparent 28rem),
            #f6f8fb !important;
    }
    .block-container {
        max-width: 1240px;
        padding-top: 1.1rem !important;
        padding-bottom: 2rem !important;
    }
    .app-shell-header {
        background: rgba(255, 255, 255, 0.84);
        border: 1px solid #dbe7f3;
        border-radius: 8px;
        padding: 1.35rem 1.4rem;
        margin-bottom: 0.8rem;
        box-shadow: 0 18px 50px rgba(15, 23, 42, 0.08);
    }
    .app-brand-row {
        display: flex;
        justify-content: space-between;
        align-items: flex-start;
        gap: 1rem;
        flex-wrap: wrap;
    }
    .app-kicker {
        color: #047857;
        font-size: 0.74rem;
        font-weight: 900;
        text-transform: uppercase;
        letter-spacing: 0.12em;
        margin-bottom: 0.25rem;
    }
    .app-title {
        color: #0f172a;
        font-size: 2.25rem;
        line-height: 1.05;
        font-weight: 900;
        margin: 0;
    }
    .app-subtitle {
        color: #64748b;
        font-size: 0.96rem;
        font-weight: 600;
        margin: 0.45rem 0 0;
        max-width: 720px;
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
        min-height: 36px;
        border-radius: 8px;
        padding: 0.48rem 0.78rem;
        background: #ffffff;
        border: 1px solid #dbe7f3;
        color: #0f766e !important;
        font-size: 0.8rem;
        font-weight: 800;
        text-decoration: none !important;
    }
    .quick-link.primary {
        background: #0f766e;
        border-color: #0f766e;
        color: #ffffff !important;
    }
    .mode-banner {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 0.8rem;
        flex-wrap: wrap;
        background: #ffffff;
        border: 1px solid var(--mode-color);
        border-left: 5px solid var(--mode-color);
        border-radius: 8px;
        padding: 0.9rem 1rem;
        margin: 0.65rem 0 1rem;
        box-shadow: 0 12px 34px rgba(15, 23, 42, 0.06);
    }
    .mode-title {
        color: var(--mode-color);
        font-weight: 900;
        font-size: 0.98rem;
    }
    .mode-desc {
        color: #64748b;
        font-size: 0.9rem;
        font-weight: 600;
    }
    .stat-card {
        background: #ffffff !important;
        border: 1px solid #dbe7f3 !important;
        border-radius: 8px !important;
        padding: 0.95rem 0.8rem !important;
        box-shadow: 0 10px 28px rgba(15, 23, 42, 0.06);
    }
    .stat-label {
        color: #64748b !important;
        letter-spacing: 0.08em !important;
    }
    .rekomendasi-hero {
        background: #0f172a !important;
        border: 1px solid #1e293b !important;
        border-radius: 8px !important;
        padding: 1.1rem 1.2rem !important;
        text-align: left !important;
        margin: 1rem 0 0.75rem !important;
    }
    .rekomendasi-hero::before { display: none !important; }
    .hero-title {
        color: #ffffff;
        font-size: 1.35rem;
        line-height: 1.2;
        margin: 0;
        font-weight: 900;
    }
    .hero-meta {
        color: #a7f3d0;
        margin: 0.25rem 0 0;
        font-weight: 700;
        font-size: 0.9rem;
    }
    .rekomendasi-card {
        background: #ffffff !important;
        border: 1px solid #dbe7f3 !important;
        border-radius: 8px !important;
        padding: 1rem !important;
        text-align: left !important;
        box-shadow: 0 14px 38px rgba(15, 23, 42, 0.07);
    }
    .rekomendasi-card:hover {
        border-color: #10b981 !important;
        box-shadow: 0 18px 48px rgba(15, 23, 42, 0.10) !important;
        transform: translateY(-2px) !important;
    }
    .coin-card-head {
        display: flex;
        align-items: flex-start;
        justify-content: space-between;
        gap: 1rem;
        flex-wrap: wrap;
    }
    .coin-left {
        display: flex;
        align-items: center;
        gap: 0.75rem;
        min-width: 220px;
    }
    .coin-avatar {
        width: 44px;
        height: 44px;
        border-radius: 8px;
        display: grid;
        place-items: center;
        background: #ecfdf5;
        border: 1px solid #bbf7d0;
        color: #047857;
        font-weight: 900;
        font-size: 0.9rem;
    }
    .coin-symbol {
        color: #0f172a;
        font-weight: 900;
        font-size: 1.24rem;
        line-height: 1;
    }
    .coin-category {
        color: #64748b;
        font-size: 0.78rem;
        font-weight: 700;
        margin-top: 0.2rem;
    }
    .coin-price-wrap {
        display: flex;
        align-items: center;
        justify-content: flex-end;
        gap: 0.55rem;
        flex-wrap: wrap;
    }
    .price-tag {
        color: #0f172a !important;
        background: none !important;
        -webkit-text-fill-color: initial !important;
        font-size: 1.55rem !important;
        line-height: 1.05;
        font-weight: 900;
    }
    .profit-badge, .loss-badge, .neutral-badge {
        border-radius: 8px !important;
        padding: 0.35rem 0.55rem !important;
        box-shadow: none !important;
        font-size: 0.8rem !important;
    }
    .signal-pill {
        display: inline-flex;
        align-items: center;
        border-radius: 8px;
        padding: 0.4rem 0.62rem;
        font-size: 0.78rem;
        font-weight: 900;
        margin-top: 0.6rem;
    }
    .signal-buy { color: #047857; background: #ecfdf5; border: 1px solid #bbf7d0; }
    .signal-watch { color: #b45309; background: #fffbeb; border: 1px solid #fde68a; }
    .signal-avoid { color: #b91c1c; background: #fef2f2; border: 1px solid #fecaca; }
    .metrics-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(118px, 1fr));
        gap: 0.5rem;
        margin-top: 0.85rem;
    }
    .metric-chip {
        background: #f8fafc;
        border: 1px solid #e2e8f0;
        border-radius: 8px;
        padding: 0.58rem 0.65rem;
        min-height: 64px;
    }
    .metric-label {
        color: #64748b;
        display: block;
        font-size: 0.66rem;
        font-weight: 900;
        letter-spacing: 0.08em;
        text-transform: uppercase;
    }
    .metric-value {
        color: #0f172a;
        display: block;
        font-size: 0.95rem;
        font-weight: 900;
        margin-top: 0.22rem;
        word-break: break-word;
    }
    .card-section {
        margin-top: 0.72rem;
        padding: 0.72rem;
        border-radius: 8px;
        background: #f8fafc;
        border: 1px solid #e2e8f0;
    }
    .section-row {
        display: flex;
        justify-content: space-between;
        align-items: center;
        gap: 0.7rem;
        flex-wrap: wrap;
    }
    .section-label {
        color: #64748b;
        font-size: 0.68rem;
        font-weight: 900;
        letter-spacing: 0.08em;
        text-transform: uppercase;
    }
    .section-strong {
        color: #0f172a;
        font-size: 0.86rem;
        font-weight: 900;
    }
    .scenario-grid {
        display: grid;
        grid-template-columns: repeat(2, minmax(0, 1fr));
        gap: 0.55rem;
        margin-top: 0.72rem;
    }
    .scenario-box {
        border-radius: 8px;
        padding: 0.7rem;
        border: 1px solid;
        min-height: 108px;
    }
    .scenario-title {
        font-size: 0.68rem;
        font-weight: 900;
        letter-spacing: 0.08em;
        text-transform: uppercase;
    }
    .scenario-action {
        color: #334155;
        font-size: 0.8rem;
        font-weight: 700;
        margin-top: 0.35rem;
        min-height: 34px;
    }
    .scenario-price {
        font-size: 0.95rem;
        font-weight: 900;
        margin-top: 0.25rem;
    }
    .check-list {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
        gap: 0.35rem;
        margin-top: 0.45rem;
    }
    .check-row {
        display: flex;
        justify-content: space-between;
        align-items: center;
        gap: 0.5rem;
        background: #ffffff;
        border: 1px solid #e2e8f0;
        border-radius: 8px;
        padding: 0.38rem 0.48rem;
        font-size: 0.75rem;
        font-weight: 800;
    }
    .check-ok { color: #047857; }
    .check-no { color: #94a3b8; }
    .learning-panel {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 1rem;
        flex-wrap: wrap;
        background: #ffffff;
        border: 1px solid #bfdbfe;
        border-left: 5px solid #2563eb;
        border-radius: 8px;
        padding: 0.9rem 1rem;
        margin: 0.8rem 0 1rem;
        box-shadow: 0 12px 34px rgba(15, 23, 42, 0.06);
    }
    .learning-title {
        color: #0f172a;
        font-size: 1rem;
        font-weight: 900;
        margin-top: 0.18rem;
    }
    .learning-note {
        color: #64748b;
        font-size: 0.84rem;
        font-weight: 700;
        margin-top: 0.25rem;
    }
    .learning-stats {
        display: grid;
        grid-template-columns: repeat(3, minmax(76px, 1fr));
        gap: 0.5rem;
        min-width: min(360px, 100%);
    }
    .learning-stats div {
        background: #eff6ff;
        border: 1px solid #dbeafe;
        border-radius: 8px;
        padding: 0.55rem 0.65rem;
        text-align: center;
    }
    .learning-stats span {
        display: block;
        color: #1d4ed8;
        font-size: 1.05rem;
        font-weight: 900;
        line-height: 1.1;
    }
    .learning-stats small {
        display: block;
        color: #64748b;
        font-size: 0.66rem;
        font-weight: 900;
        letter-spacing: 0.08em;
        text-transform: uppercase;
        margin-top: 0.18rem;
    }
    .news-panel {
        background: #ffffff;
        border: 1px solid #fed7aa;
        border-left: 5px solid #f97316;
        border-radius: 8px;
        padding: 0.9rem 1rem;
        margin: 0.8rem 0 1rem;
        box-shadow: 0 12px 34px rgba(15, 23, 42, 0.06);
    }
    .news-list {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
        gap: 0.5rem;
        margin-top: 0.65rem;
    }
    .news-headline {
        display: block;
        color: #0f172a !important;
        background: #fff7ed;
        border: 1px solid #fed7aa;
        border-radius: 8px;
        padding: 0.55rem 0.65rem;
        font-size: 0.8rem;
        font-weight: 800;
        text-decoration: none !important;
        line-height: 1.35;
    }
    .news-headline span {
        display: block;
        color: #c2410c;
        font-size: 0.65rem;
        font-weight: 900;
        letter-spacing: 0.08em;
        text-transform: uppercase;
        margin-bottom: 0.16rem;
    }
    .buy-button-sm {
        border-radius: 8px !important;
        padding: 0.62rem 1rem !important;
        background: #047857 !important;
        box-shadow: none !important;
    }
    .buy-button-sm.neutral {
        background: #f8fafc !important;
        border: 1px solid #cbd5e1 !important;
        color: #334155 !important;
    }
    .freshness-badge {
        background: #ffffff !important;
        color: #475569 !important;
        border: 1px solid #dbe7f3 !important;
        border-radius: 8px !important;
        box-shadow: 0 8px 22px rgba(15, 23, 42, 0.05);
    }
    div.stButton > button[kind="primary"] {
        background: #047857 !important;
        border: 1px solid #047857 !important;
        color: #ffffff !important;
        border-radius: 8px !important;
        font-weight: 900 !important;
        min-height: 42px;
        box-shadow: 0 12px 30px rgba(4, 120, 87, 0.18);
    }
    div.stButton > button[kind="primary"]:hover {
        background: #065f46 !important;
        border-color: #065f46 !important;
    }
    .fomo-card {
        background: #ffffff !important;
        border-radius: 8px !important;
        border-width: 1px !important;
        box-shadow: 0 10px 26px rgba(15, 23, 42, 0.06);
    }
    @media (max-width: 768px) {
        .app-title { font-size: 1.65rem; }
        .app-shell-header { padding: 1rem; }
        .quick-links { justify-content: flex-start; }
        .coin-price-wrap { justify-content: flex-start; }
        .scenario-grid { grid-template-columns: 1fr; }
        .price-tag { font-size: 1.25rem !important; }
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


# =============================================================================
# CANDLE FETCHING
# =============================================================================
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


def compute_atr(candles, period=14):
    if candles.empty or len(candles) < period + 1:
        return None
    high = candles["high"].astype(float)
    low = candles["low"].astype(float)
    close = candles["close"].astype(float)
    tr = pd.concat([
        high - low,
        (high - close.shift(1)).abs(),
        (low - close.shift(1)).abs()
    ], axis=1).max(axis=1)
    return float(tr.rolling(period).mean().iloc[-1])


def analyze_coin_advanced(symbol, data, candles, market_stats):
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
        - fomo_penalty
        - micin_penalty
        + mode_rules.get("score_adjustment", 0)
    )
    score = int(clamp(round(base), 0, 100))

    # Action
    if score >= 80 and change > 1:
        action, emoji = "BELI KUAT", "🟢"
    elif score >= 65 and change > 0:
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

    # Multi-timeframe guard: jangan agresif jika 4H/1D kompak bearish.
    if mtf["mtf_adjustment"] <= -5 and action in ("BELI KUAT", "CICIL BELI"):
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

    # Laraskan rekomendasi tindakan berdasarkan komite verdict
    if verdict == "TOLAK":
        action, emoji = "JANGAN BELI", "🔴"
    elif verdict == "TUNGGU" and is_entry_action(action):
        action, emoji = "WATCH", "⚪"

    # --- ENTRY ZONE & TWO STEPS AHEAD ---
    # Entry Zone: harga ideal untuk entry berdasarkan support/resistance
    entry_zone_low = price * 0.97  # -3% dari harga saat ini
    entry_zone_high = price * 1.01  # +1% dari harga saat ini
    entry_zone_label = "⬇️ Koreksi" if range_pos > 70 else "⬆️ Saat ini" if range_pos < 30 else "⚖️ Netral"
    
    # Support & Resistance levels
    support_s1 = price * 0.95  # -5%
    support_s2 = price * 0.90  # -10%
    resistance_r1 = price * 1.05  # +5%
    resistance_r2 = price * 1.10  # +10%
    
    # Two Steps Ahead scenarios
    if is_entry_action(action):
        # Skenario bullish
        step1_action = "🚀 Naik ke R1"
        step1_price = resistance_r1
        step1_gain = 5.0
        step2_action = "🚀🚀 Tembus R1, lanjut ke R2"
        step2_price = resistance_r2
        step2_gain = 10.0
        # Skenario bearish (jika gagal)
        fail_action = "📉 Gagal, turun ke S1"
        fail_price = support_s1
        fail_loss = 5.0
    elif "WATCH" in action:
        step1_action = "⏳ Pantau support S1"
        step1_price = support_s1
        step1_gain = -5.0
        step2_action = "⏳ Jika S1 bertahan, target R1"
        step2_price = resistance_r1
        step2_gain = 5.0
        fail_action = "📉 Jika S1 jebol, turun ke S2"
        fail_price = support_s2
        fail_loss = 10.0
    else:
        step1_action = "⛔ Hindari dulu"
        step1_price = 0
        step1_gain = 0
        step2_action = "⛔ Pantau dari jauh"
        step2_price = 0
        step2_gain = 0
        fail_action = "⛔ Tidak direkomendasikan"
        fail_price = 0
        fail_loss = 0

    # ATR based Dynamic TP/SL with Fallback
    atr = compute_atr(candles)
    if atr and atr > 0 and atr < price * 0.25:
        stop_loss = price - (1.5 * atr)
        target = price + (2.0 * atr)
        tp1 = price + (0.7 * atr)
        tp2 = price + (1.4 * atr)
        trailing = clamp((1.5 * atr) / price * 100 * 0.55, 1.5, 5)
    else:
        # Fallback ke rumus momentum biasa jika ATR tidak valid
        gain_pct = clamp(3 + max(change, 0) * 0.75 + (score - 60) * 0.22, 2, 18)
        stop_pct = clamp(2.6 + abs(change) * 0.35 + (1 if risk_level == "TINGGI" else 0), 2.5, 9)
        tp1 = price * (1 + gain_pct * 0.35 / 100)
        tp2 = price * (1 + gain_pct * 0.7 / 100)
        target = price * (1 + gain_pct / 100)
        stop_loss = price * (1 - stop_pct / 100)
        trailing = clamp(stop_pct * 0.55, 1.5, 5)

    # Allocation (adjusted by verdict, confluence, conf strength, and market mode)
    risk_mod = {"RENDAH": 1.0, "SEDANG": 0.65, "TINGGI": 0.35}[risk_level]
    conf_size_mult = 1.0 if confluence["confluence_passed"] == 5 else 0.5 if confluence["confluence_passed"] == 4 else 0
    market_mult = mode_rules.get("allocation_multiplier", 1.0)
    alloc = (
        clamp(7 * (score / 100) * risk_mod * size_mult * conf_size_mult * market_mult, 0, 10)
        if is_entry_action(action) and confluence["allow_entry"]
        else 0
    )

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
    if not SIGNAL_LEARNING_ENABLED or not os.path.exists(SIGNAL_JOURNAL_FILE):
        return _empty_learning_journal()
    try:
        with open(SIGNAL_JOURNAL_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return _empty_learning_journal()
        data.setdefault("version", 1)
        data.setdefault("signals", [])
        data.setdefault("updated_at", None)
        return data
    except (OSError, ValueError, TypeError):
        return _empty_learning_journal()


def save_learning_journal(journal):
    if not SIGNAL_LEARNING_ENABLED:
        return
    try:
        journal["signals"] = journal.get("signals", [])[-500:]
        journal["updated_at"] = datetime.now(BOT_WIB).isoformat()
        tmp_path = f"{SIGNAL_JOURNAL_FILE}.tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(journal, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, SIGNAL_JOURNAL_FILE)
    except OSError:
        pass


def _parse_iso_datetime(value):
    try:
        return datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


def build_learning_profile(journal):
    signals = journal.get("signals", [])
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
    candles_map = _cached_fetch_candles_parallel(pairs_list)
    
    for idx, (symbol, data) in enumerate(assets_data.items()):
        pair = data["pair"]
        candles = candles_map.get(pair, pd.DataFrame())
        result = analyze_coin_advanced(symbol, data, candles, market_stats)
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
    st.markdown(
        f"""
        <div class="learning-panel">
            <div>
                <div class="section-label">Learning engine</div>
                <div class="learning-title">Web mulai belajar dari hasil sinyal</div>
                <div class="learning-note">{best_text}</div>
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
    return
    st.markdown(
        f"""
        <div style="background:linear-gradient(135deg,#0f172a,#1e293b);border-radius:16px;padding:1rem 1.5rem;
                    margin:0.5rem 0;text-align:center;border:1px solid {color}40">
            <div style="font-size:0.75rem;color:#94a3b8;text-transform:uppercase;letter-spacing:0.1em;margin-bottom:0.3rem">
                Fear & Greed Index
            </div>
            <div style="font-size:2.5rem;font-weight:900;color:{color}">{emoji} {val}</div>
            <div style="font-size:0.9rem;font-weight:700;color:{color};text-transform:uppercase">{label}</div>
            <div style="margin-top:0.5rem;background:#334155;border-radius:8px;height:8px;overflow:hidden">
                <div style="width:{val}%;height:100%;background:linear-gradient(90deg,#ef4444,#f97316,#eab308,#22c55e);border-radius:8px"></div>
            </div>
            <div style="display:flex;justify-content:space-between;font-size:0.6rem;color:#64748b;margin-top:0.2rem">
                <span>Extreme Fear</span><span>Extreme Greed</span>
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
        st.markdown("Auto-refresh: **60 detik**")
        st.markdown(
            f"""<a href="{TELEGRAM_COMMUNITY}" target="_blank" style="color:#2563eb;font-weight:900;text-decoration:none">Gabung Telegram Premium</a>""",
            unsafe_allow_html=True,
        )
        return
        st.markdown(
            f"""
            <div style="text-align:center;padding:1rem 0">
                <div style="font-size:1.5rem;font-weight:900;background:linear-gradient(135deg,#10b981,#3b82f6);
                            -webkit-background-clip:text;-webkit-text-fill-color:transparent">💰 Kripto Mania</div>
                <div style="color:#64748b;font-size:0.8rem;margin-top:0.3rem">Dashboard Trading Premium</div>
            </div>""",
            unsafe_allow_html=True,
        )
        st.markdown("---")
        # Referral CTA — prominent
        st.markdown(
            f"""
            <div style="background:linear-gradient(135deg,#059669,#10b981);border-radius:12px;padding:1rem;
                        text-align:center;margin-bottom:1rem">
                <div style="font-size:1.1rem;font-weight:800;color:white">🚀 Mulai Trading Sekarang!</div>
                <div style="font-size:0.75rem;color:#d1fae5;margin:0.3rem 0">Daftar Indodax gratis & dapatkan bonus</div>
                <a href="{INDODAX_REF}" target="_blank" style="display:inline-block;background:white;color:#059669;
                   font-weight:800;padding:0.5rem 1.5rem;border-radius:8px;text-decoration:none;margin-top:0.3rem;
                   font-size:0.9rem">Daftar Sekarang →</a>
            </div>""",
            unsafe_allow_html=True,
        )
        # Fear & Greed in sidebar
        if fg_data:
            render_fear_greed(fg_data)
        # Market summary
        st.markdown("#### 📊 Ringkasan Market")
        if market_stats:
            mode_rules = MARKET_MODE_RULES[market_stats['mode']]
            st.markdown(f"**Status:** {mode_rules['label']}")
            st.markdown(f"**Hijau/Merah:** {market_stats['green_count']}/{market_stats['red_count']}")
            st.markdown(f"**Volume:** {format_idr(market_stats['total_vol'])}")
        # Top picks
        buy_picks = [r for r in all_results if is_entry_action(r.get("action", ""))][:3]
        if buy_picks:
            st.markdown("#### 🔥 Top 3 Picks")
            for p in buy_picks:
                st.markdown(f"**{p['symbol']}** — Score {p['score']}/100 · {p['change']:+.1f}%")
        st.markdown("---")
        # Bot status
        st.markdown("#### 🤖 Status Bot")
        if BOT_ENABLED:
            st.markdown("✅ Telegram Bot: **Aktif 24/7**")
        else:
            st.markdown("⚪ Telegram Bot: **Nonaktif**")
        st.markdown("✅ Auto-refresh: **60 detik**")
        st.markdown("---")
        st.markdown(
            f"""
            <div style="text-align:center">
                <a href="{TELEGRAM_COMMUNITY}" target="_blank" style="color:#3b82f6;font-weight:700;text-decoration:none">
                    💬 Gabung Telegram Premium
                </a>
            </div>""",
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


def render_rekomendasi_card(item, idx):
    change_sign = "+" if item["change"] >= 0 else ""
    change_color = "#22c55e" if item["change"] >= 0 else "#ef4444"
    pair_upper = item["pair"].upper().replace("_", "")
    buy_link = f"https://indodax.com/market/{pair_upper}?ref=narwanpratanta"

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

    check_rows = ""
    for label, ok in confluence_checks.items():
        row_class = "check-ok" if ok else "check-no"
        status = "Valid" if ok else "Belum"
        check_rows += (
            f'<div class="check-row {row_class}">'
            f'<span>{label}</span><span>{status}</span>'
            f'</div>'
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

            <div class="scenario-grid">
                <div class="scenario-box" style="background:#ecfdf5;border-color:#bbf7d0">
                    <div class="scenario-title" style="color:#047857">Skenario naik/pantau</div>
                    <div class="scenario-action">{step_action}</div>
                    <div class="scenario-price" style="color:#047857">{visible_price(item.get('step1_price', 0))}</div>
                </div>
                <div class="scenario-box" style="background:#fef2f2;border-color:#fecaca">
                    <div class="scenario-title" style="color:#b91c1c">Skenario gagal</div>
                    <div class="scenario-action">{fail_action}</div>
                    <div class="scenario-price" style="color:#b91c1c">{visible_price(item.get('fail_price', 0))}</div>
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
    return
    
    # Entry Zone display
    entry_color = "#22c55e" if "Koreksi" in item.get("entry_zone_label", "") else "#f59e0b" if "Netral" in item.get("entry_zone_label", "") else "#3b82f6"
    
    # Tentukan teks tombol dan CSS class berdasarkan status rekomendasi
    is_buy_signal = (
        is_entry_action(item.get("action", "")) and
        item.get("allocation_pct", 0) > 0 and
        item.get("confluence_passed", 0) >= 4 and
        item.get("verdict", "") not in ("TOLAK", "TUNGGU")
    )

    if is_buy_signal:
        if item.get("confluence_passed", 0) == 5:
            cta_text = "🔥 Entry Valid"
        else:
            cta_text = "🟡 Entry Kecil"
        cta_class = "buy-button-sm"
    else:
        cta_text = "👀 Pantau di Indodax"
        cta_class = "buy-button-sm neutral"
        
    # Scenario UI: jangan tampilkan "Skenario Bullish" untuk JANGAN BELI/HINDARI
    action_text = str(item.get("action", ""))
    entry_action = is_entry_action(action_text)
    
    if entry_action:
        left_scenario_title = "✅ SKENARIO BULLISH"
        left_scenario_color = "#22c55e"
        left_scenario_bg = "rgba(34,197,94,0.08)"
        left_scenario_border = "#22c55e20"
    elif "WATCH" in action_text:
        left_scenario_title = "👀 RENCANA PANTAU"
        left_scenario_color = "#f59e0b"
        left_scenario_bg = "rgba(245,158,11,0.08)"
        left_scenario_border = "#f59e0b25"
    else:
        left_scenario_title = "⛔ STATUS"
        left_scenario_color = "#94a3b8"
        left_scenario_bg = "rgba(148,163,184,0.08)"
        left_scenario_border = "#94a3b825"
    
    def scenario_price(value):
        try:
            value = float(value)
            return format_price(value) if value > 0 else "-"
        except (TypeError, ValueError):
            return "-"
    
    def scenario_pct(value, force_plus=False):
        try:
            value = float(value)
            if value == 0:
                return "-"
            return f"{value:+.1f}%" if force_plus else f"{value:.1f}%"
        except (TypeError, ValueError):
            return "-"
    
    step1_price_text = scenario_price(item.get("step1_price", 0))
    step1_gain_text = scenario_pct(item.get("step1_gain", 0), force_plus=True)
    fail_price_text = scenario_price(item.get("fail_price", 0))
    fail_loss_text = scenario_pct(item.get("fail_loss", 0))
    
    # Confluence checklist HTML
    confluence_passed = item.get("confluence_passed", 0)
    confluence_label = item.get("confluence_label", "INVALID 0/5")
    confluence_strength = item.get("confluence_strength", "TOLAK")
    confluence_checks = item.get("confluence_checks", {})
    
    if confluence_label.startswith("VALID 5/5") or confluence_label.startswith("VALID 4/5"):
        conf_color = "#10b981"
    elif confluence_label.startswith("VALID 3/5"):
        conf_color = "#f59e0b"
    else:
        conf_color = "#ef4444"
    
    checklist_html = ""
    for label, ok in confluence_checks.items():
        icon = "🟢" if ok else "🔴"
        style = "color:#22c55e;font-weight:700" if ok else "color:#94a3b8"
        checklist_html += (
            f'<div style="display:flex;justify-content:space-between;font-size:0.75rem;padding:0.15rem 0.3rem">'
            f'<span style="{style}">{icon} {label}</span>'
            f'<span style="font-weight:bold;{style}">{"VALID" if ok else "TOLAK"}</span>'
            f'</div>'
        )
        
    st.markdown(
        dedent(f"""
        <div class="rekomendasi-card" style="margin-bottom:0.8rem">
            <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:0.5rem">
                <div style="display:flex;align-items:center;gap:0.6rem">
                    <span style="font-size:1.8rem">{item['emoji']}</span>
                    <div>
                        <span style="font-size:1.3rem;font-weight:900;color:white">{item['symbol']}</span>
                        <span style="font-size:0.7rem;color:#666;margin-left:0.4rem">{item['category']}</span>
                    </div>
                </div>
                <div style="display:flex;align-items:center;gap:0.8rem;flex-wrap:wrap">
                    <span class="price-tag">{format_price(item['price'])}</span>
                    <span class="{'profit-badge' if item['change']>=0 else 'loss-badge'}">{change_sign}{item['change']:.2f}%</span>
                </div>
            </div>
            <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(110px,1fr));gap:0.4rem;margin-top:0.8rem;text-align:center">
                <div style="background:rgba(255,255,255,0.06);border-radius:10px;padding:0.5rem 0.3rem"><span style="color:#aaa;font-size:0.65rem;text-transform:uppercase;letter-spacing:0.05em">Score</span><br><span style="font-weight:900;font-size:1.1rem;color:#10b981">{item['score']}/100</span></div>
                <div style="background:rgba(255,255,255,0.06);border-radius:10px;padding:0.5rem 0.3rem"><span style="color:#aaa;font-size:0.65rem;text-transform:uppercase;letter-spacing:0.05em">Risk</span><br><span style="font-weight:700;font-size:0.9rem;color:{'#ef4444' if item['risk_level']=='TINGGI' else '#f59e0b' if item['risk_level']=='SEDANG' else '#22c55e'}">{item['risk_level']}</span></div>
                <div style="background:rgba(255,255,255,0.06);border-radius:10px;padding:0.5rem 0.3rem"><span style="color:#aaa;font-size:0.65rem;text-transform:uppercase;letter-spacing:0.05em">Alokasi</span><br><span style="font-weight:900;font-size:1rem;color:#fbbf24">{item['allocation_pct']:.1f}%</span></div>
                <div style="background:rgba(255,255,255,0.06);border-radius:10px;padding:0.5rem 0.3rem"><span style="color:#aaa;font-size:0.65rem;text-transform:uppercase;letter-spacing:0.05em">TP1</span><br><span style="font-weight:700;font-size:0.85rem;color:#22c55e">{format_price(item['tp1'])}</span></div>
                <div style="background:rgba(255,255,255,0.06);border-radius:10px;padding:0.5rem 0.3rem"><span style="color:#aaa;font-size:0.65rem;text-transform:uppercase;letter-spacing:0.05em">TP2</span><br><span style="font-weight:700;font-size:0.85rem;color:#22c55e">{format_price(item['tp2'])}</span></div>
                <div style="background:rgba(255,255,255,0.06);border-radius:10px;padding:0.5rem 0.3rem"><span style="color:#aaa;font-size:0.65rem;text-transform:uppercase;letter-spacing:0.05em">Target</span><br><span style="font-weight:700;font-size:0.85rem;color:#22c55e">{format_price(item['target'])}</span></div>
                <div style="background:rgba(255,255,255,0.06);border-radius:10px;padding:0.5rem 0.3rem"><span style="color:#aaa;font-size:0.65rem;text-transform:uppercase;letter-spacing:0.05em">Stop Loss</span><br><span style="font-weight:700;font-size:0.85rem;color:#ef4444">{format_price(item['stop_loss'])}</span></div>
                <div style="background:rgba(255,255,255,0.06);border-radius:10px;padding:0.5rem 0.3rem"><span style="color:#aaa;font-size:0.65rem;text-transform:uppercase;letter-spacing:0.05em">Trailing</span><br><span style="font-weight:700;font-size:0.85rem;color:#f59e0b">{item['trailing_stop_pct']:.1f}%</span></div>
            </div>
            <!-- ENTRY ZONE -->
            <div style="margin-top:0.6rem;padding:0.5rem;background:rgba(255,255,255,0.04);border-radius:12px;border:1px solid {entry_color}30">
                <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:0.3rem">
                    <span style="font-size:0.75rem;color:#aaa;text-transform:uppercase;letter-spacing:0.05em">🎯 Entry Zone</span>
                    <span style="font-size:0.85rem;font-weight:700;color:{entry_color}">{item.get('entry_zone_label', '⚖️ Netral')}</span>
                </div>
                <div style="display:flex;justify-content:space-between;margin-top:0.2rem">
                    <span style="font-size:0.8rem;color:#22c55e">⬇️ {format_price(item.get('entry_zone_low', 0))}</span>
                    <span style="font-size:0.8rem;color:#f59e0b">⟷</span>
                    <span style="font-size:0.8rem;color:#ef4444">⬆️ {format_price(item.get('entry_zone_high', 0))}</span>
                </div>
            </div>
            <!-- TWO STEPS AHEAD -->
            <div style="margin-top:0.5rem;display:grid;grid-template-columns:1fr 1fr;gap:0.4rem">
                <div style="background:{left_scenario_bg};border-radius:10px;padding:0.4rem;text-align:center;border:1px solid {left_scenario_border}">
                    <div style="font-size:0.65rem;color:{left_scenario_color};font-weight:700">{left_scenario_title}</div>
                    <div style="font-size:0.75rem;color:#ccc;margin-top:0.15rem">{item.get('step1_action', '⏳')}</div>
                    <div style="font-size:0.85rem;font-weight:800;color:{left_scenario_color}">{step1_price_text}</div>
                    <div style="font-size:0.7rem;color:{left_scenario_color}">{step1_gain_text}</div>
                </div>
                <div style="background:rgba(239,68,68,0.08);border-radius:10px;padding:0.4rem;text-align:center;border:1px solid #ef444420">
                    <div style="font-size:0.65rem;color:#ef4444;font-weight:700">❌ SKENARIO BEARISH</div>
                    <div style="font-size:0.75rem;color:#ccc;margin-top:0.15rem">{item.get('fail_action', '⛔')}</div>
                    <div style="font-size:0.85rem;font-weight:800;color:#ef4444">{fail_price_text}</div>
                    <div style="font-size:0.7rem;color:#ef4444">{fail_loss_text}</div>
                </div>
            </div>
            <!-- CONFLUENCE GATE CHECKLIST -->
            <div style="margin-top:0.6rem;padding:0.5rem;background:rgba(255,255,255,0.03);border-radius:12px;border:1px solid {conf_color}30">
                <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:0.3rem">
                    <span style="font-size:0.75rem;color:#aaa;text-transform:uppercase;letter-spacing:0.05em">🛡️ Confluence Gate</span>
                    <span style="font-size:0.8rem;font-weight:900;color:{conf_color};background:{conf_color}15;padding:0.15rem 0.5rem;border-radius:6px">{confluence_label}</span>
                </div>
                <div style="display:flex;flex-direction:column;gap:0.15rem;background:rgba(0,0,0,0.15);border-radius:8px;padding:0.3rem">
                    {checklist_html}
                </div>
            </div>
            <div style="margin-top:0.8rem;text-align:center">
                <a href="{buy_link}" target="_blank" class="{cta_class}">{cta_text}</a>
            </div>
        </div>
        """).strip(),
        unsafe_allow_html=True,
    )



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
        render_rekomendasi_card(item, i)


def render_fomo_alerts(tickers, prices_24h):
    fomo_gila, fomo, pumping = _bot_detect_fomo(tickers, prices_24h)
    if not fomo_gila and not fomo and not pumping:
        return
    st.markdown("## 🚨 FOMO Alert")
    if fomo_gila:
        st.markdown("### 🚀 FOMO Gila (>15%)")
        cols = st.columns(min(len(fomo_gila), 4))
        for i, coin in enumerate(fomo_gila[:4]):
            with cols[i]:
                pair_upper = coin["pair"].upper().replace("_", "")
                link = f"https://indodax.com/market/{pair_upper}?ref=narwanpratanta"
                st.markdown(
                    f"""<div class="fomo-card" style="border-color:#ef4444;background:#ef444410">
                        <div style="font-size:1.5rem;font-weight:900;color:#ef4444">+{coin['change']}%</div>
                        <div style="font-weight:800;font-size:1.1rem">{coin['symbol']}</div>
                        <div style="font-size:0.85rem;color:#888">{format_price(coin['price'])}</div>
                        <div style="font-size:0.75rem;color:#666">Vol: {format_idr(coin['vol_idr'])}</div>
                        <a href="{link}" target="_blank" style="display:inline-block;margin-top:0.4rem;background:#ef4444;color:white;padding:4px 14px;border-radius:8px;text-decoration:none;font-weight:700;font-size:0.8rem">⚠️ Pantau</a>
                    </div>""",
                    unsafe_allow_html=True,
                )
    if fomo:
        st.markdown("### 🔥 FOMO (>8%)")
        cols = st.columns(min(len(fomo), 4))
        for i, coin in enumerate(fomo[:4]):
            with cols[i]:
                pair_upper = coin["pair"].upper().replace("_", "")
                link = f"https://indodax.com/market/{pair_upper}?ref=narwanpratanta"
                st.markdown(
                    f"""<div class="fomo-card" style="border-color:#f59e0b;background:#f59e0b10">
                        <div style="font-size:1.3rem;font-weight:900;color:#f59e0b">+{coin['change']}%</div>
                        <div style="font-weight:800;font-size:1rem">{coin['symbol']}</div>
                        <div style="font-size:0.8rem;color:#888">{format_price(coin['price'])}</div>
                        <a href="{link}" target="_blank" style="display:inline-block;margin-top:0.3rem;background:#f59e0b;color:white;padding:3px 12px;border-radius:8px;text-decoration:none;font-weight:700;font-size:0.75rem">⚠️ Pantau</a>
                    </div>""",
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
                <p>© 2025 Rekomendasi Beli Crypto · Data dari Indodax</p>
            </div>
            """,
            unsafe_allow_html=True,
        )


# =============================================================================
# MAIN APP
# =============================================================================
def main():
    # --- AUTO REFRESH ---
    # Refresh otomatis setiap 60 detik
    st.markdown(
        f"""
        <meta http-equiv="refresh" content="60">
        <div style="display:none">autorefresh</div>
        """,
        unsafe_allow_html=True,
    )
    
    render_header()
    
    # --- REFRESH BUTTON & TIMER ---
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        if st.button("Refresh Data Sekarang", use_container_width=True, type="primary"):
            st.cache_data.clear()
            st.rerun()
    
    loading_placeholder = st.empty()
    loading_placeholder.markdown(loading_markup(), unsafe_allow_html=True)
    tickers, prices_24h, server_time, error = fetch_all_ticker_data()
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
    st.markdown(
        f"""<div style="display:flex;justify-content:center;margin-bottom:0.5rem">
            <div class="freshness-badge">
                <span class="freshness-dot {freshness}"></span>
                <span>{freshness_text} · {time_str}</span>
                <span style="margin-left:8px;font-size:0.7rem;color:#666">Auto-refresh tiap 60 detik</span>
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
    render_fomo_alerts(tickers, prices_24h)

    tab1, tab2, tab3, tab4, tab5 = st.tabs(["Rekomendasi Beli", "Semua Aset", "Micin/Meme", "Analisis Detail", "Tanya AI Advisor"])
    with tab1:
        render_rekomendasi_list(all_results, "Rekomendasi Beli Hari Ini", max_items=20)
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
        api_key = get_secret("DEEPSEEK_API_KEY", "")
        
        if not api_key:
            st.warning("⚠️ **DEEPSEEK_API_KEY tidak ditemukan.** Pastikan Anda telah memasang API Key di Hugging Face Space Secrets.")
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
                
                # Panggil DeepSeek API dengan context market
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
                            
                            context_str += "- Rekomendasi Teratas:\n"
                            for c in top_picks:
                                context_str += f"  * {c['symbol']}: Harga {format_price(c['price'])} ({c['change']:+.2f}%), Score: {c['score']}/100, Rekomendasi: {c['action']}, Target: {format_price(c['target'])}, SL: {format_price(c['stop_loss'])}\n"
                            
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
                            client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")
                            response = client.chat.completions.create(
                                model="deepseek-chat",
                                messages=api_messages,
                                temperature=0.7,
                                max_tokens=1000
                            )
                            
                            ai_response = response.choices[0].message.content
                            st.markdown(ai_response)
                            st.session_state.messages.append({"role": "assistant", "content": ai_response})
                            
                        except Exception as e:
                            st.error(f"Gagal menghubungi AI Advisor: {e}")
    render_donation()
    render_footer()


if __name__ == "__main__":
    main()


