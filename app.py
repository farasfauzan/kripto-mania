import os
import threading
import time
from datetime import datetime, timedelta, timezone

import pandas as pd
import requests
import streamlit as st
import streamlit.components.v1 as components
from openai import OpenAI

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
    # Layer 1
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
    # Layer 2
    "MATIC": "Layer2", "ARB": "Layer2", "OP": "Layer2", "IMX": "Layer2", "LRC": "Layer2",
    "MANTA": "Layer2", "STRK": "Layer2", "METIS": "Layer2", "SKL": "Layer2", "CELO": "Layer2",
    "BOBA": "Layer2", "ZKSYNC": "Layer2", "SCROLL": "Layer2", "LINEA": "Layer2", "BLAST": "Layer2",
    "MODE": "Layer2", "ZORA": "Layer2", "FUEL": "Layer2", "ALT": "Layer1", "ALTLAYER": "Layer1",
    # DeFi
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
    # AI
    "FET": "AI", "RNDR": "AI", "TAO": "AI", "GRT": "AI", "AKT": "AI",
    "WLD": "AI", "AGIX": "AI", "OCEAN": "AI", "PRIME": "AI", "AIOZ": "AI",
    "ARKM": "AI", "AITECH": "AI", "PAAL": "AI", "AGI": "AI", "OLAS": "AI",
    "NMR": "AI", "CTXC": "AI", "MDT": "AI", "VAI": "AI", "VIRTUALS": "AI",
    "AI": "AI", "AIXBT": "AI", "NFP": "AI", "CGPT": "AI", "IDX": "AI",
    # Gaming
    "IMX": "Gaming", "GALA": "Gaming", "AXS": "Gaming", "SAND": "Gaming", "MANA": "Gaming",
    "ENJ": "Gaming", "ILV": "Gaming", "MAGIC": "Gaming", "APE": "Gaming", "YGG": "Gaming",
    "PRIME": "Gaming", "PIXEL": "Gaming", "PORTAL": "Gaming", "BIGTIME": "Gaming", "WEMIX": "Gaming",
    "TLM": "Gaming", "VOXEL": "Gaming", "DAR": "Gaming", "SHRAP": "Gaming", "MYRIA": "Gaming",
    "NAKA": "Gaming", "BEAM": "Gaming", "RON": "Gaming", "SUPER": "Gaming", "MAVIA": "Gaming",
    "XAI": "Gaming", "ACE": "Gaming", "NYAN": "Gaming", "GAMEE": "Gaming", "PLYA": "Gaming",
    # RWA
    "ONDO": "RWA", "MKR": "RWA", "CFG": "RWA", "PENDLE": "RWA", "RIO": "RWA",
    "TRU": "RWA", "SNX": "RWA", "MPL": "RWA", "GFI": "RWA", "PRO": "RWA",
    "FACTR": "RWA", "DOVA": "RWA", "CHEX": "RWA", "LAND": "RWA", "TOKEN": "RWA",
    # Stablecoin
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
    "tickers": None,       # raw tickers dict
    "fetched_at": None,     # datetime when fetched
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
# 🤖 TELEGRAM BOT DAEMON — background thread untuk sinyal + FOMO alert
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

def _bot_split_text(text, max_len=TELEGRAM_MAX_LENGTH):
    """Split long message agar tidak melebihi batas Telegram."""
    if len(text) <= max_len:
        return [text]
    # Split on double newline boundaries when possible
    chunks = []
    while len(text) > max_len:
        # Cari titik potong terbaik: akhir baris terdekat sebelum max_len
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
    """Kirim pesan ke Telegram dengan Markdown fallback + auto-split pesan panjang."""
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
            time.sleep(0.3)  # Rate limit gentle gap
    return all_ok

def _bot_format_idr(value):
    """Short Rupiah formatter untuk pesan Telegram (compact)."""
    if value is None:
        return "-"
    if value >= 1_000_000:
        return f"Rp{value/1_000_000:,.1f}JT"
    if value >= 1_000:
        return f"Rp{value:,.0f}"
    return f"Rp{value:,.2f}"

def _bot_format_sinyal_harian(signals):
    buy_signals = [s for s in signals if "BELI" in s["action"]]
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
        if "BELI" in action:
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
        "🟢 BELI KUAT": 0,
        "🟡 CICIL BELI": 1,
        "⚪ WATCH": 2,
        "🔴 JANGAN BELI": 3,
        "⛔ HINDARI": 4,
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

def _bot_detect_fomo(raw_tickers):
    fomo_gila, fomo, pumping = [], [], []
    for pair, info in raw_tickers.items():
        if not pair.endswith("_idr"):
            continue
        try:
            change = float(info.get("change", 0) or 0)
            price = float(info["last"])
            vol = float(info.get("vol_idr", 0))
        except (KeyError, ValueError):
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

def _telegram_bot_daemon():
    """Background daemon: sinyal harian jam 8 pagi + FOMO check tiap 2 menit.
    Shares raw ticker data ke st.session_state agar UI tidak perlu fetch ulang."""
    import time as _time
    last_sinyal_date = None
    fomo_sent = {}
    consecutive_errors = 0

    # Kirim notifikasi bot aktif
    _bot_send_message("🤖 *Bot Radar Aktif (24/7)*\nMemantau market Indodax... 🚀")

    cycle = 0
    while True:
        try:
            cycle += 1
            resp = requests.get("https://indodax.com/api/tickers", timeout=10)
            tickers = resp.json().get("tickers", {})

            if not tickers:
                consecutive_errors += 1
                wait = min(30, consecutive_errors * 5)  # Backoff: 5, 10, 15, 20, 25, 30s
                _time.sleep(wait)
                continue

            consecutive_errors = 0
            now = datetime.now(BOT_WIB)
            today = now.strftime("%Y-%m-%d")

            # SHARE: Simpan raw tickers ke global variable (thread-safe)
            try:
                _write_shared_tickers(tickers)
            except Exception:
                pass

            # 1. Sinyal harian jam 8 pagi (check pas jam 8-9)
            if 8 <= now.hour <= 9 and last_sinyal_date != today:
                prices = {}
                for sym, pair in BOT_MAIN_ASSETS.items():
                    if pair in tickers:
                        try:
                            prices[sym] = {
                                "price": float(tickers[pair]["last"]),
                                "high": float(tickers[pair].get("high", 0)),
                                "low": float(tickers[pair].get("low", 0)),
                                "vol_idr": float(tickers[pair].get("vol_idr", 0)),
                                "change": float(tickers[pair].get("change", 0) or 0),
                            }
                        except (KeyError, ValueError):
                            pass
                if prices:
                    signals = _bot_generate_signal(prices)
                    msg = _bot_format_sinyal_harian(signals)
                    if msg:
                        if _bot_send_message(msg):
                            last_sinyal_date = today
                    else:
                        last_sinyal_date = today

            # 2. FOMO check
            fomo_gila, fomo, pumping = _bot_detect_fomo(tickers)
            total = len(fomo_gila) + len(fomo) + len(pumping)
            if total > 0:
                now_ts = _time.time()
                new_alerts = {}
                for lst in [fomo_gila, fomo, pumping]:
                    for coin in lst:
                        sym = coin["symbol"]
                        change = coin["change"]
                        if sym in fomo_sent:
                            if change >= fomo_sent[sym]["change"] + 5.0:
                                new_alerts[sym] = coin
                        else:
                            new_alerts[sym] = coin

                # Cleanup > 6 jam
                fomo_sent = {k: v for k, v in fomo_sent.items() if now_ts - v.get("_sent_at", 0) < 21600}

                if new_alerts:
                    new_gila = [v for v in new_alerts.values() if v["change"] > 15]
                    new_fomo = [v for v in new_alerts.values() if 8 < v["change"] <= 15]
                    new_pump = [v for v in new_alerts.values() if 5 < v["change"] <= 8]
                    new_gila.sort(key=lambda x: x["change"], reverse=True)
                    new_fomo.sort(key=lambda x: x["change"], reverse=True)
                    new_pump.sort(key=lambda x: x["change"], reverse=True)
                    fomo_msg = _bot_format_fomo_alert(new_gila, new_fomo, new_pump)
                    if fomo_msg and _bot_send_message(fomo_msg, alert=True):
                        for sym, coin in new_alerts.items():
                            coin["_sent_at"] = now_ts
                            fomo_sent[sym] = coin

            # Tidur 2 menit
            _time.sleep(120)

        except Exception:
            consecutive_errors += 1
            backoff = min(120, 10 * (2 ** min(consecutive_errors - 1, 4)))  # 10, 20, 40, 80, 120s
            _time.sleep(backoff)


def start_telegram_bot():
    """Start Telegram bot daemon thread (hanya sekali)."""
    if not BOT_ENABLED or not BOT_TOKEN or not BOT_CHAT_ID:
        st.session_state.telegram_bot_started = False
        return
    if not st.session_state.get("telegram_bot_started"):
        st.session_state.telegram_bot_started = True
        t = threading.Thread(target=_telegram_bot_daemon, daemon=True, name="telegram-bot")
        t.start()


start_telegram_bot()

