"""Research validation report and artifact writers."""

from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from quant.research_validation.config import (
    DEFAULT_FORWARD_DAYS,
    DEFAULT_HOLDING_PERIOD,
    RECOMMENDED_PERFORMANCE_WORK,
    REPORT_INTERPRETATION_NOTES,
    REPORT_SCHEMA_VERSION,
    REPORT_TITLE,
    RESEARCH_VALIDATION_RELEASE,
)
from quant.research_validation.report_input import ResearchValidationReportInput
from quant.reports.report_io import generate_report_path, write_json_report
from quant.reports.visualization.chart_builder import ChartBuilder


class ResearchValidationReportWriter:
    def __init__(self, report_dir: str | Path = "reports", chart_dir: str | Path | None = None) -> None:
        self.report_dir = Path(report_dir)
        self.chart_dir = Path(chart_dir) if chart_dir else self.report_dir / "charts"

    def write_outputs(self, report: dict[str, Any], charts_enabled: bool = False, chart_dir: Path | None = None) -> tuple[dict[str, Any], float]:
        self.report_dir.mkdir(parents=True, exist_ok=True)
        json_path = generate_report_path(self.report_dir, "research_validation", unique=True)
        stamp = json_path.stem.removeprefix("research_validation_").rsplit("_", 1)[0]
        report = report | {"report_path": str(json_path)}
        summary_path = self.report_dir / "research_validation_summary.md"
        agent_path = self.report_dir / "agent_export_research_validation.md"
        selected_chart_dir = chart_dir or self.chart_dir
        chart_started = time.monotonic()
        charts = self.charts(report, stamp, selected_chart_dir) if charts_enabled else []
        chart_write_seconds = time.monotonic() - chart_started
        chart_output_paths = (
            sorted(str(path) for path in selected_chart_dir.glob(f"research_validation_{stamp}*"))
            if charts_enabled
            else []
        )
        report["summary_path"] = str(summary_path)
        report["agent_summary_path"] = str(agent_path)
        report["charts_enabled"] = bool(charts_enabled)
        report["chart_count"] = len(charts)
        report["chart_paths"] = chart_output_paths
        report["visualizations"] = [chart.to_dict() for chart in charts]
        summary_path.write_text(markdown_summary(report), encoding="utf-8")
        agent_path.write_text(agent_summary(report), encoding="utf-8")
        return report, chart_write_seconds

    def write_manifest(
        self,
        run_dir: Path,
        run_id: str,
        run_type: str,
        mode: str,
        status: str | None,
        aggregate_report_path: str | None,
        summary_path: str | None,
        agent_export_path: str | None,
        substep_report_paths: list[str],
        artifact_paths: list[str],
        chart_paths: list[str],
        log_paths: list[str],
        warnings: list[str],
        warning_statistics: list[dict[str, Any]],
        compaction_status: str,
    ) -> Path:
        created_at = datetime.now().isoformat(timespec="seconds")
        for name in ("summaries", "substeps", "artifacts", "charts", "exports", "logs"):
            (run_dir / name).mkdir(parents=True, exist_ok=True)
        substep_report_paths = sorted(set(substep_report_paths) | directory_files(run_dir / "substeps"))
        artifact_paths = sorted(set(artifact_paths) | directory_files(run_dir / "artifacts"))
        chart_paths = sorted(set(chart_paths) | directory_files(run_dir / "charts"))
        log_paths = sorted(set(log_paths) | directory_files(run_dir / "logs"))
        manifest = {
            "run_id": run_id,
            "run_type": run_type,
            "created_at": created_at,
            "mode": mode,
            "status": status,
            "timestamp": created_at,
            "aggregate_report_path": aggregate_report_path,
            "summary_paths": [path for path in [summary_path] if path],
            "summary_path": summary_path,
            "export_paths": [path for path in [agent_export_path] if path],
            "agent_export_path": agent_export_path,
            "substep_report_paths": substep_report_paths,
            "artifact_paths": artifact_paths,
            "chart_paths": chart_paths,
            "log_paths": log_paths,
            "warnings": sorted(set(warnings)),
            "warning_summary": list(warning_statistics),
            "compaction_status": compaction_status,
        }
        path = run_dir / "manifest.json"
        return write_json_report(path, manifest, sort_keys=True)

    @staticmethod
    def write_aggregate_report(path: Path, report: dict[str, Any]) -> None:
        metadata = report.setdefault("performance_metadata", {})
        metadata["aggregate_report_size_bytes"] = 0
        for _ in range(5):
            encoded = json.dumps(report, indent=2, sort_keys=True).encode("utf-8")
            size = len(encoded)
            if metadata.get("aggregate_report_size_bytes") == size:
                break
            metadata["aggregate_report_size_bytes"] = size
        write_json_report(path, report, sort_keys=True)

    @staticmethod
    def charts(report: dict[str, Any], stamp: str, chart_dir: Path):
        builder = ChartBuilder(chart_dir)
        prefix = f"research_validation_{stamp}"
        charts = [
            builder.bar_chart(prefix, "factor_evidence_ranking", "Factor Evidence Ranking", {row["factor"]: row.get("evidence_score") for row in report["top_10_factors"]}),
            builder.bar_chart(prefix, "strategy_returns", "Strategy Returns", {row["strategy"]: row.get("total_return") for row in report["strategy_rankings"]}),
            builder.bar_chart(prefix, "warning_frequency", "Warning Frequency", {row["code"]: row["count"] for row in report["warning_statistics"][:12]}),
            builder.bar_chart(prefix, "coverage", "Factor Coverage", {row["factor"]: row.get("coverage") for row in report["factor_rankings"] if row.get("coverage") is not None}),
        ]
        clean = [chart for chart in charts if chart is not None]
        builder.dashboard(
            prefix=prefix,
            title=REPORT_TITLE,
            report_type="research_validation",
            metrics={
                "mode": report["mode"],
                "status": report["status"],
                "runtime_seconds": report["runtime_seconds"],
                "current_regime": report["current_regime"],
            },
            charts=clean,
            warnings=[f"{row['code']}: {row['count']}" for row in report["warning_statistics"][:10]],
            notes=report["interpretation_notes"],
        )
        return clean


