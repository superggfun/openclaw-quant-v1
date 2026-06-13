"""Research validation recommendation rules."""

from __future__ import annotations

from collections import Counter
from typing import Any


def recommendations(warnings: Counter[str], strategies: list[dict[str, Any]]) -> list[str]:
    output = []
    if any(code in warnings for code in ("WARN_LOW_FACTOR_COVERAGE", "PARTIAL_FUNDAMENTAL_DATA")):
        output.append("Improve factor and fundamental coverage before relying on accounting-heavy strategies.")
    if warnings.get("WARN_LOW_WALK_FORWARD_FOLDS"):
        output.append("Persist more walk-forward evidence for candidate factors and strategies.")
    if warnings.get("WARN_LOW_REGIME_SAMPLE"):
        output.append("Extend regime history and factor-by-regime samples before regime-aware decisions.")
    if warnings.get("SLOW_STEP"):
        output.append("Prioritize semantic-preserving cache work for slow validation steps.")
    if not any(row.get("gate_status") == "PASS" for row in strategies):
        output.append("Keep current DSL strategies in research candidate status until gates pass without warnings.")
    output.append("Do not tune parameters from this sprint; use evidence to prioritize data and validation improvements.")
    return output
