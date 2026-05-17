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

def _bot_detect_fomo(raw_tickers):
    fomo_gila, fomo, pumping = [], [], []
    for pair, info in raw_tickers.items():
        if not pair.endswith("_idr"):
            continue
        try:
            price = float(info["last"])
            low = float(info.get("low", 0))
            vol = float(info.get("vol_idr", 0))
            # Indodax API tidak punya field 'change', hitung dari low ke last
            if low > 0:
                change = ((price - low) / low) * 100
            else:
                change = 0.0
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
    import time as _time
    last_sinyal_date = None
    fomo_sent = {}
    consecutive_errors = 0
    _bot_send_message("🤖 *Bot Radar Aktif (24/7)*\nMemantau market Indodax... 🚀")
    cycle = 0
    while True:
        try:
            cycle += 1
            resp = requests.get("https://indodax.com/api/tickers", timeout=10)
            tickers = resp.json().get("tickers", {})
            if not tickers:
                consecutive_errors += 1
                wait = min(30, consecutive_errors * 5)
                _time.sleep(wait)
                continue
            consecutive_errors = 0
            now = datetime.now(BOT_WIB)
            today = now.strftime("%Y-%m-%d")
            try:
                _write_shared_tickers(tickers)
            except Exception:
                pass
            if 8 <= now.hour <= 9 and last_sinyal_date != today:
                prices = {}
                for sym, pair in BOT_MAIN_ASSETS.items():
                    if pair in tickers:
                        try:
                            info = tickers[pair]
                            price = float(info["last"])
                            low = float(info.get("low", 0))
                            # Indodax API tidak punya field 'change', hitung dari low ke last
                            if low > 0:
                                change = ((price - low) / low) * 100
                            else:
                                change = 0.0
                            prices[sym] = {
                                "price": price,
                                "high": float(info.get("high", 0)),
                                "low": low,
                                "vol_idr": float(info.get("vol_idr", 0)),
                                "change": round(change, 2),
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
            _time.sleep(120)
        except Exception:
            consecutive_errors += 1
            backoff = min(120, 10 * (2 ** min(consecutive_errors - 1, 4)))
            _time.sleep(backoff)

def start_telegram_bot():
    if not BOT_ENABLED or not BOT_TOKEN or not BOT_CHAT_ID:
        st.session_state.telegram_bot_started = False
        return
    if not st.session_state.get("telegram_bot_started"):
        st.session_state.telegram_bot_started = True
        t = threading.Thread(target=_telegram_bot_daemon, daemon=True, name="telegram-bot")
        t.start()

start_telegram_bot()

# =============================================================================
# STYLING
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
    .stat-value { font-size: 1.5rem; font-weight: 900; }
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
    """Fetch all tickers from Indodax API."""
    try:
        resp = requests.get("https://indodax.com/api/tickers", timeout=10)
        data = resp.json()
        tickers = data.get("tickers", {})
        server_time = data.get("server_time", None)
        if server_time:
            try:
                server_dt = datetime.fromtimestamp(int(server_time), tz=timezone.utc)
            except (ValueError, OSError):
                server_dt = datetime.now(timezone.utc)
        else:
            server_dt = datetime.now(timezone.utc)
        return tickers, server_dt, None
    except requests.RequestException as e:
        return None, None, str(e)
    except (KeyError, ValueError, TypeError) as e:
        return None, None, str(e)


def fetch_all_ticker_data():
    """Main fetch function — tries shared tickers first, then API."""
    shared_tickers, shared_at, shared_err = _read_shared_tickers()
    if shared_tickers and shared_at and (datetime.now() - shared_at).total_seconds() < 120:
        return shared_tickers, shared_at, None
    tickers, server_time, error = fetch_indodax_tickers()
    if tickers:
        return tickers, server_time, None
    if shared_tickers:
        return shared_tickers, shared_at, "⚠️ Data dari cache (API timeout)"
    return {}, datetime.now(), "❌ Gagal ambil data"


def extract_asset_data(tickers, asset_dict):
    """Extract price data for a given asset dictionary.
    
    Indodax API tidak menyediakan field 'change' secara langsung.
    Kita hitung perubahan harga dari (last - low) / low * 100 sebagai
    estimasi perubahan 24 jam.
    """
    result = {}
    for symbol, (pair, _) in asset_dict.items():
        if pair in tickers:
            try:
                info = tickers[pair]
                price = float(info["last"])
                high = float(info.get("high", 0))
                low = float(info.get("low", 0))
                vol_idr = float(info.get("vol_idr", 0))
                # Hitung perubahan dari low ke last sebagai estimasi 24h change
                if low > 0:
                    change = ((price - low) / low) * 100
                else:
                    change = 0.0
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
# MARKET ANALYSIS
# =============================================================================
def compute_market_stats(tickers):
    """Compute overall market statistics.
    
    Indodax API tidak menyediakan field 'change'. Kita hitung
    perubahan dari (last - low) / low * 100 sebagai estimasi.
    """
    idr_pairs = {k: v for k, v in tickers.items() if k.endswith("_idr")}
    if not idr_pairs:
        return None
    changes = []
    volumes = []
    green_count = 0
    for pair, info in idr_pairs.items():
        try:
            price = float(info["last"])
            low = float(info.get("low", 0))
            vol = float(info.get("vol_idr", 0))
            # Hitung perubahan dari low ke last
            if low > 0:
                change = ((price - low) / low) * 100
            else:
                change = 0.0
            changes.append(change)
            volumes.append(vol)
            if change > 0:
                green_count += 1
        except (ValueError, TypeError, KeyError):
            continue

    if not changes:
        return None
    total = len(changes)
    green_pct = (green_count / total) * 100 if total > 0 else 0
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
        "red_count": total - green_count,
        "green_pct": round(green_pct, 1),
        "avg_change": round(avg_change, 2),
        "total_vol": total_vol,
        "mode": mode,
    }


