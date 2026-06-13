"""Shared helpers for research validation execution phases."""

from __future__ import annotations

import time

from quant.research_validation.models import ResearchValidationPhaseState, ValidationStep


def budget_exhausted(started: float, reserve_seconds: float, timeout: float) -> bool:
    return time.monotonic() - started + reserve_seconds >= timeout


def record_skip(state: ResearchValidationPhaseState, name: str, category: str, target: str, reason: str) -> None:
    step = ValidationStep(name, category, target, "TIMEOUT" if reason == "TIMEOUT" else "SKIPPED", 0.0, warnings=[reason])
    state.steps.append(step)
    state.skipped_steps.append(step.to_dict() | {"reason": reason})
    state.warning_counter.update([reason])
