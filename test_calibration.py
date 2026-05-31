"""Test untuk core/calibration.py dan backtest realistis di core/indicators.py.

Jalankan: python3 test_calibration.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import core.calibration as cal  # noqa: E402
import core.indicators as ci  # noqa: E402

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


def make_candles(n=320, seed=7, trend=0.0, start=10_000.0):
    rng = np.random.default_rng(seed)
    steps = rng.normal(trend, 50, n)
    close = np.clip(start + np.cumsum(steps), 1.0, None)
    high = close + np.abs(rng.normal(0, 30, n))
    low = np.clip(close - np.abs(rng.normal(0, 30, n)), 0.5, None)
    open_ = close + rng.normal(0, 10, n)
    vol = np.abs(rng.normal(1000, 200, n)) + 1
    times = (pd.Series(range(n)) * 3600 + 1_600_000_000).astype(int)
    return pd.DataFrame(
        {"time": times, "open": open_, "high": high, "low": low, "close": close, "volume": vol}
    )


# =============================================================================
# _to_unit
# =============================================================================
check("to_unit 0..1 lewat", cal._to_unit(0.7) == 0.7)
check("to_unit 0..100 dibagi", cal._to_unit(70) == 0.7)
check("to_unit clamp atas", cal._to_unit(150) == 1.0)
check("to_unit clamp bawah", cal._to_unit(-5) == 0.0)

# =============================================================================
# brier_score
# =============================================================================
check("brier kosong None", cal.brier_score([]) is None)
# Prediksi sempurna: 1.0 utk yang WIN, 0.0 utk LOSS -> brier 0
perfect = [(1.0, 1), (0.0, 0), (1.0, "WIN"), (0.0, "LOSS")]
check("brier sempurna = 0", cal.brier_score(perfect) == 0.0)
# Prediksi terbalik total -> brier 1
worst = [(0.0, 1), (1.0, 0)]
check("brier terburuk = 1", cal.brier_score(worst) == 1.0)
# Nebak 50% terus -> brier 0.25
half = [(50, 1), (50, 0), (50, 1), (50, 0)]
check("brier nebak 50% = 0.25", cal.brier_score(half) == 0.25)

# =============================================================================
# reliability_buckets
# =============================================================================
empty_buckets = cal.reliability_buckets([])
check("buckets kosong", empty_buckets == [])

# Semua prediksi 70%, separuh menang -> actual 50%, gap 20
seventy = [(70, 1), (70, 0), (70, 1), (70, 0)]
b = cal.reliability_buckets(seventy)
check("buckets 70% satu bin", len(b) == 1, f"len={len(b)}")
check("buckets avg_predicted 70", b[0]["avg_predicted"] == 70.0, str(b[0]))
check("buckets actual 50", b[0]["actual_freq"] == 50.0, str(b[0]))
check("buckets gap 20", b[0]["gap"] == 20.0, str(b[0]))
check("buckets count 4", b[0]["count"] == 4)

# =============================================================================
# ECE
# =============================================================================
check("ece kosong None", cal.expected_calibration_error([]) is None)
# Terkalibrasi sempurna: bin 70% benar2 70% menang (10 sampel)
calibrated = [(70, 1)] * 7 + [(70, 0)] * 3
ece_cal = cal.expected_calibration_error(calibrated)
check("ece terkalibrasi ~0", ece_cal == 0.0, f"ece={ece_cal}")
# Tidak terkalibrasi: bilang 90% tapi cuma 10% menang
miscal = [(90, 1)] + [(90, 0)] * 9
ece_mis = cal.expected_calibration_error(miscal)
check("ece miskalibrasi tinggi", ece_mis > 0.5, f"ece={ece_mis}")

# =============================================================================
# calibration_grade
# =============================================================================
g_low = cal.calibration_grade(0.1, 0.03, 5)
check("grade data kurang", g_low["grade"] == "DATA KURANG")
g_good = cal.calibration_grade(0.18, 0.04, 50)
check("grade baik", g_good["grade"] == "TERKALIBRASI BAIK", str(g_good))
g_bad = cal.calibration_grade(0.30, 0.20, 50)
check("grade buruk", g_bad["grade"] == "BELUM TERKALIBRASI", str(g_bad))

# =============================================================================
# build_calibration_report
# =============================================================================
rng = np.random.default_rng(1)
# Bangun dataset terkalibrasi: outcome ~ bernoulli(prob)
sample = []
for _ in range(300):
    p = rng.uniform(0.1, 0.9)
    y = 1 if rng.random() < p else 0
    sample.append((p * 100, y))
report = cal.build_calibration_report(sample)
check("report sample_count", report["sample_count"] == 300)
check("report punya brier", report["brier_score"] is not None)
check("report punya buckets", len(report["buckets"]) > 0)
check("report terkalibrasi (data jujur)", report["ece"] < 0.1, f"ece={report['ece']}")

# =============================================================================
# extract_pairs_from_journal
# =============================================================================
journal = {
    "signals": [
        {"status": "TARGET", "outcome": "WIN", "forecast_prob": 72},
        {"status": "SL", "outcome": "LOSS", "ml_prob": 40},
        {"status": "OPEN", "outcome": None, "forecast_prob": 60},  # diabaikan (belum tutup)
        {"status": "EXPIRED", "outcome": "LOSS"},  # diabaikan (tidak ada prob)
        {"status": "TP", "outcome": "WIN", "forecast_step1_prob": 65},
    ]
}
pairs = cal.extract_pairs_from_journal(journal)
check("extract hanya yg punya prob & tertutup", len(pairs) == 3, f"pairs={pairs}")
check("extract outcome benar", sorted(p[1] for p in pairs) == [0, 1, 1], str(pairs))

# =============================================================================
# INTEGRASI: forecast_prob disimpan saat record_signal & terbaca utk kalibrasi
# =============================================================================
import tempfile  # noqa: E402

_d = tempfile.mkdtemp(prefix="test_calib_")
os.environ["SIGNAL_JOURNAL_FILE"] = os.path.join(_d, "j.json")
os.environ["SIGNAL_JOURNAL_DB"] = os.path.join(_d, "j.db")
import journal_store  # noqa: E402

journal_store.reset_journal()
import learning_engine as le  # noqa: E402

le.SIGNAL_LEARNING_DEDUPE_HOURS = 0


def _entry(a):
    return True


_item = {
    "symbol": "BTCUSDT", "action": "BUY", "score": 80, "allocation_pct": 8,
    "confluence_passed": 5, "entry": 50000, "tp1": 51000, "target": 52000,
    "stop_loss": 49000, "forecast_step1_prob": 72,
}
le.record_signal(_item, _entry)
_j = journal_store.load_journal()
check("forecast_prob tersimpan", _j["signals"][0].get("forecast_prob") == 72.0,
      str(_j["signals"][0].get("forecast_prob")))
# Tutup sebagai WIN, lalu pastikan terbaca untuk kalibrasi
le.train_from_prices([{"symbol": "BTCUSDT", "price": 52500}])
_j2 = journal_store.load_journal()
_pairs = cal.extract_pairs_from_journal(_j2)
check("forecast_prob -> pair kalibrasi", _pairs == [(72.0, 1)], str(_pairs))
journal_store.reset_journal()

# =============================================================================
# BACKTEST REALISTIS
# =============================================================================
bt = ci.compute_backtest(make_candles())
check("bt key baru lengkap",
      {"bt_wr", "bt_trades", "bt_label", "bt_wr_gross", "bt_oos_wr", "bt_avg_net_pct", "bt_cost_pct"} <= set(bt))
check("bt cost = 0.8 default", bt["bt_cost_pct"] == 0.8, f"cost={bt['bt_cost_pct']}")
# Winrate net harus <= gross (biaya hanya menurunkan, tidak menaikkan)
if bt["bt_trades"] >= 6:
    check("bt net <= gross", bt["bt_wr"] <= bt["bt_wr_gross"], f"net={bt['bt_wr']} gross={bt['bt_wr_gross']}")
    check("bt oos 0..100", 0 <= bt["bt_oos_wr"] <= 100)
# Fee lebih tinggi -> winrate net tidak boleh lebih tinggi
bt_highfee = ci.compute_backtest(make_candles(), fee_pct_per_side=1.0, slippage_pct_per_side=0.5)
check("bt fee tinggi -> net <= net default", bt_highfee["bt_wr"] <= bt["bt_wr"] + 1e-9,
      f"highfee={bt_highfee['bt_wr']} default={bt['bt_wr']}")
check("bt data kurang default", ci.compute_backtest(make_candles(n=20))["bt_label"] == "DATA KURANG")
# Default backtest tetap punya key cost meski data kurang
check("bt default tetap punya cost key", "bt_cost_pct" in ci.compute_backtest(make_candles(n=20)))

# build_verdict masih jalan dgn struktur bt baru (key lama tetap ada)
adx = ci.compute_adx(make_candles())
ml = ci.compute_ml_forecast(make_candles())
v = ci.build_verdict(70, 55, "bullish", "bullish", adx, ml, bt, "SEDANG", 6_000_000_000)
check("build_verdict kompatibel dgn bt baru", v[0] in {"APPROVE", "APPROVE KECIL", "TUNGGU", "TOLAK"}, str(v))

print(f"\n=== {passed}/{passed + failed} tests passed ===")
sys.exit(0 if failed == 0 else 1)
