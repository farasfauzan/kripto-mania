"""Test paper-trade ("andai beli") dari early signal.

Jalankan: python3 test_paper.py
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(__file__))

_d = tempfile.mkdtemp(prefix="test_paper_")
os.environ["SIGNAL_JOURNAL_FILE"] = os.path.join(_d, "j.json")
os.environ["SIGNAL_JOURNAL_DB"] = os.path.join(_d, "j.db")

import journal_store  # noqa: E402

journal_store.reset_journal()

import learning_engine as le  # noqa: E402

le.SIGNAL_LEARNING_DEDUPE_HOURS = 0
le.SIGNAL_LEARNING_TTL_HOURS = 72

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


def _entry(a):
    return True


# =============================================================================
# record_paper_signal
# =============================================================================
prof = le.record_paper_signal({
    "symbol": "SOLUSDT", "pair": "sol_idr", "price": 100.0,
    "score": 60, "tp1": 101.8, "tp2": 103.5, "target": 103.5, "stop_loss": 97.5,
    "forecast_step1_prob": 64,
})
check("paper tercatat -> paper_active=1", prof["paper_active"] == 1, str(prof))
check("paper tidak masuk learning nyata (active=0)", prof["active"] == 0, str(prof))
check("paper tidak masuk total_signals nyata", prof["total_signals"] == 0, str(prof))

# Dobel di simbol sama saat masih OPEN -> ditolak
prof2 = le.record_paper_signal({
    "symbol": "SOLUSDT", "pair": "sol_idr", "price": 100.0,
    "tp1": 101.8, "target": 103.5, "stop_loss": 97.5,
})
check("paper dobel ditolak", prof2 is None or prof2["paper_active"] == 1)

# =============================================================================
# Penutupan WIN via train_from_prices + collector
# =============================================================================
collector = []
prof3 = le.train_from_prices([{"symbol": "SOLUSDT", "price": 104.0}], closed_collector=collector)
check("paper ditutup -> collector terisi", len(collector) == 1, str(collector))
if collector:
    c = collector[0]
    check("collector outcome WIN", c["outcome"] == "WIN", str(c))
    check("collector pnl positif", c["pnl_pct"] > 0, str(c))
    check("collector simbol benar", c["symbol"] == "SOLUSDT")
check("paper_closed=1 setelah tutup", prof3["paper_closed"] == 1, str(prof3))
check("paper_winrate 100 (1 win)", prof3["paper_winrate"] == 100.0, str(prof3))
check("learning nyata tetap 0 closed", prof3["closed"] == 0, str(prof3))

# =============================================================================
# Penutupan LOSS (SL)
# =============================================================================
journal_store.reset_journal()
le.record_paper_signal({
    "symbol": "PEPEUSDT", "pair": "pepe_idr", "price": 100.0,
    "tp1": 101.8, "target": 103.5, "stop_loss": 97.5,
})
collector2 = []
prof4 = le.train_from_prices([{"symbol": "PEPEUSDT", "price": 97.0}], closed_collector=collector2)
check("paper SL -> collector LOSS", len(collector2) == 1 and collector2[0]["outcome"] == "LOSS", str(collector2))
check("paper SL pnl negatif", collector2 and collector2[0]["pnl_pct"] < 0, str(collector2))
check("paper_winrate 0 (1 loss)", prof4["paper_winrate"] == 0.0, str(prof4))

# =============================================================================
# Real signal vs paper terpisah
# =============================================================================
journal_store.reset_journal()
# Real signal (lolos gate)
le.record_signal({
    "symbol": "BTCUSDT", "action": "BELI KUAT", "score": 85, "allocation_pct": 8,
    "confluence_passed": 5, "price": 50000, "tp1": 51000, "target": 52000, "stop_loss": 49000,
}, _entry)
# Paper signal
le.record_paper_signal({
    "symbol": "ETHUSDT", "pair": "eth_idr", "price": 3000,
    "tp1": 3050, "target": 3100, "stop_loss": 2950,
})
prof5 = le.build_profile()
check("real active=1 (BTC)", prof5["active"] == 1, str(prof5))
check("paper_active=1 (ETH)", prof5["paper_active"] == 1, str(prof5))
check("real total tidak hitung paper", prof5["total_signals"] == 1, str(prof5))

journal_store.reset_journal()

# collector None tidak crash (kompatibilitas pemanggil lama)
le.record_paper_signal({"symbol": "ADAUSDT", "pair": "ada_idr", "price": 1.0,
                        "tp1": 1.02, "target": 1.05, "stop_loss": 0.97})
prof6 = le.train_from_prices([{"symbol": "ADAUSDT", "price": 1.06}])
check("train_from_prices tanpa collector tetap jalan", prof6["paper_closed"] == 1, str(prof6))
journal_store.reset_journal()

print(f"\n=== {passed}/{passed + failed} tests passed ===")
sys.exit(0 if failed == 0 else 1)
