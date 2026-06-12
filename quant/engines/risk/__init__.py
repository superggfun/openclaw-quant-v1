"""Risk engine layered namespace."""

from quant.risk import *  # noqa: F401,F403
from quant.utils.module_alias import alias_modules

alias_modules(__name__, {"risk_engine": "quant.risk.risk_engine"})

