"""Strategy evaluation engine layered namespace."""

from quant.strategy_eval import *  # noqa: F401,F403
from quant.utils.module_alias import alias_modules

alias_modules(__name__, {"strategy_evaluation": "quant.strategy_eval.strategy_evaluation"})

