import hmac
import math
import os
import secrets
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from core import execution_engine, portfolio_manager, risk_manager
from core.applog import get_logger
from core.persistence import (
    CorruptJSONError,
    atomic_write_json,
    locked_json_update,
    read_json_safe,
    read_json_strict,
)

logger = get_logger("command_router")

PENDING_STATUSES = {"PENDING", "EXECUTING", "SUBMITTING"}
FINAL_STATUSES = {"CANCELLED", "EXECUTED", "EXPIRED", "FAILED", "FAILED_UNKNOWN"}
SENSITIVE_COMMANDS = {"BUY", "SELL", "KILL", "RESUME", "CANCEL"}


def env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    value = str(raw).strip().lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    return default


def env_int(name: str, default: int) -> int:
    try:
        value = int(str(os.environ.get(name, str(default))).strip())
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default


def _writable_data_path(filename: str) -> str:
    override = os.environ.get("PENDING_TRADES_FILE") if filename == "pending_trades.json" else os.environ.get("RISK_OVERRIDE_FILE")
    if override:
        return override
    try:
        if os.path.isdir("/data") and os.access("/data", os.W_OK):
            return os.path.join("/data", filename)
    except OSError:
        pass
    return filename


def pending_trades_path() -> str:
    return _writable_data_path("pending_trades.json")


def risk_override_path() -> str:
    return _writable_data_path("risk_override.json")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


def _parse_datetime(value: Any) -> Optional[datetime]:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _read_json(path: str, default, fail_closed_default=None):
    return read_json_safe(path, default, fail_closed_default=fail_closed_default)


def _write_json(path: str, data) -> bool:
    try:
        return atomic_write_json(path, data)
    except Exception as e:
        logger.error(f"Failed to write {path}: {e}")
        return False


def read_pending_proposals() -> list:
    data = read_json_strict(pending_trades_path(), [])
    return _require_proposal_list(data)


def _load_proposals() -> list:
    return read_pending_proposals()


def _require_proposal_list(proposals) -> list:
    if not isinstance(proposals, list):
        raise CorruptJSONError("pending_trades.json must contain a JSON list")
    return proposals


def _save_proposals(proposals: list) -> bool:
    return _write_json(pending_trades_path(), proposals)


def _clean_symbol(symbol) -> str:
    return str(symbol or "").strip().lower()


def _positive_float(value):
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _canonical_proposal_amount(proposal):
    if str(proposal.get("action", "")).upper() == "BUY":
        return proposal.get("proposed_idr")
    return proposal.get("amount_coin")


def _detail_value_matches(actual, expected) -> bool:
    if str(actual).upper() == "ALL" or str(expected).upper() == "ALL":
        return str(actual).upper() == str(expected).upper()
    actual_number = _positive_float(actual)
    expected_number = _positive_float(expected)
    if actual_number is None or expected_number is None:
        return False
    return math.isclose(actual_number, expected_number, rel_tol=1e-9, abs_tol=1e-9)


def _canonical_order_details(proposal: dict) -> dict:
    stored = proposal.get("canonical_order") if isinstance(proposal.get("canonical_order"), dict) else None
    source = stored or proposal
    action = str(source.get("action", proposal.get("action", ""))).strip().upper()
    return {
        "action": action,
        "side": str(source.get("side", action.lower())).strip().lower(),
        "symbol": _clean_symbol(source.get("symbol", proposal.get("symbol"))),
        "amount": source.get("amount") if stored else _canonical_proposal_amount(proposal),
        "price": source.get("price", proposal.get("price")),
        "execution_mode_at_creation": _normalized_execution_mode(
            source.get(
                "execution_mode_at_creation",
                proposal.get("execution_mode_at_creation", proposal.get("mode")),
            )
        ),
    }


def _proposal_mode() -> str:
    if execution_engine.is_paper_trading_mode():
        return "paper"
    if execution_engine.is_auto_trade_enabled():
        return "real"
    return "blocked"


def _normalized_execution_mode(value) -> str:
    return str(value or "").strip().lower() if str(value or "").strip().lower() in {"paper", "real", "blocked"} else "blocked"


def confirm_before_trade() -> bool:
    return env_bool("CONFIRM_BEFORE_TRADE", True)


