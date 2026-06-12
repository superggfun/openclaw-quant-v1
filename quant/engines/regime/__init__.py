"""Regime detection engine layered namespace."""

from quant.regime_detection import *  # noqa: F401,F403
from quant.utils.module_alias import alias_modules

alias_modules(
    __name__,
    {
        "market_regime": "quant.regime_detection.market_regime",
        "regime_analytics": "quant.regime_detection.regime_analytics",
        "regime_classification": "quant.regime_detection.regime_classification",
        "regime_detector": "quant.regime_detection.regime_detector",
        "regime_history": "quant.regime_detection.regime_history",
    },
)