# =============================================================================
# STYLING — SOFT LIGHT SHELL + DARK TRADING CARDS
# =============================================================================
st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800;900&display=swap');
    @import url('https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css');

    * { font-family: 'Plus Jakarta Sans', sans-serif !important; }

    .stApp {
        background: linear-gradient(180deg, #f8fafc 0%, #eef4ff 48%, #e8f7ef 100%);
        color: #0f172a;
    }

    .block-container {
        padding-top: 1.4rem;
    }

    /* === BUTTONS === */
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
    .buy-button-sm:hover {
        background: #16a34a;
        transform: scale(1.04);
    }

    /* === HERO CARD === */
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

    /* === SUB CARDS === */
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

    /* === BADGES === */
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

    /* === SIDEBAR === */
    section[data-testid="stSidebar"] {
        background-color: #ffffff !important;
        border-right: 1px solid #dbeafe;
    }

    /* === HEADERS === */
    h1 { font-size: 2.6rem !important; font-weight: 900 !important; text-align: center; }
    h2 { font-weight: 800 !important; }
    h3 { font-weight: 700 !important; }

    /* === STAT CARDS === */
    .stat-card {
        background: #111;
        border: 1px solid #222;
        border-radius: 16px;
        padding: 1rem;
        text-align: center;
    }
    .stat-value {
        font-size: 1.5rem;
        font-weight: 900;
    }
    .stat-label {
        font-size: 0.75rem;
        color: #888;
        text-transform: uppercase;
        letter-spacing: 0.1em;
        margin-top: 4px;
    }

    /* === AD BANNER === */
    .ad-banner {
        background: linear-gradient(135deg, #1a1a2e, #16213e);
        border: 1px solid #2a2a4a;
        border-radius: 16px;
        padding: 1rem 1.5rem;
        text-align: center;
    }

    /* === PRO CARD === */
    .pro-card {
        background: linear-gradient(135deg, #1e1b4b, #312e81);
        border: 2px solid #6366f1;
        border-radius: 20px;
        padding: 2rem;
        text-align: center;
    }

    /* === TABLES */
    .stDataFrame {
        border: 1px solid #dbeafe !important;
        border-radius: 14px !important;
    }

    /* === TABS === */
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
        background-color: transparent;
    }
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

    /* === METRIC CARDS (Streamlit) === */
    [data-testid="stMetricValue"] {
        font-weight: 900 !important;
    }

    /* === DIVIDER === */
    hr {
        border-color: #dbeafe !important;
    }

    /* === TOOLTIP / COPY === */
    .wallet-text {
        font-family: 'Courier New', monospace;
        font-size: 0.65rem;
        word-break: break-all;
        color: #666;
    }

    /* === FRESHNESS BADGE === */
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

    /* === LOADING SCREEN === */
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
    @keyframes loaderSpin {
        to { transform: rotate(360deg); }
    }
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
        .app-loading-ring,
        .app-loading-bars span {
            animation: none;
        }
    }

    @keyframes pulse {
        0%, 100% { opacity: 1; }
        50% { opacity: 0.4; }
    }

    /* === FOMO CARDS === */
    .fomo-card {
        border-radius: 16px;
        padding: 1.2rem 0.8rem;
        text-align: center;
        margin-bottom: 0.5rem;
        border: 2px solid #fbbf24;
    }

    /* === MOBILE RESPONSIVENESS === */
    @media (max-width: 768px) {
        h1 { font-size: 1.6rem !important; }
        .price-tag { font-size: 1.5rem; }
        .buy-button { padding: 12px 28px; font-size: 1rem; }
        .rekomendasi-hero { padding: 1.5rem 1rem; }
    }

    /* === STREAMLIT OVERRIDES === */
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


loading_placeholder = st.empty()
loading_placeholder.markdown(loading_markup(), unsafe_allow_html=True)

# =============================================================================
# DATA ENGINE — SINGLE API CALL FOR EVERYTHING
# =============================================================================
def fetch_all_data():
    """
    Single API call to fetch ALL tickers.
    Returns: (grouped_prices, all_tickers_raw, status)
    """
    grouped = {"main": {}, "micin": {}}
    all_tickers = {}
    status = {"source": "loading", "server_time": None, "error": None}

    try:
        response = requests.get("https://indodax.com/api/tickers", timeout=5.0)
        response.raise_for_status()
        tickers = response.json().get("tickers", {})

        if not tickers:
            raise ValueError("Empty tickers response")

        for pair, info in tickers.items():
            try:
                parsed = {
                    "pair": pair,
                    "price": float(info["last"]),
                    "high": float(info.get("high", 0)),
                    "low": float(info.get("low", 0)),
                    "vol_idr": float(info.get("vol_idr", 0)),
                    "change_pct": float(info.get("change", 0) or 0),
                }
                all_tickers[pair] = parsed
                status["server_time"] = info.get("server_time", status["server_time"])
            except (KeyError, ValueError, TypeError):
                continue

        # Populate grouped for known MAIN_ASSETS
        for symbol, (pair, _) in MAIN_ASSETS.items():
            if pair in all_tickers:
                grouped["main"][symbol] = all_tickers[pair]

        # Populate grouped for known MICIN_ASSETS
        for symbol, (pair, _) in MICIN_ASSETS.items():
            if pair in all_tickers:
                grouped["micin"][symbol] = all_tickers[pair]

        status["source"] = "live"

    except requests.exceptions.Timeout:
        status = {"source": "offline", "server_time": None, "error": "API timeout — server Indodax lambat merespon"}
    except requests.exceptions.ConnectionError:
        status = {"source": "offline", "server_time": None, "error": "Gagal koneksi — periksa internet kamu"}
    except Exception as exc:
        status = {"source": "offline", "server_time": None, "error": str(exc)}

    return grouped, all_tickers, status


@st.cache_data(ttl=900, show_spinner=False)
def fetch_ohlc_history(pair_id, tf="60", lookback_days=21):
    """Ambil candle historis Indodax untuk indikator teknikal."""
    end_ts = int(time.time())
    start_ts = end_ts - lookback_days * 24 * 60 * 60
    symbol = pair_id.replace("_", "").upper()
    url = "https://indodax.com/tradingview/history_v2"
    params = {"from": start_ts, "to": end_ts, "tf": tf, "symbol": symbol}

    try:
        response = requests.get(url, params=params, timeout=6.0)
        response.raise_for_status()
        rows = response.json()
    except (requests.RequestException, ValueError, TypeError):
        return pd.DataFrame()

    if not isinstance(rows, list):
        return pd.DataFrame()

    candles = pd.DataFrame(rows)
    if candles.empty:
        return candles

    rename_map = {
        "Time": "time",
        "Open": "open",
        "High": "high",
        "Low": "low",
        "Close": "close",
        "Volume": "volume",
    }
    candles = candles.rename(columns=rename_map)
    required = ["time", "open", "high", "low", "close", "volume"]
    if not all(col in candles.columns for col in required):
        return pd.DataFrame()

    for col in required:
        candles[col] = pd.to_numeric(candles[col], errors="coerce")
    candles = candles.dropna(subset=["time", "open", "high", "low", "close"]).sort_values("time")
    return candles.tail(500).reset_index(drop=True)


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================
def format_idr(value):
    """Format number ke Rupiah dengan suffix yang tepat."""
    if value is None:
        return "-"
    try:
        value = float(value)
    except (TypeError, ValueError):
        return "-"
    sign = "-" if value < 0 else ""
    value = abs(value)
    if value >= 1_000_000_000:
        return f"{sign}Rp{value/1_000_000_000:,.2f} M"
    if value >= 1_000_000:
        return f"{sign}Rp{value/1_000_000:,.1f} JT"
    if value >= 1_000:
        return f"{sign}Rp{value:,.0f}"
    if value >= 1:
        return f"{sign}Rp{value:,.2f}"
    return f"{sign}Rp{value:,.6f}"


def format_volume(value):
    """Format volume ke format yang readable."""
    if value is None:
        return "-"
    if value >= 1_000_000_000_000:
        return f"Rp{value/1_000_000_000_000:,.1f} T"
    if value >= 1_000_000_000:
        return f"Rp{value/1_000_000_000:,.1f} M"
    if value >= 1_000_000:
        return f"Rp{value/1_000_000:,.1f} JT"
    return f"Rp{value:,.0f}"


def clamp(value, lower, upper):
    return max(lower, min(upper, value))


def build_trade_link(symbol):
    pair = ALL_ASSETS.get(symbol, (f"{symbol.lower()}_idr", ""))[0]
    pair_url = pair.upper().replace("_", "")
    return f"https://indodax.com/market/{pair_url}?ref=narwanpratanta"


def get_paper_trades():
    if "paper_trades" not in st.session_state:
        st.session_state.paper_trades = []
    return st.session_state.paper_trades


def has_open_paper_trade(symbol):
    return any(
        trade.get("symbol") == symbol and trade.get("status") == "OPEN"
        for trade in get_paper_trades()
    )


def compute_paper_risk_guard(trades):
    """Freqtrade-lite guard: cegah paper trade berlebihan saat performa sedang buruk."""
    today = datetime.now().strftime("%Y-%m-%d")
    open_trades = [t for t in trades if t.get("status") == "OPEN"]
    closed = [t for t in trades if t.get("status") == "CLOSED"]
    open_exposure = sum(float(t.get("size_pct", 0) or 0) for t in open_trades)
    today_realized = sum(
        float(t.get("pnl_1jt", 0) or 0)
        for t in closed
        if str(t.get("closed_at", "")).startswith(today)
    )

    consecutive_losses = 0
    for trade in reversed(closed):
        if float(trade.get("pnl_pct", 0) or 0) < 0:
            consecutive_losses += 1
        elif float(trade.get("pnl_pct", 0) or 0) > 0:
            break

    reasons = []
    if len(open_trades) >= 4:
        reasons.append("maksimal 4 posisi terbuka")
    if open_exposure >= 18:
        reasons.append("eksposur paper sudah >=18%")
    if today_realized <= -25_000:
        reasons.append("daily loss guard aktif")
    if consecutive_losses >= 3:
        reasons.append("cooldown setelah 3 loss beruntun")

    return {
        "allowed": not reasons,
        "status": "LOCKED" if reasons else "OK",
        "reason": " • ".join(reasons) if reasons else "Risk guard aman.",
        "open_count": len(open_trades),
        "open_exposure": round(open_exposure, 2),
        "today_realized": round(today_realized, 0),
        "consecutive_losses": consecutive_losses,
    }


def add_paper_trade_from_signal(row):
    trades = get_paper_trades()
    symbol = row["symbol"]
    if has_open_paper_trade(symbol):
        return False, f"{symbol} sudah punya paper trade aktif."

    guard = compute_paper_risk_guard(trades)
    if not guard["allowed"]:
        return False, f"Risk guard aktif: {guard['reason']}"

    entry_price = float(row.get("price", 0) or 0)
    if entry_price <= 0:
        return False, "Harga entry belum valid."

    size_pct = float(row.get("allocation_pct", 0) or 0)
    if size_pct <= 0:
        size_pct = 1.0

    trade = {
        "id": f"{symbol}-{datetime.now().strftime('%Y%m%d%H%M%S')}",
        "symbol": symbol,
        "status": "OPEN",
        "stage": "ENTRY",
        "entry_price": entry_price,
        "current_price": entry_price,
        "highest_price": entry_price,
        "size_pct": round(size_pct, 2),
        "opened_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "closed_at": None,
        "exit_price": None,
        "exit_reason": None,
        "pnl_pct": 0.0,
        "pnl_1jt": 0.0,
        "tp1": float(row.get("take_profit_1", entry_price) or entry_price),
        "tp2": float(row.get("take_profit_2", entry_price) or entry_price),
        "tp3": float(row.get("take_profit_3", row.get("target_price", entry_price)) or entry_price),
        "stop_loss": float(row.get("stop_loss", entry_price * 0.97) or entry_price * 0.97),
        "trailing_stop_pct": float(row.get("trailing_stop_pct", 3.0) or 3.0),
        "score": int(row.get("score", 0) or 0),
        "agent_verdict": row.get("agent_verdict", "-"),
        "agent_net_score": int(row.get("agent_net_score", 0) or 0),
        "strategy_mode": row.get("strategy_mode", "-"),
        "risk_level": row.get("risk_level", "-"),
    }
    trades.append(trade)
    st.session_state.paper_trades = trades[-120:]
    return True, f"{symbol} masuk paper trade."


def update_paper_trades(all_prices):
    trades = get_paper_trades()
    for trade in trades:
        if trade.get("status") != "OPEN":
            continue

        symbol = trade.get("symbol")
        current_price = float(all_prices.get(symbol, trade.get("current_price", 0)) or 0)
        if current_price <= 0:
            continue

        entry_price = float(trade.get("entry_price", current_price) or current_price)
        trade["current_price"] = current_price
        trade["highest_price"] = max(float(trade.get("highest_price", entry_price) or entry_price), current_price)
        trade["pnl_pct"] = round((current_price - entry_price) / entry_price * 100, 2) if entry_price > 0 else 0
        trade["pnl_1jt"] = round(1_000_000 * trade["size_pct"] / 100 * trade["pnl_pct"] / 100, 0)

        if current_price >= trade.get("tp1", entry_price) and trade.get("stage") == "ENTRY":
            trade["stage"] = "TP1 HIT"
        if current_price >= trade.get("tp2", entry_price) and trade.get("stage") in {"ENTRY", "TP1 HIT"}:
            trade["stage"] = "TP2 HIT"

        trailing_floor = trade["highest_price"] * (1 - float(trade.get("trailing_stop_pct", 3.0) or 3.0) / 100)
        should_trail = trade.get("stage") in {"TP1 HIT", "TP2 HIT"}

        if current_price <= trade.get("stop_loss", 0):
            trade["status"] = "CLOSED"
            trade["stage"] = "STOP HIT"
            trade["exit_reason"] = "STOP LOSS"
        elif current_price >= trade.get("tp3", entry_price):
            trade["status"] = "CLOSED"
            trade["stage"] = "TP3 HIT"
            trade["exit_reason"] = "TARGET HIT"
        elif should_trail and current_price <= trailing_floor:
            trade["status"] = "CLOSED"
            trade["stage"] = "TRAILING STOP"
            trade["exit_reason"] = "TRAILING STOP"

        if trade.get("status") == "CLOSED":
            trade["exit_price"] = current_price
            trade["closed_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            trade["pnl_pct"] = round((current_price - entry_price) / entry_price * 100, 2) if entry_price > 0 else 0
            trade["pnl_1jt"] = round(1_000_000 * trade["size_pct"] / 100 * trade["pnl_pct"] / 100, 0)

    st.session_state.paper_trades = trades
    return trades


def summarize_paper_trades(trades):
    closed = [t for t in trades if t.get("status") == "CLOSED"]
    open_trades = [t for t in trades if t.get("status") == "OPEN"]
    wins = [t for t in closed if t.get("pnl_pct", 0) > 0]
    losses = [t for t in closed if t.get("pnl_pct", 0) < 0]
    winrate = len(wins) / len(closed) * 100 if closed else 0
    avg_pnl = sum(t.get("pnl_pct", 0) for t in closed) / len(closed) if closed else 0
    realized = sum(t.get("pnl_1jt", 0) for t in closed)
    floating = sum(t.get("pnl_1jt", 0) for t in open_trades)
    gross_profit = sum(t.get("pnl_1jt", 0) for t in wins)
    gross_loss = abs(sum(t.get("pnl_1jt", 0) for t in losses))
    profit_factor = gross_profit / gross_loss if gross_loss else float(len(wins)) if wins else 0
    avg_win = sum(t.get("pnl_pct", 0) for t in wins) / len(wins) if wins else 0
    avg_loss = abs(sum(t.get("pnl_pct", 0) for t in losses) / len(losses)) if losses else 0
    expectancy = (winrate / 100 * avg_win) - ((100 - winrate) / 100 * avg_loss) if closed else 0

    equity = 0
    peak = 0
    max_drawdown = 0
    for trade in closed:
        equity += float(trade.get("pnl_1jt", 0) or 0)
        peak = max(peak, equity)
        max_drawdown = min(max_drawdown, equity - peak)

    guard = compute_paper_risk_guard(trades)
    return {
        "total": len(trades),
        "open": len(open_trades),
        "closed": len(closed),
        "wins": len(wins),
        "losses": len(losses),
        "winrate": round(winrate, 1),
        "avg_pnl": round(avg_pnl, 2),
        "profit_factor": round(profit_factor, 2),
        "expectancy": round(expectancy, 2),
        "max_drawdown": round(max_drawdown, 0),
        "realized": round(realized, 0),
        "floating": round(floating, 0),
        "guard": guard,
    }


def build_agentic_verdict(snapshot):
    """TradingAgents-lite: bull/bear/risk/portfolio committee tanpa dependency berat."""
    bull_points = []
    bear_points = []
    bull_score = 0
    bear_score = 0

    score = snapshot.get("score", 0)
    value_score = snapshot.get("value_score", 0)
    technical_score = snapshot.get("technical_score", 0)
    ml_probability = snapshot.get("ml_probability", 50)
    ml_confidence = snapshot.get("ml_confidence", "rendah")
    risk_reward = snapshot.get("risk_reward", 0)
    risk_level = snapshot.get("risk_level", "SEDANG")
    backtest_winrate = snapshot.get("backtest_winrate", 0)
    backtest_trades = snapshot.get("backtest_trades", 0)
    backtest_label = snapshot.get("backtest_label", "DATA KURANG")
    strategy_mode = snapshot.get("strategy_mode", "WATCH")
    trend_strength = snapshot.get("trend_strength", "sideways")
    bb_signal = snapshot.get("bb_signal", "netral")
    supertrend_bias = snapshot.get("supertrend_bias", "netral")
    atr_pct = snapshot.get("atr_pct", 0)
    lab_winrate = snapshot.get("lab_winrate", 0)
    lab_trades = snapshot.get("lab_trades", 0)
    rsi = snapshot.get("rsi", 50)
    daily_change = snapshot.get("daily_change", 0)
    range_position = snapshot.get("range_position", 50)
    volume_idr = snapshot.get("volume_idr", 0)
    category = snapshot.get("category", "")

    if score >= 75:
        bull_score += 18
        bull_points.append("score trading kuat")
    elif score >= 65:
        bull_score += 10
        bull_points.append("score cukup untuk entry kecil")
    else:
        bear_score += 8
        bear_points.append("score belum dominan")

    if value_score >= 70:
        bull_score += 12
        bull_points.append("value mendukung")
    elif value_score < 45:
        bear_score += 12
        bear_points.append("kualitas hold lemah")

    if technical_score >= 18:
        bull_score += 12
        bull_points.append("teknikal kompak")
    elif technical_score < 0:
        bear_score += 10
        bear_points.append("teknikal melemah")

    if ml_probability >= 62:
        bull_score += 12 if ml_confidence != "rendah" else 7
        bull_points.append(f"ML bullish {ml_probability:.1f}%")
    elif ml_probability <= 42:
        bear_score += 12 if ml_confidence != "rendah" else 7
        bear_points.append(f"ML bearish {ml_probability:.1f}%")

    if backtest_trades >= 10 and backtest_winrate >= 58:
        bull_score += 14
        bull_points.append(f"rapor candle {backtest_winrate:.1f}%")
    elif backtest_trades >= 10 and backtest_label == "LEMAH":
        bear_score += 16
        bear_points.append("rapor candle lemah")
    elif backtest_trades < 6:
        bear_score += 5
        bear_points.append("rapor historis minim")

    if risk_reward >= 1.25:
        bull_score += 8
        bull_points.append("risk/reward menarik")
    elif risk_reward < 0.9:
        bear_score += 9
        bear_points.append("risk/reward kurang enak")

    if trend_strength in {"bullish_strong", "bullish_moderate"}:
        bull_score += 7
        bull_points.append("trend bullish")
    elif trend_strength in {"bearish_strong", "bearish_moderate"}:
        bear_score += 9
        bear_points.append("trend bearish")

    if supertrend_bias == "bullish":
        bull_score += 7
        bull_points.append("Supertrend bullish")
    elif supertrend_bias == "bearish":
        bear_score += 9
        bear_points.append("Supertrend bearish")

    if lab_trades >= 8 and lab_winrate >= 56:
        bull_score += 7
        bull_points.append(f"strategy lab {lab_winrate:.1f}%")
    elif lab_trades >= 8 and lab_winrate < 45:
        bear_score += 7
        bear_points.append("strategy lab lemah")

    if bb_signal == "overbought" or rsi >= 78 or range_position >= 88:
        bear_score += 8
        bear_points.append("harga mulai panas")
    elif bb_signal in {"oversold", "low_range"} and 35 <= rsi <= 68:
        bull_score += 5
        bull_points.append("entry belum terlalu panas")

    if abs(daily_change) >= 12:
        bear_score += 10
        bear_points.append("volatilitas 24j ekstrem")
    if atr_pct >= 7:
        bear_score += 6
        bear_points.append("ATR terlalu liar")
    if volume_idr < 100_000_000:
        bear_score += 12
        bear_points.append("likuiditas tipis")
    elif volume_idr >= 5_000_000_000:
        bull_score += 5
        bull_points.append("likuiditas kuat")
    if category == "Meme":
        bear_score += 4
        bear_points.append("kategori spekulatif")

    net_score = int(clamp(50 + bull_score - bear_score, 0, 100))

    if risk_level == "TINGGI" or bear_score >= bull_score + 18:
        risk_decision = "REJECT"
        verdict = "DITOLAK RISK MANAGER"
        verdict_color = "#ef4444"
        size_multiplier = 0
        note = "Risiko lebih besar daripada alasan beli."
    elif bear_score >= bull_score + 5:
        risk_decision = "WAIT"
        verdict = "TUNGGU"
        verdict_color = "#f59e0b"
        size_multiplier = 0
        note = "Masih ada kontra yang perlu dibersihkan."
    elif risk_level == "SEDANG" or strategy_mode in {"SCALP ONLY", "TRADE KECIL"}:
        risk_decision = "SMALL SIZE"
        verdict = "APPROVE KECIL"
        verdict_color = "#f59e0b"
        size_multiplier = 0.55
        note = "Boleh, tapi ukuran posisi harus kecil."
    else:
        risk_decision = "APPROVE"
        verdict = "APPROVE"
        verdict_color = "#22c55e"
        size_multiplier = 1.0
        note = "Bull case lebih kuat dan risiko masih terkendali."

    if net_score < 48 and risk_decision != "REJECT":
        risk_decision = "WAIT"
        verdict = "TUNGGU"
        verdict_color = "#f59e0b"
        size_multiplier = 0
        note = "Committee belum cukup sepakat untuk entry."

    return {
        "agent_bull_score": bull_score,
        "agent_bear_score": bear_score,
        "agent_net_score": net_score,
        "agent_bull_case": " • ".join(bull_points[:4]) if bull_points else "belum ada bull case kuat",
        "agent_bear_case": " • ".join(bear_points[:4]) if bear_points else "kontra utama minim",
        "agent_risk_decision": risk_decision,
        "agent_verdict": verdict,
        "agent_verdict_color": verdict_color,
        "agent_size_multiplier": size_multiplier,
        "agent_note": note,
    }


def build_decision_board(recs_df, market_stats):
    if recs_df.empty:
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), "Tunggu data masuk dulu.", pd.DataFrame()

    board = recs_df.copy()
    risk_penalty = board["risk_level"].map({"RENDAH": 0, "SEDANG": 9, "TINGGI": 22}).fillna(12)
    backtest_winrate = board["backtest_winrate"] if "backtest_winrate" in board else pd.Series(50, index=board.index)
    backtest_trades = board["backtest_trades"] if "backtest_trades" in board else pd.Series(0, index=board.index)
    backtest_label = board["backtest_label"] if "backtest_label" in board else pd.Series("", index=board.index)
    backtest_bonus = ((backtest_winrate - 50) * 0.18).fillna(0)
    backtest_bonus = backtest_bonus.where(backtest_trades >= 6, 0)
    agent_net_score = board["agent_net_score"] if "agent_net_score" in board else pd.Series(50, index=board.index)
    agent_verdict = board["agent_verdict"] if "agent_verdict" in board else pd.Series("", index=board.index)
    agent_bonus = ((agent_net_score - 50) * 0.22).fillna(0)
    lab_winrate = board["lab_winrate"] if "lab_winrate" in board else pd.Series(50, index=board.index)
    lab_trades = board["lab_trades"] if "lab_trades" in board else pd.Series(0, index=board.index)
    lab_bonus = ((lab_winrate - 50) * 0.10).fillna(0).where(lab_trades >= 8, 0)
    ta_plus_score = board["ta_plus_score"] if "ta_plus_score" in board else pd.Series(0, index=board.index)
    mode_bonus = board["strategy_mode"].map({
        "SWING / HOLD": 10,
        "SCALP ONLY": 3,
        "TRADE KECIL": 1,
        "WATCH VALUE": -2,
        "WATCH": -8,
        "SKIP": -25,
    }).fillna(0)
    ml_bonus = ((board["ml_probability"] - 50) * 0.35).fillna(0)
    rr_bonus = board["risk_reward"].clip(0, 3).fillna(0) * 4
    board["decision_score"] = (
        board["score"] * 0.42
        + board["value_score"] * 0.18
        + board["technical_score"] * 0.18
        + ml_bonus
        + rr_bonus
        + backtest_bonus
        + agent_bonus
        + lab_bonus
        + ta_plus_score * 0.35
        + mode_bonus
        - risk_penalty
    ).round(1)

    clean_buy = board[
        (board["action"] == "buy")
        & (board["risk_level"] != "TINGGI")
        & ~((board["ml_label"] == "BEARISH") & (board["ml_confidence"] != "rendah"))
        & ~((backtest_label == "LEMAH") & (backtest_trades >= 10))
        & ~agent_verdict.isin(["DITOLAK RISK MANAGER", "TUNGGU"])
    ].sort_values(["decision_score", "risk_reward", "score"], ascending=False)

    quick_picks = clean_buy.head(3)
    backup_picks = board[
        (board["action"] == "buy")
        & ~board["symbol"].isin(set(quick_picks["symbol"]))
        & (board["risk_level"] != "TINGGI")
        & ~((backtest_label == "LEMAH") & (backtest_trades >= 10))
        & ~agent_verdict.isin(["DITOLAK RISK MANAGER", "TUNGGU"])
    ].sort_values(["decision_score", "score"], ascending=False).head(2)
    watch_picks = board[
        (board["action"] != "buy")
        & (board["value_score"] >= 55)
    ].sort_values(["value_score", "decision_score"], ascending=False).head(2)

    mode = market_stats.get("mode", "normal")
    if quick_picks.empty:
        message = "Belum ada coin yang cukup bersih. Lebih baik tunggu dan simpan modal."
    elif mode == "defensive":
        message = "Market defensif. Kalau tetap entry, ambil 1 coin saja dengan size kecil."
    elif len(quick_picks) == 1:
        message = "Ada 1 kandidat paling bersih. Jangan merasa wajib ambil coin lain."
    else:
        message = "Pilih maksimal 1 coin utama. Coin cadangan hanya dipakai kalau entry utama gagal."

    return quick_picks, backup_picks, watch_picks, message, board


def render_tradingview_widget(symbol, height=450):
    """Render TradingView advanced chart widget."""
    pair = ALL_ASSETS.get(symbol, (f"{symbol.lower()}_idr", ""))[0]
    pair_tv = pair.upper().replace("_", "")
    tv_id = f"tradingview_{pair_tv}"

    html_code = f"""
    <div class="tradingview-widget-container" style="height:{height}px;width:100%">
      <div id="{tv_id}" style="height:calc(100% - 32px);width:100%"></div>
      <script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script>
      <script type="text/javascript">
      new TradingView.widget({{
        "autosize": true,
        "symbol": "{pair_tv}",
        "interval": "60",
        "timezone": "Asia/Jakarta",
        "theme": "dark",
        "style": "1",
        "locale": "id",
        "toolbar_bg": "#f1f3f6",
        "enable_publishing": false,
        "hide_side_toolbar": false,
        "allow_symbol_change": true,
        "container_id": "{tv_id}"
      }});
      </script>
    </div>
    """
    components.html(html_code, height=height)


@st.cache_data(ttl=900, show_spinner=False)
def get_ai_market_narrative(symbol, label, score, market_mode, reason):
    """Ambil analisa naratif dari AI DeepSeek (Cached 15 menit)."""
    api_key = get_secret("DEEPSEEK_API_KEY")
    if not api_key:
        return "⚠️ *Hubungkan API Key DeepSeek di `secrets.toml` untuk mengaktifkan AI Narrator.*"

    try:
        client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")

        prompt = f"""
        Kamu adalah 'Bot Trader Gacor', asisten senior yang blak-blakan dan ahli.
        Analisis data koin ini dan berikan narasi singkat (3-4 kalimat) dalam Bahasa Indonesia yang 'hidup', santai tapi tajam.

        Koin: {symbol}
        Aksi: {label}
        Market: {market_mode}
        Skor: {score}/100
        Alasan: {reason}

        Berikan opini manusiawi, jangan seperti robot kaku. Fokus pada apakah ini momen emas atau harus hati-hati.
        """

        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {{"role": "system", "content": "You are a witty and professional crypto trader assistant."}},
                {{"role": "user", "content": prompt}}
            ],
            max_tokens=300,
            temperature=0.8
        )
        return response.choices[0].message.content
    except Exception:
        return "*(AI sedang memantau chart lain, coba refresh nanti...)*"


def get_series(symbol):
    """Ambil price history series untuk symbol tertentu."""
    history = st.session_state.price_history
    if history.empty or symbol not in history.columns:
        return pd.Series(dtype=float)
    return history[symbol].dropna()


def compute_technical_indicators(series, price, high_24h, low_24h, volume_idr, candles=None):
    """Hitung indikator teknikal dari candle historis, lalu fallback ke riwayat sesi."""
    candles = candles if candles is not None else pd.DataFrame()
    if not candles.empty and "close" in candles.columns:
        clean = pd.to_numeric(candles["close"], errors="coerce").dropna()
        candle_high = pd.to_numeric(candles.get("high"), errors="coerce").dropna()
        candle_low = pd.to_numeric(candles.get("low"), errors="coerce").dropna()
        candle_volume = pd.to_numeric(candles.get("volume"), errors="coerce").dropna()
        source = "ohlc"
    else:
        clean = pd.to_numeric(series, errors="coerce").dropna()
        candle_high = pd.Series(dtype=float)
        candle_low = pd.Series(dtype=float)
        candle_volume = pd.Series(dtype=float)
        source = "session"

    if price and (clean.empty or clean.iloc[-1] != price):
        clean = pd.concat([clean, pd.Series([price])], ignore_index=True)

    points = len(clean)
    ema_fast = clean.ewm(span=5, adjust=False).mean().iloc[-1] if points >= 3 else price
    ema_slow = clean.ewm(span=12, adjust=False).mean().iloc[-1] if points >= 5 else price
    ema_trend_pct = ((ema_fast - ema_slow) / ema_slow * 100) if ema_slow else 0
    ema_bias = "bullish" if ema_fast > ema_slow else "bearish" if ema_fast < ema_slow else "netral"

    if points >= 8:
        delta = clean.diff()
        gain = delta.clip(lower=0).ewm(alpha=1 / 14, adjust=False).mean()
        loss = (-delta.clip(upper=0)).ewm(alpha=1 / 14, adjust=False).mean()
        rs = gain / loss.replace(0, pd.NA)
        rsi = float((100 - (100 / (1 + rs))).fillna(50).iloc[-1])
    else:
        rsi = 50 + clamp((price - low_24h) / (high_24h - low_24h) * 50 - 25, -25, 25) if high_24h > low_24h else 50

    if points >= 15:
        macd_line = clean.ewm(span=12, adjust=False).mean() - clean.ewm(span=26, adjust=False).mean()
        signal_line = macd_line.ewm(span=9, adjust=False).mean()
        macd_hist = float(macd_line.iloc[-1] - signal_line.iloc[-1])
        prev_hist = float(macd_line.iloc[-2] - signal_line.iloc[-2]) if len(macd_line) > 1 else 0
    else:
        macd_hist = ema_trend_pct
        prev_hist = 0

    if macd_hist > 0 and prev_hist <= 0:
        macd_signal = "bullish cross"
    elif macd_hist > 0:
        macd_signal = "bullish"
    elif macd_hist < 0 and prev_hist >= 0:
        macd_signal = "bearish cross"
    elif macd_hist < 0:
        macd_signal = "bearish"
    else:
        macd_signal = "netral"

    recent_high = candle_high.tail(60).max() if not candle_high.empty else clean.tail(30).max() if points else high_24h
    recent_low = candle_low.tail(60).min() if not candle_low.empty else clean.tail(30).min() if points else low_24h
    support = min(low_24h, recent_low) if pd.notna(recent_low) else low_24h
    resistance = max(high_24h, recent_high) if pd.notna(recent_high) else high_24h
    support_gap_pct = ((price - support) / price * 100) if price else 0
    resistance_gap_pct = ((resistance - price) / price * 100) if price else 0
    volume_score = clamp(volume_idr / 5_000_000_000 * 100, 0, 100)
    if len(candle_volume) >= 20 and candle_volume.tail(20).mean() > 0:
        volume_ratio = float(candle_volume.iloc[-1] / candle_volume.tail(20).mean())
        volume_spike = "spike" if volume_ratio >= 1.8 else "kuat" if volume_ratio >= 1.15 else "normal" if volume_ratio >= 0.7 else "tipis"
    else:
        volume_ratio = 0
        volume_spike = "kuat" if volume_score >= 70 else "sedang" if volume_score >= 25 else "tipis"

    technical_score = 0
    technical_score += clamp(ema_trend_pct * 3, -12, 12)
    technical_score += 8 if macd_signal == "bullish cross" else 5 if macd_signal == "bullish" else -8 if macd_signal == "bearish cross" else -5 if macd_signal == "bearish" else 0
    technical_score += 6 if 45 <= rsi <= 68 else -7 if rsi > 78 else -4 if rsi < 30 else 0
    technical_score += 4 if support_gap_pct < 4 and resistance_gap_pct > 3 else -5 if resistance_gap_pct < 1.5 else 0
    technical_score += 6 if volume_spike == "spike" else 4 if volume_spike == "kuat" else 1 if volume_spike in {"sedang", "normal"} else -3

    # Bollinger Bands scoring — dipanggil dari luar
    bb_bonus = bb_penalty = 0
    bb_display = {"bb_score": 0, "bb_bonus": 0, "bb_penalty": 0}
    # values filled externally in compute_recommendation

    return {
        **bb_display,
        "ema_fast": ema_fast,
        "ema_slow": ema_slow,
        "ema_bias": ema_bias,
        "ema_trend_pct": round(ema_trend_pct, 2),
        "rsi": round(clamp(rsi, 0, 100), 1),
        "macd_hist": round(macd_hist, 4),
        "macd_signal": macd_signal,
        "support": support,
        "resistance": resistance,
        "support_gap_pct": round(support_gap_pct, 2),
        "resistance_gap_pct": round(resistance_gap_pct, 2),
        "volume_spike": volume_spike,
        "volume_ratio": round(volume_ratio, 2),
        "technical_score": round(technical_score, 1),
        "history_points": points,
        "indicator_source": source,
    }


