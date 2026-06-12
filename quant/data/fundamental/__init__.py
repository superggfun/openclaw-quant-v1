"""Layered fundamental-data package."""

from quant.utils.module_alias import alias_modules

_ALIASES = {
    "fundamental_importer": "quant.fundamental_data.fundamental_importer",
    "fundamental_models": "quant.fundamental_data.fundamental_models",
    "fundamental_quality": "quant.fundamental_data.fundamental_quality",
    "fundamental_service": "quant.fundamental_data.fundamental_service",
    "fundamental_store": "quant.fundamental_data.fundamental_store",
}

alias_modules(__name__, _ALIASES)
