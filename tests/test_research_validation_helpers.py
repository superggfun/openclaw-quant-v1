from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from quant.research_validation.ranking import factor_rankings, strategy_rankings
from quant.research_validation.recommendations import recommendations
from quant.research_validation.report_writer import ResearchValidationReportWriter, agent_summary


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
