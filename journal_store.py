"""
Journal Store
=============
Backend persisten untuk signal journal dengan dua strategi:

1. **SQLite (default)** — file `signal_journal.db`. Skala lebih baik saat
   journal mencapai ribuan entry. Read/write atomik, indexed, query winrate
   per-symbol jadi instant.
2. **JSON fallback** — file `signal_journal.json`. Otomatis dipakai kalau
   SQLite gagal init (filesystem read-only, dll).

Auto-migrate: jika `signal_journal.json` ada saat first run dan SQLite
masih kosong, isi JSON akan diimpor sekali ke SQLite. Setelah migrasi sukses,
JSON tetap ada sebagai backup tapi tidak ditulis lagi.

API kompatibel 100% dengan kode existing:
    load_journal() -> dict({"version", "signals": [...], "updated_at"})
    save_journal(journal) -> bool

Override storage path lewat env var `SIGNAL_JOURNAL_FILE` (untuk JSON path)
atau `SIGNAL_JOURNAL_DB` (untuk SQLite path).
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from typing import Any

WIB = timezone(timedelta(hours=7))


def _persist_dir() -> str:
    """Direktori penyimpanan yang BERTAHAN antar restart, kalau ada.

    Hugging Face Spaces dgn persistent storage me-mount disk di /data. Tanpa
    ini, filesystem container EPHEMERAL: signal_journal.db hilang tiap rebuild/
    restart -> learning tidak pernah terkumpul, panel selalu kosong.

    Prioritas:
      1. env SIGNAL_JOURNAL_DIR (override manual)
      2. /data (HF persistent storage) — dipakai hanya kalau ada & bisa ditulis
      3. "" (working dir) — perilaku lama, fallback aman
    """
    override = os.environ.get("SIGNAL_JOURNAL_DIR")
    if override:
        try:
            os.makedirs(override, exist_ok=True)
            if os.access(override, os.W_OK):
                return override
        except OSError:
            pass
    hf_data = "/data"
    try:
        if os.path.isdir(hf_data) and os.access(hf_data, os.W_OK):
            return hf_data
    except OSError:
        pass
    return ""


def _resolve(default_name: str, env_value: str | None) -> str:
    """Kalau path eksplisit diberi lewat env, hormati apa adanya. Kalau tidak,
    taruh di direktori persisten bila tersedia (fallback ke working dir)."""
    if env_value:
        return env_value
    base = _persist_dir()
    return os.path.join(base, default_name) if base else default_name


JSON_PATH = _resolve("signal_journal.json", os.environ.get("SIGNAL_JOURNAL_FILE"))
# DB default: turunkan dari JSON_PATH (ganti .json -> .db) supaya keduanya
# satu folder; atau hormati SIGNAL_JOURNAL_DB kalau diset eksplisit.
_db_default = (os.path.splitext(JSON_PATH)[0] + ".db") if JSON_PATH.endswith(".json") else "signal_journal.db"
DB_PATH = os.environ.get("SIGNAL_JOURNAL_DB", _db_default)
ENABLED = str(os.environ.get("ENABLE_SIGNAL_LEARNING", "true")).lower() in {"1", "true", "yes", "on"}
MAX_ENTRIES = int(os.environ.get("SIGNAL_JOURNAL_MAX", "5000"))

# Dipakai bersama bot daemon thread + UI thread. SQLite punya locking sendiri
# tapi kita tetap pegang lock di sisi Python supaya migration & truncate
# operasi konsisten.
_LOCK = threading.RLock()
_BACKEND: str | None = None  # "sqlite" / "json" — diisi saat first init


# Kolom signal yang dipersist. `id` bukan bagian dari payload public.
SIGNAL_COLUMNS = (
    "symbol", "pair", "action", "entry", "score", "allocation_pct",
    "tp1", "tp2", "target", "stop_loss",
    "opened_at", "closed_at",
    "status", "outcome", "tp1_hit",
    "max_price", "min_price",
    "max_gain_pct", "max_drawdown_pct",
    "last_price", "source",
)


def _empty_journal() -> dict:
    return {"version": 1, "signals": [], "updated_at": None}


# =============================================================================
# SQLITE BACKEND
# =============================================================================
def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    return conn


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS journal_meta (
            key TEXT PRIMARY KEY,
            value TEXT
        );
        CREATE TABLE IF NOT EXISTS signals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            pair TEXT,
            action TEXT,
            entry REAL,
            score INTEGER,
            allocation_pct REAL,
            tp1 REAL,
            tp2 REAL,
            target REAL,
            stop_loss REAL,
            opened_at TEXT,
            closed_at TEXT,
            status TEXT,
            outcome TEXT,
            tp1_hit INTEGER DEFAULT 0,
            max_price REAL,
            min_price REAL,
            max_gain_pct REAL,
            max_drawdown_pct REAL,
            last_price REAL,
            source TEXT,
            extra_json TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_signals_symbol ON signals(symbol);
        CREATE INDEX IF NOT EXISTS idx_signals_status ON signals(status);
        CREATE INDEX IF NOT EXISTS idx_signals_opened_at ON signals(opened_at);

        -- Portfolio tracker (manual user positions)
        CREATE TABLE IF NOT EXISTS portfolio_positions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            pair TEXT,
            qty REAL NOT NULL,
            avg_buy_price REAL NOT NULL,
            notes TEXT,
            opened_at TEXT NOT NULL,
            closed_at TEXT,
            status TEXT NOT NULL DEFAULT 'OPEN'
        );
        CREATE INDEX IF NOT EXISTS idx_portfolio_status ON portfolio_positions(status);
        CREATE INDEX IF NOT EXISTS idx_portfolio_symbol ON portfolio_positions(symbol);

        -- Portfolio settings (capital total, risk preference, dll)
        CREATE TABLE IF NOT EXISTS portfolio_settings (
            key TEXT PRIMARY KEY,
            value TEXT
        );
        """
    )
    conn.commit()


