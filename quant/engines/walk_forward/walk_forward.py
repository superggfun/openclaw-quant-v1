"""Walk-forward validation for alpha and factor long-short strategies."""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from quant.engines.backtest.backtest_engine import PortfolioBacktestEngine
from quant.config import DEFAULT_SYMBOLS
from quant.engines.factor_backtest.factor_backtest import FactorBacktest
from quant.factors.price.factor_registry import FactorRegistry
from quant.data.fundamental.fundamental_store import FundamentalStore
from quant.reports.report_io import generate_report_path, write_json_report
from quant.storage.sqlite_store import SQLitePriceStore
from quant.engines.walk_forward.rolling_validation import RollingValidation

DEFAULT_STABILITY_FACTORS = [
    "momentum_20d",
    "momentum_60d",
    "quality_score",
    "growth_score",
    "low_volatility_score",
    "value_score",
    "reversal_5d",
    "reversal_20d",
    "risk_adjusted_momentum",
    "fundamental_value_score",
    "fundamental_quality_score",
    "fundamental_growth_score",
    "fundamental_health_score",
    "fundamental_composite_score",
]


@dataclass(frozen=True)
class WalkForwardFold:
    fold: int
    fold_id: str
    train_start: str
    train_end: str
    test_start: str
    test_end: str
    train_return: float | None
    test_return: float | None
    train_sharpe: float | None
    test_sharpe: float | None
    train_max_drawdown: float | None
    test_max_drawdown: float | None
    ic: float | None
    rank_ic: float | None
    icir: float | None
    turnover: float | None
    cost: float | None
    train_report: str | None
    test_report: str | None
    no_lookahead: bool
    fold_warnings: list[dict[str, str]]