def parse_command(text) -> dict:
    raw = str(text or "").strip()
    if not raw:
        return {"type": "UNKNOWN", "raw": raw, "error": "Empty command"}

    parts = raw.split()
    head = parts[0].lstrip("/").upper()

    if head in {"STATUS", "RISK", "KILL", "RESUME"}:
        if len(parts) != 1:
            return {"type": "UNKNOWN", "raw": raw, "error": f"{head} does not accept arguments"}
        return {"type": head, "raw": raw}

    if head == "CANCEL":
        if len(parts) != 2:
            return {"type": "UNKNOWN", "raw": raw, "error": "CANCEL requires SYMBOL"}
        return {"type": "CANCEL", "symbol": _clean_symbol(parts[1]), "raw": raw}

    if head == "BUY":
        if len(parts) != 3:
            return {"type": "UNKNOWN", "raw": raw, "error": "BUY requires SYMBOL and AMOUNT_IDR"}
        amount = _positive_float(parts[2])
        if amount is None:
            return {"type": "UNKNOWN", "symbol": _clean_symbol(parts[1]), "raw": raw, "error": "Invalid BUY amount"}
        return {"type": "BUY", "symbol": _clean_symbol(parts[1]), "amount": amount, "raw": raw}

    if head == "SELL":
        if len(parts) != 3:
            return {"type": "UNKNOWN", "raw": raw, "error": "SELL requires SYMBOL and AMOUNT/ALL"}
        amount_raw = parts[2].upper()
        amount = "ALL" if amount_raw == "ALL" else _positive_float(parts[2])
        if amount is None:
            return {"type": "UNKNOWN", "symbol": _clean_symbol(parts[1]), "raw": raw, "error": "Invalid SELL amount"}
        return {"type": "SELL", "symbol": _clean_symbol(parts[1]), "amount": amount, "raw": raw}

    return {"type": "UNKNOWN", "raw": raw, "error": "Unknown command"}


def authorize_telegram_command(message, command, configured_chat_id, allowed_user_id=None) -> dict:
    message = message if isinstance(message, dict) else {}
    command = command if isinstance(command, dict) else {}
    msg_chat_id = str(message.get("chat", {}).get("id", ""))
    if not configured_chat_id or msg_chat_id != str(configured_chat_id):
        return {"allowed": False, "reason": "Unauthorized Telegram chat"}

    allowed_user = str(
        allowed_user_id if allowed_user_id is not None else os.environ.get("TELEGRAM_ALLOWED_USER_ID", "")
    ).strip()
    sender_id = str(message.get("from", {}).get("id", "")).strip()
    if allowed_user and sender_id != allowed_user:
        return {"allowed": False, "reason": "Unauthorized Telegram user"}

    command_type = str(command.get("type", "UNKNOWN")).upper()
    chat_type = str(message.get("chat", {}).get("type", "")).lower()
    if not allowed_user and command_type in SENSITIVE_COMMANDS and chat_type in {"group", "supergroup", "channel"}:
        return {
            "allowed": False,
            "reason": "Sensitive command blocked in group: TELEGRAM_ALLOWED_USER_ID is not configured",
        }
    return {"allowed": True, "reason": "Authorized"}


def _expire_proposals_in_place(proposals: list) -> list:
    now = _now()
    for proposal in proposals:
        if proposal.get("status") != "PENDING":
            continue
        expires_at = _parse_datetime(proposal.get("expires_at"))
        if expires_at is None:
            logger.warning(f"Proposal {proposal.get('id', '?')} has invalid/missing expiry; expiring fail-closed.")
            proposal["status"] = "EXPIRED"
        elif expires_at <= now:
            proposal["status"] = "EXPIRED"
    return proposals


def expire_old_proposals() -> list:
    return locked_json_update(
        pending_trades_path(),
        lambda proposals: _expire_proposals_in_place(_require_proposal_list(proposals)),
        [],
        fail_closed=True,
    )


