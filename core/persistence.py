"""Small, dependency-free persistence helpers for safety-critical JSON state."""

from __future__ import annotations

import copy
import json
import os
import tempfile
import time
from contextlib import contextmanager
from typing import Any, Callable

from core.applog import get_logger

logger = get_logger("persistence")

try:
    import fcntl
except ImportError:  # pragma: no cover - exercised only on platforms without fcntl
    fcntl = None


class CorruptJSONError(ValueError):
    """Raised when existing JSON state cannot be trusted."""


def _copy(value):
    return copy.deepcopy(value)


def _positive_float_env(name: str, default: float) -> float:
    try:
        value = float(str(os.environ.get(name, default)).strip())
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default


def _pid_is_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except (PermissionError, OSError):
        return True
    return True


def _remove_stale_fallback_lock(lock_path: str, stale_seconds: float) -> bool:
    try:
        age = time.time() - os.path.getmtime(lock_path)
        if age <= stale_seconds:
            return False
        with open(lock_path, "r") as lock_file:
            owner = json.load(lock_file)
        pid = int(owner.get("pid"))
        created_at = float(owner.get("created_at"))
        if pid <= 0 or created_at <= 0 or _pid_is_alive(pid):
            return False
        os.unlink(lock_path)
        logger.warning(f"Removed stale lock {lock_path} owned by dead pid {pid}")
        return True
    except (FileNotFoundError, TypeError, ValueError, json.JSONDecodeError, OSError):
        return False


@contextmanager
def file_lock(path: str, timeout_seconds: float = 10.0):
    """Lock a sidecar file so read-modify-write operations are serialized."""
    lock_path = f"{path}.lock"
    directory = os.path.dirname(os.path.abspath(lock_path))
    os.makedirs(directory, exist_ok=True)

    if fcntl is not None:
        lock_file = open(lock_path, "a+")
        try:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            yield
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
            lock_file.close()
        return

    timeout_seconds = _positive_float_env("FILE_LOCK_TIMEOUT_SECONDS", timeout_seconds)
    stale_seconds = _positive_float_env("FILE_LOCK_STALE_SECONDS", 300.0)
    deadline = time.monotonic() + timeout_seconds
    lock_fd = None
    while lock_fd is None:
        try:
            lock_fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            try:
                owner = json.dumps({"pid": os.getpid(), "created_at": time.time()}).encode("utf-8")
                os.write(lock_fd, owner)
                os.fsync(lock_fd)
            except Exception:
                os.close(lock_fd)
                lock_fd = None
                try:
                    os.unlink(lock_path)
                except OSError:
                    pass
                raise
        except FileExistsError:
            if _remove_stale_fallback_lock(lock_path, stale_seconds):
                continue
            if time.monotonic() >= deadline:
                raise TimeoutError(f"Timed out acquiring lock for {path}")
            time.sleep(0.05)
    try:
        yield
    finally:
        os.close(lock_fd)
        try:
            os.unlink(lock_path)
        except FileNotFoundError:
            pass


def atomic_write_json(path: str, data: Any) -> bool:
    """Write JSON through a unique temp file, fsync it, then atomically replace."""
    absolute_path = os.path.abspath(path)
    directory = os.path.dirname(absolute_path)
    os.makedirs(directory, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(prefix=f".{os.path.basename(path)}.", suffix=".tmp", dir=directory)
    try:
        with os.fdopen(fd, "w") as tmp_file:
            json.dump(data, tmp_file, indent=2)
            tmp_file.flush()
            os.fsync(tmp_file.fileno())
        os.replace(tmp_path, absolute_path)
        try:
            directory_fd = os.open(directory, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        except OSError:
            pass
        return True
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def read_json_safe(path: str, default: Any, fail_closed_default: Any = None):
    """Read JSON, optionally returning a stricter value when existing data is corrupt."""
    if not os.path.exists(path):
        return _copy(default)
    try:
        with open(path, "r") as source:
            return json.load(source)
    except Exception as exc:
        logger.error(f"Failed to read JSON {path}: {exc}")
        fallback = fail_closed_default if fail_closed_default is not None else default
        return _copy(fallback)


def read_json_strict(path: str, default: Any):
    """Treat a missing file as empty/default, but reject corrupt existing state."""
    if not os.path.exists(path):
        return _copy(default)
    try:
        with open(path, "r") as source:
            return json.load(source)
    except Exception as exc:
        logger.error(f"Corrupt JSON state {path}: {exc}")
        raise CorruptJSONError(f"Corrupt JSON state: {path}") from exc


def locked_json_update(path: str, update_fn: Callable[[Any], Any], default: Any, fail_closed: bool = False):
    """Run one JSON read-modify-write transaction under a sidecar file lock."""
    with file_lock(path):
        current = read_json_strict(path, default) if fail_closed else read_json_safe(path, default)
        updated = update_fn(current)
        if updated is None:
            updated = current
        atomic_write_json(path, updated)
        return updated


def append_jsonl(path: str, record: dict) -> bool:
    """Append one durable JSONL recovery record under a sidecar lock."""
    absolute_path = os.path.abspath(path)
    os.makedirs(os.path.dirname(absolute_path), exist_ok=True)
    with file_lock(path):
        with open(absolute_path, "a") as journal:
            journal.write(json.dumps(record, separators=(",", ":")) + "\n")
            journal.flush()
            os.fsync(journal.fileno())
    return True


def order_recovery_journal_path() -> str:
    override = os.environ.get("ORDER_RECOVERY_JOURNAL_FILE")
    if override:
        return override
    try:
        if os.path.isdir("/data") and os.access("/data", os.W_OK):
            return os.path.join("/data", "order_recovery_journal.jsonl")
    except OSError:
        pass
    return "order_recovery_journal.jsonl"


def append_order_recovery_record(record: dict) -> bool:
    return append_jsonl(order_recovery_journal_path(), record)
