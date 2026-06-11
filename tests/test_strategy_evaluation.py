import json
from pathlib import Path

import pytest

from quant.cli import main
from quant.strategy_eval.strategy_evaluation import StrategyEvaluation


def write_json(path: Path, data: dict) -> Path:
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return path


def factor_backtest_report() -> dict:
    return {
        "factor": "momentum_20d",
        "start_date": "2024-01-01",
        "end_date": "2024-03-31",
        "holding_period": 1,
        "quantiles": 5,
        "long_quantile": 5,
        "short_quantile": 1,
        "observations": 12,
        "rebalance_dates": ["2024-01-31", "2024-02-29", "2024-03-31"],
        "long_leg_return": 0.12,
        "short_leg_return": -0.03,
        "long_short_return": 0.15,
        "annual_return": 0.42,
        "volatility": 0.18,
        "sharpe": 1.4,
        "max_drawdown": -0.05,
        "hit_rate": 2 / 3,
        "turnover": 0.5,
        "gross_exposure": 2.0,
        "net_exposure": 0.0,
        "ic_mean": 0.1,
        "rank_ic_mean": 0.08,
        "icir": 0.5,
        "excluded_symbols": [],
        "exclusion_reasons": {},
        "no_lookahead": True,
        "signal_execution_lag": "factor uses signal_date and earlier; future_return uses T+1 close",
        "pipeline_enabled": False,
        "pipeline_config_path": None,
        "pipeline_config": None,
        "periods": [
            {
                "signal_date": "2024-01-31",
                "future_date": "2024-02-01",
                "long_symbols": ["AAA"],
                "short_symbols": ["BBB"],
                "long_weights": {"AAA": 1.0},
                "short_weights": {"BBB": -1.0},
                "long_weight_sum": 1.0,
                "short_weight_sum": -1.0,
                "net_exposure": 0.0,
                "gross_exposure": 2.0,
                "quantile_returns": {"q1": -0.01, "q5": 0.04},
                "long_return": 0.04,
                "short_return": -0.01,
                "long_short_return": 0.05,
                "turnover": None,
            },
            {
                "signal_date": "2024-02-29",
                "future_date": "2024-03-01",
                "long_symbols": ["CCC"],
                "short_symbols": ["DDD"],
                "long_weights": {"CCC": 1.0},
                "short_weights": {"DDD": -1.0},
                "long_weight_sum": 1.0,
                "short_weight_sum": -1.0,
                "net_exposure": 0.0,
                "gross_exposure": 2.0,
                "quantile_returns": {"q1": 0.02, "q5": -0.03},
                "long_return": -0.03,
                "short_return": 0.02,
                "long_short_return": -0.05,
                "turnover": 1.0,
            },
            {
                "signal_date": "2024-03-31",
                "future_date": "2024-04-01",
                "long_symbols": ["AAA"],
                "short_symbols": ["DDD"],
                "long_weights": {"AAA": 1.0},
                "short_weights": {"DDD": -1.0},
                "long_weight_sum": 1.0,
                "short_weight_sum": -1.0,
                "net_exposure": 0.0,
                "gross_exposure": 2.0,
                "quantile_returns": {"q1": -0.02, "q5": 0.03},
                "long_return": 0.03,
                "short_return": -0.02,
                "long_short_return": 0.05,
                "turnover": 1.0,
            },
        ],
        "warnings": [],
    }


def backtest_report() -> dict:
    return {
        "start": "2024-01-01",
        "end": "2024-01-05",
        "initial_cash": 100000,
        "strategy": "alpha",
        "mode": "alpha",
        "rebalance_frequency": "daily",
        "no_lookahead": True,
        "signal_execution_lag": "next trading day",
        "alpha_config": {},
        "excluded_symbols_per_rebalance": {},
        "metrics": {
            "final_value": 103000,
            "total_return": 0.03,
            "annual_return": 1.2,
            "max_drawdown": -0.01,
            "volatility": 0.12,
            "sharpe_ratio": 1.1,
            "trade_count": 2,
            "turnover": 0.4,
            "total_cost": 25.0,
            "cash_ratio": 0.1,
        },
        "trades": [
            {"date": "2024-01-02", "symbol": "AAA", "side": "BUY", "notional": 50000, "total_cost": 10},
            {"date": "2024-01-04", "symbol": "AAA", "side": "SELL", "notional": 52000, "total_cost": 15},
        ],
        "equity_curve": [
            {"date": "2024-01-01", "cash": 100000, "equity": 100000, "positions": {}},
            {"date": "2024-01-02", "cash": 50000, "equity": 101000, "positions": {"AAA": 51000}},
            {"date": "2024-02-01", "cash": 52000, "equity": 103000, "positions": {"AAA": 51000}},
        ],
    }


def test_summary_metrics(tmp_path: Path) -> None:
    report_path = write_json(tmp_path / "factor_backtest.json", factor_backtest_report())

    result = StrategyEvaluation(report_dir=tmp_path / "reports").evaluate(report_path)

    assert result.report_type == "factor_backtest"
    assert result.summary["total_return"] == 0.15
    assert result.summary["calmar_ratio"] == pytest.approx(0.42 / 0.05)
    assert Path(result.report_path).exists()


