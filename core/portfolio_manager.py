import os
import math
import uuid
from copy import deepcopy
from datetime import datetime, timezone
from core.applog import get_logger
from core.execution_engine import execute_sell
from core.persistence import (
    append_order_recovery_record,
    locked_json_update,
    read_json_safe,
)

logger = get_logger("portfolio_manager")

PORTFOLIO_FILE = "active_trades.json"
MAX_ACTIVE_TRADES = int(os.environ.get("MAX_ACTIVE_TRADES", "5"))


def active_trade_count() -> int:
    """Hitung jumlah posisi terbuka (status = OPEN)."""
    data = _load_portfolio()
    if not isinstance(data, dict):
        return 0
    count = 0
    for sym, pos in data.items():
        if (
            isinstance(pos, dict)
            and str(pos.get("status", "")).strip().upper() == "OPEN"
        ):
            count += 1
    return count


def can_open_new_trade() -> bool:
    """True kalo masih bisa buka posisi baru (belum reach max)."""
    return active_trade_count() < MAX_ACTIVE_TRADES


def _normalize_mode(mode) -> str:
    return "real" if str(mode or "").strip().lower() == "real" else "paper"


def _current_price_value(current_prices: dict, symbol: str):
    for key in (symbol, symbol.upper(), symbol.lower()):
        if key in current_prices:
            value = current_prices[key]
            if isinstance(value, dict):
                return True, value.get("price")
            return True, value
    return False, None


def _positive_float(value, label: str, symbol: str):
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        logger.error(
            f"Invalid {label} for {symbol.upper()}: {value!r}. Auto-sell skipped."
        )
        return None
    if parsed <= 0:
        logger.error(
            f"Invalid {label} for {symbol.upper()}: {parsed}. Auto-sell skipped."
        )
        return None
    return parsed


def _load_portfolio() -> dict:
    data = read_json_safe(PORTFOLIO_FILE, {})
    return data if isinstance(data, dict) else {}


def _save_portfolio(data: dict) -> bool:
    try:
        locked_json_update(PORTFOLIO_FILE, lambda _current: data, {})
        return True
    except Exception as e:
        logger.error(f"Failed to save portfolio: {e}")
        return False


def record_order_recovery(
    symbol: str,
    action: str,
    amount,
    price,
    result: dict,
    reason: str,
    save_error: str,
) -> bool:
    record = {
        "symbol": str(symbol or "").strip().lower(),
        "action": str(action or "").strip().lower(),
        "amount": amount,
        "price": price,
        "received_coin": (result or {}).get("received_coin"),
        "received_idr": (result or {}).get("received_idr"),
        "order_id": (result or {}).get("order_id"),
        "timestamp": datetime.now().isoformat(),
        "reason": reason,
        "mode": "real",
        "error": save_error,
    }
    try:
        return append_order_recovery_record(record)
    except Exception as e:
        logger.error(
            f"CRITICAL: Failed to write order recovery journal for {symbol.upper()}: {e}"
        )
        return False


