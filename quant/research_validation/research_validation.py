"""Bounded research validation sprint orchestration."""

from __future__ import annotations

import time
from bisect import bisect_right
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

from quant.cli_commands.common import load_alpha_config
from quant.factor_acceleration import FactorBatchTask, run_factor_batch_tasks
from quant.factor_cache import FactorEvalCache
from quant.engines.factor_backtest.factor_backtest import FactorBacktest
from quant.engines.factor_eval.factor_evaluation import FactorEvaluation
from quant.factors.store.factor_analytics import FactorAnalytics
from quant.factors.store.factor_store import FactorStore
from quant.factors.store.factor_registry_store import FactorRegistryStore
from quant.factors.price.factor_registry import FactorRegistry
from quant.engines.regime.regime_analytics import RegimeAnalytics
from quant.engines.regime.regime_history import RegimeHistoryStore
from quant.strategy_dsl.strategy_registry import StrategyRegistry
from quant.engines.walk_forward.walk_forward import DEFAULT_STABILITY_FACTORS
from quant.research_validation.config import (
    DEFAULT_FORWARD_DAYS,
    DEFAULT_HOLDING_PERIOD,
    QUICK_DEFAULT_START,
    ResearchValidationConfig,
)
from quant.research_validation.models import (
    ResearchValidationPhaseState,
    ResearchValidationRunContext,
    ResearchValidationRunOptions,
    ValidationStep,
)
from quant.research_validation.factor_phase import run_factor_validation_phase
from quant.research_validation.ranking import coverage as ranking_coverage
from quant.research_validation.regime_phase import run_regime_phase
from quant.research_validation.ranking import factor_rankings, num as ranking_num, strategy_rankings
from quant.research_validation.recommendations import recommendations as research_recommendations
from quant.research_validation.report_input import ResearchValidationReportInput
from quant.research_validation.report_writer import (
    ResearchValidationReportWriter,
    agent_summary,
    build_research_validation_report,
    directory_files,
    markdown_summary,
)
from quant.reports.report_io import generate_report_path, write_json_report
from quant.research_validation.run_options import normalize_run_options
from quant.research_validation.scope import ResearchValidationScopePlanner
from quant.research_validation.strategy_phase import run_strategy_phase
from quant.research_validation.walk_forward_phase import run_walk_forward_phase


