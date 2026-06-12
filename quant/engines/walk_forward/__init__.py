"""Walk-forward validation engine layered namespace."""

from quant.walk_forward import *  # noqa: F401,F403
from quant.utils.module_alias import alias_modules

alias_modules(
    __name__,
    {
        "rolling_validation": "quant.walk_forward.rolling_validation",
        "walk_forward": "quant.walk_forward.walk_forward",
    },
)
