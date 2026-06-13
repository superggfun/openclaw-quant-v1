"""Shared symbol-list helpers for factor engines."""

from __future__ import annotations


def normalize_symbols(symbols: list[str]) -> list[str]:
    normalized = []
    seen = set()
    for symbol in symbols:
        ticker = str(symbol).upper().strip()
        if ticker and ticker not in seen:
            normalized.append(ticker)
            seen.add(ticker)
    return normalized


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
