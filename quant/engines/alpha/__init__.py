"""Alpha engine layered namespace."""

from quant.alpha import *  # noqa: F401,F403
from quant.utils.module_alias import alias_modules

alias_modules(__name__, {"alpha_engine": "quant.alpha.alpha_engine"})