def build_research_validation_report(report_input: ResearchValidationReportInput) -> dict[str, Any]:
    scope = report_input.scope
    symbol_diagnostics = report_input.symbol_diagnostics
    warning_counter = report_input.warning_counter
    report = {
        "metadata": {
            "report_type": "research_validation",
            "schema_version": REPORT_SCHEMA_VERSION,
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "release": RESEARCH_VALIDATION_RELEASE,
            "feature_development_frozen": True,
            "offline_research_only": True,
            "live_trading": False,
            "broker_integration": False,
        },
        "schema_version": REPORT_SCHEMA_VERSION,
        "run_id": report_input.run_id,
        "run_artifact_dir": str(report_input.run_dir),
        "mode": report_input.mode,
        "start_date": report_input.start,
        "end_date": report_input.end,
        "effective_start_date": report_input.effective_start,
        "effective_end_date": report_input.effective_end,
        "trading_day_count": scope["trading_day_count"],
        "frequency": "daily",
        "forward_days": DEFAULT_FORWARD_DAYS,
        "holding_period": DEFAULT_HOLDING_PERIOD,
        "symbol_count": scope["symbol_count"],
        "factor_count": scope["factor_count"],
        "estimated_observation_count": scope["estimated_observation_count"],
        "parameters": {
            "start": report_input.start,
            "end": report_input.end,
            "effective_start_date": report_input.effective_start,
            "effective_end_date": report_input.effective_end,
            "trading_day_count": scope["trading_day_count"],
            "frequency": "daily",
            "forward_days": DEFAULT_FORWARD_DAYS,
            "holding_period": DEFAULT_HOLDING_PERIOD,
            "symbol_count": scope["symbol_count"],
            "factor_count": scope["factor_count"],
            "estimated_observation_count": scope["estimated_observation_count"],
            "max_factors": report_input.max_factors,
            "max_strategies": report_input.max_strategies,
            "max_folds": report_input.folds,
            "timeout_seconds": report_input.timeout,
            "batch_size": report_input.effective_batch_size,
            "max_symbols": report_input.max_symbols,
            "factor_family": report_input.family,
            "resume": report_input.resume,
            "skip_existing": report_input.skip_existing,
            "use_cache": report_input.use_cache,
            "cache_stats": report_input.cache_stats,
            "bulk_matrix": report_input.bulk_matrix,
            "parallel": report_input.parallel,
            "workers": report_input.worker_count,
            "parallel_target": report_input.parallel_target,
            "write_substep_reports": report_input.write_substep_reports,
            "write_batch_artifacts": report_input.write_batch_artifacts,
            "write_intermediate_reports": report_input.write_intermediate_reports,
            "write_charts": report_input.write_charts,
            "write_debug_logs": report_input.write_debug_logs,
            "artifact_dir": str(report_input.run_dir),
            "universe": report_input.universe,
        },
        "symbol_diagnostics": symbol_diagnostics,
        "coverage_statistics": {
            "explicit_universe_size": symbol_diagnostics.get("requested_symbol_count"),
            "evaluated_symbols": symbol_diagnostics.get("selected_symbol_count"),
            "skipped_symbols": symbol_diagnostics.get("skipped_symbol_count"),
            "missing_price_symbols": symbol_diagnostics.get("missing_price_symbols", []),
            "price_coverage": (symbol_diagnostics.get("price_coverage") or {}).get("coverage_pct"),
            "fundamental_coverage": (symbol_diagnostics.get("fundamental_coverage") or {}).get("coverage_pct"),
        },
        "factor_store_growth": {
            "before": report_input.factor_store_before,
            "after": report_input.factor_store_after,
            "growth": report_input.factor_store_growth,
        },
        "cache_summary": report_input.cache_summary_data,
        "performance_metadata": report_input.performance_metadata,
        "regime_sample_counts": report_input.regime_sample_counts,
        "batching": {
            "batch_count": len(report_input.batches),
            "completed_batches": report_input.completed_batches,
            "skipped_batches": report_input.skipped_batches,
        },
        "charts_enabled": bool(report_input.write_charts),
        "chart_count": 0,
        "runtime_seconds": round(report_input.runtime, 6),
        "status": "WARNING" if report_input.partial or warning_counter else "PASS",
        "partial_results": report_input.partial,
        "completed_steps": [step.to_dict() for step in report_input.steps if step.status in {"PASS", "WARNING"}],
        "skipped_steps": report_input.skipped_steps,
        "timed_out_steps": [step.to_dict() for step in report_input.steps if step.status == "TIMEOUT"],
        "slowest_steps": [step.to_dict() for step in sorted(report_input.steps, key=lambda item: item.runtime_seconds, reverse=True)[:10]],
        "slow_steps": report_input.slow_steps,
        "factor_rankings": report_input.factor_rankings,
        "top_10_factors": report_input.factor_rankings[:10],
        "strategy_rankings": report_input.strategy_rankings,
        "top_5_strategies": report_input.strategy_rankings[:5],
        "current_regime": report_input.current_regime,
        "best_factor_in_current_regime": report_input.best_current_regime_factor,
        "warning_statistics": [{"code": code, "count": count} for code, count in warning_counter.most_common()],
        "factor_evidence_summary": report_input.factor_evidence_summary,
        "factor_eval_results": report_input.factor_eval_results,
        "factor_backtest_results": report_input.factor_backtest_results,
        "walk_forward_results": report_input.walk_forward_results,
        "strategy_results": report_input.strategy_results,
        "gate_results": report_input.gate_results,
        "factor_rank_report": report_input.factor_rank,
        "regime_rank_report": report_input.regime_rank,
        "recommendations": report_input.recommendations,
        "recommended_performance_work": list(RECOMMENDED_PERFORMANCE_WORK),
        "interpretation_notes": list(REPORT_INTERPRETATION_NOTES),
    }
    return report


