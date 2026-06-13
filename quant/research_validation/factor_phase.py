"""Factor evaluation and backtest phases for research validation."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from quant.factor_acceleration import FactorBatchTask
from quant.research_validation.config import DEFAULT_FORWARD_DAYS, DEFAULT_HOLDING_PERIOD
from quant.research_validation.models import ResearchValidationPhaseState, ValidationStep
from quant.research_validation.phase_common import budget_exhausted, record_skip


def run_factor_validation_phase(
    runner,
    *,
    state: ResearchValidationPhaseState,
    factors: list[str],
    batches: list[list[str]],
    started: float,
    reserve_seconds: float,
    timeout: float,
    parallel: bool,
    worker_count: int,
    skip_existing: bool,
    resume: bool,
    bulk_matrix: bool,
    effective_start: str | None,
    effective_end: str | None,
    write_substep_reports: bool,
    write_batch_artifacts: bool,
    substep_dir: Path,
    batch_artifact_dir: Path,
) -> None:
    pending_factor_evals: list[Any] = []
    pending_factor_backtests: list[Any] = []
    pending_regime_items: list[tuple[str, list[dict], str | None]] = []

    if parallel:
        _run_parallel_factor_phase(
            runner,
            state=state,
            factors=factors,
            batches=batches,
            started=started,
            reserve_seconds=reserve_seconds,
            timeout=timeout,
            worker_count=worker_count,
            skip_existing=skip_existing,
            resume=resume,
            bulk_matrix=bulk_matrix,
            effective_start=effective_start,
            effective_end=effective_end,
            write_substep_reports=write_substep_reports,
            write_batch_artifacts=write_batch_artifacts,
            substep_dir=substep_dir,
            batch_artifact_dir=batch_artifact_dir,
            pending_factor_evals=pending_factor_evals,
            pending_factor_backtests=pending_factor_backtests,
            pending_regime_items=pending_regime_items,
        )

    if pending_factor_evals or pending_factor_backtests or pending_regime_items:
        write_started = time.monotonic()
        eval_saved = runner.context.factor_store.save_factor_evaluations(pending_factor_evals)
        backtest_saved = runner.context.factor_store.save_factor_backtests(pending_factor_backtests)
        regime_saved = runner.context.factor_store.save_factor_regime_history_many(pending_regime_items)
        state.factor_store_write_seconds = time.monotonic() - write_started
        state.batch_write_summary = {
            "factor_evaluations": len(eval_saved),
            "factor_backtests": len(backtest_saved),
            "regime_items": len(pending_regime_items),
            "regime_rows": regime_saved.get("saved_regime_rows", 0),
            "sqlite_write_mode": "batched_main_process",
        }

    _run_serial_factor_eval_phase(
        runner,
        state=state,
        factors=factors,
        batches=batches,
        started=started,
        reserve_seconds=reserve_seconds,
        timeout=timeout,
        skip_existing=skip_existing,
        resume=resume,
        bulk_matrix=bulk_matrix,
        effective_start=effective_start,
        effective_end=effective_end,
        write_substep_reports=write_substep_reports,
        substep_dir=substep_dir,
    )
    _run_serial_factor_backtest_phase(
        runner,
        state=state,
        factors=factors,
        batches=batches,
        started=started,
        reserve_seconds=reserve_seconds,
        timeout=timeout,
        bulk_matrix=bulk_matrix,
        effective_start=effective_start,
        effective_end=effective_end,
        write_substep_reports=write_substep_reports,
        write_batch_artifacts=write_batch_artifacts,
        substep_dir=substep_dir,
        batch_artifact_dir=batch_artifact_dir,
    )


def _run_parallel_factor_phase(
    runner,
    *,
    state: ResearchValidationPhaseState,
    factors: list[str],
    batches: list[list[str]],
    started: float,
    reserve_seconds: float,
    timeout: float,
    worker_count: int,
    skip_existing: bool,
    resume: bool,
    bulk_matrix: bool,
    effective_start: str | None,
    effective_end: str | None,
    write_substep_reports: bool,
    write_batch_artifacts: bool,
    substep_dir: Path,
    batch_artifact_dir: Path,
    pending_factor_evals: list[Any],
    pending_factor_backtests: list[Any],
    pending_regime_items: list[tuple[str, list[dict], str | None]],
) -> None:
    parallel_tasks: list[FactorBatchTask] = []
    for factor in factors:
        for batch_index, batch in enumerate(batches, start=1):
            target = f"{factor} batch {batch_index}/{len(batches)}"
            if budget_exhausted(started, reserve_seconds, timeout):
                record_skip(state, "factor_eval", "factor", target, "TIMEOUT")
                continue
            if (skip_existing or resume) and runner._has_existing_factor_values(factor, batch):
                state.skipped_batches.append(
                    {
                        "step": "factor_eval",
                        "factor": factor,
                        "batch_index": batch_index,
                        "symbols": batch,
                        "reason": "SKIP_EXISTING",
                    }
                )
                record_skip(state, "factor_eval", "factor", target, "SKIP_EXISTING")
                continue
            parallel_tasks.append(
                FactorBatchTask(
                    kind="factor_eval",
                    factor=factor,
                    batch_index=batch_index,
                    batch_count=len(batches),
                    symbols=batch,
                    db_path=str(runner.context.db_path),
                    report_dir=str(substep_dir if write_substep_reports else runner.report_dir),
                    bulk_matrix=bulk_matrix,
                    start=effective_start,
                    end=effective_end,
                    forward_days=DEFAULT_FORWARD_DAYS,
                    holding_period=DEFAULT_HOLDING_PERIOD,
                    write_report=write_substep_reports,
                )
            )
    for factor in factors:
        for batch_index, batch in enumerate(batches, start=1):
            if budget_exhausted(started, reserve_seconds, timeout):
                record_skip(state, "factor_backtest", "factor", f"{factor} batch {batch_index}/{len(batches)}", "TIMEOUT")
                continue
            parallel_tasks.append(
                FactorBatchTask(
                    kind="factor_backtest",
                    factor=factor,
                    batch_index=batch_index,
                    batch_count=len(batches),
                    symbols=batch,
                    db_path=str(runner.context.db_path),
                    report_dir=str(substep_dir if write_substep_reports else runner.report_dir),
                    bulk_matrix=bulk_matrix,
                    start=effective_start,
                    end=effective_end,
                    forward_days=DEFAULT_FORWARD_DAYS,
                    holding_period=DEFAULT_HOLDING_PERIOD,
                    write_report=write_substep_reports,
                )
            )
    try:
        parallel_budget = max(timeout - (time.monotonic() - started) - reserve_seconds, 0.0)
        state.factor_eval_serial = False
        state.factor_backtest_serial = False

        def handle_parallel_result(item) -> None:
            _handle_parallel_factor_result(
                runner,
                state=state,
                item=item,
                write_batch_artifacts=write_batch_artifacts,
                batch_artifact_dir=batch_artifact_dir,
                pending_factor_evals=pending_factor_evals,
                pending_factor_backtests=pending_factor_backtests,
                pending_regime_items=pending_regime_items,
            )

        parallel_compute_started = time.monotonic()
        runner._run_factor_batch_tasks(parallel_tasks, worker_count, timeout_seconds=parallel_budget, on_result=handle_parallel_result)
        state.parallel_compute_seconds = time.monotonic() - parallel_compute_started
    except Exception as exc:
        state.factor_eval_serial = True
        state.factor_backtest_serial = True
        pending_factor_evals.clear()
        pending_factor_backtests.clear()
        pending_regime_items.clear()
        state.warning_counter.update(["PARALLEL_FALLBACK_SERIAL"])
        state.steps.append(
            ValidationStep(
                "parallel_factor_batch",
                "factor",
                "factor_batch",
                "WARNING",
                0.0,
                warnings=["PARALLEL_FALLBACK_SERIAL"],
                error=str(exc),
                details={"workers": worker_count},
            )
        )


def _handle_parallel_factor_result(
    runner,
    *,
    state: ResearchValidationPhaseState,
    item,
    write_batch_artifacts: bool,
    batch_artifact_dir: Path,
    pending_factor_evals: list[Any],
    pending_factor_backtests: list[Any],
    pending_regime_items: list[tuple[str, list[dict], str | None]],
) -> None:
    result = item.result
    step = ValidationStep(
        item.task.kind,
        "factor",
        item.task.target,
        item.status,
        item.runtime_seconds,
        getattr(result, "report_path", None) if result is not None else None,
        item.warnings,
        item.error,
        details={
            "factor": item.task.factor,
            "batch_index": item.task.batch_index,
            "symbols_evaluated": item.task.symbols,
            "parallel": True,
        },
    )
    state.steps.append(step)
    state.warning_counter.update(runner._warning_codes(step.warnings or []))
    if result is None:
        return
    if item.task.kind == "factor_eval":
        finalize_started = time.monotonic()
        compact_started = time.monotonic()
        report_result = runner._compact_factor_eval_result(result, item.task)
        if result.report_path:
            state.substep_report_paths.append(result.report_path)
        state.report_compaction_seconds += time.monotonic() - compact_started
        pending_factor_evals.append(result)
        pending_regime_items.append((result.factor, runner._factor_regime_rows_from_evaluation(result), result.report_path))
        state.parallel_finalize_seconds += time.monotonic() - finalize_started
        state.factor_eval_results.append(report_result)
        state.completed_batches.append(
            {
                "step": "factor_eval",
                "factor": item.task.factor,
                "batch_index": item.task.batch_index,
                "symbols_evaluated": item.task.symbols,
                "observations": int(report_result.get("observation_count") or len(report_result.get("observations") or [])),
                "runtime_seconds": step.runtime_seconds,
                "status": step.status,
                "report_path": step.report_path,
                "parallel": True,
            }
        )
    elif item.task.kind == "factor_backtest":
        finalize_started = time.monotonic()
        compact_started = time.monotonic()
        artifact_path = ""
        if write_batch_artifacts:
            artifact_path = runner._write_batch_artifact("factor_backtest", item.task, result.to_report(), batch_artifact_dir)
            state.artifact_paths.append(artifact_path)
            state.detailed_artifact_count += 1
        if result.report_path:
            state.substep_report_paths.append(result.report_path)
        report_result = runner._compact_factor_backtest_result(result, item.task, artifact_path)
        state.report_compaction_seconds += time.monotonic() - compact_started
        pending_factor_backtests.append(result)
        pending_regime_items.append((result.factor, runner._factor_regime_rows_from_backtest(result), result.report_path))
        state.parallel_finalize_seconds += time.monotonic() - finalize_started
        state.factor_backtest_results.append(report_result)
        state.completed_batches.append(
            {
                "step": "factor_backtest",
                "factor": item.task.factor,
                "batch_index": item.task.batch_index,
                "symbols_evaluated": item.task.symbols,
                "observations": report_result.get("observation_count"),
                "runtime_seconds": step.runtime_seconds,
                "status": step.status,
                "report_path": step.report_path,
                "parallel": True,
            }
        )


def _run_serial_factor_eval_phase(
    runner,
    *,
    state: ResearchValidationPhaseState,
    factors: list[str],
    batches: list[list[str]],
    started: float,
    reserve_seconds: float,
    timeout: float,
    skip_existing: bool,
    resume: bool,
    bulk_matrix: bool,
    effective_start: str | None,
    effective_end: str | None,
    write_substep_reports: bool,
    substep_dir: Path,
) -> None:
    for factor in ([] if not state.factor_eval_serial else factors):
        for batch_index, batch in enumerate(batches, start=1):
            target = f"{factor} batch {batch_index}/{len(batches)}"
            if budget_exhausted(started, reserve_seconds, timeout):
                record_skip(state, "factor_eval", "factor", target, "TIMEOUT")
                continue
            if (skip_existing or resume) and runner._has_existing_factor_values(factor, batch):
                state.skipped_batches.append(
                    {
                        "step": "factor_eval",
                        "factor": factor,
                        "batch_index": batch_index,
                        "symbols": batch,
                        "reason": "SKIP_EXISTING",
                    }
                )
                record_skip(state, "factor_eval", "factor", target, "SKIP_EXISTING")
                continue
            step, result = runner._timed_step(
                "factor_eval",
                "factor",
                target,
                lambda f=factor, symbols=batch: runner._run_factor_eval(
                    f,
                    symbols,
                    start=effective_start,
                    end=effective_end,
                    bulk_matrix=bulk_matrix,
                    write_report=write_substep_reports,
                    report_dir=substep_dir,
                ),
                details={"factor": factor, "batch_index": batch_index, "symbols_evaluated": batch},
            )
            state.steps.append(step)
            state.warning_counter.update(runner._warning_codes(step.warnings))
            if result:
                if result.get("report_path"):
                    state.substep_report_paths.append(result["report_path"])
                result["batch_index"] = batch_index
                result["batch_symbols"] = batch
                state.factor_eval_results.append(result)
                state.completed_batches.append(
                    {
                        "step": "factor_eval",
                        "factor": factor,
                        "batch_index": batch_index,
                        "symbols_evaluated": batch,
                        "observations": int(result.get("observation_count") or len(result.get("observations") or [])),
                        "runtime_seconds": step.runtime_seconds,
                        "status": step.status,
                        "report_path": step.report_path,
                    }
                )


def _run_serial_factor_backtest_phase(
    runner,
    *,
    state: ResearchValidationPhaseState,
    factors: list[str],
    batches: list[list[str]],
    started: float,
    reserve_seconds: float,
    timeout: float,
    bulk_matrix: bool,
    effective_start: str | None,
    effective_end: str | None,
    write_substep_reports: bool,
    write_batch_artifacts: bool,
    substep_dir: Path,
    batch_artifact_dir: Path,
) -> None:
    for factor in ([] if not state.factor_backtest_serial else factors):
        for batch_index, batch in enumerate(batches, start=1):
            target = f"{factor} batch {batch_index}/{len(batches)}"
            if budget_exhausted(started, reserve_seconds, timeout):
                record_skip(state, "factor_backtest", "factor", target, "TIMEOUT")
                continue
            step, result = runner._timed_step(
                "factor_backtest",
                "factor",
                target,
                lambda f=factor, symbols=batch: runner._run_factor_backtest(
                    f,
                    symbols,
                    start=effective_start,
                    end=effective_end,
                    bulk_matrix=bulk_matrix,
                    write_report=write_substep_reports,
                    write_batch_artifact=write_batch_artifacts,
                    report_dir=substep_dir,
                    artifact_dir=batch_artifact_dir,
                ),
                details={"factor": factor, "batch_index": batch_index, "symbols_evaluated": batch},
            )
            state.steps.append(step)
            state.warning_counter.update(runner._warning_codes(step.warnings))
            if result:
                if result.get("report_path"):
                    state.substep_report_paths.append(result["report_path"])
                if result.get("artifact_path"):
                    state.artifact_paths.append(result["artifact_path"])
                result["batch_index"] = batch_index
                result["batch_symbols"] = batch
                state.factor_backtest_results.append(result)
                state.completed_batches.append(
                    {
                        "step": "factor_backtest",
                        "factor": factor,
                        "batch_index": batch_index,
                        "symbols_evaluated": batch,
                        "observations": result.get("observation_count"),
                        "runtime_seconds": step.runtime_seconds,
                        "status": step.status,
                        "report_path": step.report_path,
                    }
                )