def save_position(
    symbol: str,
    buy_price: float,
    amount_coin: float,
    tp1: float,
    tp2: float,
    sl: float,
    trade_type: str = "EARLY",
    mode: str = "paper",
    entry_features: dict = None,
) -> bool:
    """Mencatat posisi baru yang baru saja dibeli.

    Args:
        symbol: 'btc', 'doge' dll.
        buy_price: Harga beli rata-rata.
        amount_coin: Jumlah koin yang dipegang.
        tp1, tp2, sl: Target profit dan stop loss.
        trade_type: "EARLY" atau "KUAT"
        mode: "paper" atau "real". Default aman: "paper".
        entry_features: Fitur ML saat entry.
    """
    mode = _normalize_mode(mode)
    final = {}

    def update(portfolio):
        nonlocal mode, buy_price, amount_coin
        portfolio = portfolio if isinstance(portfolio, dict) else {}
        if symbol in portfolio:
            old = portfolio[symbol]
            if str(old.get("status", "OPEN")).strip().upper() != "OPEN":
                raise ValueError(f"Position {symbol.upper()} is not OPEN")
            old_mode = _normalize_mode(old.get("mode", "paper"))
            if old_mode != mode:
                logger.warning(
                    f"Mixed position mode for {symbol.upper()} ({old_mode} + {mode}); forcing PAPER for safety."
                )
                mode = "paper"
            total_coin = old["amount_coin"] + amount_coin
            avg_price = (
                (old["buy_price"] * old["amount_coin"]) + (buy_price * amount_coin)
            ) / total_coin
            logger.info(
                f"Adding position to {symbol.upper()}. New Avg: {avg_price:.0f}, Total Coin: {total_coin}"
            )
            amount_coin = total_coin
            buy_price = avg_price
        portfolio[symbol] = {
            "buy_price": buy_price,
            "amount_coin": amount_coin,
            "tp1": tp1,
            "tp2": tp2,
            "sl": sl,
            "trade_type": trade_type,
            "timestamp": datetime.now().isoformat(),
            "highest_price": buy_price,
            "mode": mode,
            "status": "OPEN",
            "entry_features": entry_features,
        }
        final.update(portfolio[symbol])
        return portfolio

    try:
        locked_json_update(PORTFOLIO_FILE, update, {})
    except Exception as e:
        logger.error(f"Failed to save position {symbol.upper()}: {e}")
        return False
    logger.info(
        f"Posisi disimpan: {symbol.upper()} | Mode: {final['mode'].upper()} | Beli: {final['buy_price']:,.0f} | SL: {sl:,.0f} | TP1: {tp1:,.0f}"
    )
    return True


def remove_position(symbol: str) -> bool:
    """Menghapus posisi dari catatan (setelah dijual)."""
    removed = False

    def update(portfolio):
        nonlocal removed
        portfolio = portfolio if isinstance(portfolio, dict) else {}
        if symbol in portfolio:
            del portfolio[symbol]
            removed = True
        return portfolio

    try:
        locked_json_update(PORTFOLIO_FILE, update, {})
    except Exception as e:
        logger.error(f"Failed to remove position {symbol.upper()}: {e}")
        return False
    if removed:
        logger.info(f"Posisi {symbol.upper()} dihapus dari portofolio.")
    return removed


def update_position_after_sell(
    symbol: str,
    sold_amount: float,
    sell_all: bool = False,
    dust_threshold: float = 0.000000000001,
    portfolio: dict = None,
) -> bool:
    """Persist a confirmed sell and only mutate caller state after a successful write."""
    source = portfolio if isinstance(portfolio, dict) else None
    updated_snapshot = {}

    def update(current):
        current = current if isinstance(current, dict) else {}
        current_positions = (
            current.get("positions")
            if isinstance(current.get("positions"), dict)
            else current
        )
        if isinstance(current_positions, dict) and symbol in current_positions:
            target = current
        elif not current and source is not None:
            target = deepcopy(source)
        else:
            target = current
        positions = (
            target.get("positions")
            if isinstance(target.get("positions"), dict)
            else target
        )
        position = positions.get(symbol) if isinstance(positions, dict) else None
        if not isinstance(position, dict):
            raise ValueError(f"No tracked position for {symbol.upper()}")
        if str(position.get("status", "OPEN")).strip().upper() not in {
            "OPEN",
            "SELLING",
        }:
            raise ValueError(f"Position {symbol.upper()} is not sellable")
        held = float(position.get("amount_coin", 0))
        amount = float(sold_amount)
        if amount <= 0 or amount > held:
            raise ValueError(f"Invalid sold amount for {symbol.upper()}")
        remaining = held - amount
        if sell_all or remaining <= dust_threshold:
            del positions[symbol]
        else:
            position["amount_coin"] = remaining
            position["status"] = "OPEN"
        updated_snapshot.update(deepcopy(target))
        return target

    try:
        locked_json_update(PORTFOLIO_FILE, update, {})
    except Exception as e:
        logger.error(f"Failed to update position after sell {symbol.upper()}: {e}")
        return False
    if source is not None:
        source.clear()
        source.update(updated_snapshot)
    return True


