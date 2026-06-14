"""Alpha Stability Audit Orchestrator – Module 7.

Runs all audit modules for one or more factors and produces a unified report.

HPC: universe_sensitivity copies the DB to /dev/shm (RAM disk) and
parallelises its backtests internally via ProcessPoolExecutor.
Other modules remain sequential – a single backtest each, so per-module
parallelism adds overhead without benefit.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from quant.config import DEFAULT_SYMBOLS
from quant.engines.factor_backtest.factor_backtest import FactorBacktest, FactorBacktestResult
from quant.engines.factor_eval.factor_evaluation import SUPPORTED_FACTORS
from quant.engines.alpha_stability.models import AuditModuleResult
from quant.engines.alpha_stability.universe_sensitivity import run_universe_sensitivity
from quant.engines.alpha_stability.cost_sensitivity import run_cost_sensitivity
from quant.engines.alpha_stability.turnover_audit import run_turnover_audit
from quant.engines.alpha_stability.decile_analysis import run_decile_analysis
from quant.engines.alpha_stability.ic_decay import run_ic_decay
from quant.engines.alpha_stability.stability_score import compute_stability_score
from quant.reports.report_io import generate_report_path, write_json_report
from quant.storage.sqlite_store import SQLitePriceStore
from quant.data.fundamental.fundamental_store import FundamentalStore


@dataclass(frozen=True)
class AlphaStabilityAuditResult:
    """Complete audit result for a single factor."""

    factor: str
    composite_score: float
    status: str
    modules: dict[str, AuditModuleResult]
    runtime_seconds: float
    report_path: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "factor": self.factor,
            "composite_score": round(self.composite_score, 2),
            "status": self.status,
            "modules": {k: v.to_dict() for k, v in self.modules.items()},
            "runtime_seconds": round(self.runtime_seconds, 6),
            "report_path": self.report_path,
        }


class AlphaStabilityAudit:
    """Orchestrate all alpha stability audit modules.

    Modules run sequentially.  Parallelism lives *inside*
    universe_sensitivity (ProcessPoolExecutor + /dev/shm RAM disk).
    Set `universe_workers` (default: up to 8) for more concurrency.
    """

    def __init__(
        self,
        price_store: SQLitePriceStore,
        fundamental_store: FundamentalStore | None = None,
        report_dir: str | Path = "reports",
        universe_workers: int | None = None,
    ) -> None:
        self.price_store = price_store
        self.fundamental_store = fundamental_store
        self.report_dir = Path(report_dir)
        self.universe_workers = universe_workers

    def run(
        self,
        factor: str,
        *,
        universe: list[str] | None = None,
        start: str | None = None,
        end: str | None = None,
        holding_period: int = 20,
        quantiles: int = 5,
        universe_sizes: list[int] | None = None,
        cost_levels_bps: list[int] | None = None,
        ic_horizons: list[int] | None = None,
        fold_consistency_score: float | None = None,
        bulk_matrix: bool = True,
        write_report: bool = True,
    ) -> AlphaStabilityAuditResult:
        """Run the full stability audit for *factor*.

        ``bulk_matrix`` (default True) enables accelerated matrix-path evaluation
        and backtest for all modules.
        """

        started = time.monotonic()
        modules: dict[str, AuditModuleResult] = {}

        # Phase 1: Baseline backtest
        backtest_engine = FactorBacktest(self.price_store, self.fundamental_store)
        try:
            baseline_universe = list(universe) if universe else None
            baseline = backtest_engine.run(
                factor=factor,
                start=start,
                end=end,
                holding_period=holding_period,
                quantiles=quantiles,
                universe=baseline_universe,
                bulk_matrix=bulk_matrix,
                write_report=False,
            )
        except (ValueError, Exception) as exc:
            runtime = time.monotonic() - started
            return AlphaStabilityAuditResult(
                factor=factor,
                composite_score=0.0,
                status="fail",
                modules={},
                runtime_seconds=runtime,
                report_path="",
            )

        # Module 1: Universe Sensitivity (internally parallel)
        try:
            modules["universe_sensitivity"] = run_universe_sensitivity(
                factor=factor,
                price_store=self.price_store,
                fundamental_store=self.fundamental_store,
                universe_sizes=universe_sizes,
                symbols=universe,
                start=start,
                end=end,
                holding_period=holding_period,
                quantiles=quantiles,
                max_workers=self.universe_workers,
                bulk_matrix=bulk_matrix,
            )
        except Exception as exc:
            modules["universe_sensitivity"] = AuditModuleResult(
                module="universe_sensitivity",
                status="fail",
                score=0.0,
                details={"error": str(exc)},
                warnings=[str(exc)],
            )

        # Module 2: Cost Sensitivity
        try:
            modules["cost_sensitivity"] = run_cost_sensitivity(
                factor=factor,
                price_store=self.price_store,
                fundamental_store=self.fundamental_store,
                cost_levels_bps=cost_levels_bps,
                universe=universe,
                start=start,
                end=end,
                holding_period=holding_period,
                quantiles=quantiles,
                bulk_matrix=bulk_matrix,
            )
        except Exception as exc:
            modules["cost_sensitivity"] = AuditModuleResult(
                module="cost_sensitivity",
                status="fail",
                score=0.0,
                details={"error": str(exc)},
                warnings=[str(exc)],
            )

        # Module 3: Turnover Audit
        try:
            modules["turnover_audit"] = run_turnover_audit(baseline)
        except Exception as exc:
            modules["turnover_audit"] = AuditModuleResult(
                module="turnover_audit",
                status="fail",
                score=0.0,
                details={"error": str(exc)},
                warnings=[str(exc)],
            )

        # Module 4: Decile Analysis
        try:
            modules["decile_analysis"] = run_decile_analysis(
                factor=factor,
                price_store=self.price_store,
                fundamental_store=self.fundamental_store,
                universe=universe,
                start=start,
                end=end,
                holding_period=holding_period,
                bulk_matrix=bulk_matrix,
            )
        except Exception as exc:
            modules["decile_analysis"] = AuditModuleResult(
                module="decile_analysis",
                status="fail",
                score=0.0,
                details={"error": str(exc)},
                warnings=[str(exc)],
            )

        # Module 5: IC Decay
        try:
            modules["ic_decay"] = run_ic_decay(
                factor=factor,
                price_store=self.price_store,
                fundamental_store=self.fundamental_store,
                horizons=ic_horizons,
                universe=universe,
                start=start,
                end=end,
            )
        except Exception as exc:
            modules["ic_decay"] = AuditModuleResult(
                module="ic_decay",
                status="fail",
                score=0.0,
                details={"error": str(exc)},
                warnings=[str(exc)],
            )

        # Module 6: Stability Score
        stability = compute_stability_score(
            universe_result=modules.get("universe_sensitivity"),
            cost_result=modules.get("cost_sensitivity"),
            turnover_result=modules.get("turnover_audit"),
            ic_decay_result=modules.get("ic_decay"),
            fold_consistency_score=fold_consistency_score,
        )
        modules["stability_score"] = stability

        runtime = time.monotonic() - started

        result = AlphaStabilityAuditResult(
            factor=factor,
            composite_score=stability.score,
            status=stability.status,
            modules=modules,
            runtime_seconds=runtime,
            report_path="",
        )

        if write_report:
            report_path = self._write_report(result)
            result = replace(result, report_path=str(report_path))

        return result

    def run_all(
        self,
        *,
        factors: list[str] | None = None,
        universe: list[str] | None = None,
        start: str | None = None,
        end: str | None = None,
        holding_period: int = 20,
        quantiles: int = 5,
        universe_sizes: list[int] | None = None,
        cost_levels_bps: list[int] | None = None,
        ic_horizons: list[int] | None = None,
        write_report: bool = True,
    ) -> list[AlphaStabilityAuditResult]:
        """Run audit for multiple factors sequentially."""
        target_factors = factors or sorted(SUPPORTED_FACTORS)
        results = []
        for factor in target_factors:
            result = self.run(
                factor,
                universe=universe,
                start=start,
                end=end,
                holding_period=holding_period,
                quantiles=quantiles,
                universe_sizes=universe_sizes,
                cost_levels_bps=cost_levels_bps,
                ic_horizons=ic_horizons,
                write_report=write_report,
            )
            results.append(result)
        return results

    def _write_report(self, result: AlphaStabilityAuditResult) -> Path:
        path = generate_report_path(self.report_dir, f"alpha_stability_{result.factor}")
        write_json_report(path, result.to_dict())
        return path
