import os
from datetime import datetime, timedelta, timezone

# Storage backend: SQLite (default) atau JSON fallback. API kompatibel
# dengan kode lama: load_journal()/save_journal() tetap return/terima dict.
from journal_store import (
    JSON_PATH as SIGNAL_JOURNAL_FILE,  # noqa: F401  (re-export untuk test_learning.py)
    load_journal,
    save_journal,
)


WIB = timezone(timedelta(hours=7))
SIGNAL_LEARNING_ENABLED = str(os.environ.get("ENABLE_SIGNAL_LEARNING", "true")).lower() in {"1", "true", "yes", "on"}
SIGNAL_LEARNING_TTL_HOURS = int(os.environ.get("SIGNAL_LEARNING_TTL_HOURS", "72"))
SIGNAL_LEARNING_DEDUPE_HOURS = int(os.environ.get("SIGNAL_LEARNING_DEDUPE_HOURS", "6"))


def _parse_iso_datetime(value):
    try:
        dt = datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None
    # Legacy entries may be tz-naive; treat them as WIB so subtraction with
    # the tz-aware "now" doesn't blow up the daemon loop.
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=WIB)
    return dt


def _as_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _item_value(item, *keys, default=None):
    for key in keys:
        if isinstance(item, dict) and key in item:
            return item.get(key)
    return default


def build_profile(journal=None):
    journal = journal or load_journal()
    all_signals = journal.get("signals", [])
    # Pisahkan paper-trade ("andai beli" dari early signal) dari sinyal nyata,
    # supaya learning sinyal sungguhan tidak tercemar eksperimen early.
    signals = [s for s in all_signals if s.get("source") != "early"]
    paper = [s for s in all_signals if s.get("source") == "early"]
    closed = [s for s in signals if s.get("status") in {"TARGET", "TP", "SL", "EXPIRED"}]
    wins = [s for s in closed if s.get("outcome") == "WIN"]
    losses = [s for s in closed if s.get("outcome") == "LOSS"]
    active = [s for s in signals if s.get("status") == "OPEN"]

    by_symbol = {}
    for sig in closed:
        symbol = sig.get("symbol")
        if not symbol:
            continue
        stats = by_symbol.setdefault(symbol, {"closed": 0, "wins": 0, "losses": 0, "max_gain_sum": 0.0})
        stats["closed"] += 1
        stats["wins"] += 1 if sig.get("outcome") == "WIN" else 0
        stats["losses"] += 1 if sig.get("outcome") == "LOSS" else 0
        stats["max_gain_sum"] += _as_float(sig.get("max_gain_pct"))

    for stats in by_symbol.values():
        stats["winrate"] = round(stats["wins"] / stats["closed"] * 100, 1) if stats["closed"] else 0.0
        stats["avg_max_gain"] = round(stats["max_gain_sum"] / stats["closed"], 2) if stats["closed"] else 0.0

    best_symbols = sorted(
        ((sym, stats) for sym, stats in by_symbol.items() if stats["closed"] >= 2),
        key=lambda item: (item[1]["winrate"], item[1]["closed"]),
        reverse=True,
    )[:3]

    # Statistik paper-trade ("andai beli") — terpisah, hanya untuk info.
    paper_closed = [s for s in paper if s.get("status") in {"TARGET", "TP", "SL", "EXPIRED"}]
    paper_wins = [s for s in paper_closed if s.get("outcome") == "WIN"]

    return {
        "enabled": SIGNAL_LEARNING_ENABLED,
        "total_signals": len(signals),
        "closed": len(closed),
        "wins": len(wins),
        "losses": len(losses),
        "active": len(active),
        "winrate": round(len(wins) / len(closed) * 100, 1) if closed else None,
        "by_symbol": by_symbol,
        "best_symbols": best_symbols,
        # Paper-trade ("andai beli") dari early signal
        "paper_active": len([s for s in paper if s.get("status") == "OPEN"]),
        "paper_closed": len(paper_closed),
        "paper_wins": len(paper_wins),
        "paper_winrate": round(len(paper_wins) / len(paper_closed) * 100, 1) if paper_closed else None,
        "updated_at": journal.get("updated_at"),
    }


