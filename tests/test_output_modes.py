"""Tests for output_modes scoring, enums, and result dataclass output methods."""

import json
import pytest

from quant.engines.output_modes import (
    FactorStatus,
    OutputMode,
    score_factor,
)
from quant.engines.factor_eval.factor_evaluation import (
    FactorEvaluationResult,
    FactorObservation,
)
from quant.engines.factor_backtest.factor_backtest import (
    FactorBacktestResult,
    FactorBacktestObservation,
    FactorBacktestPeriod,
)


# ── Fixtures ──

@pytest.fixture
def mock_eval_result() -> dict:
    """Return a realistic factor evaluation result dict."""
    return {
        "ic_mean": 0.035,
        "icir": 0.6,
        "ic_positive_rate": 0.58,
        "rank_ic_mean": 0.032,
        "observation_count": 600,
        "warnings": [],
        "performance_metadata": {"fallback_used": False},
    }


@pytest.fixture
def mock_backtest_result() -> dict:
    """Return a realistic factor backtest result dict."""
    return {
        "cumulative_forward_spread": 0.15,
        "mean_forward_spread": 0.005,
        "spread_sharpe_like": 0.9,
        "spread_max_drawdown": -0.12,
        "forward_spread_hit_rate": 0.55,
        "turnover": 0.25,
    }


@pytest.fixture
def mock_eval_dataclass() -> FactorEvaluationResult:
    """Construct a FactorEvaluationResult with synthetic observations."""
    obs = [
        FactorObservation(
            signal_date="2023-01-03",
            future_date="2023-02-01",
            symbol="AAPL",
            factor_value=1.23,
            future_return=0.02,
            forward_days=20,
        ),
        FactorObservation(
            signal_date="2023-01-04",
            future_date="2023-02-02",
            symbol="MSFT",
            factor_value=0.87,
            future_return=-0.01,
            forward_days=20,
        ),
        FactorObservation(
            signal_date="2023-01-05",
            future_date="2023-02-03",
            symbol="GOOGL",
            factor_value=-0.45,
            future_return=0.03,
            forward_days=20,
        ),
    ]
    return FactorEvaluationResult(
        factor="momentum_20d",
        start_date="2023-01-01",
        end_date="2023-12-31",
        forward_days=20,
        universe=["AAPL", "MSFT", "GOOGL"],
        no_lookahead=True,
        ic_mean=0.035,
        ic_std=0.08,
        ic_positive_rate=0.58,
        ic_count=220,
        rank_ic_mean=0.032,
        rank_ic_std=0.075,
        rank_ic_positive_rate=0.56,
        rank_ic_count=220,
        icir=0.6,
        quintiles={"q1": -0.01, "q2": 0.0, "q3": 0.005, "q4": 0.01, "q5": 0.025},
        spread_return=0.035,
        decay={"1d": {"ic": 0.035, "rank_ic": 0.032, "ic_count": 220, "rank_ic_count": 220}},
        half_life_days=45.2,
        observations=obs,
        excluded_symbols=[],
        exclusion_reasons={},
        factor_family="momentum",
        factor_type="price",
        factor_category="trend",
        factor_description="20-day price momentum",
        factor_inputs=["close"],
        factor_higher_is_better=True,
        factor_no_lookahead=True,
        factor_coverage={"AAPL": 1.0, "MSFT": 1.0, "GOOGL": 1.0},
        warnings=[],
        pipeline_config=None,
        report_path="",
    )


@pytest.fixture
def mock_backtest_period() -> FactorBacktestPeriod:
    """Return a single FactorBacktestPeriod."""
    return FactorBacktestPeriod(
        signal_date="2023-01-03",
        future_date="2023-02-01",
        long_symbols=["AAPL", "GOOGL"],
        short_symbols=["MSFT"],
        long_weights={"AAPL": 0.5, "GOOGL": 0.5},
        short_weights={"MSFT": -1.0},
        long_weight_sum=1.0,
        short_weight_sum=-1.0,
        net_exposure=0.0,
        gross_exposure=2.0,
        quantile_returns={"q1": -0.02, "q2": 0.0, "q3": 0.005, "q4": 0.01, "q5": 0.03},
        long_return=0.025,
        short_return=-0.015,
        long_short_return=0.04,
        turnover=0.12,
    )


