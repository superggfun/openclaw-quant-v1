"""Bounded v0.38 research validation sprint orchestration."""

from __future__ import annotations

import json
import math
import time
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from quant.cli_commands.common import load_alpha_config
from quant.factor_store.factor_registry_store import FactorRegistryStore
from quant.factors.factor_registry import FactorRegistry
from quant.strategy_dsl.strategy_registry import StrategyRegistry
from quant.visualization.chart_builder import ChartBuilder
from quant.walk_forward.walk_forward import DEFAULT_STABILITY_FACTORS


QUICK_FACTOR_PRIORITY = [
    "momentum_20d",
    "momentum_60d",
    "quality_score",
    "low_volatility_score",
    "fundamental_quality_score",
]
QUICK_UNIVERSE = ["SPY", "QQQ", "NVDA", "AAPL", "MSFT"]


@dataclass(frozen=True)
class ValidationStep:
    name: str
    category: str
    target: str
    status: str
    runtime_seconds: float
    report_path: str | None = None
    warnings: list[str] | None = None
    error: str | None = None
    details: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "category": self.category,
            "target": self.target,
            "status": self.status,
            "runtime_seconds": round(self.runtime_seconds, 6),
            "report_path": self.report_path,
            "warnings": list(self.warnings or []),
            "error": self.error,
            "details": self.details or {},
        }


