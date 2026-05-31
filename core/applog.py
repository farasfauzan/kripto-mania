"""Logging terstruktur terpusat untuk Kripto Mania.

Sebelumnya bot & commands pakai print() polos tanpa level — di Hugging Face
Spaces, log tanpa level (INFO/WARNING/ERROR) sulit dipilah saat ada masalah.
Modul ini memberi format konsisten + level, menulis ke stdout (yang ditangkap
HF Spaces), zona waktu WIB.

Pemakaian:
    from core.applog import get_logger
    log = get_logger("bot")
    log.info("Sinyal terkirim")
    log.warning("Retry fetch")
    log.error("Gagal kirim: %s", err)

Level bisa diatur lewat env LOG_LEVEL (default INFO).
"""
from __future__ import annotations

import logging
import os
import sys
from datetime import datetime, timedelta, timezone

WIB = timezone(timedelta(hours=7))

_CONFIGURED = False


class _WIBFormatter(logging.Formatter):
    """Formatter dgn timestamp WIB (HH:MM:SS) + level singkat."""

    def formatTime(self, record, datefmt=None):  # noqa: N802 (override stdlib)
        dt = datetime.fromtimestamp(record.created, tz=WIB)
        return dt.strftime(datefmt or "%H:%M:%S")


def _configure_root() -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return
    level_name = os.environ.get("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(_WIBFormatter("[%(asctime)s] %(levelname)s %(name)s: %(message)s"))

    root = logging.getLogger("kripto")
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)
    root.propagate = False
    _CONFIGURED = True


def get_logger(name: str = "app") -> logging.Logger:
    """Kembalikan logger child di bawah namespace 'kripto'."""
    _configure_root()
    return logging.getLogger(f"kripto.{name}")
