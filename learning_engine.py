import json
import os
from datetime import datetime, timedelta, timezone


WIB = timezone(timedelta(hours=7))
SIGNAL_JOURNAL_FILE = os.environ.get("SIGNAL_JOURNAL_FILE", "signal_journal.json")
SIGNAL_LEARNING_ENABLED = str(os.environ.get("ENABLE_SIGNAL_LEARNING", "true")).lower() in {"1", "true", "yes", "on"}
SIGNAL_LEARNING_TTL_HOURS = int(os.environ.get("SIGNAL_LEARNING_TTL_HOURS", "72"))
SIGNAL_LEARNING_DEDUPE_HOURS = int(os.environ.get("SIGNAL_LEARNING_DEDUPE_HOURS", "6"))


def _empty_journal():
    return {"version": 1, "signals": [], "updated_at": None}


def load_journal():
    if not SIGNAL_LEARNING_ENABLED or not os.path.exists(SIGNAL_JOURNAL_FILE):
        return _empty_journal()
    try:
        with open(SIGNAL_JOURNAL_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return _empty_journal()
        data.setdefault("version", 1)
        data.setdefault("signals", [])
        data.setdefault("updated_at", None)
        return data
    except (OSError, ValueError, TypeError):
        return _empty_journal()


def save_journal(journal):
    if not SIGNAL_LEARNING_ENABLED:
        return False
    try:
        journal["signals"] = journal.get("signals", [])[-500:]
        journal["updated_at"] = datetime.now(WIB).isoformat()
        tmp_path = f"{SIGNAL_JOURNAL_FILE}.tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(journal, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, SIGNAL_JOURNAL_FILE)
        return True
    except OSError:
        return False


def _parse_iso_datetime(value):
    try:
        return datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


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
    signals = journal.get("signals", [])
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
        "updated_at": journal.get("updated_at"),
    }


def apply_learning_adjustments(items, profile=None):
    profile = profile or build_profile()
    by_symbol = profile.get("by_symbol", {})
    for item in items:
        stats = by_symbol.get(item.get("symbol"), {})
        closed = stats.get("closed", 0)
        adjustment = 0
        note = "Mengumpulkan data"
        if closed >= 3:
            winrate = stats.get("winrate", 0)
            if winrate >= 70:
                adjustment = 5
                note = f"Riwayat kuat ({winrate:.0f}% WR)"
            elif winrate >= 58:
                adjustment = 2
                note = f"Riwayat positif ({winrate:.0f}% WR)"
            elif winrate <= 38:
                adjustment = -6
                note = f"Riwayat lemah ({winrate:.0f}% WR)"
            elif winrate <= 48:
                adjustment = -3
                note = f"Riwayat hati-hati ({winrate:.0f}% WR)"
            else:
                note = f"Riwayat netral ({winrate:.0f}% WR)"

        item["learning_adjustment"] = adjustment
        item["learning_note"] = note
        item["learning_trades"] = closed
        if adjustment:
            item["score"] = int(max(0, min(100, int(item.get("score", 0)) + adjustment)))
            alloc_key = "allocation_pct" if "allocation_pct" in item else "alloc_pct" if "alloc_pct" in item else None
            if alloc_key and _as_float(item.get(alloc_key)) > 0:
                item[alloc_key] = round(max(0, min(10, _as_float(item[alloc_key]) * (1 + adjustment / 25))), 1)
    return items


def train_from_prices(price_items, now=None):
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

        if tp1 > 0 and price >= tp1 and not old_tp1_hit:
            sig["tp1_hit"] = True
            changed = True
            
        if target > 0 and price >= target:
            sig["status"] = "TARGET"
            sig["outcome"] = "WIN"
            sig["closed_at"] = now.isoformat()
            changed = True
        elif stop_loss > 0 and price <= stop_loss:
            sig["status"] = "SL"
            sig["outcome"] = "WIN" if sig.get("tp1_hit") else "LOSS"
            sig["closed_at"] = now.isoformat()
            changed = True
        elif age_hours >= SIGNAL_LEARNING_TTL_HOURS:
            sig["status"] = "TP" if sig.get("tp1_hit") else "EXPIRED"
            sig["outcome"] = "WIN" if sig.get("tp1_hit") else "LOSS"
            sig["closed_at"] = now.isoformat()
            changed = True

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
        "source": item.get("source", "bot"),
    })
    save_journal(journal)
    return build_profile(journal)
