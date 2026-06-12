"""Layered alias for Strategy Evaluation Gates."""

from quant.strategy_gates import *  # noqa: F401,F403
from quant.utils.module_alias import alias_modules

alias_modules(
    __name__,
    {
        "gate_models": "quant.strategy_gates.gate_models",
        "gate_runner": "quant.strategy_gates.gate_runner",
        "gate_rules": "quant.strategy_gates.gate_rules",
        "gate_report": "quant.strategy_gates.gate_report",
        "gate_registry": "quant.strategy_gates.gate_registry",
    },
)