def test_return_attribution(tmp_path: Path) -> None:
    report_path = write_json(tmp_path / "factor_backtest.json", factor_backtest_report())

    result = StrategyEvaluation(report_dir=tmp_path / "reports").evaluate(report_path)

    assert result.return_attribution["long_leg_return"] == 0.12
    assert result.return_attribution["short_leg_return"] == -0.03
    assert result.return_attribution["long_short_return"] == 0.15
    assert result.return_attribution["cost_drag"] == 0.0


def test_drawdown_attribution(tmp_path: Path) -> None:
    report_path = write_json(tmp_path / "factor_backtest.json", factor_backtest_report())

    result = StrategyEvaluation(report_dir=tmp_path / "reports").evaluate(report_path)

    assert result.drawdown["max_drawdown"] < 0
    assert result.drawdown["drawdown_start"] is not None
    assert result.drawdown["drawdown_end"] is not None
    assert "largest_contributors_to_drawdown" in result.drawdown


def test_factor_backtest_drawdown_uses_initial_capital_peak(tmp_path: Path) -> None:
    report = factor_backtest_report()
    report["long_short_return"] = -0.5
    report["max_drawdown"] = 0.0
    report["periods"] = [
        {
            **report["periods"][0],
            "signal_date": "2024-01-31",
            "long_return": -0.25,
            "short_return": 0.25,
            "long_short_return": -0.5,
        }
    ]
    report_path = write_json(tmp_path / "factor_backtest.json", report)

    result = StrategyEvaluation(report_dir=tmp_path / "reports").evaluate(report_path)

    assert result.summary_metrics["max_drawdown"] == pytest.approx(-0.5)
    assert result.drawdown["max_drawdown"] == pytest.approx(-0.5)


def test_rolling_metrics(tmp_path: Path) -> None:
    report = factor_backtest_report()
    for index in range(4, 30):
        report["periods"].append(
            {
                **report["periods"][-1],
                "signal_date": f"2024-04-{index:02d}",
                "long_short_return": 0.01,
            }
        )
    report_path = write_json(tmp_path / "factor_backtest.json", report)

    result = StrategyEvaluation(report_dir=tmp_path / "reports").evaluate(report_path)

    assert "20" in result.rolling_metrics
    assert result.rolling_metrics["20"]["rolling_return"]
    assert "60" in result.rolling_metrics


def test_monthly_aggregation(tmp_path: Path) -> None:
    report_path = write_json(tmp_path / "factor_backtest.json", factor_backtest_report())

    result = StrategyEvaluation(report_dir=tmp_path / "reports").evaluate(report_path)

    assert set(result.monthly_returns) == {"2024-01", "2024-02", "2024-03"}


def test_yearly_aggregation(tmp_path: Path) -> None:
    report_path = write_json(tmp_path / "factor_backtest.json", factor_backtest_report())

    result = StrategyEvaluation(report_dir=tmp_path / "reports").evaluate(report_path)

    assert set(result.yearly_returns) == {"2024"}


def test_missing_report_handling(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="report file not found"):
        StrategyEvaluation(report_dir=tmp_path / "reports").evaluate(tmp_path / "missing.json")


def test_no_lookahead_compatibility(tmp_path: Path) -> None:
    report = factor_backtest_report()
    report["no_lookahead"] = True
    report_path = write_json(tmp_path / "factor_backtest.json", report)

    result = StrategyEvaluation(report_dir=tmp_path / "reports").evaluate(report_path)

    assert result.report_type == "factor_backtest"
    assert result.metadata["source_no_lookahead"] is True
    assert "NO_LOOKAHEAD_NOT_MARKED" not in {warning["code"] for warning in result.warnings}