def markdown_summary(report: dict[str, Any]) -> str:
    lines = [
        f"# {REPORT_TITLE}",
        "",
        "## Executive Summary",
        f"- Mode: {report['mode']}",
        f"- Status: {report['status']}",
        f"- Runtime seconds: {report['runtime_seconds']}",
        f"- Partial results: {report['partial_results']}",
        f"- Current regime: {report['current_regime']}",
        "",
        "## Top Factors",
    ]
    for row in report["top_10_factors"]:
        lines.append(f"- {row['factor']}: grade={row.get('evidence_grade')} rank_score={row.get('rank_score')} ic={row.get('ic')} rank_ic={row.get('rank_ic')} confidence={row.get('confidence')}")
    lines.extend(["", "## Top Strategies"])
    for row in report["top_5_strategies"]:
        lines.append(f"- {row['strategy']}: gate={row.get('gate_status')} return={row.get('total_return')} warnings={row.get('warning_count')}")
    lines.extend(["", "## Most Common Warnings"])
    for row in report["warning_statistics"][:20]:
        lines.append(f"- {row['code']}: {row['count']}")
    lines.extend(["", "## Recommendations"])
    for item in report["recommendations"]:
        lines.append(f"- {item}")
    return "\n".join(lines) + "\n"


def agent_summary(report: dict[str, Any]) -> str:
    top = report["top_10_factors"][0]["factor"] if report["top_10_factors"] else "N/A"
    top_factor = report["top_10_factors"][0] if report["top_10_factors"] else {}
    top_strategy = report["top_5_strategies"][0] if report.get("top_5_strategies") else {}
    warning = report["warning_statistics"][0]["code"] if report["warning_statistics"] else "N/A"
    best_regime = (report.get("best_factor_in_current_regime") or {}).get("factor_name")
    coverage = report.get("coverage_statistics") or {}
    return "\n".join(
        [
            "# Agent Research Validation Summary",
            f"Mode: {report['mode']}",
            "",
            "## Data Coverage",
            f"Evaluated symbols: {coverage.get('evaluated_symbols')}",
            f"Price coverage: {coverage.get('price_coverage')}",
            f"Fundamental coverage: {coverage.get('fundamental_coverage')}",
            "",
            "## Factor Evidence",
            f"Top factor: {top}",
            f"Top factor grade: {top_factor.get('evidence_grade')}",
            f"Top factor rank score: {top_factor.get('rank_score')}",
            "",
            "## Strategy Evidence",
            f"Top strategy: {top_strategy.get('strategy', 'N/A')}",
            f"Top strategy gate: {top_strategy.get('gate_status')}",
            "",
            "## Regime Context",
            f"Current regime: {report['current_regime']}",
            f"Best factor in current regime: {best_regime}",
            "Regime result is diagnostic, not conclusive.",
            "",
            "## Warnings",
            f"Most common warning: {warning}",
            "",
            "## Next Recommended Checks",
            "Improve coverage, persist more validation history, and review slow steps before full sprint runs.",
        ]
    ) + "\n"


def directory_files(path: Path) -> set[str]:
    return {str(item) for item in path.glob("*") if item.is_file()}
