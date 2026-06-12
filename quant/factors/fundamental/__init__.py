"""Layered fundamental-factor package."""

from quant.utils.module_alias import alias_modules

_ALIASES = {
    "factor_registry_extension": "quant.fundamental_factors.factor_registry_extension",
    "financial_health_factors": "quant.fundamental_factors.financial_health_factors",
    "growth_factors": "quant.fundamental_factors.growth_factors",
    "quality_factors": "quant.fundamental_factors.quality_factors",
    "value_factors": "quant.fundamental_factors.value_factors",
}

alias_modules(__name__, _ALIASES)
