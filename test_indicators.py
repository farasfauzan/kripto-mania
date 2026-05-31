"""Test untuk core/indicators.py — jaring pengaman bagi otak sinyal.

Gaya test mengikuti test_learning.py (assert polos + exit code, tanpa pytest)
supaya bisa dijalankan: python3 test_indicators.py

Yang diuji:
- Kontrak nilai (RSI 0-100, prob 0-100, score 0-100)
- Penanganan data kosong / kurang → default aman, tidak crash
- Invariant struktur (confluence passed sesuai checks, verdict valid)
- Konsistensi tipe & key output
"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

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
    """Candle sintetik deterministik (time dalam detik, kolom OHLCV)."""
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


EMPTY = pd.DataFrame()
FULL = make_candles()
UPTREND = make_candles(seed=3, trend=40.0)
DOWNTREND = make_candles(seed=9, trend=-40.0)
TINY = make_candles(n=5)

# =============================================================================
# clamp
# =============================================================================
check("clamp dalam rentang", ci.clamp(5, 0, 10) == 5)
check("clamp bawah", ci.clamp(-3, 0, 10) == 0)
check("clamp atas", ci.clamp(99, 0, 10) == 10)
check("clamp batas", ci.clamp(10, 0, 10) == 10)

# =============================================================================
# is_entry_action
# =============================================================================
check("entry BELI KUAT", ci.is_entry_action("🟢 BELI KUAT") is True)
check("entry CICIL BELI", ci.is_entry_action("CICIL BELI") is True)
check("entry HOLD bukan", ci.is_entry_action("HOLD") is False)
check("entry JANGAN BELI bukan", ci.is_entry_action("JANGAN BELI") is False)
check("entry None aman", ci.is_entry_action(None) is False)

# =============================================================================
# compute_rsi
# =============================================================================
close = FULL["close"].astype(float)
rsi = ci.compute_rsi(close)
check("rsi tipe float", isinstance(rsi, float))
check("rsi 0..100", 0 <= rsi <= 100, f"rsi={rsi}")
# Uptrend kuat → RSI tinggi; downtrend → RSI rendah
rsi_up = ci.compute_rsi(UPTREND["close"].astype(float))
rsi_dn = ci.compute_rsi(DOWNTREND["close"].astype(float))
check("rsi uptrend > downtrend", rsi_up > rsi_dn, f"up={rsi_up} dn={rsi_dn}")

# =============================================================================
# compute_ema
# =============================================================================
ema = ci.compute_ema(close, 12)
check("ema panjang sama", len(ema) == len(close))
check("ema tidak NaN di akhir", pd.notna(ema.iloc[-1]))

# =============================================================================
# compute_macd
# =============================================================================
macd_sig, hist = ci.compute_macd(close)
check("macd label valid", macd_sig in {"bullish cross", "bullish", "bearish cross", "bearish", "netral"}, macd_sig)
check("macd data kurang netral", ci.compute_macd(close.head(5)) == ("netral", 0))

# =============================================================================
# compute_bollinger
# =============================================================================
bb = ci.compute_bollinger(close)
check("bb punya key", "bb_signal" in bb and "bb_pct_b" in bb)
check("bb signal valid", bb["bb_signal"] in {"oversold", "overbought", "netral"}, bb["bb_signal"])
check("bb data kurang default", ci.compute_bollinger(close.head(5)) == {"bb_signal": "netral", "bb_pct_b": 0.5})

# =============================================================================
# compute_supertrend
# =============================================================================
st = ci.compute_supertrend(FULL)
check("supertrend valid", st in {"bullish", "bearish", "netral"}, st)
check("supertrend empty netral", ci.compute_supertrend(EMPTY) == "netral")
check("supertrend tiny netral", ci.compute_supertrend(TINY) == "netral")

# =============================================================================
# compute_volume_analysis
# =============================================================================
vlabel, vratio = ci.compute_volume_analysis(FULL)
check("vol label valid", vlabel in {"spike", "kuat", "normal", "tipis"}, vlabel)
check("vol ratio > 0", vratio > 0)
check("vol empty default", ci.compute_volume_analysis(EMPTY) == ("normal", 1.0))

# =============================================================================
# compute_adx
# =============================================================================
adx = ci.compute_adx(FULL)
check("adx key", "adx" in adx and "trend" in adx)
check("adx trend valid", adx["trend"] in {"bullish_strong", "bullish", "bearish_strong", "bearish", "sideways"}, adx["trend"])
check("adx empty default", ci.compute_adx(EMPTY) == {"adx": 25, "trend": "sideways"})

# =============================================================================
# compute_ml_forecast
# =============================================================================
ml = ci.compute_ml_forecast(FULL)
check("ml key lengkap", {"ml_prob", "ml_label", "ml_conf"} <= set(ml))
check("ml prob 0..100", 0 <= ml["ml_prob"] <= 100, f"prob={ml['ml_prob']}")
check("ml label valid", ml["ml_label"] in {"BULLISH", "BEARISH", "NETRAL", "NO DATA"}, ml["ml_label"])
check("ml conf valid", ml["ml_conf"] in {"tinggi", "sedang", "rendah"}, ml["ml_conf"])
check("ml data kurang NO DATA", ci.compute_ml_forecast(TINY)["ml_label"] == "NO DATA")

# =============================================================================
# compute_backtest
# =============================================================================
bt = ci.compute_backtest(FULL)
check("bt key lengkap", {"bt_wr", "bt_trades", "bt_label"} <= set(bt))
check("bt wr 0..100", 0 <= bt["bt_wr"] <= 100, f"wr={bt['bt_wr']}")
check("bt trades >= 0", bt["bt_trades"] >= 0)
check("bt data kurang default", ci.compute_backtest(TINY)["bt_label"] == "DATA KURANG")

# =============================================================================
# compute_multi_timeframe_confirmation
# =============================================================================
mtf = ci.compute_multi_timeframe_confirmation(FULL)
check("mtf key lengkap", {"mtf_label", "mtf_4h", "mtf_1d", "mtf_score", "mtf_adjustment"} <= set(mtf))
check("mtf adjustment range", -8 <= mtf["mtf_adjustment"] <= 7, f"adj={mtf['mtf_adjustment']}")

# =============================================================================
# Confluence suite
# =============================================================================
ema200 = ci.compute_ema200_trend(FULL)
check("ema200 key", {"ema200_ok", "ema200", "trend_side"} <= set(ema200))
check("ema200 data kurang", ci.compute_ema200_trend(TINY)["trend_side"] == "NO DATA")

va = ci.compute_volume_anomaly(FULL)
check("vol anomaly key", {"volume_ok", "volume_ratio"} <= set(va))
check("vol anomaly bool", isinstance(va["volume_ok"], (bool, np.bool_)))

pin = ci.detect_bullish_pinbar(FULL)
check("pinbar key", {"pinbar_ok", "pinbar_type"} <= set(pin))

dw = ci.compute_dynamic_walls(FULL)
check("dynamic walls key", "dynamic_wall_ok" in dw and "wall_type" in dw)

sr = ci.compute_static_sr(FULL)
check("static sr key", {"sr_ok", "sr_type", "support", "resistance"} <= set(sr))
check("static sr support<=resistance", sr["support"] <= sr["resistance"], f"{sr['support']} {sr['resistance']}")

conf = ci.compute_confluence_signal(FULL)
check("confluence key", {"confluence_passed", "confluence_total", "confluence_label", "allow_entry", "checks"} <= set(conf))
check("confluence total 5", conf["confluence_total"] == 5)
# Invariant penting: passed harus sama dgn jumlah check True
check(
    "confluence passed == sum(checks)",
    conf["confluence_passed"] == sum(1 for v in conf["checks"].values() if v),
    f"passed={conf['confluence_passed']}",
)
check("confluence allow_entry hanya >=4", conf["allow_entry"] == (conf["confluence_passed"] >= 4))
check("confluence empty tidak crash", ci.compute_confluence_signal(EMPTY)["confluence_passed"] == 0)

# =============================================================================
# build_verdict
# =============================================================================
v_action, v_net, v_alloc = ci.build_verdict(78, 55, "bullish", "bullish", adx, ml, bt, "RENDAH", 6_000_000_000)
check("verdict action valid", v_action in {"APPROVE", "APPROVE KECIL", "TUNGGU", "TOLAK"}, v_action)
check("verdict net 0..100", 0 <= v_net <= 100, f"net={v_net}")
check("verdict alloc 0..1", 0 <= v_alloc <= 1, f"alloc={v_alloc}")
# Risk TINGGI selalu TOLAK
vt = ci.build_verdict(90, 55, "bullish", "bullish", adx, ml, bt, "TINGGI", 6_000_000_000)
check("verdict risk TINGGI -> TOLAK", vt[0] == "TOLAK", vt[0])
check("verdict risk TINGGI alloc 0", vt[2] == 0)

# Out-of-sample decay: bt dgn oos jeblok harus lebih bearish dari oos sehat
bt_stale = {"bt_wr": 60, "bt_trades": 20, "bt_label": "TERUJI", "bt_oos_wr": 30}
bt_fresh = {"bt_wr": 60, "bt_trades": 20, "bt_label": "TERUJI", "bt_oos_wr": 62}
_, net_stale, _ = ci.build_verdict(70, 55, "bullish", "bullish", adx, ml, bt_stale, "RENDAH", 6_000_000_000)
_, net_fresh, _ = ci.build_verdict(70, 55, "bullish", "bullish", adx, ml, bt_fresh, "RENDAH", 6_000_000_000)
check("verdict OOS jeblok < OOS sehat", net_stale < net_fresh, f"stale={net_stale} fresh={net_fresh}")
# Kompatibilitas: bt tanpa key oos tetap jalan (pemanggil lama)
bt_legacy = {"bt_wr": 60, "bt_trades": 20, "bt_label": "TERUJI"}
v_legacy = ci.build_verdict(70, 55, "bullish", "bullish", adx, ml, bt_legacy, "RENDAH", 6_000_000_000)
check("verdict kompatibel bt tanpa oos", v_legacy[0] in {"APPROVE", "APPROVE KECIL", "TUNGGU", "TOLAK"})

# =============================================================================
# compute_market_regime (filter kondisi BTC)
# =============================================================================
# Fixture realistis: penurunan bertahap yg tetap di atas lantai harga, supaya
# momentum & EMA mencerminkan downtrend nyata (bukan flatline di clip floor).
def make_regime_candles(direction, n=120, seed=11, start=60_000.0):
    rng = np.random.default_rng(seed)
    drift = {"up": 0.004, "down": -0.004, "flat": 0.0}[direction]
    rets = rng.normal(drift, 0.012, n)
    close = start * np.cumprod(1 + rets)
    close = np.clip(close, 1.0, None)
    high = close * (1 + np.abs(rng.normal(0, 0.004, n)))
    low = close * (1 - np.abs(rng.normal(0, 0.004, n)))
    open_ = close * (1 + rng.normal(0, 0.002, n))
    vol = np.abs(rng.normal(1000, 150, n)) + 1
    times = (pd.Series(range(n)) * 3600 + 1_600_000_000).astype(int)
    return pd.DataFrame(
        {"time": times, "open": open_, "high": high, "low": low, "close": close, "volume": vol}
    )


BTC_UP = make_regime_candles("up", seed=21)
BTC_DOWN = make_regime_candles("down", seed=22)
reg_up = ci.compute_market_regime(BTC_UP)
reg_dn = ci.compute_market_regime(BTC_DOWN)
reg_empty = ci.compute_market_regime(EMPTY)
reg_tiny = ci.compute_market_regime(TINY)
check("regime key lengkap", {"regime", "regime_adjustment", "allow_aggressive", "btc_momentum_pct", "note"} <= set(reg_up))
check("regime uptrend RISK_ON", reg_up["regime"] == "RISK_ON", str(reg_up))
check("regime downtrend RISK_OFF", reg_dn["regime"] == "RISK_OFF", str(reg_dn))
check("regime RISK_OFF tahan agresif", reg_dn["allow_aggressive"] is False)
check("regime RISK_OFF adjustment negatif", reg_dn["regime_adjustment"] < 0)
check("regime RISK_ON adjustment positif", reg_up["regime_adjustment"] > 0)
check("regime empty NO DATA netral", reg_empty["regime"] == "NO DATA" and reg_empty["regime_adjustment"] == 0)
check("regime data kurang tidak menghukum", reg_tiny["regime_adjustment"] == 0)
check("regime adjustment dalam range", -8 <= reg_dn["regime_adjustment"] <= 4)

# =============================================================================
# fetch_candles — kontrak bentuk output (tanpa jaringan: tidak dipanggil live)
# =============================================================================
check("fetch_candles callable", callable(ci.fetch_candles))

# =============================================================================
# Robustness: semua fungsi utama tidak boleh crash di DataFrame kosong
# =============================================================================
no_crash = True
try:
    ci.compute_supertrend(EMPTY)
    ci.compute_volume_analysis(EMPTY)
    ci.compute_adx(EMPTY)
    ci.compute_ml_forecast(EMPTY)
    ci.compute_backtest(EMPTY)
    ci.compute_multi_timeframe_confirmation(EMPTY)
    ci.compute_ema200_trend(EMPTY)
    ci.compute_volume_anomaly(EMPTY)
    ci.detect_bullish_pinbar(EMPTY)
    ci.compute_dynamic_walls(EMPTY)
    ci.compute_static_sr(EMPTY)
    ci.compute_confluence_signal(EMPTY)
except Exception as e:  # noqa: BLE001
    no_crash = False
    print(f"  crash di empty: {e}")
check("semua fungsi aman di DataFrame kosong", no_crash)

print(f"\n=== {passed}/{passed + failed} tests passed ===")
sys.exit(0 if failed == 0 else 1)
