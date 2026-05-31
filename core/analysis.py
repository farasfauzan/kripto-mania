"""Logika keputusan sinyal — sumber kebenaran tunggal untuk web & bot.

Sebelumnya, web (`analyze_coin_advanced`) dan bot (`analyze_coin`) punya
threshold action & gate yang BERBEDA, sehingga koin yang sama bisa
"CICIL BELI" di web tapi "JANGAN BELI" di Telegram. Modul ini menyatukan
keputusan itu supaya tidak akan pernah lagi kontradiktif.

Pemisahan tanggung jawab:
  - SCORING DASAR (compute_base_score): faktor teknikal yg sama persis di
    kedua permukaan (EMA/MACD/RSI/Supertrend/Volume/BB/ADX/ML/Backtest/MTF).
  - PENYESUAIAN EKSTRA (extra_adjustment): web menambahkan intel/smart/
    forecast/mode/regime; bot mengirim 0. Ini satu-satunya titik perbedaan
    yang DIIZINKAN, dan sifatnya menambah konteks, bukan mengubah aturan.
  - KEPUTUSAN (decide_action): threshold & semua gate (confluence, anti-FOMO,
    MTF, regime, verdict) — IDENTIK untuk web & bot.

Threshold mengikuti versi web (lebih lengkap & konservatif) sebagai standar.
"""
from __future__ import annotations

from core.indicators import clamp, is_entry_action


# Ambang keputusan — satu definisi, dipakai web & bot.
THRESHOLDS = {
    "beli_kuat_score": 80,
    "beli_kuat_change": 1.0,
    "cicil_score": 65,
    "cicil_change": 0.0,
    "watch_score": 50,
    "jangan_score": 35,
    # Gate
    "confluence_min_entry": 4,      # < ini, entry tidak diizinkan penuh
    "confluence_watch_floor": 3,    # 3 -> turun ke WATCH, < 3 -> JANGAN BELI
    "antifomo_range_pos": 85,
    "antifomo_change": 5,
    "mtf_guard": -5,                # MTF adjustment <= ini -> jangan agresif
}


def compute_base_score(change, ema_trend_pct, macd_signal, rsi, supertrend,
                       vol_label, bb_signal, adx_trend, ml, bt, mtf_adjustment,
                       vol_idr, symbol, is_micin, range_pos=50):
    """Skor teknikal dasar (0..100 sebelum extra). IDENTIK web & bot.

    Mengembalikan (score_base_float, komponen) — score belum di-clamp/round
    supaya pemanggil bisa menambah extra_adjustment dulu.
    """
    liquidity_bonus = min(16, vol_idr / 1_000_000_000)
    fomo_penalty = 9 if range_pos > 88 and change > 8 else 0
    micin_penalty = 6 if is_micin else 0

    tech_score = 0
    tech_score += clamp(ema_trend_pct * 3, -12, 12)
    tech_score += (
        8 if macd_signal == "bullish cross" else 5 if macd_signal == "bullish"
        else -8 if macd_signal == "bearish cross" else -5 if macd_signal == "bearish" else 0
    )
    tech_score += 6 if 45 <= rsi <= 68 else -7 if rsi > 78 else -4 if rsi < 30 else 0
    tech_score += 5 if supertrend == "bullish" else -6 if supertrend == "bearish" else 0
    tech_score += 4 if vol_label in ("spike", "kuat") else -3 if vol_label == "tipis" else 0

    bb_bonus = 7 if bb_signal == "oversold" else -5 if bb_signal == "overbought" else 0
    adx_bonus = 5 if adx_trend in ("bullish_strong", "bullish") else -5 if adx_trend in ("bearish_strong", "bearish") else 0

    ml_adj = (ml["ml_prob"] - 50) * 0.28
    if ml["ml_conf"] == "rendah":
        ml_adj *= 0.45
    elif ml["ml_conf"] == "sedang":
        ml_adj *= 0.75

    bt_adj = 0
    if bt["bt_trades"] >= 6:
        bt_adj = (bt["bt_wr"] - 50) * 0.12

    base = (
        50
        + change * 4.2
        + liquidity_bonus
        + tech_score * 0.65
        + bb_bonus
        + adx_bonus
        + ml_adj
        + bt_adj
        + mtf_adjustment
        - fomo_penalty
        - micin_penalty
    )
    return base, {
        "liquidity_bonus": liquidity_bonus,
        "tech_score": tech_score,
        "bb_bonus": bb_bonus,
        "adx_bonus": adx_bonus,
        "ml_adj": ml_adj,
        "bt_adj": bt_adj,
        "fomo_penalty": fomo_penalty,
        "micin_penalty": micin_penalty,
    }


