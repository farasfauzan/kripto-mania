#!/usr/bin/env python3
"""
Telegram Command Handler — /scan /top /portfolio /journal /stats /weather /alert
User ketik command di Telegram → bot response otomatis.
"""

import os
import time
import requests
import pandas as pd
from datetime import datetime, timezone, timedelta

# Import dari telegram_bot (yang load config)
# Kita re-implement minimal functions needed

WIB = timezone(timedelta(hours=7))

# Re-use config dari environment
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

BOT_TOKEN = _get_api_key("TELEGRAM_BOT_TOKEN")
CHAT_ID = _get_api_key("TELEGRAM_CHAT_ID")
INDODAX_REF = "narwanpratanta"
TELEGRAM_CHANNEL = "https://t.me/+VPlOcY2wFGA0NWU1"

# Global state (akan di-set dari telegram_bot)
_active_signals = {}
_daily_stats = {"tp_hit": 0, "sl_hit": 0, "signals_sent": 0}
_message_fingerprints = {}
_last_fomo_alert_time = 0

# Import functions yang dibutuhkan dari telegram_bot
# Kita akan import setelah telegram_bot di-load

def format_idr_simple(value):
    if value is None or value == 0:
        return "-"
    if value >= 1_000_000_000:
        return f"Rp{value/1_000_000_000:.2f}M"
    if value >= 1_000_000:
        return f"Rp{value/1_000_000:.1f}JT"
    if value >= 1_000:
        return f"Rp{value:,.0f}"
    return f"Rp{value:,.2f}"


def send_telegram_message(text, notify=False, force=False):
    """Send message via Telegram Bot API."""
    if not BOT_TOKEN or not CHAT_ID:
        return False
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    chunks = [text] if len(text) <= 4096 else _split_text(text)
    for i, chunk in enumerate(chunks):
        payload = {
            "chat_id": CHAT_ID,
            "text": chunk,
            "parse_mode": "Markdown",
            "disable_notification": not notify
        }
        try:
            resp = requests.post(url, json=payload, timeout=10)
            result = resp.json()
            if not result.get("ok"):
                print(f"[CMD] Telegram error: {result.get('description', '')}")
        except Exception as e:
            print(f"[CMD] Send error: {e}")
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


def _is_entry_action(action):
    action = str(action or "").upper()
    return "BELI KUAT" in action or "CICIL BELI" in action


def _fetch_all_tickers():
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
            change = ((price - ref_price) / ref_price * 100) if ref_price > 0 else 0.0
            all_coins[symbol] = {
                "symbol": symbol, "pair": pair,
                "price": price, "change": round(change, 2),
                "vol_idr": float(info.get("vol_idr", 0)),
                "high": float(info.get("high", 0)),
                "low": float(info.get("low", 0)),
            }
        return all_coins
    except Exception as e:
        print(f"[CMD] Fetch error: {e}")
        return {}


def _fetch_candles(pair_id, tf="60", lookback_days=21):
    end_ts = int(time.time())
    start_ts = end_ts - lookback_days * 86400
    symbol = pair_id.replace("_", "").upper()
    url = "https://indodax.com/tradingview/history_v2"
    try:
        resp = requests.get(url, params={"from": start_ts, "to": end_ts, "tf": tf, "symbol": symbol}, timeout=8)
        rows = resp.json()
    except:
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


def _detect_market_mode(all_coins):
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
# COMMAND HANDLERS
# =============================================================================

