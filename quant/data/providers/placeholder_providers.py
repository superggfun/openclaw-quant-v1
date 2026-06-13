"""Placeholder provider specs for future integrations."""

from __future__ import annotations

from quant.data.providers.base import PlaceholderProvider
from quant.data.providers.provider_specs import ProviderSpec


_PLACEHOLDERS = {
    "akshare": "Future AkShare daily data provider placeholder",
    "tushare": "Future Tushare daily data provider placeholder",
    "alpha_vantage": "Future Alpha Vantage daily data provider placeholder",
    "polygon": "Future Polygon.io daily data provider placeholder",
}


PROVIDER_SPECS = tuple(
    ProviderSpec(name, lambda name=name, description=description: PlaceholderProvider(name, description))
    for name, description in _PLACEHOLDERS.items()
)