def _row_to_signal(row: sqlite3.Row) -> dict:
    sig: dict[str, Any] = {col: row[col] for col in SIGNAL_COLUMNS}
    # Restore typing seperti API JSON lama
    if sig.get("tp1_hit") is not None:
        sig["tp1_hit"] = bool(sig["tp1_hit"])
    sig["_db_id"] = row["id"]
    extra = row["extra_json"]
    if extra:
        try:
            sig.update(json.loads(extra))
        except (TypeError, ValueError):
            pass
    return sig


def _signal_to_params(sig: dict) -> dict:
    params: dict[str, Any] = {col: sig.get(col) for col in SIGNAL_COLUMNS}
    if params.get("tp1_hit") is not None:
        params["tp1_hit"] = 1 if params["tp1_hit"] else 0
    # Apa pun key tambahan di dict (non-standard) disimpan sebagai JSON
    extras = {k: v for k, v in sig.items() if k not in SIGNAL_COLUMNS and not k.startswith("_")}
    params["extra_json"] = json.dumps(extras, ensure_ascii=False) if extras else None
    return params


def _load_sqlite() -> dict:
    with _LOCK:
        try:
            conn = _connect()
            try:
                _ensure_schema(conn)
                rows = conn.execute(
                    "SELECT * FROM signals ORDER BY id ASC"
                ).fetchall()
                meta = {
                    r["key"]: r["value"]
                    for r in conn.execute("SELECT key, value FROM journal_meta").fetchall()
                }
            finally:
                conn.close()
            return {
                "version": int(meta.get("version", 1)),
                "signals": [_row_to_signal(r) for r in rows],
                "updated_at": meta.get("updated_at"),
            }
        except sqlite3.Error:
            return _empty_journal()


def _save_sqlite(journal: dict) -> bool:
    if not ENABLED:
        return False
    signals = journal.get("signals", []) or []
    # Cap MAX_ENTRIES dari yang terbaru — sama persis behaviour JSON lama (slice 500).
    if len(signals) > MAX_ENTRIES:
        signals = signals[-MAX_ENTRIES:]
        journal["signals"] = signals

    with _LOCK:
        try:
            conn = _connect()
            try:
                _ensure_schema(conn)
                conn.execute("BEGIN")

                # Kumpulkan id existing untuk diff delete.
                existing_ids = {
                    r["id"] for r in conn.execute("SELECT id FROM signals").fetchall()
                }
                seen_ids: set[int] = set()

                for sig in signals:
                    params = _signal_to_params(sig)
                    db_id = sig.get("_db_id")
                    if db_id and db_id in existing_ids:
                        cols = ", ".join(f"{c}=:{c}" for c in SIGNAL_COLUMNS) + ", extra_json=:extra_json"
                        conn.execute(
                            f"UPDATE signals SET {cols} WHERE id=:id",
                            {**params, "id": db_id},
                        )
                        seen_ids.add(db_id)
                    else:
                        cols = ", ".join(SIGNAL_COLUMNS) + ", extra_json"
                        placeholders = ", ".join(f":{c}" for c in SIGNAL_COLUMNS) + ", :extra_json"
                        cur = conn.execute(
                            f"INSERT INTO signals ({cols}) VALUES ({placeholders})",
                            params,
                        )
                        new_id = cur.lastrowid
                        sig["_db_id"] = new_id
                        seen_ids.add(new_id)

                # Hapus row yang sudah tidak ada di list (hasil cap MAX_ENTRIES, dll)
                stale = existing_ids - seen_ids
                if stale:
                    conn.executemany(
                        "DELETE FROM signals WHERE id = ?",
                        [(sid,) for sid in stale],
                    )

                # Update meta
                now_iso = datetime.now(WIB).isoformat()
                journal["updated_at"] = now_iso
                conn.executemany(
                    "INSERT INTO journal_meta(key, value) VALUES(?, ?) "
                    "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                    [
                        ("version", str(int(journal.get("version", 1)))),
                        ("updated_at", now_iso),
                    ],
                )

                conn.commit()
            finally:
                conn.close()
            return True
        except sqlite3.Error:
            return False


