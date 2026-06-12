"""Layered price-factor package."""

from quant.utils.module_alias import alias_modules

_ALIASES = {
    "factor_registry": "quant.factors.factor_registry",
    "growth_factors": "quant.factors.growth_factors",
    "low_volatility_factors": "quant.factors.low_volatility_factors",
    "quality_factors": "quant.factors.quality_factors",
    "reversal_factors": "quant.factors.reversal_factors",
    "value_factors": "quant.factors.value_factors",
}

alias_modules(__name__, _ALIASES)

