from __future__ import annotations

import json
from pathlib import Path

from quant.reports.agent_export.agent_exporter import AgentExporter
from quant.reports.visualization.registry import REPORT_SPECS, discover_report_specs, discover_spec_modules
from quant.reports.visualization.report_visualizer import ReportVisualizer


def write_report(tmp_path: Path, name: str, payload: dict) -> Path:
    path = tmp_path / "reports" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def trade_sim_report() -> dict:
    return {
        "metadata": {"report_type": "trade_sim"},
        "strategy": "alpha",
        "portfolio_method": "equal_weight",
        "initial_cash": 100000,
        "final_equity": 105000,
        "total_return": 0.05,
        "max_drawdown": -0.02,
        "total_cost": 12.5,
        "trade_count": 2,
        "equity_curve": [
            {"date": "2024-01-02", "equity": 100000},
            {"date": "2024-01-31", "equity": 102000},
            {"date": "2024-02-29", "equity": 105000},
        ],
        "cash_curve": [
            {"date": "2024-01-02", "cash": 100000},
            {"date": "2024-01-31", "cash": 40000},
            {"date": "2024-02-29", "cash": 42000},
        ],
        "trades": [
            {"date": "2024-01-03", "cost": 5.0},
            {"date": "2024-02-01", "cost": 7.5},
        ],
        "rebalance_events": [],
        "warnings": ["WARN_TEST"],
        "no_lookahead": True,
    }


def walk_forward_report() -> dict:
    return {
        "strategy": "alpha",
        "folds": [
            {"fold_id": 1, "train_metrics": {"total_return": 0.1, "sharpe": 1.2}, "test_metrics": {"total_return": 0.04, "sharpe": 0.7}},
            {"fold_id": 2, "train_metrics": {"total_return": 0.2, "sharpe": 1.5}, "test_metrics": {"total_return": -0.02, "sharpe": -0.1}},
        ],
        "summary": {"average_test_return": 0.01},
        "stability_analysis": {
            "factor_stability_ranking": [
                {"factor": "quality_score", "stability_score": 0.8},
                {"factor": "momentum_20d", "stability_score": 0.4},
            ]
        },
        "warnings": ["WARN_OVERFIT"],
    }


def test_visualizer_detects_and_generates_trade_sim_files(tmp_path: Path) -> None:
    report_path = write_report(tmp_path, "trade_sim_sample.json", trade_sim_report())

    result = ReportVisualizer().visualize_file(report_path, output_dir=report_path.parent / "charts")

    assert result.report_type == "trade_sim"
    assert Path(result.dashboard_path).exists()
    assert Path(result.visual_summary_path).exists()
    assert len(result.charts) >= 5
    for chart in result.charts:
        assert Path(chart["png_path"]).exists()
        assert Path(chart["svg_path"]).exists()
        assert Path(chart["png_path"]).read_bytes().startswith(b"\x89PNG")


def test_visualization_report_specs_are_auto_discovered() -> None:
    modules = discover_spec_modules()
    discovered = discover_report_specs(modules)

    assert discovered == REPORT_SPECS
    assert "factor_eval" in discovered
    assert discovered["factor_eval"].build_charts.__module__.endswith(".factors")
    assert all(not module.__name__.endswith(".common") for module in modules)


def test_walk_forward_dashboard_generation(tmp_path: Path) -> None:
    report_path = write_report(tmp_path, "walk_forward_sample.json", walk_forward_report())

    result = ReportVisualizer().visualize_file(report_path, output_dir=report_path.parent / "charts")

    assert result.report_type == "walk_forward"
    assert "summary.html" in result.dashboard_path
    assert {chart["chart_id"] for chart in result.charts} >= {"fold_returns", "train_vs_test_return", "train_vs_test_sharpe"}


def test_missing_fields_still_generate_dashboard(tmp_path: Path) -> None:
    report_path = write_report(tmp_path, "risk_sample.json", {"risk_score": 50, "holdings": []})

    result = ReportVisualizer().visualize_file(report_path, output_dir=tmp_path / "charts")

    assert result.report_type == "risk"
    assert Path(result.dashboard_path).exists()
    assert any(warning.startswith("VISUALIZATION_SKIPPED_CHART") for warning in result.warnings)


