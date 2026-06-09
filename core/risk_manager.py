import os
from typing import Any, Optional

from core.applog import get_logger
from core.persistence import read_json_safe

logger = get_logger("risk_manager")

DEFAULTS = {
    "MAX_DAILY_LOSS_PCT": 3.0,
    "MAX_OPEN_POSITIONS": 3,
    "MAX_ALLOCATION_PER_COIN_PCT": 10.0,
    "MAX_TOTAL_EXPOSURE_PCT": 30.0,
    "MAX_CONSECUTIVE_LOSSES": 3,
    "KILL_SWITCH": False,
    "RISK_OFF_MODE": False,
}


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


def env_float(name: str, default: float) -> float:
    try:
        value = float(str(os.environ.get(name, str(default))).strip())
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default


def _risk_override_path() -> str:
    override = os.environ.get("RISK_OVERRIDE_FILE")
    if override:
        return override
    try:
        if os.path.isdir("/data") and os.access("/data", os.W_OK):
            return os.path.join("/data", "risk_override.json")
    except OSError:
        pass
    return "risk_override.json"


def _load_risk_override() -> dict:
    path = _risk_override_path()
    data = read_json_safe(
        path,
        {},
        fail_closed_default={"kill_switch": True, "_corrupted": True},
    )
    if not isinstance(data, dict):
        logger.error("Risk override is not a JSON object; activating runtime kill fail-closed.")
        return {"kill_switch": True, "_corrupted": True}
    if data.get("_corrupted"):
        logger.warning("Risk override is corrupted; runtime kill is active fail-closed.")
    return data


def get_risk_config() -> dict:
    env_kill_switch = env_bool("KILL_SWITCH", DEFAULTS["KILL_SWITCH"])
    config = {
        "max_daily_loss_pct": env_float("MAX_DAILY_LOSS_PCT", DEFAULTS["MAX_DAILY_LOSS_PCT"]),
        "max_open_positions": env_int("MAX_OPEN_POSITIONS", DEFAULTS["MAX_OPEN_POSITIONS"]),
        "max_allocation_per_coin_pct": env_float(
            "MAX_ALLOCATION_PER_COIN_PCT",
            DEFAULTS["MAX_ALLOCATION_PER_COIN_PCT"],
        ),
        "max_total_exposure_pct": env_float("MAX_TOTAL_EXPOSURE_PCT", DEFAULTS["MAX_TOTAL_EXPOSURE_PCT"]),
        "max_consecutive_losses": env_int("MAX_CONSECUTIVE_LOSSES", DEFAULTS["MAX_CONSECUTIVE_LOSSES"]),
        "kill_switch": env_kill_switch,
        "risk_off_mode": env_bool("RISK_OFF_MODE", DEFAULTS["RISK_OFF_MODE"]),
        "risk_override_corrupted": False,
    }
    override = _load_risk_override()
    if override.get("_corrupted"):
        config["risk_override_corrupted"] = True
        config["kill_switch"] = True
    if isinstance(override.get("kill_switch"), bool):
        config["kill_switch"] = env_kill_switch or override["kill_switch"]
    if isinstance(override.get("risk_off_mode"), bool):
        config["risk_off_mode"] = override["risk_off_mode"]
    return config


def _result(allowed: bool, reason: str, risk_level: str, checks: Optional[dict] = None) -> dict:
    return {
        "allowed": allowed,
        "reason": reason,
        "risk_level": risk_level,
        "checks": checks or {},
    }


