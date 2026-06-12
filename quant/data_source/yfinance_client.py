"""Backward-compatible yfinance market data client."""

from __future__ import annotations

from quant.data_providers.base import PRICE_COLUMNS
from quant.data_providers.yfinance_provider import YFinanceProvider


class YFinanceClient(YFinanceProvider):
    """Compatibility alias for older imports.

    New code should use `quant.data_providers.yfinance_provider.YFinanceProvider`.
    """