def create_trade_proposal(
    symbol,
    action,
    proposed_idr=None,
    amount_coin=None,
    price=None,
    tp1=None,
    tp2=None,
    sl=None,
    risk_level=None,
    reason="",
    mode=None,
    metadata=None,
    ttl_minutes=None,
) -> dict:
    clean_symbol = _clean_symbol(symbol)
    clean_action = str(action or "").strip().upper()
    ttl = ttl_minutes if isinstance(ttl_minutes, int) and ttl_minutes > 0 else env_int("PENDING_TRADE_TTL_MINUTES", 10)
    created_at = _now()
    current_mode = _proposal_mode()
    requested_mode = _normalized_execution_mode(mode) if mode is not None else current_mode
    execution_mode = current_mode if requested_mode == current_mode else "blocked"
    proposal = {
        "id": uuid.uuid4().hex[:12],
        "symbol": clean_symbol,
        "action": clean_action,
        "proposed_idr": proposed_idr,
        "amount_coin": amount_coin,
        "price": price,
        "tp1": tp1,
        "tp2": tp2,
        "sl": sl,
        "risk_level": risk_level,
        "reason": reason,
        "created_at": _iso(created_at),
        "expires_at": _iso(created_at + timedelta(minutes=ttl)),
        "mode": execution_mode,
        "execution_mode_at_creation": execution_mode,
        "side": clean_action.lower(),
        "confirmation_token": secrets.token_urlsafe(32),
        "status": "PENDING",
        "metadata": metadata or {},
    }
    proposal["canonical_order"] = _canonical_order_details(proposal)
    blocked_by_executing = False

    def update(proposals):
        nonlocal blocked_by_executing
        proposals = _expire_proposals_in_place(_require_proposal_list(proposals))
        if any(
            old.get("symbol") == clean_symbol
            and old.get("action") == clean_action
            and old.get("status") in {"EXECUTING", "SUBMITTING"}
            for old in proposals
        ):
            blocked_by_executing = True
            return proposals
        for old in proposals:
            if old.get("symbol") == clean_symbol and old.get("action") == clean_action and old.get("status") == "PENDING":
                old["status"] = "CANCELLED"
        proposals.append(proposal)
        return proposals

    try:
        locked_json_update(pending_trades_path(), update, [], fail_closed=True)
        if blocked_by_executing:
            return {
                **proposal,
                "status": "FAILED",
                "error": "An EXECUTING proposal already exists for this symbol/action",
            }
        return proposal
    except Exception as e:
        logger.error(f"Failed to create proposal for {clean_symbol.upper()}: {e}")
        return {
            **proposal,
            "status": "FAILED",
            "error": f"Proposal persistence failed: {e}",
        }


def create_buy_confirmation_proposal(symbol, amount_idr, price, **kwargs) -> dict:
    if not confirm_before_trade():
        return {"requires_confirmation": False, "proposal": None}
    proposal = create_trade_proposal(
        symbol=symbol,
        action="BUY",
        proposed_idr=amount_idr,
        price=price,
        **kwargs,
    )
    return {"requires_confirmation": True, "proposal": proposal}


def get_pending_proposal(symbol, action=None):
    proposals = expire_old_proposals()
    clean_symbol = _clean_symbol(symbol)
    clean_action = str(action or "").strip().upper()
    matches = [
        proposal
        for proposal in proposals
        if proposal.get("symbol") == clean_symbol
        and proposal.get("status") == "PENDING"
        and (not clean_action or proposal.get("action") == clean_action)
    ]
    return matches[-1] if matches else None


def _update_proposal_status(proposal_id, status: str, expected_status=None, updates=None):
    updated = None

    def update(proposals):
        nonlocal updated
        proposals = _require_proposal_list(proposals)
        for proposal in proposals:
            if proposal.get("id") == proposal_id:
                if expected_status is not None and proposal.get("status") != expected_status:
                    return proposals
                proposal["status"] = status
                if isinstance(updates, dict):
                    proposal.update(updates)
                updated = dict(proposal)
                break
        return proposals

    try:
        locked_json_update(pending_trades_path(), update, [], fail_closed=True)
    except Exception as e:
        logger.error(f"Failed to update proposal {proposal_id}: {e}")
        return None
    return updated


def _tokens_match(actual, supplied) -> bool:
    if not actual or not supplied:
        return False
    return hmac.compare_digest(str(actual), str(supplied))


