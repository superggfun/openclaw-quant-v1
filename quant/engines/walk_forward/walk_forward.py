"""Walk-forward validation for alpha and factor long-short strategies."""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from datetime import datetime
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import pandas as pd

from quant.config import DEFAULT_SYMBOLS
from quant.core.collections import dedupe_by
from quant.core.symbols import normalize_symbols
from quant.reports.report_io import generate_report_path, write_json_report
from quant.storage.sqlite_store import SQLitePriceStore
from quant.data.fundamental.fundamental_store import FundamentalStore
from quant.engines.walk_forward.models import WalkForwardFoldTask, WalkForwardFold, WalkForwardResult
from quant.engines.walk_forward.fold_runner import run_fold_worker, factor_stability_worker
from quant.engines.walk_forward.rolling_validation import RollingValidation
from quant.factors.price.factor_registry import FactorRegistry
from quant.engines.backtest.backtest_engine import PortfolioBacktestEngine
from quant.engines.factor_backtest.factor_backtest import FactorBacktest

DEFAULT_STABILITY_FACTORS = [
    "momentum_20d",
    "momentum_60d",
    "quality_price_proxy",
    "growth_price_proxy",
    "low_volatility_score",
    "value_price_proxy",
    "reversal_5d",
    "reversal_20d",
    "risk_adjusted_momentum",
    "fundamental_value_score",
    "fundamental_quality_score",
    "fundamental_growth_score",
    "fundamental_health_score",
    "fundamental_composite_score",
]

# Module-level helper for row counting in purge/embargo reporting

def _count_price_rows(price_store, symbols: list[str], start: str, end: str) -> int:
    """Count unique trading days across all symbols in a date range."""
    dates = set()
    for symbol in symbols:
        history = price_store.get_price_history(symbol, start=start, end=end)
        if not history.empty and "date" in history.columns:
            dates.update(str(d) for d in history["date"])
    return len(dates)

# Module-level worker for factor stability IC computation
def _factor_stability_worker(task):
    return factor_stability_worker(task)


