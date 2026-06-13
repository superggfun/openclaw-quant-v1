from __future__ import annotations

import json
from pathlib import Path

from quant.reports.agent_export.agent_exporter import AgentExporter
from quant.reports.agent_export.registry import EXPORT_SPECS, discover_export_modules, discover_export_specs


def write_report(tmp_path: Path, payload: dict) -> Path:
    path = tmp_path / "report.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_report_detection() -> None:
    exporter = AgentExporter()

    assert exporter.detect_report_type({"factors": [], "selected_symbols": [], "target_weights": {}}) == "alpha"
    assert exporter.detect_report_type({"factor": "momentum_20d", "forward_days": 20, "decay": {}}) == "factor_eval"
    assert exporter.detect_report_type({"factor": "momentum_20d", "holding_period": 20, "long_short_return": 0.1}) == "factor_backtest"
    assert exporter.detect_report_type({"summary_metrics": {}, "attribution": {}, "robustness_diagnostics": {}}) == "strategy_eval"
    assert exporter.detect_report_type({"method": "risk_parity", "risk_contribution_pct": {}, "covariance_matrix": {}}) == "portfolio_construction"
    assert exporter.detect_report_type({"risk_score": 60, "holdings": []}) == "risk"
    assert exporter.detect_report_type({"items": [], "cash_after_rebalance": 100}) == "rebalance"
    assert exporter.detect_report_type({"executed_trades": [], "unfilled_trades": [], "execution_costs": {}}) == "execution"
    assert exporter.detect_report_type({"metrics": {}, "equity_curve": []}) == "backtest"


def test_agent_export_specs_are_auto_discovered() -> None:
    modules = discover_export_modules()
    discovered = discover_export_specs(modules)

    assert discovered == EXPORT_SPECS
    assert "factor_eval" in {spec.report_type for spec in discovered}
    assert any(spec.report_type == "factor_eval" and spec.export.__module__.endswith(".factors") for spec in discovered)


def test_alpha_export(tmp_path: Path) -> None:
    report = {
        "config": {"universe": ["SPY", "QQQ", "NVDA"], "weighting_mode": "equal_weight"},
        "as_of_date": "2024-01-31",
        "selected_symbols": ["NVDA", "QQQ"],
        "target_weights": {"NVDA": 0.2, "QQQ": 0.2, "cash": 0.6},
    }
    export = AgentExporter().export_report(report, str(write_report(tmp_path, report))).to_dict()

    assert export["report_type"] == "alpha"
    assert export["key_metrics"]["selected_symbols"] == ["NVDA", "QQQ"]
    assert "WARN_UNIVERSE_SMALL" in export["warnings"]
    assert "run factor evaluation" in export["recommended_next_steps"]


def test_factor_eval_export() -> None:
    report = {
        "factor": "momentum_20d",
        "forward_days": 20,
        "ic_mean": -0.129,
        "rank_ic_mean": -0.1,
        "icir": -0.144,
        "ic_count": 12,
        "decay": {"1d": {"ic": -0.02}, "20d": {"ic": 0.03}},
    }

    export = AgentExporter().export_report(report).to_dict()

    assert export["report_type"] == "factor_eval"
    assert export["key_metrics"]["best_horizon"] == "20d"
    assert "WARN_FACTOR_IC_NEGATIVE" in export["warnings"]
    assert "negative predictive quality" in export["key_findings"]


def test_factor_eval_export_includes_fundamental_coverage() -> None:
    report = {
        "factor": "fundamental_quality_score",
        "forward_days": 20,
        "ic_mean": 0.07,
        "rank_ic_mean": 0.05,
        "icir": 0.2,
        "ic_count": 10,
        "decay": {"20d": {"ic": 0.07}},
        "factor_coverage": {
            "coverage_percentage": 0.65,
            "missing_percentage": 0.35,
            "covered_symbols": ["AAPL", "MSFT"],
            "missing_symbols": ["SPY"],
            "fundamental_metrics_used": ["roe", "roa"],
            "no_lookahead_filter": "report_date <= signal_date",
        },
    }

    export = AgentExporter().export_report(report).to_dict()

    assert export["report_type"] == "factor_eval"
    assert export["key_metrics"]["factor_coverage"]["coverage_percentage"] == 0.65
    assert "WARN_PARTIAL_FUNDAMENTAL_DATA" in export["warnings"]


def test_multi_factor_export() -> None:
    report = {
        "metadata": {"report_type": "multi_factor"},
        "as_of_date": "2024-04-01",
        "factor_families": {"momentum_60d": "PRICE", "fundamental_quality_score": "QUALITY"},
        "factor_weights": {"momentum_60d": 0.4, "fundamental_quality_score": 0.6},
        "family_weights": {"PRICE": 0.4, "QUALITY": 0.6},
        "coverage": {"momentum_60d": 1.0, "fundamental_quality_score": 0.5},
        "confidence": {"overall_confidence": 0.65},
        "scores": [{"symbol": "AAPL", "final_alpha_score": 0.8, "overall_confidence": 0.7}],
    }

    export = AgentExporter().export_report(report).to_dict()

    assert export["report_type"] == "multi_factor"
    assert export["key_metrics"]["overall_confidence"] == 0.65
    assert export["key_metrics"]["top_symbols"][0]["symbol"] == "AAPL"
    assert "WARN_LOW_FACTOR_COVERAGE" in export["warnings"]