def claim_pending_proposal(symbol_or_id, confirmation_token=None, action=None):
    """Atomically validate and claim exactly one pending proposal."""
    target = str(symbol_or_id or "").strip().lower()
    clean_action = str(action or "").strip().upper()
    claimed = None

    def update(proposals):
        nonlocal claimed
        proposals = _expire_proposals_in_place(_require_proposal_list(proposals))
        matches = [
            proposal
            for proposal in proposals
            if (
                str(proposal.get("id", "")).lower() == target
                or proposal.get("symbol") == target
            )
            and (not clean_action or proposal.get("action") == clean_action)
        ]
        for proposal in reversed(matches):
            if proposal.get("status") != "PENDING":
                continue
            if not _tokens_match(proposal.get("confirmation_token"), confirmation_token):
                return proposals
            proposal["status"] = "EXECUTING"
            claimed = dict(proposal)
            return proposals
        return proposals

    try:
        locked_json_update(pending_trades_path(), update, [], fail_closed=True)
    except Exception as e:
        logger.error(f"Failed to claim proposal {symbol_or_id}: {e}")
        return None
    return claimed


def _claim_proposal(proposal: dict, confirmation_token=None):
    if not isinstance(proposal, dict):
        return None
    return claim_pending_proposal(
        proposal.get("id"),
        confirmation_token=confirmation_token,
        action=proposal.get("action"),
    )


def consume_confirmation_token_for_submit(
    proposal_id,
    token,
    action,
    symbol,
    amount,
    price,
    requested_mode,
    execution_amount=None,
):
    """Atomically consume a confirmation token and authorize one submit attempt."""
    consumed = None
    submit_authorization = secrets.token_urlsafe(32)
    submit_attempt_id = uuid.uuid4().hex

    def update(proposals):
        nonlocal consumed
        proposals = _require_proposal_list(proposals)
        for proposal in proposals:
            if proposal.get("id") != proposal_id:
                continue
            if proposal.get("status") != "EXECUTING":
                return proposals
            if not _tokens_match(proposal.get("confirmation_token"), token):
                return proposals
            expires_at = _parse_datetime(proposal.get("expires_at"))
            if expires_at is None or expires_at <= _now():
                proposal["status"] = "EXPIRED"
                return proposals
            canonical = _canonical_order_details(proposal)
            clean_action = str(action or "").strip().upper()
            clean_symbol = _clean_symbol(symbol)
            clean_mode = _normalized_execution_mode(requested_mode)
            if (
                canonical["action"] != clean_action
                or canonical["side"] != clean_action.lower()
                or canonical["symbol"] != clean_symbol
                or not _detail_value_matches(canonical["amount"], amount)
                or not _detail_value_matches(canonical["price"], price)
                or canonical["execution_mode_at_creation"] != clean_mode
            ):
                return proposals
            bound_amount = execution_amount if execution_amount is not None else amount
            if _positive_float(bound_amount) is None:
                return proposals
            proposal["status"] = "SUBMITTING"
            proposal["confirmation_token"] = None
            proposal["confirmation_token_consumed_at"] = _iso(_now())
            proposal["submit_authorization"] = submit_authorization
            proposal["submit_attempt_id"] = submit_attempt_id
            proposal["submit_details"] = {
                "action": clean_action,
                "symbol": clean_symbol,
                "amount": float(bound_amount),
                "price": float(price),
                "requested_mode": clean_mode,
            }
            consumed = dict(proposal)
            return proposals
        return proposals

    try:
        locked_json_update(pending_trades_path(), update, [], fail_closed=True)
    except Exception as e:
        logger.error(f"Failed to consume confirmation token for {proposal_id}: {e}")
        return None
    return consumed


def consume_submit_authorization(
    proposal_id,
    submit_authorization,
    action,
    symbol,
    amount,
    price,
    requested_mode,
) -> bool:
    """Consume the final execution authorization exactly once inside execution_engine."""
    consumed = False

    def update(proposals):
        nonlocal consumed
        proposals = _require_proposal_list(proposals)
        for proposal in proposals:
            submit_details = proposal.get("submit_details") if isinstance(proposal.get("submit_details"), dict) else {}
            if (
                proposal.get("id") == proposal_id
                and proposal.get("status") == "SUBMITTING"
                and proposal.get("action") == str(action or "").upper()
                and _tokens_match(proposal.get("submit_authorization"), submit_authorization)
                and submit_details.get("action") == str(action or "").upper()
                and submit_details.get("symbol") == _clean_symbol(symbol)
                and _detail_value_matches(submit_details.get("amount"), amount)
                and _detail_value_matches(submit_details.get("price"), price)
                and submit_details.get("requested_mode") == _normalized_execution_mode(requested_mode)
                and submit_details.get("requested_mode") == "real"
                and _normalized_execution_mode(
                    proposal.get("execution_mode_at_creation", proposal.get("mode"))
                ) == "real"
            ):
                proposal["submit_authorization"] = None
                proposal["submit_authorization_consumed_at"] = _iso(_now())
                consumed = True
                return proposals
        return proposals

    try:
        locked_json_update(pending_trades_path(), update, [], fail_closed=True)
    except Exception as e:
        logger.error(f"Failed to consume submit authorization for {proposal_id}: {e}")
        return False
    return consumed


