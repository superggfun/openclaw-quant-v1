"""Walk-forward validation phase for research validation."""

from __future__ import annotations

from pathlib import Path

from quant.research_validation.models import ResearchValidationPhaseState
from quant.research_validation.phase_common import budget_exhausted, record_skip


def run_walk_forward_phase(
    runner,
    *,
    state: ResearchValidationPhaseState,
    factors: list[str],
    folds: int,
    universe: list[str],
    started: float,
    reserve_seconds: float,
    timeout: float,
    effective_start: str | None,
    effective_end: str | None,
    substep_dir: Path,
    write_substep_reports: bool,
) -> None:
    for factor in runner._major_factors(factors):
        if budget_exhausted(started, reserve_seconds, timeout):
            record_skip(state, "walk_forward", "factor", factor, "TIMEOUT")
            continue
        step, result = runner._timed_step(
            "walk_forward",
            "factor",
            factor,
            lambda f=factor: runner._run_walk_forward_factor(
                f,
                folds,
                universe,
                effective_start,
                effective_end,
                report_dir=substep_dir,
                write_report=write_substep_reports,
            ),
        )
        state.steps.append(step)
        state.warning_counter.update(runner._warning_codes(step.warnings))
        if result:
            if result.get("report_path"):
                state.substep_report_paths.append(result["report_path"])
            state.walk_forward_results.append(result)
