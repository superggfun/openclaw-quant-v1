"""Factor evaluation engine layered namespace."""

from quant.factor_eval import *  # noqa: F401,F403
from quant.utils.module_alias import alias_modules

alias_modules(__name__, {"factor_evaluation": "quant.factor_eval.factor_evaluation"})