def _finish_proposal(proposal_id, success: bool, result=None):
    unknown = bool(
        isinstance(result, dict)
        and result.get("submission_status") == "UNKNOWN"
        and result.get("manual_reconciliation_required")
    )
    final_status = "EXECUTED" if success else ("FAILED_UNKNOWN" if unknown else "FAILED")
    updates = None
    if unknown:
        updates = {
            "manual_reconciliation_required": True,
            "submission_status": "UNKNOWN",
            "failure_error": result.get("error"),
        }
    return (
        _update_proposal_status(proposal_id, final_status, expected_status="SUBMITTING", updates=updates)
        or _update_proposal_status(proposal_id, final_status, expected_status="EXECUTING", updates=updates)
    )


def _blocked_result(action: str, symbol: str, error: str) -> dict:
    return {
        "success": False,
        "mode": "blocked",
        "action": action,
        "symbol": symbol,
        "error": error,
        "reason": error,
    }


def _persistence_failure_result(result: dict, error: str, recovery_written: bool = False) -> dict:
    failed = dict(result or {})
    failed.update({
        "success": False,
        "order_executed": bool((result or {}).get("success")),
        "portfolio_saved": False,
        "recovery_journal_written": bool(recovery_written),
        "error": error,
        "reason": error,
    })
    return failed


def _proposal_execution_flags(proposal: dict):
    creation_mode = _normalized_execution_mode(
        proposal.get("execution_mode_at_creation", proposal.get("mode"))
    )
    current_mode = _proposal_mode()
    if creation_mode == "blocked":
        return None, None, "Proposal was blocked at creation and cannot be executed"
    if creation_mode != current_mode:
        return None, None, (
            f"Proposal execution mode changed from {creation_mode} to {current_mode}; execution blocked"
        )
    return creation_mode == "paper", creation_mode == "real", None


def cancel_trade_proposal(symbol):
    clean_symbol = _clean_symbol(symbol)
    cancelled = None

    def update(proposals):
        nonlocal cancelled
        proposals = _expire_proposals_in_place(_require_proposal_list(proposals))
        for proposal in reversed(proposals):
            if proposal.get("symbol") == clean_symbol and proposal.get("status") == "PENDING":
                proposal["status"] = "CANCELLED"
                cancelled = dict(proposal)
                break
        return proposals

    try:
        locked_json_update(pending_trades_path(), update, [], fail_closed=True)
    except Exception as e:
        logger.error(f"Failed to cancel proposal for {clean_symbol.upper()}: {e}")
        return None
    return cancelled


def _context_value(context, key, default=None):
    if isinstance(context, dict) and key in context:
        return context.get(key)
    return default


def _risk_metadata(context=None, proposal=None) -> dict:
    context = context if isinstance(context, dict) else {}
    metadata = dict(proposal.get("metadata") or {}) if isinstance(proposal, dict) else {}
    for key in ("portfolio_state", "daily_stats", "total_capital_idr", "market_state", "risk_tag"):
        if key in context:
            metadata[key] = context[key]
    metadata.setdefault("source", "telegram_confirmation")
    return metadata


def _portfolio_positions(portfolio):
    if not isinstance(portfolio, dict):
        return None
    positions = portfolio.get("positions")
    return positions if isinstance(positions, dict) else portfolio


def _position_dust_threshold() -> float:
    try:
        value = float(str(os.environ.get("POSITION_DUST_THRESHOLD", "0.000000000001")).strip())
    except (TypeError, ValueError):
        return 0.000000000001
    return value if value > 0 else 0.000000000001


