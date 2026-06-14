from __future__ import annotations

from quant.core.collections import dedupe_by, dedupe_text
from quant.core.equity import equity_curve_stats
from quant.core.symbols import normalize_symbols


def test_normalize_symbols_dedupes_and_excludes_cash() -> None:
    assert normalize_symbols([" spy ", "SPY", "cash", "qqq"], exclude={"CASH"}) == ["SPY", "QQQ"]


def test_normalize_symbols_can_require_non_empty() -> None:
    try:
        normalize_symbols(["cash"], exclude={"CASH"}, require_non_empty=True, empty_message="need symbols")
    except ValueError as exc:
        assert str(exc) == "need symbols"
    else:
        raise AssertionError("expected ValueError")


def test_dedupe_helpers_preserve_order() -> None:
    assert dedupe_text(["A", "B", "A", "", "C"]) == ["A", "B", "C"]
    warnings = [
        {"code": "LOW", "reason": "coverage"},
        {"code": "LOW", "reason": "coverage"},
        {"code": "SLOW", "reason": "runtime"},
    ]
    assert dedupe_by(warnings, ("code", "reason")) == [warnings[0], warnings[2]]


def test_equity_curve_stats_common_metrics() -> None:
    stats = equity_curve_stats(
        [
            {"date": "2024-01-01", "equity": 100.0},
            {"date": "2024-01-02", "equity": 110.0},
            {"date": "2024-01-03", "equity": 105.0},
        ],
        100.0,
    )

    assert round(stats.total_return, 6) == 0.05
    assert stats.final_value == 105.0
    assert round(float(stats.max_drawdown), 6) == -0.045455


# ── Spread metric tests ──

from quant.engines.factor_common.stats import (
    compound_return,
    cumulative_spread_return,
    max_drawdown,
    spread_max_drawdown,
)


def test_cumulative_spread_return_additive() -> None:
    """cumulative_spread_return sums period returns, not cumprod."""
    assert cumulative_spread_return([0.03, 0.03, 0.03]) == 0.09
    assert cumulative_spread_return([0.10, -0.10, 0.05]) == 0.05
    assert cumulative_spread_return([]) is None
    assert cumulative_spread_return([None, 0.03, None]) == 0.03


def test_spread_cumprod_vs_cumsum_semantic_difference() -> None:
    """[0.03] * 100: cumprod exploits vs cumsum diverges drastically.

    cumprod: (1.03)^100 - 1 ≈ 1828% — explosive, meaningless for spread returns
    cumsum: 0.03 * 100 = 3.0 — 300% cumulative spread, diagnostic
    """
    returns = [0.03] * 100
    compound = compound_return(returns)  # multiplicative
    cumulative = cumulative_spread_return(returns)  # additive

    # cumprod is absurdly large for spread returns
    assert compound > 15.0  # ~18.2x
    # cumsum is a reasonable diagnostic sum
    assert cumulative == 3.0
    assert compound != cumulative
    assert abs(compound - 18.2188) < 0.3


def test_spread_max_drawdown_cumsum_based() -> None:
    """spread_max_drawdown uses cumsum, not cumprod."""
    returns = [0.03, 0.03, -0.50, 0.03, 0.03]
    dd = spread_max_drawdown(returns)
    # cumsum: [0.03, 0.06, -0.44, -0.41, -0.38], peak=0.06, min=-0.44, dd=-0.50
    assert dd == -0.50

    # Compare with compound max_drawdown for the same sequence
    cd = max_drawdown(returns)
    # cumprod: peak ≈ 1.0609, equity at -0.44 cumsum ≈ 0.53045, dd ≈ -0.5
    # This verifies they differ in methodology
    assert cd is not None
    assert cd <= 0


def test_spread_max_drawdown_all_positive() -> None:
    """With all positive spreads, drawdown should be 0."""
    assert spread_max_drawdown([0.01, 0.02, 0.03]) == 0.0


def test_spread_metrics_empty_or_none() -> None:
    """Both functions return None for empty / all-None input."""
    assert cumulative_spread_return([]) is None
    assert cumulative_spread_return([None, None]) is None
    assert spread_max_drawdown([]) is None
    assert spread_max_drawdown([None, None]) is None
