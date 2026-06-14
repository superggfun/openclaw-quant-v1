"""Shared helpers for fundamental factor computations.

Extracted from duplicated `_num()` and `_mean_available()` definitions
across value, quality, growth, and financial_health factor modules.
"""

from __future__ import annotations

import math
from typing import Any


def safe_num(value: Any) -> float | None:
    """Convert *value* to float, rejecting None, NaN, Inf, and non-numeric types.

    All fundamental factor modules should use this instead of inline ``float(value)``
    so that bad data from yfinance / financial APIs never leaks into composites.
    """
    try:
        if value is None:
            return None
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return number


def mean_available(values: list[float | None], min_count: int = 1) -> float | None:
    """Arithmetic mean of non-None values.

    Returns None when fewer than *min_count* values are available.  Use
    ``min_count=2`` (or higher) in composites so a stock with only one
    lucky data point doesn't get an inflated score.
    """
    clean = [v for v in values if v is not None]
    if len(clean) < min_count:
        return None
    return sum(clean) / len(clean)

def clip_value(value: float | None, low: float, high: float) -> float | None:
    """Clip *value* to [low, high].  Returns None if input is None."""
    if value is None:
        return None
    return max(low, min(high, value))