def execute_confirmed_buy(
    symbol,
    amount_idr,
    context=None,
    proposal_id=None,
    confirmation_token=None,
) -> dict:
    clean_symbol = _clean_symbol(symbol)
    amount = _positive_float(amount_idr)
    if amount is None:
        return _blocked_result("buy", clean_symbol, "Invalid amount")

    try:
        proposal = get_pending_proposal(clean_symbol, action="BUY")
    except CorruptJSONError as e:
        return _blocked_result("buy", clean_symbol, f"Pending proposal persistence is corrupt: {e}")
    if not proposal:
        return _blocked_result("buy", clean_symbol, "No pending BUY proposal")
    if proposal_id != proposal.get("id") or not _tokens_match(proposal.get("confirmation_token"), confirmation_token):
        return _blocked_result("buy", clean_symbol, "Invalid proposal confirmation token")
    if not _detail_value_matches(proposal.get("proposed_idr"), amount):
        return _blocked_result("buy", clean_symbol, "BUY amount does not match proposal")

    price = _positive_float(proposal.get("price"))
    if price is None:
        return _blocked_result("buy", clean_symbol, "Missing proposal price")

    claimed = _claim_proposal(proposal, confirmation_token=confirmation_token)
    if not claimed:
        return _blocked_result("buy", clean_symbol, "Proposal is no longer PENDING")

    canonical = _canonical_order_details(claimed)
    canonical_amount = _positive_float(canonical.get("amount"))
    canonical_price = _positive_float(canonical.get("price"))
    force_paper, require_real, mode_error = _proposal_execution_flags(claimed)
    if canonical_amount is None or canonical_price is None or mode_error:
        _finish_proposal(claimed["id"], False)
        return _blocked_result("buy", clean_symbol, mode_error or "Proposal canonical BUY details are invalid")

    submitting = consume_confirmation_token_for_submit(
        claimed["id"],
        confirmation_token,
        action="BUY",
        symbol=canonical["symbol"],
        amount=canonical_amount,
        price=canonical_price,
        requested_mode=canonical["execution_mode_at_creation"],
        execution_amount=canonical_amount,
    )
    if not submitting:
        _finish_proposal(claimed["id"], False)
        return _blocked_result("buy", clean_symbol, "Confirmation token could not be consumed for submit")

    metadata = _risk_metadata(context, claimed)
    metadata["proposal_id"] = claimed["id"]
    metadata["submit_authorization"] = submitting.get("submit_authorization")
    metadata["submit_attempt_id"] = submitting.get("submit_attempt_id")
    try:
        result = execution_engine.execute_buy(
            canonical["symbol"],
            canonical_amount,
            canonical_price,
            reason=claimed.get("reason", "Telegram confirmed BUY"),
            metadata=metadata,
            force_paper=force_paper,
            require_real=require_real,
        )
    except Exception as e:
        _finish_proposal(claimed["id"], False)
        logger.error(f"Confirmed buy execution failed for {clean_symbol.upper()}: {e}")
        return _blocked_result("buy", clean_symbol, str(e))

    if result.get("success"):
        saved = portfolio_manager.save_position(
            symbol=canonical["symbol"],
            buy_price=result.get("avg_price", canonical_price),
            amount_coin=result.get("received_coin", canonical_amount / canonical_price),
            tp1=claimed.get("tp1") or canonical_price,
            tp2=claimed.get("tp2") or canonical_price,
            sl=claimed.get("sl") or canonical_price,
            trade_type=claimed.get("reason") or "CONFIRMED",
            mode=result.get("mode", claimed.get("mode", "paper")),
        )
        if not saved:
            error = "Order executed but portfolio position could not be saved"
            recovery_written = False
            if result.get("mode") == "real":
                recovery_written = portfolio_manager.record_order_recovery(
                    canonical["symbol"],
                    "buy",
                    canonical_amount,
                    canonical_price,
                    result,
                    claimed.get("reason", "Telegram confirmed BUY"),
                    error,
                )
            _finish_proposal(claimed["id"], False, result=result)
            logger.error(f"Confirmed buy position save failed for {clean_symbol.upper()}")
            return _persistence_failure_result(
                result,
                error,
                recovery_written=recovery_written,
            )
    _finish_proposal(claimed["id"], bool(result.get("success")), result=result)
    return result


