"""Komite agen — lapisan PENJELAS keputusan (transparan, gratis, deterministik).

PENTING: modul ini TIDAK mengambil keputusan akhir. Keputusan tetap milik
`core.analysis.decide_action` (yang sudah teruji). Komite ini hanya menjelaskan
"kenapa" dengan memecah angka indikator yang SUDAH dihitung menjadi suara
beberapa agen spesialis + alasan tiap agen.

Nol panggilan API, nol biaya — murni aritmatika atas data yang sudah ada.
Tujuannya: keputusan jadi bisa dijelaskan ("BELI karena 4 dari 5 agen setuju")
dan tiap agen bisa diukur akurasinya lewat panel kalibrasi nanti.

Tiap agen mengembalikan dict:
    {"name", "vote", "weight", "reason"}
  vote: "BULLISH" / "BEARISH" / "NETRAL"
"""
from __future__ import annotations


def _vote(name, vote, weight, reason):
    return {"name": name, "vote": vote, "weight": weight, "reason": reason}


def technical_agent(rsi, macd_signal, supertrend, ema_bias):
    """Agen teknikal klasik: EMA/MACD/Supertrend/RSI."""
    score = 0
    bits = []
    if macd_signal in ("bullish cross", "bullish"):
        score += 2 if "cross" in macd_signal else 1
        bits.append("MACD naik")
    elif macd_signal in ("bearish cross", "bearish"):
        score -= 2 if "cross" in macd_signal else 1
        bits.append("MACD turun")
    if supertrend == "bullish":
        score += 1
        bits.append("Supertrend hijau")
    elif supertrend == "bearish":
        score -= 1
        bits.append("Supertrend merah")
    if ema_bias == "bullish":
        score += 1
    elif ema_bias == "bearish":
        score -= 1
    if rsi > 78:
        score -= 1
        bits.append(f"RSI panas {rsi:.0f}")
    elif 45 <= rsi <= 68:
        bits.append(f"RSI sehat {rsi:.0f}")
    vote = "BULLISH" if score >= 2 else "BEARISH" if score <= -2 else "NETRAL"
    reason = ", ".join(bits) if bits else "sinyal teknikal campuran"
    return _vote("Teknikal", vote, 1.0, reason)


def ml_agent(ml):
    """Agen ML: hasil KNN yang sudah di-shrink walk-forward."""
    prob = ml.get("ml_prob", 50)
    conf = ml.get("ml_conf", "rendah")
    wf = ml.get("ml_wf_acc")
    weight = {"tinggi": 1.2, "sedang": 0.8, "rendah": 0.4}.get(conf, 0.4)
    if prob >= 60:
        vote = "BULLISH"
    elif prob <= 40:
        vote = "BEARISH"
    else:
        vote = "NETRAL"
    wf_txt = f", akurasi uji {wf:.0f}%" if wf is not None else ", skill belum teruji"
    reason = f"prob naik {prob:.0f}% (conf {conf}{wf_txt})"
    return _vote("ML/KNN", vote, weight, reason)


def regime_agent(regime):
    """Agen regime: kondisi BTC global."""
    reg = regime.get("regime", "NO DATA") if regime else "NO DATA"
    mom = regime.get("btc_momentum_pct", 0.0) if regime else 0.0
    if reg == "RISK_ON":
        return _vote("Regime BTC", "BULLISH", 0.8, f"BTC sehat (+{mom:.1f}%)")
    if reg == "RISK_OFF":
        return _vote("Regime BTC", "BEARISH", 1.0, f"BTC lemah ({mom:.1f}%), market global jatuh")
    return _vote("Regime BTC", "NETRAL", 0.5, "BTC sideways / data kurang")