def calculate_kelly_allocation(winrate_pct, avg_gain_pct, avg_loss_pct, base_alloc=5.0, max_fraction=0.10):
    """
    Menghitung alokasi modal optimal berdasarkan Kelly Criterion.
    winrate_pct: winrate historis (%)
    avg_gain_pct: gain rata-rata koin tersebut (%)
    avg_loss_pct: loss rata-rata koin tersebut (%)
    base_alloc: alokasi dasar jika data kurang (default 5.0%)
    max_fraction: alokasi maksimal per koin (default 10.0%)
    """
    if winrate_pct <= 0 or avg_loss_pct <= 0:
        return base_alloc
    
    p = winrate_pct / 100.0
    b = (avg_gain_pct / avg_loss_pct) if avg_gain_pct > 0 else 1.0
    
    # Kelly formula
    kelly_f = (p * b - (1 - p)) / b
    
    # Amankan dengan fractional Kelly (50% dari Kelly penuh untuk meminimalkan volatilitas saldo)
    fractional_kelly = kelly_f * 0.5
    
    # Konversi ke persentase dan batasi di rentang aman [1.0%, max_fraction * 100]
    allocation = max(1.0, min(max_fraction * 100, fractional_kelly * 100))
    return round(allocation, 1)


def apply_learning_adjustments(items, profile=None):
    profile = profile or build_profile()
    by_symbol = profile.get("by_symbol", {})
    for item in items:
        stats = by_symbol.get(item.get("symbol"), {})
        closed = stats.get("closed", 0)
        adjustment = 0
        note = "Mengumpulkan data"
        
        # Inisialisasi variabel Kelly
        winrate = 0.0
        avg_gain = 3.0
        avg_loss = 3.5
        kelly_f = 0.0
        
        if closed >= 3:
            winrate = stats.get("winrate", 0.0)
            avg_gain = stats.get("avg_max_gain", 3.0)
            p = winrate / 100.0
            b = (avg_gain / avg_loss) if avg_gain > 0 else 1.0
            kelly_f = (p * b - (1 - p)) / b if b > 0 else 0.0
            
            if winrate >= 70:
                adjustment = 5
                note = f"Riwayat kuat ({winrate:.0f}% WR, Kelly: {kelly_f*100:.1f}%)"
            elif winrate >= 58:
                adjustment = 2
                note = f"Riwayat positif ({winrate:.0f}% WR, Kelly: {kelly_f*100:.1f}%)"
            elif winrate <= 38:
                adjustment = -6
                note = f"Riwayat lemah ({winrate:.0f}% WR, Kelly: Batal)"
            elif winrate <= 48:
                adjustment = -3
                note = f"Riwayat hati-hati ({winrate:.0f}% WR, Kelly: Kurangi)"
            else:
                note = f"Riwayat netral ({winrate:.0f}% WR, Kelly: {kelly_f*100:.1f}%)"

        item["learning_adjustment"] = adjustment
        item["learning_note"] = note
        item["learning_trades"] = closed
        
        # Terapkan penyesuaian skor
        if adjustment:
            item["score"] = int(max(0, min(100, int(item.get("score", 0)) + adjustment)))
            
        # Terapkan alokasi menggunakan Kelly Criterion jika data mencukupi
        alloc_key = "allocation_pct" if "allocation_pct" in item else "alloc_pct" if "alloc_pct" in item else None
        if alloc_key and _as_float(item.get(alloc_key)) > 0:
            if closed >= 3:
                kelly_val = calculate_kelly_allocation(winrate, avg_gain, avg_loss, base_alloc=_as_float(item.get(alloc_key)))
                if winrate <= 38:
                    item[alloc_key] = 0.0
                elif winrate <= 48:
                    item[alloc_key] = round(max(0.5, min(3.0, kelly_val)), 1)
                else:
                    item[alloc_key] = kelly_val
            elif adjustment:
                # Fallback ke multiplier lama jika closed < 3 tetapi ada adjustment dari tempat lain
                item[alloc_key] = round(max(0, min(10, _as_float(item[alloc_key]) * (1 + adjustment / 25))), 1)
    return items