class ResearchValidationRunner:
    """Run bounded research validation without changing engine semantics."""

    def __init__(self, context, report_dir: str | Path = "reports") -> None:
        self.context = context
        self.report_dir = Path(report_dir)
        self.chart_dir = self.report_dir / "charts"
        self.factor_registry = FactorRegistry(context.fundamental_store)

    def run(
        self,
        mode: str = "quick",
        max_factors: int | None = None,
        max_strategies: int | None = None,
        max_folds: int | None = None,
        timeout_seconds: float | None = None,
        batch_size: int | None = None,
        max_symbols: int | None = None,
        factor_family: str = "all",
        resume: bool = False,
        skip_existing: bool = False,
    ) -> dict[str, Any]:
        mode = mode.strip().lower()
        if mode not in {"quick", "full"}:
            raise ValueError("mode must be quick or full")
        family = factor_family.strip().lower()
        if family not in {"price", "fundamental", "all"}:
            raise ValueError("factor_family must be price, fundamental, or all")
        timeout = float(timeout_seconds if timeout_seconds is not None else (120 if mode == "quick" else 3600))
        factors = self._select_factors(mode, max_factors, family)
        strategies = self._select_strategies(mode, max_strategies)
        symbol_diagnostics = self._select_and_filter_symbols(mode, max_symbols, factors)
        universe = symbol_diagnostics["selected_symbols"]
        batches = self._symbol_batches(universe, batch_size or (10 if mode == "quick" else 25))
        folds = max_folds if max_folds is not None else (1 if mode == "quick" else 5)
        reserve_seconds = 15.0 if mode == "quick" else 0.0
        started = time.monotonic()
        steps: list[ValidationStep] = []
        skipped_steps: list[dict[str, Any]] = []
        warning_counter: Counter[str] = Counter()
        factor_eval_results: list[dict[str, Any]] = []
        factor_backtest_results: list[dict[str, Any]] = []
        walk_forward_results: list[dict[str, Any]] = []
        strategy_results: list[dict[str, Any]] = []
        gate_results: list[dict[str, Any]] = []
        completed_batches: list[dict[str, Any]] = []
        skipped_batches: list[dict[str, Any]] = []
        factor_store_before = self._factor_store_counts()

        FactorRegistryStore(self.context.factor_store).sync()

        def budget_exhausted() -> bool:
            return time.monotonic() - started + reserve_seconds >= timeout

        def record_skip(name: str, category: str, target: str, reason: str) -> None:
            step = ValidationStep(name, category, target, "TIMEOUT" if reason == "TIMEOUT" else "SKIPPED", 0.0, warnings=[reason])
            steps.append(step)
            skipped_steps.append(step.to_dict() | {"reason": reason})
            warning_counter.update([reason])

        for factor in factors:
            for batch_index, batch in enumerate(batches, start=1):
                target = f"{factor} batch {batch_index}/{len(batches)}"
                if budget_exhausted():
                    record_skip("factor_eval", "factor", target, "TIMEOUT")
                    continue
                if (skip_existing or resume) and self._has_existing_factor_values(factor, batch):
                    skipped = {
                        "step": "factor_eval",
                        "factor": factor,
                        "batch_index": batch_index,
                        "symbols": batch,
                        "reason": "SKIP_EXISTING",
                    }
                    skipped_batches.append(skipped)
                    record_skip("factor_eval", "factor", target, "SKIP_EXISTING")
                    continue
                step, result = self._timed_step(
                    "factor_eval",
                    "factor",
                    target,
                    lambda f=factor, symbols=batch: self._run_factor_eval(f, symbols),
                    details={"factor": factor, "batch_index": batch_index, "symbols_evaluated": batch},
                )
                steps.append(step)
                warning_counter.update(self._warning_codes(step.warnings))
                if result:
                    result["batch_index"] = batch_index
                    result["batch_symbols"] = batch
                    factor_eval_results.append(result)
                    completed_batches.append(
                        {
                            "step": "factor_eval",
                            "factor": factor,
                            "batch_index": batch_index,
                            "symbols_evaluated": batch,
                            "observations": len(result.get("observations") or []),
                            "runtime_seconds": step.runtime_seconds,
                            "status": step.status,
                            "report_path": step.report_path,
                        }
                    )

        for factor in factors:
            for batch_index, batch in enumerate(batches, start=1):
                target = f"{factor} batch {batch_index}/{len(batches)}"
                if budget_exhausted():
                    record_skip("factor_backtest", "factor", target, "TIMEOUT")
                    continue
                step, result = self._timed_step(
                    "factor_backtest",
                    "factor",
                    target,
                    lambda f=factor, symbols=batch: self._run_factor_backtest(f, symbols),
                    details={"factor": factor, "batch_index": batch_index, "symbols_evaluated": batch},
                )
                steps.append(step)
                warning_counter.update(self._warning_codes(step.warnings))
                if result:
                    result["batch_index"] = batch_index
                    result["batch_symbols"] = batch
                    factor_backtest_results.append(result)
                    completed_batches.append(
                        {
                            "step": "factor_backtest",
                            "factor": factor,
                            "batch_index": batch_index,
                            "symbols_evaluated": batch,
                            "observations": result.get("observations"),
                            "runtime_seconds": step.runtime_seconds,
                            "status": step.status,
                            "report_path": step.report_path,
                        }
                    )

        if not budget_exhausted():
            step, result = self._timed_step("detect_regime", "regime", "SPY", self._run_regime_detection)
            steps.append(step)
            warning_counter.update(self._warning_codes(step.warnings))
            regime_detection = result or {}
        else:
            record_skip("detect_regime", "regime", "SPY", "TIMEOUT")
            regime_detection = {}

        for strategy in strategies:
            if budget_exhausted():
                record_skip("strategy_run_with_gates", "strategy", strategy, "TIMEOUT")
                continue
            step, result = self._timed_step("strategy_run_with_gates", "strategy", strategy, lambda s=strategy: self._run_strategy(s))
            steps.append(step)
            warning_counter.update(self._warning_codes(step.warnings))
            if result:
                strategy_results.append(result)
                gate_path = ((result.get("artifacts") or {}).get("strategy_gate_report_path"))
                if gate_path:
                    try:
                        gate_report = json.loads(Path(gate_path).read_text(encoding="utf-8"))
                        gate_results.append(gate_report)
                        warning_counter.update(self._warning_codes(gate_report.get("warnings") or []))
                    except (FileNotFoundError, json.JSONDecodeError):
                        warning_counter.update(["WARN_GATE_REPORT_UNREADABLE"])

        for factor in self._major_factors(factors):
            if budget_exhausted():
                record_skip("walk_forward", "factor", factor, "TIMEOUT")
                continue
            step, result = self._timed_step("walk_forward", "factor", factor, lambda f=factor: self._run_walk_forward_factor(f, folds, universe))
            steps.append(step)
            warning_counter.update(self._warning_codes(step.warnings))
            if result:
                walk_forward_results.append(result)

        factor_rank = self.context.factor_store.rank_factors(limit=50)
        regime_rank = self.context.regime_analytics.regime_rank(limit=10)
        factor_store_after = self._factor_store_counts()
        factor_store_growth = {
            table: factor_store_after.get(table, 0) - factor_store_before.get(table, 0)
            for table in sorted(set(factor_store_before) | set(factor_store_after))
        }
        warning_counter.update(self._warning_codes(factor_rank.get("warnings") or []))
        warning_counter.update(self._warning_codes(regime_rank.get("warnings") or []))

        runtime = time.monotonic() - started
        slow_threshold = max(2.0, timeout / 20.0)
        slow_steps = [
            step.to_dict() | {"reason": "SLOW_STEP"}
            for step in sorted(steps, key=lambda item: item.runtime_seconds, reverse=True)
            if step.runtime_seconds >= slow_threshold
        ][:10]
        for _ in slow_steps:
            warning_counter.update(["SLOW_STEP"])
        partial = any(step.status in {"FAIL", "TIMEOUT", "SKIPPED"} for step in steps) or runtime >= timeout
        if partial:
            warning_counter.update(["PARTIAL_RESULTS"])

        factor_rankings = self._factor_rankings(factors, factor_eval_results, factor_backtest_results, walk_forward_results, factor_rank)
        strategy_rankings = self._strategy_rankings(strategy_results)
        current_regime = self._current_regime(regime_detection, regime_rank)
        best_current_regime_factor = self._best_current_regime_factor(current_regime, regime_rank)
        recommendations = self._recommendations(warning_counter, strategy_rankings)

        report = {
            "metadata": {
                "report_type": "research_validation",
                "generated_at": datetime.now().isoformat(timespec="seconds"),
                "release": "v0.39.0-research-validation-coverage-expansion",
                "folded_release": "v0.38.0 research validation was folded into v0.39.0 before release because the original unbounded validation was too slow.",
                "feature_development_frozen": True,
                "offline_research_only": True,
                "live_trading": False,
                "broker_integration": False,
            },
            "mode": mode,
            "parameters": {
                "max_factors": max_factors,
                "max_strategies": max_strategies,
                "max_folds": folds,
                "timeout_seconds": timeout,
                "batch_size": batch_size or (10 if mode == "quick" else 25),
                "max_symbols": max_symbols,
                "factor_family": family,
                "resume": resume,
                "skip_existing": skip_existing,
                "universe": universe,
            },
            "symbol_diagnostics": symbol_diagnostics,
            "coverage_statistics": {
                "explicit_universe_size": symbol_diagnostics.get("requested_symbol_count"),
                "evaluated_symbols": symbol_diagnostics.get("selected_symbol_count"),
                "skipped_symbols": symbol_diagnostics.get("skipped_symbol_count"),
                "missing_price_symbols": symbol_diagnostics.get("missing_price_symbols", []),
                "price_coverage": (symbol_diagnostics.get("price_coverage") or {}).get("coverage_pct"),
                "fundamental_coverage": (symbol_diagnostics.get("fundamental_coverage") or {}).get("coverage_pct"),
            },
            "factor_store_growth": {
                "before": factor_store_before,
                "after": factor_store_after,
                "growth": factor_store_growth,
            },
            "regime_sample_counts": self.context.regime_history_store.counts(),
            "batching": {
                "batch_count": len(batches),
                "completed_batches": completed_batches,
                "skipped_batches": skipped_batches,
            },
            "runtime_seconds": round(runtime, 6),
            "status": "WARNING" if partial or warning_counter else "PASS",
            "partial_results": partial,
            "completed_steps": [step.to_dict() for step in steps if step.status in {"PASS", "WARNING"}],
            "skipped_steps": skipped_steps,
            "timed_out_steps": [step.to_dict() for step in steps if step.status == "TIMEOUT"],
            "slowest_steps": [step.to_dict() for step in sorted(steps, key=lambda item: item.runtime_seconds, reverse=True)[:10]],
            "slow_steps": slow_steps,
            "factor_rankings": factor_rankings,
            "top_10_factors": factor_rankings[:10],
            "strategy_rankings": strategy_rankings,
            "top_5_strategies": strategy_rankings[:5],
            "current_regime": current_regime,
            "best_factor_in_current_regime": best_current_regime_factor,
            "warning_statistics": [{"code": code, "count": count} for code, count in warning_counter.most_common()],
            "factor_evidence_summary": self._factor_evidence_summary(factor_eval_results, factor_backtest_results),
            "factor_eval_results": factor_eval_results,
            "factor_backtest_results": factor_backtest_results,
            "walk_forward_results": walk_forward_results,
            "strategy_results": strategy_results,
            "gate_results": gate_results,
            "factor_rank_report": factor_rank,
            "regime_rank_report": regime_rank,
            "recommendations": recommendations,
            "recommended_performance_work": [
                "Add semantic-preserving caching around factor rows per signal_date.",
                "Cache latest fundamental-as-of lookups by symbol/date.",
                "Avoid writing intermediate reports when a caller requests in-memory validation only.",
                "Keep core engine semantics unchanged before considering parallelism or storage migrations.",
            ],
            "interpretation_notes": [
                "v0.39 combines the bounded research validation sprint and coverage expansion before release.",
                "Quick mode is bounded smoke/research validation, not full-universe validation.",
                "Full mode uses all selected factors and default fold settings and can run much longer.",
                "Expanded universe evidence is passed internally by research-validation; default factor-eval CLI behavior is unchanged unless a caller supplies a custom universe through the engine API.",
                "Gate PASS/WARNING/FAIL/REJECTED statuses are research quality controls, not trading authorization.",
                "v0.39 records runtime bottlenecks only; it does not add multiprocessing, numba, parquet, vectorized backtests, parameter tuning, or warning suppression.",
            ],
        }
        report = self._write_outputs(report)
        return report

    def _run_factor_eval(self, factor: str, universe: list[str] | None) -> dict[str, Any]:
        result = self.context.factor_evaluation.evaluate(factor=factor, universe=universe)
        saved = self.context.factor_store.save_factor_evaluation(result)
        try:
            regime_saved = self.context.regime_analytics.save_factor_evaluation_by_regime(result)
        except Exception as exc:
            regime_saved = {"error": str(exc)}
        return result.to_report() | {"report_path": result.report_path, "saved_factor_history": saved, "saved_regime_history": regime_saved}

    def _run_factor_backtest(self, factor: str, universe: list[str] | None) -> dict[str, Any]:
        result = self.context.factor_backtest_engine.run(factor=factor, universe=universe)
        saved = self.context.factor_store.save_factor_backtest(result)
        try:
            regime_saved = self.context.regime_analytics.save_factor_backtest_by_regime(result)
        except Exception as exc:
            regime_saved = {"error": str(exc)}
        return result.to_report() | {"report_path": result.report_path, "saved_factor_history": saved, "saved_regime_history": regime_saved}

    def _run_walk_forward_factor(self, factor: str, max_folds: int | None, universe: list[str] | None) -> dict[str, Any]:
        result = self.context.walk_forward_engine.run(strategy="factor_long_short", factor=factor, max_folds=max_folds, universe=universe)
        saved = self.context.factor_store.save_walk_forward(result, factor=factor)
        return result.to_report() | {"report_path": result.report_path, "saved_factor_history": saved}

    def _run_regime_detection(self) -> dict[str, Any]:
        return self.context.regime_analytics.detect_and_save()

    def _run_strategy(self, strategy: str) -> dict[str, Any]:
        return StrategyRegistry(self.context).run(strategy=strategy, with_gates=True)

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
        all_factors = sorted(self.factor_registry.factor_names())
        if factor_family == "price":
            all_factors = [factor for factor in all_factors if not self.factor_registry.describe(factor).fundamental_data_required]
        elif factor_family == "fundamental":
            all_factors = [factor for factor in all_factors if self.factor_registry.describe(factor).fundamental_data_required]
        if mode == "full":
            selected = all_factors
        else:
            priority = [factor for factor in QUICK_FACTOR_PRIORITY if factor in all_factors]
            selected = priority + [factor for factor in all_factors if factor not in priority]
        limit = max_factors if max_factors is not None else (1 if mode == "quick" else len(selected))
        return selected[: max(int(limit), 0)]

    def _select_and_filter_symbols(self, mode: str, max_symbols: int | None, factors: list[str]) -> dict[str, Any]:
        requested = QUICK_UNIVERSE if mode == "quick" and max_symbols is None else self.context.price_store.list_symbols()
        min_history = self._minimum_history_days(factors)
        selected: list[str] = []
        skipped: list[dict[str, str | int]] = []
        for symbol in requested:
            history = self.context.price_store.get_price_history(symbol)
            close_count = 0 if history.empty else int(history["close"].dropna().shape[0])
            if history.empty:
                skipped.append({"symbol": symbol, "reason": "no price data", "close_history": close_count})
                continue
            if close_count < min_history:
                skipped.append({"symbol": symbol, "reason": "insufficient close history", "close_history": close_count})
                continue
            selected.append(symbol)
            if max_symbols is not None and len(selected) >= max_symbols:
                break
        if not selected and mode == "quick":
            selected = QUICK_UNIVERSE[: max_symbols or len(QUICK_UNIVERSE)]
        return {
            "requested_symbol_count": len(requested),
            "selected_symbol_count": len(selected),
            "selected_symbols": selected,
            "skipped_symbol_count": len(skipped),
            "skipped_symbols": skipped[:200],
            "missing_price_symbols": [row["symbol"] for row in skipped if row["reason"] == "no price data"],
            "price_coverage": {
                "symbols_with_price_data": len(selected),
                "symbols_without_price_data": sum(1 for row in skipped if row["reason"] == "no price data"),
                "coverage_pct": len(selected) / len(requested) if requested else None,
            },
            "minimum_close_history_required": min_history,
            "fundamental_coverage": self._fundamental_coverage(selected),
        }

    def _minimum_history_days(self, factors: list[str]) -> int:
        lookbacks = [self.factor_registry.describe(factor).lookback_days for factor in factors if factor in self.factor_registry.factor_names()]
        return max([80, *lookbacks]) + 20

    @staticmethod
    def _symbol_batches(symbols: list[str], batch_size: int) -> list[list[str]]:
        size = max(int(batch_size), 1)
        return [symbols[index : index + size] for index in range(0, len(symbols), size)] or [[]]

    def _fundamental_coverage(self, symbols: list[str]) -> dict[str, Any]:
        if not symbols:
            return {"symbols_with_fundamentals": 0, "symbols_missing_fundamentals": 0, "coverage_pct": None}
        rows = self.context.fundamental_store.rows("fundamental_metrics", symbols)
        covered = sorted({str(row.get("symbol", "")).upper() for row in rows if row.get("report_date")})
        missing = sorted(set(symbols) - set(covered))
        return {
            "symbols_with_fundamentals": len(covered),
            "symbols_missing_fundamentals": len(missing),
            "coverage_pct": len(covered) / len(symbols) if symbols else None,
            "covered_symbols": covered,
            "missing_symbols": missing[:200],
        }

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
            row["observations"] += len(result.get("observations") or [])
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
        rows = StrategyRegistry(self.context).list_strategies().get("strategies") or []
        strategies = [row["name"] for row in rows if row.get("valid") and row.get("name")]
        limit = max_strategies if max_strategies is not None else (1 if mode == "quick" else len(strategies))
        return strategies[: max(int(limit), 0)]

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
        eval_by = {row.get("factor"): row for row in evals}
        bt_by = {row.get("factor"): row for row in backtests}
        wf_by = {((row.get("parameters") or {}).get("factor")): row for row in walk_forwards}
        confidence_by = {}
        for row in (factor_rank.get("top_factors") or []) + (factor_rank.get("worst_factors") or []):
            confidence_by[row.get("factor_name")] = self._num(row.get("confidence_score"))
        output = []
        for factor in factors:
            ev = eval_by.get(factor, {})
            bt = bt_by.get(factor, {})
            wf = wf_by.get(factor, {})
            summary = wf.get("summary") or {}
            metrics = {
                "ic": self._num(ev.get("ic_mean")),
                "rank_ic": self._num(ev.get("rank_ic_mean")),
                "icir": self._num(ev.get("icir")),
                "coverage": self._coverage(ev),
                "long_short_return": self._num(bt.get("long_short_return")),
                "sharpe": self._num(bt.get("long_short_sharpe") if bt.get("long_short_sharpe") is not None else bt.get("sharpe")),
                "drawdown": self._num(bt.get("max_drawdown")),
                "walk_forward_test_sharpe": self._num(summary.get("average_test_sharpe")),
                "confidence": confidence_by.get(factor),
            }
            score_values = [value for key, value in metrics.items() if key not in {"coverage", "drawdown", "long_short_return"} and value is not None]
            evidence_score = sum(score_values) / len(score_values) if score_values else None
            output.append({"factor": factor, **metrics, "evidence_score": evidence_score})
        return sorted(output, key=lambda row: (-10**9 if row["evidence_score"] is None else row["evidence_score"], row["factor"]), reverse=True)

    @staticmethod
    def _strategy_rankings(strategy_results: list[dict[str, Any]]) -> list[dict[str, Any]]:
        rows = []
        for report in strategy_results:
            summary = report.get("trade_sim_summary") or {}
            gate = report.get("gate_summary") or {}
            rows.append(
                {
                    "strategy": report.get("strategy_name"),
                    "version": report.get("strategy_version"),
                    "status": report.get("status"),
                    "gate_status": gate.get("overall_status"),
                    "final_equity": summary.get("final_equity"),
                    "total_return": summary.get("total_return"),
                    "max_drawdown": summary.get("max_drawdown"),
                    "trade_count": summary.get("trade_count"),
                    "warning_count": len(report.get("warnings") or []),
                    "report_path": report.get("report_path"),
                    "gate_report_path": (report.get("artifacts") or {}).get("strategy_gate_report_path"),
                }
            )
        return sorted(rows, key=lambda row: (row.get("gate_status") == "PASS", ResearchValidationRunner._num(row.get("total_return")) or -10**9), reverse=True)

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
        recommendations = []
        if any(code in warnings for code in ("WARN_LOW_FACTOR_COVERAGE", "PARTIAL_FUNDAMENTAL_DATA")):
            recommendations.append("Improve factor and fundamental coverage before relying on accounting-heavy strategies.")
        if warnings.get("WARN_LOW_WALK_FORWARD_FOLDS"):
            recommendations.append("Persist more walk-forward evidence for candidate factors and strategies.")
        if warnings.get("WARN_LOW_REGIME_SAMPLE"):
            recommendations.append("Extend regime history and factor-by-regime samples before regime-aware decisions.")
        if warnings.get("SLOW_STEP"):
            recommendations.append("Prioritize semantic-preserving cache work for slow validation steps.")
        if not any(row.get("gate_status") == "PASS" for row in strategies):
            recommendations.append("Keep current DSL strategies in research candidate status until gates pass without warnings.")
        recommendations.append("Do not tune parameters from this sprint; use evidence to prioritize data and validation improvements.")
        return recommendations

    def _write_outputs(self, report: dict[str, Any]) -> dict[str, Any]:
        self.report_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        json_path = self.report_dir / f"research_validation_{stamp}.json"
        report = report | {"report_path": str(json_path)}
        json_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
        summary_path = self.report_dir / "research_validation_summary.md"
        summary_path.write_text(self._markdown_summary(report), encoding="utf-8")
        agent_path = self.report_dir / "agent_export_research_validation.md"
        agent_path.write_text(self._agent_summary(report), encoding="utf-8")
        charts = self._charts(report, stamp)
        report["summary_path"] = str(summary_path)
        report["agent_summary_path"] = str(agent_path)
        report["visualizations"] = [chart.to_dict() for chart in charts]
        json_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
        return report

    def _charts(self, report: dict[str, Any], stamp: str):
        builder = ChartBuilder(self.chart_dir)
        prefix = f"research_validation_{stamp}"
        charts = [
            builder.bar_chart(prefix, "factor_evidence_ranking", "Factor Evidence Ranking", {row["factor"]: row.get("evidence_score") for row in report["top_10_factors"]}),
            builder.bar_chart(prefix, "strategy_returns", "Strategy Returns", {row["strategy"]: row.get("total_return") for row in report["strategy_rankings"]}),
            builder.bar_chart(prefix, "warning_frequency", "Warning Frequency", {row["code"]: row["count"] for row in report["warning_statistics"][:12]}),
            builder.bar_chart(prefix, "coverage", "Factor Coverage", {row["factor"]: row.get("coverage") for row in report["factor_rankings"] if row.get("coverage") is not None}),
        ]
        clean = [chart for chart in charts if chart is not None]
        builder.dashboard(
            prefix=prefix,
            title="Research Validation Sprint",
            report_type="research_validation",
            metrics={
                "mode": report["mode"],
                "status": report["status"],
                "runtime_seconds": report["runtime_seconds"],
                "current_regime": report["current_regime"],
            },
            charts=clean,
            warnings=[f"{row['code']}: {row['count']}" for row in report["warning_statistics"][:10]],
            notes=report["interpretation_notes"],
        )
        return clean

    @staticmethod
    def _markdown_summary(report: dict[str, Any]) -> str:
        lines = [
            "# v0.38.0 Research Validation Sprint",
            "",
            "## Executive Summary",
            f"- Mode: {report['mode']}",
            f"- Status: {report['status']}",
            f"- Runtime seconds: {report['runtime_seconds']}",
            f"- Partial results: {report['partial_results']}",
            f"- Current regime: {report['current_regime']}",
            "",
            "## Top Factors",
        ]
        for row in report["top_10_factors"]:
            lines.append(f"- {row['factor']}: score={row.get('evidence_score')} ic={row.get('ic')} rank_ic={row.get('rank_ic')} confidence={row.get('confidence')}")
        lines.extend(["", "## Top Strategies"])
        for row in report["top_5_strategies"]:
            lines.append(f"- {row['strategy']}: gate={row.get('gate_status')} return={row.get('total_return')} warnings={row.get('warning_count')}")
        lines.extend(["", "## Most Common Warnings"])
        for row in report["warning_statistics"][:20]:
            lines.append(f"- {row['code']}: {row['count']}")
        lines.extend(["", "## Recommendations"])
        for item in report["recommendations"]:
            lines.append(f"- {item}")
        return "\n".join(lines) + "\n"

    @staticmethod
    def _agent_summary(report: dict[str, Any]) -> str:
        top = report["top_10_factors"][0]["factor"] if report["top_10_factors"] else "N/A"
        warning = report["warning_statistics"][0]["code"] if report["warning_statistics"] else "N/A"
        best_regime = (report.get("best_factor_in_current_regime") or {}).get("factor_name")
        return "\n".join(
            [
                "# Agent Research Validation Summary",
                f"Mode: {report['mode']}",
                f"Current regime: {report['current_regime']}",
                f"What works: {top} has the strongest current evidence score in this bounded run.",
                f"What is uncertain: {warning} is the most common warning.",
                f"Best factor in current regime: {best_regime}",
                "What does not work: strategies remain research candidates unless gates pass without warnings.",
                "Next: improve coverage, persist more validation history, and review slow steps before full sprint runs.",
            ]
        ) + "\n"

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
        coverage = report.get("factor_coverage") or {}
        for key in ("coverage_pct", "coverage", "symbols_with_data_pct"):
            value = ResearchValidationRunner._num(coverage.get(key))
            if value is not None:
                return value
        return ResearchValidationRunner._num((report.get("saved_factor_history") or {}).get("coverage"))

    @staticmethod
    def _num(value: Any) -> float | None:
        try:
            number = float(value)
            return number if math.isfinite(number) else None
        except (TypeError, ValueError):
            return None
