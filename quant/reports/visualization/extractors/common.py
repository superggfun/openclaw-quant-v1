"""Shared data extraction helpers for report visualization."""

from __future__ import annotations

import math
from typing import Any

from quant.reports.visualization.chart_builder import ChartArtifact


def keep(*charts: ChartArtifact | None) -> list[ChartArtifact]:
    return [chart for chart in charts if chart is not None]


def finite(value: Any) -> bool:
    try:
        number = float(value)
        return math.isfinite(number)
    except (TypeError, ValueError):
        return False


def safe_float(value: Any) -> float:
    try:
        number = float(value)
        return number if math.isfinite(number) else 0.0
    except (TypeError, ValueError):
        return 0.0


def series(items: Any, label_key: str, value_key: str) -> list[tuple[str, float]]:
    output = []
    if not isinstance(items, list):
        return output
    for item in items:
        if not isinstance(item, dict):
            continue
        value = item.get(value_key)
        if finite(value):
            output.append((str(item.get(label_key, len(output) + 1)), float(value)))
    return output


def average_nested(items: list[dict[str, Any]], key: str) -> dict[str, float]:
    totals: dict[str, float] = {}
    counts: dict[str, int] = {}
    for item in items:
        values = item.get(key) or {}
        if not isinstance(values, dict):
            continue
        for label, value in values.items():
            if finite(value):
                totals[str(label)] = totals.get(str(label), 0.0) + float(value)
                counts[str(label)] = counts.get(str(label), 0) + 1
    return {
        label: totals[label] / counts[label]
        for label in sorted(totals)
        if counts.get(label)
    }


def drawdown(points: list[tuple[str, float]]) -> list[tuple[str, float]]:
    output = []
    peak = None
    for label, value in points:
        peak = value if peak is None else max(peak, value)
        output.append((label, (value / peak - 1.0) if peak else 0.0))
    return output


def drawdown_from_returns(returns: list[tuple[str, float]]) -> list[tuple[str, float]]:
    equity = 1.0
    points = []
    for label, value in returns:
        equity *= 1.0 + value
        points.append((label, equity))
    return drawdown(points)


def monthly_returns(points: list[tuple[str, float]]) -> dict[str, float]:
    by_month: dict[str, list[float]] = {}
    for label, value in points:
        by_month.setdefault(label[:7], []).append(value)
    output = {}
    for month, values in by_month.items():
        if len(values) >= 2 and values[0] != 0:
            output[month] = values[-1] / values[0] - 1.0
    return output


def items_to_mapping(items: Any, label_key: str, value_key: str) -> dict[str, float]:
    if isinstance(items, dict):
        return {str(key): float(value) for key, value in items.items() if finite(value)}
    if not isinstance(items, list):
        return {}
    output = {}
    for item in items:
        if isinstance(item, dict) and finite(item.get(value_key)):
            output[str(item.get(label_key, len(output) + 1))] = float(item[value_key])
    return output


def warning_counts(warnings: list[Any]) -> dict[str, float]:
    counts: dict[str, float] = {}
    for warning in warnings:
        text = str(warning.get("code") if isinstance(warning, dict) else warning)
        key = text.split(":")[0].split()[0]
        counts[key] = counts.get(key, 0.0) + 1.0
    return counts


def paired_average(first: dict[str, Any], second: dict[str, Any]) -> dict[str, float]:
    first_values = [float(value) for value in first.values() if finite(value)]
    second_values = [float(value) for value in second.values() if finite(value)]
    return {
        "train_average": sum(first_values) / len(first_values) if first_values else 0.0,
        "test_average": sum(second_values) / len(second_values) if second_values else 0.0,
    }


def fold_value(fold: dict[str, Any], direct_key: str, nested_key: str) -> Any:
    if direct_key in fold:
        return fold.get(direct_key)
    container = "train_metrics" if direct_key.startswith("train_") else "test_metrics"
    return (fold.get(container) or {}).get(nested_key)


def corr(xs: list[float], ys: list[float]) -> float:
    x_mean = sum(xs) / len(xs)
    y_mean = sum(ys) / len(ys)
    numerator = sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, ys, strict=False))
    x_var = sum((x - x_mean) ** 2 for x in xs)
    y_var = sum((y - y_mean) ** 2 for y in ys)
    denominator = math.sqrt(x_var * y_var)
    return numerator / denominator if denominator else 0.0


def ranks(values: list[float]) -> list[float]:
    ordered = sorted((value, index) for index, value in enumerate(values))
    output = [0.0] * len(values)
    for rank, (_, index) in enumerate(ordered, start=1):
        output[index] = float(rank)
    return output