def decide_action(score, change, confluence, range_pos, mtf_adjustment,
                  regime_allow_aggressive=True, verdict=None):
    """Tentukan action + emoji dari score & semua gate. IDENTIK web & bot.

    Urutan gate (dari pengaruh terbesar):
      1. Threshold dasar score+momentum
      2. Confluence gate (butuh >=4/5 untuk entry penuh)
      3. Anti-FOMO (jangan kejar candle di dekat puncak)
      4. MTF guard (jangan agresif lawan 4H/1D bearish)
      5. Regime guard (BTC RISK_OFF -> tahan agresif)
      6. Verdict committee (TOLAK/TUNGGU)
    """
    t = THRESHOLDS
    # 1. Threshold dasar
    if score >= t["beli_kuat_score"] and change > t["beli_kuat_change"]:
        action, emoji = "BELI KUAT", "🟢"
    elif score >= t["cicil_score"] and change > t["cicil_change"]:
        action, emoji = "CICIL BELI", "🟡"
    elif score >= t["watch_score"]:
        action, emoji = "WATCH", "⚪"
    elif score >= t["jangan_score"]:
        action, emoji = "JANGAN BELI", "🔴"
    else:
        action, emoji = "HINDARI", "⛔"

    passed = confluence.get("confluence_passed", 0)
    allow_entry = confluence.get("allow_entry", passed >= t["confluence_min_entry"])

    # 2. Confluence gate
    if not allow_entry and action in ("BELI KUAT", "CICIL BELI"):
        if passed >= t["confluence_watch_floor"]:
            action, emoji = "WATCH", "⚪"
        else:
            action, emoji = "JANGAN BELI", "🔴"

    # 3. Anti-FOMO
    if range_pos > t["antifomo_range_pos"] and change > t["antifomo_change"]:
        if action in ("BELI KUAT", "CICIL BELI"):
            action, emoji = "WATCH", "⚪"

    # 4. MTF guard
    if mtf_adjustment <= t["mtf_guard"] and action in ("BELI KUAT", "CICIL BELI"):
        action, emoji = "WATCH", "⚪"

    # 5. Regime guard
    if not regime_allow_aggressive and action == "BELI KUAT":
        action, emoji = "CICIL BELI", "🟡"

    # 6. Verdict committee
    if verdict == "TOLAK":
        action, emoji = "JANGAN BELI", "🔴"
    elif verdict == "TUNGGU" and is_entry_action(action):
        action, emoji = "WATCH", "⚪"

    return action, emoji


def compute_risk_level(change, vol_idr, rsi, macd_signal, supertrend, range_pos, ml, bt):
    """Risk level RENDAH/SEDANG/TINGGI. IDENTIK web & bot."""
    risk_pts = 0
    if abs(change) >= 10:
        risk_pts += 2
    elif abs(change) >= 5:
        risk_pts += 1
    if vol_idr < 100_000_000:
        risk_pts += 2
    elif vol_idr < 1_000_000_000:
        risk_pts += 1
    if rsi > 78:
        risk_pts += 1
    if macd_signal == "bearish cross":
        risk_pts += 1
    if supertrend == "bearish":
        risk_pts += 1
    if range_pos > 85:
        risk_pts += 1
    if ml["ml_label"] == "BEARISH" and ml["ml_conf"] != "rendah":
        risk_pts += 1
    if bt["bt_label"] == "LEMAH" and bt["bt_trades"] >= 10:
        risk_pts += 1
    return "TINGGI" if risk_pts >= 4 else "SEDANG" if risk_pts >= 2 else "RENDAH"