def claim_position_for_sell(
    symbol: str,
    reason: str,
    price: float,
    actor: str = "auto_tp_sl",
    amount=None,
) -> dict:
    """Atomically claim an OPEN position before any sell execution."""
    clean_symbol = str(symbol or "").strip().lower()
    attempt_id = uuid.uuid4().hex
    claimed = None
    denied_reason = "Position is not OPEN"
    requested_amount = None
    if amount is not None:
        requested_amount = _positive_float(amount, "sell amount", clean_symbol)
        if requested_amount is None:
            return {"allowed": False, "reason": "Invalid sell amount"}

    def update(portfolio):
        nonlocal claimed, denied_reason
        portfolio = portfolio if isinstance(portfolio, dict) else {}
        positions = (
            portfolio.get("positions")
            if isinstance(portfolio.get("positions"), dict)
            else portfolio
        )
        position = positions.get(clean_symbol) if isinstance(positions, dict) else None
        if not isinstance(position, dict):
            denied_reason = "Position not found"
            return portfolio
        status = str(position.get("status", "OPEN")).strip().upper()
        if status != "OPEN":
            denied_reason = f"Position status is {status}"
            return portfolio
        held_amount = _positive_float(
            position.get("amount_coin"), "position amount", clean_symbol
        )
        if held_amount is None:
            denied_reason = "Position has invalid amount"
            return portfolio
        claimed_amount = held_amount if requested_amount is None else requested_amount
        if claimed_amount > held_amount:
            denied_reason = "Sell amount exceeds position amount"
            return portfolio
        position.update(
            {
                "status": "SELLING",
                "selling_reason": reason,
                "selling_price": price,
                "selling_amount": claimed_amount,
                "selling_mode": _normalize_mode(position.get("mode", "paper")),
                "selling_actor": actor,
                "selling_started_at": datetime.now(timezone.utc).isoformat(),
                "sell_attempt_id": attempt_id,
            }
        )
        claimed = deepcopy(position)
        return portfolio

    try:
        locked_json_update(PORTFOLIO_FILE, update, {}, fail_closed=True)
    except Exception as e:
        logger.error(f"Failed to claim position {clean_symbol.upper()} for sell: {e}")
        return {"allowed": False, "reason": f"Position claim persistence failed: {e}"}
    if claimed is None:
        return {"allowed": False, "reason": denied_reason}
    return {
        "allowed": True,
        "reason": "Position claimed for sell",
        "symbol": clean_symbol,
        "sell_attempt_id": attempt_id,
        "position": claimed,
    }