def compute_value_layer(symbol, price_data, technicals):
    """Pisahkan kualitas hold dari timing trading agar sinyal tidak tabrakan."""
    volume_idr = price_data.get("vol_idr", 0)
    daily_change = price_data.get("change_pct", 0)
    high_24h = price_data.get("high", 0)
    low_24h = price_data.get("low", 0)
    range_width = high_24h - low_24h
    range_position = ((price_data.get("price", 0) - low_24h) / range_width * 100) if range_width > 0 else 50

    score = 50
    reasons = []

    if symbol in VALUE_BLUE_CHIPS:
        score += 18
        reasons.append("aset utama")
    elif symbol in MICIN_SYMBOLS:
        score -= 16
        reasons.append("aset spekulatif")
    else:
        score += 4
        reasons.append("aset menengah")

    if volume_idr >= 25_000_000_000:
        score += 14
        reasons.append("likuiditas sangat kuat")
    elif volume_idr >= 5_000_000_000:
        score += 9
        reasons.append("likuiditas kuat")
    elif volume_idr >= 1_000_000_000:
        score += 4
        reasons.append("likuiditas cukup")
    else:
        score -= 10
        reasons.append("likuiditas tipis")

    if abs(daily_change) <= 4:
        score += 8
        reasons.append("pergerakan stabil")
    elif abs(daily_change) <= 9:
        score += 1
        reasons.append("volatilitas sedang")
    else:
        score -= 9
        reasons.append("volatilitas tinggi")

    if 25 <= range_position <= 75:
        score += 6
        reasons.append("harga tidak terlalu ekstrem")
    elif range_position > 90:
        score -= 7
        reasons.append("dekat puncak 24j")

    if technicals["indicator_source"] == "ohlc" and technicals["history_points"] >= 100:
        score += 7
        reasons.append("data historis kuat")
    elif technicals["history_points"] < 20:
        score -= 4
        reasons.append("data teknikal terbatas")

    if technicals["rsi"] > 82:
        score -= 6
        reasons.append("RSI terlalu panas")
    elif 38 <= technicals["rsi"] <= 65:
        score += 4
        reasons.append("RSI sehat")

    value_score = int(clamp(round(score), 0, 100))
    if value_score >= 75:
        value_label = "VALUE BAGUS"
        value_color = "#22c55e"
    elif value_score >= 55:
        value_label = "VALUE CUKUP"
        value_color = "#f59e0b"
    elif value_score >= 40:
        value_label = "SPEKULATIF"
        value_color = "#fb7185"
    else:
        value_label = "RISKY HOLD"
        value_color = "#ef4444"

    return {
        "value_score": value_score,
        "value_label": value_label,
        "value_color": value_color,
        "value_reason": " • ".join(reasons[:4]),
    }


def build_ml_feature_frame(candles):
    """Bangun dataset fitur supervised dari candle OHLC untuk model ringan."""
    if candles is None or candles.empty or len(candles) < 80:
        return pd.DataFrame()

    df = candles[["open", "high", "low", "close", "volume"]].copy()
    for col in df.columns:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna()
    if len(df) < 80:
        return pd.DataFrame()

    close = df["close"]
    high = df["high"]
    low = df["low"]
    volume = df["volume"]
    ret1 = close.pct_change(1) * 100
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    rsi = 100 - (100 / (1 + gain / loss.replace(0, pd.NA)))

    features = pd.DataFrame(
        {
            "ret_1": ret1,
            "ret_3": close.pct_change(3) * 100,
            "ret_6": close.pct_change(6) * 100,
            "volatility_12": ret1.rolling(12).std(),
            "ema_gap": (close.ewm(span=8, adjust=False).mean() - close.ewm(span=21, adjust=False).mean()) / close * 100,
            "rsi": rsi,
            "range_pos": (close - low.rolling(24).min()) / (high.rolling(24).max() - low.rolling(24).min()).replace(0, pd.NA) * 100,
            "volume_ratio": volume / volume.rolling(24).mean().replace(0, pd.NA),
        }
    )
    features["future_return"] = close.shift(-6) / close * 100 - 100
    return features.replace([float("inf"), float("-inf")], pd.NA)


def compute_ml_forecast(candles):
    """Estimasi probabilitas naik memakai k-nearest neighbors dari candle historis."""
    features = build_ml_feature_frame(candles)
    feature_cols = ["ret_1", "ret_3", "ret_6", "volatility_12", "ema_gap", "rsi", "range_pos", "volume_ratio"]
    if features.empty:
        return {
            "ml_probability": 50.0,
            "ml_expected_return": 0.0,
            "ml_label": "NO DATA",
            "ml_confidence": "rendah",
            "ml_samples": 0,
            "ml_horizon": "6 candle",
        }

    features = features.copy()
    for col in feature_cols + ["future_return"]:
        features[col] = pd.to_numeric(features[col], errors="coerce")

    current = features[feature_cols].dropna().tail(1).astype(float)
    train = features.dropna(subset=feature_cols + ["future_return"]).copy()
    train[feature_cols + ["future_return"]] = train[feature_cols + ["future_return"]].astype(float)
    if current.empty or len(train) < 50:
        return {
            "ml_probability": 50.0,
            "ml_expected_return": 0.0,
            "ml_label": "DATA KURANG",
            "ml_confidence": "rendah",
            "ml_samples": len(train),
            "ml_horizon": "6 candle",
        }

    means = train[feature_cols].mean(numeric_only=True)
    stds = train[feature_cols].std(numeric_only=True).replace(0, 1).fillna(1)
    train_x = ((train[feature_cols] - means) / stds).astype(float)
    current_x = ((current.iloc[0] - means) / stds).astype(float)
    distances = (train_x.sub(current_x, axis=1).pow(2).sum(axis=1)).pow(0.5)
    distances = pd.to_numeric(distances, errors="coerce").dropna()
    if distances.empty:
        return {
            "ml_probability": 50.0,
            "ml_expected_return": 0.0,
            "ml_label": "DATA KURANG",
            "ml_confidence": "rendah",
            "ml_samples": len(train),
            "ml_horizon": "6 candle",
        }
    k = int(clamp(round(len(train) ** 0.5), 12, 35))
    nearest = train.loc[distances.nsmallest(k).index].copy()
    nearest_distances = distances.loc[nearest.index]
    weights = 1 / (nearest_distances + 0.001)
    up_labels = (nearest["future_return"] > 1.0).astype(float)
    probability = float((up_labels * weights).sum() / weights.sum() * 100)
    expected_return = float((nearest["future_return"] * weights).sum() / weights.sum())

    if probability >= 62:
        label = "BULLISH"
    elif probability <= 42:
        label = "BEARISH"
    else:
        label = "NETRAL"

    edge = abs(probability - 50)
    if len(train) >= 180 and edge >= 14:
        confidence = "tinggi"
    elif len(train) >= 90 and edge >= 8:
        confidence = "sedang"
    else:
        confidence = "rendah"

    return {
        "ml_probability": round(probability, 1),
        "ml_expected_return": round(expected_return, 2),
        "ml_label": label,
        "ml_confidence": confidence,
        "ml_samples": len(train),
        "ml_horizon": "6 candle",
    }


def compute_signal_backtest(candles, horizon=6, target_pct=2.6, stop_pct=2.2):
    """Rapor sederhana: sinyal candle serupa historisnya lebih sering kena target atau stop."""
    empty_result = {
        "backtest_winrate": 0.0,
        "backtest_trades": 0,
        "backtest_avg_return": 0.0,
        "backtest_profit_factor": 0.0,
        "backtest_label": "DATA KURANG",
        "backtest_color": "#9ca3af",
        "backtest_note": "Belum cukup candle untuk menilai sinyal.",
    }
    if candles is None or candles.empty or len(candles) < 90:
        return empty_result

    required = ["open", "high", "low", "close", "volume"]
    if not all(col in candles.columns for col in required):
        return empty_result

    df = candles[required].copy()
    for col in required:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna().reset_index(drop=True)
    if len(df) < 90:
        return empty_result

    close = df["close"].astype(float)
    high = df["high"].astype(float)
    low = df["low"].astype(float)
    volume = df["volume"].astype(float)
    ret3 = close.pct_change(3) * 100
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    rsi = 100 - (100 / (1 + gain / loss.replace(0, pd.NA)))
    ema_fast = close.ewm(span=8, adjust=False).mean()
    ema_slow = close.ewm(span=21, adjust=False).mean()
    range_low = low.rolling(24).min()
    range_high = high.rolling(24).max()
    range_pos = (close - range_low) / (range_high - range_low).replace(0, pd.NA) * 100
    volume_ratio = volume / volume.rolling(24).mean().replace(0, pd.NA)

    signal = (
        (ema_fast > ema_slow)
        & (rsi.between(42, 72))
        & (range_pos.between(32, 88))
        & (volume_ratio >= 0.75)
        & (ret3 > -3)
    ).fillna(False)

    outcomes = []
    last_entry_index = -horizon
    for idx in range(35, len(df) - horizon - 1):
        if not bool(signal.iloc[idx]) or idx - last_entry_index < horizon:
            continue
        entry = float(close.iloc[idx])
        if entry <= 0:
            continue
        target = entry * (1 + target_pct / 100)
        stop = entry * (1 - stop_pct / 100)
        outcome = None
        for step in range(idx + 1, idx + horizon + 1):
            if float(low.iloc[step]) <= stop:
                outcome = -stop_pct
                break
            if float(high.iloc[step]) >= target:
                outcome = target_pct
                break
        if outcome is None:
            outcome = float((close.iloc[idx + horizon] - entry) / entry * 100)
        outcomes.append(outcome)
        last_entry_index = idx

    if len(outcomes) < 6:
        result = empty_result.copy()
        result.update({
            "backtest_trades": len(outcomes),
            "backtest_note": "Sinyal historis masih terlalu sedikit.",
        })
        return result

    wins = [x for x in outcomes if x > 0]
    losses = [x for x in outcomes if x < 0]
    winrate = len(wins) / len(outcomes) * 100
    avg_return = sum(outcomes) / len(outcomes)
    profit_factor = (sum(wins) / abs(sum(losses))) if losses else float(len(wins))

    if len(outcomes) >= 14 and winrate >= 58 and avg_return > 0:
        label = "TERUJI BAGUS"
        color = "#22c55e"
        note = "Sinyal serupa historisnya cukup sering berhasil."
    elif winrate >= 50 and avg_return >= -0.2:
        label = "CUKUP"
        color = "#f59e0b"
        note = "Sinyal historis lumayan, tetap perlu disiplin exit."
    else:
        label = "LEMAH"
        color = "#ef4444"
        note = "Sinyal serupa historisnya belum meyakinkan."

    return {
        "backtest_winrate": round(winrate, 1),
        "backtest_trades": len(outcomes),
        "backtest_avg_return": round(avg_return, 2),
        "backtest_profit_factor": round(profit_factor, 2),
        "backtest_label": label,
        "backtest_color": color,
        "backtest_note": note,
    }


def combine_strategy_mode(trading_score, value_score, action):
    if action == "buy" and trading_score >= 70 and value_score >= 70:
        return "SWING / HOLD", "#22c55e", "Trading dan value sama-sama mendukung."
    if action == "buy" and trading_score >= 70 and value_score < 55:
        return "SCALP ONLY", "#f97316", "Momentum bagus, tapi kualitas hold lemah."
    if action != "buy" and value_score >= 70:
        return "WATCH VALUE", "#38bdf8", "Aset layak pantau, tunggu timing entry."
    if action == "buy":
        return "TRADE KECIL", "#eab308", "Boleh entry kecil dengan disiplin exit."
    if value_score < 40:
        return "SKIP", "#ef4444", "Timing dan value belum mendukung."
    return "WATCH", "#9ca3af", "Belum ada konfirmasi kuat."


def compute_bollinger_vwap(series, candles=None):
    """Bollinger Bands (20,2) + simulated VWAP dari candles."""
    candles = candles if candles is not None else pd.DataFrame()
    if not candles.empty and "close" in candles.columns:
        close = pd.to_numeric(candles["close"], errors="coerce").dropna()
        vol = pd.to_numeric(candles.get("volume"), errors="coerce").dropna()
        hi = pd.to_numeric(candles.get("high"), errors="coerce").dropna()
        lo = pd.to_numeric(candles.get("low"), errors="coerce").dropna()
    else:
        close = pd.to_numeric(series, errors="coerce").dropna()
        vol = pd.Series(dtype=float)
        hi = pd.Series(dtype=float)
        lo = pd.Series(dtype=float)

    bb_upper = bb_middle = bb_lower = bb_pct_b = bb_bandwidth = 0
    bb_signal = "netral"
    vwap_val = close.iloc[-1] if len(close) > 0 else 0

    if len(close) >= 20:
        bb_middle = float(close.tail(20).mean())
        bb_std = float(close.tail(20).std())
        bb_upper = bb_middle + 2 * bb_std
        bb_lower = bb_middle - 2 * bb_std
        last = float(close.iloc[-1])
        if bb_upper > bb_lower:
            bb_pct_b = (last - bb_lower) / (bb_upper - bb_lower)
        bb_bandwidth = (bb_upper - bb_lower) / bb_middle if bb_middle > 0 else 0

        if bb_pct_b < 0.15:
            bb_signal = "oversold"
        elif bb_pct_b > 0.85:
            bb_signal = "overbought"
        elif 0.35 <= bb_pct_b <= 0.65:
            bb_signal = "mid_range"
        elif bb_pct_b < 0.35:
            bb_signal = "low_range"
        else:
            bb_signal = "high_range"

    # Simulated VWAP
    if len(close) >= 20 and len(vol) >= 20:
        common_len = min(len(close), len(vol))
        if common_len >= 20:
            c = close.tail(common_len)
            v = vol.tail(common_len)
            typical = (hi.tail(common_len).values + lo.tail(common_len).values + c.values) / 3 if len(hi) >= common_len and len(lo) >= common_len else c.values
            total_vol = v.sum()
            if total_vol > 0:
                vwap_val = float((typical * v.values).sum() / total_vol)

    return {
        "bb_middle": round(bb_middle, 2),
        "bb_upper": round(bb_upper, 2),
        "bb_lower": round(bb_lower, 2),
        "bb_pct_b": round(bb_pct_b, 2),
        "bb_bandwidth": round(bb_bandwidth, 2),
        "bb_signal": bb_signal,
        "vwap": round(vwap_val, 2),
        "bb_points": len(close),
    }


def compute_adx(series, candles=None):
    """ADX approximation dari close price atau candles."""
    candles = candles if candles is not None else pd.DataFrame()
    if not candles.empty and "high" in candles.columns and "low" in candles.columns and "close" in candles.columns:
        hi = pd.to_numeric(candles["high"], errors="coerce")
        lo = pd.to_numeric(candles["low"], errors="coerce")
        cl = pd.to_numeric(candles["close"], errors="coerce")
    else:
        cl = pd.to_numeric(series, errors="coerce").dropna()
        hi = cl * 1.002
        lo = cl * 0.998

    adx_val = pdi_val = ndi_val = 25
    trend_strength = "sideways"
    history = len(cl)

    if history >= 28:
        # Ensure all series are float64 to avoid downstream dtype issues
        hi = hi.astype(float)
        lo = lo.astype(float)
        cl = cl.astype(float)

        tr = pd.concat([
            hi - lo,
            (hi - cl.shift(1)).abs(),
            (lo - cl.shift(1)).abs(),
        ], axis=1).max(axis=1)

        up_move = hi - hi.shift(1)
        down_move = lo.shift(1) - lo

        plus_dm = up_move.where((up_move > down_move) & (up_move > 0), 0.0)
        minus_dm = down_move.where((down_move > up_move) & (down_move > 0), 0.0)

        atr = tr.ewm(alpha=1 / 14, adjust=False).mean()
        smooth_plus = plus_dm.ewm(alpha=1 / 14, adjust=False).mean()
        smooth_minus = minus_dm.ewm(alpha=1 / 14, adjust=False).mean()
        pdi_raw = 100 * smooth_plus / atr.replace(0, float('nan'))
        ndi_raw = 100 * smooth_minus / atr.replace(0, float('nan'))
        pdi = pdi_raw.fillna(0.0)
        ndi = ndi_raw.fillna(0.0)

        denom = (pdi + ndi).replace(0.0, float('nan'))
        dx = 100 * abs(pdi - ndi) / denom
        dx = dx.fillna(50.0)  # neutral ADX when pdi=ndi=0
        dx = dx.astype(float)
        adx = dx.ewm(alpha=1 / 14, adjust=False).mean().fillna(25.0)

        adx_val = float(adx.iloc[-1])
        pdi_val = float(pdi.iloc[-1])
        ndi_val = float(ndi.iloc[-1])

    if adx_val >= 25:
        if pdi_val > ndi_val:
            trend_strength = "bullish_strong" if adx_val >= 40 else "bullish_moderate"
        else:
            trend_strength = "bearish_strong" if adx_val >= 40 else "bearish_moderate"
    elif adx_val >= 18:
        trend_strength = "weak_trend"
    else:
        trend_strength = "sideways"

    return {
        "adx": round(adx_val, 1),
        "pdi": round(pdi_val, 1),
        "ndi": round(ndi_val, 1),
        "trend_strength": trend_strength,
        "adx_points": history,
    }


def compute_ta_plus(candles=None):
    """TA-lite dari ide library `ta`: ATR, MFI, OBV, Supertrend, dan candle pattern."""
    default = {
        "atr_pct": 0.0,
        "mfi": 50.0,
        "obv_trend": "netral",
        "supertrend_bias": "netral",
        "candle_signal": "netral",
        "ta_plus_score": 0,
    }
    if candles is None or candles.empty:
        return default
    required = ["open", "high", "low", "close", "volume"]
    if not all(col in candles.columns for col in required):
        return default

    df = candles[required].copy()
    for col in required:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna().reset_index(drop=True)
    if len(df) < 30:
        return default

    open_ = df["open"].astype(float)
    high = df["high"].astype(float)
    low = df["low"].astype(float)
    close = df["close"].astype(float)
    volume = df["volume"].astype(float)

    tr = pd.concat([
        high - low,
        (high - close.shift(1)).abs(),
        (low - close.shift(1)).abs(),
    ], axis=1).max(axis=1)
    atr = tr.rolling(14).mean()
    last_close = float(close.iloc[-1])
    atr_pct = float(atr.iloc[-1] / last_close * 100) if last_close > 0 and pd.notna(atr.iloc[-1]) else 0

    typical = (high + low + close) / 3
    money_flow = typical * volume
    positive_flow = money_flow.where(typical > typical.shift(1), 0.0).rolling(14).sum()
    negative_flow = money_flow.where(typical < typical.shift(1), 0.0).rolling(14).sum()
    mfi_series = 100 - (100 / (1 + positive_flow / negative_flow.replace(0, pd.NA)))
    mfi = float(mfi_series.fillna(50).iloc[-1])

    obv_step = volume.where(close.diff() > 0, -volume.where(close.diff() < 0, 0.0))
    obv = obv_step.fillna(0).cumsum()
    obv_fast = obv.rolling(5).mean()
    obv_slow = obv.rolling(20).mean()
    if pd.notna(obv_fast.iloc[-1]) and pd.notna(obv_slow.iloc[-1]):
        obv_trend = "naik" if obv_fast.iloc[-1] > obv_slow.iloc[-1] else "turun" if obv_fast.iloc[-1] < obv_slow.iloc[-1] else "netral"
    else:
        obv_trend = "netral"

    ema_fast = close.ewm(span=10, adjust=False).mean()
    ema_slow = close.ewm(span=30, adjust=False).mean()
    supertrend_floor = ((high + low) / 2) - (2.4 * atr)
    if pd.notna(supertrend_floor.iloc[-1]) and close.iloc[-1] > supertrend_floor.iloc[-1] and ema_fast.iloc[-1] > ema_slow.iloc[-1]:
        supertrend_bias = "bullish"
    elif pd.notna(supertrend_floor.iloc[-1]) and (close.iloc[-1] < supertrend_floor.iloc[-1] or ema_fast.iloc[-1] < ema_slow.iloc[-1]):
        supertrend_bias = "bearish"
    else:
        supertrend_bias = "netral"

    prev_open, prev_close = float(open_.iloc[-2]), float(close.iloc[-2])
    curr_open, curr_close = float(open_.iloc[-1]), float(close.iloc[-1])
    body = abs(curr_close - curr_open)
    candle_range = max(float(high.iloc[-1] - low.iloc[-1]), 1e-9)
    if curr_close > curr_open and prev_close < prev_open and curr_close >= prev_open and curr_open <= prev_close:
        candle_signal = "bullish engulfing"
    elif curr_close < curr_open and prev_close > prev_open and curr_open >= prev_close and curr_close <= prev_open:
        candle_signal = "bearish engulfing"
    elif body / candle_range <= 0.12:
        candle_signal = "doji"
    else:
        candle_signal = "netral"

    ta_score = 0
    ta_score += 6 if supertrend_bias == "bullish" else -7 if supertrend_bias == "bearish" else 0
    ta_score += 4 if obv_trend == "naik" else -4 if obv_trend == "turun" else 0
    ta_score += 4 if 38 <= mfi <= 72 else -6 if mfi > 84 else -2 if mfi < 20 else 0
    ta_score += 5 if candle_signal == "bullish engulfing" else -5 if candle_signal == "bearish engulfing" else 0
    ta_score += -4 if atr_pct >= 7 else 2 if 1 <= atr_pct <= 4.5 else 0

    return {
        "atr_pct": round(atr_pct, 2),
        "mfi": round(clamp(mfi, 0, 100), 1),
        "obv_trend": obv_trend,
        "supertrend_bias": supertrend_bias,
        "candle_signal": candle_signal,
        "ta_plus_score": round(ta_score, 1),
    }


