import os
import uuid
from datetime import datetime, timezone
from typing import Optional

from core import indodax_trade, risk_manager
from core.applog import get_logger
from core.persistence import append_order_recovery_record

logger = get_logger("execution_engine")


def env_bool(name: str, default: bool = False) -> bool:
    return str(os.environ.get(name, str(default))).lower() in {"1", "true", "yes", "on"}


def is_auto_trade_enabled() -> bool:
    return env_bool("AUTO_TRADE_ENABLED", False)


def is_paper_trading_mode() -> bool:
    return env_bool("PAPER_TRADING_MODE", True)


def confirm_before_trade() -> bool:
    return env_bool("CONFIRM_BEFORE_TRADE", True)


def _base_result(success: bool, mode: str, action: str, symbol: str, reason: str, error: Optional[str] = None) -> dict:
    result = {
        "success": success,
        "mode": mode,
        "action": action,
        "symbol": symbol,
        "reason": reason,
    }
    if error:
        result["error"] = error
    return result


def _clean_symbol(symbol) -> str:
    return str(symbol or "").strip().lower()


def _positive_float(value, label: str):
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None, f"Invalid {label}: {value!r}"
    if parsed <= 0:
        return None, f"Invalid {label}: {parsed}"
    return parsed, None


def _validate_inputs(symbol, amount, price, action: str, reason: str):
    clean_symbol = _clean_symbol(symbol)
    if not clean_symbol:
        return None, None, None, _base_result(False, "blocked", action, "", reason, "Invalid symbol")

    parsed_amount, amount_error = _positive_float(amount, "amount")
    if amount_error:
        return clean_symbol, None, None, _base_result(False, "blocked", action, clean_symbol, reason, amount_error)

    parsed_price, price_error = _positive_float(price, "price")
    if price_error:
        return clean_symbol, None, None, _base_result(False, "blocked", action, clean_symbol, reason, price_error)

    return clean_symbol, parsed_amount, parsed_price, None


def _risk_context(metadata=None, risk_context=None) -> dict:
    merged = {}
    if isinstance(metadata, dict):
        if isinstance(metadata.get("risk_context"), dict):
            merged.update(metadata.get("risk_context"))
        for key in ("portfolio_state", "daily_stats", "market_state", "total_capital_idr", "risk_tag"):
            if key in metadata:
                merged[key] = metadata[key]
    if isinstance(risk_context, dict):
        merged.update(risk_context)
    context = risk_manager.build_risk_context(metadata=merged)
    return {
        "portfolio_state": context.get("portfolio_state"),
        "daily_stats": context.get("daily_stats"),
        "market_state": context.get("market_state"),
        "total_capital_idr": context.get("total_capital_idr"),
        "risk_tag": context.get("risk_tag"),
    }


def _execution_mode(force_paper: bool = False) -> str:
    if force_paper:
        return "paper"
    if is_paper_trading_mode():
        return "paper"
    if not is_auto_trade_enabled():
        return "blocked"
    return "real"


def _consume_submit_permission(action: str, symbol: str, amount, price, mode: str, metadata=None) -> bool:
    if not isinstance(metadata, dict):
        return action != "BUY" or not confirm_before_trade()
    proposal_id = metadata.get("proposal_id")
    submit_authorization = metadata.get("submit_authorization")
    if not proposal_id and not submit_authorization:
        return action != "BUY" or not confirm_before_trade()
    if not proposal_id or not submit_authorization:
        return False
    try:
        from core import command_router

        return command_router.consume_submit_authorization(
            proposal_id,
            submit_authorization,
            action=action,
            symbol=symbol,
            amount=amount,
            price=price,
            requested_mode=mode,
        )
    except Exception as e:
        logger.error(f"Failed to consume submit authorization: {e}")
        return False


def _record_submission(status: str, attempt_id: str, action: str, symbol: str, amount, price, reason: str, metadata=None, result=None, error=None) -> bool:
    record = {
        "status": status,
        "attempt_id": attempt_id,
        "proposal_id": (metadata or {}).get("proposal_id") if isinstance(metadata, dict) else None,
        "action": action,
        "symbol": symbol,
        "amount": amount,
        "price": price,
        "mode": "real",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "reason": reason,
        "order_id": (result or {}).get("order_id") if isinstance(result, dict) else None,
        "error": error or ((result or {}).get("error") if isinstance(result, dict) else None),
    }
    try:
        return append_order_recovery_record(record)
    except Exception as e:
        logger.error(f"Failed to write {status} recovery record for {symbol.upper()}: {e}")
        return False


def _real_attempt_id(metadata=None) -> str:
    if isinstance(metadata, dict):
        for key in ("submit_attempt_id", "sell_attempt_id", "attempt_id"):
            if metadata.get(key):
                return str(metadata[key])
    return uuid.uuid4().hex


