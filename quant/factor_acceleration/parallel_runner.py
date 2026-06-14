"""Safe process-parallel compute helpers for research validation."""

from __future__ import annotations

import time
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable


@dataclass(frozen=True)
class FactorBatchTask:
    kind: str
    factor: str
    batch_index: int
    batch_count: int
    symbols: list[str]
    db_path: str
    report_dir: str
    bulk_matrix: bool = False
    max_workers: int = 1
    start: str | None = None
    end: str | None = None
    forward_days: int = 20
    holding_period: int = 20
    prefer_in_memory: bool = True
    strict_in_memory: bool = False
    write_report: bool = False

    @property
    def target(self) -> str:
        return f"{self.factor} batch {self.batch_index}/{self.batch_count}"


@dataclass(frozen=True)
class FactorBatchResult:
    task: FactorBatchTask
    result: Any | None
    runtime_seconds: float
    warnings: list[str]
    error: str | None = None

    @property
    def status(self) -> str:
        if self.error == "TIMEOUT":
            return "TIMEOUT"
        if self.error:
            return "FAIL"
        return "WARNING" if self.warnings else "PASS"


def run_factor_batch_tasks(
    tasks: list[FactorBatchTask],
    workers: int,
    soft_timeout_seconds: float | None = None,
    on_result: Callable[[FactorBatchResult], None] | None = None,
) -> list[FactorBatchResult]:
    """Run batch tasks with optional soft timeout.

    ``soft_timeout_seconds`` marks remaining tasks as TIMEOUT once the wall-clock
    exceeds the deadline, but does NOT kill already-running workers — they will
    finish naturally.  On non-fork platforms, ``ProcessPoolExecutor.__exit__``
    still waits for running workers, so actual termination may lag.
    """
    if not tasks:
        return []
    max_workers = max(1, min(int(workers), len(tasks)))
    started = time.monotonic()
    if max_workers == 1:
        results = []
        for index, task in enumerate(tasks):
            if soft_timeout_seconds is not None and time.monotonic() - started >= soft_timeout_seconds:
                for result in _timeout_results(tasks[index:]):
                    results.append(result)
                    if on_result is not None:
                        on_result(result)
                break
            result = _run_task(task)
            results.append(result)
            if on_result is not None:
                on_result(result)
        return _sort_results(results)

    results: list[FactorBatchResult] = []

    def record(result: FactorBatchResult) -> None:
        results.append(result)
        if on_result is not None:
            on_result(result)

    next_index = 0
    future_by_task = {}
    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        while next_index < len(tasks) and len(future_by_task) < max_workers:
            if soft_timeout_seconds is not None and time.monotonic() - started >= soft_timeout_seconds:
                break
            task = tasks[next_index]
            future_by_task[executor.submit(_run_task, task)] = task
            next_index += 1

        while future_by_task:
            remaining = None
            if soft_timeout_seconds is not None:
                remaining = soft_timeout_seconds - (time.monotonic() - started)
                if remaining <= 0:
                    break
            done, _ = wait(future_by_task, timeout=remaining, return_when=FIRST_COMPLETED)
            if not done:
                break
            for future in done:
                task = future_by_task.pop(future)
                try:
                    record(future.result())
                except Exception as exc:
                    record(FactorBatchResult(task=task, result=None, runtime_seconds=0.0, warnings=["PARALLEL_WORKER_FAILED"], error=str(exc)))
                if next_index < len(tasks) and (soft_timeout_seconds is None or time.monotonic() - started < soft_timeout_seconds):
                    next_task = tasks[next_index]
                    future_by_task[executor.submit(_run_task, next_task)] = next_task
                    next_index += 1
        if future_by_task:
            for future in future_by_task:
                future.cancel()
            for result in _timeout_results(list(future_by_task.values())):
                record(result)
        if next_index < len(tasks):
            for result in _timeout_results(tasks[next_index:]):
                record(result)
    return _sort_results(results)


def _timeout_results(tasks: list[FactorBatchTask]) -> list[FactorBatchResult]:
    return [
        FactorBatchResult(task=task, result=None, runtime_seconds=0.0, warnings=["TIMEOUT"], error="TIMEOUT")
        for task in tasks
    ]


def _sort_results(results: list[FactorBatchResult]) -> list[FactorBatchResult]:
    kind_order = {"factor_eval": 0, "factor_backtest": 1}
    return sorted(results, key=lambda item: (kind_order.get(item.task.kind, 99), item.task.factor, item.task.batch_index))


def _run_task(task: FactorBatchTask) -> FactorBatchResult:
    started = time.monotonic()
    try:
        if task.kind == "factor_eval":
            result = _factor_eval(task)
        elif task.kind == "factor_backtest":
            result = _factor_backtest(task)
        else:
            raise ValueError(f"unsupported factor batch task kind: {task.kind}")
        warnings = _warning_codes(getattr(result, "warnings", []))
        return FactorBatchResult(task=task, result=result, runtime_seconds=time.monotonic() - started, warnings=warnings)
    except Exception as exc:
        return FactorBatchResult(task=task, result=None, runtime_seconds=time.monotonic() - started, warnings=["STEP_FAILED"], error=str(exc))


def _factor_eval(task: FactorBatchTask):
    from quant.engines.factor_eval.factor_evaluation import FactorEvaluation
    from quant.data.fundamental.fundamental_store import FundamentalStore
    from quant.storage.sqlite_store import SQLitePriceStore

    db_path = Path(task.db_path)
    return FactorEvaluation(
        SQLitePriceStore(db_path),
        FundamentalStore(db_path),
        report_dir=Path(task.report_dir),
    ).evaluate(
        factor=task.factor,
        start=task.start,
        end=task.end,
        forward_days=task.forward_days,
        universe=task.symbols,
        bulk_matrix=task.bulk_matrix,
        max_workers=task.max_workers,
        prefer_in_memory=task.prefer_in_memory,
        strict_in_memory=task.strict_in_memory,
        cache_stats=task.bulk_matrix,
        write_report=task.write_report,
    )


def _factor_backtest(task: FactorBatchTask):
    from quant.engines.factor_backtest.factor_backtest import FactorBacktest
    from quant.data.fundamental.fundamental_store import FundamentalStore
    from quant.storage.sqlite_store import SQLitePriceStore

    db_path = Path(task.db_path)
    return FactorBacktest(
        SQLitePriceStore(db_path),
        FundamentalStore(db_path),
        report_dir=Path(task.report_dir),
    ).run(
        factor=task.factor,
        start=task.start,
        end=task.end,
        holding_period=task.holding_period,
        universe=task.symbols,
        bulk_matrix=task.bulk_matrix,
        max_workers=task.max_workers,
        prefer_in_memory=task.prefer_in_memory,
        strict_in_memory=task.strict_in_memory,
        write_report=task.write_report,
    )


def _warning_codes(warnings: list[Any]) -> list[str]:
    output = []
    for warning in warnings:
        if isinstance(warning, dict):
            output.append(str(warning.get("code") or "WARN_UNKNOWN"))
        else:
            output.append(str(warning).split(":", 1)[0])
    return [code for code in output if code]