def _maybe_collect_paper(sig, collector):
    """Kalau sinyal yg baru ditutup adalah paper-trade (source=early), masukkan
    ke collector supaya pemanggil (bot) bisa kabari hasil "andai beli"-nya."""
    if collector is None or sig.get("source") != "early":
        return
    entry = _as_float(sig.get("entry"))
    last = _as_float(sig.get("last_price"), entry)
    pnl = round((last - entry) / entry * 100, 2) if entry > 0 else 0.0
    collector.append({
        "symbol": sig.get("symbol"),
        "status": sig.get("status"),
        "outcome": sig.get("outcome"),
        "entry": entry,
        "exit": last,
        "pnl_pct": pnl,
        "max_gain_pct": _as_float(sig.get("max_gain_pct")),
    })


def train_from_prices(price_items, now=None, closed_collector=None):
    journal = load_journal()
    if not SIGNAL_LEARNING_ENABLED:
        return build_profile(journal)
    now = now or datetime.now(WIB)
    if isinstance(price_items, dict):
        iterable = price_items.values()
    else:
        iterable = price_items or []
    price_map = {
        item.get("symbol"): _as_float(item.get("price"))
        for item in iterable
        if isinstance(item, dict) and item.get("symbol")
    }
    changed = False

    for sig in journal.get("signals", []):
        if sig.get("status") != "OPEN":
            continue
        symbol = sig.get("symbol")
        price = price_map.get(symbol)
        if not price:
            continue
        entry = _as_float(sig.get("entry"), price)
        sig["last_price"] = price
        
        old_max = _as_float(sig.get("max_price"), entry)
        old_min = _as_float(sig.get("min_price"), entry)
        old_tp1_hit = sig.get("tp1_hit", False)

        new_max = max(old_max, price)
        new_min = min(old_min, price)

        sig["max_price"] = new_max
        sig["min_price"] = new_min
        sig["max_gain_pct"] = round((new_max - entry) / entry * 100, 2) if entry > 0 else 0
        sig["max_drawdown_pct"] = round((new_min - entry) / entry * 100, 2) if entry > 0 else 0

        if new_max != old_max or new_min != old_min:
            changed = True

        opened_at = _parse_iso_datetime(sig.get("opened_at")) or now
        age_hours = (now - opened_at).total_seconds() / 3600
        stop_loss = _as_float(sig.get("stop_loss"))
        tp1 = _as_float(sig.get("tp1"))
        target = _as_float(sig.get("target"))

        # Use running max/min so brief intra-poll spikes/dips that hit
        # TP or SL between polls aren't missed (poll interval is ~3 min).
        if tp1 > 0 and new_max >= tp1 and not old_tp1_hit:
            sig["tp1_hit"] = True
            changed = True

        if target > 0 and new_max >= target:
            sig["status"] = "TARGET"
            sig["outcome"] = "WIN"
            sig["closed_at"] = now.isoformat()
            changed = True
            _maybe_collect_paper(sig, closed_collector)
        elif stop_loss > 0 and new_min <= stop_loss:
            sig["status"] = "SL"
            sig["outcome"] = "WIN" if sig.get("tp1_hit") else "LOSS"
            sig["closed_at"] = now.isoformat()
            changed = True
            _maybe_collect_paper(sig, closed_collector)
        elif age_hours >= SIGNAL_LEARNING_TTL_HOURS:
            sig["status"] = "TP" if sig.get("tp1_hit") else "EXPIRED"
            sig["outcome"] = "WIN" if sig.get("tp1_hit") else "LOSS"
            sig["closed_at"] = now.isoformat()
            changed = True
            _maybe_collect_paper(sig, closed_collector)

    if changed:
        save_journal(journal)
    return build_profile(journal)


