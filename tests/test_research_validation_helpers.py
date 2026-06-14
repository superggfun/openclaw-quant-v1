from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import pytest

from quant.research_validation.models import ValidationStep
from quant.research_validation.ranking import factor_rankings, strategy_rankings
from quant.research_validation.recommendations import recommendations
from quant.research_validation.report_input import ResearchValidationReportInput
from quant.research_validation.report_writer import ResearchValidationReportWriter, agent_summary, build_research_validation_report


def _minimal_report_input_kwargs(tmp_path: Path) -> dict:
    return {
        "scope": {
            "trading_day_count": 2,
            "symbol_count": 1,
            "factor_count": 1,
            "estimated_observation_count": 2,
        },
        "symbol_diagnostics": {
            "requested_symbol_count": 1,
            "selected_symbol_count": 1,
            "skipped_symbol_count": 0,
        },
        "warning_counter": Counter(),
        "run_id": "rv-test",
        "run_dir": tmp_path / "runs" / "rv-test",
        "mode": "quick",
        "start": "2024-01-01",
        "end": "2024-01-03",
        "effective_start": "2024-01-01",
        "effective_end": "2024-01-03",
        "max_factors": 1,
        "max_strategies": 1,
        "folds": 1,
        "timeout": 30.0,
        "effective_batch_size": 1,
        "max_symbols": 1,
        "family": "price",
        "resume": False,
        "skip_existing": False,
        "use_cache": False,
        "cache_stats": False,
        "bulk_matrix": False,
        "parallel": False,
        "worker_count": 1,
        "matrix_workers": 4,
        "parallel_target": "factor_batch",
        "write_substep_reports": False,
        "write_batch_artifacts": False,
        "write_intermediate_reports": False,
        "write_charts": False,
        "write_debug_logs": False,
        "universe": ["SPY"],
        "factor_store_before": {"factor_history": 0},
        "factor_store_after": {"factor_history": 1},
        "factor_store_growth": {"factor_history": 1},
        "cache_summary_data": {"cache_enabled": False},
        "performance_metadata": {"sqlite_writes": "main_process_only"},
        "regime_sample_counts": {},
        "batches": [["SPY"]],
        "completed_batches": [],
        "skipped_batches": [],
        "runtime": 1.2345678,
        "partial": False,
        "steps": [ValidationStep("factor_eval", "factor", "momentum_20d", "PASS", 0.1)],
        "skipped_steps": [],
        "slow_steps": [],
        "factor_rankings": [{"factor": "momentum_20d", "evidence_score": 0.5}],
        "strategy_rankings": [{"strategy": "demo", "total_return": 0.01}],
        "current_regime": "BULL",
        "best_current_regime_factor": None,
        "factor_evidence_summary": {"usable_factor_count": 1},
        "factor_eval_results": [],
        "factor_backtest_results": [],
        "walk_forward_results": [],
        "strategy_results": [],
        "gate_results": [],
        "factor_rank": {},
        "regime_rank": {},
        "recommendations": [],
    }


def test_factor_rankings_include_raw_metrics_and_grade() -> None:
    rows = factor_rankings(
        ["momentum_20d"],
        [{"factor": "momentum_20d", "ic_mean": 0.08, "rank_ic_mean": 0.07, "icir": 0.2, "coverage": 0.95}],
        [{"factor": "momentum_20d", "long_short_return": 0.03, "sharpe": 1.1, "max_drawdown": -0.05}],
        [{"parameters": {"factor": "momentum_20d"}, "summary": {"average_test_sharpe": 0.4}}],
        {"top_factors": [{"factor_name": "momentum_20d", "confidence_score": 0.6}]},
    )

    row = rows[0]
    assert row["raw_metrics"]["ic"] == 0.08
    assert row["rank_score"] == row["evidence_score"]
    assert row["evidence_grade"] in {"candidate", "usable_but_needs_walk_forward", "weak_or_inconclusive"}


def test_strategy_rankings_and_recommendations_are_report_helpers() -> None:
    strategies = strategy_rankings(
        [
            {
                "strategy_name": "demo",
                "strategy_version": "v1",
                "status": "OK",
                "gate_summary": {"overall_status": "WARNING"},
                "trade_sim_summary": {"total_return": 0.02},
                "warnings": ["WARN_LOW_FACTOR_COVERAGE"],
            }
        ]
    )

    output = recommendations(Counter({"WARN_LOW_FACTOR_COVERAGE": 1}), strategies)

    assert strategies[0]["strategy"] == "demo"
    assert any("coverage" in item for item in output)


def test_research_validation_report_uses_explicit_input_boundary(tmp_path: Path) -> None:
    kwargs = _minimal_report_input_kwargs(tmp_path)

    report = build_research_validation_report(ResearchValidationReportInput(**kwargs))

    assert report["run_id"] == "rv-test"
    assert report["parameters"]["universe"] == ["SPY"]
    assert report["completed_steps"][0]["name"] == "factor_eval"
    assert report["top_10_factors"] == kwargs["factor_rankings"]
    assert report["status"] == "PASS"

    kwargs["unused_local"] = "this used to leak through locals()"
    with pytest.raises(TypeError):
        ResearchValidationReportInput(**kwargs)


def test_report_writer_manifest_and_agent_summary(tmp_path: Path) -> None:
    writer = ResearchValidationReportWriter(tmp_path / "reports")
    run_dir = tmp_path / "reports" / "runs" / "rv-test"

    manifest_path = writer.write_manifest(
        run_dir=run_dir,
        run_id="rv-test",
        run_type="research_validation",
        mode="quick",
        status="WARNING",
        aggregate_report_path="report.json",
        summary_path="summary.md",
        agent_export_path="agent.md",
        substep_report_paths=[],
        artifact_paths=[],
        chart_paths=[],
        log_paths=[],
        warnings=["WARN_LOW_REGIME_SAMPLE"],
        warning_statistics=[{"code": "WARN_LOW_REGIME_SAMPLE", "count": 1}],
        compaction_status="compact",
    )
    report = {
        "mode": "quick",
        "current_regime": "BULL",
        "top_10_factors": [],
        "warning_statistics": [{"code": "WARN_LOW_REGIME_SAMPLE", "count": 1}],
        "best_factor_in_current_regime": None,
    }

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    summary = agent_summary(report)

    assert manifest["run_id"] == "rv-test"
    assert "Regime result is diagnostic" in summary