def _consume_position_sell_claim(symbol: str, amount, price, metadata=None) -> dict:
    if not isinstance(metadata, dict) or not metadata.get("sell_attempt_id"):
        return {"allowed": False, "reason": "Tracked position sell attempt id is required"}
    if str(metadata.get("position_mode") or "").strip().lower() != "real":
        return {"allowed": False, "reason": "Real sell requires a real-position claim"}
    try:
        from core import portfolio_manager

        return portfolio_manager.consume_sell_attempt_for_submit(
            symbol,
            metadata.get("sell_attempt_id"),
            expected_amount=amount,
            expected_price=price,
            expected_mode=metadata.get("position_mode"),
            actor=metadata.get("selling_actor"),
        )
    except Exception as e:
        logger.error(f"Failed to consume tracked position sell claim: {e}")
        return {"allowed": False, "reason": f"Tracked position sell claim validation failed: {e}"}


def execute_buy(
    symbol,
    idr_amount,
    price,
    reason="",
    metadata=None,
    force_paper: bool = False,
    require_real: bool = False,
    risk_context=None,
) -> dict:
    symbol, amount, price, invalid = _validate_inputs(symbol, idr_amount, price, "buy", reason)
    if invalid:
        return invalid

    mode = _execution_mode(force_paper=force_paper)
    bypass_risk = (mode == "paper") and str(reason).startswith("Manual")

    if bypass_risk:
        risk = {"allowed": True, "reason": "Bypassed for manual paper trade", "risk_level": "LOW"}
    else:
        risk = risk_manager.can_open_position(
            symbol,
            amount,
            **_risk_context(metadata=metadata, risk_context=risk_context),
        )

    if not risk.get("allowed"):
        result = _base_result(False, "blocked", "buy", symbol, risk.get("reason", "Risk manager blocked buy"), risk.get("reason"))
        result["risk"] = risk
        result["metadata"] = metadata or {}
        return result

    if require_real and mode != "real":
        return _base_result(False, "blocked", "buy", symbol, reason, "Real trade blocked: real position requires real execution gate")
    if mode == "real" and not _consume_submit_permission("BUY", symbol, amount, price, mode, metadata):
        return _base_result(False, "blocked", "buy", symbol, reason, "Real buy blocked: CONFIRM_BEFORE_TRADE requires Telegram confirmation")
    if mode == "paper":
        received_coin = amount / price
        return {
            **_base_result(True, "paper", "buy", symbol, reason),
            "order_id": "paper",
            "received_coin": received_coin,
            "spent_idr": amount,
            "avg_price": price,
            "metadata": metadata or {},
            "risk": risk,
        }
    if mode == "blocked":
        return _base_result(False, "blocked", "buy", symbol, reason, "Real trade blocked: AUTO_TRADE_ENABLED is false")

    attempt_id = _real_attempt_id(metadata)
    if not _record_submission("PRE_SUBMIT", attempt_id, "buy", symbol, amount, price, reason, metadata=metadata):
        return _base_result(False, "blocked", "buy", symbol, reason, "Real buy blocked: PRE_SUBMIT recovery record failed")
    logger.info(f"Executing REAL BUY {symbol.upper()} for Rp{amount:,.0f}")
    try:
        res = indodax_trade.buy_market(symbol, amount, price)
    except Exception as e:
        logger.error(f"Real buy failed for {symbol.upper()}: {e}")
        _record_submission("SUBMITTED_UNKNOWN", attempt_id, "buy", symbol, amount, price, reason, metadata=metadata, error=str(e))
        result = _base_result(False, "real", "buy", symbol, reason, str(e))
        result.update({"attempt_id": attempt_id, "submission_status": "UNKNOWN", "manual_reconciliation_required": True})
        return result

    result = dict(res or {})
    if result.get("submission_status") == "UNKNOWN":
        result.update(_base_result(False, "real", "buy", symbol, reason, result.get("error") or "Trade submission status unknown"))
        result.update({
            "attempt_id": attempt_id,
            "submission_status": "UNKNOWN",
            "manual_reconciliation_required": True,
            "metadata": metadata or {},
            "risk": risk,
        })
        _record_submission(
            "SUBMITTED_UNKNOWN",
            attempt_id,
            "buy",
            symbol,
            amount,
            price,
            reason,
            metadata=metadata,
            result=result,
        )
        return result
    result.update(_base_result(bool(result.get("success")), "real", "buy", symbol, reason, result.get("error")))
    result["attempt_id"] = attempt_id
    result["submission_status"] = "SUCCESS" if result.get("success") else "FAILED"
    _record_submission(
        "SUBMITTED_SUCCESS" if result.get("success") else "SUBMITTED_FAILED",
        attempt_id,
        "buy",
        symbol,
        amount,
        price,
        reason,
        metadata=metadata,
        result=result,
    )
    result["metadata"] = metadata or {}
    result["risk"] = risk
    return result


