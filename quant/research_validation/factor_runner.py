"""Extracted factor evaluation / backtest runner logic."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import uuid4

from quant.factor_acceleration import FactorBatchTask
from quant.engines.factor_backtest.factor_backtest import FactorBacktest
from quant.engines.factor_eval.factor_evaluation import FactorEvaluation
from quant.reports.report_io import generate_report_path, write_json_report
from quant.research_validation.config import DEFAULT_FORWARD_DAYS, DEFAULT_HOLDING_PERIOD
from quant.research_validation.utility import coverage_pct


def run_factor_eval(
    runner,
    factor: str,
    universe: list[str] | None,
    start: str | None = None,
    end: str | None = None,
    bulk_matrix: bool = True,
    max_workers: int = 4,
    prefer_in_memory: bool = True,
    strict_in_memory: bool = False,
    write_report: bool = False,
    report_dir: str | Path | None = None,
) -> dict[str, Any]:
    engine = runner.context.factor_evaluation
    if report_dir is not None:
        engine = FactorEvaluation(runner.context.price_store, runner.context.fundamental_store, report_dir=report_dir)
    result = engine.evaluate(
        factor=factor,
        start=start,
        end=end,
        forward_days=DEFAULT_FORWARD_DAYS,
        universe=universe,
        use_cache=runner.factor_eval_cache is not None,
        factor_cache=runner.factor_eval_cache,
        cache_stats=runner.factor_eval_cache is not None,
        bulk_matrix=bulk_matrix,
        max_workers=max_workers,
        prefer_in_memory=prefer_in_memory,
        strict_in_memory=strict_in_memory,
        write_report=write_report,
    )
    return finalize_factor_eval_result(runner, result)


def finalize_factor_eval_result(runner, result) -> dict[str, Any]:
    saved = runner.context.factor_store.save_factor_evaluation(result)
    try:
        regime_saved = runner.context.regime_analytics.save_factor_evaluation_by_regime(result)
    except Exception as exc:
        regime_saved = {"error": str(exc)}
    return compact_factor_eval_result(runner, result) | {"saved_factor_history": saved, "saved_regime_history": regime_saved}


def run_factor_backtest(
    runner,
    factor: str,
    universe: list[str] | None,
    start: str | None = None,
    end: str | None = None,
    bulk_matrix: bool = True,
    max_workers: int = 4,
    prefer_in_memory: bool = True,
    strict_in_memory: bool = False,
    write_report: bool = False,
    write_batch_artifact: bool = False,
    report_dir: str | Path | None = None,
    artifact_dir: str | Path | None = None,
) -> dict[str, Any]:
    engine = runner.context.factor_backtest_engine
    if report_dir is not None:
        engine = FactorBacktest(runner.context.price_store, runner.context.fundamental_store, report_dir=report_dir)
    result = engine.run(
        factor=factor,
        start=start,
        end=end,
        holding_period=DEFAULT_HOLDING_PERIOD,
        universe=universe,
        bulk_matrix=bulk_matrix,
        max_workers=max_workers,
        prefer_in_memory=prefer_in_memory,
        strict_in_memory=strict_in_memory,
        write_report=write_report,
    )
    return finalize_factor_backtest_result(runner, result, write_batch_artifact=write_batch_artifact, artifact_dir=artifact_dir)


def finalize_factor_backtest_result(
    runner,
    result,
    write_batch_artifact: bool = False,
    artifact_dir: str | Path | None = None,
) -> dict[str, Any]:
    saved = runner.context.factor_store.save_factor_backtest(result)
    try:
        regime_saved = runner.context.regime_analytics.save_factor_backtest_by_regime(result)
    except Exception as exc:
        regime_saved = {"error": str(exc)}
    artifact_path = ""
    if write_batch_artifact:
        artifact_path = write_batch_artifact_to_dir("factor_backtest", None, result.to_report(), Path(artifact_dir) if artifact_dir else runner.report_dir / "research_validation_batches")
    return compact_factor_backtest_result(runner, result, artifact_path=artifact_path) | {"saved_factor_history": saved, "saved_regime_history": regime_saved}


def compact_factor_eval_result(runner, result, task: FactorBatchTask | None = None) -> dict[str, Any]:
    coverage = coverage_pct(result.factor_coverage)
    output = {
        "factor": result.factor,
        "factor_name": result.factor,
        "batch_id": batch_id(task),
        "batch_index": task.batch_index if task else None,
        "batch_symbols": list(task.symbols) if task else list(result.universe),
        "universe_size": len(task.symbols) if task else len(result.universe),
        "observation_count": len(result.observations),
        "ic_mean": result.ic_mean,
        "rank_ic_mean": result.rank_ic_mean,
        "icir": result.icir,
        "ic_count": result.ic_count,
        "rank_ic_count": result.rank_ic_count,
        "coverage": coverage,
        "warnings": list(result.warnings or []),
        "report_path": result.report_path,
        "artifact_path": result.report_path or None,
    }
    if result.performance_metadata:
        output["performance_metadata"] = {
            key: result.performance_metadata.get(key)
            for key in (
                "bulk_matrix_enabled",
                "provider_type",
                "cache_strategy",
                "fallback_used",
                "fallback_reason",
                "platform",
                "multiprocessing_start_method",
                "memory_preload_enabled",
                "memory_preload_seconds",
                "estimated_matrix_memory_mb",
                "requested_workers",
                "matrix_workers",
                "matrix_rows",
                "bulk_read_seconds",
                "matrix_build_seconds",
                "eval_seconds",
            )
            if key in result.performance_metadata
        }
    return output


def compact_factor_backtest_result(
    runner,
    result,
    task: FactorBatchTask | None = None,
    artifact_path: str | None = None,
) -> dict[str, Any]:
    coverage = coverage_pct(result.factor_coverage)
    sharpe = result.long_short_sharpe if result.long_short_sharpe is not None else result.sharpe
    output = {
        "factor": result.factor,
        "factor_name": result.factor,
        "batch_id": batch_id(task),
        "batch_index": task.batch_index if task else None,
        "batch_symbols": list(task.symbols) if task else None,
        "universe_size": len(task.symbols) if task else None,
        "observation_count": result.observations,
        # ── Spread-semantics primary metrics ──
        "cumulative_forward_spread": result.long_short_return,
        "annualized_mean_forward_spread": result.annual_return,
        "spread_sharpe_like": sharpe,
        "spread_max_drawdown": result.max_drawdown,
        # ── Legacy metric aliases (nested to keep primary surface clean) ──
        "legacy_metrics": {
            "long_short_return": result.long_short_return,
            "sharpe": sharpe,
            "long_short_sharpe": result.long_short_sharpe,
            "max_drawdown": result.max_drawdown,
            "annual_return": result.annual_return,
        },
        "turnover": result.turnover,
        "ic_mean": result.ic_mean,
        "rank_ic_mean": result.rank_ic_mean,
        "icir": result.icir,
        "coverage": coverage,
        "warnings": list(result.warnings or []),
        "report_path": result.report_path,
        "artifact_path": artifact_path or result.report_path or None,
    }
    if result.performance_metadata:
        output["performance_metadata"] = {
            key: result.performance_metadata.get(key)
            for key in (
                "bulk_matrix_enabled",
                "provider_type",
                "cache_strategy",
                "fallback_used",
                "fallback_reason",
                "platform",
                "multiprocessing_start_method",
                "memory_preload_enabled",
                "memory_preload_seconds",
                "estimated_matrix_memory_mb",
                "requested_workers",
                "matrix_workers",
                "matrix_rows",
                "bulk_read_seconds",
                "matrix_build_seconds",
                "eval_seconds",
            )
            if key in result.performance_metadata
        }
    return output


def write_batch_artifact(kind: str, task: FactorBatchTask | None, report: dict[str, Any], artifact_dir: Path) -> str:
    artifact_dir.mkdir(parents=True, exist_ok=True)
    factor = (task.factor if task else report.get("factor") or kind).replace("/", "_")
    batch = f"batch_{task.batch_index:04d}_of_{task.batch_count:04d}" if task else f"batch_{uuid4().hex[:8]}"
    path = generate_report_path(artifact_dir, f"{kind}_{factor}_{batch}", unique=True)
    write_json_report(path, report, sort_keys=True)
    return str(path)


# Compatibility alias used by finalize_factor_backtest_result above
write_batch_artifact_to_dir = write_batch_artifact


def batch_id(task: FactorBatchTask | None) -> str | None:
    if task is None:
        return None
    return f"{task.factor}:{task.batch_index}/{task.batch_count}"


def cache_summary(runner, use_cache: bool, cache_stats: bool) -> dict[str, Any]:
    if not (use_cache or cache_stats):
        return {"cache_enabled": False}
    snapshot = runner.factor_eval_cache.snapshot() if runner.factor_eval_cache is not None else {}
    return {"cache_enabled": use_cache, **snapshot}