def compute_strategy_lab(candles, horizon=6):
    """VectorBT-lite: batch test beberapa gaya strategi di candle yang sama."""
    default = {
        "lab_best_strategy": "DATA KURANG",
        "lab_score": 0.0,
        "lab_winrate": 0.0,
        "lab_trades": 0,
        "lab_avg_return": 0.0,
        "lab_profit_factor": 0.0,
    }
    if candles is None or candles.empty or len(candles) < 100:
        return default
    required = ["high", "low", "close", "volume"]
    if not all(col in candles.columns for col in required):
        return default

    df = candles[required].copy()
    for col in required:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna().reset_index(drop=True)
    if len(df) < 100:
        return default

    high = df["high"].astype(float)
    low = df["low"].astype(float)
    close = df["close"].astype(float)
    volume = df["volume"].astype(float)
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    rsi = 100 - (100 / (1 + gain / loss.replace(0, pd.NA)))
    ema8 = close.ewm(span=8, adjust=False).mean()
    ema21 = close.ewm(span=21, adjust=False).mean()
    ema50 = close.ewm(span=50, adjust=False).mean()
    volume_ratio = volume / volume.rolling(24).mean().replace(0, pd.NA)
    high_break = high.shift(1).rolling(24).max()
    low_range = low.rolling(24).min()
    high_range = high.rolling(24).max()
    range_pos = (close - low_range) / (high_range - low_range).replace(0, pd.NA) * 100

    variants = {
        "Trend Rider": (ema8 > ema21) & (ema21 > ema50) & rsi.between(45, 72) & (volume_ratio >= 0.8),
        "Dip Buyer": (ema8 >= ema21) & rsi.between(32, 52) & range_pos.between(18, 55),
        "Breakout": (close > high_break) & (volume_ratio >= 1.15) & rsi.between(50, 78),
        "Calm Swing": (ema8 > ema21) & rsi.between(42, 65) & range_pos.between(35, 78) & (volume_ratio >= 0.7),
    }

    results = []
    for name, signal in variants.items():
        outcomes = []
        last_idx = -horizon
        for idx in range(60, len(df) - horizon):
            if not bool(signal.fillna(False).iloc[idx]) or idx - last_idx < horizon:
                continue
            entry = float(close.iloc[idx])
            if entry <= 0:
                continue
            ret = float((close.iloc[idx + horizon] - entry) / entry * 100)
            outcomes.append(ret)
            last_idx = idx
        if not outcomes:
            continue
        wins = [x for x in outcomes if x > 0]
        losses = [x for x in outcomes if x < 0]
        winrate = len(wins) / len(outcomes) * 100
        avg_return = sum(outcomes) / len(outcomes)
        profit_factor = (sum(wins) / abs(sum(losses))) if losses else float(len(wins))
        score = winrate * 0.45 + avg_return * 8 + min(len(outcomes), 30) * 0.75 + min(profit_factor, 4) * 5
        results.append({
            "name": name,
            "score": score,
            "winrate": winrate,
            "trades": len(outcomes),
            "avg_return": avg_return,
            "profit_factor": profit_factor,
        })

    if not results:
        return default
    best = sorted(results, key=lambda x: (x["score"], x["trades"]), reverse=True)[0]
    return {
        "lab_best_strategy": best["name"],
        "lab_score": round(best["score"], 1),
        "lab_winrate": round(best["winrate"], 1),
        "lab_trades": best["trades"],
        "lab_avg_return": round(best["avg_return"], 2),
        "lab_profit_factor": round(best["profit_factor"], 2),
    }


def compute_recommendation(symbol, price_data, market_stats=None, historical_candles=None, series_len_threshold=5):
    """
    Hitung rekomendasi berdasarkan momentum harga.
    Returns dict dengan detail rekomendasi.
    """
    price = price_data.get("price", 0)
    daily_change = price_data.get("change_pct", 0)
    high_24h = price_data.get("high", 0)
    low_24h = price_data.get("low", 0)
    volume_idr = price_data.get("vol_idr", 0)
    series = get_series(symbol)

    if len(series) >= series_len_threshold:
        change_short = ((price - series.iloc[-min(series_len_threshold, len(series))]) / series.iloc[-min(series_len_threshold, len(series))]) * 100
        change_long = ((price - series.iloc[0]) / series.iloc[0]) * 100 if series.iloc[0] > 0 else 0
        volatility = series.pct_change().std() * 100 if len(series) > 1 else 0
    else:
        change_short = daily_change
        change_long = 0
        volatility = 0

    market_stats = market_stats or {}
    market_mode = market_stats.get("mode", "normal")
    market_rule = MARKET_MODE_RULES.get(market_mode, MARKET_MODE_RULES["normal"])

    # Weighted momentum score
    momentum = change_short * 0.45 + change_long * 0.2 + daily_change * 0.35
    range_width = high_24h - low_24h
    range_position = ((price - low_24h) / range_width * 100) if range_width > 0 else 50
    liquidity_score = min(100, max(0, volume_idr / 10_000_000_000 * 100))
    candles = historical_candles.get(symbol, pd.DataFrame()) if historical_candles else pd.DataFrame()
    technicals = compute_technical_indicators(series, price, high_24h, low_24h, volume_idr, candles)
    ml_forecast = compute_ml_forecast(candles)
    bb_data = compute_bollinger_vwap(series, candles)
    adx_data = compute_adx(series, candles)
    ta_plus = compute_ta_plus(candles)
    strategy_lab = compute_strategy_lab(candles)
    backtest = compute_signal_backtest(candles)
    ml_adjustment = (ml_forecast["ml_probability"] - 50) * 0.28
    if ml_forecast["ml_confidence"] == "rendah":
        ml_adjustment *= 0.45
    elif ml_forecast["ml_confidence"] == "sedang":
        ml_adjustment *= 0.75
    backtest_adjustment = 0
    if backtest["backtest_trades"] >= 6:
        backtest_adjustment = (backtest["backtest_winrate"] - 50) * 0.12
        if backtest["backtest_avg_return"] > 0:
            backtest_adjustment += min(4, backtest["backtest_avg_return"] * 1.4)
    fomo_penalty = 9 if range_position > 88 and daily_change > 8 else 0
    volatility_penalty = min(18, volatility * 2.5)
    micin_penalty = 6 if symbol in MICIN_SYMBOLS else 0

    # Bollinger Bands scoring
    bb_bonus = 0
    if bb_data["bb_signal"] == "oversold":
        bb_bonus = 7  # Mean reversion entry bagus
    elif bb_data["bb_signal"] == "low_range" and bb_data["bb_bandwidth"] > 0.08:
        bb_bonus = 3
    elif bb_data["bb_signal"] == "overbought":
        bb_bonus = -5
    if bb_data["vwap"] > 0 and price < bb_data["vwap"] * 0.98:
        bb_bonus += 3  # Harga di bawah VWAP = diskon

    # ADX scoring
    adx_bonus = 0
    ts = adx_data["trend_strength"]
    if ts in ("bullish_strong", "bullish_moderate"):
        adx_bonus = 5 if ts == "bullish_strong" else 3
        if adx_data["adx"] >= 30:
            adx_bonus += 3  # Tren makin mantap
    elif ts in ("bearish_strong", "bearish_moderate"):
        adx_bonus = -6 if ts == "bearish_strong" else -3

    lab_adjustment = 0
    if strategy_lab["lab_trades"] >= 8:
        lab_adjustment = clamp((strategy_lab["lab_winrate"] - 50) * 0.08 + strategy_lab["lab_avg_return"] * 1.4, -5, 7)

    base_score = (
        50
        + momentum * 4.2
        + daily_change * 1.1
        + liquidity_score * 0.18
        + technicals["technical_score"] * 0.65
        + ml_adjustment
        + market_rule["score_adjustment"]
        + bb_bonus
        + adx_bonus
        + ta_plus["ta_plus_score"]
        + backtest_adjustment
        + lab_adjustment
        - volatility_penalty
        - fomo_penalty
        - micin_penalty
    )
    score = int(clamp(round(base_score), 0, 100))

    # Recommendation logic with score, momentum, and market context.
    if score >= 80 and momentum > 1:
        label = "🟢 BELI KUAT"
        color = "#22c55e"
        action = "buy"
        entry_stage = "CONFIRMED"
    elif score >= 65 and momentum > 0:
        label = "🟡 CICIL BELI"
        color = "#eab308"
        action = "buy"
        entry_stage = "ENTRY KECIL"
    elif score >= 50:
        label = "⚪ WATCH"
        color = "#9ca3af"
        action = "hold"
        entry_stage = "WATCHLIST"
    elif score >= 35:
        label = "🔴 JANGAN BELI"
        color = "#ef4444"
        action = "skip"
        entry_stage = "SKIP"
    else:
        label = "⛔ HINDARI"
        color = "#dc2626"
        action = "skip"
        entry_stage = "AVOID"

    risk_points = 0
    if volatility >= 4:
        risk_points += 2
    elif volatility >= 2:
        risk_points += 1
    if abs(daily_change) >= 10:
        risk_points += 2
    elif abs(daily_change) >= 5:
        risk_points += 1
    if volume_idr < 100_000_000:
        risk_points += 2
    elif volume_idr < 1_000_000_000:
        risk_points += 1
    if range_position > 85:
        risk_points += 1
    if technicals["rsi"] > 78:
        risk_points += 1
    if technicals["macd_signal"] == "bearish cross":
        risk_points += 1
    if ml_forecast["ml_label"] == "BEARISH" and ml_forecast["ml_confidence"] != "rendah":
        risk_points += 1
    if backtest["backtest_label"] == "LEMAH" and backtest["backtest_trades"] >= 10:
        risk_points += 1
    if ta_plus["atr_pct"] >= 7:
        risk_points += 1
    if ta_plus["supertrend_bias"] == "bearish":
        risk_points += 1

    if risk_points >= 4:
        risk_level = "TINGGI"
        risk_color = "#ef4444"
    elif risk_points >= 2:
        risk_level = "SEDANG"
        risk_color = "#f59e0b"
    else:
        risk_level = "RENDAH"
        risk_color = "#22c55e"

    # Potential gain, exit plan, and allocation. Conservative by design.
    if action == "buy":
        potential_gain = clamp(3 + (score - 60) * 0.22 + max(momentum, 0) * 0.75, 3, 18)
        if symbol in MICIN_SYMBOLS:
            potential_gain = clamp(potential_gain * 1.15, 3, 25)
    elif action == "skip":
        potential_gain = -clamp(abs(momentum) * 1.15 + (100 - score) * 0.03, 1, 15)
    else:
        potential_gain = clamp(abs(momentum) * 0.65 + 0.5, 0.5, 3)

    stop_loss_pct = clamp(
        2.6 + abs(momentum) * 0.45 + volatility * 0.8 + ta_plus["atr_pct"] * 0.25 + (1.2 if symbol in MICIN_SYMBOLS else 0),
        2.5,
        15 if symbol in MICIN_SYMBOLS else 10,
    )
    stop_loss = price * (1 - stop_loss_pct / 100)
    target_price = price * (1 + max(potential_gain, 0.5) / 100)
    take_profit_1 = price * (1 + max(potential_gain, 1) * 0.35 / 100)
    take_profit_2 = price * (1 + max(potential_gain, 1) * 0.7 / 100)
    take_profit_3 = target_price
    trailing_stop_pct = clamp(stop_loss_pct * 0.55, 1.5, 7 if symbol in MICIN_SYMBOLS else 5)
    risk_reward = (potential_gain / stop_loss_pct) if stop_loss_pct > 0 and potential_gain > 0 else 0

    risk_modifier = {"RENDAH": 1.0, "SEDANG": 0.68, "TINGGI": 0.38}[risk_level]
    base_allocation = 7.5 if symbol not in MICIN_SYMBOLS else 3.2
    max_allocation = 12 if symbol not in MICIN_SYMBOLS else 5
    allocation_pct = 0
    if action == "buy":
        allocation_pct = base_allocation * (score / 100) * market_rule["allocation_multiplier"] * risk_modifier
        allocation_pct = clamp(allocation_pct, 1.0, max_allocation)
    risk_per_trade_pct = clamp((0.45 + score / 100 * 1.45) * risk_modifier, 0.35, 2.0)
    if market_mode == "defensive":
        risk_per_trade_pct = clamp(risk_per_trade_pct * 0.65, 0.25, 1.2)

    if action == "buy":
        position_plan = f"Pakai max {allocation_pct:.1f}% modal, masuk bertahap 50/30/20."
        exit_rule = f"TP 30% di TP1, 30% di TP2, sisanya trailing {trailing_stop_pct:.1f}%."
    elif action == "hold":
        position_plan = "Belum entry. Masukkan watchlist dan tunggu score naik di atas 65."
        exit_rule = "Tidak ada posisi baru. Validasi ulang setelah candle berikutnya."
    else:
        position_plan = "Tidak entry. Simpan modal untuk setup yang lebih bersih."
        exit_rule = "Jika sudah terlanjur masuk, prioritaskan proteksi modal."

    # Investment scenario for Rp1.000.000
    invest_amount = 1_000_000
    qty = invest_amount / price if price > 0 else 0
    estimated_profit = invest_amount * (potential_gain / 100)

    reasons = []
    if momentum > 1:
        reasons.append("momentum positif")
    elif momentum < -0.5:
        reasons.append("momentum melemah")
    else:
        reasons.append("momentum netral")
    if daily_change > 0:
        reasons.append("24j hijau")
    elif daily_change < 0:
        reasons.append("24j merah")
    if volume_idr >= 1_000_000_000:
        reasons.append("volume kuat")
    elif volume_idr > 0:
        reasons.append("volume tipis")
    if range_position > 80:
        reasons.append("dekat high 24j")
    elif range_position < 25:
        reasons.append("dekat low 24j")
    if technicals["ema_bias"] == "bullish":
        reasons.append("EMA bullish")
    elif technicals["ema_bias"] == "bearish":
        reasons.append("EMA bearish")
    if technicals["macd_signal"] in {"bullish cross", "bearish cross"}:
        reasons.append(f"MACD {technicals['macd_signal']}")
    if technicals["rsi"] > 75:
        reasons.append("RSI panas")
    elif technicals["rsi"] < 35:
        reasons.append("RSI murah")
    if ml_forecast["ml_label"] == "BULLISH":
        reasons.append(f"ML bullish {ml_forecast['ml_probability']:.1f}%")
    elif ml_forecast["ml_label"] == "BEARISH":
        reasons.append(f"ML bearish {ml_forecast['ml_probability']:.1f}%")
    if ta_plus["supertrend_bias"] == "bullish":
        reasons.append("Supertrend bullish")
    elif ta_plus["supertrend_bias"] == "bearish":
        reasons.append("Supertrend bearish")
    if backtest["backtest_trades"] >= 6:
        reasons.append(f"rapor {backtest['backtest_winrate']:.1f}%")
    if strategy_lab["lab_trades"] >= 6:
        reasons.append(f"lab {strategy_lab['lab_best_strategy']}")
    reasons.append(MARKET_MODE_RULES.get(market_mode, MARKET_MODE_RULES["normal"])["label"].replace("🚀 ", "").replace("⚖️ ", "").replace("🛡️ ", "").lower())
    value_layer = compute_value_layer(symbol, price_data, technicals)
    strategy_mode, strategy_color, strategy_note = combine_strategy_mode(score, value_layer["value_score"], action)
    agentic = build_agentic_verdict({
        "score": score,
        "value_score": value_layer["value_score"],
        "technical_score": technicals["technical_score"],
        "ml_probability": ml_forecast["ml_probability"],
        "ml_confidence": ml_forecast["ml_confidence"],
        "risk_reward": risk_reward,
        "risk_level": risk_level,
        "backtest_winrate": backtest["backtest_winrate"],
        "backtest_trades": backtest["backtest_trades"],
        "backtest_label": backtest["backtest_label"],
        "strategy_mode": strategy_mode,
        "trend_strength": adx_data["trend_strength"],
        "supertrend_bias": ta_plus["supertrend_bias"],
        "atr_pct": ta_plus["atr_pct"],
        "lab_winrate": strategy_lab["lab_winrate"],
        "lab_trades": strategy_lab["lab_trades"],
        "bb_signal": bb_data["bb_signal"],
        "rsi": technicals["rsi"],
        "daily_change": daily_change,
        "range_position": range_position,
        "volume_idr": volume_idr,
        "category": COIN_CATEGORIES.get(symbol, ""),
    })
    if action == "buy":
        allocation_pct = round(allocation_pct * agentic["agent_size_multiplier"], 2)
        if agentic["agent_size_multiplier"] == 0:
            position_plan = "Risk manager menolak entry. Tunggu setup lebih bersih."
            exit_rule = "Tidak buka posisi baru."
        elif agentic["agent_size_multiplier"] < 1:
            position_plan = f"Pakai max {allocation_pct:.1f}% modal setelah dipotong risk manager, masuk bertahap 50/30/20."

    return {
        "symbol": symbol,
        "price": price,
        "volume_idr": volume_idr,
        "score": score,
        "value_score": value_layer["value_score"],
        "value_label": value_layer["value_label"],
        "value_color": value_layer["value_color"],
        "value_reason": value_layer["value_reason"],
        "strategy_mode": strategy_mode,
        "strategy_color": strategy_color,
        "strategy_note": strategy_note,
        "label": label,
        "color": color,
        "action": action,
        "entry_stage": entry_stage,
        "market_mode": market_mode,
        "quality": "kuat" if technicals["indicator_source"] == "ohlc" and technicals["history_points"] >= 50 else "cukup" if technicals["history_points"] >= 8 else "awal",
        "daily_change": round(daily_change, 2),
        "momentum": round(momentum, 2),
        "range_position": round(range_position, 1),
        "liquidity_score": round(liquidity_score, 1),
        "technical_score": technicals["technical_score"],
        "ml_probability": ml_forecast["ml_probability"],
        "ml_expected_return": ml_forecast["ml_expected_return"],
        "ml_label": ml_forecast["ml_label"],
        "ml_confidence": ml_forecast["ml_confidence"],
        "ml_samples": ml_forecast["ml_samples"],
        "ml_horizon": ml_forecast["ml_horizon"],
        "backtest_winrate": backtest["backtest_winrate"],
        "backtest_trades": backtest["backtest_trades"],
        "backtest_avg_return": backtest["backtest_avg_return"],
        "backtest_profit_factor": backtest["backtest_profit_factor"],
        "backtest_label": backtest["backtest_label"],
        "backtest_color": backtest["backtest_color"],
        "backtest_note": backtest["backtest_note"],
        "ema_bias": technicals["ema_bias"],
        "ema_trend_pct": technicals["ema_trend_pct"],
        "rsi": technicals["rsi"],
        "macd_signal": technicals["macd_signal"],
        "support": technicals["support"],
        "resistance": technicals["resistance"],
        "support_gap_pct": technicals["support_gap_pct"],
        "resistance_gap_pct": technicals["resistance_gap_pct"],
        "volume_spike": technicals["volume_spike"],
        "volume_ratio": technicals["volume_ratio"],
        "history_points": technicals["history_points"],
        "indicator_source": technicals["indicator_source"],
        "potential_gain_pct": round(potential_gain, 2),
        "target_price": target_price,
        "stop_loss": stop_loss,
        "stop_loss_pct": round(stop_loss_pct, 2),
        "take_profit_1": take_profit_1,
        "take_profit_2": take_profit_2,
        "take_profit_3": take_profit_3,
        "trailing_stop_pct": round(trailing_stop_pct, 2),
        "risk_reward": round(risk_reward, 2),
        "allocation_pct": round(allocation_pct, 2),
        "risk_per_trade_pct": round(risk_per_trade_pct, 2),
        "risk_level": risk_level,
        "risk_color": risk_color,
        "reason": " • ".join(reasons[:4]),
        "position_plan": position_plan,
        "exit_rule": exit_rule,
        "agent_bull_score": agentic["agent_bull_score"],
        "agent_bear_score": agentic["agent_bear_score"],
        "agent_net_score": agentic["agent_net_score"],
        "agent_bull_case": agentic["agent_bull_case"],
        "agent_bear_case": agentic["agent_bear_case"],
        "agent_risk_decision": agentic["agent_risk_decision"],
        "agent_verdict": agentic["agent_verdict"],
        "agent_verdict_color": agentic["agent_verdict_color"],
        "agent_size_multiplier": agentic["agent_size_multiplier"],
        "agent_note": agentic["agent_note"],
        "invest_1jt_qty": qty,
        "profit_1jt": estimated_profit,
        "volatility": round(volatility, 2) if volatility else 0,
        "bb_signal": bb_data["bb_signal"],
        "bb_pct_b": bb_data["bb_pct_b"],
        "bb_bandwidth": bb_data["bb_bandwidth"],
        "bb_middle": bb_data["bb_middle"],
        "bb_upper": bb_data["bb_upper"],
        "bb_lower": bb_data["bb_lower"],
        "vwap": bb_data["vwap"],
        "adx": adx_data["adx"],
        "pdi": adx_data["pdi"],
        "ndi": adx_data["ndi"],
        "trend_strength": adx_data["trend_strength"],
        "atr_pct": ta_plus["atr_pct"],
        "mfi": ta_plus["mfi"],
        "obv_trend": ta_plus["obv_trend"],
        "supertrend_bias": ta_plus["supertrend_bias"],
        "candle_signal": ta_plus["candle_signal"],
        "ta_plus_score": ta_plus["ta_plus_score"],
        "lab_best_strategy": strategy_lab["lab_best_strategy"],
        "lab_score": strategy_lab["lab_score"],
        "lab_winrate": strategy_lab["lab_winrate"],
        "lab_trades": strategy_lab["lab_trades"],
        "lab_avg_return": strategy_lab["lab_avg_return"],
        "lab_profit_factor": strategy_lab["lab_profit_factor"],
        "category": COIN_CATEGORIES.get(symbol, ""),
    }