def test_factor_backtest_compatibility(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    report_path = write_json(tmp_path / "factor_backtest.json", factor_backtest_report())

    exit_code = main(["strategy-eval", "--report", str(report_path)])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "Strategy Evaluation Summary" in output
    assert "return_attribution:" in output
    assert "risk_attribution:" in output


def test_backtest_compatibility(tmp_path: Path) -> None:
    report_path = write_json(tmp_path / "backtest.json", backtest_report())

    result = StrategyEvaluation(report_dir=tmp_path / "reports").evaluate(report_path)

    assert result.report_type == "backtest"
    assert result.summary["total_return"] == 0.03
    assert result.return_attribution["cost_drag"] == pytest.approx(-25 / 100000)
    assert result.risk_attribution["average_cash"] is not None


def test_sortino_and_calmar_ratio(tmp_path: Path) -> None:
    report_path = write_json(tmp_path / "factor_backtest.json", factor_backtest_report())

    result = StrategyEvaluation(report_dir=tmp_path / "reports").evaluate(report_path)

    assert "sortino_ratio" in result.summary_metrics
    assert result.summary_metrics["calmar_ratio"] == pytest.approx(0.42 / 0.05)


def test_information_ratio_with_benchmark(tmp_path: Path) -> None:
    report_path = write_json(tmp_path / "factor_backtest.json", factor_backtest_report())
    benchmark = {
        "2024-01-31": 0.01,
        "2024-02-29": 0.01,
        "2024-03-31": 0.01,
    }

    result = StrategyEvaluation(report_dir=tmp_path / "reports").evaluate(
        report_path,
        benchmark_returns=benchmark,
        benchmark_name="SPY",
    )

    assert result.benchmark_metrics["benchmark"] == "SPY"
    assert result.summary_metrics["benchmark_return"] == pytest.approx((1.01**3) - 1)
    assert result.summary_metrics["information_ratio"] is not None


def test_attribution_by_symbol_and_side(tmp_path: Path) -> None:
    report_path = write_json(tmp_path / "factor_backtest.json", factor_backtest_report())

    result = StrategyEvaluation(report_dir=tmp_path / "reports").evaluate(report_path)

    assert result.return_attribution["by_symbol"]["AAA"] > 0
    assert result.return_attribution["by_side"]["long_side"] == 0.12
    assert result.return_attribution["by_side"]["short_side"] == -0.03
    assert result.return_attribution["by_side"]["raw_short_leg_underlying_return"] == -0.03
    assert result.return_attribution["by_side"]["short_side_contribution"] == pytest.approx(0.01)
    assert result.attribution["methodology"]["by_side"]
    assert result.attribution["top_positive_contributors"]
    assert result.attribution["top_negative_contributors"]


def test_cost_attribution_by_symbol(tmp_path: Path) -> None:
    report_path = write_json(tmp_path / "backtest.json", backtest_report())

    result = StrategyEvaluation(report_dir=tmp_path / "reports").evaluate(report_path)

    assert result.attribution["cost_attribution_by_symbol"]["AAA"] == pytest.approx(-25 / 100000)
    assert result.attribution["turnover_attribution_by_symbol"]["AAA"] == pytest.approx(102000 / 100000)


def test_concentration_detection(tmp_path: Path) -> None:
    report = factor_backtest_report()
    report["long_short_return"] = 0.06
    report["long_leg_return"] = 0.06
    report["short_leg_return"] = 0.0
    report["periods"] = [
        {
            **report["periods"][0],
            "long_symbols": ["AAA"],
            "short_symbols": ["BBB"],
            "long_return": 0.06,
            "short_return": 0.0,
            "long_short_return": 0.06,
        }
    ]
    report_path = write_json(tmp_path / "factor_backtest.json", report)

    result = StrategyEvaluation(report_dir=tmp_path / "reports").evaluate(report_path)

    codes = {warning["code"] for warning in result.warnings}
    assert "SYMBOL_CONCENTRATION" in codes
    assert result.attribution["return_concentration"]["top_1_pct"] >= 0.5


def test_high_turnover_and_high_cost_warnings(tmp_path: Path) -> None:
    report = backtest_report()
    report["metrics"]["turnover"] = 1.5
    report["metrics"]["total_cost"] = 5000
    report["trades"][0]["total_cost"] = 2500
    report["trades"][1]["total_cost"] = 2500
    report_path = write_json(tmp_path / "backtest.json", report)

    result = StrategyEvaluation(report_dir=tmp_path / "reports").evaluate(report_path)

    codes = {warning["code"] for warning in result.warnings}
    assert "HIGH_TURNOVER" in codes
    assert "HIGH_COST_DRAG" in codes


def test_benchmark_underperformance_warning(tmp_path: Path) -> None:
    report_path = write_json(tmp_path / "factor_backtest.json", factor_backtest_report())

    result = StrategyEvaluation(report_dir=tmp_path / "reports").evaluate(
        report_path,
        benchmark_returns={"2024-01-31": 0.10, "2024-02-29": 0.10, "2024-03-31": 0.10},
        benchmark_name="SPY",
    )

    assert "BENCHMARK_UNDERPERFORMANCE" in {warning["code"] for warning in result.warnings}


def test_report_schema_contains_v14_sections(tmp_path: Path) -> None:
    report_path = write_json(tmp_path / "factor_backtest.json", factor_backtest_report())

    result = StrategyEvaluation(report_dir=tmp_path / "reports").evaluate(report_path)
    payload = json.loads(Path(result.report_path).read_text(encoding="utf-8"))

    assert set(payload) >= {
        "metadata",
        "input_report_paths",
        "strategy_type",
        "evaluation_window",
        "summary_metrics",
        "benchmark_metrics",
        "attribution",
        "robustness_diagnostics",
        "warnings",
        "interpretation_notes",
    }


def test_cli_accepts_factor_backtest_report_flag(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    report_path = write_json(tmp_path / "factor_backtest.json", factor_backtest_report())

    exit_code = main(["strategy-eval", "--factor-backtest-report", str(report_path)])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "strategy_type: factor_backtest" in output
    assert "summary_metrics:" in output


def test_cli_accepts_backtest_report_flag(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    report_path = write_json(tmp_path / "backtest.json", backtest_report())

    exit_code = main(["strategy-eval", "--backtest-report", str(report_path)])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "strategy_type: backtest" in output
    assert "cost_to_return_ratio:" in output
