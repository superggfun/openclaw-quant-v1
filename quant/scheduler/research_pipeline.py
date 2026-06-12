"""Research pipeline primitives with failure isolation."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from time import perf_counter
from typing import Any, Callable


@dataclass
class PipelineStep:
    """Single scheduler step result."""

    name: str
    status: str
    start_time: str
    end_time: str
    duration_seconds: float
    warnings: list[str] = field(default_factory=list)
    artifacts: list[str] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


class ResearchPipeline:
    """Run pipeline steps while isolating failures."""

    def __init__(self) -> None:
        self.steps: list[PipelineStep] = []

    def run_step(self, name: str, enabled: bool, action: Callable[[], dict[str, Any]]) -> PipelineStep:
        start = datetime.now()
        timer = perf_counter()
        if not enabled:
            step = PipelineStep(
                name=name,
                status="SKIPPED",
                start_time=start.isoformat(timespec="seconds"),
                end_time=start.isoformat(timespec="seconds"),
                duration_seconds=0.0,
                summary={"skip_reason": "disabled_by_config"},
            )
            self.steps.append(step)
            return step
        try:
            result = action()
            status = str(result.get("status") or "PASS")
            warnings = [str(item) for item in result.get("warnings") or []]
            artifacts = [str(item) for item in result.get("artifacts") or [] if item]
            summary = dict(result.get("summary") or {})
            error = result.get("error")
        except Exception as exc:  # Failure isolation is a scheduler feature.
            status = "FAIL"
            warnings = [f"WARN_PIPELINE_STEP_FAILED: {name}: {exc}"]
            artifacts = []
            summary = {}
            error = str(exc)
        end = datetime.now()
        step = PipelineStep(
            name=name,
            status=status,
            start_time=start.isoformat(timespec="seconds"),
            end_time=end.isoformat(timespec="seconds"),
            duration_seconds=round(perf_counter() - timer, 6),
            warnings=warnings,
            artifacts=artifacts,
            summary=summary,
            error=error,
        )
        self.steps.append(step)
        return step

    def to_list(self) -> list[dict[str, Any]]:
        return [step.__dict__ for step in self.steps]
