"""Backward-compatible yfinance market data client."""

from __future__ import annotations

from quant.data.providers.base import PRICE_COLUMNS
from quant.data.providers.yfinance_provider import YFinanceProvider


class YFinanceClient(YFinanceProvider):
    """Compatibility alias for older imports.

    New code should use `quant.data.providers.yfinance_provider.YFinanceProvider`.
    """