def compute_coin_score(data, market_stats):
    """Compute a buy score for a single coin."""
    change = data["change"]
    vol_idr = data["vol_idr"]
    high = data["high"]
    low = data["low"]
    price = data["price"]
    range_width = high - low
    range_position = ((price - low) / range_width * 100) if range_width > 0 else 50
    score = 50
    score += clamp(change * 3, -25, 25)
    vol_score = min(15, vol_idr / 500_000_000)
    score += vol_score
    if range_position > 85 and change > 5:
        score -= 12
    if range_position < 20 and change < -3:
        score += 8
    if vol_idr < 100_000_000:
        score -= 10
    if vol_idr > 5_000_000_000:
        score += 5
    if market_stats:
        mode = market_stats["mode"]
        adj = MARKET_MODE_RULES[mode]["score_adjustment"]
        score += adj
    score = int(clamp(score, 0, 100))
    return score


def determine_action(score, change, vol_idr):
    """Determine buy/sell action based on score."""
    if score >= 80 and change > 1:
        return "🟢 BELI KUAT", "🔥"
    elif score >= 68 and change > 0:
        return "🟡 CICIL BELI", "📈"
    elif score >= 55:
        return "⚪ WATCH", "⏸️"
    elif score >= 40:
        return "🔴 JANGAN BELI", "📉"
    else:
        return "⛔ HINDARI", "💀"


def determine_risk_level(change, vol_idr):
    if abs(change) >= 10 or vol_idr < 100_000_000:
        return "TINGGI"
    elif abs(change) >= 5 or vol_idr < 1_000_000_000:
        return "SEDANG"
    return "RENDAH"


def compute_allocation_pct(action, score, risk_level, market_mode):
    if "BELI" not in action:
        return 0
    risk_mod = {"RENDAH": 1.0, "SEDANG": 0.65, "TINGGI": 0.35}[risk_level]
    mode_mult = MARKET_MODE_RULES[market_mode]["allocation_multiplier"]
    base = 7 * (score / 100) * risk_mod * mode_mult
    return clamp(base, 1, 10)


def compute_targets(price, change, score, risk_level):
    gain_pct = clamp(3 + max(change, 0) * 0.85 + (score - 60) * 0.12, 2, 16)
    stop_pct = clamp(2.6 + abs(change) * 0.35 + (1 if risk_level == "TINGGI" else 0), 2.5, 9)
    target = price * (1 + gain_pct / 100)
    tp1 = price * (1 + gain_pct * 0.35 / 100)
    tp2 = price * (1 + gain_pct * 0.7 / 100)
    stop_loss = price * (1 - stop_pct / 100)
    trailing_stop_pct = clamp(stop_pct * 0.55, 1.5, 5)
    return target, tp1, tp2, stop_loss, trailing_stop_pct, gain_pct, stop_pct


