"""Layered factor-store package."""

from quant.utils.module_alias import alias_modules

_ALIASES = {
    "factor_analytics": "quant.factor_store.factor_analytics",
    "factor_history": "quant.factor_store.factor_history",
    "factor_registry_store": "quant.factor_store.factor_registry_store",
    "factor_store": "quant.factor_store.factor_store",
}

alias_modules(__name__, _ALIASES)

