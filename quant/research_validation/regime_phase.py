"""Regime detection phase for research validation."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from quant.research_validation.models import ResearchValidationPhaseState
from quant.research_validation.phase_common import budget_exhausted, record_skip


def run_regime_phase(
    runner,
    *,
    state: ResearchValidationPhaseState,
    started: float,
    reserve_seconds: float,
    timeout: float,
    substep_dir: Path,
    write_substep_reports: bool,
) -> dict[str, Any]:
    if budget_exhausted(started, reserve_seconds, timeout):
        record_skip(state, "detect_regime", "regime", "SPY", "TIMEOUT")
        return {}
    step, result = runner._timed_step(
        "detect_regime",
        "regime",
        "SPY",
        lambda: runner._run_regime_detection(report_dir=substep_dir, write_report=write_substep_reports),
    )
    state.steps.append(step)
    state.warning_counter.update(runner._warning_codes(step.warnings))
    regime_detection = result or {}
    if regime_detection.get("report_path"):
        state.substep_report_paths.append(regime_detection["report_path"])
    return regime_detection
