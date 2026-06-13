"""Extracted static / shared utility functions for research validation."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from quant.research_validation.ranking import coverage as ranking_coverage
from quant.research_validation.ranking import num as ranking_num
from quant.research_validation.report_writer import directory_files as report_writer_directory_files


def coverage_pct(coverage: dict | None) -> float | None:
    if not coverage:
        return None
    return coverage.get("coverage_percentage")


def factor_evidence_summary(evals: list[dict[str, Any]], backtests: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for result in evals:
        factor = result.get("factor")
        if not factor:
            continue
        row = rows.setdefault(factor, {"factor": factor, "eval_batches": 0, "backtest_batches": 0, "observations": 0})
        row["eval_batches"] += 1
        row["observations"] += int(result.get("observation_count") or len(result.get("observations") or []))
        row["latest_ic"] = result.get("ic_mean")
        row["latest_rank_ic"] = result.get("rank_ic_mean")
        row["latest_icir"] = result.get("icir")
    for result in backtests:
        factor = result.get("factor")
        if not factor:
            continue
        row = rows.setdefault(factor, {"factor": factor, "eval_batches": 0, "backtest_batches": 0, "observations": 0})
        row["backtest_batches"] += 1
        row["latest_long_short_return"] = result.get("long_short_return")
        row["latest_sharpe"] = result.get("long_short_sharpe") if result.get("long_short_sharpe") is not None else result.get("sharpe")
    return sorted(rows.values(), key=lambda row: row["factor"])


def has_existing_factor_values(runner, factor: str, symbols: list[str]) -> bool:
    if not symbols:
        return False
    placeholders = ",".join("?" for _ in symbols)
    query = f"""
        SELECT COUNT(DISTINCT symbol) AS symbol_count
        FROM factor_values
        WHERE factor_name = ? AND symbol IN ({placeholders})
    """
    try:
        with runner.context.factor_store.connect() as connection:
            row = connection.execute(query, [factor, *symbols]).fetchone()
        return int(row["symbol_count"] if hasattr(row, "keys") else row[0]) >= len(symbols)
    except Exception:
        return False


def factor_store_counts(runner) -> dict[str, int]:
    tables = [
        "factor_values",
        "factor_evaluation_history",
        "factor_backtest_history",
        "factor_walk_forward_history",
        "factor_stability_history",
    ]
    counts: dict[str, int] = {}
    with runner.context.factor_store.connect() as connection:
        for table in tables:
            try:
                row = connection.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()
                counts[table] = int(row["count"])
            except Exception:
                counts[table] = 0
    return counts


def directory_files(path: Path) -> set[str]:
    return report_writer_directory_files(path)


def warning_codes(warnings: list[Any]) -> list[str]:
    output = []
    for warning in warnings:
        if isinstance(warning, dict):
            output.append(str(warning.get("code") or "WARN_UNKNOWN"))
        else:
            output.append(str(warning).split(":", 1)[0])
    return [code for code in output if code]


def report_coverage(report: dict[str, Any]) -> float | None:
    """Evaluate coverage from a factor report dict (delegates to ranking.coverage)."""
    return ranking_coverage(report)


def safe_num(value: Any) -> float | None:
    """Safe numeric conversion (delegates to ranking.num)."""
    return ranking_num(value)
