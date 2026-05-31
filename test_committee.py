"""Test untuk core/committee.py — lapisan penjelas keputusan.

Jalankan: python3 test_committee.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

import core.committee as cm  # noqa: E402

passed = 0
failed = 0


def check(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
        print(f"PASS: {name}")
    else:
        failed += 1
        print(f"FAIL: {name} {detail}")


VOTES = {"BULLISH", "BEARISH", "NETRAL"}

# =============================================================================
# Agen individual
# =============================================================================
t_bull = cm.technical_agent(rsi=55, macd_signal="bullish cross", supertrend="bullish", ema_bias="bullish")
check("technical bullish", t_bull["vote"] == "BULLISH", str(t_bull))
t_bear = cm.technical_agent(rsi=82, macd_signal="bearish cross", supertrend="bearish", ema_bias="bearish")
check("technical bearish", t_bear["vote"] == "BEARISH", str(t_bear))
check("technical punya reason", len(t_bull["reason"]) > 0)

ml_b = cm.ml_agent({"ml_prob": 72, "ml_conf": "tinggi", "ml_wf_acc": 60})
check("ml bullish + bobot tinggi", ml_b["vote"] == "BULLISH" and ml_b["weight"] >= 1.0, str(ml_b))
ml_low = cm.ml_agent({"ml_prob": 72, "ml_conf": "rendah", "ml_wf_acc": None})
check("ml conf rendah -> bobot kecil", ml_low["weight"] < 0.5, str(ml_low))
ml_bear = cm.ml_agent({"ml_prob": 35, "ml_conf": "sedang", "ml_wf_acc": 55})
check("ml bearish", ml_bear["vote"] == "BEARISH")

check("regime risk_on bullish", cm.regime_agent({"regime": "RISK_ON", "btc_momentum_pct": 3.0})["vote"] == "BULLISH")
check("regime risk_off bearish", cm.regime_agent({"regime": "RISK_OFF", "btc_momentum_pct": -4.0})["vote"] == "BEARISH")
check("regime no data netral", cm.regime_agent({"regime": "NO DATA"})["vote"] == "NETRAL")

bt_strong = cm.backtest_agent({"bt_trades": 20, "bt_wr": 65, "bt_oos_wr": 62})
check("backtest kuat bullish", bt_strong["vote"] == "BULLISH", str(bt_strong))
# OOS jeblok -> diturunkan ke netral (pola basi)
bt_stale = cm.backtest_agent({"bt_trades": 20, "bt_wr": 65, "bt_oos_wr": 40})
check("backtest OOS jeblok -> netral", bt_stale["vote"] == "NETRAL", str(bt_stale))
bt_thin = cm.backtest_agent({"bt_trades": 3, "bt_wr": 80})
check("backtest data kurang netral", bt_thin["vote"] == "NETRAL")

risk_hi = cm.risk_agent("TINGGI", 6_000_000_000)
check("risk tinggi -> bearish + bobot besar", risk_hi["vote"] == "BEARISH" and risk_hi["weight"] >= 1.5, str(risk_hi))
risk_thin = cm.risk_agent("SEDANG", 50_000_000)
check("risk likuiditas tipis -> bearish", risk_thin["vote"] == "BEARISH")
check("risk rendah -> bullish", cm.risk_agent("RENDAH", 6_000_000_000)["vote"] == "BULLISH")

# =============================================================================
# build_committee
# =============================================================================
bullish_item = {
    "rsi": 55, "macd_signal": "bullish cross", "supertrend": "bullish", "ema_bias": "bullish",
    "ml_prob": 70, "ml_conf": "tinggi", "ml_wf_acc": 60,
    "bt_trades": 20, "bt_wr": 63, "bt_oos_wr": 60,
    "btc_regime": "RISK_ON", "btc_momentum_pct": 3.0,
    "risk_level": "RENDAH", "vol_idr": 6_000_000_000,
}
com = cm.build_committee(bullish_item)
check("committee punya 5 agen", len(com["agents"]) == 5, str(len(com["agents"])))
check("committee semua vote valid", all(a["vote"] in VOTES for a in com["agents"]))
check("committee bullish konsensus naik", com["consensus"] == "SETUJU NAIK", str(com))
check("committee consensus_pct 0..100", 0 <= com["consensus_pct"] <= 100)
check("committee bull > bear (item bullish)", com["bull_weight"] > com["bear_weight"])

bearish_item = {
    "rsi": 82, "macd_signal": "bearish cross", "supertrend": "bearish", "ema_bias": "bearish",
    "ml_prob": 32, "ml_conf": "sedang", "ml_wf_acc": 54,
    "bt_trades": 20, "bt_wr": 42, "bt_oos_wr": 40,
    "btc_regime": "RISK_OFF", "btc_momentum_pct": -4.0,
    "risk_level": "TINGGI", "vol_idr": 50_000_000,
}
com_bear = cm.build_committee(bearish_item)
check("committee bearish konsensus turun", com_bear["consensus"] == "SETUJU TURUN", str(com_bear))
check("committee bear > bull (item bearish)", com_bear["bear_weight"] > com_bear["bull_weight"])

# Item kosong/default tidak crash
com_empty = cm.build_committee({})
check("committee item kosong tidak crash", len(com_empty["agents"]) == 5)

# Summary line
line = cm.committee_summary_line(com)
check("summary line ada angka", "naik" in line and "%" in line, line)

# Konsistensi: build_committee TIDAK mengubah item (tidak ada side-effect)
snapshot = dict(bullish_item)
cm.build_committee(bullish_item)
check("build_committee tidak mengubah item", bullish_item == snapshot)

print(f"\n=== {passed}/{passed + failed} tests passed ===")
sys.exit(0 if failed == 0 else 1)
