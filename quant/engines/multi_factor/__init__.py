"""Multi-factor engine layered namespace."""

from quant.multi_factor import *  # noqa: F401,F403
from quant.utils.module_alias import alias_modules

alias_modules(
    __name__,
    {
        "factor_combiner": "quant.multi_factor.factor_combiner",
        "factor_stability": "quant.multi_factor.factor_stability",
        "factor_weighting": "quant.multi_factor.factor_weighting",
        "multi_factor_model": "quant.multi_factor.multi_factor_model",
    },
)

