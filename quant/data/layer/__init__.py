"""Layered data-quality and universe package."""

from quant.utils.module_alias import alias_modules

_ALIASES = {
    "data_quality": "quant.data_layer.data_quality",
    "symbol_metadata": "quant.data_layer.symbol_metadata",
    "universe_manager": "quant.data_layer.universe_manager",
}

alias_modules(__name__, _ALIASES)