# =============================================================================
# JSON FALLBACK (kompatibel dengan kode lama)
# =============================================================================
def _load_json() -> dict:
    if not os.path.exists(JSON_PATH):
        return _empty_journal()
    try:
        with open(JSON_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return _empty_journal()
        data.setdefault("version", 1)
        data.setdefault("signals", [])
        data.setdefault("updated_at", None)
        return data
    except (OSError, ValueError, TypeError):
        return _empty_journal()


def _save_json(journal: dict) -> bool:
    if not ENABLED:
        return False
    try:
        journal["signals"] = (journal.get("signals") or [])[-MAX_ENTRIES:]
        journal["updated_at"] = datetime.now(WIB).isoformat()
        tmp_path = f"{JSON_PATH}.tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(journal, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, JSON_PATH)
        return True
    except OSError:
        return False


# =============================================================================
# AUTO-MIGRATION
# =============================================================================
def _migrate_json_to_sqlite() -> None:
    """Sekali jalan: kalau JSON ada & SQLite kosong, import semua signal."""
    if not os.path.exists(JSON_PATH):
        return
    try:
        conn = _connect()
        try:
            _ensure_schema(conn)
            already = conn.execute("SELECT COUNT(*) FROM signals").fetchone()[0]
            if already > 0:
                return
        finally:
            conn.close()
    except sqlite3.Error:
        return

    legacy = _load_json()
    if not legacy.get("signals"):
        return

    # Reset _db_id supaya save_sqlite generate id baru
    for sig in legacy["signals"]:
        sig.pop("_db_id", None)
    if _save_sqlite(legacy):
        # Buat marker JSON sudah dimigrasi (jangan hapus file demi safety/backup)
        try:
            backup_path = JSON_PATH + ".migrated"
            if not os.path.exists(backup_path):
                os.replace(JSON_PATH, backup_path)
        except OSError:
            pass


# =============================================================================
# BACKEND DETECTION
# =============================================================================
def _detect_backend() -> str:
    """Pilih sqlite kalau bisa write ke directory; fallback JSON."""
    global _BACKEND
    if _BACKEND is not None:
        return _BACKEND
    try:
        conn = _connect()
        try:
            _ensure_schema(conn)
        finally:
            conn.close()
        _BACKEND = "sqlite"
        # Lakukan one-time migration kalau perlu
        _migrate_json_to_sqlite()
    except sqlite3.Error:
        _BACKEND = "json"
    return _BACKEND


def get_backend() -> str:
    """Diagnostik: tahu backend mana yang aktif."""
    return _detect_backend()


# =============================================================================
# PUBLIC API (drop-in replacement)
# =============================================================================
def load_journal() -> dict:
    if not ENABLED:
        return _empty_journal()
    backend = _detect_backend()
    if backend == "sqlite":
        return _load_sqlite()
    return _load_json()


def save_journal(journal: dict) -> bool:
    if not ENABLED:
        return False
    backend = _detect_backend()
    if backend == "sqlite":
        return _save_sqlite(journal)
    return _save_json(journal)


def reset_journal() -> bool:
    """Hapus semua entry. Dipakai oleh test_learning.py."""
    with _LOCK:
        ok = True
        if os.path.exists(DB_PATH):
            try:
                os.remove(DB_PATH)
            except OSError:
                ok = False
        for path in (JSON_PATH, JSON_PATH + ".tmp", JSON_PATH + ".migrated"):
            if os.path.exists(path):
                try:
                    os.remove(path)
                except OSError:
                    ok = False
        global _BACKEND
        _BACKEND = None
        return ok


# =============================================================================
# PORTFOLIO TRACKER API
# =============================================================================
PORTFOLIO_COLUMNS = (
    "symbol", "pair", "qty", "avg_buy_price", "notes",
    "opened_at", "closed_at", "status",
)


def _row_to_position(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        **{col: row[col] for col in PORTFOLIO_COLUMNS},
    }


def list_positions(status: str | None = "OPEN") -> list[dict]:
    """List posisi portfolio. status=None untuk ambil semua, default OPEN."""
    if _detect_backend() != "sqlite":
        return []
    with _LOCK:
        try:
            conn = _connect()
            try:
                _ensure_schema(conn)
                if status is None:
                    rows = conn.execute(
                        "SELECT * FROM portfolio_positions ORDER BY opened_at DESC"
                    ).fetchall()
                else:
                    rows = conn.execute(
                        "SELECT * FROM portfolio_positions WHERE status = ? ORDER BY opened_at DESC",
                        (status,),
                    ).fetchall()
                return [_row_to_position(r) for r in rows]
            finally:
                conn.close()
        except sqlite3.Error:
            return []


def add_position(symbol: str, pair: str, qty: float, avg_buy_price: float,
                 notes: str = "", opened_at: str | None = None) -> int | None:
    """Tambah posisi baru. Return id baru, atau None kalau gagal."""
    if _detect_backend() != "sqlite":
        return None
    if not symbol or qty <= 0 or avg_buy_price <= 0:
        return None
    opened_at = opened_at or datetime.now(WIB).isoformat()
    with _LOCK:
        try:
            conn = _connect()
            try:
                _ensure_schema(conn)
                cur = conn.execute(
                    """INSERT INTO portfolio_positions
                       (symbol, pair, qty, avg_buy_price, notes, opened_at, status)
                       VALUES (?, ?, ?, ?, ?, ?, 'OPEN')""",
                    (symbol.upper(), pair, float(qty), float(avg_buy_price), notes, opened_at),
                )
                conn.commit()
                return cur.lastrowid
            finally:
                conn.close()
        except sqlite3.Error:
            return None


def update_position(position_id: int, qty: float | None = None,
                    avg_buy_price: float | None = None, notes: str | None = None) -> bool:
    """Update qty / avg buy / notes posisi existing."""
    if _detect_backend() != "sqlite":
        return False
    fields = []
    params: list[Any] = []
    if qty is not None and qty > 0:
        fields.append("qty = ?")
        params.append(float(qty))
    if avg_buy_price is not None and avg_buy_price > 0:
        fields.append("avg_buy_price = ?")
        params.append(float(avg_buy_price))
    if notes is not None:
        fields.append("notes = ?")
        params.append(notes)
    if not fields:
        return False
    params.append(position_id)
    with _LOCK:
        try:
            conn = _connect()
            try:
                conn.execute(
                    f"UPDATE portfolio_positions SET {', '.join(fields)} "
                    f"WHERE id = ? AND status = 'OPEN'",
                    params,
                )
                conn.commit()
                return True
            finally:
                conn.close()
        except sqlite3.Error:
            return False


def close_position(position_id: int) -> bool:
    """Tutup posisi (mark CLOSED), tidak hapus row supaya jejak history tetap ada."""
    if _detect_backend() != "sqlite":
        return False
    with _LOCK:
        try:
            conn = _connect()
            try:
                conn.execute(
                    "UPDATE portfolio_positions SET status='CLOSED', closed_at=? WHERE id=?",
                    (datetime.now(WIB).isoformat(), position_id),
                )
                conn.commit()
                return True
            finally:
                conn.close()
        except sqlite3.Error:
            return False


def delete_position(position_id: int) -> bool:
    """Hapus permanen — pakai kalau user salah input, bukan untuk close."""
    if _detect_backend() != "sqlite":
        return False
    with _LOCK:
        try:
            conn = _connect()
            try:
                conn.execute("DELETE FROM portfolio_positions WHERE id=?", (position_id,))
                conn.commit()
                return True
            finally:
                conn.close()
        except sqlite3.Error:
            return False


def get_setting(key: str, default: str = "") -> str:
    if _detect_backend() != "sqlite":
        return default
    with _LOCK:
        try:
            conn = _connect()
            try:
                _ensure_schema(conn)
                row = conn.execute(
                    "SELECT value FROM portfolio_settings WHERE key = ?", (key,)
                ).fetchone()
                return row["value"] if row else default
            finally:
                conn.close()
        except sqlite3.Error:
            return default


def set_setting(key: str, value: str) -> bool:
    if _detect_backend() != "sqlite":
        return False
    with _LOCK:
        try:
            conn = _connect()
            try:
                _ensure_schema(conn)
                conn.execute(
                    "INSERT INTO portfolio_settings(key, value) VALUES(?, ?) "
                    "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                    (key, str(value)),
                )
                conn.commit()
                return True
            finally:
                conn.close()
        except sqlite3.Error:
            return False