@dataclass(frozen=True)
class WalkForwardResult:
    metadata: dict[str, Any]
    strategy: str
    parameters: dict[str, Any]
    folds: list[WalkForwardFold]
    summary: dict[str, Any]
    rolling_validation: dict[str, Any]
    stability_analysis: dict[str, Any]
    warnings: list[dict[str, str]]
    recommendations: list[str]
    report_path: str

    def to_report(self) -> dict[str, Any]:
        return {
            "metadata": self.metadata,
            "strategy": self.strategy,
            "parameters": self.parameters,
            "folds": [asdict(fold) for fold in self.folds],
            "summary": self.summary,
            "rolling_validation": self.rolling_validation,
            "stability_analysis": self.stability_analysis,
            "warnings": self.warnings,
            "recommendations": self.recommendations,
        }


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
    ) -> WalkForwardResult:
        strategy = strategy.strip().lower()
        if strategy not in {"alpha", "factor_long_short"}:
            raise ValueError("strategy must be one of: alpha, factor_long_short")
        if train_years <= 0 or test_years <= 0:
            raise ValueError("train_years and test_years must be positive")
        symbols = self._normalize_symbols(universe or list(DEFAULT_SYMBOLS))
        start_date, end_date = self._date_range(symbols, start, end)
        fold_windows = self.generate_windows(start_date, end_date, train_years, test_years)
        if max_folds is not None and max_folds > 0 and len(fold_windows) > max_folds:
            fold_windows = fold_windows[-max_folds:]
        if not fold_windows:
            raise ValueError("not enough history to generate walk-forward folds")

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
                "factor": factor if strategy == "factor_long_short" else None,
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
    ) -> list[dict[str, str]]:
        start_ts = pd.to_datetime(start)
        end_ts = pd.to_datetime(end)
        train_days = max(1, int(round(train_years * 365.25)))
        test_days = max(1, int(round(test_years * 365.25)))
        windows = []
        train_start = start_ts
        while True:
            train_end = train_start + pd.Timedelta(days=train_days - 1)
            test_start = train_end + pd.Timedelta(days=1)
            test_end = test_start + pd.Timedelta(days=test_days - 1)
            if test_end > end_ts:
                break
            windows.append(
                {
                    "train_start": train_start.strftime("%Y-%m-%d"),
                    "train_end": train_end.strftime("%Y-%m-%d"),
                    "test_start": test_start.strftime("%Y-%m-%d"),
                    "test_end": test_end.strftime("%Y-%m-%d"),
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
    ) -> dict[str, Any]:
        windows = fold_windows or self.generate_windows(start, end, 3.0, 1.0)
        if max_folds is not None and max_folds > 0 and len(windows) > max_folds:
            windows = windows[-max_folds:]
        ranking = {}
        for factor in factors:
            if factor not in self.factor_registry.factor_names():
                continue
            ic_values = []
            rank_ic_values = []
            for window in windows:
                ic, rank_ic = self._lightweight_factor_ic(
                    factor=factor,
                    symbols=symbols,
                    start=window["test_start"],
                    end=window["test_end"],
                    forward_days=20,
                )
                if ic is not None:
                    ic_values.append(ic)
                if rank_ic is not None:
                    rank_ic_values.append(rank_ic)
            score = self._stability_score(ic_values, rank_ic_values)
            ranking[factor] = {
                "classification": self._stability_label(score),
                "score": score,
                "average_ic": self._mean(ic_values),
                "average_rank_ic": self._mean(rank_ic_values),
                "fold_count": len(ic_values),
            }
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
            "methodology": "classification uses average absolute IC adjusted for cross-fold variability",
        }

    def _lightweight_factor_ic(
        self,
        factor: str,
        symbols: list[str],
        start: str,
        end: str,
        forward_days: int,
    ) -> tuple[float | None, float | None]:
        rows = []
        for symbol in symbols:
            history = self.price_store.get_price_history(symbol)
            if history.empty:
                continue
            history = history.sort_values("date").reset_index(drop=True)
            history["close"] = pd.to_numeric(history["close"], errors="coerce")
            history = history.dropna(subset=["close"]).reset_index(drop=True)
            for index in range(len(history)):
                signal_date = str(history.iloc[index]["date"])
                if signal_date < start or signal_date > end:
                    continue
                future_index = index + forward_days
                if future_index >= len(history):
                    continue
                factor_value = self.factor_registry.factor_value(
                    history.iloc[: index + 1]["close"],
                    factor,
                    symbol=symbol,
                    as_of_date=signal_date,
                )
                if factor_value is None or pd.isna(factor_value):
                    continue
                signal_close = float(history.iloc[index]["close"])
                future_close = float(history.iloc[future_index]["close"])
                rows.append(
                    {
                        "signal_date": signal_date,
                        "symbol": symbol,
                        "factor_value": float(factor_value),
                        "future_return": (future_close / signal_close) - 1.0,
                    }
                )
        if not rows:
            return None, None
        frame = pd.DataFrame(rows)
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
        return self._mean(ic_values), self._mean(rank_ic_values)

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
            return self._run_alpha_fold(index, window, symbols, initial_cash, rebalance_frequency, alpha_config, pipeline_config)
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
    ) -> WalkForwardFold:
        config = dict(alpha_config or {})
        config["universe"] = symbols
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
            holding_period=20,
            universe=symbols,
            pipeline_config=pipeline_config,
        )
        test = backtest.run(
            factor=factor,
            start=window["test_start"],
            end=window["test_end"],
            holding_period=20,
            universe=symbols,
            pipeline_config=pipeline_config,
        )
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
    def _stability_score(ic_values: list[float], rank_ic_values: list[float]) -> float | None:
        values = [abs(value) for value in ic_values + rank_ic_values if value is not None]
        if not values:
            return None
        mean = float(pd.Series(values, dtype="float64").mean())
        penalty = float(pd.Series(values, dtype="float64").std()) if len(values) > 1 else 0.0
        return mean - penalty

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
    def _dedupe_warnings(warnings: list[dict[str, str]]) -> list[dict[str, str]]:
        output = []
        seen = set()
        for warning in warnings:
            key = (warning["code"], warning["reason"])
            if key not in seen:
                output.append(warning)
                seen.add(key)
        return output

    @staticmethod
    def _normalize_symbols(symbols: list[str]) -> list[str]:
        output = []
        seen = set()
        for symbol in symbols:
            ticker = str(symbol).upper().strip()
            if ticker and ticker not in seen:
                output.append(ticker)
                seen.add(ticker)
        return output

    def _write_report(self, result: WalkForwardResult) -> Path:
        strategy = str((result.parameters or {}).get("strategy") or "walk_forward")
        return write_json_report(
            generate_report_path(self.report_dir, f"walk_forward_{strategy}", unique=True),
            result.to_report(),
        )
