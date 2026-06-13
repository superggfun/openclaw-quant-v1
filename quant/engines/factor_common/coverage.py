"""Shared factor coverage helpers."""

from __future__ import annotations

from typing import Any, Iterable


def factor_coverage(factor_registry: Any, factor: str, symbols: list[str], observations: Iterable[Any]) -> dict | None:
    if not factor_registry.is_fundamental(factor):
        return None

    observation_rows = list(observations)
    covered_symbols = sorted({str(getattr(observation, "symbol")) for observation in observation_rows})
    missing_symbols = sorted(set(symbols) - set(covered_symbols))
    total_symbols = len(symbols)
    coverage_pct = (len(covered_symbols) / total_symbols) if total_symbols else 0.0
    metadata = factor_registry.metadata(factor)
    report_dates = []
    statement = str(metadata.get("fundamental_statement") or "fundamental_metrics")

    for observation in observation_rows:
        row = factor_registry.latest_fundamental_row(
            str(getattr(observation, "symbol")),
            statement,
            str(getattr(observation, "signal_date")),
        )
        if row and row.get("report_date"):
            report_dates.append(str(row["report_date"]))

    return {
        "coverage_percentage": coverage_pct,
        "missing_percentage": 1.0 - coverage_pct,
        "covered_symbols": covered_symbols,
        "missing_symbols": missing_symbols,
        "fundamental_metrics_used": metadata.get("fundamental_metrics_used") or [],
        "report_date_coverage": {
            "earliest_report_date": min(report_dates) if report_dates else None,
            "latest_report_date": max(report_dates) if report_dates else None,
            "observations_with_report_date": len(report_dates),
        },
        "no_lookahead_filter": "report_date <= signal_date",
    }


def factor_coverage_warnings(factor: str, coverage: dict | None) -> list[str]:
    if coverage is None:
        return []
    if not coverage["covered_symbols"]:
        return [f"MISSING_FUNDAMENTAL_DATA: {factor} has no symbols with usable report_date-filtered fundamentals"]
    if coverage["missing_symbols"]:
        return [f"PARTIAL_FUNDAMENTAL_DATA: {factor} covers {coverage['coverage_percentage']:.2%} of the universe"]
    return []