def backtest_agent(bt):
    """Agen backtest: pola serupa di masa lalu (net + out-of-sample)."""
    trades = bt.get("bt_trades", 0)
    if trades < 6:
        return _vote("Backtest", "NETRAL", 0.3, "data historis belum cukup")
    wr = bt.get("bt_wr", 0)
    oos = bt.get("bt_oos_wr")
    weight = 1.0 if trades >= 12 else 0.6
    if wr >= 58:
        vote = "BULLISH"
    elif wr <= 45:
        vote = "BEARISH"
    else:
        vote = "NETRAL"
    oos_txt = f", OOS {oos:.0f}%" if oos is not None else ""
    # Kalau out-of-sample jeblok jauh, turunkan ke NETRAL (pola mungkin basi)
    if oos is not None and (wr - oos) >= 20 and vote == "BULLISH":
        vote = "NETRAL"
        oos_txt += " (memburuk, pola basi)"
    return _vote("Backtest", vote, weight, f"winrate net {wr:.0f}%{oos_txt} dari {trades} uji")


def risk_agent(risk_level, vol_idr):
    """Agen risiko: hak VETO konteks. BEARISH = waspada, bukan sinyal jual."""
    if risk_level == "TINGGI":
        return _vote("Risiko", "BEARISH", 1.5, "risiko TINGGI — tahan diri / size kecil")
    if vol_idr < 100_000_000:
        return _vote("Risiko", "BEARISH", 1.2, "likuiditas tipis — rawan slippage")
    if risk_level == "RENDAH":
        return _vote("Risiko", "BULLISH", 0.6, "risiko terkendali")
    return _vote("Risiko", "NETRAL", 0.6, "risiko sedang")


def build_committee(item):
    """Susun semua suara agen dari satu hasil analisis (dict `item`).

    `item` adalah hasil analyze_coin / analyze_coin_advanced yang sudah berisi
    semua angka indikator. Mengembalikan ringkasan transparan — TIDAK mengubah
    item["action"] (keputusan tetap dari decide_action).
    """
    ml = {
        "ml_prob": item.get("ml_prob", 50),
        "ml_conf": item.get("ml_conf", "rendah"),
        "ml_wf_acc": item.get("ml_wf_acc"),
    }
    bt = {
        "bt_trades": item.get("bt_trades", 0),
        "bt_wr": item.get("bt_wr", 0),
        "bt_oos_wr": item.get("bt_oos_wr"),
    }
    regime = {
        "regime": item.get("btc_regime", "NO DATA"),
        "btc_momentum_pct": item.get("btc_momentum_pct", 0.0),
    }
    agents = [
        technical_agent(
            item.get("rsi", 50), item.get("macd_signal", "netral"),
            item.get("supertrend", "netral"), item.get("ema_bias", "netral"),
        ),
        ml_agent(ml),
        regime_agent(regime),
        backtest_agent(bt),
        risk_agent(item.get("risk_level", "SEDANG"), item.get("vol_idr", 0)),
    ]

    bull_w = sum(a["weight"] for a in agents if a["vote"] == "BULLISH")
    bear_w = sum(a["weight"] for a in agents if a["vote"] == "BEARISH")
    n_bull = sum(1 for a in agents if a["vote"] == "BULLISH")
    n_bear = sum(1 for a in agents if a["vote"] == "BEARISH")
    n_neutral = sum(1 for a in agents if a["vote"] == "NETRAL")
    total_w = bull_w + bear_w
    consensus_pct = round(bull_w / total_w * 100, 1) if total_w > 0 else 50.0

    if bull_w > bear_w * 1.3:
        consensus = "SETUJU NAIK"
    elif bear_w > bull_w * 1.3:
        consensus = "SETUJU TURUN"
    else:
        consensus = "TERBELAH"

    return {
        "agents": agents,
        "bull_votes": n_bull,
        "bear_votes": n_bear,
        "neutral_votes": n_neutral,
        "bull_weight": round(bull_w, 2),
        "bear_weight": round(bear_w, 2),
        "consensus": consensus,
        "consensus_pct": consensus_pct,
    }


def committee_summary_line(committee):
    """Satu baris ringkas untuk Telegram / UI."""
    return (
        f"Komite: {committee['bull_votes']} naik / {committee['bear_votes']} turun / "
        f"{committee['neutral_votes']} netral → {committee['consensus']} ({committee['consensus_pct']:.0f}%)"
    )
