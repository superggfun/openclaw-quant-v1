from __future__ import annotations

from dataclasses import dataclass

import pytest

from quant.engines.factor_common import (
    compound_return,
    cross_section_correlations,
    hit_rate,
    mean,
    normalize_symbols,
    sharpe,
    std,
)


@dataclass(frozen=True)
class Observation:
    signal_date: str
    symbol: str
    factor_value: float
    future_return: float


def test_factor_common_stats_ignore_missing_values() -> None:
    values = [0.01, None, 0.03]

    assert mean(values) == pytest.approx(0.02)
    assert std(values) is not None
    assert hit_rate(values) == 1.0
    assert compound_return(values) == pytest.approx((1.01 * 1.03) - 1.0)
    assert sharpe([0.01, -0.02, 0.03]) is not None


def test_factor_common_cross_section_correlations() -> None:
    observations = [
        Observation("2024-01-01", "AAA", 1.0, 0.01),
        Observation("2024-01-01", "BBB", 2.0, 0.02),
        Observation("2024-01-02", "AAA", 1.0, 0.03),
        Observation("2024-01-02", "BBB", 2.0, 0.01),
    ]

    ic_values, rank_ic_values = cross_section_correlations(observations)

    assert ic_values == pytest.approx([1.0, -1.0])
    assert rank_ic_values == pytest.approx([1.0, -1.0])


def test_factor_common_normalizes_symbols_without_duplicates() -> None:
    assert normalize_symbols([" spy ", "SPY", "qqq", "", " QQQ "]) == ["SPY", "QQQ"]