@pytest.fixture
def mock_backtest_dataclass(
    mock_backtest_period: FactorBacktestPeriod,
) -> FactorBacktestResult:
    """Construct a FactorBacktestResult with a single period."""
    return FactorBacktestResult(
        factor="momentum_20d",
        start_date="2023-01-01",
        end_date="2023-12-31",
        holding_period=20,
        quantiles=5,
        long_quantile=5,
        short_quantile=1,
        observations=300,
        rebalance_dates=["2023-01-03"],
        quantile_returns={"q1": -0.02, "q2": 0.0, "q3": 0.005, "q4": 0.01, "q5": 0.03},
        top_quantile_return=0.03,
        bottom_quantile_return=-0.02,
        long_symbols_by_date={"2023-01-03": ["AAPL", "GOOGL"]},
        short_symbols_by_date={"2023-01-03": ["MSFT"]},
        long_leg_return=0.025,
        short_leg_return=-0.015,
        long_short_return=0.04,
        annual_return=0.12,
        long_short_annual_return=0.12,
        volatility=0.18,
        long_short_volatility=0.18,
        sharpe=0.67,
        long_short_sharpe=0.67,
        max_drawdown=-0.10,
        hit_rate=0.55,
        turnover=0.25,
        gross_exposure=2.0,
        net_exposure=0.0,
        ic_mean=0.035,
        rank_ic_mean=0.032,
        icir=0.6,
        ic_count=220,
        factor_family="momentum",
        factor_type="price",
        factor_category="trend",
        factor_description="20-day price momentum",
        factor_inputs=["close"],
        factor_higher_is_better=True,
        factor_no_lookahead=True,
        factor_coverage={"AAPL": 1.0, "MSFT": 1.0},
        excluded_symbols=[],
        exclusion_reasons={},
        no_lookahead=True,
        signal_execution_lag="T+20",
        pipeline_enabled=False,
        pipeline_config_path=None,
        pipeline_config=None,
        periods=[mock_backtest_period],
        warnings=[],
        report_path="",
    )


# ── score_factor() tests ──


class TestScoreFactor:
    """Tests for score_factor() function."""

    def test_valid_inputs_returns_expected_range(
        self,
        mock_eval_result: dict,
        mock_backtest_result: dict,
    ) -> None:
        """score_factor() with valid inputs returns a score in 0-100."""
        result = score_factor(mock_eval_result, mock_backtest_result)
        assert "score" in result
        assert "status" in result
        assert "reason" in result
        assert 0.0 <= result["score"] <= 100.0
        assert result["status"] in {"PASS", "WATCH", "REJECT", "ERROR"}

    def test_empty_inputs_returns_zero_with_error(
        self,
    ) -> None:
        """score_factor() with empty dicts still returns a dict (no crash)."""
        result = score_factor({}, {})
        assert "score" in result
        assert "status" in result
        # With no IC or returns, score should be low and likely REJECT
        assert isinstance(result["score"], (int, float))
        assert result["status"] in {"PASS", "WATCH", "REJECT", "ERROR"}

    def test_all_none_inputs(self) -> None:
        """score_factor() with all-None values handles gracefully."""
        eval_result = {
            "ic_mean": None,
            "icir": None,
            "observation_count": 0,
            "warnings": None,
        }
        backtest_result = {
            "cumulative_forward_spread": None,
            "mean_forward_spread": None,
            "spread_max_drawdown": None,
            "forward_spread_hit_rate": None,
            "turnover": None,
        }
        result = score_factor(eval_result, backtest_result)
        assert "score" in result
        assert result["score"] <= 15.0  # Risk starts at 50 * 0.20 = 10, quality starts at 60 * 0.10 = 6

    def test_strong_factor_passes(self) -> None:
        """A strong factor should get PASS status."""
        eval_result = {
            "ic_mean": 0.06,
            "icir": 0.8,
            "ic_positive_rate": 0.65,
            "rank_ic_mean": 0.055,
            "observation_count": 800,
            "warnings": [],
            "performance_metadata": {"fallback_used": False},
        }
        backtest_result = {
            "cumulative_forward_spread": 0.40,
            "mean_forward_spread": 0.015,
            "spread_sharpe_like": 1.8,
            "spread_max_drawdown": -0.08,
            "forward_spread_hit_rate": 0.62,
            "turnover": 0.15,
        }
        result = score_factor(eval_result, backtest_result)
        assert result["status"] == "PASS"
        assert result["score"] >= 70

    def test_weak_factor_rejects(self) -> None:
        """A weak factor should get REJECT status."""
        result = score_factor({}, {})
        assert result["status"] in {"REJECT", "ERROR"}


