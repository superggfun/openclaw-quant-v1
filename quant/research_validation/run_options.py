"""Option normalization for research validation runs."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from quant.research_validation.models import ResearchValidationRunOptions


def normalize_run_options(
    *,
    config: Any,
    scope_planner: Any,
    mode: str,
    start: str | None,
    end: str | None,
    max_factors: int | None,
    max_strategies: int | None,
    max_folds: int | None,
    timeout_seconds: float | None,
    batch_size: int | None,
    max_symbols: int | None,
    factor_family: str,
    resume: bool,
    skip_existing: bool,
    use_cache: bool,
    cache_stats: bool,
    bulk_matrix: bool,
    prefer_in_memory: bool,
    strict_in_memory: bool,
    parallel: bool,
    workers: int | None,
    parallel_target: str,
    charts: bool,
    write_substep_reports: bool,
    write_batch_artifacts: bool,
    write_intermediate_reports: bool,
    write_debug_logs: bool,
    artifact_dir: str | Path | None,
) -> ResearchValidationRunOptions:
    normalized_mode = mode.strip().lower()
    if normalized_mode not in {"quick", "full"}:
        raise ValueError("mode must be quick or full")
    if use_cache and bulk_matrix:
        raise ValueError("--use-cache and --bulk-matrix are mutually exclusive; pass --no-bulk-matrix to use cache")
    family = factor_family.strip().lower()
    if family not in {"price", "fundamental", "all"}:
        raise ValueError("factor_family must be price, fundamental, or all")
    normalized_parallel_target = parallel_target.strip().lower()
    if normalized_parallel_target != "factor_batch":
        raise ValueError("parallel_target must be factor_batch")

    default_timeout = config.quick_default_timeout_seconds if normalized_mode == "quick" else config.full_default_timeout_seconds
    return ResearchValidationRunOptions(
        mode=normalized_mode,
        start=start,
        end=end,
        max_factors=max_factors,
        max_strategies=max_strategies,
        max_folds=max_folds,
        folds=max_folds if max_folds is not None else (1 if normalized_mode == "quick" else 5),
        timeout_seconds=float(timeout_seconds if timeout_seconds is not None else default_timeout),
        batch_size=batch_size,
        max_symbols=max_symbols,
        factor_family=family,
        resume=resume,
        skip_existing=skip_existing,
        use_cache=use_cache,
        cache_stats=cache_stats,
        bulk_matrix=bulk_matrix,
        prefer_in_memory=prefer_in_memory,
        strict_in_memory=strict_in_memory,
        parallel=parallel,
        workers=workers,
        worker_count=scope_planner.worker_count(parallel=parallel, workers=workers),
        matrix_workers=1 if parallel else max(1, workers or 4),
        parallel_target=normalized_parallel_target,
        charts=charts,
        write_substep_reports=write_substep_reports,
        write_batch_artifacts=write_batch_artifacts,
        write_intermediate_reports=write_intermediate_reports,
        write_debug_logs=write_debug_logs,
        artifact_dir=artifact_dir,
    )