# =============================================================================
# DETECT FOMO COINS FROM ALL TICKERS
# =============================================================================
def detect_fomo_coins(all_tickers):
    """
    Deteksi koin yang lagi naik tajam dari seluruh ticker Indodax.
    Returns list of dicts, sorted by change descending.
    """
    fomo_list = []
    for pair, info in all_tickers.items():
        if not pair.endswith("_idr"):
            continue
        change = info.get("change_pct", 0)
        vol = info.get("vol_idr", 0)
        price = info.get("price", 0)
        if change > 5 and vol > 100_000_000:
            sym = pair.replace("_idr", "").upper()
            fomo_list.append({
                "symbol": sym,
                "pair": pair,
                "price": price,
                "change": change,
                "vol_idr": vol,
            })

    fomo_list.sort(key=lambda x: x["change"], reverse=True)
    return fomo_list


# =============================================================================
# COMPUTE MARKET OVERVIEW
# =============================================================================
def compute_market_overview(all_tickers):
    """Hitung statistik market-wide."""
    idr_pairs = {k: v for k, v in all_tickers.items() if k.endswith("_idr")}
    if not idr_pairs:
        mode = "defensive"
        rule = MARKET_MODE_RULES[mode]
        return {
            "total_volume": 0,
            "gainers": 0,
            "losers": 0,
            "total_pairs": 0,
            "avg_change": 0,
            "breadth_pct": 0,
            "mode": mode,
            "mode_label": rule["label"],
            "mode_description": rule["description"],
            "mode_color": rule["color"],
            "allocation_multiplier": rule["allocation_multiplier"],
            "score_adjustment": rule["score_adjustment"],
        }

    changes = [v["change_pct"] for v in idr_pairs.values()]
    total_vol = sum(v["vol_idr"] for v in idr_pairs.values())
    gainers = sum(1 for c in changes if c > 0)
    losers = sum(1 for c in changes if c < 0)
    total_pairs = len(idr_pairs)
    avg_change = round(sum(changes) / total_pairs, 2) if changes else 0
    breadth_pct = round((gainers / total_pairs) * 100, 1) if total_pairs else 0

    if breadth_pct >= 60 and avg_change >= 0.25:
        mode = "aggressive"
    elif breadth_pct < 42 or avg_change < -0.75:
        mode = "defensive"
    else:
        mode = "normal"
    rule = MARKET_MODE_RULES[mode]

    return {
        "total_volume": total_vol,
        "gainers": gainers,
        "losers": losers,
        "total_pairs": total_pairs,
        "avg_change": avg_change,
        "breadth_pct": breadth_pct,
        "mode": mode,
        "mode_label": rule["label"],
        "mode_description": rule["description"],
        "mode_color": rule["color"],
        "allocation_multiplier": rule["allocation_multiplier"],
        "score_adjustment": rule["score_adjustment"],
    }


# =============================================================================
# FETCH & PROCESS DATA
# =============================================================================
# Prefer shared ticker data from the bot daemon if it's fresh (<2 menit)
_shared_tickers, _shared_fetched, _shared_err = _read_shared_tickers()
now = datetime.now()
USE_SHARED = False

if _shared_tickers and _shared_fetched:
    _age = (now - _shared_fetched).total_seconds()
    if _age < 120:
        USE_SHARED = True

if USE_SHARED:
    # Reuse raw tickers from bot daemon — faster, no extra API call
    all_tickers = {}
    for pair, info in _shared_tickers.items():
        try:
            parsed = {
                "pair": pair,
                "price": float(info["last"]),
                "high": float(info.get("high", 0)),
                "low": float(info.get("low", 0)),
                "vol_idr": float(info.get("vol_idr", 0)),
                "change_pct": float(info.get("change", 0) or 0),
            }
            all_tickers[pair] = parsed
        except (KeyError, ValueError, TypeError):
            continue

    # Populate grouped data so all_prices gets filled
    data = {"main": {}, "micin": {}}
    for symbol, (ticker_pair, _) in MAIN_ASSETS.items():
        if ticker_pair in all_tickers:
            data["main"][symbol] = all_tickers[ticker_pair]
    for symbol, (ticker_pair, _) in MICIN_ASSETS.items():
        if ticker_pair in all_tickers:
            data["micin"][symbol] = all_tickers[ticker_pair]

    data_status = {
        "source": "live",
        "server_time": _shared_fetched.isoformat(),
        "error": None,
    }
else:
    # --- FRAGMENT UNTUK UPDATE MULUS ---
    @st.fragment(run_every=st.session_state.get("refresh_seconds", 15) if st.session_state.get("live_update", True) else None)
    def render_main_content():
        # 1. Fetch Data & Compute Stats
        data, all_tickers, data_status = fetch_all_data()
        if all_tickers:
            market_stats = compute_market_overview(all_tickers)
            st.session_state.last_grouped_data = data
            st.session_state.last_all_tickers = all_tickers
            st.session_state.last_market_stats = market_stats
            st.session_state.data_status = data_status
        else:
            data = st.session_state.get("last_grouped_data", {"main": {}, "micin": {}})
            all_tickers = st.session_state.get("last_all_tickers", {})
            market_stats = st.session_state.get("last_market_stats")
            if not all_tickers or not market_stats:
                loading_placeholder.markdown(
                    loading_markup(
                        "Menunggu data market...",
                        "Koneksi ke Indodax belum memberi data. App akan mencoba lagi otomatis.",
                    ),
                    unsafe_allow_html=True,
                )
                return
            data_status = {
                "source": "stale",
                "server_time": st.session_state.data_status.get("server_time"),
                "error": data_status.get("error"),
            }

        # 2. Metrics Header
        m_col1, m_col2, m_col3 = st.columns([1, 1, 1.2])
        with m_col1:
            st.metric("Gainers", f"🚀 {market_stats['gainers']}", delta_color="normal")
            st.metric("Losers", f"🔻 {market_stats['losers']}", delta_color="inverse")
        with m_col2:
            st.metric("Total Vol (24j)", f"Rp{format_volume(market_stats['total_volume'])}")
            st.metric("Avg Change", f"{market_stats['avg_change']:+.2f}%")
        with m_col3:
            m_color = "#22c55e" if market_stats["mode"] == "aggressive" else "#f59e0b" if market_stats["mode"] == "normal" else "#ef4444"
            live_hint = "LIVE" if data_status.get("source") == "live" else "DATA LAMA"
            st.markdown(
                f"""
                <div style="background:{m_color}22; border:1px solid {m_color}; border-radius:12px; padding:10px; text-align:center;">
                    <p style="margin:0; font-size:0.8rem; color:{m_color}; font-weight:700;">MODE MARKET · {live_hint}</p>
                    <h3 style="margin:0; color:{m_color}; text-transform:uppercase;">{market_stats['mode']}</h3>
                </div>
                """,
                unsafe_allow_html=True,
            )

        # 3. Call the rest of the UI
        render_dashboard_ui(data, all_tickers, data_status, market_stats)

