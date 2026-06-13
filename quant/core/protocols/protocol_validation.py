"""Validation helpers for protocol objects."""

from __future__ import annotations

from typing import Any


def validate_protocol_object(obj: Any) -> list[str]:
    validate = getattr(obj, "validate", None)
    if callable(validate):
        return list(validate())
    return ["object does not expose validate()"]


def validate_signal_execution_dates(signal_date: str | None, execution_date: str | None) -> list[str]:
    if signal_date and execution_date and str(signal_date) > str(execution_date):
        return ["signal_date must be on or before execution_date"]
    return []


def validate_fill_references_order(fill: Any, orders: list[Any]) -> list[str]:
    order_ids = {getattr(order, "order_id", None) for order in orders}
    fill_order_id = getattr(fill, "order_id", None)
    if order_ids and fill_order_id not in order_ids:
        return [f"fill {getattr(fill, 'fill_id', '')} references unknown order {fill_order_id}"]
    return []


def reconcile_account(account_state: Any, tolerance: float = 0.02) -> list[str]:
    cash = float(getattr(account_state, "cash", 0.0))
    equity = float(getattr(account_state, "equity", 0.0))
    positions = getattr(account_state, "positions", [])
    market_value = sum(float(getattr(position, "market_value", 0.0)) for position in positions)
    if abs(cash + market_value - equity) > tolerance:
        return ["account reconciliation failed: cash + position market value != equity"]
    return []


def validate_weights(weights: dict[str, float], tolerance: float = 0.02) -> list[str]:
    if not weights:
        return []
    total = sum(float(value) for value in weights.values())
    if abs(total - 1.0) > tolerance:
        return [f"weights sum to {total:.6f}, outside tolerance"]
    if any(float(value) < -tolerance for value in weights.values()):
        return ["weights contain negative values"]
    return []
