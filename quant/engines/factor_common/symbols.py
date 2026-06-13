"""Shared symbol-list helpers for factor engines."""

from __future__ import annotations

from quant.core.symbols import normalize_symbols


def exclude_symbol(
    symbol: str,
    reason: str,
    excluded_symbols: list[str],
    exclusion_reasons: dict[str, str],
    warnings: list[str],
) -> None:
    excluded_symbols.append(symbol)
    exclusion_reasons[symbol] = reason
    warnings.append(f"excluded {symbol}: {reason}")