def _positive_float(value: Any):
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _float_value(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _first_number(data: Optional[dict], keys: tuple, default: float = 0.0) -> float:
    if not isinstance(data, dict):
        return default
    for key in keys:
        if key in data:
            return _float_value(data.get(key), default)
    return default


def _symbol(value: Any) -> str:
    return str(value or "").strip().lower()


def _position_rows(portfolio_state=None) -> list[tuple[str, dict]]:
    if not portfolio_state:
        return []

    rows = []
    if isinstance(portfolio_state, dict):
        raw_positions = portfolio_state.get("positions", portfolio_state)
        if isinstance(raw_positions, dict):
            for key, pos in raw_positions.items():
                if isinstance(pos, dict):
                    rows.append((_symbol(pos.get("symbol", key)), pos))
        elif isinstance(raw_positions, list):
            for pos in raw_positions:
                if isinstance(pos, dict):
                    rows.append((_symbol(pos.get("symbol")), pos))
    elif isinstance(portfolio_state, list):
        for pos in portfolio_state:
            if isinstance(pos, dict):
                rows.append((_symbol(pos.get("symbol")), pos))

    return [(sym, pos) for sym, pos in rows if sym]


def _position_value_idr(pos: dict) -> float:
    for key in ("value_idr", "exposure_idr", "market_value_idr", "invested_idr", "cost_idr", "spent_idr"):
        if key in pos:
            return max(0.0, _float_value(pos.get(key)))

    qty = _first_number(pos, ("amount_coin", "qty", "quantity", "coin_amount"), 0.0)
    price = _first_number(pos, ("buy_price", "avg_buy_price", "avg_price", "price", "current_price"), 0.0)
    return max(0.0, qty * price)


def _open_positions(portfolio_state=None) -> list[tuple[str, dict]]:
    rows = []
    for sym, pos in _position_rows(portfolio_state):
        status = str(pos.get("status", "OPEN")).strip().upper()
        if status not in {"CLOSED", "SOLD", "CANCELLED", "CANCELED"}:
            rows.append((sym, pos))
    return rows


def _capital_idr(portfolio_state=None, total_capital_idr=None):
    parsed = _positive_float(total_capital_idr)
    if parsed is not None:
        return parsed
    if isinstance(portfolio_state, dict):
        for key in ("total_capital_idr", "capital_idr", "equity_idr", "portfolio_capital_idr"):
            parsed = _positive_float(portfolio_state.get(key))
            if parsed is not None:
                return parsed
    return None


def _estimated_capital_from_portfolio(portfolio_state=None):
    if not isinstance(portfolio_state, dict):
        return None

    cash = None
    for key in ("cash_idr", "available_idr", "available_cash_idr", "idr_balance", "free_idr"):
        parsed = _positive_float(portfolio_state.get(key))
        if parsed is not None:
            cash = parsed
            break
    if cash is None:
        return None

    positions = _open_positions(portfolio_state)
    exposure = sum(_position_value_idr(pos) for _, pos in positions)
    estimate = cash + exposure
    return estimate if estimate > 0 else None


def build_risk_context(
    portfolio_state=None,
    daily_stats=None,
    total_capital_idr=None,
    metadata=None,
) -> dict:
    metadata = metadata if isinstance(metadata, dict) else {}

    nested = metadata.get("risk_context") if isinstance(metadata.get("risk_context"), dict) else {}
    context = dict(nested)

    def choose(key, fallback=None):
        if key in metadata:
            return metadata.get(key)
        if fallback is not None:
            return fallback
        return context.get(key)

    context["portfolio_state"] = choose("portfolio_state", portfolio_state)
    context["daily_stats"] = choose("daily_stats", daily_stats)
    context["market_state"] = choose("market_state")
    context["risk_tag"] = choose("risk_tag")

    capital_sources = []
    if "total_capital_idr" in metadata:
        capital_sources.append(metadata.get("total_capital_idr"))
    if total_capital_idr is not None:
        capital_sources.append(total_capital_idr)
    if "total_capital_idr" in context:
        capital_sources.append(context.get("total_capital_idr"))

    capital = None
    for source in capital_sources:
        capital = _positive_float(source)
        if capital is not None:
            break
    if capital is None:
        capital = _positive_float(os.environ.get("TOTAL_CAPITAL_IDR"))
    if capital is None:
        capital = _capital_idr(context.get("portfolio_state"))
    if capital is None:
        capital = _estimated_capital_from_portfolio(context.get("portfolio_state"))
    context["total_capital_idr"] = capital
    context["total_capital_available"] = capital is not None
    return context


def _daily_loss_pct(daily_stats=None) -> float:
    if not isinstance(daily_stats, dict):
        return 0.0
    direct = _first_number(daily_stats, ("daily_loss_pct", "loss_pct", "realized_loss_pct"), None)
    if direct is not None:
        return max(0.0, direct)
    pnl = _first_number(daily_stats, ("daily_pnl_pct", "pnl_pct", "profit_pct"), 0.0)
    return abs(pnl) if pnl < 0 else 0.0


def _consecutive_losses(daily_stats=None) -> int:
    if not isinstance(daily_stats, dict):
        return 0
    return max(0, int(_first_number(daily_stats, ("consecutive_losses", "loss_streak", "daily_loss_streak"), 0)))


def _risk_tag_value(risk_tag=None, market_state=None) -> str:
    if risk_tag is not None:
        return str(risk_tag).strip().lower()
    if isinstance(market_state, dict):
        for key in ("risk_tag", "risk_level", "mode", "regime"):
            if market_state.get(key) is not None:
                return str(market_state.get(key)).strip().lower()
    return ""


def _is_aggressive_or_high_risk(tag: str) -> bool:
    tag = str(tag or "").lower()
    tokens = ("aggressive", "agresif", "high", "high-risk", "tinggi", "risk_high", "micin")
    return any(token in tag for token in tokens)


def _risk_level_from_exposure(total_pct: Optional[float], max_total_pct: float) -> str:
    if total_pct is None or max_total_pct <= 0:
        return "LOW"
    ratio = total_pct / max_total_pct
    if ratio >= 0.85:
        return "HIGH"
    if ratio >= 0.55:
        return "MEDIUM"
    return "LOW"


def can_open_position(
    symbol,
    proposed_idr,
    portfolio_state=None,
    daily_stats=None,
    market_state=None,
    total_capital_idr=None,
    risk_tag=None,
) -> dict:
    config = get_risk_config()
    clean_symbol = _symbol(symbol)
    proposed = _positive_float(proposed_idr)
    context = build_risk_context(
        portfolio_state=portfolio_state,
        daily_stats=daily_stats,
        total_capital_idr=total_capital_idr,
        metadata={"market_state": market_state, "risk_tag": risk_tag},
    )
    portfolio_state = context["portfolio_state"]
    daily_stats = context["daily_stats"]
    market_state = context["market_state"]
    risk_tag = context["risk_tag"]
    positions = _open_positions(portfolio_state)
    capital = _capital_idr(portfolio_state, context.get("total_capital_idr"))
    daily_loss = _daily_loss_pct(daily_stats)
    consecutive_losses = _consecutive_losses(daily_stats)
    tag = _risk_tag_value(risk_tag, market_state)

    exposure_now = sum(_position_value_idr(pos) for _, pos in positions)
    coin_now = sum(_position_value_idr(pos) for sym, pos in positions if sym == clean_symbol)
    exposure_after = exposure_now + (proposed or 0.0)
    coin_after = coin_now + (proposed or 0.0)
    coin_pct = (coin_after / capital * 100) if capital else None
    exposure_pct = (exposure_after / capital * 100) if capital else None

    checks = {
        "config": config,
        "symbol": clean_symbol,
        "proposed_idr": proposed_idr,
        "open_positions": len(positions),
        "open_positions_count": len(positions),
        "daily_loss_pct": daily_loss,
        "consecutive_losses": consecutive_losses,
        "risk_tag": tag,
        "total_capital_idr": capital,
        "total_capital_available": context.get("total_capital_available", capital is not None),
        "current_exposure_idr": exposure_now,
        "proposed_exposure_idr": proposed or 0.0,
        "coin_exposure_after_idr": coin_after,
        "coin_exposure_after_pct": coin_pct,
        "symbol_allocation_pct": coin_pct,
        "total_exposure_after_idr": exposure_after,
        "total_exposure_after_pct": exposure_pct,
        "exposure_pct": exposure_pct,
    }

    def blocked(reason: str):
        return _result(False, reason, "BLOCKED", checks)

    if config["kill_switch"]:
        return blocked("KILL_SWITCH is active")
    if config["risk_off_mode"] and _is_aggressive_or_high_risk(tag):
        return blocked("RISK_OFF_MODE blocks aggressive/high-risk buy")
    if not clean_symbol:
        return blocked("Invalid symbol")
    if proposed is None:
        return blocked("Invalid proposed_idr")
    if len(positions) >= config["max_open_positions"]:
        return blocked("MAX_OPEN_POSITIONS reached")
    if daily_loss >= config["max_daily_loss_pct"]:
        return blocked("MAX_DAILY_LOSS_PCT reached")
    if consecutive_losses >= config["max_consecutive_losses"]:
        return blocked("MAX_CONSECUTIVE_LOSSES reached")
    if coin_pct is not None and coin_pct > config["max_allocation_per_coin_pct"]:
        return blocked("MAX_ALLOCATION_PER_COIN_PCT exceeded")
    if exposure_pct is not None and exposure_pct > config["max_total_exposure_pct"]:
        return blocked("MAX_TOTAL_EXPOSURE_PCT exceeded")

    risk_level = _risk_level_from_exposure(exposure_pct, config["max_total_exposure_pct"])
    return _result(True, "Risk checks passed", risk_level, checks)


def can_execute_sell(symbol, amount, price, reason="", position_mode="paper") -> dict:
    clean_symbol = _symbol(symbol)
    parsed_amount = _positive_float(amount)
    parsed_price = _positive_float(price)
    checks = {
        "symbol": clean_symbol,
        "amount": amount,
        "price": price,
        "reason": reason,
        "position_mode": str(position_mode or "paper").strip().lower(),
        "kill_switch_ignored_for_sell": get_risk_config()["kill_switch"],
    }
    if not clean_symbol:
        return _result(False, "Invalid symbol", "BLOCKED", checks)
    if parsed_amount is None:
        return _result(False, "Invalid amount", "BLOCKED", checks)
    if parsed_price is None:
        return _result(False, "Invalid price", "BLOCKED", checks)
    return _result(True, "Sell allowed: reducing risk", "LOW", checks)


def get_risk_status(portfolio_state=None, daily_stats=None) -> dict:
    config = get_risk_config()
    positions = _open_positions(portfolio_state)
    capital = _capital_idr(portfolio_state)
    exposure_now = sum(_position_value_idr(pos) for _, pos in positions)
    exposure_pct = (exposure_now / capital * 100) if capital else None
    daily_loss = _daily_loss_pct(daily_stats)
    consecutive_losses = _consecutive_losses(daily_stats)
    blocked = (
        config["kill_switch"]
        or daily_loss >= config["max_daily_loss_pct"]
        or consecutive_losses >= config["max_consecutive_losses"]
        or len(positions) >= config["max_open_positions"]
        or (exposure_pct is not None and exposure_pct >= config["max_total_exposure_pct"])
    )
    return {
        "status": "BLOCKED" if blocked else "OK",
        "risk_level": "BLOCKED" if blocked else _risk_level_from_exposure(exposure_pct, config["max_total_exposure_pct"]),
        "config": config,
        "open_positions": len(positions),
        "daily_loss_pct": daily_loss,
        "consecutive_losses": consecutive_losses,
        "total_exposure_idr": exposure_now,
        "total_exposure_pct": exposure_pct,
    }
