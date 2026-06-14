"""Performance profiler for existing OpenClaw Quant engines."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from quant.engines.factor_backtest.factor_backtest import FactorBacktest
from quant.engines.factor_eval.factor_evaluation import FactorEvaluation
from quant.performance.performance_registry import DEFAULT_PROFILE_FACTORS, normalize_targets
from quant.performance.performance_report import PerformanceReportBuilder
from quant.performance.runtime_tracker import RuntimeTracker
from quant.research_validation import ResearchValidationRunner
from quant.strategy_dsl.strategy_registry import StrategyRegistry
from quant.engines.walk_forward.walk_forward import WalkForwardEngine


class ProfiledPriceStore:
    """Timing proxy for SQLitePriceStore read paths."""

    def __init__(self, inner: Any, tracker: RuntimeTracker) -> None:
        self.inner = inner
        self.tracker = tracker
        self.query_stats: dict[str, dict[str, Any]] = {}

    def __getattr__(self, name: str) -> Any:
        return getattr(self.inner, name)

    def _record_query(self, name: str, runtime: float, rows: int | None = None) -> None:
        bucket = self.query_stats.setdefault(name, {"name": name, "count": 0, "runtime_seconds": 0.0, "rows": 0})
        bucket["count"] += 1
        bucket["runtime_seconds"] += runtime
        if rows is not None:
            bucket["rows"] += rows
        self.tracker.record("database", name, runtime, {"rows": rows})

    def get_price_history(self, *args: Any, **kwargs: Any):
        started = time.perf_counter()
        result = self.inner.get_price_history(*args, **kwargs)
        runtime = time.perf_counter() - started
        self._record_query("get_price_history", runtime, len(result) if hasattr(result, "__len__") else None)
        return result

    def get_prices(self, *args: Any, **kwargs: Any):
        started = time.perf_counter()
        result = self.inner.get_prices(*args, **kwargs)
        runtime = time.perf_counter() - started
        self._record_query("get_prices", runtime, len(result) if hasattr(result, "__len__") else None)
        return result

    def list_symbols(self, *args: Any, **kwargs: Any):
        started = time.perf_counter()
        result = self.inner.list_symbols(*args, **kwargs)
        runtime = time.perf_counter() - started
        self._record_query("list_symbols", runtime, len(result) if hasattr(result, "__len__") else None)
        return result

    def latest_date(self, *args: Any, **kwargs: Any):
        started = time.perf_counter()
        result = self.inner.latest_date(*args, **kwargs)
        runtime = time.perf_counter() - started
        self._record_query("latest_date", runtime, 1 if result else 0)
        return result

    def profile(self) -> dict[str, Any]:
        rows = [
            {
                **values,
                "runtime_seconds": round(values["runtime_seconds"], 6),
            }
            for values in self.query_stats.values()
        ]
        return {
            "query_count": sum(row["count"] for row in rows),
            "runtime_seconds": round(sum(row["runtime_seconds"] for row in rows), 6),
            "slowest_queries": sorted(rows, key=lambda item: item["runtime_seconds"], reverse=True)[:20],
        }


class ProfiledFundamentalStore:
    """Timing proxy for FundamentalStore lookup paths."""

    def __init__(self, inner: Any, tracker: RuntimeTracker) -> None:
        self.inner = inner
        self.tracker = tracker
        self.lookup_count = 0
        self.lookup_runtime = 0.0

    def __getattr__(self, name: str) -> Any:
        return getattr(self.inner, name)

    def rows(self, *args: Any, **kwargs: Any):
        started = time.perf_counter()
        result = self.inner.rows(*args, **kwargs)
        runtime = time.perf_counter() - started
        self.lookup_count += 1
        self.lookup_runtime += runtime
        self.tracker.record("fundamental_lookup", "rows", runtime, {"rows": len(result) if hasattr(result, "__len__") else None})
        return result

    def profile(self) -> dict[str, Any]:
        return {
            "lookup_count": self.lookup_count,
            "runtime_seconds": round(self.lookup_runtime, 6),
            "slowest_lookup": "rows" if self.lookup_count else None,
        }


class PerformanceProfiler:
    """Run bounded performance profiling around existing engines."""

    def __init__(self, context: Any, report_dir: str | Path = "reports") -> None:
        self.context = context
        self.report_dir = Path(report_dir)

    def run(
        self,
        targets: list[str] | None = None,
        factors: list[str] | None = None,
        max_symbols: int = 5,
        max_factors: int = 2,
        max_folds: int = 1,
        timeout_seconds: float = 180.0,
        bulk_matrix: bool = True,
        workers: int = 1,
        strict_in_memory: bool = False,
    ) -> dict[str, Any]:
        tracker = RuntimeTracker()
        profiled_prices = ProfiledPriceStore(self.context.price_store, tracker)
        profiled_fundamentals = ProfiledFundamentalStore(self.context.fundamental_store, tracker)
        factor_evaluation = FactorEvaluation(profiled_prices, profiled_fundamentals)
        factor_backtest = FactorBacktest(profiled_prices, profiled_fundamentals)
        walk_forward = WalkForwardEngine(profiled_prices, profiled_fundamentals)
        selected_targets = normalize_targets(targets)
        selected_factors = self._select_factors(factors, max_factors)
        symbols = self._select_symbols(profiled_prices, max_symbols)
        started = time.perf_counter()
        results: list[dict[str, Any]] = []

        for target in selected_targets:
            if time.perf_counter() - started >= timeout_seconds:
                results.append({"target": target, "status": "TIMEOUT", "runtime_seconds": 0.0, "details": {"reason": "profile budget exhausted"}})
                continue
            if target == "factor_eval":
                results.extend(
                    self._profile_factor_eval(
                        factor_evaluation,
                        selected_factors,
                        symbols,
                        tracker,
                        bulk_matrix=bulk_matrix,
                        workers=workers,
                        strict_in_memory=strict_in_memory,
                    )
                )
            elif target == "factor_backtest":
                results.extend(
                    self._profile_factor_backtest(
                        factor_backtest,
                        selected_factors[:1],
                        symbols,
                        tracker,
                        bulk_matrix=bulk_matrix,
                        workers=workers,
                        strict_in_memory=strict_in_memory,
                    )
                )
            elif target == "walk_forward":
                results.extend(self._profile_walk_forward(walk_forward, selected_factors[:1], symbols, max_folds, tracker))
            elif target == "strategy_run":
                results.append(self._profile_strategy_run(tracker))
            elif target == "research_validation":
                results.append(
                    self._profile_research_validation(
                        max_symbols=min(max_symbols, 10),
                        tracker=tracker,
                        bulk_matrix=bulk_matrix,
                        workers=workers,
                        strict_in_memory=strict_in_memory,
                    )
                )

        factor_store_profile = self._profile_factor_store(tracker)
        report = PerformanceReportBuilder(self.report_dir).build(
            parameters={
                "targets": selected_targets,
                "factors": selected_factors,
                "max_symbols": max_symbols,
                "max_factors": max_factors,
                "max_folds": max_folds,
                "timeout_seconds": timeout_seconds,
                "symbols": symbols,
                "bulk_matrix": bulk_matrix,
                "workers": workers,
                "strict_in_memory": strict_in_memory,
            },
            tracker_summary=tracker.summary(),
            target_results=results,
            database_profile=profiled_prices.profile(),
            factor_store_profile=factor_store_profile,
            fundamental_profile=profiled_fundamentals.profile(),
        )
        return report

    def latest_report(self) -> dict[str, Any] | None:
        return PerformanceReportBuilder(self.report_dir).latest_profile()

    def _profile_factor_eval(
        self,
        engine: FactorEvaluation,
        factors: list[str],
        symbols: list[str],
        tracker: RuntimeTracker,
        bulk_matrix: bool,
        workers: int,
        strict_in_memory: bool,
    ) -> list[dict[str, Any]]:
        rows = []
        for factor in factors:
            with tracker.track("factor_eval", factor, symbols=len(symbols)):
                started = time.perf_counter()
                result = engine.evaluate(
                    factor=factor,
                    universe=symbols,
                    bulk_matrix=bulk_matrix,
                    max_workers=workers,
                    strict_in_memory=strict_in_memory,
                    cache_stats=bulk_matrix,
                )
                runtime = time.perf_counter() - started
            hpc_details = self._hpc_details(result.performance_metadata)
            hpc_details["eval_seconds"] = hpc_details.get("eval_seconds") or round(runtime, 6)
            rows.append(
                {
                    "target": "factor_eval",
                    "factor": factor,
                    "status": "PASS" if not result.warnings else "WARNING",
                    "runtime_seconds": round(runtime, 6),
                    "details": {
                        "observations": len(result.observations),
                        "ic_mean": result.ic_mean,
                        "rank_ic_mean": result.rank_ic_mean,
                        "report_path": result.report_path,
                        "warnings": result.warnings,
                        **hpc_details,
                    },
                }
            )
        return rows

    def _profile_factor_backtest(
        self,
        engine: FactorBacktest,
        factors: list[str],
        symbols: list[str],
        tracker: RuntimeTracker,
        bulk_matrix: bool,
        workers: int,
        strict_in_memory: bool,
    ) -> list[dict[str, Any]]:
        rows = []
        for factor in factors:
            with tracker.track("factor_backtest", factor, symbols=len(symbols)):
                started = time.perf_counter()
                result = engine.run(
                    factor=factor,
                    universe=symbols,
                    bulk_matrix=bulk_matrix,
                    max_workers=workers,
                    strict_in_memory=strict_in_memory,
                )
                runtime = time.perf_counter() - started
            hpc_details = self._hpc_details(result.performance_metadata)
            rows.append(
                {
                    "target": "factor_backtest",
                    "factor": factor,
                    "status": "PASS" if not result.warnings else "WARNING",
                    "runtime_seconds": round(runtime, 6),
                    "details": {
                        "observations": result.observations,
                        "long_short_return": result.long_short_return,
                        "sharpe": result.long_short_sharpe,
                        "report_path": result.report_path,
                        "warnings": result.warnings,
                        **hpc_details,
                    },
                }
            )
        return rows

    def _profile_walk_forward(
        self,
        engine: WalkForwardEngine,
        factors: list[str],
        symbols: list[str],
        max_folds: int,
        tracker: RuntimeTracker,
    ) -> list[dict[str, Any]]:
        rows = []
        for factor in factors:
            with tracker.track("walk_forward", factor, symbols=len(symbols), max_folds=max_folds):
                started = time.perf_counter()
                result = engine.run(strategy="factor_long_short", factor=factor, universe=symbols, max_folds=max_folds)
                runtime = time.perf_counter() - started
            rows.append(
                {
                    "target": "walk_forward",
                    "factor": factor,
                    "status": "PASS" if not result.warnings else "WARNING",
                    "runtime_seconds": round(runtime, 6),
                    "details": {
                        "fold_count": result.summary.get("fold_count"),
                        "average_test_sharpe": result.summary.get("average_test_sharpe"),
                        "report_path": result.report_path,
                        "warnings": result.warnings,
                    },
                }
            )
        return rows

    def _profile_strategy_run(self, tracker: RuntimeTracker) -> dict[str, Any]:
        with tracker.track("strategy_run", "momentum_fundamental"):
            started = time.perf_counter()
            result = StrategyRegistry(self.context).run(strategy="momentum_fundamental")
            runtime = time.perf_counter() - started
        return {
            "target": "strategy_run",
            "strategy": "momentum_fundamental",
            "status": result.get("status", "PASS"),
            "runtime_seconds": round(runtime, 6),
            "details": {
                "trade_sim_summary": result.get("trade_sim_summary"),
                "report_path": result.get("report_path"),
            },
        }

    def _profile_research_validation(
        self,
        max_symbols: int,
        tracker: RuntimeTracker,
        bulk_matrix: bool,
        workers: int,
        strict_in_memory: bool,
    ) -> dict[str, Any]:
        with tracker.track("research_validation", "quick", max_symbols=max_symbols):
            started = time.perf_counter()
            result = ResearchValidationRunner(self.context).run(
                mode="quick",
                max_factors=1,
                max_strategies=0,
                max_folds=1,
                max_symbols=max_symbols,
                batch_size=max(1, min(5, max_symbols)),
                timeout_seconds=30,
                bulk_matrix=bulk_matrix,
                workers=workers,
                strict_in_memory=strict_in_memory,
            )
            runtime = time.perf_counter() - started
        hpc_details = self._hpc_details(result.get("performance_metadata") or {})
        return {
            "target": "research_validation",
            "status": result.get("status", "PASS"),
            "runtime_seconds": round(runtime, 6),
            "details": {
                "partial_results": result.get("partial_results"),
                "completed_batches": len((result.get("batching") or {}).get("completed_batches") or []),
                "report_path": result.get("report_path"),
                **hpc_details,
            },
        }

    def _profile_factor_store(self, tracker: RuntimeTracker) -> dict[str, Any]:
        with tracker.track("factor_store", "rank_factors"):
            started = time.perf_counter()
            result = self.context.factor_store.rank_factors(limit=10)
            runtime = time.perf_counter() - started
        return {
            "load_runtime_seconds": round(runtime, 6),
            "save_runtime_seconds": 0.0,
            "ranked_factors": len(result.get("top_factors") or []),
        }

    def _select_factors(self, factors: list[str] | None, max_factors: int) -> list[str]:
        selected = factors or list(DEFAULT_PROFILE_FACTORS)
        return selected[: max(1, max_factors)]

    @staticmethod
    def _select_symbols(price_store: Any, max_symbols: int) -> list[str]:
        symbols = price_store.list_symbols()
        filtered = []
        for symbol in symbols:
            history = price_store.get_price_history(symbol)
            if not history.empty and len(history["close"].dropna()) >= 120:
                filtered.append(symbol)
            if len(filtered) >= max_symbols:
                break
        return filtered or ["SPY", "QQQ", "AAPL", "MSFT", "NVDA"][:max_symbols]

    @staticmethod
    def _hpc_details(metadata: dict[str, Any] | None) -> dict[str, Any]:
        metadata = metadata or {}
        return {
            "provider_type": metadata.get("provider_type"),
            "cache_strategy": metadata.get("cache_strategy"),
            "fallback_used": metadata.get("fallback_used"),
            "fallback_reason": metadata.get("fallback_reason"),
            "matrix_workers": metadata.get("matrix_workers"),
            "matrix_build_seconds": metadata.get("matrix_build_seconds"),
            "eval_seconds": metadata.get("eval_seconds"),
        }
