"""Validation gates for strategy DSL definitions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from quant.config import DEFAULT_SYMBOLS
from quant.factors.price.factor_registry import FactorRegistry
from quant.engines.portfolio.portfolio_construction import SUPPORTED_METHODS
from quant.strategy_dsl.strategy_definition import StrategyDefinition


@dataclass(frozen=True)
class StrategyValidationResult:
    strategy_name: str
    strategy_version: str
    valid: bool
    errors: list[str]
    warnings: list[str]
    gates: dict[str, Any]

    def to_report(self) -> dict[str, Any]:
        return {
            "metadata": {"report_type": "strategy_validation"},
            "strategy_name": self.strategy_name,
            "strategy_version": self.strategy_version,
            "valid": self.valid,
            "errors": self.errors,
            "warnings": self.warnings,
            "gates": self.gates,
            "offline_research_only": True,
            "live_trading": False,
            "broker_integration": False,
            "no_lookahead_preserved": True,
        }


class StrategyValidator:
    """Validate strategy schemas without executing quant engines."""

    def __init__(self, factor_registry: FactorRegistry | None = None) -> None:
        self.factor_registry = factor_registry or FactorRegistry()

    def validate(self, definition: StrategyDefinition) -> StrategyValidationResult:
        errors: list[str] = []
        warnings: list[str] = []
        warnings.extend(_unsupported_field_warnings(definition))
        if _contains_lookahead_override(definition.to_dict()):
            errors.append("NO_LOOKAHEAD_OVERRIDE_NOT_ALLOWED")
        if not definition.name:
            errors.append("MISSING_NAME")
        if not definition.description:
            errors.append("MISSING_DESCRIPTION")
        if not definition.version:
            errors.append("MISSING_VERSION")
        if not definition.author:
            errors.append("MISSING_AUTHOR")
        if not definition.created_at:
            errors.append("MISSING_CREATED_AT")
        if not definition.factors:
            errors.append("MISSING_FACTORS")
        factor_names = set(self.factor_registry.factor_names())
        total_weight = 0.0
        for factor in definition.factors:
            name = str(factor.get("name") or "").strip().lower()
            if not name:
                errors.append("FACTOR_MISSING_NAME")
                continue
            if name not in factor_names:
                errors.append(f"UNSUPPORTED_FACTOR: {name}")
            weight = _float(factor.get("weight"), default=1.0)
            if weight is None or weight < 0:
                errors.append(f"INVALID_FACTOR_WEIGHT: {name}")
            else:
                total_weight += weight
        if definition.factors and total_weight <= 0:
            errors.append("FACTOR_WEIGHTS_SUM_TO_ZERO")
        if total_weight > 0 and abs(total_weight - 1.0) > 1e-9:
            warnings.append("WARN_FACTOR_WEIGHTS_NORMALIZED")
        if definition.universe.get("type") not in {None, "default", "custom", "sector", "etf", "large_cap"}:
            errors.append(f"UNSUPPORTED_UNIVERSE_TYPE: {definition.universe.get('type')}")
        if definition.universe.get("type") == "custom" and not definition.symbols:
            errors.append("CUSTOM_UNIVERSE_REQUIRES_SYMBOLS")
        if not definition.symbols and definition.universe.get("type") in {None, "default"}:
            warnings.append(f"WARN_DEFAULT_UNIVERSE_USED: {len(DEFAULT_SYMBOLS)} symbols")
        if definition.portfolio_method not in SUPPORTED_METHODS:
            errors.append(f"UNSUPPORTED_PORTFOLIO_METHOD: {definition.portfolio_method}")
        max_position = _float(definition.portfolio.get("max_position_weight"), default=0.20)
        cash_buffer = _float(definition.portfolio.get("cash_buffer"), default=0.10)
        if max_position is None or not 0 < max_position <= 1:
            errors.append("INVALID_MAX_POSITION_WEIGHT")
        if cash_buffer is None or not 0 <= cash_buffer < 1:
            errors.append("INVALID_CASH_BUFFER")
        if bool(definition.regime.get("enabled")) and not definition.regime.get("preferred_regimes"):
            warnings.append("WARN_REGIME_ENABLED_WITHOUT_PREFERRED_REGIMES")
        if definition.execution.get("live_trading") or definition.execution.get("broker"):
            errors.append("LIVE_TRADING_NOT_SUPPORTED")
        gates = {
            "require_walk_forward": bool(definition.validation.get("require_walk_forward", False)),
            "minimum_ic": _float(definition.validation.get("minimum_ic"), default=None),
            "minimum_coverage": _float(definition.validation.get("minimum_coverage"), default=None),
            "minimum_regime_sample": int(definition.validation.get("minimum_regime_sample", 0) or 0),
            "factor_weight_sum": round(total_weight, 10),
            "normalized_factor_weights": _normalized_weights(definition.factors, total_weight),
        }
        return StrategyValidationResult(
            strategy_name=definition.name,
            strategy_version=definition.version,
            valid=not errors,
            errors=errors,
            warnings=warnings,
            gates=gates,
        )


def _float(value: Any, default: float | None) -> float | None:
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


ALLOWED_TOP_LEVEL = {
    "name",
    "description",
    "version",
    "author",
    "created_at",
    "tags",
    "universe",
    "factors",
    "regime",
    "portfolio",
    "risk",
    "execution",
    "validation",
    "metadata",
}
ALLOWED_UNIVERSE = {"type", "symbols", "sector", "max_symbols"}
ALLOWED_FACTOR = {"name", "weight"}
ALLOWED_REGIME = {"enabled", "adjust_confidence", "preferred_regimes"}
ALLOWED_PORTFOLIO = {"method", "max_position_weight", "cash_buffer"}
ALLOWED_RISK = {"max_drawdown_limit", "max_turnover", "min_factor_confidence"}
ALLOWED_EXECUTION = {"cost_model", "slippage_model", "slippage_bps", "max_adv_participation"}
ALLOWED_VALIDATION = {"require_walk_forward", "minimum_ic", "minimum_coverage", "minimum_regime_sample"}
ALLOWED_METADATA = {"top_n"}


def _unsupported_field_warnings(definition: StrategyDefinition) -> list[str]:
    data = definition.to_dict()
    warnings = _unknown_keys("top_level", data, ALLOWED_TOP_LEVEL)
    warnings.extend(_unknown_keys("universe", definition.universe, ALLOWED_UNIVERSE))
    warnings.extend(_unknown_keys("regime", definition.regime, ALLOWED_REGIME))
    warnings.extend(_unknown_keys("portfolio", definition.portfolio, ALLOWED_PORTFOLIO))
    warnings.extend(_unknown_keys("risk", definition.risk, ALLOWED_RISK))
    warnings.extend(_unknown_keys("execution", definition.execution, ALLOWED_EXECUTION))
    warnings.extend(_unknown_keys("validation", definition.validation, ALLOWED_VALIDATION))
    warnings.extend(_unknown_keys("metadata", definition.metadata, ALLOWED_METADATA))
    for factor in definition.factors:
        warnings.extend(_unknown_keys(f"factor:{factor.get('name', '<unknown>')}", factor, ALLOWED_FACTOR))
    return warnings


def _unknown_keys(section: str, values: dict[str, Any], allowed: set[str]) -> list[str]:
    return [f"WARN_UNSUPPORTED_FIELD: {section}.{key}" for key in sorted(set(values) - allowed)]


def _contains_lookahead_override(value: Any) -> bool:
    if isinstance(value, dict):
        for key, item in value.items():
            normalized = str(key).lower()
            if normalized in {"allow_lookahead", "lookahead"} and bool(item):
                return True
            if normalized in {"no_lookahead", "no_lookahead_preserved"} and item is False:
                return True
            if _contains_lookahead_override(item):
                return True
    if isinstance(value, list):
        return any(_contains_lookahead_override(item) for item in value)
    return False


def _normalized_weights(factors: list[dict[str, Any]], total_weight: float) -> dict[str, float]:
    if total_weight <= 0:
        return {}
    output = {}
    for factor in factors:
        name = str(factor.get("name") or "").strip().lower()
        weight = _float(factor.get("weight"), default=1.0)
        if name and weight is not None and weight >= 0:
            output[name] = round(weight / total_weight, 10)
    return output
