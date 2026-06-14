"""Bounded research validation sprint orchestration."""

from __future__ import annotations

import time
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

from quant.factor_acceleration import FactorBatchTask
from quant.factor_cache import FactorEvalCache
from quant.factors.store.factor_store import FactorStore
from quant.factors.store.factor_registry_store import FactorRegistryStore
from quant.factors.price.factor_registry import FactorRegistry
from quant.engines.regime.regime_analytics import RegimeAnalytics
from quant.engines.regime.regime_history import RegimeHistoryStore
from quant.strategy_dsl.strategy_registry import StrategyRegistry
from quant.engines.walk_forward.walk_forward import DEFAULT_STABILITY_FACTORS
from quant.research_validation.config import (
    QUICK_DEFAULT_START,
    ResearchValidationConfig,
)
from quant.research_validation.models import (
    ResearchValidationPhaseState,
    ResearchValidationRunContext,
    ResearchValidationRunOptions,
    ValidationStep,
)
from quant.research_validation.factor_phase import FactorPhaseConfig, run_factor_validation_phase
from quant.research_validation.regime_phase import run_regime_phase
from quant.research_validation.ranking import factor_rankings, strategy_rankings
from quant.research_validation.recommendations import recommendations as research_recommendations
from quant.research_validation.report_input import ResearchValidationReportInput
from quant.research_validation.report_writer import (
    ResearchValidationReportWriter,
    agent_summary,
    build_research_validation_report,
    markdown_summary,
)
from quant.research_validation.run_options import normalize_run_options
from quant.research_validation.scope import ResearchValidationScopePlanner
from quant.research_validation.factor_runner import (
    batch_id,
    cache_summary,
    compact_factor_backtest_result,
    compact_factor_eval_result,
    finalize_factor_backtest_result,
    finalize_factor_eval_result,
    run_factor_backtest,
    run_factor_eval,
    write_batch_artifact,
)
from quant.research_validation.regime_runner import (
    factor_regime_rows_from_backtest,
    factor_regime_rows_from_evaluation,
    regime_for_date,
    run_regime_detection,
)
from quant.research_validation.strategy_phase import run_strategy_phase
from quant.research_validation.utility import (
    coverage_pct,
    directory_files as dir_files,
    factor_evidence_summary,
    factor_store_counts,
    has_existing_factor_values,
    report_coverage,
    safe_num,
    warning_codes,
)
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
        cost_profile: str = "conservative",
        resume: bool = False,
        skip_existing: bool = False,
        use_cache: bool = False,
        cache_stats: bool = False,
        bulk_matrix: bool = True,
        prefer_in_memory: bool = True,
        strict_in_memory: bool = False,
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
        options = normalize_run_options(
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
            cost_profile=cost_profile,
            resume=resume,
            skip_existing=skip_existing,
            use_cache=use_cache,
            cache_stats=cache_stats,
            bulk_matrix=bulk_matrix,
            prefer_in_memory=prefer_in_memory,
            strict_in_memory=strict_in_memory,
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
        cost_profile = options.cost_profile
        resume = options.resume
        skip_existing = options.skip_existing
        use_cache = options.use_cache
        cache_stats = options.cache_stats
        bulk_matrix = options.bulk_matrix
        prefer_in_memory = options.prefer_in_memory
        strict_in_memory = options.strict_in_memory
        parallel = options.parallel
        worker_count = options.worker_count
        matrix_workers = options.matrix_workers
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
            config=FactorPhaseConfig(
                started=started,
                reserve_seconds=reserve_seconds,
                timeout=timeout,
                parallel=parallel,
                worker_count=worker_count,
                matrix_workers=matrix_workers,
                skip_existing=skip_existing,
                resume=resume,
                bulk_matrix=bulk_matrix,
                prefer_in_memory=prefer_in_memory,
                strict_in_memory=strict_in_memory,
                effective_start=effective_start,
                effective_end=effective_end,
                write_substep_reports=write_substep_reports,
                write_batch_artifacts=write_batch_artifacts,
                substep_dir=substep_dir,
                batch_artifact_dir=batch_artifact_dir,
            ),
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
            cost_profile=cost_profile,
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
            prefer_in_memory=prefer_in_memory,
            strict_in_memory=strict_in_memory,
            parallel=parallel,
            factor_eval_serial=phase_state.factor_eval_serial,
            factor_backtest_serial=phase_state.factor_backtest_serial,
            worker_count=worker_count,
            matrix_workers=matrix_workers,
            completed_batches=phase_state.completed_batches,
            factor_eval_results=phase_state.factor_eval_results,
            factor_backtest_results=phase_state.factor_backtest_results,
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
                cost_profile=cost_profile,
                resume=resume,
                skip_existing=skip_existing,
                use_cache=use_cache,
                cache_stats=cache_stats,
                bulk_matrix=bulk_matrix,
                parallel=parallel,
                worker_count=worker_count,
                matrix_workers=matrix_workers,
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
        prefer_in_memory: bool,
        strict_in_memory: bool,
        parallel: bool,
        factor_eval_serial: bool,
        factor_backtest_serial: bool,
        worker_count: int,
        matrix_workers: int,
        completed_batches: list[dict[str, Any]],
        factor_eval_results: list[dict[str, Any]],
        factor_backtest_results: list[dict[str, Any]],
        parallel_compute_seconds: float,
        parallel_finalize_seconds: float,
        factor_store_write_seconds: float,
        report_compaction_seconds: float,
        detailed_artifact_count: int,
        batch_write_summary: dict[str, Any],
        cache_summary_data: dict[str, Any],
    ) -> dict[str, Any]:
        from quant.data.research_data_store import multiprocessing_start_method, platform_label

        provider_summary = ResearchValidationRunner._provider_metadata_summary(
            factor_eval_results,
            factor_backtest_results,
        )
        return {
            "bulk_matrix_enabled": bulk_matrix,
            "parallel_enabled": parallel and not factor_eval_serial and not factor_backtest_serial,
            "provider_type": provider_summary.get("primary_provider_type") or ("bulk_matrix" if bulk_matrix else "serial_reference"),
            "provider_types_used": provider_summary["provider_types_used"],
            "preferred_provider_type": "in_memory" if prefer_in_memory else "sqlite",
            "strict_in_memory": strict_in_memory,
            "platform": provider_summary.get("primary_platform") or platform_label(),
            "platforms_used": provider_summary["platforms_used"],
            "multiprocessing_start_method": provider_summary.get("primary_multiprocessing_start_method") or multiprocessing_start_method(),
            "multiprocessing_start_methods_used": provider_summary["multiprocessing_start_methods_used"],
            "memory_preload_enabled": provider_summary["memory_preload_enabled_any"],
            "memory_preload_enabled_any": provider_summary["memory_preload_enabled_any"],
            "memory_preload_seconds": provider_summary["memory_preload_seconds_total"],
            "memory_preload_seconds_total": provider_summary["memory_preload_seconds_total"],
            "estimated_matrix_memory_mb": provider_summary["estimated_matrix_memory_mb_max"],
            "estimated_matrix_memory_mb_max": provider_summary["estimated_matrix_memory_mb_max"],
            "estimated_matrix_memory_mb_sum": provider_summary["estimated_matrix_memory_mb_sum"],
            "workers": worker_count,
            "outer_workers": worker_count,
            "requested_workers_used": provider_summary["requested_workers_used"],
            "matrix_workers": matrix_workers,
            "matrix_workers_used": provider_summary["matrix_workers_used"],
            "matrix_build_seconds": provider_summary.get("matrix_build_seconds"),
            "bulk_read_seconds": provider_summary.get("bulk_read_seconds"),
            "fallback_used": provider_summary["fallback_count"] > 0,
            "fallback_count": provider_summary["fallback_count"],
            "fallback_reasons": provider_summary["fallback_reasons"],
            "cache_strategy": provider_summary.get("primary_cache_strategy") or ("memory_first_bulk_matrix" if bulk_matrix else "sqlite_serial"),
            "cache_strategies_used": provider_summary["cache_strategies_used"],
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

    @staticmethod
    def _provider_metadata_summary(
        factor_eval_results: list[dict[str, Any]],
        factor_backtest_results: list[dict[str, Any]],
    ) -> dict[str, Any]:
        metadata_rows = [
            row.get("performance_metadata") or {}
            for row in [*factor_eval_results, *factor_backtest_results]
            if row.get("performance_metadata")
        ]
        provider_types = sorted({str(row.get("provider_type")) for row in metadata_rows if row.get("provider_type")})
        cache_strategies = sorted({str(row.get("cache_strategy")) for row in metadata_rows if row.get("cache_strategy")})
        platforms = sorted({str(row.get("platform")) for row in metadata_rows if row.get("platform")})
        start_methods = sorted({str(row.get("multiprocessing_start_method")) for row in metadata_rows if row.get("multiprocessing_start_method")})
        requested_workers = sorted({
            int(row.get("requested_workers"))
            for row in metadata_rows
            if row.get("requested_workers") is not None
        })
        matrix_workers = sorted({
            int(row.get("matrix_workers"))
            for row in metadata_rows
            if row.get("matrix_workers") is not None
        })
        fallback_rows = [row for row in metadata_rows if row.get("fallback_used")]
        fallback_reasons = sorted({str(row.get("fallback_reason")) for row in fallback_rows if row.get("fallback_reason")})
        matrix_build_values = [float(row["matrix_build_seconds"]) for row in metadata_rows if row.get("matrix_build_seconds") is not None]
        bulk_read_values = [float(row["bulk_read_seconds"]) for row in metadata_rows if row.get("bulk_read_seconds") is not None]
        memory_preload_values = [float(row["memory_preload_seconds"]) for row in metadata_rows if row.get("memory_preload_seconds") is not None]
        estimated_memory_values = [float(row["estimated_matrix_memory_mb"]) for row in metadata_rows if row.get("estimated_matrix_memory_mb") is not None]
        memory_preload_any = any(bool(row.get("memory_preload_enabled")) for row in metadata_rows)
        return {
            "primary_provider_type": provider_types[0] if len(provider_types) == 1 else None,
            "provider_types_used": provider_types,
            "primary_cache_strategy": cache_strategies[0] if len(cache_strategies) == 1 else None,
            "cache_strategies_used": cache_strategies,
            "primary_platform": platforms[0] if len(platforms) == 1 else None,
            "platforms_used": platforms,
            "primary_multiprocessing_start_method": start_methods[0] if len(start_methods) == 1 else None,
            "multiprocessing_start_methods_used": start_methods,
            "requested_workers_used": requested_workers,
            "matrix_workers_used": matrix_workers,
            "fallback_count": len(fallback_rows),
            "fallback_reasons": fallback_reasons,
            "matrix_build_seconds": round(sum(matrix_build_values), 6) if matrix_build_values else None,
            "bulk_read_seconds": round(sum(bulk_read_values), 6) if bulk_read_values else None,
            "memory_preload_enabled_any": memory_preload_any,
            "memory_preload_seconds_total": round(sum(memory_preload_values), 6) if memory_preload_values else 0.0,
            "estimated_matrix_memory_mb_max": round(max(estimated_memory_values), 6) if estimated_memory_values else None,
            "estimated_matrix_memory_mb_sum": round(sum(estimated_memory_values), 6) if estimated_memory_values else None,
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
        bulk_matrix: bool = True,
        max_workers: int = 4,
        prefer_in_memory: bool = True,
        strict_in_memory: bool = False,
        write_report: bool = False,
        report_dir: str | Path | None = None,
    ) -> dict[str, Any]:
        return run_factor_eval(
            self,
            factor=factor,
            universe=universe,
            start=start,
            end=end,
            bulk_matrix=bulk_matrix,
            max_workers=max_workers,
            prefer_in_memory=prefer_in_memory,
            strict_in_memory=strict_in_memory,
            write_report=write_report,
            report_dir=report_dir,
        )

    def _cache_summary(self, use_cache: bool, cache_stats: bool) -> dict[str, Any]:
        return cache_summary(self, use_cache, cache_stats)

    def _run_factor_backtest(
        self,
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
        return run_factor_backtest(
            self,
            factor=factor,
            universe=universe,
            start=start,
            end=end,
            bulk_matrix=bulk_matrix,
            max_workers=max_workers,
            prefer_in_memory=prefer_in_memory,
            strict_in_memory=strict_in_memory,
            write_report=write_report,
            write_batch_artifact=write_batch_artifact,
            report_dir=report_dir,
            artifact_dir=artifact_dir,
        )

    def _compact_factor_eval_result(self, result, task: FactorBatchTask | None = None) -> dict[str, Any]:
        return compact_factor_eval_result(self, result, task)

    def _compact_factor_backtest_result(
        self,
        result,
        task: FactorBatchTask | None = None,
        artifact_path: str | None = None,
    ) -> dict[str, Any]:
        return compact_factor_backtest_result(self, result, task, artifact_path)

    def _write_batch_artifact(self, kind: str, task: FactorBatchTask | None, report: dict[str, Any], artifact_dir: Path) -> str:
        return write_batch_artifact(kind, task, report, artifact_dir)

    @staticmethod
    def _coverage_pct(coverage: dict | None) -> float | None:
        return coverage_pct(coverage)

    def _factor_regime_rows_from_evaluation(self, result) -> list[dict]:
        return factor_regime_rows_from_evaluation(self, result)

    def _factor_regime_rows_from_backtest(self, result) -> list[dict]:
        return factor_regime_rows_from_backtest(self, result)

    def _regime_for_date(self, date: str) -> str | None:
        return regime_for_date(self, date)

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
        return run_regime_detection(self, report_dir, write_report)

    def _run_strategy(
        self,
        strategy: str,
        start: str | None,
        end: str | None,
        report_dir: str | Path,
        cost_profile: str,
        write_report: bool,
        write_intermediate_reports: bool,
    ) -> dict[str, Any]:
        return StrategyRegistry(self.context, report_dir=report_dir).run(
            strategy=strategy,
            start=start or QUICK_DEFAULT_START,
            end=end or start or QUICK_DEFAULT_START,
            cost_profile=cost_profile,
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

    def _fundamental_coverage(self, symbols: list[str]) -> dict[str, Any]:
        return self.scope_planner.fundamental_coverage(symbols)

    def _has_existing_factor_values(self, factor: str, symbols: list[str]) -> bool:
        return has_existing_factor_values(self, factor, symbols)

    def _factor_store_counts(self) -> dict[str, int]:
        return factor_store_counts(self)

    @staticmethod
    def _factor_evidence_summary(evals: list[dict[str, Any]], backtests: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return factor_evidence_summary(evals, backtests)

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

    @staticmethod
    def _warning_codes(warnings: list[Any]) -> list[str]:
        return warning_codes(warnings)

    @staticmethod
    def _coverage(report: dict[str, Any]) -> float | None:
        return report_coverage(report)

    @staticmethod
    def _num(value: Any) -> float | None:
        return safe_num(value)
