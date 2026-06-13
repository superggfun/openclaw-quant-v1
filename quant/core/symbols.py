"""Shared symbol normalization helpers."""

from __future__ import annotations

from collections.abc import Iterable


def normalize_symbols(
    symbols: Iterable[object],
    *,
    exclude: set[str] | frozenset[str] | None = None,
    require_non_empty: bool = False,
    empty_message: str = "at least one symbol is required",
) -> list[str]:
    excluded = {symbol.upper().strip() for symbol in (exclude or set())}
    normalized: list[str] = []
    seen: set[str] = set()
    for symbol in symbols:
        ticker = str(symbol).upper().strip()
        if ticker and ticker not in seen and ticker not in excluded:
            normalized.append(ticker)
            seen.add(ticker)
    if require_non_empty and not normalized:
        raise ValueError(empty_message)
    return normalized