def execute_sell(
    symbol,
    coin_amount,
    price,
    reason="",
    metadata=None,
    force_paper: bool = False,
    require_real: bool = False,
    allow_untracked_real_sell: bool = False,
) -> dict:
    position_mode = "paper"
    if isinstance(metadata, dict):
        position_mode = metadata.get("position_mode", position_mode)
    risk = risk_manager.can_execute_sell(symbol, coin_amount, price, reason=reason, position_mode=position_mode)
    if not risk.get("allowed"):
        result = _base_result(False, "blocked", "sell", _clean_symbol(symbol), risk.get("reason", "Risk manager blocked sell"), risk.get("reason"))
        result["risk"] = risk
        result["metadata"] = metadata or {}
        return result

    symbol, amount, price, invalid = _validate_inputs(symbol, coin_amount, price, "sell", reason)
    if invalid:
        return invalid

    mode = _execution_mode(force_paper=force_paper)
    if require_real and mode != "real":
        return _base_result(False, "blocked", "sell", symbol, reason, "Real trade blocked: real position requires real execution gate")
    if mode == "paper":
        received_idr = amount * price
        return {
            **_base_result(True, "paper", "sell", symbol, reason),
            "order_id": "paper",
            "sold_coin": amount,
            "received_idr": received_idr,
            "avg_price": price,
            "metadata": metadata or {},
            "risk": risk,
        }
    if mode == "blocked":
        return _base_result(False, "blocked", "sell", symbol, reason, "Real trade blocked: AUTO_TRADE_ENABLED is false")

    has_position_claim = bool(isinstance(metadata, dict) and metadata.get("sell_attempt_id"))
    has_proposal = bool(isinstance(metadata, dict) and metadata.get("proposal_id"))
    if not has_position_claim:
        if not allow_untracked_real_sell:
            return _base_result(False, "blocked", "sell", symbol, reason, "Real sell blocked: tracked position claim is required")
        if not has_proposal:
            return _base_result(False, "blocked", "sell", symbol, reason, "Untracked real sell blocked: explicit proposal confirmation is required")

    if has_proposal:
        if not _consume_submit_permission("SELL", symbol, amount, price, mode, metadata):
            return _base_result(False, "blocked", "sell", symbol, reason, "Real sell blocked: submit authorization already consumed or invalid")

    if has_position_claim:
        consumed_claim = _consume_position_sell_claim(symbol, amount, price, metadata)
        if not consumed_claim.get("allowed"):
            error = consumed_claim.get("reason", "Tracked position sell claim is invalid")
            return _base_result(False, "blocked", "sell", symbol, reason, f"Real sell blocked: {error}")
        symbol = consumed_claim["symbol"]
        amount = consumed_claim["amount"]
        price = consumed_claim["price"]

    attempt_id = _real_attempt_id(metadata)
    if not _record_submission("PRE_SUBMIT", attempt_id, "sell", symbol, amount, price, reason, metadata=metadata):
        return _base_result(False, "blocked", "sell", symbol, reason, "Real sell blocked: PRE_SUBMIT recovery record failed")
    logger.info(f"Executing REAL SELL {amount} {symbol.upper()} at Rp{price:,.0f}")
    try:
        res = indodax_trade.sell_market(symbol, amount, price)
    except Exception as e:
        logger.error(f"Real sell failed for {symbol.upper()}: {e}")
        _record_submission("SUBMITTED_UNKNOWN", attempt_id, "sell", symbol, amount, price, reason, metadata=metadata, error=str(e))
        result = _base_result(False, "real", "sell", symbol, reason, str(e))
        result.update({"attempt_id": attempt_id, "submission_status": "UNKNOWN", "manual_reconciliation_required": True})
        return result

    result = dict(res or {})
    if result.get("submission_status") == "UNKNOWN":
        result.update(_base_result(False, "real", "sell", symbol, reason, result.get("error") or "Trade submission status unknown"))
        result.update({
            "attempt_id": attempt_id,
            "submission_status": "UNKNOWN",
            "manual_reconciliation_required": True,
            "metadata": metadata or {},
            "risk": risk,
        })
        _record_submission(
            "SUBMITTED_UNKNOWN",
            attempt_id,
            "sell",
            symbol,
            amount,
            price,
            reason,
            metadata=metadata,
            result=result,
        )
        return result
    result.update(_base_result(bool(result.get("success")), "real", "sell", symbol, reason, result.get("error")))
    result["attempt_id"] = attempt_id
    result["submission_status"] = "SUCCESS" if result.get("success") else "FAILED"
    _record_submission(
        "SUBMITTED_SUCCESS" if result.get("success") else "SUBMITTED_FAILED",
        attempt_id,
        "sell",
        symbol,
        amount,
        price,
        reason,
        metadata=metadata,
        result=result,
    )
    result["metadata"] = metadata or {}
    result["risk"] = risk
    return result
