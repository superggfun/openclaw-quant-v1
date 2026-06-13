"""Factor and fundamental visualization extractors."""

from __future__ import annotations

from typing import Any

from quant.reports.visualization.chart_builder import ChartArtifact, ChartBuilder
from quant.reports.visualization.extractors.common import (
    average_nested,
    corr,
    finite,
    items_to_mapping,
    keep,
    ranks,
    series,
    warning_counts,
)
from quant.reports.visualization.specs import report_spec


def factor_eval_charts(builder: ChartBuilder, prefix: str, report: dict[str, Any]) -> list[ChartArtifact]:
    ic_history, rank_history = _factor_eval_history(report.get("observations") or [])
    ic_values = {str(index + 1): value for index, (_, value) in enumerate(ic_history)}
    decay = {
        horizon: values.get("ic")
        for horizon, values in (report.get("decay") or {}).items()
        if isinstance(values, dict)
    }
    return keep(
        builder.line_chart(prefix, "ic_history", "IC History", ic_history),
        builder.line_chart(prefix, "rank_ic_history", "Rank IC History", rank_history),
        builder.bar_chart(prefix, "ic_distribution", "IC Distribution", ic_values),
        builder.bar_chart(prefix, "quintile_returns", "Quintile Returns", report.get("quintiles") or {}),
        builder.line_chart(prefix, "factor_decay", "Factor Decay", list(decay.items())),
    )


def fundamental_coverage_charts(builder: ChartBuilder, prefix: str, report: dict[str, Any]) -> list[ChartArtifact]:
    coverage = report.get("coverage") or {}
    return keep(builder.bar_chart(prefix, "statement_coverage", "Statement Coverage", coverage.get("statement_coverage") or {}))


def fundamental_quality_charts(builder: ChartBuilder, prefix: str, report: dict[str, Any]) -> list[ChartArtifact]:
    return keep(builder.bar_chart(prefix, "warnings_by_reason", "Warnings By Reason", warning_counts(report.get("warnings") or [])))


def multi_factor_charts(builder: ChartBuilder, prefix: str, report: dict[str, Any]) -> list[ChartArtifact]:
    scores = [item for item in (report.get("scores") or []) if isinstance(item, dict)]
    top = sorted(
        scores,
        key=lambda item: (float(item.get("final_alpha_score") or -999), str(item.get("symbol"))),
        reverse=True,
    )[:5]
    confidence = {
        item.get("symbol", f"symbol_{index + 1}"): item.get("overall_confidence")
        for index, item in enumerate(top)
    }
    stability = {
        factor: values.get("score")
        for factor, values in (report.get("stability") or {}).items()
        if isinstance(values, dict)
    }
    return keep(
        builder.bar_chart(prefix, "family_contribution", "Family Contribution", average_nested(top, "family_contributions")),
        builder.bar_chart(prefix, "factor_contribution", "Factor Contribution", average_nested(top, "factor_contributions")),
        builder.bar_chart(prefix, "confidence", "Confidence", confidence),
        builder.bar_chart(prefix, "stability_ranking", "Stability Ranking", stability),
    )


def factor_store_summary_charts(builder: ChartBuilder, prefix: str, report: dict[str, Any]) -> list[ChartArtifact]:
    return keep(builder.bar_chart(prefix, "factor_store_counts", "Factor Store Counts", report.get("counts") or {}))


def factor_history_charts(builder: ChartBuilder, prefix: str, report: dict[str, Any]) -> list[ChartArtifact]:
    evaluations = report.get("evaluation_history") or []
    stability = report.get("stability_history") or []
    return keep(
        builder.line_chart(prefix, "ic_history", "IC History", series(evaluations, "evaluation_date", "ic")),
        builder.line_chart(prefix, "rank_ic_history", "RankIC History", series(evaluations, "evaluation_date", "rank_ic")),
        builder.line_chart(prefix, "stability_history", "Stability History", series(stability, "timestamp", "stability_score")),
        builder.line_chart(prefix, "coverage_history", "Coverage History", series(evaluations, "evaluation_date", "coverage")),
    )


def factor_rank_charts(builder: ChartBuilder, prefix: str, report: dict[str, Any]) -> list[ChartArtifact]:
    return keep(
        builder.bar_chart(prefix, "factor_ranking", "Factor Ranking", items_to_mapping(report.get("top_factors"), "factor_name", "health_score")),
        builder.bar_chart(prefix, "stability_ranking", "Stability Ranking", items_to_mapping(report.get("most_stable_factors"), "factor_name", "stability_score")),
        builder.bar_chart(prefix, "coverage_ranking", "Coverage Ranking", items_to_mapping(report.get("top_factors"), "factor_name", "coverage")),
    )


def _factor_eval_history(observations: list[dict]) -> tuple[list[tuple[str, float]], list[tuple[str, float]]]:
    by_date: dict[str, list[tuple[float, float]]] = {}
    for row in observations:
        if not isinstance(row, dict):
            continue
        factor = row.get("factor_value")
        future = row.get("future_return")
        if finite(factor) and finite(future):
            by_date.setdefault(str(row.get("signal_date")), []).append((float(factor), float(future)))
    ic_history = []
    rank_history = []
    for date in sorted(by_date):
        pairs = by_date[date]
        if len(pairs) < 2:
            continue
        xs = [pair[0] for pair in pairs]
        ys = [pair[1] for pair in pairs]
        ic_history.append((date, corr(xs, ys)))
        rank_history.append((date, corr(ranks(xs), ranks(ys))))
    return ic_history, rank_history


REPORT_SPECS = (
    report_spec("factor_eval", ("ic_history", "rank_ic_history", "ic_distribution", "quintile_returns", "factor_decay"), factor_eval_charts),
    report_spec("fundamental_coverage", ("statement_coverage",), fundamental_coverage_charts),
    report_spec("fundamental_quality", ("warnings_by_reason",), fundamental_quality_charts),
    report_spec("multi_factor", ("family_contribution", "factor_contribution", "confidence", "stability_ranking"), multi_factor_charts),
    report_spec("factor_store_summary", ("factor_store_counts",), factor_store_summary_charts),
    report_spec("factor_history", ("ic_history", "rank_ic_history", "stability_history", "coverage_history"), factor_history_charts),
    report_spec("factor_rank", ("factor_ranking", "stability_ranking", "coverage_ranking"), factor_rank_charts),
)