# ── Enum tests ──


class TestEnums:
    """Tests for OutputMode and FactorStatus enums."""

    def test_output_mode_values(self) -> None:
        """OutputMode has expected values."""
        assert OutputMode.COMPACT.value == "compact"
        assert OutputMode.FULL.value == "full"
        assert OutputMode.ARCHIVE.value == "archive"
        assert len(OutputMode) == 3

    def test_factor_status_values(self) -> None:
        """FactorStatus has expected values."""
        assert FactorStatus.PASS.value == "PASS"
        assert FactorStatus.WATCH.value == "WATCH"
        assert FactorStatus.REJECT.value == "REJECT"
        assert FactorStatus.ERROR.value == "ERROR"
        assert len(FactorStatus) == 4

    def test_output_mode_is_str_enum(self) -> None:
        """OutputMode values are strings (str Enum)."""
        for member in OutputMode:
            assert isinstance(member.value, str)

    def test_factor_status_is_str_enum(self) -> None:
        """FactorStatus values are strings (str Enum)."""
        for member in FactorStatus:
            assert isinstance(member.value, str)


# ── FactorEvaluationResult output mode tests ──


class TestFactorEvaluationResultOutputModes:
    """Tests for FactorEvaluationResult output methods."""

    def test_to_summary_excludes_observations_by_default(
        self,
        mock_eval_dataclass: FactorEvaluationResult,
    ) -> None:
        """to_summary() does NOT include observations by default."""
        summary = mock_eval_dataclass.to_summary()
        assert "observations" not in summary
        assert "factor" in summary
        assert "ic_mean" in summary
        assert "observations_count" in summary
        assert summary["observations_count"] == 3

    def test_to_summary_includes_observations_when_requested(
        self,
        mock_eval_dataclass: FactorEvaluationResult,
    ) -> None:
        """to_summary(include_observations=True) DOES include observations."""
        summary = mock_eval_dataclass.to_summary(include_observations=True)
        assert "observations" in summary
        assert len(summary["observations"]) == 3
        # Check observation structure
        obs0 = summary["observations"][0]
        assert "signal_date" in obs0
        assert "future_date" in obs0
        assert "symbol" in obs0
        assert "factor_value" in obs0
        assert "future_return" in obs0

    def test_to_mcp_response_returns_same_as_to_summary(
        self,
        mock_eval_dataclass: FactorEvaluationResult,
    ) -> None:
        """to_mcp_response() returns same as to_summary()."""
        mcp = mock_eval_dataclass.to_mcp_response()
        summary = mock_eval_dataclass.to_summary()
        assert mcp == summary

    def test_to_mcp_response_with_observations(
        self,
        mock_eval_dataclass: FactorEvaluationResult,
    ) -> None:
        """to_mcp_response(include_observations=True) returns same as to_summary()."""
        mcp = mock_eval_dataclass.to_mcp_response(include_observations=True)
        summary = mock_eval_dataclass.to_summary(include_observations=True)
        assert mcp == summary

    def test_to_json_produces_valid_json(
        self,
        mock_eval_dataclass: FactorEvaluationResult,
    ) -> None:
        """to_json() produces valid JSON."""
        json_str = mock_eval_dataclass.to_json()
        parsed = json.loads(json_str)
        assert parsed["factor"] == "momentum_20d"
        assert "observations" not in parsed

    def test_to_json_pretty_produces_indented_json(
        self,
        mock_eval_dataclass: FactorEvaluationResult,
    ) -> None:
        """to_json(pretty=True) produces indented (multiline) JSON."""
        json_str = mock_eval_dataclass.to_json(pretty=True)
        assert "\n" in json_str
        assert '  "' in json_str or "  " in json_str  # has indentation
        parsed = json.loads(json_str)
        assert parsed["factor"] == "momentum_20d"

    def test_to_json_with_observations(
        self,
        mock_eval_dataclass: FactorEvaluationResult,
    ) -> None:
        """to_json(include_observations=True) includes observations in JSON."""
        json_str = mock_eval_dataclass.to_json(include_observations=True)
        parsed = json.loads(json_str)
        assert "observations" in parsed
        assert len(parsed["observations"]) == 3