class WalkForwardEngine:
    """Run deterministic out-of-sample validation without changing strategy semantics."""

    def __init__(
        self,
        price_store: SQLitePriceStore,
        fundamental_store: FundamentalStore | None = None,
        report_dir: str | Path = "reports",
    ) -> None:
        self.price_store = price_store
        self.report_dir = Path(report_dir)
        self.fundamental_store = fundamental_store or FundamentalStore(price_store.db_path)
        self.factor_registry = FactorRegistry(self.fundamental_store)

    def run(
        self,
        strategy: str = "alpha",
        factor: str = "momentum_20d",
        train_years: float = 3.0,
        test_years: float = 1.0,
        start: str | None = None,
        end: str | None = None,
        universe: list[str] | None = None,
        initial_cash: float = 100000.0,
        rebalance_frequency: str = "monthly",
        alpha_config: dict | None = None,
        pipeline_config: dict | None = None,
        max_folds: int | None = 5,
        write_report: bool = True,
        parallel: bool = False,
        workers: int | None = None,
        purge_days: int = 0,
        embargo_days: int = 0,
    ) -> WalkForwardResult:
        strategy = strategy.strip().lower()
        if strategy not in {"alpha", "factor_long_short"}:
            raise ValueError("strategy must be one of: alpha, factor_long_short")
        if train_years <= 0 or test_years <= 0:
            raise ValueError("train_years and test_years must be positive")

        # Auto-default purge_days to factor's forward_return_horizon if both are 0
        if purge_days == 0 and embargo_days == 0:
            try:
                definition = self.factor_registry.describe(factor)
                if definition.forward_return_horizon > 0:
                    purge_days = definition.forward_return_horizon
            except (ValueError, AttributeError):
                pass

        symbols = self._normalize_symbols(universe or list(DEFAULT_SYMBOLS))
        start_date, end_date = self._date_range(symbols, start, end)
        fold_windows = self.generate_windows(start_date, end_date, train_years, test_years,
                                              purge_days=purge_days, embargo_days=embargo_days)
        if max_folds is not None and max_folds > 0 and len(fold_windows) > max_folds:
            fold_windows = fold_windows[-max_folds:]
        if not fold_windows:
            raise ValueError("not enough history to generate walk-forward folds")

        if parallel:
            folds = self._run_folds_parallel(
                fold_windows=fold_windows,
                strategy=strategy,
                factor=factor,
                symbols=symbols,
                initial_cash=initial_cash,
                rebalance_frequency=rebalance_frequency,
                alpha_config=alpha_config,
                pipeline_config=pipeline_config,
                workers=workers,
            )
        else:
            folds = []
            for index, window in enumerate(fold_windows, start=1):
                folds.append(
                    self._run_fold(
                        index=index,
                        strategy=strategy,
                        factor=factor,
                        window=window,
                        symbols=symbols,
                        initial_cash=initial_cash,
                        rebalance_frequency=rebalance_frequency,
                        alpha_config=alpha_config,
                        pipeline_config=pipeline_config,
                    )
                )
        summary = self._summary(folds)
        warnings = self._warnings(folds)
        rolling = RollingValidation.analyze(
            {fold.test_end: fold.test_return for fold in folds if fold.test_return is not None},
            {fold.test_end: fold.ic for fold in folds if fold.ic is not None},
            {fold.test_end: fold.rank_ic for fold in folds if fold.rank_ic is not None},
            window=min(3, max(len(folds), 1)),
        )
        stability = self.factor_stability(
            factors=DEFAULT_STABILITY_FACTORS,
            symbols=symbols,
            start=start_date,
            end=end_date,
            max_folds=max_folds,
            fold_windows=fold_windows,
            parallel=parallel,
            workers=workers,
        )
        recommendations = self._recommendations(warnings, stability)
        result = WalkForwardResult(
            metadata={
                "created_at": datetime.now().isoformat(timespec="seconds"),
                "engine": "WalkForwardEngine",
                "no_lookahead": True,
                "validation_layer_only": True,
            },
            strategy=strategy,
            parameters={
                "factor": factor,
                "validation_notes": (
                    "factor_long_short returns are research spread returns, not cash-account equity curves"
                    if strategy == "factor_long_short"
                    else "alpha uses the existing no-lookahead next-trading-day execution backtest path"
                ),
                "train_years": train_years,
                "test_years": test_years,
                "start": start_date,
                "end": end_date,
                "universe": symbols,
                "initial_cash": initial_cash,
                "rebalance_frequency": rebalance_frequency,
                "max_folds": max_folds,
                "purge_days": purge_days,
                "embargo_days": embargo_days,
            },
            folds=folds,
            summary=summary,
            rolling_validation=rolling,
            stability_analysis=stability,
            warnings=warnings,
            recommendations=recommendations,
            report_path="",
        )
        path = self._write_report(result) if write_report else ""
        return replace(result, report_path=str(path))

    @staticmethod
    def generate_windows(
        start: str,
        end: str,
        train_years: float,
        test_years: float,
        purge_days: int = 0,
        embargo_days: int = 0,
    ) -> list[dict[str, str]]:
        start_ts = pd.to_datetime(start)
        end_ts = pd.to_datetime(end)
        train_days = max(1, int(round(train_years * 365.25)))
        test_days = max(1, int(round(test_years * 365.25)))
        purge_delta = pd.Timedelta(days=purge_days) if purge_days > 0 else pd.Timedelta(days=0)
        embargo_delta = pd.Timedelta(days=embargo_days) if embargo_days > 0 else pd.Timedelta(days=0)
        windows = []
        train_start = start_ts
        while True:
            train_end = train_start + pd.Timedelta(days=train_days - 1)
            effective_train_end = train_end - purge_delta
            if effective_train_end <= train_start:
                effective_train_end = train_start
            test_start = train_end + pd.Timedelta(days=1) + embargo_delta
            test_end = test_start + pd.Timedelta(days=test_days - 1)
            if test_end > end_ts:
                break
            windows.append(
                {
                    "train_start": train_start.strftime("%Y-%m-%d"),
                    "train_end": effective_train_end.strftime("%Y-%m-%d"),
                    "train_end_raw": train_end.strftime("%Y-%m-%d"),
                    "test_start": test_start.strftime("%Y-%m-%d"),
                    "test_end": test_end.strftime("%Y-%m-%d"),
                    "purge_days": purge_days,
                    "embargo_days": embargo_days,
                }
            )
            train_start = train_start + pd.Timedelta(days=test_days)
        return windows

    def factor_stability(
        self,
        factors: list[str],
        symbols: list[str],
        start: str,
        end: str,
        max_folds: int | None,
        fold_windows: list[dict[str, str]] | None = None,
        parallel: bool = False,
        workers: int | None = None,
        forward_days: int = 20,
    ) -> dict[str, Any]:
        windows = fold_windows or self.generate_windows(start, end, 3.0, 1.0)
        if max_folds is not None and max_folds > 0 and len(windows) > max_folds:
            windows = windows[-max_folds:]
        if parallel:
            started = time.monotonic()
            # Build task list: one per (factor, window) combination
            tasks = []
            for factor in factors:
                if factor not in self.factor_registry.factor_names():
                    continue
                higher_is_better = self.factor_registry.describe(factor).higher_is_better
                for wi, window in enumerate(windows):
                    tasks.append({
                        "factor": factor,
                        "higher_is_better": higher_is_better,
                        "window_idx": wi,
                        "symbols": list(symbols),
                        "start": window["test_start"],
                        "end": window["test_end"],
                        "forward_days": 20,
                        "db_path": str(self.price_store.db_path),
                    })
            wcount = workers or min(len(tasks), 4)
            wcount = max(1, min(wcount, len(tasks)))

            from collections import defaultdict
            factor_ic = defaultdict(list)
            factor_rank_ic = defaultdict(list)

            if wcount == 1:
                for t in tasks:
                    fn, _, ic, rank_ic = _factor_stability_worker(t)
                    if ic is not None:
                        factor_ic[fn].append(ic)
                    if rank_ic is not None:
                        factor_rank_ic[fn].append(rank_ic)
            else:
                with ProcessPoolExecutor(max_workers=wcount) as executor:
                    futures = [executor.submit(_factor_stability_worker, t) for t in tasks]
                    for future in as_completed(futures):
                        fn, _, ic, rank_ic = future.result()
                        if ic is not None:
                            factor_ic[fn].append(ic)
                        if rank_ic is not None:
                            factor_rank_ic[fn].append(rank_ic)

            elapsed = time.monotonic() - started
            import sys
            print(
                f"[factor_stability parallel] {len(tasks)} tasks x {wcount} workers "
                f"-> {elapsed:.1f}s wall",
                file=sys.stderr,
            )

            ranking = {}
            for factor in factors:
                if factor not in self.factor_registry.factor_names():
                    continue
                ic_values = factor_ic.get(factor, [])
                rank_ic_values = factor_rank_ic.get(factor, [])
                ranking[factor] = self._stability_metrics(ic_values, rank_ic_values)
                ranking[factor]["fold_count"] = len(ic_values)
        else:
            ranking = {}
            for factor in factors:
                if factor not in self.factor_registry.factor_names():
                    continue
                higher_is_better = self.factor_registry.describe(factor).higher_is_better
                ic_values = []
                rank_ic_values = []
                for window in windows:
                    ic, rank_ic = self._lightweight_factor_ic(
                        factor=factor,
                        higher_is_better=higher_is_better,
                        symbols=symbols,
                        start=window["test_start"],
                        end=window["test_end"],
                        forward_days=forward_days,
                    )
                    if ic is not None:
                        ic_values.append(ic)
                    if rank_ic is not None:
                        rank_ic_values.append(rank_ic)
                ranking[factor] = self._stability_metrics(ic_values, rank_ic_values)
                ranking[factor]["fold_count"] = len(ic_values)
        ordered = sorted(
            ranking.items(),
            key=lambda item: (item[1]["score"] if item[1]["score"] is not None else -999),
            reverse=True,
        )
        return {
            "factor_stability_ranking": [
                {"factor": factor, **metrics}
                for factor, metrics in ordered
            ],
            "methodology": (
                "ranking and classification use direction-adjusted IC. "
                "absolute_stability_score is retained only as a signal-strength diagnostic."
            ),
        }

    def _lightweight_factor_ic(
        self,
        factor: str,
        higher_is_better: bool,
        symbols: list[str],
        start: str,
        end: str,
        forward_days: int,
    ) -> tuple[float | None, float | None]:
        """Compute per-date IC / rank IC using FactorMatrixBuilder (vectorized)."""
        from quant.factor_acceleration import FactorMatrixBuilder
        matrix = FactorMatrixBuilder(self.price_store, self.factor_registry).build(
            factor=factor,
            symbols=symbols,
            start=start,
            end=end,
            forward_days=forward_days,
        )
        rows = [
            {
                "signal_date": row.signal_date,
                "symbol": row.symbol,
                "factor_value": self._directional_factor_value(row.factor_value, higher_is_better),
                "future_return": row.future_return,
            }
            for row in matrix.valid_rows
        ]
        if not rows:
            return None, None
        frame = pd.DataFrame(rows)
        return self._compute_ic_from_frame(frame)


    def _run_folds_parallel(
        self,
        fold_windows,
        strategy,
        factor,
        symbols,
        initial_cash,
        rebalance_frequency,
        alpha_config,
        pipeline_config,
        workers,
    ):
        worker_count = workers or min(len(fold_windows), 4)
        worker_count = max(1, min(worker_count, len(fold_windows)))
        started = time.monotonic()

        tasks = []
        for index, w in enumerate(fold_windows, start=1):
            tasks.append(WalkForwardFoldTask(
                index=index,
                strategy=strategy,
                factor=factor,
                train_start=w["train_start"],
                train_end=w["train_end"],
                test_start=w["test_start"],
                test_end=w["test_end"],
                symbols=list(symbols),
                initial_cash=initial_cash,
                rebalance_frequency=rebalance_frequency,
                alpha_config=dict(alpha_config) if alpha_config else None,
                pipeline_config=dict(pipeline_config) if pipeline_config else None,
                db_path=str(self.price_store.db_path),
                report_dir=str(self.report_dir),
                purge_days=w.get("purge_days", 0),
                embargo_days=w.get("embargo_days", 0),
            ))

        results = []
        if worker_count == 1:
            for task in tasks:
                results.append(run_fold_worker(task))
        else:
            with ProcessPoolExecutor(max_workers=worker_count) as executor:
                futures = {executor.submit(run_fold_worker, t): t.index for t in tasks}
                for future in as_completed(futures):
                    results.append(future.result())
            results.sort(key=lambda f: f.fold)

        elapsed = time.monotonic() - started
        import sys
        print(
            f"[walk_forward parallel] {len(tasks)} folds x {worker_count} workers "
            f"-> {elapsed:.1f}s wall",
            file=sys.stderr,
        )
        return results

    def _run_fold(
        self,
        index: int,
        strategy: str,
        factor: str,
        window: dict[str, str],
        symbols: list[str],
        initial_cash: float,
        rebalance_frequency: str,
        alpha_config: dict | None,
        pipeline_config: dict | None,
    ) -> WalkForwardFold:
        if strategy == "alpha":
            return self._run_alpha_fold(index, window, symbols, initial_cash, rebalance_frequency, alpha_config, pipeline_config, factor)
        return self._run_factor_fold(index, factor, window, symbols, pipeline_config)

    def _run_alpha_fold(
        self,
        index: int,
        window: dict[str, str],
        symbols: list[str],
        initial_cash: float,
        rebalance_frequency: str,
        alpha_config: dict | None,
        pipeline_config: dict | None,
        factor: str = "",
    ) -> WalkForwardFold:
        config = dict(alpha_config or {})
        config["universe"] = symbols
        if factor and not config.get("factor_weights") and not config.get("multi_factor"):
            config["factor_weights"] = {factor: 1.0}
        engine = PortfolioBacktestEngine(self.price_store, report_dir=self.report_dir)
        train = engine.run(
            start=window["train_start"],
            end=window["train_end"],
            initial_cash=initial_cash,
            strategy="alpha",
            rebalance_frequency=rebalance_frequency,
            alpha_config=config,
            alpha_pipeline_config=pipeline_config,
        )
        test = engine.run(
            start=window["test_start"],
            end=window["test_end"],
            initial_cash=initial_cash,
            strategy="alpha",
            rebalance_frequency=rebalance_frequency,
            alpha_config=config,
            alpha_pipeline_config=pipeline_config,
        )
        # Compute row counts for purge/embargo reporting
        e_train = _count_price_rows(self.price_store, symbols, window["train_start"], window["train_end"])
        e_test = _count_price_rows(self.price_store, symbols, window["test_start"], window["test_end"])
        pd = window.get("purge_days", 0)
        ed = window.get("embargo_days", 0)
        r_purge = 0
        if pd > 0 and "train_end_raw" in window:
            import pandas as _pd2
            purge_start = (_pd2.Timestamp(window["train_end"]) + _pd2.Timedelta(days=1)).strftime("%Y-%m-%d")
            r_purge = _count_price_rows(self.price_store, symbols, purge_start, window["train_end_raw"])
        r_embargo = ed  # embargo calendar days = embargo gap
        fold = WalkForwardFold(
            fold=index,
            fold_id=f"fold_{index:03d}",
            train_start=window["train_start"],
            train_end=window["train_end"],
            test_start=window["test_start"],
            test_end=window["test_end"],
            train_return=train.metrics.total_return,
            test_return=test.metrics.total_return,
            train_sharpe=train.metrics.sharpe_ratio,
            test_sharpe=test.metrics.sharpe_ratio,
            train_max_drawdown=-abs(train.metrics.max_drawdown),
            test_max_drawdown=-abs(test.metrics.max_drawdown),
            ic=None,
            rank_ic=None,
            icir=None,
            turnover=test.metrics.turnover,
            cost=test.metrics.total_cost,
            train_report=train.report_path,
            test_report=test.report_path,
            no_lookahead=bool(train.no_lookahead and test.no_lookahead),
            fold_warnings=[],
            purge_days=pd,
            embargo_days=ed,
            removed_by_purge=r_purge,
            removed_by_embargo=r_embargo,
            effective_train_rows=e_train,
            effective_test_rows=e_test,
        )
        return self._with_fold_warnings(fold, strategy="alpha")

    def _run_factor_fold(
        self,
        index: int,
        factor: str,
        window: dict[str, str],
        symbols: list[str],
        pipeline_config: dict | None,
    ) -> WalkForwardFold:
        backtest = FactorBacktest(self.price_store, self.fundamental_store, report_dir=self.report_dir)
        train = backtest.run(
            factor=factor,
            start=window["train_start"],
            end=window["train_end"],
            holding_period=forward_days,
            universe=symbols,
            pipeline_config=pipeline_config,
        )
        test = backtest.run(
            factor=factor,
            start=window["test_start"],
            end=window["test_end"],
            holding_period=forward_days,
            universe=symbols,
            pipeline_config=pipeline_config,
        )
        # Compute purge/embargo row counts
        purge_days = int(window.get("purge_days", 0))
        embargo_days = int(window.get("embargo_days", 0))
        effective_train_rows = _count_price_rows(self.price_store, symbols, window["train_start"], window["train_end"])
        effective_test_rows = _count_price_rows(self.price_store, symbols, window["test_start"], window["test_end"])
        raw_train_end = pd.Timestamp(window["train_end"]) + pd.Timedelta(days=purge_days)
        removed_by_purge = 0
        if purge_days > 0:
            purge_start = (pd.Timestamp(window["train_end"]) + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
            removed_by_purge = _count_price_rows(self.price_store, symbols, purge_start, raw_train_end.strftime("%Y-%m-%d"))
        removed_by_embargo = 0
        if embargo_days > 0:
            embargo_start = (raw_train_end + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
            embargo_end = (pd.Timestamp(window["test_start"]) - pd.Timedelta(days=1)).strftime("%Y-%m-%d")
            removed_by_embargo = _count_price_rows(self.price_store, symbols, embargo_start, embargo_end)
        fold = WalkForwardFold(
            fold=index,
            fold_id=f"fold_{index:03d}",
            train_start=window["train_start"],
            train_end=window["train_end"],
            test_start=window["test_start"],
            test_end=window["test_end"],
            train_return=train.long_short_return,
            test_return=test.long_short_return,
            train_sharpe=train.long_short_sharpe,
            test_sharpe=test.long_short_sharpe,
            train_max_drawdown=train.max_drawdown,
            test_max_drawdown=test.max_drawdown,
            ic=test.ic_mean,
            rank_ic=test.rank_ic_mean,
            icir=test.icir,
            turnover=test.turnover,
            cost=0.0,
            train_report=train.report_path,
            test_report=test.report_path,
            no_lookahead=bool(train.no_lookahead and test.no_lookahead),
            fold_warnings=[],
            purge_days=purge_days,
            embargo_days=embargo_days,
            removed_by_purge=removed_by_purge,
            removed_by_embargo=removed_by_embargo,
            effective_train_rows=effective_train_rows,
            effective_test_rows=effective_test_rows,
        )
        return self._with_fold_warnings(fold, strategy="factor_long_short")

    def _date_range(self, symbols: list[str], start: str | None, end: str | None) -> tuple[str, str]:
        dates = []
        for symbol in symbols:
            history = self.price_store.get_price_history(symbol)
            if not history.empty:
                dates.extend(str(value) for value in history["date"].tolist())
        if not dates:
            raise ValueError("no price history available for walk-forward universe")
        inferred_start = max(min(dates), start) if start else min(dates)
        inferred_end = min(max(dates), end) if end else max(dates)
        if pd.to_datetime(inferred_start) >= pd.to_datetime(inferred_end):
            raise ValueError("walk-forward start must be before end")
        return inferred_start, inferred_end

    def _summary(self, folds: list[WalkForwardFold]) -> dict[str, Any]:
        train_returns = [fold.train_return for fold in folds if fold.train_return is not None]
        test_returns = [fold.test_return for fold in folds if fold.test_return is not None]
        train_sharpes = [fold.train_sharpe for fold in folds if fold.train_sharpe is not None]
        test_sharpes = [fold.test_sharpe for fold in folds if fold.test_sharpe is not None]
        ic_values = [fold.ic for fold in folds if fold.ic is not None]
        rank_ic_values = [fold.rank_ic for fold in folds if fold.rank_ic is not None]
        icir_values = [fold.icir for fold in folds if fold.icir is not None]
        best = max(folds, key=lambda fold: fold.test_return if fold.test_return is not None else -999)
        worst = min(folds, key=lambda fold: fold.test_return if fold.test_return is not None else 999)
        return {
            "fold_count": len(folds),
            "average_train_return": self._mean(train_returns),
            "average_test_return": self._mean(test_returns),
            "average_train_sharpe": self._mean(train_sharpes),
            "average_test_sharpe": self._mean(test_sharpes),
            "average_ic": self._mean(ic_values),
            "average_rank_ic": self._mean(rank_ic_values),
            "average_icir": self._mean(icir_values),
            "best_fold": asdict(best),
            "worst_fold": asdict(worst),
        }

    def _warnings(self, folds: list[WalkForwardFold]) -> list[dict[str, str]]:
        warnings = []
        for fold in folds:
            warnings.extend(fold.fold_warnings)
            if (fold.train_sharpe or 0.0) > 2.0 and (fold.test_sharpe or 0.0) < 0.5:
                warnings.append({"code": "WARN_OVERFIT", "reason": f"fold {fold.fold} train Sharpe > 2.0 but test Sharpe < 0.5"})
            if fold.ic is not None and abs(fold.ic) < 0.01:
                warnings.append({"code": "WARN_FACTOR_DECAY", "reason": f"fold {fold.fold} test IC is near zero"})
            if fold.train_return is not None and fold.test_return is not None and fold.train_return > 0 and fold.test_return < 0:
                warnings.append({"code": "WARN_REGIME_DEPENDENT", "reason": f"fold {fold.fold} train return positive but test return negative"})
            if not fold.no_lookahead:
                warnings.append({"code": "WARN_NO_LOOKAHEAD_NOT_CONFIRMED", "reason": f"fold {fold.fold} source report was not marked no_lookahead"})
        return self._dedupe_warnings(warnings)

    @staticmethod
    def _with_fold_warnings(fold: WalkForwardFold, strategy: str) -> WalkForwardFold:
        warnings = list(fold.fold_warnings)
        if (
            fold.test_return is not None
            and fold.test_sharpe is not None
            and fold.test_return > 1.0
            and fold.test_sharpe < 0.5
        ):
            warnings.append(
                {
                    "code": "WARN_COMPOUNDED_RETURN_WEAK_SHARPE",
                    "reason": (
                        f"{fold.fold_id} has high compounded test return but weak arithmetic Sharpe; "
                        "inspect return path stability"
                    ),
                }
            )
        if strategy == "factor_long_short" and fold.test_return is not None and fold.test_return <= -0.999999:
            warnings.append(
                {
                    "code": "WARN_SPREAD_RETURN_WIPEOUT",
                    "reason": (
                        f"{fold.fold_id} factor long-short spread compounded to about -100%; "
                        "research spread returns are not cash-account equity curves"
                    ),
                }
            )
        if pd.to_datetime(fold.train_end) >= pd.to_datetime(fold.test_start):
            warnings.append(
                {
                    "code": "WARN_TRAIN_TEST_OVERLAP",
                    "reason": f"{fold.fold_id} train_end is not before test_start",
                }
            )
        return WalkForwardFold(
            fold=fold.fold,
            fold_id=fold.fold_id,
            train_start=fold.train_start,
            train_end=fold.train_end,
            test_start=fold.test_start,
            test_end=fold.test_end,
            train_return=fold.train_return,
            test_return=fold.test_return,
            train_sharpe=fold.train_sharpe,
            test_sharpe=fold.test_sharpe,
            train_max_drawdown=fold.train_max_drawdown,
            test_max_drawdown=fold.test_max_drawdown,
            ic=fold.ic,
            rank_ic=fold.rank_ic,
            icir=fold.icir,
            turnover=fold.turnover,
            cost=fold.cost,
            train_report=fold.train_report,
            test_report=fold.test_report,
            no_lookahead=fold.no_lookahead,
            fold_warnings=warnings,
            purge_days=getattr(fold, "purge_days", 0),
            embargo_days=getattr(fold, "embargo_days", 0),
            removed_by_purge=getattr(fold, "removed_by_purge", 0),
            removed_by_embargo=getattr(fold, "removed_by_embargo", 0),
            effective_train_rows=getattr(fold, "effective_train_rows", 0),
            effective_test_rows=getattr(fold, "effective_test_rows", 0),
        )

    @staticmethod
    def _recommendations(warnings: list[dict[str, str]], stability: dict[str, Any]) -> list[str]:
        codes = {warning["code"] for warning in warnings}
        recommendations = ["review out-of-sample folds before promoting strategy"]
        if "WARN_OVERFIT" in codes:
            recommendations.append("simplify signal rules or reduce selection pressure")
        if "WARN_FACTOR_DECAY" in codes:
            recommendations.append("compare factor decay across horizons")
        if "WARN_REGIME_DEPENDENT" in codes:
            recommendations.append("inspect regime-specific periods and benchmark context")
        ranking = stability.get("factor_stability_ranking") or []
        if ranking:
            recommendations.append(f"prioritize stable factors such as {ranking[0]['factor']}")
        return recommendations

    @staticmethod
    def _compute_ic_from_frame(frame: pd.DataFrame) -> tuple[float | None, float | None]:
        """Compute mean IC and mean rank IC from a DataFrame of per-day observations."""
        ic_values = []
        rank_ic_values = []
        for _, group in frame.groupby("signal_date"):
            if len(group) < 2:
                continue
            if group["factor_value"].nunique() < 2 or group["future_return"].nunique() < 2:
                continue
            ic = group["factor_value"].corr(group["future_return"])
            rank_ic = group["factor_value"].rank().corr(group["future_return"].rank())
            if pd.notna(ic):
                ic_values.append(float(ic))
            if pd.notna(rank_ic):
                rank_ic_values.append(float(rank_ic))
        mean_ic = sum(ic_values) / len(ic_values) if ic_values else None
        mean_rank_ic = sum(rank_ic_values) / len(rank_ic_values) if rank_ic_values else None
        return mean_ic, mean_rank_ic

    @staticmethod
    def _directional_factor_value(value: float, higher_is_better: bool) -> float:
        return float(value) if higher_is_better else -float(value)

    @staticmethod
    def _directional_stability_score(ic_values: list[float], rank_ic_values: list[float]) -> float | None:
        values = [float(value) for value in ic_values + rank_ic_values if value is not None and pd.notna(value)]
        if not values:
            return None
        mean = float(pd.Series(values, dtype="float64").mean())
        penalty = float(pd.Series(values, dtype="float64").std()) if len(values) > 1 else 0.0
        return mean - penalty

    @staticmethod
    def _absolute_stability_score(ic_values: list[float], rank_ic_values: list[float]) -> float | None:
        values = [abs(float(value)) for value in ic_values + rank_ic_values if value is not None and pd.notna(value)]
        if not values:
            return None
        mean = float(pd.Series(values, dtype="float64").mean())
        penalty = float(pd.Series(values, dtype="float64").std()) if len(values) > 1 else 0.0
        return mean - penalty

    @staticmethod
    def _stability_metrics(ic_values: list[float], rank_ic_values: list[float]) -> dict[str, Any]:
        directional_score = WalkForwardEngine._directional_stability_score(ic_values, rank_ic_values)
        absolute_score = WalkForwardEngine._absolute_stability_score(ic_values, rank_ic_values)
        return {
            "classification": WalkForwardEngine._stability_label(directional_score),
            "score": directional_score,
            "directional_stability_score": directional_score,
            "absolute_stability_score": absolute_score,
            "average_ic": WalkForwardEngine._mean(ic_values),
            "average_rank_ic": WalkForwardEngine._mean(rank_ic_values),
            "mean_directional_ic": WalkForwardEngine._mean(ic_values),
            "mean_directional_rank_ic": WalkForwardEngine._mean(rank_ic_values),
            "mean_abs_ic": WalkForwardEngine._mean_abs(ic_values),
            "mean_abs_rank_ic": WalkForwardEngine._mean_abs(rank_ic_values),
            "direction_consistency": WalkForwardEngine._direction_consistency(ic_values + rank_ic_values),
        }

    @staticmethod
    def _stability_label(score: float | None) -> str:
        if score is None:
            return "insufficient_data"
        if score >= 0.05:
            return "stable"
        if score >= 0.015:
            return "moderate"
        return "unstable"

    @staticmethod
    def _mean(values: list[float]) -> float | None:
        clean = [float(value) for value in values if value is not None and pd.notna(value)]
        if not clean:
            return None
        return float(sum(clean) / len(clean))

    @staticmethod
    def _mean_abs(values: list[float]) -> float | None:
        clean = [abs(float(value)) for value in values if value is not None and pd.notna(value)]
        if not clean:
            return None
        return float(sum(clean) / len(clean))

    @staticmethod
    def _direction_consistency(values: list[float]) -> float | None:
        clean = [float(value) for value in values if value is not None and pd.notna(value)]
        if not clean:
            return None
        return float(sum(1 for value in clean if value > 0.0) / len(clean))

    @staticmethod
    def _dedupe_warnings(warnings: list[dict[str, str]]) -> list[dict[str, str]]:
        return dedupe_by(warnings, ("code", "reason"))

    @staticmethod
    def _normalize_symbols(symbols: list[str]) -> list[str]:
        return normalize_symbols(symbols)

    def _write_report(self, result: WalkForwardResult) -> Path:
        strategy = str(result.strategy or "walk_forward")
        json_path = write_json_report(
            generate_report_path(self.report_dir, f"walk_forward_{strategy}", unique=True),
            result.to_report(),
        )
        # Also write a human-readable summary markdown
        self._write_summary_markdown(result, json_path)
        return json_path

    @staticmethod
    def _write_summary_markdown(result: WalkForwardResult, json_path: Path) -> None:
        md_path = json_path.with_suffix(".md")
        params = result.parameters or {}
        purge_days = params.get("purge_days", 0)
        embargo_days = params.get("embargo_days", 0)
        folds = result.folds

        lines = [
            f"# Walk-Forward Report: {params.get('factor', 'unknown')}",
            "",
            f"- **Strategy**: {result.strategy or 'unknown'}",
            f"- **Period**: {params.get('start', '?')} → {params.get('end', '?')}",
            f"- **Train/Test**: {params.get('train_years', '?')}y / {params.get('test_years', '?')}y",
            f"- **Folds**: {len(folds)}",
            "",
            "## Purge / Embargo Validation",
            "",
            f"| Parameter | Value |",
            f"|-----------|-------|",
            f"| purge_days | {purge_days} |",
            f"| embargo_days | {embargo_days} |",
            "",
            "| Fold | Train | Train End | Test Start | Test End | Removed by Purge | Embargo Gap | Eff. Train Rows | Eff. Test Rows | Return | Sharpe |",
            "|------|-------|-----------|------------|----------|-----------------|-------------|----------------|---------------|--------|--------|",
        ]

        for f in folds:
            train_label = f"{f.train_start} → {f.train_end}"
            test_label = f"{f.test_start} → {f.test_end}"
            ret_str = f"{f.test_return*100:.1f}%" if f.test_return is not None else "N/A"
            sh_str = f"{f.test_sharpe:.2f}" if f.test_sharpe is not None else "N/A"
            lines.append(
                f"| {f.fold} | {train_label} | {f.train_end} | {f.test_start} | {f.test_end} | "
                f"{f.removed_by_purge} | {f.removed_by_embargo} | "
                f"{f.effective_train_rows} | {f.effective_test_rows} | "
                f"{ret_str} | {sh_str} |"
            )

        lines.append("")
        lines.append("## No-Lookahead Certification")
        lines.append("")
        all_clean = all(f.no_lookahead for f in folds)
        lines.append(f"- {'✅' if all_clean else '⚠️'} All folds certified no-lookahead: {'PASS' if all_clean else 'WARNINGS'}")
        if purge_days > 0:
            lines.append(f"- Purge window: {purge_days} calendar days removed from training")
        if embargo_days > 0:
            lines.append(f"- Embargo gap: {embargo_days} calendar days between train and test")

        if result.recommendations:
            lines.append("")
            lines.append("## Recommendations")
            for rec in result.recommendations:
                lines.append(f"- {rec}")

        lines.append("")
        lines.append(f"*Report: [{json_path.name}]({json_path.name})*")

        md_path.write_text("\n".join(lines), encoding="utf-8")
