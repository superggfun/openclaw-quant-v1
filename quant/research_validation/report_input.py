"""Explicit input boundary for research validation report assembly."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from quant.research_validation.models import ValidationStep


@dataclass(kw_only=True)
class ResearchValidationReportInput:
    scope: dict[str, Any]
    symbol_diagnostics: dict[str, Any]
    warning_counter: Counter[str]
    run_id: str
    run_dir: Path
    mode: str
    start: str | None
    end: str | None
    effective_start: str | None
    effective_end: str | None
    max_factors: int | None
    max_strategies: int | None
    folds: int
    timeout: float
    effective_batch_size: int
    max_symbols: int | None
    family: str
    resume: bool
    skip_existing: bool
    use_cache: bool
    cache_stats: bool
    bulk_matrix: bool
    parallel: bool
    worker_count: int
    matrix_workers: int
    parallel_target: str
    write_substep_reports: bool
    write_batch_artifacts: bool
    write_intermediate_reports: bool
    write_charts: bool
    write_debug_logs: bool
    universe: list[str]
    factor_store_before: dict[str, int]
    factor_store_after: dict[str, int]
    factor_store_growth: dict[str, int]
    cache_summary_data: dict[str, Any]
    performance_metadata: dict[str, Any]
    regime_sample_counts: dict[str, int]
    batches: list[list[str]]
    completed_batches: list[dict[str, Any]]
    skipped_batches: list[dict[str, Any]]
    runtime: float
    partial: bool
    steps: list[ValidationStep]
    skipped_steps: list[dict[str, Any]]
    slow_steps: list[dict[str, Any]]
    factor_rankings: list[dict[str, Any]]
    strategy_rankings: list[dict[str, Any]]
    current_regime: str | None
    best_current_regime_factor: dict[str, Any] | None
    factor_evidence_summary: dict[str, Any]
    factor_eval_results: list[dict[str, Any]]
    factor_backtest_results: list[dict[str, Any]]
    walk_forward_results: list[dict[str, Any]]
    strategy_results: list[dict[str, Any]]
    gate_results: list[dict[str, Any]]
    factor_rank: dict[str, Any]
    regime_rank: dict[str, Any]
    recommendations: list[dict[str, Any]]
