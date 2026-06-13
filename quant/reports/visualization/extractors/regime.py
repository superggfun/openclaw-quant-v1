"""Regime visualization extractors."""

from __future__ import annotations

from typing import Any

from quant.reports.visualization.chart_builder import ChartArtifact, ChartBuilder
from quant.reports.visualization.extractors.common import items_to_mapping, keep, safe_float, series
from quant.reports.visualization.specs import report_spec


def regime_detection_charts(builder: ChartBuilder, prefix: str, report: dict[str, Any]) -> list[ChartArtifact]:
    return _regime_sequence_charts(builder, prefix, report, report.get("observations") or [])


def regime_history_charts(builder: ChartBuilder, prefix: str, report: dict[str, Any]) -> list[ChartArtifact]:
    return _regime_sequence_charts(builder, prefix, report, list(reversed(report.get("history") or [])))


def regime_report_charts(builder: ChartBuilder, prefix: str, report: dict[str, Any]) -> list[ChartArtifact]:
    return keep(
        builder.bar_chart(prefix, "regime_frequency", "Regime Frequency", report.get("regime_counts") or {}),
        builder.bar_chart(prefix, "factor_performance_by_regime", "Factor Performance By Regime", _factor_regime_mapping(report)),
    )


def regime_rank_charts(builder: ChartBuilder, prefix: str, report: dict[str, Any]) -> list[ChartArtifact]:
    return keep(
        builder.bar_chart(prefix, "factor_performance_by_regime", "Best Factor By Regime", _best_by_regime_mapping(report)),
        builder.bar_chart(prefix, "regime_stability", "Regime Stability", items_to_mapping(report.get("most_stable_across_regimes"), "factor_name", "stability")),
    )


def _regime_sequence_charts(builder: ChartBuilder, prefix: str, report: dict[str, Any], rows: list[dict[str, Any]]) -> list[ChartArtifact]:
    return keep(
        builder.line_chart(prefix, "regime_timeline", "Regime Timeline", _regime_timeline(rows)),
        builder.bar_chart(prefix, "regime_frequency", "Regime Frequency", report.get("regime_counts") or {}),
        builder.line_chart(prefix, "regime_confidence", "Regime Confidence", series(rows, "date", "confidence")),
    )


def _regime_timeline(items: list[dict[str, Any]]) -> list[tuple[str, float]]:
    order = {
        "UNKNOWN": 0,
        "LOW_VOL": 1,
        "RANGE_BOUND": 2,
        "BULL": 3,
        "TRENDING": 4,
        "RECOVERY": 5,
        "HIGH_VOL": 6,
        "BEAR": 7,
        "CRISIS": 8,
    }
    return [
        (str(item.get("date")), float(order.get(str(item.get("regime") or "UNKNOWN"), 0)))
        for item in items
        if item.get("date")
    ]


def _factor_regime_mapping(report: dict[str, Any]) -> dict[str, float]:
    output = {}
    for regime, rows in (report.get("factor_performance_by_regime") or {}).items():
        if isinstance(rows, list) and rows:
            best = max(rows, key=lambda row: safe_float(row.get("icir")))
            output[str(regime)] = safe_float(best.get("icir"))
    return output


def _best_by_regime_mapping(report: dict[str, Any]) -> dict[str, float]:
    output = {}
    for regime, rows in (report.get("best_by_regime") or {}).items():
        if isinstance(rows, list) and rows:
            output[str(regime)] = safe_float(rows[0].get("health_score"))
    return output


REPORT_SPECS = (
    report_spec("regime_detection", ("regime_timeline", "regime_frequency", "regime_confidence"), regime_detection_charts),
    report_spec("regime_history", ("regime_timeline", "regime_frequency", "regime_confidence"), regime_history_charts),
    report_spec("regime_report", ("regime_frequency", "factor_performance_by_regime"), regime_report_charts),
    report_spec("regime_rank", ("factor_performance_by_regime", "regime_stability"), regime_rank_charts),
)