def render_dashboard_ui(data, all_tickers, data_status, market_stats):
    # Logic for rendering the tabs and cards
    # Logic for rendering the tabs and cards
    # Build all_prices dict — ALL IDR pairs, not just curated lists

    # Build all_prices dict — ALL IDR pairs, not just curated lists
    all_prices = {}
    all_price_data = {}
    
    # First: curated Main + Micin
    for cat in ["main", "micin"]:
        for sym, pd_dict in data[cat].items():
            all_prices[sym] = pd_dict["price"]
            all_price_data[sym] = pd_dict
    
    # Then: ALL remaining IDR pairs from ticker data
    for pair, info in all_tickers.items():
        if not pair.endswith("_idr"):
            continue
        sym = pair.replace("_idr", "").upper()
        if sym in all_prices:
            continue  # sudah ada dari curated
        all_prices[sym] = info["price"]
        all_price_data[sym] = info
    
    # Fallback to last snapshot if API is dead
    if not all_prices and st.session_state.last_snapshot:
        all_prices = st.session_state.last_snapshot.copy()
        data_status["source"] = "stale"
    
    # Update price history (deduplicate — skip if identical to last snapshot)
    if all_prices:
        # Only append if prices actually changed
        if not st.session_state.last_snapshot or all_prices != st.session_state.last_snapshot:
            new_row = pd.DataFrame([all_prices], index=[datetime.now()])
            st.session_state.price_history = pd.concat(
                [st.session_state.price_history, new_row]
            ).tail(300)  # Keep last 300 snapshots
            st.session_state.last_snapshot = all_prices
        st.session_state.fetch_timestamp = datetime.now()
    
    # Compute FOMO from same data (no extra API call!)
    fomo_coins = detect_fomo_coins(all_tickers)
    
    # Compute market overview
    market_stats = compute_market_overview(all_tickers)
    
    # Load OHLC candles for stronger indicators. Cached for 15 minutes.
    historical_candles = {}
    if all_price_data:
        for symbol in all_price_data:
            pair_id = ALL_ASSETS.get(symbol, (None, None))[0]
            if pair_id:
                historical_candles[symbol] = fetch_ohlc_history(pair_id, tf="60", lookback_days=21)
    
    # Compute recommendations
    recs = []
    for s, p in all_prices.items():
        pd_entry = all_price_data.get(s, {"price": p, "change_pct": 0})
        recs.append(compute_recommendation(s, pd_entry, market_stats, historical_candles))
    
    recs_df = pd.DataFrame(recs).sort_values(["score", "risk_reward"], ascending=False) if recs else pd.DataFrame()
    
    # Separate buy/hold/skip
    decision_picks, backup_picks, watch_picks, decision_message, decision_board = build_decision_board(recs_df, market_stats)
    if not decision_board.empty and "decision_score" in decision_board.columns:
        recs_df = decision_board
    buy_recs = decision_picks.head(4) if not decision_picks.empty else pd.DataFrame()
    hold_skip_recs = recs_df[recs_df["action"] != "buy"] if not recs_df.empty else pd.DataFrame()
    mode_counts = recs_df["strategy_mode"].value_counts().to_dict() if not recs_df.empty else {}
    paper_trades = update_paper_trades(all_prices)
    
    # =============================================================================
    #                              UI STARTS HERE
    # =============================================================================
    loading_placeholder.empty()
    
    # --- HEADER ---
    st.markdown(
        """
        <div style="text-align:center; padding:1rem 0;">
            <h1 style="background:linear-gradient(to right, #fbbf24, #22c55e, #3b82f6); 
                       -webkit-background-clip:text; -webkit-text-fill-color:transparent;
                       background-clip:text;">
                💰 REKOMENDASI BELI CRYPTO HARI INI
            </h1>
            <p style="color:#888; font-size:1.1rem; font-weight:600; margin-top:-10px;">
                Live dari Indodax • Sinyal Real-time • Update Otomatis
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    
    # --- DATA STATUS BADGE ---
    status_source = data_status["source"]
    status_dot_class = {"live": "live", "stale": "stale", "offline": "offline", "loading": "offline"}.get(status_source, "offline")
    status_label = {"live": "LIVE", "stale": "DATA LAMA", "offline": "OFFLINE", "loading": "LOADING"}.get(status_source, "UNKNOWN")
    status_time_str = (
        f"🕐 {st.session_state.fetch_timestamp.strftime('%H:%M:%S')}"
        if st.session_state.fetch_timestamp
        else ""
    )
    
    st.markdown(
        f"""
        <div style="display:flex; justify-content:center; align-items:center; gap:1rem; margin-bottom:1rem;">
            <div class="freshness-badge">
                <span class="freshness-dot {status_dot_class}"></span>
                {status_label}
            </div>
            <span style="color:#666; font-size:0.8rem;">{status_time_str}</span>
            {f'<span style="color:#ef4444; font-size:0.75rem;">⚠️ {data_status["error"]}</span>' if data_status.get("error") else ""}
        </div>
        """,
        unsafe_allow_html=True,
    )
    
    if market_stats["total_pairs"] > 0:
        st.markdown(
            f"""
            <div style="background:#111; border:1px solid {market_stats['mode_color']}; border-radius:18px;
                        padding:1rem 1.2rem; margin:0 auto 1.2rem auto; max-width:980px;">
                <div style="display:flex; justify-content:space-between; gap:1rem; align-items:center; flex-wrap:wrap;">
                    <div>
                        <p style="margin:0; color:#888; font-size:0.78rem; text-transform:uppercase; letter-spacing:0.12em;">Mode Market & Bot</p>
                        <h3 style="margin:4px 0; color:{market_stats['mode_color']};">{market_stats['mode_label']}</h3>
                        <p style="margin:0; color:#aaa; font-size:0.88rem;">{market_stats['mode_description']}</p>
                    </div>
                    <div style="display:flex; gap:1rem; flex-wrap:wrap;">
                        <div style="text-align:center;">
                            <p style="margin:0; color:#888; font-size:0.75rem;">Breadth</p>
                            <p style="margin:2px 0 0 0; color:white; font-weight:900;">{market_stats['breadth_pct']:.1f}%</p>
                        </div>
                        <div style="text-align:center;">
                            <p style="margin:0; color:#888; font-size:0.75rem;">Avg 24j</p>
                            <p style="margin:2px 0 0 0; color:{'#22c55e' if market_stats['avg_change'] >= 0 else '#ef4444'}; font-weight:900;">{market_stats['avg_change']:+.2f}%</p>
                        </div>
                        <div style="text-align:center;">
                            <p style="margin:0; color:#888; font-size:0.75rem;">Risk Mode</p>
                            <p style="margin:2px 0 0 0; color:white; font-weight:900;">{market_stats['allocation_multiplier']:.2f}x size</p>
                        </div>
                    </div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    
    if mode_counts:
        st.markdown(
            f"""
            <div style="display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:0.75rem; margin:0 0 1.2rem 0;">
                <div style="background:#052e16; border:1px solid #16a34a; border-radius:14px; padding:0.9rem; text-align:center;">
                    <p style="color:#86efac; margin:0; font-size:0.75rem;">SWING / HOLD</p>
                    <p style="color:white; margin:4px 0 0 0; font-weight:900; font-size:1.4rem;">{mode_counts.get('SWING / HOLD', 0)}</p>
                </div>
                <div style="background:#431407; border:1px solid #f97316; border-radius:14px; padding:0.9rem; text-align:center;">
                    <p style="color:#fdba74; margin:0; font-size:0.75rem;">SCALP ONLY</p>
                    <p style="color:white; margin:4px 0 0 0; font-weight:900; font-size:1.4rem;">{mode_counts.get('SCALP ONLY', 0)}</p>
                </div>
                <div style="background:#082f49; border:1px solid #38bdf8; border-radius:14px; padding:0.9rem; text-align:center;">
                    <p style="color:#7dd3fc; margin:0; font-size:0.75rem;">WATCH VALUE</p>
                    <p style="color:white; margin:4px 0 0 0; font-weight:900; font-size:1.4rem;">{mode_counts.get('WATCH VALUE', 0)}</p>
                </div>
                <div style="background:#111827; border:1px solid #374151; border-radius:14px; padding:0.9rem; text-align:center;">
                    <p style="color:#d1d5db; margin:0; font-size:0.75rem;">WATCH / SKIP</p>
                    <p style="color:white; margin:4px 0 0 0; font-weight:900; font-size:1.4rem;">{mode_counts.get('WATCH', 0) + mode_counts.get('SKIP', 0)}</p>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    
    # --- SIMPLE DECISION BOARD ---
    st.markdown(
        "<h2 style='text-align:center; margin-top:1.5rem;'>🎯 JAWABAN CEPAT: PILIH YANG MANA?</h2>",
        unsafe_allow_html=True,
    )
    st.markdown(
        f"<p style='text-align:center; color:#94a3b8; margin-top:-0.4rem;'>{decision_message}</p>",
        unsafe_allow_html=True,
    )
    
    if decision_picks.empty:
        watch_text = ""
        if not watch_picks.empty:
            watch_names = ", ".join(watch_picks["symbol"].head(2).tolist())
            watch_text = f" Kandidat watchlist: {watch_names}."
        st.info(
            "Saat ini bot belum menemukan setup beli yang cukup bersih. "
            "Mode paling aman: tunggu candle berikutnya, jangan paksa entry." + watch_text
        )
    else:
        primary = decision_picks.iloc[0]
        primary_link = build_trade_link(primary["symbol"])
        primary_size = max(1.0, min(primary["allocation_pct"], 6.0))
        st.markdown(
            f"""
            <div style="background:#08111f; border:2px solid #22c55e; border-radius:18px;
                        padding:1.2rem; margin:0.8rem 0 1rem 0;">
                <div style="display:flex; justify-content:space-between; gap:1rem; align-items:center; flex-wrap:wrap;">
                    <div style="min-width:240px;">
                        <p style="margin:0; color:#86efac; font-size:0.78rem; text-transform:uppercase; letter-spacing:0.12em; font-weight:900;">
                            Pilihan Utama
                        </p>
                        <h2 style="margin:0.15rem 0; color:white; text-align:left !important;">{primary['symbol']} · {primary['label']}</h2>
                        <p style="margin:0; color:#cbd5e1;">
                            {format_idr(primary['price'])} · Score {primary['score']}/100 · Decision {primary['decision_score']:.1f}
                        </p>
                    </div>
                    <div style="display:flex; gap:1.2rem; flex-wrap:wrap;">
                        <div>
                            <p style="margin:0; color:#94a3b8; font-size:0.75rem;">Beli Maks</p>
                            <p style="margin:2px 0 0 0; color:#38bdf8; font-weight:900; font-size:1.35rem;">{primary_size:.1f}% modal</p>
                        </div>
                        <div>
                            <p style="margin:0; color:#94a3b8; font-size:0.75rem;">Target</p>
                            <p style="margin:2px 0 0 0; color:#fbbf24; font-weight:900; font-size:1.35rem;">{format_idr(primary['target_price'])}</p>
                        </div>
                        <div>
                            <p style="margin:0; color:#94a3b8; font-size:0.75rem;">Stop</p>
                            <p style="margin:2px 0 0 0; color:#ef4444; font-weight:900; font-size:1.35rem;">{format_idr(primary['stop_loss'])}</p>
                        </div>
                        <div>
                            <p style="margin:0; color:#94a3b8; font-size:0.75rem;">ML</p>
                            <p style="margin:2px 0 0 0; color:#bfdbfe; font-weight:900; font-size:1.35rem;">{primary['ml_probability']:.1f}%</p>
                        </div>
                        <div>
                            <p style="margin:0; color:#94a3b8; font-size:0.75rem;">Rapor Candle</p>
                            <p style="margin:2px 0 0 0; color:{primary['backtest_color']}; font-weight:900; font-size:1.35rem;">{primary['backtest_winrate']:.1f}%</p>
                        </div>
                    </div>
                    <a href="{primary_link}" target="_blank" style="text-decoration:none;">
                        <div style="background:#22c55e; color:#07111f; padding:12px 16px; border-radius:12px; font-weight:900;">
                            BUKA MARKET ↗
                        </div>
                    </a>
                </div>
                <p style="margin:0.85rem 0 0 0; color:#9ca3af; font-size:0.86rem;">
                    Kenapa ini dipilih: {primary['reason']} · {primary['strategy_note']} · Risk {primary['risk_level']}
                </p>
                <p style="margin:0.35rem 0 0 0; color:{primary['backtest_color']}; font-size:0.84rem; font-weight:800;">
                    Rapor candle: {primary['backtest_label']} · {primary['backtest_trades']} setup · Avg {primary['backtest_avg_return']:+.2f}% · PF {primary['backtest_profit_factor']:.2f}
                </p>
                <p style="margin:0.35rem 0 0 0; color:#7dd3fc; font-size:0.84rem; font-weight:800;">
                    TA+: ATR {primary['atr_pct']:.2f}% · MFI {primary['mfi']:.1f} · OBV {primary['obv_trend']} · Supertrend {primary['supertrend_bias']} · Candle {primary['candle_signal']}
                </p>
                <p style="margin:0.35rem 0 0 0; color:#c4b5fd; font-size:0.84rem; font-weight:800;">
                    Strategy Lab: {primary['lab_best_strategy']} · Winrate {primary['lab_winrate']:.1f}% · {primary['lab_trades']} trade · Avg {primary['lab_avg_return']:+.2f}%
                </p>
                <p style="margin:0.35rem 0 0 0; color:{primary['agent_verdict_color']}; font-size:0.86rem; font-weight:900;">
                    Agent Committee: {primary['agent_verdict']} · Net {primary['agent_net_score']}/100 · Bull {primary['agent_bull_score']} vs Bear {primary['agent_bear_score']} · {primary['agent_note']}
                </p>
                <p style="margin:0.25rem 0 0 0; color:#94a3b8; font-size:0.8rem;">
                    Bull: {primary['agent_bull_case']}<br>
                    Bear: {primary['agent_bear_case']}
                </p>
                <p style="margin:0.35rem 0 0 0; color:#cbd5e1; font-size:0.84rem;">
                    Aturan anti-bingung: entry bertahap 50/30/20, jangan ambil lebih dari 1 coin utama sekaligus, stop kalau harga tembus stop loss.
                </p>
            </div>
            """,
            unsafe_allow_html=True,
        )

        paper_col1, paper_col2 = st.columns([1, 2])
        with paper_col1:
            paper_guard = compute_paper_risk_guard(paper_trades)
            disable_paper = (
                has_open_paper_trade(primary["symbol"])
                or primary["agent_verdict"] in {"TUNGGU", "DITOLAK RISK MANAGER"}
                or not paper_guard["allowed"]
            )
            if st.button("🧪 Masukkan Paper Trade", disabled=disable_paper, width="stretch", key=f"paper_primary_{primary['symbol']}"):
                ok, message = add_paper_trade_from_signal(primary)
                if ok:
                    st.success(message)
                    st.rerun()
                else:
                    st.warning(message)
        with paper_col2:
            if has_open_paper_trade(primary["symbol"]):
                st.caption(f"🧪 {primary['symbol']} sudah dipantau di Paper Trading.")
            elif primary["agent_verdict"] in {"TUNGGU", "DITOLAK RISK MANAGER"}:
                st.caption("Risk manager belum approve, jadi paper trade dikunci dulu.")
            elif not paper_guard["allowed"]:
                st.caption(f"Risk guard aktif: {paper_guard['reason']}")
            else:
                st.caption("Paper trade hanya simulasi. Cocok untuk mengukur sinyal sebelum pakai uang asli.")
    
        # --- AI & CHART SECTION (Stacked for better UI) ---
        st.markdown("---")
        
        # AI Narrative Card
        st.markdown("#### 💬 AI Market Narrator (DeepSeek)")
        with st.container():
            st.markdown(
                """
                <div style="background:#0f172a; border:1px solid #1e293b; border-radius:16px; padding:1.5rem; margin-bottom:1rem;">
                """, 
                unsafe_allow_html=True
            )
            # Hanya update AI setiap 15 menit atau kalau koin berubah (efisiensi token)
            narrative = get_ai_market_narrative(
                primary["symbol"], 
                primary["label"], 
                primary["score"], 
                market_stats.get("mode", "normal"),
                primary["reason"]
            )
            st.write(narrative)
            st.markdown("</div>", unsafe_allow_html=True)
            st.caption("🤖 Analisa dinamis oleh AI berdasarkan data real-time koin pilihan.")
    
        # Live Chart Card
        st.markdown(f"#### 📈 Live Chart: {primary['symbol']}")
        with st.container():
            st.markdown(
                """
                <div style="background:#111; border:1px solid #27272a; border-radius:16px; padding:10px; margin-bottom:2rem;">
                """, 
                unsafe_allow_html=True
            )
            render_tradingview_widget(primary["symbol"], height=500)
            st.markdown("</div>", unsafe_allow_html=True)
    
        if len(decision_picks) > 1 or not backup_picks.empty:
            compact_picks = pd.concat([decision_picks.iloc[1:], backup_picks]).drop_duplicates("symbol").head(3)
            if not compact_picks.empty:
                st.markdown(
                    "<p style='color:#94a3b8; font-weight:800; margin:0.4rem 0;'>Cadangan kalau pilihan utama belum masuk entry:</p>",
                    unsafe_allow_html=True,
                )
                cols = st.columns(min(3, len(compact_picks)))
                for i, row in enumerate(compact_picks.to_dict("records")):
                    with cols[i % len(cols)]:
                        st.markdown(
                            f"""
                            <div style="background:#111827; border:1px solid #374151; border-radius:14px; padding:0.9rem;">
                                <p style="margin:0; color:white; font-weight:900;">{row['symbol']} · {row['strategy_mode']}</p>
                                <p style="margin:4px 0; color:#fbbf24; font-weight:800;">{format_idr(row['price'])}</p>
                            <p style="margin:2px 0; color:#94a3b8; font-size:0.8rem;">Score {row['score']}/100 · ML {row['ml_probability']:.1f}% · Risk {row['risk_level']}</p>
                            <p style="margin:2px 0; color:{row['backtest_color']}; font-size:0.8rem;">Rapor {row['backtest_winrate']:.1f}% · {row['backtest_trades']} setup · {row['backtest_label']}</p>
                            <p style="margin:2px 0; color:{row['agent_verdict_color']}; font-size:0.8rem;">Agent {row['agent_verdict']} · Net {row['agent_net_score']}/100</p>
                            <p style="margin:2px 0; color:#c4b5fd; font-size:0.8rem;">Lab {row['lab_best_strategy']} · {row['lab_winrate']:.1f}%</p>
                            <p style="margin:2px 0; color:#38bdf8; font-size:0.8rem;">Size max {min(row['allocation_pct'], 4.0):.1f}% · Target {format_idr(row['target_price'])}</p>
                        </div>
                            """,
                            unsafe_allow_html=True,
                        )
    
    # --- OFFLINE / ERROR STATE ---
    if status_source in ("offline",) and not all_prices:
        st.error(
            f"🚫 **Gagal mengambil data dari Indodax.** \n\n"
            f"*{data_status.get('error', 'Unknown error')}*\n\n"
            "Coba refresh halaman atau periksa koneksi internet kamu."
        )
        st.stop()
    
        st.markdown("### 📱 GABUNG KOMUNITAS")
        st.markdown(
            f"""
            <a href="{TELEGRAM_COMMUNITY}" target="_blank" style="text-decoration:none;">
                <div style="background:linear-gradient(135deg, #1d4ed8, #7c3aed); color:white; 
                            text-align:center; padding:14px; border-radius:14px; font-weight:700;
                            transition:all 0.2s ease; box-shadow:0 4px 20px rgba(124,58,237,0.3);">
                    <i class="fa-brands fa-telegram"></i> JOIN GRUP SINYAL PREMIUM 🚀
                </div>
            </a>
            """,
            unsafe_allow_html=True,
        )
    
        st.divider()
    
        # --- RESET BUTTON ---
        if st.button("🗑️ RESET DATA", width="stretch", help="Hapus riwayat harga"):
            st.session_state.price_history = pd.DataFrame()
            st.session_state.last_snapshot = {}
            st.session_state.fetch_timestamp = None
            st.cache_data.clear()
            st.rerun()
    
        st.caption(f"💡 Data real-time setiap {refresh_seconds} detik • {datetime.now().strftime('%H:%M:%S')}")
    
    # =============================================================================
    #  🏆 HERO SECTION — TOP BUY RECOMMENDATION
    # =============================================================================
    if not buy_recs.empty:
        top = buy_recs.iloc[0]
        pair_top = ALL_ASSETS.get(top["symbol"], (f"{top['symbol'].lower()}_idr", ""))[0]
        pair_url_top = pair_top.upper().replace("_", "")
        trade_link_top = f"https://indodax.com/market/{pair_url_top}?ref=narwanpratanta"
    
        daily_cls = "profit-badge" if top["daily_change"] >= 0 else "loss-badge"
    
        st.markdown(
            f"""
            <div class="rekomendasi-hero">
                <p style="color:#10b981; font-weight:800; letter-spacing:0.25em; margin:0; font-size:0.9rem;">
                    🔥 PILIHAN UTAMA HARI INI 🔥
                </p>
                <h2 style="font-size:3rem; margin:0.3rem 0; color:white; position:relative; z-index:1;">
                    {top['symbol']}
                </h2>
                <p class="price-tag" style="position:relative; z-index:1;">{format_idr(top['price'])}</p>
                <p style="font-size:1.3rem; font-weight:800; margin:0.5rem 0; position:relative; z-index:1;">
                    <span class="{daily_cls}">{top['label']}</span>
                </p>
                <div style="display:flex; justify-content:center; gap:2rem; margin:1.2rem 0; flex-wrap:wrap; position:relative; z-index:1;">
                    <div>
                        <p style="color:#888; margin:0; font-size:0.75rem; text-transform:uppercase; letter-spacing:0.1em;">Potensi Untung</p>
                        <p style="color:#22c55e; font-weight:900; font-size:1.6rem; margin:4px 0 0 0;">+{top['potential_gain_pct']}%</p>
                    </div>
                    <div>
                        <p style="color:#888; margin:0; font-size:0.75rem; text-transform:uppercase; letter-spacing:0.1em;">Target Jual</p>
                        <p style="color:#fbbf24; font-weight:900; font-size:1.6rem; margin:4px 0 0 0;">{format_idr(top['target_price'])}</p>
                    </div>
                    <div>
                        <p style="color:#888; margin:0; font-size:0.75rem; text-transform:uppercase; letter-spacing:0.1em;">Untung dr 1JT</p>
                        <p style="color:#22c55e; font-weight:900; font-size:1.6rem; margin:4px 0 0 0;">{format_idr(top['profit_1jt'])}</p>
                    </div>
                    <div>
                        <p style="color:#888; margin:0; font-size:0.75rem; text-transform:uppercase; letter-spacing:0.1em;">Stop Loss</p>
                        <p style="color:#ef4444; font-weight:900; font-size:1.6rem; margin:4px 0 0 0;">{format_idr(top['stop_loss'])}</p>
                    </div>
                    <div>
                        <p style="color:#888; margin:0; font-size:0.75rem; text-transform:uppercase; letter-spacing:0.1em;">Risk/Reward</p>
                        <p style="color:#38bdf8; font-weight:900; font-size:1.6rem; margin:4px 0 0 0;">1:{top['risk_reward']:.2f}</p>
                    </div>
                    <div>
                        <p style="color:#888; margin:0; font-size:0.75rem; text-transform:uppercase; letter-spacing:0.1em;">Score Bot</p>
                        <p style="color:white; font-weight:900; font-size:1.6rem; margin:4px 0 0 0;">{top['score']}/100</p>
                    </div>
                    <div>
                        <p style="color:#888; margin:0; font-size:0.75rem; text-transform:uppercase; letter-spacing:0.1em;">Max Size</p>
                        <p style="color:#38bdf8; font-weight:900; font-size:1.6rem; margin:4px 0 0 0;">{top['allocation_pct']:.1f}%</p>
                    </div>
                </div>
                <div style="display:flex; justify-content:center; gap:1rem; flex-wrap:wrap; margin:0.6rem 0 1rem 0; position:relative; z-index:1;">
                    <span style="background:#052e16; border:1px solid #16a34a; color:#86efac; padding:8px 14px; border-radius:12px; font-weight:800;">TP1 {format_idr(top['take_profit_1'])}</span>
                    <span style="background:#052e16; border:1px solid #16a34a; color:#86efac; padding:8px 14px; border-radius:12px; font-weight:800;">TP2 {format_idr(top['take_profit_2'])}</span>
                    <span style="background:#052e16; border:1px solid #16a34a; color:#86efac; padding:8px 14px; border-radius:12px; font-weight:800;">TP3 {format_idr(top['take_profit_3'])}</span>
                    <span style="background:#111827; border:1px solid #38bdf8; color:#7dd3fc; padding:8px 14px; border-radius:12px; font-weight:800;">Trailing {top['trailing_stop_pct']:.1f}%</span>
                </div>
                <a href="{trade_link_top}" target="_blank" class="buy-button" style="position:relative; z-index:1;">
                    🔥 BELI {top['symbol']} SEKARANG DI INDODAX 🔥
                </a>
                <p style="color:#666; font-size:0.75rem; margin-top:10px; position:relative; z-index:1;">
                    24j: {'+' if top['daily_change'] >= 0 else ''}{top['daily_change']}% &nbsp;|&nbsp; 
                    Momentum: {top['momentum']} &nbsp;|&nbsp;
                    Risk: {top['risk_level']} &nbsp;|&nbsp;
                    Vol: {format_volume(top['volume_idr'])}
                </p>
                <p style="color:#94a3b8; font-size:0.78rem; margin:6px 0 0 0; position:relative; z-index:1;">
                    Teknikal: RSI {top['rsi']:.1f} · EMA {top['ema_bias']} ({top['ema_trend_pct']:+.2f}%) · MACD {top['macd_signal']} · Data {top['quality']} ({top['indicator_source']})
                </p>
                <p style="color:#cbd5e1; font-size:0.82rem; margin:6px 0 0 0; position:relative; z-index:1;">
                    Mode: <b style="color:{top['strategy_color']};">{top['strategy_mode']}</b> · Value {top['value_score']}/100 ({top['value_label']}) · {top['strategy_note']}
                </p>
                <p style="color:#bfdbfe; font-size:0.8rem; margin:6px 0 0 0; position:relative; z-index:1;">
                    ML: <b>{top['ml_label']}</b> · Prob naik {top['ml_probability']:.1f}% · Expected {top['ml_expected_return']:+.2f}% · Confidence {top['ml_confidence']}
                </p>
                <p style="color:{top['backtest_color']}; font-size:0.8rem; margin:6px 0 0 0; position:relative; z-index:1; font-weight:800;">
                    Rapor candle: {top['backtest_label']} · Winrate {top['backtest_winrate']:.1f}% dari {top['backtest_trades']} setup · Avg {top['backtest_avg_return']:+.2f}%
                </p>
                <p style="color:{top['agent_verdict_color']}; font-size:0.8rem; margin:6px 0 0 0; position:relative; z-index:1; font-weight:900;">
                    Agent Committee: {top['agent_verdict']} · Net {top['agent_net_score']}/100 · Bull {top['agent_bull_score']} vs Bear {top['agent_bear_score']}
                </p>
                <p style="color:#9ca3af; font-size:0.82rem; margin:6px 0 0 0; position:relative; z-index:1;">
                    Alasan: {top['reason']}
                </p>
                <p style="color:#94a3b8; font-size:0.78rem; margin:6px 0 0 0; position:relative; z-index:1;">
                    Value: {top['value_reason']}
                </p>
                <p style="color:#cbd5e1; font-size:0.82rem; margin:6px 0 0 0; position:relative; z-index:1;">
                    Plan: {top['position_plan']} Exit: {top['exit_rule']}
                </p>
            </div>
            """,
            unsafe_allow_html=True,
        )
    
        # --- PRICE SPARKLINE FOR TOP PICK ---
        top_series = get_series(top["symbol"])
        if len(top_series) >= 3:
            st.caption(f"📈 Trend harga {top['symbol']} (riwayat sesi ini)")
            st.line_chart(
                top_series,
                height=120,
            )
    else:
        # No buy recommendations
        st.info(
            "🔍 **Belum ada rekomendasi BELI saat ini.** "
            "Market sedang dalam kondisi kurang favorable. Cek lagi nanti atau pantau koin yang TAHAN dulu.",
        )
    
    # =============================================================================
    #  🟢 MORE BUY RECOMMENDATIONS (positions 2-6)
    # =============================================================================
    if len(buy_recs) > 1:
        st.markdown(
            "<h2 style='text-align:center; margin-top:2rem;'>🟢 CADANGAN, BUKAN WAJIB DIBELI</h2>",
            unsafe_allow_html=True,
        )
        sub_buys = buy_recs.iloc[1:].to_dict("records")
        n_cols = min(len(sub_buys), 5)
        cols = st.columns(n_cols) if n_cols > 0 else []
    
        for i, row in enumerate(sub_buys):
            pair_r = ALL_ASSETS.get(row["symbol"], (f"{row['symbol'].lower()}_idr", ""))[0]
            pair_url_r = pair_r.upper().replace("_", "")
            trade_link_r = f"https://indodax.com/market/{pair_url_r}?ref=narwanpratanta"
    
            col_idx = i % n_cols
            with cols[col_idx]:
                st.markdown(
                    f"""
                    <div class="rekomendasi-card">
                        <h3 style="margin:0; color:white; font-size:1.2rem;">{row['symbol']}</h3>
                        <p style="font-size:1.2rem; font-weight:800; color:#fbbf24; margin:6px 0;">
                            {format_idr(row['price'])}
                        </p>
                        <span class="profit-badge">+{row['potential_gain_pct']}% potensi</span>
                        <div style="margin:10px 0; font-size:0.82rem; color:#888;">
                            <p style="margin:3px 0;">🎯 Target: <b style="color:#fbbf24;">{format_idr(row['target_price'])}</b></p>
                            <p style="margin:3px 0;">🛑 Stop: <b style="color:#ef4444;">{format_idr(row['stop_loss'])}</b></p>
                            <p style="margin:3px 0;">🧭 Mode: <b style="color:{row['strategy_color']};">{row['strategy_mode']}</b></p>
                            <p style="margin:3px 0;">📊 24j: {'+' if row['daily_change'] >= 0 else ''}{row['daily_change']}%</p>
                            <p style="margin:3px 0;">🧠 Trading: <b style="color:white;">{row['score']}/100</b> · Value: <b style="color:{row['value_color']};">{row['value_score']}/100</b></p>
                            <p style="margin:3px 0;">🤖 ML: <b style="color:#bfdbfe;">{row['ml_probability']:.1f}%</b> {row['ml_label']} · {row['ml_confidence']}</p>
                            <p style="margin:3px 0;">📈 Rapor: <b style="color:{row['backtest_color']};">{row['backtest_winrate']:.1f}%</b> · {row['backtest_trades']} setup · {row['backtest_label']}</p>
                            <p style="margin:3px 0;">🏛️ Agent: <b style="color:{row['agent_verdict_color']};">{row['agent_verdict']}</b> · Net {row['agent_net_score']}/100</p>
                            <p style="margin:3px 0;">🧪 Lab: <b style="color:#c4b5fd;">{row['lab_best_strategy']}</b> · {row['lab_winrate']:.1f}%</p>
                            <p style="margin:3px 0;">📦 Size: <b style="color:#38bdf8;">{row['allocation_pct']:.1f}%</b></p>
                            <p style="margin:3px 0;">⚖️ R/R: <b style="color:#38bdf8;">1:{row['risk_reward']:.2f}</b></p>
                            <p style="margin:3px 0;">🧯 Risk: <b style="color:{row['risk_color']};">{row['risk_level']}</b></p>
                            <p style="margin:3px 0;">🎯 TP: <b style="color:#22c55e;">{format_idr(row['take_profit_1'])}</b> / <b style="color:#22c55e;">{format_idr(row['take_profit_2'])}</b></p>
                            <p style="margin:3px 0;">📐 RSI {row['rsi']:.1f} · EMA {row['ema_bias']} · MACD {row['macd_signal']}</p>
                        </div>
                        <p style="color:#777; font-size:0.72rem; line-height:1.45; min-height:34px; margin:4px 0 10px 0;">
                            {row['reason']}
                        </p>
                        <a href="{trade_link_r}" target="_blank" style="text-decoration:none;">
                            <div style="background:#22c55e; color:white; padding:10px; border-radius:12px; 
                                        font-weight:700; font-size:0.9rem; transition:all 0.2s;">
                                BELI SEKARANG ↗
                            </div>
                        </a>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
    
    # =============================================================================
    #  🚀 FOMO COINS — COINS PUMPING HARD
    # =============================================================================
    if fomo_coins:
        st.markdown(
            "<h2 style='text-align:center; margin-top:2rem;'>🚀 KOIN LAGI NAIK TAJAM (FOMO)</h2>",
            unsafe_allow_html=True,
        )
        st.markdown(
            "<p style='text-align:center; color:#fbbf24; font-size:0.9rem;'>⚠️ Hati-hati FOMO! Koreksi bisa terjadi kapan saja. High risk, high reward.</p>",
            unsafe_allow_html=True,
        )
    
        # Display up to 10 FOMO coins in a responsive grid
        display_fomo = fomo_coins[:10]
        fomo_n_cols = min(len(display_fomo), 5)
        fomo_cols = st.columns(fomo_n_cols)
    
        for i, coin in enumerate(display_fomo):
            with fomo_cols[i % fomo_n_cols]:
                pair_url = coin["pair"].upper().replace("_", "")
                trade_link_fomo = f"https://indodax.com/market/{pair_url}?ref=narwanpratanta"
    
                if coin["change"] > 15:
                    emoji_fomo = "🚀"
                    level = "FOMO GILA"
                    bg = "linear-gradient(135deg, #7c2d12, #9a3412)"
                    border_color = "#f97316"
                elif coin["change"] > 8:
                    emoji_fomo = "🔥"
                    level = "FOMO"
                    bg = "linear-gradient(135deg, #1a0a2e, #2d1b4e)"
                    border_color = "#fbbf24"
                else:
                    emoji_fomo = "📈"
                    level = "Pumping"
                    bg = "linear-gradient(135deg, #0f172a, #1e293b)"
                    border_color = "#fbbf24"
    
                st.markdown(
                    f"""
                    <div class="fomo-card" style="background:{bg}; border-color:{border_color};">
                        <p style="font-size:2rem; margin:0;">{emoji_fomo}</p>
                        <p style="font-weight:900; font-size:1.2rem; color:white; margin:6px 0;">
                            {coin['symbol']}
                        </p>
                        <p style="color:#fbbf24; font-weight:800; font-size:1.1rem; margin:6px 0;">
                            +{coin['change']:.2f}%
                        </p>
                        <p style="color:#888; font-size:0.75rem; margin:2px 0;">{level}</p>
                        <p style="color:#666; font-size:0.7rem; margin:2px 0;">
                            Vol: {format_volume(coin['vol_idr'])}
                        </p>
                        <a href="{trade_link_fomo}" target="_blank" style="text-decoration:none;">
                            <div style="background:#fbbf24; color:#0a0a0a; padding:8px; border-radius:10px; 
                                        font-weight:800; font-size:0.8rem; margin-top:8px;">
                                🔥 BELI SEKARANG
                            </div>
                        </a>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
                
    # =============================================================================
    #  📊 TABS — FULL TABLE + PREMIUM
    # =============================================================================
    t1, t2, t3, t4, t5 = st.tabs(["🔎 SMART SCANNER", "📋 WATCHLIST", "📈 PERF TRACKER", "💎 JOIN PREMIUM", "📊 SEMUA COIN & DATA"])
    
    # TAB 1: Smart Scanner (dipindah ke atas — fitur find/search)
    with t1:
        st.markdown("### 🔎 Smart Scanner")
        st.caption("Filter cepat untuk menemukan coin yang sesuai gaya trading kamu.")
    
        if not recs_df.empty:
            scanner_left, scanner_mid, scanner_right = st.columns([1.1, 1, 1])
            with scanner_left:
                keyword = st.text_input("Cari coin", placeholder="BTC, ETH, DOGE...")
            with scanner_mid:
                filter_mode = st.selectbox("Filter rekomendasi", ["Semua", "Beli saja", "Tahan", "Hindari/Jangan beli"])
            with scanner_right:
                sort_mode = st.selectbox("Urutkan", ["Score bot", "Agent committee", "Strategy lab", "TA+ score", "Rapor candle", "ML probability", "Value score", "Tech score", "Potensi untung", "Risk/reward", "Max size", "Volume", "Momentum", "Perubahan 24j"])
    
            min_volume = st.slider("Minimum volume 24j", 0, 50_000_000_000, 100_000_000, step=100_000_000, format="Rp%d")
    
            scan_df = recs_df.copy()
            if keyword:
                scan_df = scan_df[scan_df["symbol"].str.contains(keyword.upper(), na=False)]
            if filter_mode == "Beli saja":
                scan_df = scan_df[scan_df["action"] == "buy"]
            elif filter_mode == "Tahan":
                scan_df = scan_df[scan_df["action"] == "hold"]
            elif filter_mode == "Hindari/Jangan beli":
                scan_df = scan_df[scan_df["action"] == "skip"]
            scan_df = scan_df[scan_df["volume_idr"] >= min_volume]
    
            sort_map = {
                "Score bot": "score",
                "Agent committee": "agent_net_score",
                "Strategy lab": "lab_score",
                "TA+ score": "ta_plus_score",
                "Rapor candle": "backtest_winrate",
                "ML probability": "ml_probability",
                "Value score": "value_score",
                "Tech score": "technical_score",
                "Potensi untung": "potential_gain_pct",
                "Risk/reward": "risk_reward",
                "Max size": "allocation_pct",
                "Volume": "volume_idr",
                "Momentum": "momentum",
                "Perubahan 24j": "daily_change",
            }
            scan_df = scan_df.sort_values(sort_map[sort_mode], ascending=False)
    
            if scan_df.empty:
                st.info("Tidak ada coin yang cocok dengan filter ini.")
            else:
                scan_cards = scan_df.head(12).to_dict("records")
                card_cols = st.columns(3)
                for i, row in enumerate(scan_cards):
                    pair_scan = ALL_ASSETS.get(row["symbol"], (f"{row['symbol'].lower()}_idr", ""))[0]
                    trade_link_scan = f"https://indodax.com/market/{pair_scan.upper().replace('_', '')}?ref=narwanpratanta"
                    with card_cols[i % 3]:
                        st.markdown(
                            f"""
                            <div style="background:#111; border:1px solid #27272a; border-radius:16px; padding:1rem; min-height:245px;">
                                <div style="display:flex; justify-content:space-between; align-items:center; gap:8px;">
                                    <h3 style="margin:0; color:white;">{row['symbol']}</h3>
                                    <span style="background:{row['risk_color']}; color:white; padding:4px 10px; border-radius:99px; font-size:0.72rem; font-weight:800;">
                                        RISK {row['risk_level']}
                                    </span>
                                </div>
                                <p style="color:#fbbf24; font-weight:900; font-size:1.3rem; margin:8px 0 2px 0;">
                                    {format_idr(row['price'])}
                                </p>
                                <p style="color:{row['color']}; font-weight:800; margin:4px 0;">{row['label']}</p>
                                <p style="background:{row['strategy_color']}; color:#0a0a0a; display:inline-block; padding:4px 10px; border-radius:99px; font-size:0.75rem; font-weight:900; margin:4px 0;">
                                    {row['strategy_mode']}
                                </p>
                                <div style="display:grid; grid-template-columns:1fr 1fr; gap:8px; margin:10px 0; color:#888; font-size:0.78rem;">
                                    <span>24j<br><b style="color:{'#22c55e' if row['daily_change'] >= 0 else '#ef4444'};">{row['daily_change']:+.2f}%</b></span>
                                    <span>Trading<br><b style="color:white;">{row['score']}/100</b></span>
                                    <span>Value<br><b style="color:{row['value_color']};">{row['value_score']}/100</b></span>
                                    <span>ML<br><b style="color:#bfdbfe;">{row['ml_probability']:.1f}%</b></span>
                                    <span>R/R<br><b style="color:#38bdf8;">1:{row['risk_reward']:.2f}</b></span>
                                    <span>Max Size<br><b style="color:#38bdf8;">{row['allocation_pct']:.1f}%</b></span>
                                    <span>Rapor<br><b style="color:{row['backtest_color']};">{row['backtest_winrate']:.1f}%</b></span>
                                    <span>Setup<br><b style="color:white;">{row['backtest_trades']}</b></span>
                                    <span>Agent<br><b style="color:{row['agent_verdict_color']};">{row['agent_net_score']}</b></span>
                                    <span>Final<br><b style="color:{row['agent_verdict_color']};">{row['agent_risk_decision']}</b></span>
                                    <span>Lab<br><b style="color:#c4b5fd;">{row['lab_winrate']:.1f}%</b></span>
                                    <span>TA+<br><b style="color:#7dd3fc;">{row['ta_plus_score']:+.1f}</b></span>
                                </div>
                                <p style="color:#bfdbfe; font-size:0.76rem; line-height:1.45; margin:4px 0;">
                                    ML {row['ml_label']} · Expected {row['ml_expected_return']:+.2f}% · Confidence {row['ml_confidence']} · Sample {row['ml_samples']}
                                </p>
                                <p style="color:#888; font-size:0.76rem; line-height:1.45; margin:4px 0;">
                                    TP: <b style="color:#22c55e;">{format_idr(row['take_profit_1'])}</b> / <b style="color:#22c55e;">{format_idr(row['take_profit_2'])}</b> / <b style="color:#22c55e;">{format_idr(row['take_profit_3'])}</b><br>
                                    SL: <b style="color:#ef4444;">{format_idr(row['stop_loss'])}</b> · Trail {row['trailing_stop_pct']:.1f}%
                                </p>
                                <p style="color:#888; font-size:0.76rem; line-height:1.45; margin:4px 0;">
                                    RSI <b style="color:white;">{row['rsi']:.1f}</b> · EMA <b style="color:white;">{row['ema_bias']}</b> · MACD <b style="color:white;">{row['macd_signal']}</b><br>
                                    ATR <b style="color:white;">{row['atr_pct']:.2f}%</b> · MFI <b style="color:white;">{row['mfi']:.1f}</b> · ST <b style="color:white;">{row['supertrend_bias']}</b><br>
                                    S/R: <b style="color:#22c55e;">{format_idr(row['support'])}</b> / <b style="color:#fbbf24;">{format_idr(row['resistance'])}</b><br>
                                    Source: <b style="color:white;">{row['indicator_source']}</b> · Vol {row['volume_spike']}
                                </p>
                                <p style="color:#9ca3af; font-size:0.78rem; line-height:1.45; min-height:38px; margin:8px 0;">
                                    {row['reason']}
                                </p>
                                <p style="color:#94a3b8; font-size:0.74rem; line-height:1.45; min-height:34px; margin:6px 0;">
                                    Value: {row['value_reason']}
                                </p>
                                <a href="{trade_link_scan}" target="_blank" style="text-decoration:none;">
                                    <div style="background:#22c55e; color:white; padding:10px; border-radius:12px; text-align:center; font-weight:800;">
                                        BUKA MARKET ↗
                                    </div>
                                </a>
                            </div>
                            """,
                            unsafe_allow_html=True,
                        )
        else:
            st.warning("Scanner belum punya data. Coba refresh halaman.")
    
    with t2:
        st.markdown("### 📋 WATCHLIST KAMU")
        st.caption("Pantau coin favorit & dapatkan alert kalau harga tembus level kunci.")
    
        # Init watchlist di session state
        if "watchlist" not in st.session_state:
            st.session_state.watchlist = {}  # {symbol: {"added_at": datetime, "entry_price": float, "alert_above": float, "alert_below": float, "note": str}}
    
        wl_col1, wl_col2 = st.columns([1.5, 1])
        with wl_col1:
            wl_new_coin = st.selectbox("🪙 Tambah coin ke watchlist", [""] + sorted(all_prices.keys()), key="wl_select")
        with wl_col2:
            wl_alert_above = st.text_input("🔔 Alert jika >", placeholder="Harga (opsional)", key="wl_alert_above")
            wl_alert_below = st.text_input("🔔 Alert jika <", placeholder="Harga (opsional)", key="wl_alert_below")
            wl_note = st.text_input("📝 Catatan (opsional)", placeholder="e.g. tunggu break resistance", key="wl_note")
    
        if st.button("➕ Tambahkan ke Watchlist", disabled=(not wl_new_coin)):
            try:
                alert_above_val = float(wl_alert_above) if wl_alert_above.strip() else None
            except ValueError:
                alert_above_val = None
            try:
                alert_below_val = float(wl_alert_below) if wl_alert_below.strip() else None
            except ValueError:
                alert_below_val = None
    
            st.session_state.watchlist[wl_new_coin] = {
                "added_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "entry_price": all_prices.get(wl_new_coin, 0),
                "current_price": all_prices.get(wl_new_coin, 0),
                "alert_above": alert_above_val,
                "alert_below": alert_below_val,
                "note": wl_note,
                "last_alert": None,
            }
            st.success(f"✅ {wl_new_coin} masuk watchlist!")
            st.rerun()
    
        if st.session_state.watchlist:
            # Tampilkan watchlist dengan status live
            st.divider()
            st.markdown(f"**{len(st.session_state.watchlist)} coin dipantau**")
    
            for sym, wl in list(st.session_state.watchlist.items()):
                current_price = all_prices.get(sym, wl.get("entry_price", 0))
                entry_price = wl.get("entry_price", 0)
                change_from_entry = ((current_price - entry_price) / entry_price * 100) if entry_price > 0 else 0
                wl["current_price"] = current_price
    
                # Alert check
                alert_icon = ""
                alert_msg = ""
                above = wl.get("alert_above")
                below = wl.get("alert_below")
                if above and current_price >= above:
                    alert_icon = "🔔"
                    alert_msg = f"ALERT: Harga di atas {format_idr(above)}!"
                elif below and current_price <= below:
                    alert_icon = "🔔"
                    alert_msg = f"ALERT: Harga di bawah {format_idr(below)}!"
    
                # Get current recommendation
                wl_rec = recs_df[recs_df["symbol"] == sym].iloc[0].to_dict() if not recs_df.empty and sym in set(recs_df["symbol"]) else None
    
                change_clr = "#22c55e" if change_from_entry >= 0 else "#ef4444"
                st.markdown(
                    f"""
                    <div style="background:#111; border:1px solid {'#fbbf24' if alert_icon else '#27272a'}; border-radius:14px; padding:0.9rem; margin:6px 0;">
                        <div style="display:flex; justify-content:space-between; align-items:center; gap:1rem; flex-wrap:wrap;">
                            <div>
                                <b style="color:white; font-size:1.1rem;">{alert_icon} {sym}</b>
                                <span style="color:#888; font-size:0.75rem; margin-left:8px;">{wl.get('added_at', '')}</span>
                            </div>
                            <div style="text-align:right;">
                                <p style="margin:0; color:#fbbf24; font-weight:900;">{format_idr(current_price)}</p>
                                <p style="margin:2px 0 0 0; color:{change_clr}; font-size:0.8rem;">{' +' if change_from_entry >= 0 else ' '}{change_from_entry:+.2f}% dari entry</p>
                            </div>
                        </div>
                        {f'<p style="color:#fbbf24; font-weight:700; margin:6px 0 0 0;">{alert_msg}</p>' if alert_msg else ''}
                        {f'<p style="color:#bfdbfe; font-size:0.78rem; margin:6px 0 0 0;">Bot: <b>{wl_rec["label"]}</b> · Score {wl_rec["score"]}/100 · ML {wl_rec["ml_probability"]:.1f}% · Rapor {wl_rec["backtest_winrate"]:.1f}% · Agent <b style="color:{wl_rec["agent_verdict_color"]};">{wl_rec["agent_verdict"]}</b></p>' if wl_rec else ''}
                        <div style="display:flex; gap:1rem; margin:6px 0 0 0; font-size:0.75rem; color:#888; flex-wrap:wrap;">
                            <span>🔺 Alert >: {format_idr(above) if above else '-'}</span>
                            <span>🔻 Alert <: {format_idr(below) if below else '-'}</span>
                            <span>📝 {wl.get('note', '-')}</span>
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
    
            if st.button("🗑️ Kosongkan Watchlist"):
                st.session_state.watchlist = {}
                st.rerun()
        else:
            st.info("Watchlist kosong. Tambahkan coin yang mau kamu pantau!")
    
    with t3:
        st.markdown("### 📈 PERFORMANCE TRACKER")
        st.caption("Track akurasi rekomendasi bot dari waktu ke waktu. Data disimpan di session.")

        st.markdown("#### 🧪 Paper Trading Engine")
        st.caption("Simulasi posisi dari sinyal bot: entry virtual, pantau TP/SL/trailing, lalu hitung PnL tanpa uang asli.")
        paper_summary = summarize_paper_trades(paper_trades)
        p_col1, p_col2, p_col3, p_col4, p_col5 = st.columns(5)
        with p_col1:
            st.metric("Paper Trades", paper_summary["total"])
        with p_col2:
            st.metric("Open", paper_summary["open"])
        with p_col3:
            st.metric("Winrate", f"{paper_summary['winrate']}%")
        with p_col4:
            st.metric("Realized", format_idr(paper_summary["realized"]))
        with p_col5:
            st.metric("Floating", format_idr(paper_summary["floating"]))
        q_col1, q_col2, q_col3, q_col4 = st.columns(4)
        with q_col1:
            st.metric("Profit Factor", paper_summary["profit_factor"])
        with q_col2:
            st.metric("Expectancy", f"{paper_summary['expectancy']:+.2f}%")
        with q_col3:
            st.metric("Max Drawdown", format_idr(paper_summary["max_drawdown"]))
        with q_col4:
            guard = paper_summary["guard"]
            st.metric("Risk Guard", guard["status"], delta=f"{guard['open_exposure']:.1f}% open")
        if paper_summary["guard"]["status"] != "OK":
            st.warning(f"Risk guard aktif: {paper_summary['guard']['reason']}")

        if paper_trades:
            paper_rows = []
            for trade in reversed(paper_trades[-30:]):
                paper_rows.append({
                    "Coin": trade["symbol"],
                    "Status": trade["status"],
                    "Stage": trade["stage"],
                    "Entry": format_idr(trade["entry_price"]),
                    "Now/Exit": format_idr(trade.get("exit_price") or trade.get("current_price")),
                    "PnL %": f"{trade.get('pnl_pct', 0):+.2f}%",
                    "PnL 1JT": format_idr(trade.get("pnl_1jt", 0)),
                    "Size": f"{trade.get('size_pct', 0):.1f}%",
                    "Agent": trade.get("agent_verdict", "-"),
                    "Opened": trade.get("opened_at", "-"),
                    "Closed": trade.get("closed_at") or "-",
                })
            st.dataframe(pd.DataFrame(paper_rows), hide_index=True, width="stretch", height=320)
            reset_col1, reset_col2 = st.columns([1, 3])
            with reset_col1:
                if st.button("🗑️ Reset Paper", width="stretch"):
                    st.session_state.paper_trades = []
                    st.rerun()
            with reset_col2:
                st.caption("Reset hanya menghapus simulasi di sesi ini, tidak menyentuh data market atau rekomendasi.")
        else:
            st.info("Belum ada paper trade. Pakai tombol di pilihan utama untuk mulai simulasi.")

        st.divider()

        if not recs_df.empty:
            st.markdown("#### 🏛️ Agent Committee")
            st.caption("Versi ringan dari TradingAgents: bull analyst, bear analyst, risk manager, lalu portfolio verdict.")
            agent_df = recs_df.copy().sort_values(["agent_net_score", "decision_score", "score"], ascending=False)
            agent_metric1, agent_metric2, agent_metric3, agent_metric4 = st.columns(4)
            with agent_metric1:
                st.metric("Approved", int(agent_df["agent_verdict"].isin(["APPROVE", "APPROVE KECIL"]).sum()))
            with agent_metric2:
                st.metric("Wait/Reject", int(agent_df["agent_verdict"].isin(["TUNGGU", "DITOLAK RISK MANAGER"]).sum()))
            with agent_metric3:
                st.metric("Avg Net", f"{agent_df['agent_net_score'].mean():.1f}/100")
            with agent_metric4:
                top_agent = agent_df.iloc[0]["symbol"] if not agent_df.empty else "-"
                st.metric("Agent Pick", top_agent)

            agent_display = agent_df[
                [
                    "symbol",
                    "agent_verdict",
                    "agent_net_score",
                    "agent_bull_score",
                    "agent_bear_score",
                    "agent_bull_case",
                    "agent_bear_case",
                    "agent_note",
                ]
            ].head(12).copy()
            agent_display.columns = ["Coin", "Verdict", "Net", "Bull", "Bear", "Bull Case", "Bear Case", "Catatan"]
            st.dataframe(agent_display, hide_index=True, width="stretch", height=360)
            st.divider()

            st.markdown("#### 🧬 Strategy Lab")
            st.caption("VectorBT-lite: bandingkan gaya Trend Rider, Dip Buyer, Breakout, dan Calm Swing dari candle yang sama.")
            lab_df = recs_df[recs_df["lab_trades"] > 0].copy()
            if lab_df.empty:
                st.info("Belum cukup candle untuk strategy lab.")
            else:
                lab_df = lab_df.sort_values(["lab_score", "lab_winrate", "lab_avg_return"], ascending=False)
                lab_col1, lab_col2, lab_col3, lab_col4 = st.columns(4)
                with lab_col1:
                    st.metric("Coin Teralab", len(lab_df))
                with lab_col2:
                    st.metric("Avg Lab Winrate", f"{lab_df['lab_winrate'].mean():.1f}%")
                with lab_col3:
                    st.metric("Avg Lab Return", f"{lab_df['lab_avg_return'].mean():+.2f}%")
                with lab_col4:
                    st.metric("Best Lab", lab_df.iloc[0]["symbol"])
                lab_display = lab_df[
                    [
                        "symbol",
                        "lab_best_strategy",
                        "lab_score",
                        "lab_winrate",
                        "lab_trades",
                        "lab_avg_return",
                        "lab_profit_factor",
                        "agent_verdict",
                    ]
                ].head(12).copy()
                lab_display.columns = ["Coin", "Best Strategy", "Lab Score", "Winrate %", "Trades", "Avg Return %", "PF", "Agent"]
                st.dataframe(lab_display, hide_index=True, width="stretch", height=330)
            st.divider()

            st.markdown("#### 📐 TA+ Scanner")
            st.caption("Indikator ekstra ala library TA: ATR, MFI, OBV, Supertrend, dan candle pattern.")
            ta_df = recs_df.copy().sort_values(["ta_plus_score", "score"], ascending=False)
            ta_display = ta_df[
                [
                    "symbol",
                    "ta_plus_score",
                    "atr_pct",
                    "mfi",
                    "obv_trend",
                    "supertrend_bias",
                    "candle_signal",
                    "risk_level",
                ]
            ].head(12).copy()
            ta_display.columns = ["Coin", "TA+ Score", "ATR %", "MFI", "OBV", "Supertrend", "Candle", "Risk"]
            st.dataframe(ta_display, hide_index=True, width="stretch", height=330)
            st.divider()

            st.markdown("#### 🧪 Rapor Candle Otomatis")
            st.caption("Simulasi historis ringan dari candle 1 jam: apakah setup serupa lebih sering kena target atau stop.")
            bt_df = recs_df[recs_df["backtest_trades"] >= 6].copy()
            if bt_df.empty:
                st.info("Belum cukup setup historis untuk bikin rapor otomatis.")
            else:
                bt_df = bt_df.sort_values(["backtest_winrate", "backtest_avg_return", "score"], ascending=False)
                bt_metric1, bt_metric2, bt_metric3, bt_metric4 = st.columns(4)
                with bt_metric1:
                    st.metric("Coin Teruji", len(bt_df))
                with bt_metric2:
                    st.metric("Avg Winrate", f"{bt_df['backtest_winrate'].mean():.1f}%")
                with bt_metric3:
                    st.metric("Avg Return", f"{bt_df['backtest_avg_return'].mean():+.2f}%")
                with bt_metric4:
                    strongest = bt_df.iloc[0]["symbol"]
                    st.metric("Rapor Terkuat", strongest)

                bt_display = bt_df[
                    [
                        "symbol",
                        "backtest_label",
                        "backtest_winrate",
                        "backtest_trades",
                        "backtest_avg_return",
                        "backtest_profit_factor",
                        "score",
                        "strategy_mode",
                        "risk_level",
                    ]
                ].head(12).copy()
                bt_display.columns = ["Coin", "Rapor", "Winrate %", "Setup", "Avg Return %", "Profit Factor", "Score", "Mode", "Risk"]
                st.dataframe(bt_display, hide_index=True, width="stretch", height=360)

            st.divider()

        if "perf_log" not in st.session_state:
            st.session_state.perf_log = []  # list of {symbol, score, action, ml_label, recorded_at, result (pending/win/loss/breakeven)}
    
        # Show current recommendations snapshot
        if not recs_df.empty:
            st.markdown("**📸 Snapshot rekomendasi saat ini**")
            if st.button("💾 Catat rekomendasi ke tracker"):
                snapshot_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                new_entries = []
                for _, row in recs_df.iterrows():
                    new_entries.append({
                        "symbol": row["symbol"],
                        "price": row["price"],
                        "score": row["score"],
                        "action": row["action"],
                        "ml_label": row["ml_label"],
                        "ml_probability": row["ml_probability"],
                        "strategy_mode": row["strategy_mode"],
                        "recorded_at": snapshot_time,
                        "result": "pending",
                        "exit_price": None,
                        "exit_at": None,
                        "pnl_pct": None,
                    })
                st.session_state.perf_log.extend(new_entries)
                st.success(f"✅ {len(new_entries)} rekomendasi dicatat!")
    
        # Tracked history  
        if st.session_state.perf_log:
            st.divider()
            st.markdown(f"**{len(st.session_state.perf_log)} rekomendasi tercatat**")
    
            # Update results
            perf_update_col1, perf_update_col2, perf_update_col3 = st.columns([2, 1, 1])
            with perf_update_col1:
                perf_symbols = sorted(set(e["symbol"] for e in st.session_state.perf_log if e["result"] == "pending"))
                if perf_symbols:
                    perf_fix_coin = st.selectbox("Update hasil coin", [""] + perf_symbols, key="perf_fix")
                else:
                    perf_fix_coin = ""
            with perf_update_col2:
                perf_result = st.selectbox("Hasil", ["", "WIN ✅", "LOSS ❌", "BREAKEVEN ➖"], key="perf_result")
            with perf_update_col3:
                perf_exit_price = st.text_input("Exit price", placeholder="Harga jual", key="perf_exit")
    
            if st.button("📝 Simpan hasil", disabled=(not perf_fix_coin or not perf_result)):
                try:
                    exit_price_val = float(perf_exit_price) if perf_exit_price.strip() else None
                except ValueError:
                    exit_price_val = None
    
                result_map = {"WIN ✅": "win", "LOSS ❌": "loss", "BREAKEVEN ➖": "breakeven"}
                for entry in st.session_state.perf_log:
                    if entry["symbol"] == perf_fix_coin and entry["result"] == "pending":
                        entry["result"] = result_map[perf_result]
                        entry["exit_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        entry["exit_price"] = exit_price_val
                        if exit_price_val and entry["price"] > 0:
                            entry["pnl_pct"] = round((exit_price_val - entry["price"]) / entry["price"] * 100, 2)
                st.success(f"✅ Hasil untuk {perf_fix_coin} disimpan!")
                st.rerun()
    
            # Performance stats
            st.divider()
            pending = [e for e in st.session_state.perf_log if e["result"] == "pending"]
            resolved = [e for e in st.session_state.perf_log if e["result"] != "pending"]
            wins = [e for e in resolved if e["result"] == "win"]
            losses = [e for e in resolved if e["result"] == "loss"]
    
            stat1, stat2, stat3, stat4, stat5 = st.columns(5)
            with stat1:
                st.metric("Total Tercatat", len(st.session_state.perf_log))
            with stat2:
                st.metric("Resolved", len(resolved))
            with stat3:
                st.metric("Pending", len(pending))
            with stat4:
                win_rate = round(len(wins) / len(resolved) * 100, 1) if resolved else 0
                st.metric("Win Rate", f"{win_rate}%")
            with stat5:
                avg_pnl = round(sum(e.get("pnl_pct", 0) or 0 for e in resolved) / len(resolved), 2) if resolved else 0
                st.metric("Avg PnL", f"{avg_pnl:+.2f}%")
    
            # Per-symbol summary
            if resolved:
                st.markdown("**📋 Ringkasan per coin**")
                perf_summary = []
                for sym in sorted(set(e["symbol"] for e in resolved)):
                    sym_entries = [e for e in resolved if e["symbol"] == sym]
                    sym_wins = [e for e in sym_entries if e["result"] == "win"]
                    sym_rate = round(len(sym_wins) / len(sym_entries) * 100, 1) if sym_entries else 0
                    sym_pnl = round(sum(e.get("pnl_pct", 0) or 0 for e in sym_entries) / len(sym_entries), 2)
                    perf_summary.append({
                        "Coin": sym,
                        "Entries": len(sym_entries),
                        "Win Rate": f"{sym_rate}%",
                        "Avg PnL": f"{sym_pnl:+.2f}%",
                    })
                perf_df = pd.DataFrame(perf_summary)
                st.dataframe(perf_df, hide_index=True)
    
            # Recent entries
            st.markdown("**📜 Log terbaru**")
            recent_display = []
            for e in st.session_state.perf_log[-30:]:
                result_emoji = {"win": "✅", "loss": "❌", "breakeven": "➖", "pending": "⏳"}.get(e["result"], "⏳")
                recent_display.append({
                    "Coin": e["symbol"],
                    "Price": format_idr(e["price"]),
                    "Score": e["score"],
                    "Action": e["action"],
                    "ML": f'{e["ml_label"]} {e["ml_probability"]:.1f}%',
                    "Recorded": e["recorded_at"],
                    "Result": result_emoji + " " + e["result"],
                    "PnL": f'{e.get("pnl_pct", 0):+.2f}%' if e.get("pnl_pct") else "-",
                })
            st.dataframe(pd.DataFrame(recent_display), hide_index=True)
    
            if st.button("🗑️ Reset tracker"):
                st.session_state.perf_log = []
                st.rerun()
    
    with t4:
        st.markdown(
            f"""
            <div class="pro-card">
                <h2 style="color:white; font-size:2rem; margin-top:0;">
                    <i class="fa-solid fa-crown" style="color:#fbbf24;"></i> JOIN PREMIUM TELEGRAM
                </h2>
                <p style="color:#a5b4fc; font-size:1.1rem;">
                    Dapatkan sinyal trading harian langsung ke HP kamu!
                </p>
                <div style="text-align:left; max-width:420px; margin:1.5rem auto; color:#c7d2fe; line-height:2;">
                    <p>✅ Sinyal BELI / JUAL setiap hari</p>
                    <p>✅ Analisa market real-time</p>
                    <p>✅ Grup diskusi eksklusif</p>
                    <p>✅ Tips cuan dari trader pro</p>
                    <p>✅ Notifikasi langsung ke Telegram</p>
                </div>
                <p style="color:#fbbf24; font-weight:900; font-size:1.6rem; margin:1.2rem 0;">
                    Rp 50.000 / bulan
                </p>
                <a href="{TELEGRAM_COMMUNITY}" target="_blank" style="text-decoration:none;">
                    <div style="background:linear-gradient(135deg, #6366f1, #4f46e5); color:white; 
                                padding:16px 48px; border-radius:16px; font-weight:800; font-size:1.2rem; 
                                display:inline-block; box-shadow:0 4px 24px rgba(99,102,241,0.4);
                                transition:all 0.2s ease;">
                        GABUNG SEKARANG 🚀
                    </div>
                </a>
            </div>
            """,
            unsafe_allow_html=True,
        )
    
        st.divider()
    
        # --- DONATION SECTION ---
        st.markdown("### ☕ TRAKTIR KOPI (DONASI CRYPTO)")
        dc1, dc2, dc3 = st.columns(3)
    
        wallet_style = "background:#111; border:1px solid #2a2a2a; border-radius:14px; padding:1rem; text-align:center;"
    
        with dc1:
            st.markdown(
                f"""
                <div style="{wallet_style}">
                    <p style="color:#f7931a; font-weight:700; margin:0 0 6px 0; font-size:1rem;">₿ BTC</p>
                    <code style="font-size:0.55rem; word-break:break-all; color:#666; background:transparent;">
                        {DONATION_WALLETS['BTC']}
                    </code>
                </div>
                """,
                unsafe_allow_html=True,
            )
        with dc2:
            st.markdown(
                f"""
                <div style="{wallet_style}">
                    <p style="color:#627eea; font-weight:700; margin:0 0 6px 0; font-size:1rem;">Ξ ETH</p>
                    <code style="font-size:0.55rem; word-break:break-all; color:#666; background:transparent;">
                        {DONATION_WALLETS['ETH']}
                    </code>
                </div>
                """,
                unsafe_allow_html=True,
            )
        with dc3:
            st.markdown(
                f"""
                <div style="{wallet_style}">
                    <p style="color:#26a17b; font-weight:700; margin:0 0 6px 0; font-size:1rem;">💵 USDT (TRC20)</p>
                    <code style="font-size:0.55rem; word-break:break-all; color:#666; background:transparent;">
                        {DONATION_WALLETS['USDT_TRC20']}
                    </code>
                </div>
                """,
                unsafe_allow_html=True,
            )
    
    with t5:
        st.markdown("### 📋 Tabel Lengkap Harga & Rekomendasi")
        st.caption("Harga real-time dari Indodax. Data diperbarui otomatis.")
    
        if not recs_df.empty:
            display_df = recs_df[
                [
                    "symbol",
                    "score",
                    "value_score",
                    "strategy_mode",
                    "ml_probability",
                    "ml_expected_return",
                    "ml_label",
                    "ml_confidence",
                    "backtest_winrate",
                    "backtest_trades",
                    "backtest_avg_return",
                    "backtest_label",
                    "agent_verdict",
                    "agent_net_score",
                    "agent_bull_score",
                    "agent_bear_score",
                    "lab_best_strategy",
                    "lab_winrate",
                    "lab_trades",
                    "lab_avg_return",
                    "ta_plus_score",
                    "atr_pct",
                    "mfi",
                    "obv_trend",
                    "supertrend_bias",
                    "candle_signal",
                    "price",
                    "daily_change",
                    "potential_gain_pct",
                    "risk_reward",
                    "allocation_pct",
                    "risk_per_trade_pct",
                    "risk_level",
                    "volume_idr",
                    "label",
                    "value_label",
                    "technical_score",
                    "rsi",
                    "ema_bias",
                    "macd_signal",
                    "bb_signal",
                    "bb_pct_b",
                    "adx",
                    "trend_strength",
                    "category",
                    "support",
                    "resistance",
                    "volume_spike",
                    "indicator_source",
                    "quality",
                    "take_profit_1",
                    "take_profit_2",
                    "target_price",
                    "stop_loss",
                    "trailing_stop_pct",
                    "reason",
                ]
            ].copy()
            display_df.columns = [
                "Coin",
                "Score",
                "Value",
                "Mode",
                "ML Prob %",
                "ML Exp %",
                "ML Label",
                "ML Conf",
                "Rapor %",
                "Setup Hist",
                "Rapor Avg %",
                "Rapor Label",
                "Agent Verdict",
                "Agent Net",
                "Bull",
                "Bear",
                "Lab Strategy",
                "Lab Win %",
                "Lab Trades",
                "Lab Avg %",
                "TA+",
                "ATR %",
                "MFI",
                "OBV",
                "Supertrend",
                "Candle",
                "Harga",
                "24j %",
                "Potensi Untung %",
                "R/R",
                "Max Size %",
                "Risk/Trade %",
                "Risk",
                "Volume",
                "Rekomendasi",
                "Value Label",
                "Tech Score",
                "RSI",
                "EMA",
                "MACD",
                "BB Signal",
                "BB %B",
                "ADX",
                "Trend",
                "Kategori",
                "Support",
                "Resistance",
                "Vol Spike",
                "Source",
                "Data",
                "TP1",
                "TP2",
                "Target Jual",
                "Stop Loss",
                "Trailing %",
                "Alasan",
            ]
            display_df["Harga"] = display_df["Harga"].apply(format_idr)
            display_df["Volume"] = display_df["Volume"].apply(format_volume)
            display_df["Support"] = display_df["Support"].apply(format_idr)
            display_df["Resistance"] = display_df["Resistance"].apply(format_idr)
            display_df["TP1"] = display_df["TP1"].apply(format_idr)
            display_df["TP2"] = display_df["TP2"].apply(format_idr)
            display_df["Target Jual"] = display_df["Target Jual"].apply(format_idr)
            display_df["Stop Loss"] = display_df["Stop Loss"].apply(format_idr)
    
            def color_recommendation(val):
                if "BELI" in str(val).upper():
                    return "background-color: #064e3b; color: #22c55e; font-weight: 800;"
                elif "JUAL" in str(val).upper() or "JANGAN" in str(val).upper() or "HINDARI" in str(val).upper():
                    return "background-color: #450a0a; color: #ef4444; font-weight: 800;"
                return "background-color: #1a1a1a; color: #9ca3af; font-weight: 700;"
    
            def color_risk(val):
                if val == "TINGGI":
                    return "background-color: #450a0a; color: #ef4444; font-weight: 800;"
                if val == "SEDANG":
                    return "background-color: #451a03; color: #fbbf24; font-weight: 800;"
                return "background-color: #064e3b; color: #22c55e; font-weight: 800;"
    
            def color_mode(val):
                if val == "SWING / HOLD":
                    return "background-color: #052e16; color: #86efac; font-weight: 900;"
                if val == "SCALP ONLY":
                    return "background-color: #431407; color: #fdba74; font-weight: 900;"
                if val == "WATCH VALUE":
                    return "background-color: #082f49; color: #7dd3fc; font-weight: 900;"
                if val == "SKIP":
                    return "background-color: #450a0a; color: #ef4444; font-weight: 900;"
                return "background-color: #111827; color: #d1d5db; font-weight: 800;"

            def color_backtest(val):
                if val == "TERUJI BAGUS":
                    return "background-color: #052e16; color: #86efac; font-weight: 900;"
                if val == "CUKUP":
                    return "background-color: #451a03; color: #fbbf24; font-weight: 900;"
                if val == "LEMAH":
                    return "background-color: #450a0a; color: #ef4444; font-weight: 900;"
                return "background-color: #111827; color: #d1d5db; font-weight: 800;"

            def color_agent(val):
                if val == "APPROVE":
                    return "background-color: #052e16; color: #86efac; font-weight: 900;"
                if val == "APPROVE KECIL":
                    return "background-color: #451a03; color: #fbbf24; font-weight: 900;"
                if val == "TUNGGU":
                    return "background-color: #111827; color: #fbbf24; font-weight: 900;"
                if val == "DITOLAK RISK MANAGER":
                    return "background-color: #450a0a; color: #ef4444; font-weight: 900;"
                return "background-color: #111827; color: #d1d5db; font-weight: 800;"
    
            st.dataframe(
                display_df.style.map(color_recommendation, subset=["Rekomendasi"]).map(color_risk, subset=["Risk"]).map(color_mode, subset=["Mode"]).map(color_backtest, subset=["Rapor Label"]).map(color_agent, subset=["Agent Verdict"]),
                width="stretch",
                hide_index=True,
                height=520,
            )
    
            csv = display_df.to_csv(index=False).encode("utf-8")
            st.download_button(
                label="📥 Download CSV",
                data=csv,
                file_name=f"rekomendasi_crypto_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
                mime="text/csv",
            )
        else:
            st.warning("Tidak ada data untuk ditampilkan. Coba refresh halaman.")
    
    st.divider()
    
    # =============================================================================
    #  🔴 COINS TO AVOID / HOLD
    # =============================================================================
    if not hold_skip_recs.empty:
        st.markdown(
            "<h2 style='text-align:center; margin-top:2rem;'>🔴 TAHAN / JANGAN DIBELI DULU</h2>",
            unsafe_allow_html=True,
        )
        skip_n_cols = min(len(hold_skip_recs), 6)
        skip_cols = st.columns(skip_n_cols)
    
        for i, row in enumerate(hold_skip_recs.to_dict("records")):
            with skip_cols[i % skip_n_cols]:
                daily_pct = row["daily_change"]
                badge_class = "profit-badge" if daily_pct >= 0 else "loss-badge"
                st.markdown(
                    f"""
                    <div style="background:#111; border:1px solid #2a2a2a; border-radius:16px; 
                                padding:1rem 0.8rem; text-align:center; transition:all 0.2s ease;"
                         onmouseover="this.style.borderColor='#444'"
                         onmouseout="this.style.borderColor='#2a2a2a'">
                        <p style="font-weight:700; margin:0; color:white; font-size:1rem;">{row['symbol']}</p>
                        <p style="color:#888; font-size:0.8rem; margin:4px 0;">{format_idr(row['price'])}</p>
                        <span style="background:{row['color']}; 
                                     color:white; padding:4px 14px; border-radius:99px; 
                                     font-weight:700; font-size:0.75rem; display:inline-block;">
                            {row['label']}
                        </span>
                        <p style="color:{'#22c55e' if daily_pct >= 0 else '#ef4444'}; 
                                  font-size:0.8rem; margin:6px 0 0 0; font-weight:600;">
                            {'+' if daily_pct >= 0 else ''}{daily_pct}% (24j)
                        </p>
                    </div>
                """,
                unsafe_allow_html=True,
            )

    # =============================================================================
    #  FOOTER
    # =============================================================================
    st.divider()
    st.markdown(
        f"""
        <div style="text-align:center; padding:2rem 1rem; color:#555; font-size:0.8rem; line-height:1.8;">
            ⚠️ <b>BUKAN SARAN KEUANGAN.</b> Trading crypto beresiko tinggi. Kamu bertanggung jawab penuh atas keputusan investasi kamu. DYOR.<br>
            🔗 Link mengandung kode referral Indodax • Data real-time dari <b>Indodax API</b><br>
            🕐 Data diambil: {datetime.now().strftime('%d %b %Y, %H:%M:%S WIB')}
        </div>
        """,
        unsafe_allow_html=True,
    )

# =============================================================================
#  START APP
# =============================================================================
# 0. Initial Data Fetch (for Sidebar) — pakai cache session agar refresh tidak terasa blank.
_, all_tickers_init, init_status = fetch_all_data()
if all_tickers_init:
    market_stats_init = compute_market_overview(all_tickers_init)
    st.session_state.last_all_tickers = all_tickers_init
    st.session_state.last_market_stats = market_stats_init
    st.session_state.data_status = init_status
else:
    all_tickers_init = st.session_state.get("last_all_tickers", {})
    market_stats_init = st.session_state.get("last_market_stats")

# 1. Render Sidebar (Static - Outside Fragment)
with st.sidebar:
    st.markdown("### ⚙️ PENGATURAN")
    live_update = st.toggle("🔄 Auto Refresh", value=True, help="Refresh data otomatis setiap beberapa detik")
    refresh_seconds = st.slider("⏱️ Interval refresh (detik)", 10, 60, 15, help="Dibuat agak longgar supaya layar tidak terasa kedip saat data berat dihitung ulang")
    st.session_state["live_update"] = live_update
    st.session_state["refresh_seconds"] = refresh_seconds
    st.divider()

    # --- BOT STATUS ---
    _, bot_fetched, _ = _read_shared_tickers()
    if not BOT_ENABLED:
        st.markdown('<div style="background:#111827; border:1px solid #374151; border-radius:12px; padding:10px 14px; margin-bottom:8px;"><p style="color:#9ca3af; font-weight:700; margin:0; font-size:0.8rem;">🤖 BOT OFF</p></div>', unsafe_allow_html=True)
    elif bot_fetched:
        st.markdown(f'<div style="background:#064e3b22; border:1px solid #064e3b; border-radius:12px; padding:10px 14px; margin-bottom:8px;"><p style="color:#22c55e; font-weight:700; margin:0; font-size:0.8rem;">🤖 BOT ACTIVE</p><p style="color:#9ca3af; margin:2px 0 0 0; font-size:0.7rem;">Last: {bot_fetched.strftime("%H:%M:%S")}</p></div>', unsafe_allow_html=True)

    # --- MARKET OVERVIEW ---
    if market_stats_init:
        st.markdown("### 📊 MARKET OVERVIEW")
        st.metric("📈 Gainers", market_stats_init["gainers"])
        st.metric("📉 Losers", market_stats_init["losers"])
        st.metric("📊 Avg Change", f"{market_stats_init['avg_change']:+.2f}%")
        st.markdown(f'<div style="background:#111; border:1px solid {market_stats_init["mode_color"]}; border-radius:12px; padding:0.85rem;"><p style="color:{market_stats_init["mode_color"]}; font-weight:900; margin:0;">{market_stats_init["mode_label"]}</p></div>', unsafe_allow_html=True)
    
    st.divider()
    
    # --- SIMULASI ---
    st.markdown("### 💵 SIMULASI")
    if all_tickers_init:
        sim_coin = st.selectbox("🎯 Pilih Coin", options=list(ALL_ASSETS.keys()))
        sim_price = float(all_tickers_init.get(ALL_ASSETS[sim_coin][0], {}).get("last", 0))
        sim_capital = st.number_input("💰 Modal", min_value=100000, value=1000000)
        st.caption(f"Harga saat ini: {format_idr(sim_price)}")

# 2. Start Telegram Bot (if enabled)
start_telegram_bot()

# 3. Render Main Content (Dynamic Fragment)
if "render_main_content" not in globals():
    @st.fragment(run_every=st.session_state.get("refresh_seconds", 15) if st.session_state.get("live_update", True) else None)
    def render_main_content():
        live_market_stats = compute_market_overview(all_tickers) if all_tickers else st.session_state.get("last_market_stats")
        if not all_tickers or not live_market_stats:
            loading_placeholder.markdown(
                loading_markup(
                    "Menunggu data market...",
                    "Koneksi ke Indodax belum memberi data. App akan mencoba lagi otomatis.",
                ),
                unsafe_allow_html=True,
            )
            return
        render_dashboard_ui(data, all_tickers, data_status, live_market_stats)

render_main_content()