def consume_sell_attempt_for_submit(
    symbol,
    sell_attempt_id,
    expected_amount=None,
    expected_price=None,
    expected_mode=None,
    actor=None,
) -> dict:
    """Atomically consume one SELLING claim immediately before a real API submit."""
    clean_symbol = str(symbol or "").strip().lower()
    clean_attempt_id = str(sell_attempt_id or "").strip()
    if not clean_symbol or not clean_attempt_id:
        return {"allowed": False, "reason": "Missing symbol or sell attempt id"}

    parsed_amount = None
    if expected_amount is not None:
        parsed_amount = _positive_float(
            expected_amount, "expected sell amount", clean_symbol
        )
        if parsed_amount is None:
            return {"allowed": False, "reason": "Invalid expected sell amount"}
    parsed_price = None
    if expected_price is not None:
        parsed_price = _positive_float(
            expected_price, "expected sell price", clean_symbol
        )
        if parsed_price is None:
            return {"allowed": False, "reason": "Invalid expected sell price"}
    normalized_mode = (
        _normalize_mode(expected_mode) if expected_mode is not None else None
    )
    clean_actor = str(actor or "").strip()
    consumed = None
    denied_reason = "Sell attempt is not available"

    def matches(left, right) -> bool:
        return math.isclose(float(left), float(right), rel_tol=1e-12, abs_tol=1e-12)

    def update(portfolio):
        nonlocal consumed, denied_reason
        portfolio = portfolio if isinstance(portfolio, dict) else {}
        positions = (
            portfolio.get("positions")
            if isinstance(portfolio.get("positions"), dict)
            else portfolio
        )
        position = positions.get(clean_symbol) if isinstance(positions, dict) else None
        if not isinstance(position, dict):
            denied_reason = "Position not found"
            return portfolio
        status = str(position.get("status", "OPEN")).strip().upper()
        if status != "SELLING":
            denied_reason = f"Position status is {status}"
            return portfolio
        if str(position.get("sell_attempt_id") or "") != clean_attempt_id:
            denied_reason = "Sell attempt id does not match position claim"
            return portfolio

        canonical_amount = position.get("selling_amount", position.get("amount_coin"))
        canonical_price = position.get("selling_price")
        canonical_mode = _normalize_mode(
            position.get("selling_mode", position.get("mode", "paper"))
        )
        canonical_actor = str(position.get("selling_actor") or "").strip()
        try:
            canonical_amount = float(canonical_amount)
            canonical_price = float(canonical_price)
        except (TypeError, ValueError):
            denied_reason = "Position sell claim has invalid canonical details"
            return portfolio
        if canonical_amount <= 0 or canonical_price <= 0:
            denied_reason = "Position sell claim has invalid canonical details"
            return portfolio
        if parsed_amount is not None and not matches(canonical_amount, parsed_amount):
            denied_reason = "Sell amount does not match position claim"
            return portfolio
        if parsed_price is not None and not matches(canonical_price, parsed_price):
            denied_reason = "Sell price does not match position claim"
            return portfolio
        if normalized_mode is not None and canonical_mode != normalized_mode:
            denied_reason = "Sell mode does not match position claim"
            return portfolio
        if clean_actor and canonical_actor != clean_actor:
            denied_reason = "Sell actor does not match position claim"
            return portfolio

        position["status"] = "SUBMITTING_SELL"
        position["consumed_sell_attempt_id"] = clean_attempt_id
        position["sell_attempt_consumed_at"] = datetime.now(timezone.utc).isoformat()
        position.pop("sell_attempt_id", None)
        consumed = {
            "symbol": clean_symbol,
            "amount": canonical_amount,
            "price": canonical_price,
            "mode": canonical_mode,
            "actor": canonical_actor,
            "sell_attempt_id": clean_attempt_id,
            "position": deepcopy(position),
        }
        return portfolio

    try:
        locked_json_update(PORTFOLIO_FILE, update, {}, fail_closed=True)
    except Exception as e:
        logger.error(f"Failed to consume sell attempt for {clean_symbol.upper()}: {e}")
        return {"allowed": False, "reason": f"Sell attempt persistence failed: {e}"}
    if consumed is None:
        return {"allowed": False, "reason": denied_reason}
    return {"allowed": True, "reason": "Sell attempt consumed for submit", **consumed}


