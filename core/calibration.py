"""Kalibrasi probabilitas — mengukur kejujuran ramalan.

Pertanyaan inti: saat model bilang "70% naik", apakah dari semua sinyal
berlabel ~70% itu benar-benar ~70% yang naik? Kalau tidak, angkanya bohong.

Modul ini TIDAK memprediksi apa pun. Ia hanya mengevaluasi seberapa
terkalibrasi prediksi yang sudah dibuat terhadap hasil aktual.

Metrik:
  - Reliability buckets: kelompokkan prediksi ke bin (0-10%, 10-20%, ...),
    bandingkan rata-rata prediksi vs frekuensi aktual naik per bin.
  - Brier score: rata-rata (prediksi - hasil)^2. 0 = sempurna, 0.25 = setara
    nebak 50% terus, makin kecil makin baik.
  - ECE (Expected Calibration Error): rata-rata |prediksi - aktual| tertimbang
    jumlah sampel per bin. 0 = terkalibrasi sempurna.
"""
from __future__ import annotations


def _to_unit(prob) -> float:
    """Terima probabilitas dalam 0..1 atau 0..100, kembalikan 0..1."""
    p = float(prob)
    if p > 1.0:
        p = p / 100.0
    if p < 0.0:
        return 0.0
    if p > 1.0:
        return 1.0
    return p


def brier_score(pairs) -> float | None:
    """pairs: iterable of (predicted_prob, actual_outcome_bool/0-1).

    Mengembalikan Brier score 0..1 (makin kecil makin baik) atau None bila kosong.
    """
    items = list(pairs)
    if not items:
        return None
    total = 0.0
    for prob, outcome in items:
        p = _to_unit(prob)
        y = 1.0 if (outcome is True or outcome == 1 or outcome == "WIN") else 0.0
        total += (p - y) ** 2
    return round(total / len(items), 4)


def reliability_buckets(pairs, n_bins=10):
    """Bagi prediksi ke n_bins, hitung prediksi rata-rata vs frekuensi aktual.

    Mengembalikan list dict per-bin yang punya sampel:
      {bin_low, bin_high, count, avg_predicted, actual_freq, gap}
    """
    items = []
    for prob, outcome in pairs:
        p = _to_unit(prob)
        y = 1.0 if (outcome is True or outcome == 1 or outcome == "WIN") else 0.0
        items.append((p, y))
    if not items:
        return []

    width = 1.0 / n_bins
    buckets = []
    for b in range(n_bins):
        lo = b * width
        hi = (b + 1) * width
        # bin terakhir inklusif di 1.0
        if b == n_bins - 1:
            members = [it for it in items if lo <= it[0] <= hi]
        else:
            members = [it for it in items if lo <= it[0] < hi]
        if not members:
            continue
        count = len(members)
        avg_pred = sum(p for p, _ in members) / count
        actual = sum(y for _, y in members) / count
        buckets.append({
            "bin_low": round(lo, 2),
            "bin_high": round(hi, 2),
            "count": count,
            "avg_predicted": round(avg_pred * 100, 1),
            "actual_freq": round(actual * 100, 1),
            "gap": round((avg_pred - actual) * 100, 1),
        })
    return buckets


def expected_calibration_error(pairs, n_bins=10) -> float | None:
    """ECE: rata-rata |avg_predicted - actual_freq| tertimbang count. 0..1."""
    buckets = reliability_buckets(pairs, n_bins=n_bins)
    if not buckets:
        return None
    total = sum(b["count"] for b in buckets)
    if total == 0:
        return None
    ece = sum(b["count"] * abs(b["avg_predicted"] - b["actual_freq"]) / 100.0 for b in buckets)
    return round(ece / total, 4)


def calibration_grade(brier, ece, sample_count) -> dict:
    """Terjemahkan metrik jadi label yang bisa dibaca manusia + tingkat kepercayaan."""
    if not sample_count or sample_count < 20:
        return {
            "grade": "DATA KURANG",
            "confidence": "rendah",
            "note": f"Butuh >=20 sinyal tertutup untuk menilai kalibrasi (baru {sample_count or 0}).",
        }
    if brier is None or ece is None:
        return {"grade": "DATA KURANG", "confidence": "rendah", "note": "Belum cukup data."}

    if ece <= 0.05 and brier <= 0.20:
        grade, conf = "TERKALIBRASI BAIK", "tinggi"
        note = "Probabilitas ramalan dekat dengan hasil nyata. Angka bisa dipercaya."
    elif ece <= 0.12 and brier <= 0.24:
        grade, conf = "CUKUP", "sedang"
        note = "Ramalan agak meleset dari hasil nyata. Pakai sebagai panduan, bukan kepastian."
    else:
        grade, conf = "BELUM TERKALIBRASI", "rendah"
        note = "Probabilitas ramalan jauh dari hasil nyata. Jangan andalkan angka persen-nya."
    return {"grade": grade, "confidence": conf, "note": note}


def build_calibration_report(pairs, n_bins=10) -> dict:
    """Laporan lengkap dari list (predicted_prob, outcome)."""
    items = list(pairs)
    n = len(items)
    brier = brier_score(items)
    ece = expected_calibration_error(items, n_bins=n_bins)
    buckets = reliability_buckets(items, n_bins=n_bins)
    grade = calibration_grade(brier, ece, n)
    return {
        "sample_count": n,
        "brier_score": brier,
        "ece": ece,
        "buckets": buckets,
        **grade,
    }


def extract_pairs_from_journal(journal, prob_keys=("forecast_prob", "ml_prob", "forecast_step1_prob")):
    """Ambil (predicted_prob, outcome) dari sinyal tertutup di journal.

    Mencari probabilitas yang tersimpan saat sinyal dibuat (urutan prob_keys).
    Hanya sinyal dengan status tertutup & outcome WIN/LOSS yang dihitung.
    Mengembalikan list pasangan; kosong bila belum ada data yang memadai.
    """
    pairs = []
    closed_status = {"TARGET", "TP", "SL", "EXPIRED"}
    for sig in journal.get("signals", []):
        if sig.get("status") not in closed_status:
            continue
        outcome = sig.get("outcome")
        if outcome not in {"WIN", "LOSS"}:
            continue
        prob = None
        for key in prob_keys:
            val = sig.get(key)
            if val is not None:
                try:
                    prob = float(val)
                    break
                except (TypeError, ValueError):
                    continue
        if prob is None:
            continue
        pairs.append((prob, 1 if outcome == "WIN" else 0))
    return pairs