class ResearchValidationRunner:
    """Run bounded research validation without changing engine semantics."""

    def __init__(self, context, report_dir: str | Path = "reports") -> None:
        self.context = context
        self.report_dir = Path(report_dir)
        self.chart_dir = self.report_dir / "charts"
        self.config = ResearchValidationConfig()
        self.report_writer = ResearchValidationReportWriter(self.report_dir, self.chart_dir)
        self.factor_registry = FactorRegistry(context.fundamental_store)
        self.scope_planner = ResearchValidationScopePlanner(context, self.factor_registry)
        self.factor_eval_cache: FactorEvalCache | None = None
        self._regime_dates: list[str] | None = None
        self._regime_values: list[str] | None = None

    def preview(
        self,
        mode: str = "quick",
        start: str | None = None,
        end: str | None = None,
        max_factors: int | None = None,
        max_strategies: int | None = None,
        max_folds: int | None = None,
        batch_size: int | None = None,
        max_symbols: int | None = None,
        factor_family: str = "all",
        parallel: bool = False,
        workers: int | None = None,
    ) -> dict[str, Any]:
        return self.scope_planner.preview(
            mode=mode,
            start=start,
            end=end,
            max_factors=max_factors,
            max_strategies=max_strategies,
            max_folds=max_folds,
            batch_size=batch_size,
            max_symbols=max_symbols,
            factor_family=factor_family,
            parallel=parallel,
            workers=workers,
        )

    def _normalize_options(
        self,
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
        return normalize_run_options(
            config=self.config,
            scope_planner=self.scope_planner,
            mode=mode,
            start=start,
            end=end,
            max_factors=max_factors,
            max_strategies=max_strategies,
            max_folds=max_folds,
            timeout_seconds=timeout_seconds,
            batch_size=batch_size,
            max_symbols=max_symbols,
            factor_family=factor_family,
            resume=resume,
            skip_existing=skip_existing,
            use_cache=use_cache,
            cache_stats=cache_stats,
            bulk_matrix=bulk_matrix,
            parallel=parallel,
            workers=workers,
            parallel_target=parallel_target,
            charts=charts,
            write_substep_reports=write_substep_reports,
            write_batch_artifacts=write_batch_artifacts,
            write_intermediate_reports=write_intermediate_reports,
            write_debug_logs=write_debug_logs,
            artifact_dir=artifact_dir,
        )

    def _initialize_run_context(self, artifact_dir: str | Path | None) -> ResearchValidationRunContext:
        run_id = f"rv-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid4().hex[:8]}"
        run_dir = self._run_dir(run_id, artifact_dir)
        context = ResearchValidationRunContext(
            run_id=run_id,
            run_dir=run_dir,
            substep_dir=run_dir / "substeps",
            batch_artifact_dir=run_dir / "artifacts",
            chart_dir=run_dir / "charts",
            log_dir=run_dir / "logs",
        )
        context.run_dir.mkdir(parents=True, exist_ok=True)
        return context

    @staticmethod
    def _run_factor_batch_tasks(*args, **kwargs):
        return run_factor_batch_tasks(*args, **kwargs)

    def run(
        self,
        mode: str = "quick",
        start: str | None = None,
        end: str | None = None,
        max_factors: int | None = None,
        max_strategies: int | None = None,
        max_folds: int | None = None,
        timeout_seconds: float | None = None,
        batch_size: int | None = None,
        max_symbols: int | None = None,
        factor_family: str = "all",
        resume: bool = False,
        skip_existing: bool = False,
        use_cache: bool = False,
        cache_stats: bool = False,
        bulk_matrix: bool = False,
        parallel: bool = False,
        workers: int | None = None,
        parallel_target: str = "factor_batch",
        charts: bool = False,
        write_substep_reports: bool = False,
        write_batch_artifacts: bool = False,
        write_intermediate_reports: bool = False,
        write_debug_logs: bool = False,
        artifact_dir: str | Path | None = None,
    ) -> dict[str, Any]:
        options = self._normalize_options(
            mode=mode,
            start=start,
            end=end,
            max_factors=max_factors,
            max_strategies=max_strategies,
            max_folds=max_folds,
            timeout_seconds=timeout_seconds,
            batch_size=batch_size,
            max_symbols=max_symbols,
            factor_family=factor_family,
            resume=resume,
            skip_existing=skip_existing,
            use_cache=use_cache,
            cache_stats=cache_stats,
            bulk_matrix=bulk_matrix,
            parallel=parallel,
            workers=workers,
            parallel_target=parallel_target,
            charts=charts,
            write_substep_reports=write_substep_reports,
            write_batch_artifacts=write_batch_artifacts,
            write_intermediate_reports=write_intermediate_reports,
            write_debug_logs=write_debug_logs,
            artifact_dir=artifact_dir,
        )
        mode = options.mode
        start = options.start
        end = options.end
        max_factors = options.max_factors
        max_strategies = options.max_strategies
        max_folds = options.max_folds
        timeout = options.timeout_seconds
        batch_size = options.batch_size
        max_symbols = options.max_symbols
        family = options.factor_family
        resume = options.resume
        skip_existing = options.skip_existing
        use_cache = options.use_cache
        cache_stats = options.cache_stats
        bulk_matrix = options.bulk_matrix
        parallel = options.parallel
        worker_count = options.worker_count
        parallel_target = options.parallel_target
        charts = options.charts
        write_substep_reports = options.write_substep_reports
        write_batch_artifacts = options.write_batch_artifacts
        write_intermediate_reports = options.write_intermediate_reports
        write_debug_logs = options.write_debug_logs
        artifact_dir = options.artifact_dir
        self.factor_eval_cache = FactorEvalCache() if use_cache else None
        scope = self.preview(
            mode=mode,
            start=start,
            end=end,
            max_factors=max_factors,
            max_strategies=max_strategies,
            max_folds=max_folds,
            batch_size=batch_size,
            max_symbols=max_symbols,
            factor_family=family,
            parallel=parallel,
            workers=worker_count,
        )
        factors = scope["factors"]
        strategies = scope["strategies"]
        symbol_diagnostics = scope["symbol_diagnostics"]
        universe = scope["universe"]
        effective_batch_size = scope["batch_size"]
        batches = scope["batches"]
        effective_start = scope["effective_start_date"]
        effective_end = scope["effective_end_date"]
        folds = options.folds
        reserve_seconds = self.config.quick_reserve_seconds if mode == "quick" else 0.0
        started = time.monotonic()
        run_context = self._initialize_run_context(artifact_dir)
        run_id = run_context.run_id
        run_dir = run_context.run_dir
        substep_dir = run_context.substep_dir
        batch_artifact_dir = run_context.batch_artifact_dir
        chart_dir = run_context.chart_dir
        phase_state = ResearchValidationPhaseState()
        factor_store_before = self._factor_store_counts()

        FactorRegistryStore(self.context.factor_store).sync()
        run_factor_validation_phase(
            self,
            state=phase_state,
            factors=factors,
            batches=batches,
            started=started,
            reserve_seconds=reserve_seconds,
            timeout=timeout,
            parallel=parallel,
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
        )
        regime_detection = run_regime_phase(
            self,
            state=phase_state,
            started=started,
            reserve_seconds=reserve_seconds,
            timeout=timeout,
            substep_dir=substep_dir,
            write_substep_reports=write_substep_reports,
        )
        run_strategy_phase(
            self,
            state=phase_state,
            strategies=strategies,
            started=started,
            reserve_seconds=reserve_seconds,
            timeout=timeout,
            effective_start=effective_start,
            effective_end=effective_end,
            substep_dir=substep_dir,
            write_substep_reports=write_substep_reports,
            write_intermediate_reports=write_intermediate_reports,
        )
        run_walk_forward_phase(
            self,
            state=phase_state,
            factors=factors,
            folds=folds,
            universe=universe,
            started=started,
            reserve_seconds=reserve_seconds,
            timeout=timeout,
            effective_start=effective_start,
            effective_end=effective_end,
            substep_dir=substep_dir,
            write_substep_reports=write_substep_reports,
        )

        factor_rank = self._factor_rank(write_substep_reports, substep_dir)
        regime_rank = self._regime_rank(write_substep_reports, substep_dir)
        phase_state.substep_report_paths.extend([path for path in [factor_rank.get("report_path"), regime_rank.get("report_path")] if path])
        factor_store_after = self._factor_store_counts()
        factor_store_growth = {
            table: factor_store_after.get(table, 0) - factor_store_before.get(table, 0)
            for table in sorted(set(factor_store_before) | set(factor_store_after))
        }
        phase_state.warning_counter.update(self._warning_codes(factor_rank.get("warnings") or []))
        phase_state.warning_counter.update(self._warning_codes(regime_rank.get("warnings") or []))

        runtime, slow_steps, partial = self._summarize_run_status(
            steps=phase_state.steps,
            started=started,
            timeout=timeout,
            warning_counter=phase_state.warning_counter,
            detailed_artifact_count=phase_state.detailed_artifact_count,
            factor_eval_results=phase_state.factor_eval_results,
            factor_backtest_results=phase_state.factor_backtest_results,
        )

        factor_rankings = self._factor_rankings(
            factors,
            phase_state.factor_eval_results,
            phase_state.factor_backtest_results,
            phase_state.walk_forward_results,
            factor_rank,
        )
        strategy_rankings = self._strategy_rankings(phase_state.strategy_results)
        current_regime = self._current_regime(regime_detection, regime_rank)
        best_current_regime_factor = self._best_current_regime_factor(current_regime, regime_rank)
        recommendations = self._recommendations(phase_state.warning_counter, strategy_rankings)
        cache_summary_data = self._cache_summary(use_cache, cache_stats)
        performance_metadata = self._performance_metadata(
            bulk_matrix=bulk_matrix,
            parallel=parallel,
            factor_eval_serial=phase_state.factor_eval_serial,
            factor_backtest_serial=phase_state.factor_backtest_serial,
            worker_count=worker_count,
            completed_batches=phase_state.completed_batches,
            parallel_compute_seconds=phase_state.parallel_compute_seconds,
            parallel_finalize_seconds=phase_state.parallel_finalize_seconds,
            factor_store_write_seconds=phase_state.factor_store_write_seconds,
            report_compaction_seconds=phase_state.report_compaction_seconds,
            detailed_artifact_count=phase_state.detailed_artifact_count,
            batch_write_summary=phase_state.batch_write_summary,
            cache_summary_data=cache_summary_data,
        )
        regime_sample_counts = self.context.regime_history_store.counts()
        factor_evidence_summary = self._factor_evidence_summary(phase_state.factor_eval_results, phase_state.factor_backtest_results)
        report = build_research_validation_report(
            ResearchValidationReportInput(
                scope=scope,
                symbol_diagnostics=symbol_diagnostics,
                warning_counter=phase_state.warning_counter,
                run_id=run_id,
                run_dir=run_dir,
                mode=mode,
                start=start,
                end=end,
                effective_start=effective_start,
                effective_end=effective_end,
                max_factors=max_factors,
                max_strategies=max_strategies,
                folds=folds,
                timeout=timeout,
                effective_batch_size=effective_batch_size,
                max_symbols=max_symbols,
                family=family,
                resume=resume,
                skip_existing=skip_existing,
                use_cache=use_cache,
                cache_stats=cache_stats,
                bulk_matrix=bulk_matrix,
                parallel=parallel,
                worker_count=worker_count,
                parallel_target=parallel_target,
                write_substep_reports=write_substep_reports,
                write_batch_artifacts=write_batch_artifacts,
                write_intermediate_reports=write_intermediate_reports,
                write_charts=charts,
                write_debug_logs=write_debug_logs,
                universe=universe,
                factor_store_before=factor_store_before,
                factor_store_after=factor_store_after,
                factor_store_growth=factor_store_growth,
                cache_summary_data=cache_summary_data,
                performance_metadata=performance_metadata,
                regime_sample_counts=regime_sample_counts,
                batches=batches,
                completed_batches=phase_state.completed_batches,
                skipped_batches=phase_state.skipped_batches,
                runtime=runtime,
                partial=partial,
                steps=phase_state.steps,
                skipped_steps=phase_state.skipped_steps,
                slow_steps=slow_steps,
                factor_rankings=factor_rankings,
                strategy_rankings=strategy_rankings,
                current_regime=current_regime,
                best_current_regime_factor=best_current_regime_factor,
                factor_evidence_summary=factor_evidence_summary,
                factor_eval_results=phase_state.factor_eval_results,
                factor_backtest_results=phase_state.factor_backtest_results,
                walk_forward_results=phase_state.walk_forward_results,
                strategy_results=phase_state.strategy_results,
                gate_results=phase_state.gate_results,
                factor_rank=factor_rank,
                regime_rank=regime_rank,
                recommendations=recommendations,
            )
        )
        return self._write_final_outputs(
            report,
            started=started,
            charts_enabled=charts,
            chart_dir=chart_dir,
            run_dir=run_dir,
            run_id=run_id,
            mode=mode,
            substep_report_paths=phase_state.substep_report_paths,
            artifact_paths=phase_state.artifact_paths,
            log_paths=phase_state.log_paths,
        )

    def _summarize_run_status(
        self,
        *,
        steps: list[ValidationStep],
        started: float,
        timeout: float,
        warning_counter: Counter[str],
        detailed_artifact_count: int,
        factor_eval_results: list[dict[str, Any]],
        factor_backtest_results: list[dict[str, Any]],
    ) -> tuple[float, list[dict[str, Any]], bool]:
        runtime = time.monotonic() - started
        slow_threshold = max(2.0, timeout / 20.0)
        slow_steps = [
            step.to_dict() | {"reason": "SLOW_STEP"}
            for step in sorted(steps, key=lambda item: item.runtime_seconds, reverse=True)
            if step.runtime_seconds >= slow_threshold
        ][:10]
        for _ in slow_steps:
            warning_counter.update(["SLOW_STEP"])
        if detailed_artifact_count or factor_eval_results or factor_backtest_results:
            warning_counter.update(["REPORT_COMPACTED"])
        partial = any(step.status in {"FAIL", "TIMEOUT", "SKIPPED"} for step in steps) or runtime >= timeout
        if partial:
            warning_counter.update(["PARTIAL_RESULTS"])
        return runtime, slow_steps, partial

    @staticmethod
    def _performance_metadata(
        *,
        bulk_matrix: bool,
        parallel: bool,
        factor_eval_serial: bool,
        factor_backtest_serial: bool,
        worker_count: int,
        completed_batches: list[dict[str, Any]],
        parallel_compute_seconds: float,
        parallel_finalize_seconds: float,
        factor_store_write_seconds: float,
        report_compaction_seconds: float,
        detailed_artifact_count: int,
        batch_write_summary: dict[str, Any],
        cache_summary_data: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "bulk_matrix_enabled": bulk_matrix,
            "parallel_enabled": parallel and not factor_eval_serial and not factor_backtest_serial,
            "workers": worker_count,
            "factor_batches": len(completed_batches),
            "parallel_compute_seconds": round(parallel_compute_seconds, 6),
            "parallel_finalize_seconds": round(parallel_finalize_seconds, 6),
            "factor_store_write_seconds": round(factor_store_write_seconds, 6),
            "report_compaction_seconds": round(report_compaction_seconds, 6),
            "report_write_seconds": None,
            "chart_write_seconds": None,
            "aggregate_report_size_bytes": None,
            "detailed_artifact_count": detailed_artifact_count,
            "factor_store_batch_write_summary": batch_write_summary,
            "cache_hits": cache_summary_data.get("matrix_hits") or 0,
            "cache_misses": cache_summary_data.get("matrix_misses") or 0,
            "speedup_vs_baseline": None,
            "sqlite_writes": "main_process_only",
        }

    def _write_final_outputs(
        self,
        report: dict[str, Any],
        *,
        started: float,
        charts_enabled: bool,
        chart_dir: Path,
        run_dir: Path,
        run_id: str,
        mode: str,
        substep_report_paths: list[str],
        artifact_paths: list[str],
        log_paths: list[str],
    ) -> dict[str, Any]:
        report_write_started = time.monotonic()
        report, chart_write_seconds = self._write_outputs(report, charts_enabled=charts_enabled, chart_dir=chart_dir)
        report_write_seconds = time.monotonic() - report_write_started
        report["performance_metadata"]["report_write_seconds"] = round(report_write_seconds, 6)
        report["performance_metadata"]["chart_write_seconds"] = round(chart_write_seconds, 6)
        report["total_runtime_seconds_including_report_write"] = round(time.monotonic() - started, 6)
        chart_paths = list(report.get("chart_paths") or [])
        compaction_status = (
            "compacted"
            if any(row.get("code") == "REPORT_COMPACTED" for row in report.get("warning_statistics", []))
            else "compact"
        )
        manifest_path = self._write_manifest(
            run_dir=run_dir,
            run_id=run_id,
            run_type="research_validation",
            mode=mode,
            status=report.get("status"),
            aggregate_report_path=report.get("report_path"),
            summary_path=report.get("summary_path"),
            agent_export_path=report.get("agent_summary_path"),
            substep_report_paths=substep_report_paths,
            artifact_paths=artifact_paths,
            chart_paths=chart_paths,
            log_paths=log_paths,
            warnings=[row["code"] for row in report.get("warning_statistics", [])],
            warning_statistics=report.get("warning_statistics", []),
            compaction_status=compaction_status,
        )
        report["run_id"] = run_id
        report["run_artifact_dir"] = str(run_dir)
        report["manifest_path"] = str(manifest_path)
        if report.get("report_path"):
            self._write_aggregate_report(Path(report["report_path"]), report)
        return report

    def _run_factor_eval(
        self,
        factor: str,
        universe: list[str] | None,
        start: str | None = None,
        end: str | None = None,
        bulk_matrix: bool = False,
        write_report: bool = False,
        report_dir: str | Path | None = None,
    ) -> dict[str, Any]:
        engine = self.context.factor_evaluation
        if report_dir is not None:
            engine = FactorEvaluation(self.context.price_store, self.context.fundamental_store, report_dir=report_dir)
        result = engine.evaluate(
            factor=factor,
            start=start,
            end=end,
            forward_days=DEFAULT_FORWARD_DAYS,
            universe=universe,
            use_cache=self.factor_eval_cache is not None,
            factor_cache=self.factor_eval_cache,
            cache_stats=self.factor_eval_cache is not None,
            bulk_matrix=bulk_matrix,
            write_report=write_report,
        )
        return self._finalize_factor_eval_result(result)

    def _finalize_factor_eval_result(self, result) -> dict[str, Any]:
        saved = self.context.factor_store.save_factor_evaluation(result)
        try:
            regime_saved = self.context.regime_analytics.save_factor_evaluation_by_regime(result)
        except Exception as exc:
            regime_saved = {"error": str(exc)}
        return self._compact_factor_eval_result(result) | {"saved_factor_history": saved, "saved_regime_history": regime_saved}

    def _cache_summary(self, use_cache: bool, cache_stats: bool) -> dict[str, Any]:
        if not (use_cache or cache_stats):
            return {"cache_enabled": False}
        snapshot = self.factor_eval_cache.snapshot() if self.factor_eval_cache is not None else {}
        return {"cache_enabled": use_cache, **snapshot}

    def _run_factor_backtest(
        self,
        factor: str,
        universe: list[str] | None,
        start: str | None = None,
        end: str | None = None,
        bulk_matrix: bool = False,
        write_report: bool = False,
        write_batch_artifact: bool = False,
        report_dir: str | Path | None = None,
        artifact_dir: str | Path | None = None,
    ) -> dict[str, Any]:
        engine = self.context.factor_backtest_engine
        if report_dir is not None:
            engine = FactorBacktest(self.context.price_store, self.context.fundamental_store, report_dir=report_dir)
        result = engine.run(
            factor=factor,
            start=start,
            end=end,
            holding_period=DEFAULT_HOLDING_PERIOD,
            universe=universe,
            bulk_matrix=bulk_matrix,
            write_report=write_report,
        )
        return self._finalize_factor_backtest_result(result, write_batch_artifact=write_batch_artifact, artifact_dir=artifact_dir)

    def _finalize_factor_backtest_result(
        self,
        result,
        write_batch_artifact: bool = False,
        artifact_dir: str | Path | None = None,
    ) -> dict[str, Any]:
        saved = self.context.factor_store.save_factor_backtest(result)
        try:
            regime_saved = self.context.regime_analytics.save_factor_backtest_by_regime(result)
        except Exception as exc:
            regime_saved = {"error": str(exc)}
        artifact_path = ""
        if write_batch_artifact:
            artifact_path = self._write_batch_artifact("factor_backtest", None, result.to_report(), Path(artifact_dir) if artifact_dir else self.report_dir / "research_validation_batches")
        return self._compact_factor_backtest_result(result, artifact_path=artifact_path) | {"saved_factor_history": saved, "saved_regime_history": regime_saved}

    def _compact_factor_eval_result(self, result, task: FactorBatchTask | None = None) -> dict[str, Any]:
        coverage = self._coverage_pct(result.factor_coverage)
        output = {
            "factor": result.factor,
            "factor_name": result.factor,
            "batch_id": self._batch_id(task),
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
                for key in ("bulk_matrix_enabled", "matrix_rows", "bulk_read_seconds", "matrix_build_seconds", "eval_seconds")
                if key in result.performance_metadata
            }
        return output

    def _compact_factor_backtest_result(
        self,
        result,
        task: FactorBatchTask | None = None,
        artifact_path: str | None = None,
    ) -> dict[str, Any]:
        coverage = self._coverage_pct(result.factor_coverage)
        sharpe = result.long_short_sharpe if result.long_short_sharpe is not None else result.sharpe
        return {
            "factor": result.factor,
            "factor_name": result.factor,
            "batch_id": self._batch_id(task),
            "batch_index": task.batch_index if task else None,
            "batch_symbols": list(task.symbols) if task else None,
            "universe_size": len(task.symbols) if task else None,
            "observation_count": result.observations,
            "long_short_return": result.long_short_return,
            "sharpe": sharpe,
            "long_short_sharpe": result.long_short_sharpe,
            "max_drawdown": result.max_drawdown,
            "turnover": result.turnover,
            "ic_mean": result.ic_mean,
            "rank_ic_mean": result.rank_ic_mean,
            "icir": result.icir,
            "coverage": coverage,
            "warnings": list(result.warnings or []),
            "report_path": result.report_path,
            "artifact_path": artifact_path or result.report_path or None,
        }

    def _write_batch_artifact(self, kind: str, task: FactorBatchTask | None, report: dict[str, Any], artifact_dir: Path) -> str:
        artifact_dir.mkdir(parents=True, exist_ok=True)
        factor = (task.factor if task else report.get("factor") or kind).replace("/", "_")
        batch = f"batch_{task.batch_index:04d}_of_{task.batch_count:04d}" if task else f"batch_{uuid4().hex[:8]}"
        path = generate_report_path(artifact_dir, f"{kind}_{factor}_{batch}", unique=True)
        write_json_report(path, report, sort_keys=True)
        return str(path)

    @staticmethod
    def _batch_id(task: FactorBatchTask | None) -> str | None:
        if task is None:
            return None
        return f"{task.factor}:{task.batch_index}/{task.batch_count}"

    @staticmethod
    def _coverage_pct(coverage: dict | None) -> float | None:
        if not coverage:
            return None
        return coverage.get("coverage_percentage")

    def _factor_regime_rows_from_evaluation(self, result) -> list[dict]:
        observations = []
        for obs in result.observations:
            regime = self._regime_for_date(obs.signal_date)
            if not regime:
                continue
            observations.append(
                {
                    "regime": regime,
                    "factor_value": obs.factor_value,
                    "future_return": obs.future_return,
                }
            )
        return self.context.regime_analytics._factor_rows(
            result.factor,
            observations,
            value_key="factor_value",
            return_key="future_return",
        )

    def _factor_regime_rows_from_backtest(self, result) -> list[dict]:
        observations = []
        for period in result.periods:
            regime = self._regime_for_date(period.signal_date)
            if not regime:
                continue
            observations.append({"regime": regime, "spread_return": period.long_short_return})
        rows = []
        for regime, items in self.context.regime_analytics._group(observations).items():
            returns = [self.context.regime_analytics._num(item.get("spread_return")) for item in items]
            clean = [value for value in returns if value is not None]
            if not clean:
                continue
            mean = sum(clean) / len(clean)
            std = self.context.regime_analytics._std(clean)
            rows.append(
                {
                    "factor_name": result.factor,
                    "regime": regime,
                    "ic": mean,
                    "rank_ic": None,
                    "icir": mean / std if std and std > 0 else None,
                    "coverage": len(clean) / max(len(result.periods), 1),
                    "stability": FactorAnalytics.consistency_score(clean),
                    "samples": len(clean),
                    "metric_note": "factor_backtest spread-return proxy stored in ic field for regime diagnostics",
                }
            )
        return rows

    def _regime_for_date(self, date: str) -> str | None:
        if self._regime_dates is None or self._regime_values is None:
            with self.context.regime_history_store.connect() as connection:
                rows = connection.execute("SELECT date, regime FROM regime_history ORDER BY date").fetchall()
            self._regime_dates = [row["date"] for row in rows]
            self._regime_values = [row["regime"] for row in rows]
        index = bisect_right(self._regime_dates, date) - 1
        if index < 0:
            return None
        return self._regime_values[index]

    def _run_walk_forward_factor(
        self,
        factor: str,
        max_folds: int | None,
        universe: list[str] | None,
        start: str | None,
        end: str | None,
        report_dir: str | Path | None = None,
        write_report: bool = False,
    ) -> dict[str, Any]:
        engine = self.context.walk_forward_engine
        if report_dir is not None:
            from quant.engines.walk_forward.walk_forward import WalkForwardEngine

            engine = WalkForwardEngine(self.context.price_store, self.context.fundamental_store, report_dir=report_dir)
        result = engine.run(strategy="factor_long_short", factor=factor, max_folds=max_folds, universe=universe, start=start, end=end, write_report=write_report)
        saved = self.context.factor_store.save_walk_forward(result, factor=factor)
        return result.to_report() | {"report_path": result.report_path, "saved_factor_history": saved}

    def _run_regime_detection(self, report_dir: str | Path, write_report: bool) -> dict[str, Any]:
        if write_report:
            history_store = RegimeHistoryStore(self.context.db_path, report_dir=report_dir)
            factor_store = FactorStore(self.context.db_path, report_dir=report_dir)
            return RegimeAnalytics(self.context.regime_detector, history_store, factor_store).detect_and_save(write_report=True)
        return self.context.regime_analytics.detect_and_save(write_report=False)

    def _run_strategy(
        self,
        strategy: str,
        start: str | None,
        end: str | None,
        report_dir: str | Path,
        write_report: bool,
        write_intermediate_reports: bool,
    ) -> dict[str, Any]:
        return StrategyRegistry(self.context, report_dir=report_dir).run(
            strategy=strategy,
            start=start or QUICK_DEFAULT_START,
            end=end or start or QUICK_DEFAULT_START,
            with_gates=True,
            write_report=write_report,
            write_gate_report=write_report,
            write_intermediate_reports=write_intermediate_reports,
        )

    def _factor_rank(self, write_report: bool, substep_dir: Path) -> dict[str, Any]:
        if write_report:
            return FactorStore(self.context.db_path, report_dir=substep_dir).rank_factors(limit=50, write_report=True)
        return self.context.factor_store.rank_factors(limit=50, write_report=False)

    def _regime_rank(self, write_report: bool, substep_dir: Path) -> dict[str, Any]:
        if write_report:
            history_store = RegimeHistoryStore(self.context.db_path, report_dir=substep_dir)
            factor_store = FactorStore(self.context.db_path, report_dir=substep_dir)
            return RegimeAnalytics(self.context.regime_detector, history_store, factor_store).regime_rank(limit=10, write_report=True)
        return self.context.regime_analytics.regime_rank(limit=10, write_report=False)

    def _run_dir(self, run_id: str, artifact_dir: str | Path | None) -> Path:
        if artifact_dir is None:
            return self.report_dir / "runs" / run_id
        text = str(artifact_dir).replace("<run_id>", run_id)
        return Path(text)

    def _write_manifest(
        self,
        run_dir: Path,
        run_id: str,
        run_type: str,
        mode: str,
        status: str | None,
        aggregate_report_path: str | None,
        summary_path: str | None,
        agent_export_path: str | None,
        substep_report_paths: list[str],
        artifact_paths: list[str],
        chart_paths: list[str],
        log_paths: list[str],
        warnings: list[str],
        warning_statistics: list[dict[str, Any]],
        compaction_status: str,
    ) -> Path:
        return self.report_writer.write_manifest(
            run_dir=run_dir,
            run_id=run_id,
            run_type=run_type,
            mode=mode,
            status=status,
            aggregate_report_path=aggregate_report_path,
            summary_path=summary_path,
            agent_export_path=agent_export_path,
            substep_report_paths=substep_report_paths,
            artifact_paths=artifact_paths,
            chart_paths=chart_paths,
            log_paths=log_paths,
            warnings=warnings,
            warning_statistics=warning_statistics,
            compaction_status=compaction_status,
        )

    @staticmethod
    def _directory_files(path: Path) -> set[str]:
        return directory_files(path)

    def _timed_step(
        self,
        name: str,
        category: str,
        target: str,
        fn: Callable[[], dict[str, Any]],
        details: dict[str, Any] | None = None,
    ) -> tuple[ValidationStep, dict[str, Any] | None]:
        started = time.monotonic()
        try:
            result = fn()
            runtime = time.monotonic() - started
            warnings = self._warning_codes(result.get("warnings") or [])
            status = "WARNING" if warnings else "PASS"
            return ValidationStep(name, category, target, status, runtime, result.get("report_path"), warnings, details=details), result
        except Exception as exc:
            runtime = time.monotonic() - started
            return ValidationStep(name, category, target, "FAIL", runtime, warnings=["STEP_FAILED"], error=str(exc), details=details), None

    def _select_factors(self, mode: str, max_factors: int | None, factor_family: str = "all") -> list[str]:
        return self.scope_planner.select_factors(mode, max_factors, factor_family)

    def _select_and_filter_symbols(self, mode: str, max_symbols: int | None, factors: list[str]) -> dict[str, Any]:
        return self.scope_planner.select_and_filter_symbols(mode, max_symbols, factors)

    def _effective_date_range(self, mode: str, start: str | None, end: str | None, symbols: list[str]) -> tuple[str | None, str | None]:
        return self.scope_planner.effective_date_range(mode, start, end, symbols)

    def _latest_price_date(self, symbols: list[str]) -> str | None:
        return self.scope_planner.latest_price_date(symbols)

    def _earliest_price_date(self, symbols: list[str]) -> str | None:
        return self.scope_planner.earliest_price_date(symbols)

    def _price_date_bound(self, symbols: list[str], aggregate: str) -> str | None:
        return self.scope_planner.price_date_bound(symbols, aggregate)

    def _trading_day_count(self, symbols: list[str], start: str | None, end: str | None) -> int:
        return self.scope_planner.trading_day_count(symbols, start, end)

    def _minimum_history_days(self, factors: list[str]) -> int:
        return self.scope_planner.minimum_history_days(factors)

    @staticmethod
    def _symbol_batches(symbols: list[str], batch_size: int) -> list[list[str]]:
        return ResearchValidationScopePlanner.symbol_batches(symbols, batch_size)

    @staticmethod
    def _effective_batch_size(
        symbol_count: int,
        mode: str,
        requested_batch_size: int | None,
        parallel: bool,
        workers: int,
    ) -> int:
        return ResearchValidationScopePlanner.effective_batch_size(symbol_count, mode, requested_batch_size, parallel, workers)

    def _fundamental_coverage(self, symbols: list[str]) -> dict[str, Any]:
        return self.scope_planner.fundamental_coverage(symbols)

    def _has_existing_factor_values(self, factor: str, symbols: list[str]) -> bool:
        if not symbols:
            return False
        placeholders = ",".join("?" for _ in symbols)
        query = f"""
            SELECT COUNT(DISTINCT symbol) AS symbol_count
            FROM factor_values
            WHERE factor_name = ? AND symbol IN ({placeholders})
        """
        try:
            with self.context.factor_store.connect() as connection:
                row = connection.execute(query, [factor, *symbols]).fetchone()
            return int(row["symbol_count"] if hasattr(row, "keys") else row[0]) >= len(symbols)
        except Exception:
            return False

    def _factor_store_counts(self) -> dict[str, int]:
        tables = [
            "factor_values",
            "factor_evaluation_history",
            "factor_backtest_history",
            "factor_walk_forward_history",
            "factor_stability_history",
        ]
        counts: dict[str, int] = {}
        with self.context.factor_store.connect() as connection:
            for table in tables:
                try:
                    row = connection.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()
                    counts[table] = int(row["count"])
                except Exception:
                    counts[table] = 0
        return counts

    @staticmethod
    def _factor_evidence_summary(evals: list[dict[str, Any]], backtests: list[dict[str, Any]]) -> list[dict[str, Any]]:
        rows: dict[str, dict[str, Any]] = {}
        for result in evals:
            factor = result.get("factor")
            if not factor:
                continue
            row = rows.setdefault(factor, {"factor": factor, "eval_batches": 0, "backtest_batches": 0, "observations": 0})
            row["eval_batches"] += 1
            row["observations"] += int(result.get("observation_count") or len(result.get("observations") or []))
            row["latest_ic"] = result.get("ic_mean")
            row["latest_rank_ic"] = result.get("rank_ic_mean")
            row["latest_icir"] = result.get("icir")
        for result in backtests:
            factor = result.get("factor")
            if not factor:
                continue
            row = rows.setdefault(factor, {"factor": factor, "eval_batches": 0, "backtest_batches": 0, "observations": 0})
            row["backtest_batches"] += 1
            row["latest_long_short_return"] = result.get("long_short_return")
            row["latest_sharpe"] = result.get("long_short_sharpe") if result.get("long_short_sharpe") is not None else result.get("sharpe")
        return sorted(rows.values(), key=lambda row: row["factor"])

    def _select_strategies(self, mode: str, max_strategies: int | None) -> list[str]:
        return self.scope_planner.select_strategies(mode, max_strategies)

    @staticmethod
    def _major_factors(factors: list[str]) -> list[str]:
        return [factor for factor in DEFAULT_STABILITY_FACTORS if factor in factors]

    def _factor_rankings(
        self,
        factors: list[str],
        evals: list[dict[str, Any]],
        backtests: list[dict[str, Any]],
        walk_forwards: list[dict[str, Any]],
        factor_rank: dict[str, Any],
    ) -> list[dict[str, Any]]:
        return factor_rankings(factors, evals, backtests, walk_forwards, factor_rank)

    @staticmethod
    def _strategy_rankings(strategy_results: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return strategy_rankings(strategy_results)

    @staticmethod
    def _current_regime(regime_detection: dict[str, Any], regime_rank: dict[str, Any]) -> str | None:
        current = regime_detection.get("current_regime")
        if isinstance(current, dict):
            return current.get("regime")
        current = regime_rank.get("current_regime")
        if isinstance(current, dict):
            return current.get("regime")
        return regime_detection.get("regime")

    @staticmethod
    def _best_current_regime_factor(current_regime: str | None, regime_rank: dict[str, Any]) -> dict[str, Any] | None:
        if not current_regime:
            return None
        rows = (regime_rank.get("best_by_regime") or {}).get(current_regime) or []
        return rows[0] if rows else None

    @staticmethod
    def _recommendations(warnings: Counter[str], strategies: list[dict[str, Any]]) -> list[str]:
        return research_recommendations(warnings, strategies)

    def _write_outputs(self, report: dict[str, Any], charts_enabled: bool = False, chart_dir: Path | None = None) -> tuple[dict[str, Any], float]:
        return self.report_writer.write_outputs(report, charts_enabled=charts_enabled, chart_dir=chart_dir)

    @staticmethod
    def _write_aggregate_report(path: Path, report: dict[str, Any]) -> None:
        ResearchValidationReportWriter.write_aggregate_report(path, report)

    def _charts(self, report: dict[str, Any], stamp: str, chart_dir: Path):
        return self.report_writer.charts(report, stamp, chart_dir)

    @staticmethod
    def _markdown_summary(report: dict[str, Any]) -> str:
        return markdown_summary(report)

    @staticmethod
    def _agent_summary(report: dict[str, Any]) -> str:
        return agent_summary(report)

    @staticmethod
    def _warning_codes(warnings: list[Any]) -> list[str]:
        output = []
        for warning in warnings:
            if isinstance(warning, dict):
                output.append(str(warning.get("code") or "WARN_UNKNOWN"))
            else:
                output.append(str(warning).split(":", 1)[0])
        return [code for code in output if code]

    @staticmethod
    def _coverage(report: dict[str, Any]) -> float | None:
        return ranking_coverage(report)

    @staticmethod
    def _num(value: Any) -> float | None:
        return ranking_num(value)
