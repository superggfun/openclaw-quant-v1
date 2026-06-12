"""Layered data-provider package.

New imports should prefer `quant.data.providers.*`. Existing
`quant.data_providers.*` imports remain supported.
"""

from quant.utils.module_alias import alias_modules

_ALIASES = {
    "base": "quant.data_providers.base",
    "csv_provider": "quant.data_providers.csv_provider",
    "mock_provider": "quant.data_providers.mock_provider",
    "provider_registry": "quant.data_providers.provider_registry",
    "yfinance_provider": "quant.data_providers.yfinance_provider",
}

alias_modules(__name__, _ALIASES)

from quant.data_providers import *  # noqa: F401,F403,E402

