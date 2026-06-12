"""Layered protocol package.

New imports should prefer `quant.core.protocols.*`. The v0.29
`quant.core_protocols.*` modules remain supported.
"""

from quant.utils.module_alias import alias_modules

_ALIASES = {
    "account": "quant.core_protocols.account",
    "fill": "quant.core_protocols.fill",
    "order": "quant.core_protocols.order",
    "portfolio_snapshot": "quant.core_protocols.portfolio_snapshot",
    "position": "quant.core_protocols.position",
    "protocol_validation": "quant.core_protocols.protocol_validation",
    "recommendation": "quant.core_protocols.recommendation",
    "signal": "quant.core_protocols.signal",
    "trade": "quant.core_protocols.trade",
}

alias_modules(__name__, _ALIASES)