def test_factor_backtest_export() -> None:
    report = {
        "factor": "momentum_20d",
        "holding_period": 20,
        "long_short_return": -0.2,
        "long_short_sharpe": 0.5,
        "max_drawdown": -0.45,
        "turnover": 0.3,
        "gross_exposure": 2.0,
        "net_exposure": 0.0,
        "rebalance_dates": ["2024-01-01"],
    }

    export = AgentExporter().export_report(report).to_dict()

    assert export["report_type"] == "factor_backtest"
    assert "WARN_EXTREME_DRAWDOWN" in export["warnings"]
    assert "WARN_SHARPE_RETURN_MISMATCH" in export["warnings"]
    assert "test with larger universe" in export["recommended_next_steps"]


def test_strategy_eval_export() -> None:
    report = {
        "metadata": {},
        "input_report_paths": {},
        "strategy_type": "backtest",
        "summary_metrics": {
            "total_return": 0.12,
            "annual_return": 0.15,
            "sharpe_ratio": 1.1,
            "max_drawdown": -0.08,
            "total_cost": 12.5,
            "turnover": 0.4,
        },
        "attribution": {
            "top_positive_contributors": [{"symbol": "NVDA", "contribution": 0.08}],
            "top_negative_contributors": [{"symbol": "QQQ", "contribution": -0.01}],
        },
        "robustness_diagnostics": {},
        "warnings": [{"code": "LOW_OBSERVATION_COUNT", "reason": "few samples"}],
    }

    export = AgentExporter().export_report(report).to_dict()

    assert export["report_type"] == "strategy_eval"
    assert export["key_metrics"]["total_return"] == 0.12
    assert export["key_metrics"]["top_contributors"][0]["symbol"] == "NVDA"
    assert "LOW_OBSERVATION_COUNT" in export["warnings"]


def test_portfolio_construction_export() -> None:
    report = {
        "method": "risk_parity",
        "selected_symbols": ["SPY"],
        "target_weights": {"SPY": 0.2, "cash": 0.8},
        "cash_weight": 0.8,
        "portfolio_volatility": 0.01,
        "risk_contribution_pct": {"SPY": 1.0},
        "covariance_matrix": {"SPY": {"SPY": 0.01}},
        "warnings": ["capped SPY to max_position_weight"],
    }

    export = AgentExporter().export_report(report).to_dict()

    assert export["report_type"] == "portfolio_construction"
    assert "WARN_CASH_ALLOCATION_HIGH" in export["warnings"]
    assert "WARN_MAX_WEIGHT_CONSTRAINT_BINDING" in export["warnings"]
    assert "evaluate risk parity allocation" in export["recommended_next_steps"]


def test_risk_export_missing_fields_handling() -> None:
    export = AgentExporter().export_report({"risk_score": 75, "holdings": []}).to_dict()

    assert export["report_type"] == "risk"
    assert export["key_metrics"]["risk_score"] == 75
    assert "high risk" in export["key_findings"]


def test_token_truncation_and_deterministic_output(tmp_path: Path) -> None:
    report = {
        "factor": "momentum_20d",
        "holding_period": 20,
        "long_short_return": 0.1,
        "warnings": [f"warning {index}" for index in range(20)],
    }
    exporter = AgentExporter()
    path = write_report(tmp_path, report)

    first = exporter.export_file(path, output_format="json", max_tokens=25)
    second = exporter.export_file(path, output_format="json", max_tokens=25)

    assert first == second
    payload = json.loads(first)
    assert payload["report_type"] == "factor_backtest"
    assert "long_short_return" in payload["key_metrics"]
    assert len(payload["warnings"]) <= 3


def test_detection_does_not_depend_on_filename(tmp_path: Path) -> None:
    path = tmp_path / "totally_misleading_strategy_eval_name.json"
    path.write_text(json.dumps({"factor": "momentum_20d", "holding_period": 20, "long_short_return": 0.1}), encoding="utf-8")

    payload = json.loads(AgentExporter().export_file(path, output_format="json"))

    assert payload["report_type"] == "factor_backtest"


def test_missing_fields_never_crash_or_invent_values() -> None:
    export = AgentExporter().export_report({"factor": "momentum_20d", "forward_days": 20, "decay": {}}).to_dict()

    assert export["report_type"] == "factor_eval"
    assert export["key_metrics"]["ic_mean"] is None
    assert export["key_metrics"]["best_horizon"] is None


def test_markdown_and_output_file(tmp_path: Path) -> None:
    report = {"metrics": {"total_return": 0.1}, "equity_curve": []}
    report_path = write_report(tmp_path, report)
    output_path = tmp_path / "summary.md"

    rendered = AgentExporter().export_file(report_path, output_format="markdown", output_path=output_path)

    assert rendered.startswith("# Agent Export: backtest")
    assert output_path.read_text(encoding="utf-8") == rendered
