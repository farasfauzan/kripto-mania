"""Test untuk core/analysis.py — logika keputusan terpadu web & bot.

Jalankan: python3 test_analysis.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

import core.analysis as ca  # noqa: E402

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


ML = {"ml_prob": 60.0, "ml_label": "BULLISH", "ml_conf": "sedang"}
BT = {"bt_wr": 60.0, "bt_trades": 12, "bt_label": "TERUJI"}
ML_BEAR = {"ml_prob": 35.0, "ml_label": "BEARISH", "ml_conf": "tinggi"}
BT_WEAK = {"bt_wr": 40.0, "bt_trades": 12, "bt_label": "LEMAH"}
CONF_FULL = {"confluence_passed": 5, "allow_entry": True}
CONF_4 = {"confluence_passed": 4, "allow_entry": True}
CONF_3 = {"confluence_passed": 3, "allow_entry": False}
CONF_2 = {"confluence_passed": 2, "allow_entry": False}

# =============================================================================
# compute_base_score
# =============================================================================
base_bull, comp = ca.compute_base_score(
    change=3.0, ema_trend_pct=2.0, macd_signal="bullish cross", rsi=55,
    supertrend="bullish", vol_label="kuat", bb_signal="netral",
    adx_trend="bullish", ml=ML, bt=BT, mtf_adjustment=4,
    vol_idr=6_000_000_000, symbol="ETH", is_micin=False,
)
base_bear, _ = ca.compute_base_score(
    change=-3.0, ema_trend_pct=-2.0, macd_signal="bearish cross", rsi=82,
    supertrend="bearish", vol_label="tipis", bb_signal="overbought",
    adx_trend="bearish", ml=ML_BEAR, bt=BT_WEAK, mtf_adjustment=-6,
    vol_idr=50_000_000, symbol="DOGE", is_micin=True,
)
check("base bull > bear", base_bull > base_bear, f"bull={base_bull} bear={base_bear}")
check("base komponen tech_score ada", "tech_score" in comp)
# Micin penalty mengurangi skor
base_no_micin, _ = ca.compute_base_score(
    change=3.0, ema_trend_pct=2.0, macd_signal="bullish", rsi=55,
    supertrend="bullish", vol_label="kuat", bb_signal="netral",
    adx_trend="bullish", ml=ML, bt=BT, mtf_adjustment=0,
    vol_idr=6_000_000_000, symbol="ETH", is_micin=False,
)
base_micin, _ = ca.compute_base_score(
    change=3.0, ema_trend_pct=2.0, macd_signal="bullish", rsi=55,
    supertrend="bullish", vol_label="kuat", bb_signal="netral",
    adx_trend="bullish", ml=ML, bt=BT, mtf_adjustment=0,
    vol_idr=6_000_000_000, symbol="PEPE", is_micin=True,
)
check("micin penalty mengurangi", base_micin < base_no_micin, f"micin={base_micin} no={base_no_micin}")

# =============================================================================
# decide_action — threshold dasar
# =============================================================================
check("score 85 + momentum -> BELI KUAT",
      ca.decide_action(85, 2.0, CONF_FULL, 40, 4)[0] == "BELI KUAT")
check("score 70 -> CICIL BELI",
      ca.decide_action(70, 1.0, CONF_FULL, 40, 4)[0] == "CICIL BELI")
check("score 55 -> WATCH",
      ca.decide_action(55, 1.0, CONF_FULL, 40, 4)[0] == "WATCH")
check("score 40 -> JANGAN BELI",
      ca.decide_action(40, 1.0, CONF_FULL, 40, 4)[0] == "JANGAN BELI")
check("score 20 -> HINDARI",
      ca.decide_action(20, 1.0, CONF_FULL, 40, 4)[0] == "HINDARI")
check("score 85 tapi momentum <=1 -> bukan BELI KUAT",
      ca.decide_action(85, 0.5, CONF_FULL, 40, 4)[0] != "BELI KUAT")

# =============================================================================
# Confluence gate
# =============================================================================
check("confluence 3/5 turunkan ke WATCH",
      ca.decide_action(85, 2.0, CONF_3, 40, 4)[0] == "WATCH")
check("confluence 2/5 -> JANGAN BELI",
      ca.decide_action(85, 2.0, CONF_2, 40, 4)[0] == "JANGAN BELI")
check("confluence 4/5 boleh BELI KUAT",
      ca.decide_action(85, 2.0, CONF_4, 40, 4)[0] == "BELI KUAT")

# =============================================================================
# Anti-FOMO
# =============================================================================
check("anti-FOMO range>85 change>5 -> WATCH",
      ca.decide_action(85, 6.0, CONF_FULL, 90, 4)[0] == "WATCH")
check("anti-FOMO tidak aktif kalau range rendah",
      ca.decide_action(85, 6.0, CONF_FULL, 50, 4)[0] == "BELI KUAT")

# =============================================================================
# MTF guard
# =============================================================================
check("MTF <= -5 -> WATCH",
      ca.decide_action(85, 2.0, CONF_FULL, 40, -6)[0] == "WATCH")
check("MTF -4 tidak blokir",
      ca.decide_action(85, 2.0, CONF_FULL, 40, -4)[0] == "BELI KUAT")

# =============================================================================
# Regime guard
# =============================================================================
check("regime RISK_OFF turunkan BELI KUAT ke CICIL",
      ca.decide_action(85, 2.0, CONF_FULL, 40, 4, regime_allow_aggressive=False)[0] == "CICIL BELI")
check("regime RISK_ON tidak ubah",
      ca.decide_action(85, 2.0, CONF_FULL, 40, 4, regime_allow_aggressive=True)[0] == "BELI KUAT")

# =============================================================================
# Verdict committee
# =============================================================================
check("verdict TOLAK -> JANGAN BELI",
      ca.decide_action(85, 2.0, CONF_FULL, 40, 4, verdict="TOLAK")[0] == "JANGAN BELI")
check("verdict TUNGGU -> WATCH",
      ca.decide_action(85, 2.0, CONF_FULL, 40, 4, verdict="TUNGGU")[0] == "WATCH")
check("verdict APPROVE tidak ubah",
      ca.decide_action(85, 2.0, CONF_FULL, 40, 4, verdict="APPROVE")[0] == "BELI KUAT")

# =============================================================================
# compute_risk_level
# =============================================================================
check("risk rendah (stabil)",
      ca.compute_risk_level(2.0, 6_000_000_000, 55, "bullish", "bullish", 40, ML, BT) == "RENDAH")
check("risk tinggi (volatil + ilikuid)",
      ca.compute_risk_level(12.0, 50_000_000, 82, "bearish cross", "bearish", 90, ML_BEAR, BT_WEAK) == "TINGGI")

# =============================================================================
# KONSISTENSI WEB vs BOT: keputusan harus IDENTIK untuk input sama
# =============================================================================
# Simulasi: web & bot dgn skor & gate sama HARUS hasil action sama.
scenarios = [
    (85, 2.0, CONF_FULL, 40, 4, True, "APPROVE"),
    (70, 0.5, CONF_4, 60, 0, True, "APPROVE KECIL"),
    (88, 9.0, CONF_FULL, 95, 4, True, "APPROVE"),
    (82, 2.0, CONF_3, 40, -7, False, "TUNGGU"),
    (45, 1.0, CONF_2, 30, 0, True, None),
]
all_consistent = True
for sc in scenarios:
    score, change, conf, rp, mtf, allow, verdict = sc
    a1 = ca.decide_action(score, change, conf, rp, mtf, allow, verdict)
    a2 = ca.decide_action(score, change, conf, rp, mtf, allow, verdict)
    if a1 != a2:
        all_consistent = False
check("keputusan deterministik (web==bot)", all_consistent)

print(f"\n=== {passed}/{passed + failed} tests passed ===")
sys.exit(0 if failed == 0 else 1)
