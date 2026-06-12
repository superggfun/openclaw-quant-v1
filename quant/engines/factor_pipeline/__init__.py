"""Factor preprocessing pipeline layered namespace."""

from quant.factor_pipeline import *  # noqa: F401,F403
from quant.utils.module_alias import alias_modules

alias_modules(__name__, {"factor_pipeline": "quant.factor_pipeline.factor_pipeline"})