def finalize_position_sell(
    symbol: str,
    sell_attempt_id: str,
    success: bool,
    error: str = "",
    sold_amount=None,
    sell_all: bool = True,
    dust_threshold: float = 0.000000000001,
    manual_reconciliation_required: bool = False,
    submission_status: str = "",
) -> bool:
    """Finish one claimed sell attempt; failures remain visible and fail-closed."""
    clean_symbol = str(symbol or "").strip().lower()
    finalized = False

    def update(portfolio):
        nonlocal finalized
        portfolio = portfolio if isinstance(portfolio, dict) else {}
        positions = (
            portfolio.get("positions")
            if isinstance(portfolio.get("positions"), dict)
            else portfolio
        )
        position = positions.get(clean_symbol) if isinstance(positions, dict) else None
        if not isinstance(position, dict):
            raise ValueError(f"Position {clean_symbol.upper()} not found")
        status = str(position.get("status", "")).strip().upper()
        owns_selling = (
            status == "SELLING" and position.get("sell_attempt_id") == sell_attempt_id
        )
        owns_submitting = (
            status == "SUBMITTING_SELL"
            and position.get("consumed_sell_attempt_id") == sell_attempt_id
        )
        if not owns_selling and not owns_submitting:
            raise ValueError(
                f"Sell attempt does not own position {clean_symbol.upper()}"
            )
        finished_at = datetime.now(timezone.utc).isoformat()
        if not success:
            position.update(
                {
                    "status": "FAILED_UNKNOWN"
                    if manual_reconciliation_required
                    else "FAILED",
                    "sell_error": error or "Sell execution failed",
                    "selling_finished_at": finished_at,
                    "manual_reconciliation_required": bool(
                        manual_reconciliation_required
                    ),
                    "submission_status": submission_status
                    or ("UNKNOWN" if manual_reconciliation_required else "FAILED"),
                }
            )
            finalized = True
            return portfolio

        held = float(position.get("amount_coin", 0))
        amount = held if sold_amount is None else float(sold_amount)
        if amount <= 0 or amount > held:
            raise ValueError(f"Invalid sold amount for {clean_symbol.upper()}")
        remaining = held - amount
        if remaining <= dust_threshold:
            position["status"] = "SOLD"
            position["selling_finished_at"] = finished_at
            del positions[clean_symbol]
        else:
            if sell_all:
                logger.warning(
                    f"⚠️ Partial fill detected for {clean_symbol.upper()}: requested to sell all, "
                    f"but remaining coin amount {remaining} is above dust threshold. Keeping position OPEN."
                )
            position["amount_coin"] = remaining
            position["status"] = "OPEN"
            position["last_sell_attempt_id"] = sell_attempt_id
            position["last_sell_finished_at"] = finished_at
            for key in (
                "sell_attempt_id",
                "selling_reason",
                "selling_price",
                "selling_amount",
                "selling_mode",
                "selling_actor",
                "selling_started_at",
                "consumed_sell_attempt_id",
                "sell_attempt_consumed_at",
                "sell_error",
            ):
                position.pop(key, None)
        finalized = True
        return portfolio

    try:
        locked_json_update(PORTFOLIO_FILE, update, {}, fail_closed=True)
    except Exception as e:
        logger.error(f"Failed to finalize sell for {clean_symbol.upper()}: {e}")
        return False
    return finalized


