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
