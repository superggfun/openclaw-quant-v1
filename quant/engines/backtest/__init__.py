"""Backtest engine layered namespace."""

from quant.backtest import *  # noqa: F401,F403
from quant.utils.module_alias import alias_modules

alias_modules(__name__, {"backtest_engine": "quant.backtest.backtest_engine"})