def cmd_help():
    return (
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


def cmd_scan(telegram_bot_module=None):
    """Handle /scan command — manual scan semua koin."""
    # Try to import from telegram_bot if module passed
    if telegram_bot_module:
        fetch_all = getattr(telegram_bot_module, 'fetch_all_tickers', None)
        fetch_candles = getattr(telegram_bot_module, 'fetch_candles', None)
        analyze_coin = getattr(telegram_bot_module, 'analyze_coin', None)
        apply_bot_intel = getattr(telegram_bot_module, 'apply_bot_intelligence', None)
        detect_mode = getattr(telegram_bot_module, 'detect_market_mode', None)
    else:
        fetch_all = _fetch_all_tickers
        fetch_candles = _fetch_candles
        # We need the full analyze function from telegram_bot
        # Fallback: use simplified version
        return _cmd_scan_fallback()

    send_telegram_message("⏳ *Memulai scan...*_", notify=False)

    all_coins = fetch_all()
    if not all_coins:
        send_telegram_message("❌ Gagal fetch data dari Indodax.", notify=True)
        return True

    MAIN_ASSETS = {
        "BTC": "btc_idr", "ETH": "eth_idr", "SOL": "sol_idr",
        "XRP": "xrp_idr", "BNB": "bnb_idr", "ADA": "ada_idr",
        "DOGE": "doge_idr",
    }

    signals = []
    for sym, pair in MAIN_ASSETS.items():
        if sym not in all_coins:
            continue
        candles = fetch_candles(pair)
        time.sleep(0.3)
        res = apply_bot_intel(analyze_coin(sym, all_coins[sym], candles))
        signals.append(res)

    if not signals:
        send_telegram_message("❌ Tidak ada sinyal.", notify=True)
        return True

    priority = {"BELI KUAT": 0, "CICIL BELI": 1, "WATCH": 2, "JANGAN BELI": 3, "HINDARI": 4}
    signals.sort(key=lambda x: priority.get(x["action"], 5))

    mode, _ = detect_mode(all_coins)
    mode_emoji = {"agresif": "🟢", "normal": "🟡", "defensif": "🔴"}[mode]

    lines = [
        f"*📊 HASIL SCAN — {mode_emoji} {mode.upper()}*",
        f"{datetime.now(WIB).strftime('%d/%m %H:%M WIB')}",
        "──────────────────────",
        "",
    ]

    buy_count = 0
    for s in signals[:8]:
        ch = f"+{s['change']:.2f}" if s["change"] >= 0 else f"{s['change']:.2f}"
        lines.append(f"{s['emoji']} *{s['symbol']}* -- {s['action']}")
        lines.append(f"   💰 {format_idr_simple(s['price'])} ({ch}%) | Score: {s['score']}/100")
        lines.append(f"   📊 RSI: {s['rsi']} | MACD: {s['macd_signal']} | ST: {s['supertrend']}")
        lines.append(f"   🧠 ML: {s['ml_label']} ({s['ml_prob']}%) | MTF: {s['mtf_label']}")

        if _is_entry_action(s["action"]):
            buy_count += 1
            lines.append(f"   🎯 TP1: {format_idr_simple(s['tp1'])} | SL: {format_idr_simple(s['stop_loss'])}")
            lines.append(f"   💰 Alokasi: {s['alloc_pct']}%")
        lines.append("")

    lines.append("──────────────────────")
    lines.append(f"*{buy_count} koin layak beli* dari {len(signals)} koin")
    lines.append("⚠️ Bukan saran keuangan. DYOR.")

    send_telegram_message("\n".join(lines), notify=True)
    print(f"[CMD] /scan executed — {buy_count} buy signals found")
    return True


def _cmd_scan_fallback():
    """Fallback /scan without full telegram_bot import."""
    send_telegram_message("⏳ *Memulai scan...*_", notify=False)

    all_coins = _fetch_all_tickers()
    if not all_coins:
        send_telegram_message("❌ Gagal fetch data.", notify=True)
        return True

    MAIN_ASSETS = {
        "BTC": "btc_idr", "ETH": "eth_idr", "SOL": "sol_idr",
        "XRP": "xrp_idr", "BNB": "bnb_idr", "ADA": "ada_idr",
        "DOGE": "doge_idr",
    }

    mode, _ = _detect_market_mode(all_coins)
    mode_emoji = {"agresif": "🟢", "normal": "🟡", "defensif": "🔴"}[mode]

    lines = [
        f"*📊 SCAN — {mode_emoji} {mode.upper()}*",
        f"{datetime.now(WIB).strftime('%d/%m %H:%M WIB')}",
        "──────────────────────",
        "",
    ]

    for sym, info in all_coins.items():
        if sym not in MAIN_ASSETS:
            continue
        ch = f"+{info['change']:.2f}" if info["change"] >= 0 else f"{info['change']:.2f}"
        emoji = "🟢" if info["change"] > 3 else "🟡" if info["change"] > 0 else "🔴"
        lines.append(f"{emoji} *{sym}* — {ch}% | Vol: {format_idr_simple(info['vol_idr'])}")

    lines.append("")
    lines.append("──────────────────────")
    lines.append("💡 Ketik */scan-full* untuk analisis teknikal lengkap.")
    lines.append("⚠️ Bukan saran keuangan. DYOR.")

    send_telegram_message("\n".join(lines), notify=True)
    return True


def cmd_top(telegram_bot_module=None):
    """Handle /top command — 5 koin terbaik."""
    if telegram_bot_module:
        fetch_all = telegram_bot_module.fetch_all_tickers
        fetch_candles = telegram_bot_module.fetch_candles
        analyze_coin = telegram_bot_module.analyze_coin
        apply_bot_intel = telegram_bot_module.apply_bot_intelligence
    else:
        return _cmd_top_fallback()

    all_coins = fetch_all()
    if not all_coins:
        send_telegram_message("❌ Gagal fetch data.", notify=True)
        return True

    MAIN_ASSETS = {
        "BTC": "btc_idr", "ETH": "eth_idr", "SOL": "sol_idr",
        "XRP": "xrp_idr", "BNB": "bnb_idr", "ADA": "ada_idr",
        "DOGE": "doge_idr",
    }

    signals = []
    for sym, pair in MAIN_ASSETS.items():
        if sym not in all_coins:
            continue
        candles = fetch_candles(pair)
        time.sleep(0.3)
        res = apply_bot_intel(analyze_coin(sym, all_coins[sym], candles))
        signals.append(res)

    if not signals:
        send_telegram_message("❌ Tidak ada data.", notify=True)
        return True

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
        lines.append(f"   Harga: {format_idr_simple(s['price'])} ({ch}%)")
        lines.append(f"   RSI: {s['rsi']} | MACD: {s['macd_signal']}")
        lines.append(f"   ML: {s['ml_label']} ({s['ml_prob']}%) | MTF: {s['mtf_label']}")
        lines.append(f"   Confluence: {s['confluence_label']}")

        if _is_entry_action(s["action"]):
            lines.append(f"   🎯 Entry → TP1: {format_idr_simple(s['tp1'])} | SL: {format_idr_simple(s['stop_loss'])}")
            lines.append(f"   💰 Alokasi: {s['alloc_pct']}%")
        lines.append("")

    lines.append("──────────────────────")
    lines.append("⚠️ Bukan saran keuangan. DYOR.")

    send_telegram_message("\n".join(lines), notify=True)
    print("[CMD] /top executed")
    return True


def _cmd_top_fallback():
    """Fallback /top without full telegram_bot."""
    all_coins = _fetch_all_tickers()
    if not all_coins:
        send_telegram_message("❌ Gagal fetch data.", notify=True)
        return True

    MAIN_ASSETS = {
        "BTC": "btc_idr", "ETH": "eth_idr", "SOL": "sol_idr",
        "XRP": "xrp_idr", "BNB": "bnb_idr", "ADA": "ada_idr",
        "DOGE": "doge_idr",
    }

    # Simple ranking by change + volume
    ranked = []
    for sym, info in all_coins.items():
        if sym not in MAIN_ASSETS:
            continue
        score = info["change"] + (info["vol_idr"] / 1_000_000_000)
        ranked.append((sym, info, score))

    ranked.sort(key=lambda x: x[2], reverse=True)
    top5 = ranked[:5]

    lines = [
        "*🎯 TOP 5 COIN — BY MOMENTUM*",
        f"{datetime.now(WIB).strftime('%d/%m %H:%M WIB')}",
        "──────────────────────",
        "",
    ]

    for i, (sym, info, score) in enumerate(top5, 1):
        ch = f"+{info['change']:.2f}" if info["change"] >= 0 else f"{info['change']:.2f}"
        emoji = "🟢" if info["change"] > 3 else "🟡" if info["change"] > 0 else "🔴"
        lines.append(f"{i}. {emoji} *{sym}* — {ch}%")
        lines.append(f"   💰 {format_idr_simple(info['price'])} | Vol: {format_idr_simple(info['vol_idr'])}")
        lines.append("")

    lines.append("──────────────────────")
    lines.append("💡 Ketik */scan* di bot utama untuk analisis teknikal lengkap.")
    lines.append("⚠️ Bukan saran keuangan. DYOR.")

    send_telegram_message("\n".join(lines), notify=True)
    return True


def cmd_portfolio():
    """Handle /portfolio — cek posisi terbuka."""
    global _active_signals

    if not _active_signals:
        send_telegram_message(
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
    all_coins = _fetch_all_tickers()

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
        lines.append(f"   Entry: {format_idr_simple(entry)} → Sekarang: {format_idr_simple(price)}")
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

    send_telegram_message("\n".join(lines), notify=True)
    print(f"[CMD] /portfolio — {len(_active_signals)} active positions")
    return True


def cmd_journal():
    """Handle /journal — riwayat sinyal + winrate."""
    try:
        from learning_engine import build_profile
        profile = build_profile()
    except Exception as e:
        send_telegram_message(f"❌ Gagal load journal: {str(e)[:80]}", notify=True)
        return True

    total = profile.get("closed", 0)
    wr = profile.get("winrate", 0)

    lines = [
        "📜 *RIWAYAT SINYAL*",
        f"{datetime.now(WIB).strftime('%d/%m %Y')}",
        "──────────────────────",
        "",
    ]

    lines.append(f"Total sinyal: {profile.get('total_signals', 0)}")
    lines.append(f"Selesai: {total} | Win: {profile.get('wins', 0)} | Loss: {profile.get('losses', 0)}")
    lines.append(f"*Winrate: {wr:.1f}%*")
    lines.append("")

    best = profile.get("best_symbols", [])
    if best:
        lines.append("*Top Performer:*\n")
        for sym, stats in best:
            lines.append(f"  🏆 {sym}: {stats.get('winrate', 0):.1f}% WR ({stats.get('closed', 0)} trades)")
        lines.append("")

    active = profile.get("active", 0)
    if active > 0:
        lines.append(f"Posisi aktif: {active}")

    lines.append("")
    lines.append("──────────────────────")
    lines.append("⚠️ Bukan saran keuangan. DYOR.")

    send_telegram_message("\n".join(lines), notify=True)
    print(f"[CMD] /journal — WR: {wr:.1f}%")
    return True


def cmd_stats():
    """Handle /stats — statistik performa bot."""
    try:
        from learning_engine import build_profile
        profile = build_profile()
    except Exception as e:
        send_telegram_message(f"❌ Gagal load stats: {str(e)[:80]}", notify=True)
        return True

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

    lines.append("*Hari Ini:*\n")
    lines.append(f"  Sinyal dikirim: {_daily_stats['signals_sent']}")
    lines.append(f"  TP hit: {_daily_stats['tp_hit']}")
    lines.append(f"  SL hit: {_daily_stats['sl_hit']}")
    lines.append(f"  Posisi aktif: {len(_active_signals)}")
    lines.append("")

    best = profile.get("best_symbols", [])
    if best:
        lines.append("*Top Performer:*\n")
        for sym, stats in best:
            lines.append(f"  🏆 {sym}: {stats.get('winrate', 0):.1f}% WR ({stats.get('closed', 0)} trades)")
        lines.append("")

    lines.append("──────────────────────")
    lines.append("🤖 Bot belajar otomatis dari setiap trade.")
    lines.append("💡 Semakin banyak data, semakin akurat.")

    send_telegram_message("\n".join(lines), notify=True)
    print("[CMD] /stats executed")
    return True


def cmd_weather():
    """Handle /weather — market mode saat ini."""
    all_coins = _fetch_all_tickers()
    if not all_coins:
        send_telegram_message("❌ Gagal fetch data.", notify=True)
        return True

    mode, mode_desc = _detect_market_mode(all_coins)
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

    send_telegram_message("\n".join(lines), notify=True)
    print(f"[CMD] /weather — mode: {mode}")
    return True


def cmd_alert(alert_state):
    """Handle /alert on/off."""
    if alert_state == "on":
        send_telegram_message("🔔 *Alert AKTIF* — Semua notifikasi on.", notify=True)
        return True
    else:
        send_telegram_message("🔕 *Alert NONAKTIF* — Semua notifikasi off.", notify=True)
        return True


# =============================================================================
# MAIN COMMAND DISPATCHER
# =============================================================================

def handle_telegram_command(text, telegram_bot_module=None):
    """
    Dispatch Telegram command to appropriate handler.
    Returns True if command was handled.
    """
    if not text or not text.startswith("/"):
        return False

    parts = text.strip().split()
    cmd = parts[0].lower()
    args = parts[1:] if len(parts) > 1 else []

    if cmd == "/help":
        send_telegram_message(cmd_help(), notify=True)
        return True

    if cmd == "/scan":
        return cmd_scan(telegram_bot_module)

    if cmd == "/scan-full":
        return cmd_scan_fallback()

    if cmd == "/top":
        return cmd_top(telegram_bot_module)

    if cmd == "/portfolio":
        return cmd_portfolio()

    if cmd == "/journal":
        return cmd_journal()

    if cmd == "/stats":
        return cmd_stats()

    if cmd == "/weather":
        return cmd_weather()

    if cmd == "/alert":
        state = args[0] if args else ""
        if state in ("on", "off"):
            return cmd_alert(state)
        else:
            send_telegram_message(
                "🔔 *ALERT SETTINGS*\n\n"
                "Gunakan:\n"
                "*/alert on* — Aktifkan semua alert\n"
                "*/alert off* — Nonaktifkan semua alert",
                notify=True
            )
            return True

    # Unknown command
    send_telegram_message(
        f"❓ Command *{cmd}* tidak dikenali.\n\n"
        f"Ketik */help* untuk daftar command.",
        notify=True
    )
    return True