# ── FactorBacktestResult output mode tests ──


class TestFactorBacktestResultOutputModes:
    """Tests for FactorBacktestResult output methods."""

    def test_to_summary_excludes_periods_by_default(
        self,
        mock_backtest_dataclass: FactorBacktestResult,
    ) -> None:
        """to_summary() does NOT include periods by default."""
        summary = mock_backtest_dataclass.to_summary()
        assert "periods" not in summary
        assert "factor" in summary
        assert "sharpe" in summary
        assert "total_return" in summary

    def test_to_summary_includes_periods_when_requested(
        self,
        mock_backtest_dataclass: FactorBacktestResult,
    ) -> None:
        """to_summary(include_observations=True) DOES include periods."""
        summary = mock_backtest_dataclass.to_summary(include_observations=True)
        assert "periods" in summary
        assert len(summary["periods"]) == 1
        period = summary["periods"][0]
        assert "signal_date" in period
        assert "long_symbols" in period
        assert "short_symbols" in period
        assert "long_short_return" in period
        assert "turnover" in period

    def test_to_mcp_response_returns_same_as_to_summary(
        self,
        mock_backtest_dataclass: FactorBacktestResult,
    ) -> None:
        """to_mcp_response() returns same as to_summary()."""
        mcp = mock_backtest_dataclass.to_mcp_response()
        summary = mock_backtest_dataclass.to_summary()
        assert mcp == summary

    def test_to_mcp_response_with_periods(
        self,
        mock_backtest_dataclass: FactorBacktestResult,
    ) -> None:
        """to_mcp_response(include_observations=True) returns same as to_summary()."""
        mcp = mock_backtest_dataclass.to_mcp_response(include_observations=True)
        summary = mock_backtest_dataclass.to_summary(include_observations=True)
        assert mcp == summary

    def test_to_json_produces_valid_json(
        self,
        mock_backtest_dataclass: FactorBacktestResult,
    ) -> None:
        """to_json() produces valid JSON."""
        json_str = mock_backtest_dataclass.to_json()
        parsed = json.loads(json_str)
        assert parsed["factor"] == "momentum_20d"
        assert "periods" not in parsed

    def test_to_json_pretty_produces_indented_json(
        self,
        mock_backtest_dataclass: FactorBacktestResult,
    ) -> None:
        """to_json(pretty=True) produces indented (multiline) JSON."""
        json_str = mock_backtest_dataclass.to_json(pretty=True)
        assert "\n" in json_str
        parsed = json.loads(json_str)
        assert parsed["factor"] == "momentum_20d"

    def test_to_json_with_periods(
        self,
        mock_backtest_dataclass: FactorBacktestResult,
    ) -> None:
        """to_json(include_observations=True) includes periods in JSON."""
        json_str = mock_backtest_dataclass.to_json(include_observations=True)
        parsed = json.loads(json_str)
        assert "periods" in parsed
        assert len(parsed["periods"]) == 1