def analyze_assets(assets_data, market_stats):
    """Analyze all assets and return scored results."""
    results = []
    for symbol, data in assets_data.items():
        score = compute_coin_score(data, market_stats)
        action, emoji = determine_action(score, data["change"], data["vol_idr"])
        risk_level = determine_risk_level(data["change"], data["vol_idr"])
        market_mode = market_stats["mode"] if market_stats else "normal"
        allocation_pct = compute_allocation_pct(action, score, risk_level, market_mode)
        target, tp1, tp2, stop_loss, trailing_stop_pct, gain_pct, stop_pct = compute_targets(
            data["price"], data["change"], score, risk_level
        )
        category = COIN_CATEGORIES.get(symbol, "Lainnya")
        category_color = CATEGORY_COLORS.get(category, "#6b7280")
        results.append({
            "symbol": symbol,
            "pair": data["pair"],
            "price": data["price"],
            "change": data["change"],
            "vol_idr": data["vol_idr"],
            "score": score,
            "action": action,
            "emoji": emoji,
            "risk_level": risk_level,
            "allocation_pct": allocation_pct,
            "target": target,
            "tp1": tp1,
            "tp2": tp2,
            "stop_loss": stop_loss,
            "trailing_stop_pct": trailing_stop_pct,
            "gain_pct": gain_pct,
            "stop_pct": stop_pct,
            "category": category,
            "category_color": category_color,
        })
    priority = {
        "🟢 BELI KUAT": 0, "🟡 CICIL BELI": 1, "⚪ WATCH": 2,
        "🔴 JANGAN BELI": 3, "⛔ HINDARI": 4,
    }
    results.sort(key=lambda x: (priority.get(x["action"], 5), -x["score"]))
    return results