def execute_position_sell(
    symbol: str,
    price,
    reason: str = "",
    actor: str = "position_sell",
    sold_amount=None,
    sell_all: bool = True,
    dust_threshold: float = 0.000000000001,
    metadata=None,
) -> dict:
    """Atomically claim, execute, and finalize a sell for a tracked position."""
    clean_symbol = str(symbol or "").strip().lower()
    parsed_price = _positive_float(price, "sell price", clean_symbol)
    if not clean_symbol or parsed_price is None:
        error = "Invalid tracked-position sell input"
        return {
            "success": False,
            "mode": "blocked",
            "action": "sell",
            "symbol": clean_symbol,
            "error": error,
            "reason": error,
        }

    claim = claim_position_for_sell(
        clean_symbol, reason, parsed_price, actor=actor, amount=sold_amount
    )
    if not claim.get("allowed"):
        error = claim.get("reason", "Position sell claim failed")
        return {
            "success": False,
            "mode": "blocked",
            "action": "sell",
            "symbol": clean_symbol,
            "error": error,
            "reason": error,
        }

    sell_attempt_id = claim["sell_attempt_id"]
    claimed_position = claim.get("position") or {}
    held_amount = _positive_float(
        claimed_position.get("amount_coin"), "claimed amount", clean_symbol
    )
    requested_amount = _positive_float(
        claimed_position.get("selling_amount"), "claimed sell amount", clean_symbol
    )
    if (
        held_amount is None
        or requested_amount is None
        or requested_amount > held_amount
    ):
        error = "Claimed position has invalid sell amount"
        finalize_position_sell(clean_symbol, sell_attempt_id, False, error=error)
        return {
            "success": False,
            "mode": "blocked",
            "action": "sell",
            "symbol": clean_symbol,
            "error": error,
            "reason": error,
        }

    position_mode = _normalize_mode(claimed_position.get("mode", "paper"))
    execution_metadata = dict(metadata or {})
    execution_metadata.update(
        {
            "position_mode": position_mode,
            "sell_attempt_id": sell_attempt_id,
            "selling_actor": actor,
        }
    )
    try:
        result = execute_sell(
            clean_symbol,
            requested_amount,
            parsed_price,
            reason=reason,
            metadata=execution_metadata,
            force_paper=(position_mode == "paper"),
            require_real=(position_mode == "real"),
        )
    except Exception as e:
        finalize_position_sell(clean_symbol, sell_attempt_id, False, error=str(e))
        logger.error(f"Tracked-position sell failed for {clean_symbol.upper()}: {e}")
        return {
            "success": False,
            "mode": "blocked",
            "action": "sell",
            "symbol": clean_symbol,
            "error": str(e),
            "reason": str(e),
        }

    if not isinstance(result, dict):
        error = f"Invalid sell response: {result!r}"
        finalize_position_sell(clean_symbol, sell_attempt_id, False, error=error)
        return {
            "success": False,
            "mode": "blocked",
            "action": "sell",
            "symbol": clean_symbol,
            "error": error,
            "reason": error,
        }

    unknown = bool(
        result.get("submission_status") == "UNKNOWN"
        or result.get("manual_reconciliation_required")
    )
    if not result.get("success"):
        finalized = finalize_position_sell(
            clean_symbol,
            sell_attempt_id,
            False,
            error=result.get("error") or "Sell execution failed",
            manual_reconciliation_required=unknown,
            submission_status=result.get("submission_status", ""),
        )
        result["portfolio_saved"] = finalized
        if not finalized and result.get("mode") == "real":
            result["recovery_journal_written"] = record_order_recovery(
                clean_symbol,
                "sell",
                requested_amount,
                parsed_price,
                result,
                reason,
                "Real sell result could not be persisted to portfolio",
            )
        return result

    finalized = finalize_position_sell(
        clean_symbol,
        sell_attempt_id,
        True,
        sold_amount=result.get("sold_coin", requested_amount),
        sell_all=sell_all,
        dust_threshold=dust_threshold,
    )
    if not finalized:
        error = "Real sell executed but portfolio position could not be updated"
        recovery_written = False
        if result.get("mode") == "real":
            recovery_written = record_order_recovery(
                clean_symbol,
                "sell",
                requested_amount,
                parsed_price,
                result,
                reason,
                error,
            )
        failed = dict(result)
        failed.update(
            {
                "success": False,
                "order_executed": True,
                "portfolio_saved": False,
                "recovery_journal_written": recovery_written,
                "error": error,
                "reason": error,
            }
        )
        return failed

    if result.get("success"):
        avg_price = result.get("avg_price", parsed_price)
        buy_price = claimed_position.get("buy_price", avg_price)
        was_win = avg_price >= buy_price
        entry_features = claimed_position.get("entry_features")
        try:
            from ml_engine import record_online_feedback
            record_online_feedback(clean_symbol, entry_features or {}, was_win)
            logger.info(f"Feedback online learning dikirim untuk {clean_symbol.upper()} | Win: {was_win}")
        except Exception as e:
            logger.error(f"Gagal mengirim feedback online learning: {e}")

    result["portfolio_saved"] = True
    result["sell_attempt_id"] = sell_attempt_id
    result["claimed_position"] = claimed_position
    return result


