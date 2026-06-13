"""Reusable rule helpers for Strategy Evaluation Gates."""

from __future__ import annotations

import math
from typing import Any

from quant.engines.strategy_gates.gate_models import FAIL, PASS, REJECTED, WARNING, GateResult


def pass_gate(name: str, category: str, message: str, evidence: dict[str, Any] | None = None) -> GateResult:
    return GateResult(name, category, PASS, "PASS", message, evidence or {})


def warn_gate(
    name: str,
    category: str,
    reason_code: str,
    message: str,
    evidence: dict[str, Any] | None = None,
    warnings: list[str] | None = None,
) -> GateResult:
    return GateResult(name, category, WARNING, reason_code, message, evidence or {}, warnings or [reason_code])


def fail_gate(
    name: str,
    category: str,
    reason_code: str,
    message: str,
    evidence: dict[str, Any] | None = None,
    warnings: list[str] | None = None,
) -> GateResult:
    return GateResult(name, category, FAIL, reason_code, message, evidence or {}, warnings or [reason_code])


def reject_gate(
    name: str,
    category: str,
    reason_code: str,
    message: str,
    evidence: dict[str, Any] | None = None,
    rejection_reasons: list[str] | None = None,
) -> GateResult:
    reasons = rejection_reasons or [reason_code]
    return GateResult(name, category, REJECTED, reason_code, message, evidence or {}, reasons, reasons)


def ratio(numerator: float | int | None, denominator: float | int | None) -> float:
    if denominator in {None, 0}:
        return 0.0
    try:
        return float(numerator or 0.0) / float(denominator)
    except (TypeError, ValueError, ZeroDivisionError):
        return 0.0


def finite(value: Any) -> bool:
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def num(value: Any) -> float | None:
    if finite(value):
        return float(value)
    return None