def test_missing_fields_skip_charts_for_major_report_types(tmp_path: Path) -> None:
    reports = {
        "trade_sim_missing.json": {"metadata": {"report_type": "trade_sim"}, "equity_curve": []},
        "backtest_missing.json": {"metrics": {}, "equity_curve": []},
        "strategy_eval_missing.json": {
            "summary_metrics": {"total_return": 0.01},
            "attribution": {},
            "robustness_diagnostics": {},
        },
        "factor_eval_missing.json": {"factor": "momentum_20d", "forward_days": 20, "decay": {}, "quintiles": {}},
        "factor_backtest_missing.json": {"factor": "momentum_20d", "holding_period": 20, "long_short_return": 0.0, "periods": []},
        "portfolio_construction_missing.json": {"method": "equal_weight", "target_weights": {}, "risk_contribution_pct": {}, "covariance_matrix": {}},
        "walk_forward_missing.json": {"strategy": "alpha", "folds": [], "summary": {}, "stability_analysis": {}},
    }

    for filename, payload in reports.items():
        report_path = write_report(tmp_path, filename, payload)
        result = ReportVisualizer().visualize_file(report_path, output_dir=tmp_path / "charts")

        assert Path(result.dashboard_path).exists()
        assert any(warning.startswith("VISUALIZATION_SKIPPED_CHART") for warning in result.warnings), filename


def test_dashboard_escapes_report_text(tmp_path: Path) -> None:
    report = trade_sim_report()
    report["warnings"] = ["<script>alert('x')</script>"]
    report["interpretation_notes"] = ["<img src=x onerror=alert(1)>"]
    report_path = write_report(tmp_path, "trade_sim_escape.json", report)

    result = ReportVisualizer().visualize_file(report_path, output_dir=tmp_path / "charts")
    html = Path(result.dashboard_path).read_text(encoding="utf-8")

    assert "<script>alert" not in html
    assert "<img src=x" not in html
    assert "&lt;script&gt;" in html


def test_deterministic_filenames(tmp_path: Path) -> None:
    report_path = write_report(tmp_path, "trade_sim_fixed.json", trade_sim_report())
    output_dir = report_path.parent / "charts"

    first = ReportVisualizer().visualize_file(report_path, output_dir=output_dir)
    second = ReportVisualizer().visualize_file(report_path, output_dir=output_dir)

    assert first.charts == second.charts
    assert first.dashboard_path == second.dashboard_path


def test_agent_export_includes_visualization_paths(tmp_path: Path) -> None:
    report_path = write_report(tmp_path, "trade_sim_agent.json", trade_sim_report())
    ReportVisualizer().visualize_file(report_path, output_dir=report_path.parent / "charts")

    export = AgentExporter().export_file(report_path, output_format="json")
    payload = json.loads(export)

    assert payload["report_type"] == "trade_sim"
    assert payload["visual_summary_paths"]
    assert payload["visualization_paths"]
    assert any(path.endswith(".png") for path in payload["visualization_paths"])


def test_factor_eval_quintile_chart(tmp_path: Path) -> None:
    report = {
        "factor": "momentum_20d",
        "forward_days": 20,
        "decay": {"1d": {"ic": 0.1}, "20d": {"ic": 0.03}},
        "quintiles": {"q1": -0.01, "q2": 0.0, "q3": 0.01, "q4": 0.02, "q5": 0.03},
        "observations": [
            {"signal_date": "2024-01-02", "factor_value": 1, "future_return": 0.01},
            {"signal_date": "2024-01-02", "factor_value": 2, "future_return": 0.02},
        ],
    }
    report_path = write_report(tmp_path, "factor_eval_sample.json", report)

    result = ReportVisualizer().visualize_file(report_path, output_dir=tmp_path / "charts")

    assert result.report_type == "factor_eval"
    assert "quintile_returns" in {chart["chart_id"] for chart in result.charts}


def test_multi_factor_charts(tmp_path: Path) -> None:
    report = {
        "metadata": {"report_type": "multi_factor"},
        "factor_families": {"momentum_60d": "PRICE", "fundamental_quality_score": "QUALITY"},
        "family_weights": {"PRICE": 0.4, "QUALITY": 0.6},
        "confidence": {"overall_confidence": 0.6},
        "stability": {
            "momentum_60d": {"score": 0.8},
            "fundamental_quality_score": {"score": 0.5},
        },
        "scores": [
            {
                "symbol": "AAPL",
                "final_alpha_score": 0.7,
                "overall_confidence": 0.6,
                "family_contributions": {"PRICE": 0.2, "QUALITY": 0.5},
                "factor_contributions": {"momentum_60d": 0.2, "fundamental_quality_score": 0.5},
            }
        ],
    }
    report_path = write_report(tmp_path, "multi_factor_sample.json", report)

    result = ReportVisualizer().visualize_file(report_path, output_dir=tmp_path / "charts")

    assert result.report_type == "multi_factor"
    assert {"family_contribution", "factor_contribution", "confidence", "stability_ranking"} <= {
        chart["chart_id"] for chart in result.charts
    }