def execute_confirmed_sell(
    symbol,
    amount_or_all,
    context=None,
    proposal_id=None,
    confirmation_token=None,
) -> dict:
    clean_symbol = _clean_symbol(symbol)
    context = context if isinstance(context, dict) else {}
    try:
        proposal = get_pending_proposal(clean_symbol, action="SELL")
    except CorruptJSONError as e:
        return _blocked_result("sell", clean_symbol, f"Pending proposal persistence is corrupt: {e}")
    if not proposal:
        return _blocked_result("sell", clean_symbol, "No pending SELL proposal")
    if proposal_id != proposal.get("id") or not _tokens_match(proposal.get("confirmation_token"), confirmation_token):
        return _blocked_result("sell", clean_symbol, "Invalid proposal confirmation token")
    canonical = _canonical_order_details(proposal)
    if canonical["symbol"] != clean_symbol or canonical["action"] != "SELL":
        return _blocked_result("sell", clean_symbol, "SELL proposal details do not match command")
    if not _detail_value_matches(canonical.get("amount"), amount_or_all):
        return _blocked_result("sell", clean_symbol, "SELL amount does not match proposal")

    portfolio = portfolio_manager._load_portfolio()
    positions = _portfolio_positions(portfolio)
    position = positions.get(clean_symbol) if isinstance(positions, dict) else None
    if not isinstance(position, dict):
        return _blocked_result("sell", clean_symbol, "No tracked position for SELL")

    held_amount = _positive_float(position.get("amount_coin"))
    if held_amount is None:
        return _blocked_result("sell", clean_symbol, "Tracked position has invalid amount")

    position_mode = "paper"
    position_mode = "real" if str(position.get("mode", "paper")).strip().lower() == "real" else "paper"

    if str(amount_or_all).upper() == "ALL":
        amount = held_amount
    else:
        amount = _positive_float(amount_or_all)
    if amount is None:
        return _blocked_result("sell", clean_symbol, "Invalid sell amount")
    if amount > held_amount:
        return _blocked_result("sell", clean_symbol, "Sell amount exceeds tracked position")

    price = _positive_float(canonical.get("price"))
    if price is None:
        return _blocked_result("sell", clean_symbol, "Missing sell price")

    claimed = _claim_proposal(proposal, confirmation_token=confirmation_token)
    if not claimed:
        return _blocked_result("sell", clean_symbol, "Proposal is no longer PENDING")

    canonical = _canonical_order_details(claimed)
    _force_paper, _require_real, mode_error = _proposal_execution_flags(claimed)
    if mode_error or canonical["execution_mode_at_creation"] != position_mode:
        _finish_proposal(claimed["id"], False)
        return _blocked_result(
            "sell",
            clean_symbol,
            mode_error or "Proposal mode does not match tracked position mode",
        )

    submitting = consume_confirmation_token_for_submit(
        claimed["id"],
        confirmation_token,
        action="SELL",
        symbol=canonical["symbol"],
        amount=canonical["amount"],
        price=canonical["price"],
        requested_mode=canonical["execution_mode_at_creation"],
        execution_amount=amount,
    )
    if not submitting:
        _finish_proposal(claimed["id"], False)
        return _blocked_result("sell", clean_symbol, "Confirmation token could not be consumed for submit")

    metadata = _risk_metadata(context, claimed)
    metadata["position_mode"] = position_mode
    metadata["proposal_id"] = claimed["id"]
    metadata["submit_authorization"] = submitting.get("submit_authorization")
    metadata["submit_attempt_id"] = submitting.get("submit_attempt_id")
    try:
        result = portfolio_manager.execute_position_sell(
            canonical["symbol"],
            price,
            reason=claimed.get("reason", "Telegram confirmed SELL"),
            actor="telegram_confirmation",
            sold_amount=amount,
            sell_all=(str(amount_or_all).upper() == "ALL"),
            dust_threshold=_position_dust_threshold(),
            metadata=metadata,
        )
    except Exception as e:
        _finish_proposal(claimed["id"], False)
        logger.error(f"Confirmed sell execution failed for {clean_symbol.upper()}: {e}")
        return _blocked_result("sell", clean_symbol, str(e))

    _finish_proposal(claimed["id"], bool(result.get("success")), result=result)
    return result