def record_signal(item, is_entry_action, now=None):
    if not SIGNAL_LEARNING_ENABLED or not is_entry_action(item.get("action", "")):
        return build_profile()
    allocation = _as_float(_item_value(item, "allocation_pct", "alloc_pct", default=0))
    confluence_passed = int(_item_value(item, "confluence_passed", default=0) or 0)
    if allocation <= 0 or confluence_passed < 4:
        return build_profile()

    journal = load_journal()
    now = now or datetime.now(WIB)
    symbol = item.get("symbol")
    if not symbol:
        return build_profile(journal)
    if any(s.get("symbol") == symbol and s.get("status") == "OPEN" for s in journal.get("signals", [])):
        return build_profile(journal)

    last_same = next((s for s in reversed(journal.get("signals", [])) if s.get("symbol") == symbol), None)
    if last_same:
        opened_at = _parse_iso_datetime(last_same.get("opened_at"))
        if opened_at and (now - opened_at).total_seconds() < SIGNAL_LEARNING_DEDUPE_HOURS * 3600:
            return build_profile(journal)

    price = _as_float(_item_value(item, "price", "entry", default=0))
    target = _as_float(_item_value(item, "target", "tp3", default=0))
    # Simpan probabilitas ramalan SAAT sinyal dibuat, supaya nanti bisa
    # dibandingkan dengan hasil aktual (kalibrasi). Prioritas: ramalan 6 jam
    # (step1), fallback ke probabilitas ML/KNN. Tanpa ini, kalibrasi tidak
    # punya data untuk menilai kejujuran ramalan.
    forecast_prob = _as_float(
        _item_value(item, "forecast_step1_prob", "ml_prob", default=0)
    )
    journal["signals"].append({
        "symbol": symbol,
        "pair": item.get("pair"),
        "action": item.get("action"),
        "entry": price,
        "score": int(_as_float(item.get("score"))),
        "allocation_pct": allocation,
        "tp1": _as_float(item.get("tp1")),
        "tp2": _as_float(item.get("tp2")),
        "target": target,
        "stop_loss": _as_float(_item_value(item, "stop_loss", "sl", default=0)),
        "opened_at": now.isoformat(),
        "status": "OPEN",
        "outcome": None,
        "tp1_hit": False,
        "max_price": price,
        "min_price": price,
        "max_gain_pct": 0.0,
        "max_drawdown_pct": 0.0,
        "forecast_prob": round(forecast_prob, 1) if forecast_prob > 0 else None,
        "source": item.get("source", "bot"),
        # Binance global sentiment saat sinyal dibuat (untuk korelasi training)
        "binance_signal": item.get("binance_signal"),
        "binance_adjustment": int(_as_float(item.get("binance_adjustment"))),
    })
    save_journal(journal)
    return build_profile(journal)


def record_paper_signal(item, now=None):
    """Catat sinyal EARLY sebagai paper-trade ("andai beli"), source="early".

    Berbeda dari record_signal: TIDAK menuntut confluence>=4 / alokasi>0,
    karena early signal memang sinyal dini sebelum konfirmasi penuh. Tujuannya
    melacak "seandainya beli koin ini, kena TP atau SL?" tanpa uang asli, dan
    TERPISAH dari learning sinyal nyata (build_profile mengecualikan source=early).
    """
    if not SIGNAL_LEARNING_ENABLED:
        return None
    journal = load_journal()
    now = now or datetime.now(WIB)
    symbol = item.get("symbol")
    if not symbol:
        return None

    # Jangan dobel: skip kalau sudah ada paper-trade OPEN utk simbol ini.
    if any(
        s.get("symbol") == symbol and s.get("source") == "early" and s.get("status") == "OPEN"
        for s in journal.get("signals", [])
    ):
        return None

    # Dedupe waktu: jangan catat paper-trade simbol sama terlalu rapat.
    last_same = next(
        (s for s in reversed(journal.get("signals", []))
         if s.get("symbol") == symbol and s.get("source") == "early"),
        None,
    )
    if last_same:
        opened_at = _parse_iso_datetime(last_same.get("opened_at"))
        if opened_at and (now - opened_at).total_seconds() < SIGNAL_LEARNING_DEDUPE_HOURS * 3600:
            return None

    price = _as_float(_item_value(item, "price", "entry", default=0))
    if price <= 0:
        return None
    journal["signals"].append({
        "symbol": symbol,
        "pair": item.get("pair"),
        "action": item.get("action", "EARLY"),
        "entry": price,
        "score": int(_as_float(item.get("score"))),
        "allocation_pct": 0.0,
        "tp1": _as_float(item.get("tp1")),
        "tp2": _as_float(item.get("tp2")),
        "target": _as_float(_item_value(item, "target", "tp3", default=0)),
        "stop_loss": _as_float(_item_value(item, "stop_loss", "sl", default=0)),
        "opened_at": now.isoformat(),
        "status": "OPEN",
        "outcome": None,
        "tp1_hit": False,
        "max_price": price,
        "min_price": price,
        "max_gain_pct": 0.0,
        "max_drawdown_pct": 0.0,
        "forecast_prob": _as_float(_item_value(item, "forecast_step1_prob", "ml_prob", default=0)) or None,
        "source": "early",
    })
    save_journal(journal)
    return build_profile(journal)