# =============================================================================
# UI COMPONENTS
# =============================================================================
def render_header():
    st.markdown(
        f"""
        <div style="text-align:center;margin-bottom:0.5rem">
            <h1 style="font-size:2.8rem;font-weight:900;background:linear-gradient(135deg,#10b981,#3b82f6,#f59e0b);
                       -webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text;">
                💰 Rekomendasi Beli Crypto
            </h1>
            <p style="color:#64748b;font-size:1.1rem;font-weight:500;margin-top:-0.3rem">
                Analisis Real-time dari Indodax — <strong>Bukan Saran Keuangan</strong>
            </p>
            <p style="font-size:0.85rem;color:#94a3b8">
                🔗 <a href="{INDODAX_REF}" target="_blank" style="color:#10b981;font-weight:600">Daftar Indodax via Referral</a>
                &nbsp;·&nbsp; 💬 <a href="{TELEGRAM_COMMUNITY}" target="_blank" style="color:#3b82f6;font-weight:600">Gabung Telegram Premium</a>
            </p>
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
        <div style="background:{rules['color']}15;border:2px solid {rules['color']};border-radius:16px;
                    padding:1rem 1.5rem;margin:0.5rem 0 1rem 0;text-align:center">
            <span style="font-size:1.3rem;font-weight:900;color:{rules['color']}">{rules['label']}</span>
            <span style="color:#64748b;font-size:0.95rem;margin-left:0.5rem">— {rules['description']}</span>
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
        buy_picks = [r for r in all_results if "BELI" in r["action"]][:3]
        if buy_picks:
            st.markdown("#### 🔥 Top 3 Picks")
            for p in buy_picks:
                st.markdown(f"**{p['symbol']}** — Score {p['score']}/100 · {p['change']:+.1f}%")
        st.markdown("---")
        # Bot status
        st.markdown("#### 🤖 Status Bot")
        st.markdown("✅ Telegram Bot: **Aktif 24/7**")
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
    st.markdown(
        f"""
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
            <div style="margin-top:0.8rem;text-align:center">
                <a href="{buy_link}" target="_blank" class="buy-button-sm">🔥 Beli di Indodax</a>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_rekomendasi_list(results, title, max_items=10):
    buy_results = [r for r in results if "BELI" in r["action"]]
    watch_results = [r for r in results if "WATCH" in r["action"]]
    st.markdown(
        f"""<div class="rekomendasi-hero">
            <h2 style="color:white;font-size:1.8rem;margin:0;position:relative;z-index:1">{title}</h2>
            <p style="color:#6ee7b7;margin:0.3rem 0 0 0;position:relative;z-index:1">
                {len(buy_results)} rekomendasi beli · {len(watch_results)} pantauan
            </p>
        </div>""",
        unsafe_allow_html=True,
    )
    if not results:
        st.info("Belum ada data untuk ditampilkan.")
        return
    for i, item in enumerate(results[:max_items]):
        render_rekomendasi_card(item, i)


def render_fomo_alerts(tickers):
    fomo_gila, fomo, pumping = _bot_detect_fomo(tickers)
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
                        <a href="{link}" target="_blank" style="display:inline-block;margin-top:0.4rem;background:#ef4444;color:white;padding:4px 14px;border-radius:8px;text-decoration:none;font-weight:700;font-size:0.8rem">🔥 Beli</a>
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
                        <a href="{link}" target="_blank" style="display:inline-block;margin-top:0.3rem;background:#f59e0b;color:white;padding:3px 12px;border-radius:8px;text-decoration:none;font-weight:700;font-size:0.75rem">🔥 Beli</a>
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
        if st.button("🔄 Refresh Data Sekarang", use_container_width=True, type="primary"):
            st.cache_data.clear()
            st.rerun()
    
    loading_placeholder = st.empty()
    loading_placeholder.markdown(loading_markup(), unsafe_allow_html=True)
    tickers, server_time, error = fetch_all_ticker_data()
    if error and not tickers:
        loading_placeholder.empty()
        st.error(f"❌ {error}")
        st.info("🔄 Coba refresh halaman dalam beberapa saat.")
        render_footer()
        return
    market_stats = compute_market_stats(tickers)
    main_data = extract_asset_data(tickers, MAIN_ASSETS)
    micin_data = extract_asset_data(tickers, MICIN_ASSETS)
    all_data = {**main_data, **micin_data}
    main_results = analyze_assets(main_data, market_stats)
    micin_results = analyze_assets(micin_data, market_stats)
    all_results = analyze_assets(all_data, market_stats)
    loading_placeholder.empty()
    if error:
        st.warning(error)
    freshness = "live" if not error else "stale"
    freshness_text = "Live dari Indodax" if not error else "Data cache"
    if server_time:
        time_str = server_time.strftime("%H:%M:%S WIB")
    else:
        time_str = datetime.now(timezone(timedelta(hours=7))).strftime("%H:%M:%S WIB")
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
    render_fomo_alerts(tickers)

    tab1, tab2, tab3, tab4, tab5 = st.tabs(["🔥 Rekomendasi Beli", "📊 Semua Aset", "🐕 Micin/Meme", "📈 Analisis Detail", "💬 Tanya AI Advisor (DeepSeek)"])
    with tab1:
        render_rekomendasi_list(all_results, "🔥 Rekomendasi Beli Hari Ini", max_items=20)
    with tab2:
        render_rekomendasi_list(main_results, "📊 Main Assets", max_items=15)
    with tab3:
        render_rekomendasi_list(micin_results, "🐕 Micin / Meme Coin", max_items=15)
    with tab4:
        st.markdown("## 📈 Analisis Detail Semua Aset")
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
        st.markdown("## 💬 Tanya AI Market Advisor (DeepSeek)")
        st.markdown(
            "Konsultasikan kondisi portofolio, analisis koin, atau tanyakan pergerakan market Indodax hari ini secara cerdas bersama asisten AI khusus Kripto Mania."
        )
        
        # Quick prompt buttons
        quick_prompts = [
            "🔥 Koin mana yang paling potensial naik hari ini?",
            "💰 Berapa alokasi ideal untuk pemula modal 1 juta?",
            "📊 Analisis BTC dan ETH untuk minggu ini",
            "⚠️ Koin mana yang harus dihindari saat ini?",
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
                            buy_results = [r for r in all_results if "BELI" in r["action"]]
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


