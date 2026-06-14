"""Strategy validation phase for research validation."""

from __future__ import annotations

import json
from pathlib import Path

from quant.research_validation.models import ResearchValidationPhaseState
from quant.research_validation.phase_common import budget_exhausted, record_skip


def run_strategy_phase(
    runner,
    *,
    state: ResearchValidationPhaseState,
    strategies: list[str],
    started: float,
    reserve_seconds: float,
    timeout: float,
    effective_start: str | None,
    effective_end: str | None,
    substep_dir: Path,
    cost_profile: str,
    write_substep_reports: bool,
    write_intermediate_reports: bool,
) -> None:
    for strategy in strategies:
        if budget_exhausted(started, reserve_seconds, timeout):
            record_skip(state, "strategy_run_with_gates", "strategy", strategy, "TIMEOUT")
            continue
        step, result = runner._timed_step(
            "strategy_run_with_gates",
            "strategy",
            strategy,
            lambda s=strategy: runner._run_strategy(
                s,
                effective_start,
                effective_end,
                report_dir=substep_dir,
                cost_profile=cost_profile,
                write_report=write_substep_reports,
                write_intermediate_reports=write_intermediate_reports,
            ),
        )
        state.steps.append(step)
        state.warning_counter.update(runner._warning_codes(step.warnings))
        if result:
            state.strategy_results.append(result)
            state.substep_report_paths.extend([path for path in result.get("generated_reports", []) if path])
            gate_path = ((result.get("artifacts") or {}).get("strategy_gate_report_path"))
            if gate_path:
                try:
                    gate_report = json.loads(Path(gate_path).read_text(encoding="utf-8"))
                    state.gate_results.append(gate_report)
                    state.warning_counter.update(runner._warning_codes(gate_report.get("warnings") or []))
                except (FileNotFoundError, json.JSONDecodeError):
                    state.warning_counter.update(["WARN_GATE_REPORT_UNREADABLE"])
