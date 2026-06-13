"""Data models for research validation orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ValidationStep:
    name: str
    category: str
    target: str
    status: str
    runtime_seconds: float
    report_path: str | None = None
    warnings: list[str] | None = None
    error: str | None = None
    details: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "category": self.category,
            "target": self.target,
            "status": self.status,
            "runtime_seconds": round(self.runtime_seconds, 6),
            "report_path": self.report_path,
            "warnings": list(self.warnings or []),
            "error": self.error,
            "details": self.details or {},
        }


@dataclass(frozen=True)
class ResearchValidationRunOptions:
    mode: str
    start: str | None
    end: str | None
    max_factors: int | None
    max_strategies: int | None
    max_folds: int | None
    folds: int
    timeout_seconds: float
    batch_size: int | None
    max_symbols: int | None
    factor_family: str
    resume: bool
    skip_existing: bool
    use_cache: bool
    cache_stats: bool
    bulk_matrix: bool
    parallel: bool
    workers: int | None
    worker_count: int
    parallel_target: str
    charts: bool
    write_substep_reports: bool
    write_batch_artifacts: bool
    write_intermediate_reports: bool
    write_debug_logs: bool
    artifact_dir: str | Path | None


@dataclass(frozen=True)
class ResearchValidationRunContext:
    run_id: str
    run_dir: Path
    substep_dir: Path
    batch_artifact_dir: Path
    chart_dir: Path
    log_dir: Path