def _load_risk_override() -> dict:
    data = _read_json(
        risk_override_path(),
        {},
        fail_closed_default={"kill_switch": True, "_corrupted": True},
    )
    return data if isinstance(data, dict) else {}


def _save_risk_override(data: dict) -> dict:
    data = dict(data or {})
    data["updated_at"] = _iso(_now())
    try:
        locked_json_update(risk_override_path(), lambda _current: data, {})
        return data
    except Exception as e:
        logger.error(f"Failed to save runtime risk override: {e}")
        return {"kill_switch": True, "_persistence_error": str(e)}


def set_runtime_kill_switch(enabled: bool) -> dict:
    return _save_risk_override({"kill_switch": bool(enabled)})


def handle_command(text, context=None) -> dict:
    command = parse_command(text)
    command_type = command.get("type")
    if command_type == "UNKNOWN":
        return {"success": False, "command": command, "message": command.get("error", "Unknown command")}

    if command_type == "KILL":
        override = set_runtime_kill_switch(True)
        return {"success": True, "command": command, "override": override, "message": "Kill switch aktif. Buy baru diblokir."}

    if command_type == "RESUME":
        override = set_runtime_kill_switch(False)
        if risk_manager.env_bool("KILL_SWITCH", risk_manager.DEFAULTS["KILL_SWITCH"]):
            return {
                "success": False,
                "command": command,
                "override": override,
                "warning": "Env KILL_SWITCH is still active; runtime resume cannot disable it.",
                "message": "Env KILL_SWITCH is still active; runtime resume cannot disable it.",
            }
        return {"success": True, "command": command, "override": override, "message": "Kill switch runtime dimatikan."}

    if command_type == "STATUS":
        try:
            pending = expire_old_proposals()
        except CorruptJSONError as e:
            return {"success": False, "command": command, "message": f"Pending proposal persistence is corrupt: {e}"}
        return {"success": True, "command": command, "message": "Bot aktif.", "pending": pending}

    if command_type == "RISK":
        return {"success": True, "command": command, "message": "Risk status.", "risk": risk_manager.get_risk_status(
            portfolio_state=_context_value(context, "portfolio_state"),
            daily_stats=_context_value(context, "daily_stats"),
        )}

    if command_type == "CANCEL":
        proposal = cancel_trade_proposal(command.get("symbol"))
        if not proposal:
            return {"success": False, "command": command, "message": "Tidak ada proposal pending untuk dibatalkan."}
        return {"success": True, "command": command, "proposal": proposal, "message": f"Proposal {command.get('symbol', '').upper()} dibatalkan."}

    if command_type == "BUY":
        try:
            proposal = get_pending_proposal(command.get("symbol"), action="BUY")
        except CorruptJSONError as e:
            result = _blocked_result("buy", command.get("symbol"), f"Pending proposal persistence is corrupt: {e}")
            return {"success": False, "command": command, "result": result, "message": result["error"]}
        result = execute_confirmed_buy(
            command.get("symbol"),
            command.get("amount"),
            context=context,
            proposal_id=(proposal or {}).get("id"),
            confirmation_token=(proposal or {}).get("confirmation_token"),
        )
        return {"success": bool(result.get("success")), "command": command, "result": result, "message": result.get("error") or result.get("reason", "BUY diproses.")}

    if command_type == "SELL":
        try:
            proposal = get_pending_proposal(command.get("symbol"), action="SELL")
        except CorruptJSONError as e:
            result = _blocked_result("sell", command.get("symbol"), f"Pending proposal persistence is corrupt: {e}")
            return {"success": False, "command": command, "result": result, "message": result["error"]}
        if not proposal:
            proposal = create_trade_proposal(
                command.get("symbol"),
                "SELL",
                amount_coin=command.get("amount"),
                price=_context_value(context, "price"),
                reason="Telegram confirmed SELL",
                metadata=_risk_metadata(context),
            )
        result = execute_confirmed_sell(
            command.get("symbol"),
            command.get("amount"),
            context=context,
            proposal_id=(proposal or {}).get("id"),
            confirmation_token=(proposal or {}).get("confirmation_token"),
        )
        return {"success": bool(result.get("success")), "command": command, "result": result, "message": result.get("error") or result.get("reason", "SELL diproses.")}

    return {"success": False, "command": command, "message": "Command belum didukung."}