def update_highest_price(symbol: str, highest_price: float):
    """Update trailing-high state without replacing an entire stale portfolio snapshot."""
    final_highest = None

    def update(portfolio):
        nonlocal final_highest
        portfolio = portfolio if isinstance(portfolio, dict) else {}
        position = portfolio.get(symbol)
        if not isinstance(position, dict):
            raise ValueError(f"No tracked position for {symbol.upper()}")
        previous = float(position.get("highest_price", position.get("buy_price", 0)))
        if highest_price > previous:
            position["highest_price"] = highest_price
        final_highest = max(previous, highest_price)
        return portfolio

    try:
        locked_json_update(PORTFOLIO_FILE, update, {})
    except Exception as e:
        logger.error(f"Failed to update highest price for {symbol.upper()}: {e}")
        return None
    return final_highest


def check_tp_sl(current_prices: dict) -> list:
    """Mengecek semua posisi aktif terhadap harga saat ini.
    Jika ada yang kena TP atau SL, langsung JUAL otomatis.

    Args:
        current_prices: dict {symbol: current_price_float}

    Returns:
        list of dict berisi laporan penjualan untuk dikirim ke Telegram.
    """
    portfolio = _load_portfolio()
    reports = []

    for symbol, pos in list(portfolio.items()):
        if str(pos.get("status", "OPEN")).strip().upper() != "OPEN":
            continue
        has_price, raw_curr_price = _current_price_value(current_prices, symbol)
        if not has_price:
            continue

        curr_price = _positive_float(raw_curr_price, "current price", symbol)
        amount = _positive_float(pos.get("amount_coin"), "amount", symbol)
        buy_price = _positive_float(pos.get("buy_price"), "buy price", symbol)
        if curr_price is None or amount is None or buy_price is None:
            continue
        sl = pos["sl"]
        tp1 = pos["tp1"]
        tp2 = pos["tp2"]
        highest = pos.get("highest_price", buy_price)
        position_mode = _normalize_mode(pos.get("mode", "paper"))

        # Update trailing high
        if curr_price > highest:
            pos["highest_price"] = curr_price
            persisted_highest = update_highest_price(symbol, curr_price)
            highest = persisted_highest if persisted_highest is not None else curr_price

        reason = ""
        action = False

        # Hitung PnL
        pnl_pct = (curr_price - buy_price) / buy_price * 100

        # 1. Cek Stop Loss (Cutloss)
        if curr_price <= sl:
            reason = f"🛑 STOP LOSS TERSENTUH (-{abs(pnl_pct):.2f}%)"
            action = True

        # 2. Cek Take Profit 2 (All Out)
        elif curr_price >= tp2:
            reason = f"🎯 TAKE PROFIT 2 TERSENTUH (+{pnl_pct:.2f}%)"
            action = True

        # 3. Cek Trailing Stop / TP1 (Sederhana: Kalau sudah lewat TP1, dan turun X% dari highest)
        # Trailing stop aktif jika harga sudah minimal naik 2%
        elif pnl_pct > 2.0:
            trailing_drop = (highest - curr_price) / highest * 100
            if trailing_drop >= 2.5:  # Jika turun 2.5% dari pucuk tertinggi
                reason = f"🛡️ TRAILING STOP AKTIF (+{pnl_pct:.2f}%)"
                action = True

        if action:
            logger.info(
                f"Eksekusi Jual Otomatis {symbol.upper()}: {reason} di harga {curr_price:,.0f}"
            )
            res = execute_position_sell(
                symbol,
                curr_price,
                reason=reason,
                actor="auto_tp_sl",
                sell_all=True,
                metadata={"source": "check_tp_sl"},
            )
            if res.get("success"):
                received_idr = res.get("received_idr", 0)
                spent_idr = buy_price * amount
                profit_idr = received_idr - spent_idr

                reports.append(
                    {
                        "symbol": symbol.upper(),
                        "reason": reason,
                        "sell_price": res.get("avg_price", curr_price),
                        "buy_price": buy_price,
                        "profit_pct": pnl_pct,
                        "profit_idr": profit_idr,
                        "mode": res.get("mode", position_mode),
                    }
                )
            else:
                logger.error(
                    f"Gagal mengeksekusi Auto-Sell {symbol.upper()}: {res.get('error')}"
                )

    return reports
