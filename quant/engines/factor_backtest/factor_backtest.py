"""No-lookahead long-short factor backtest."""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from pathlib import Path

import pandas as pd

from quant.config import DEFAULT_SYMBOLS
from quant.factor_acceleration import FactorMatrixBuilder
from quant.engines.factor_common import (
    annual_return,
    annual_volatility,
    apply_factor_pipeline,
    compound_return,
    cross_section_correlations,
    exclude_symbol,
    factor_coverage,
    factor_coverage_warnings,
    hit_rate,
    max_drawdown,
    mean,
    normalize_symbols,
    sharpe,
    std,
    write_factor_report,
)
from quant.engines.factor_eval.factor_evaluation import SUPPORTED_FACTORS, FactorEvaluation
from quant.engines.factor_pipeline.factor_pipeline import FactorPipeline
from quant.factors.price.factor_registry import FactorRegistry
from quant.data.fundamental.fundamental_store import FundamentalStore
from quant.storage.sqlite_store import SQLitePriceStore


@dataclass(frozen=True)
class FactorBacktestObservation:
    signal_date: str
    future_date: str
    symbol: str
    factor_value: float
    future_return: float
    quantile: int | None


@dataclass(frozen=True)
class FactorBacktestPeriod:
    signal_date: str
    future_date: str
    long_symbols: list[str]
    short_symbols: list[str]
    long_weights: dict[str, float]
    short_weights: dict[str, float]
    long_weight_sum: float
    short_weight_sum: float
    net_exposure: float
    gross_exposure: float
    quantile_returns: dict[str, float | None]
    long_return: float | None
    short_return: float | None
    long_short_return: float | None
    turnover: float | None


@dataclass(frozen=True)
class FactorBacktestResult:
    factor: str
    start_date: str | None
    end_date: str | None
    holding_period: int
    quantiles: int
    long_quantile: int
    short_quantile: int
    observations: int
    rebalance_dates: list[str]
    quantile_returns: dict[str, float | None]
    top_quantile_return: float | None
    bottom_quantile_return: float | None
    long_symbols_by_date: dict[str, list[str]]
    short_symbols_by_date: dict[str, list[str]]
    long_leg_return: float | None
    short_leg_return: float | None
    long_short_return: float | None
    annual_return: float | None
    long_short_annual_return: float | None
    volatility: float | None
    long_short_volatility: float | None
    sharpe: float | None
    long_short_sharpe: float | None
    max_drawdown: float | None
    hit_rate: float | None
    turnover: float | None
    gross_exposure: float | None
    net_exposure: float | None
    ic_mean: float | None
    rank_ic_mean: float | None
    icir: float | None
    ic_count: int
    factor_family: str
    factor_type: str
    factor_category: str
    factor_description: str
    factor_inputs: list[str]
    factor_higher_is_better: bool
    factor_no_lookahead: bool
    factor_coverage: dict | None
    excluded_symbols: list[str]
    exclusion_reasons: dict[str, str]
    no_lookahead: bool
    signal_execution_lag: str
    pipeline_enabled: bool
    pipeline_config_path: str | None
    pipeline_config: dict | None
    periods: list[FactorBacktestPeriod]
    warnings: list[str]
    report_path: str
    performance_metadata: dict | None = None

    def to_report(self) -> dict:
        return {
            "factor": self.factor,
            "start_date": self.start_date,
            "end_date": self.end_date,
            "holding_period": self.holding_period,
            "quantiles": self.quantiles,
            "long_quantile": self.long_quantile,
            "short_quantile": self.short_quantile,
            "observations": self.observations,
            "rebalance_dates": self.rebalance_dates,
            "quantile_returns": self.quantile_returns,
            "top_quantile_return": self.top_quantile_return,
            "bottom_quantile_return": self.bottom_quantile_return,
            "long_symbols_by_date": self.long_symbols_by_date,
            "short_symbols_by_date": self.short_symbols_by_date,
            "long_leg_return": self.long_leg_return,
            "short_leg_return": self.short_leg_return,
            "long_short_return": self.long_short_return,
            "annual_return": self.annual_return,
            "long_short_annual_return": self.long_short_annual_return,
            "volatility": self.volatility,
            "long_short_volatility": self.long_short_volatility,
            "sharpe": self.sharpe,
            "long_short_sharpe": self.long_short_sharpe,
            "max_drawdown": self.max_drawdown,
            "hit_rate": self.hit_rate,
            "turnover": self.turnover,
            "gross_exposure": self.gross_exposure,
            "net_exposure": self.net_exposure,
            "ic_mean": self.ic_mean,
            "rank_ic_mean": self.rank_ic_mean,
            "icir": self.icir,
            "ic_count": self.ic_count,
            "factor_family": self.factor_family,
            "factor_type": self.factor_type,
            "factor_category": self.factor_category,
            "factor_description": self.factor_description,
            "factor_inputs": self.factor_inputs,
            "factor_higher_is_better": self.factor_higher_is_better,
            "factor_no_lookahead": self.factor_no_lookahead,
            "factor_coverage": self.factor_coverage,
            "excluded_symbols": self.excluded_symbols,
            "exclusion_reasons": self.exclusion_reasons,
            "no_lookahead": self.no_lookahead,
            "signal_execution_lag": self.signal_execution_lag,
            "pipeline_enabled": self.pipeline_enabled,
            "pipeline_config_path": self.pipeline_config_path,
            "pipeline_config": self.pipeline_config,
            "periods": [asdict(period) for period in self.periods],
            "warnings": self.warnings,
        }


class FactorBacktest:
    """Backtest an equal-weight long-short factor portfolio from stored prices."""

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
        factor: str,
        start: str | None = None,
        end: str | None = None,
        holding_period: int = 20,
        quantiles: int = 5,
        long_quantile: int | None = None,
        short_quantile: int = 1,
        universe: list[str] | None = None,
        pipeline_config: dict | None = None,
        pipeline_config_path: str | None = None,
        bulk_matrix: bool = True,
        max_workers: int = 4,
        prefer_in_memory: bool = True,
        strict_in_memory: bool = False,
        write_report: bool = True,
    ) -> FactorBacktestResult:
        factor = factor.strip().lower()
        long_quantile = long_quantile or quantiles
        self._validate(factor, start, end, holding_period, quantiles, long_quantile, short_quantile)
        factor_metadata = self.factor_registry.metadata(factor)
        symbols = normalize_symbols(universe or list(DEFAULT_SYMBOLS))
        normalized_pipeline_config = (
            FactorPipeline.normalize_config(pipeline_config)
            if pipeline_config is not None
            else None
        )

        performance_metadata = None
        if bulk_matrix:
            observations, excluded_symbols, exclusion_reasons, warnings, performance_metadata = self._observations_bulk(
                factor=factor,
                symbols=symbols,
                start=start,
                end=end,
                holding_period=holding_period,
                max_workers=max_workers,
                prefer_in_memory=prefer_in_memory,
                strict_in_memory=strict_in_memory,
            )
        else:
            observations, excluded_symbols, exclusion_reasons, warnings = self._observations(
                factor=factor,
                symbols=symbols,
                start=start,
                end=end,
                holding_period=holding_period,
            )
        observations, pipeline_warnings = self._apply_pipeline(
            observations,
            factor=factor,
            pipeline_config=normalized_pipeline_config,
        )
        warnings.extend(pipeline_warnings)
        if not observations:
            raise ValueError("no factor backtest observations available")
        factor_coverage = self._factor_coverage(factor, symbols, observations)
        warnings.extend(self._factor_coverage_warnings(factor, factor_coverage))

        observations = self._assign_quantiles(observations, quantiles)
        periods = self._periods(observations, quantiles, long_quantile, short_quantile, max_workers=max_workers)
        complete_periods = [
            period
            for period in periods
            if period.long_short_return is not None
        ]
        incomplete_period_count = len(periods) - len(complete_periods)
        if incomplete_period_count:
            warnings.append(
                f"{incomplete_period_count} signal periods have an incomplete long-short construction; "
                "they are excluded from long-short return, turnover, and exposure summary metrics"
            )
        long_short_returns = [
            period.long_short_return
            for period in complete_periods
        ]
        long_returns = [period.long_return for period in complete_periods if period.long_return is not None]
        short_returns = [period.short_return for period in complete_periods if period.short_return is not None]
        ic_values, rank_ic_values = self._correlations(observations)
        quantile_returns = self._quantile_returns(observations, quantiles)
        ic_mean = self._mean(ic_values)
        ic_std = self._std(ic_values)
        long_short_return = self._compound_return(long_short_returns)
        annual_return = self._annual_return(long_short_returns)
        volatility = self._annual_volatility(long_short_returns)
        sharpe = self._sharpe(long_short_returns)
        if any(value <= -1.0 for value in long_short_returns):
            warnings.append(
                "long_short_return reached -100% because at least one leveraged long-short "
                "spread period return was <= -100%; inspect period returns before treating "
                "the compounded spread as an investable equity curve"
            )
        elif long_short_return is not None and long_short_return <= -0.999999:
            warnings.append(
                "long_short_return rounded to -100% after compounding many overlapping "
                "long-short spread returns"
            )
        if long_short_return is not None and sharpe is not None and long_short_return * sharpe < 0:
            warnings.append(
                "long_short_return and sharpe differ in sign because long_short_return is compounded "
                "while sharpe uses arithmetic period mean over overlapping forward-return observations"
            )

        result = FactorBacktestResult(
            factor=factor,
            start_date=start,
            end_date=end,
            holding_period=holding_period,
            quantiles=quantiles,
            long_quantile=long_quantile,
            short_quantile=short_quantile,
            observations=len(observations),
            rebalance_dates=[period.signal_date for period in periods],
            quantile_returns=quantile_returns,
            top_quantile_return=quantile_returns.get(f"q{long_quantile}"),
            bottom_quantile_return=quantile_returns.get(f"q{short_quantile}"),
            long_symbols_by_date={period.signal_date: period.long_symbols for period in periods},
            short_symbols_by_date={period.signal_date: period.short_symbols for period in periods},
            long_leg_return=self._compound_return(long_returns),
            short_leg_return=self._compound_return(short_returns),
            long_short_return=long_short_return,
            annual_return=annual_return,
            long_short_annual_return=annual_return,
            volatility=volatility,
            long_short_volatility=volatility,
            sharpe=sharpe,
            long_short_sharpe=sharpe,
            max_drawdown=self._max_drawdown(long_short_returns),
            hit_rate=self._hit_rate(long_short_returns),
            turnover=self._mean([period.turnover for period in complete_periods if period.turnover is not None]),
            gross_exposure=self._mean([period.gross_exposure for period in complete_periods]),
            net_exposure=self._mean([period.net_exposure for period in complete_periods]),
            ic_mean=ic_mean,
            rank_ic_mean=self._mean(rank_ic_values),
            icir=(ic_mean / ic_std) if ic_mean is not None and ic_std not in {None, 0.0} else None,
            ic_count=len(ic_values),
            factor_family=str(factor_metadata["factor_family"]),
            factor_type=str(factor_metadata["factor_type"]),
            factor_category=str(factor_metadata["factor_category"]),
            factor_description=str(factor_metadata["factor_description"]),
            factor_inputs=list(factor_metadata["factor_inputs"]),
            factor_higher_is_better=bool(factor_metadata["higher_is_better"]),
            factor_no_lookahead=bool(factor_metadata["no_lookahead"]),
            factor_coverage=factor_coverage,
            excluded_symbols=excluded_symbols,
            exclusion_reasons=exclusion_reasons,
            no_lookahead=True,
            signal_execution_lag=f"factor uses signal_date and earlier; future_return uses T+{holding_period} close",
            pipeline_enabled=normalized_pipeline_config is not None,
            pipeline_config_path=pipeline_config_path,
            pipeline_config=normalized_pipeline_config,
            periods=periods,
            warnings=warnings,
            report_path="",
            performance_metadata=performance_metadata,
        )
        report_path = self._write_report(result) if write_report else ""
        return replace(result, report_path=str(report_path))

    def _observations_bulk(
        self,
        factor: str,
        symbols: list[str],
        start: str | None,
        end: str | None,
        holding_period: int,
        max_workers: int = 4,
        prefer_in_memory: bool = True,
        strict_in_memory: bool = False,
    ) -> tuple[list[FactorBacktestObservation], list[str], dict[str, str], list[str], dict]:
        workers = max_workers if max_workers > 0 else 1
        matrix = FactorMatrixBuilder(
            self.price_store,
            self.factor_registry,
            prefer_in_memory=prefer_in_memory,
            strict_in_memory=strict_in_memory,
        ).build(
            factor=factor,
            symbols=symbols,
            start=start,
            end=end,
            forward_days=holding_period,
            max_workers=workers,
        )
        observations = [
            FactorBacktestObservation(
                signal_date=row.signal_date,
                future_date=str(row.future_date),
                symbol=row.symbol,
                factor_value=float(row.factor_value),
                future_return=float(row.future_return),
                quantile=None,
            )
            for row in matrix.valid_rows
            if row.factor_value is not None and row.future_return is not None and row.future_date is not None
        ]
        observations.sort(key=lambda row: (row.signal_date, row.symbol))
        return observations, matrix.excluded_symbols, matrix.exclusion_reasons, matrix.warnings, matrix.to_metadata()

    def _observations(
        self,
        factor: str,
        symbols: list[str],
        start: str | None,
        end: str | None,
        holding_period: int,
    ) -> tuple[list[FactorBacktestObservation], list[str], dict[str, str], list[str]]:
        observations: list[FactorBacktestObservation] = []
        excluded_symbols = []
        exclusion_reasons = {}
        warnings = []
        histories = self._price_histories(symbols)

        for symbol in symbols:
            history = histories.get(symbol)
            if history is None:
                history = histories.get(symbol.upper())
            if history is None or history.empty:
                self._exclude(symbol, "no price data", excluded_symbols, exclusion_reasons, warnings)
                continue
            history = history.sort_values("date").reset_index(drop=True)
            history["close"] = pd.to_numeric(history["close"], errors="coerce")
            history = history.dropna(subset=["close"]).reset_index(drop=True)
            if history.empty:
                self._exclude(symbol, "no valid close prices", excluded_symbols, exclusion_reasons, warnings)
                continue
            symbol_observations = self._symbol_observations(factor, symbol, history, start, end, holding_period)
            if not symbol_observations:
                self._exclude(symbol, "no valid factor and future-return pairs", excluded_symbols, exclusion_reasons, warnings)
                continue
            observations.extend(symbol_observations)

        observations.sort(key=lambda row: (row.signal_date, row.symbol))
        return observations, excluded_symbols, exclusion_reasons, warnings

    def _price_histories(self, symbols: list[str]) -> dict[str, pd.DataFrame]:
        if hasattr(self.price_store, "get_price_history_many"):
            return self.price_store.get_price_history_many(symbols)
        return {symbol: self.price_store.get_price_history(symbol) for symbol in symbols}

    def _symbol_observations(
        self,
        factor: str,
        symbol: str,
        history: pd.DataFrame,
        start: str | None,
        end: str | None,
        holding_period: int,
    ) -> list[FactorBacktestObservation]:
        import numpy as np

        # Pre-extract numpy arrays — avoids per-row Series construction overhead.
        dates_arr = history["date"].to_numpy()
        closes_arr = history["close"].to_numpy(dtype=float, na_value=float("nan"))
        max_index = len(history)

        observations = []
        for index in range(max_index):
            signal_date = str(dates_arr[index])
            if start and signal_date < start:
                continue
            if end and signal_date > end:
                continue
            future_index = index + holding_period
            if future_index >= max_index:
                continue

            # Factor computation still uses the growing slice (no-lookahead).
            historical = history.iloc[: index + 1]
            factor_value = FactorEvaluation._factor_value(
                historical["close"],
                factor,
                symbol=symbol,
                signal_date=signal_date,
                registry=self.factor_registry,
            )
            if factor_value is None:
                continue

            signal_close = closes_arr[index]
            future_close = closes_arr[future_index]
            if np.isnan(signal_close) or np.isnan(future_close):
                continue
            observations.append(
                FactorBacktestObservation(
                    signal_date=signal_date,
                    future_date=str(dates_arr[future_index]),
                    symbol=symbol,
                    factor_value=float(factor_value),
                    future_return=(float(future_close) / float(signal_close)) - 1.0,
                    quantile=None,
                )
            )
        return observations

    def _apply_pipeline(
        self,
        observations: list[FactorBacktestObservation],
        factor: str,
        pipeline_config: dict | None,
    ) -> tuple[list[FactorBacktestObservation], list[str]]:
        return apply_factor_pipeline(
            observations,
            factor=factor,
            pipeline_config=pipeline_config,
            report_dir=self.report_dir,
            rebuild_observation=lambda row, cleaned_value: FactorBacktestObservation(
                signal_date=str(row.signal_date),
                future_date=str(row.future_date),
                symbol=str(row.symbol),
                factor_value=cleaned_value,
                future_return=float(row.future_return),
                quantile=row.quantile,
            ),
            sort_key=lambda row: (row.signal_date, row.symbol),
        )

    @staticmethod
    def _assign_quantiles(
        observations: list[FactorBacktestObservation],
        quantiles: int,
    ) -> list[FactorBacktestObservation]:
        frame = pd.DataFrame([asdict(observation) for observation in observations])
        # Sort once across all groups — every group inherits this ordering.
        frame = frame.sort_values(["signal_date", "factor_value", "symbol"],
                                  ascending=[True, True, True]).reset_index(drop=True)
        # Per-group rank (0-based within each signal_date group) via cumcount.
        frame["_rank"] = frame.groupby("signal_date").cumcount()
        # Per-group size for denominator.
        frame["_grp_size"] = frame.groupby("signal_date")["_rank"].transform("max") + 1
        # Compute quantile: evenly spaced across [1, quantiles].
        # Single-observation groups get `quantiles`.
        frame["_rank"] = frame["_rank"].where(frame["_grp_size"] > 1, 0)
        frame["_denom"] = frame["_grp_size"] - 1
        frame["_denom"] = frame["_denom"].where(frame["_denom"] > 0, 1)
        frame["quantile"] = (
            (frame["_rank"] * (quantiles - 1) / frame["_denom"]).round().astype(int) + 1
        )
        # Build result dataclasses from the frame (still per-row, but no python-level
        # group iteration, sorting, or zip overhead).
        assigned = [
            FactorBacktestObservation(
                signal_date=str(r.signal_date),
                future_date=str(r.future_date),
                symbol=str(r.symbol),
                factor_value=float(r.factor_value),
                future_return=float(r.future_return),
                quantile=int(r.quantile),
            )
            for r in frame.itertuples(index=False)
        ]
        assigned.sort(key=lambda row: (row.signal_date, row.symbol))
        return assigned

    def _periods(
        self,
        observations: list[FactorBacktestObservation],
        quantiles: int,
        long_quantile: int,
        short_quantile: int,
        max_workers: int = 0,
    ) -> list[FactorBacktestPeriod]:
        global _periods_symbols, _periods_quantile, _periods_returns, _periods_future
        global _periods_quantiles, _periods_long_q, _periods_short_q

        frame = pd.DataFrame([asdict(observation) for observation in observations])

        date_indices = list(frame.groupby("signal_date", sort=False).indices.items())
        n_dates = len(date_indices)
        n_workers = max(1, min(int(max_workers), n_dates)) if max_workers > 1 else 1
        if n_workers > 1:
            from quant.data.research_data_store import multiprocessing_start_method

            if multiprocessing_start_method() != "fork":
                n_workers = 1

        # Store arrays in module globals so _compute_period_single/chunk can access them.
        # In the multiprocess path, children inherit via COW after fork.
        _periods_symbols = frame["symbol"].to_numpy()
        _periods_quantile = frame["quantile"].to_numpy()
        _periods_returns = frame["future_return"].to_numpy(dtype=float, na_value=float("nan"))
        _periods_future = frame["future_date"].to_numpy()
        _periods_quantiles = quantiles
        _periods_long_q = long_quantile
        _periods_short_q = short_quantile

        if n_workers <= 1:
            partials = _compute_periods_sequential(date_indices)
        else:
            from concurrent.futures import ProcessPoolExecutor, as_completed
            import math

            chunk_size = math.ceil(n_dates / n_workers)
            chunks = [date_indices[i:i + chunk_size] for i in range(0, n_dates, chunk_size)]

            worker_results: dict[int, list[dict]] = {}
            try:
                with ProcessPoolExecutor(max_workers=n_workers) as executor:
                    futures = {
                        executor.submit(_compute_periods_chunk, chunk): idx
                        for idx, chunk in enumerate(chunks)
                    }
                    for future in as_completed(futures):
                        idx = futures[future]
                        worker_results[idx] = future.result()
            finally:
                _periods_symbols = None
                _periods_quantile = None
                _periods_returns = None
                _periods_future = None

            # Merge chunk results in order
            partials = []
            for idx in sorted(worker_results):
                partials.extend(worker_results[idx])

        # Sort by signal_date
        partials.sort(key=lambda p: p["signal_date"])

        # ── Sequential pass: compute turnover and build final periods ──
        periods: list[FactorBacktestPeriod] = []
        previous_weights: dict[str, float] | None = None
        for p in partials:
            weights = {**p["long_weights"], **p["short_weights"]}
            turnover = self._turnover(previous_weights, weights) if previous_weights is not None else None
            previous_weights = weights
            periods.append(
                FactorBacktestPeriod(
                    signal_date=p["signal_date"],
                    future_date=p["future_date"],
                    long_symbols=p["long_symbols"],
                    short_symbols=p["short_symbols"],
                    long_weights=p["long_weights"],
                    short_weights=p["short_weights"],
                    long_weight_sum=p["long_weight_sum"],
                    short_weight_sum=p["short_weight_sum"],
                    net_exposure=p["net_exposure"],
                    gross_exposure=p["gross_exposure"],
                    quantile_returns=p["quantile_returns"],
                    long_return=p["long_return"],
                    short_return=p["short_return"],
                    long_short_return=p["long_short_return"],
                    turnover=turnover,
                )
            )
        return periods

    @staticmethod
    def _correlations(observations: list[FactorBacktestObservation]) -> tuple[list[float], list[float]]:
        return cross_section_correlations(observations)

    @staticmethod
    def _quantile_returns(
        observations: list[FactorBacktestObservation],
        quantiles: int,
    ) -> dict[str, float | None]:
        frame = pd.DataFrame([asdict(observation) for observation in observations])
        return {
            f"q{quantile}": FactorBacktest._mean(frame.loc[frame["quantile"] == quantile, "future_return"].tolist())
            for quantile in range(1, quantiles + 1)
        }

    @staticmethod
    def _turnover(previous_weights: dict[str, float], current_weights: dict[str, float]) -> float:
        symbols = set(previous_weights) | set(current_weights)
        return 0.5 * sum(abs(current_weights.get(symbol, 0.0) - previous_weights.get(symbol, 0.0)) for symbol in symbols)

    @staticmethod
    def _compound_return(values: list[float]) -> float | None:
        return compound_return(values)

    @staticmethod
    def _annual_return(values: list[float]) -> float | None:
        return annual_return(values)

    @staticmethod
    def _annual_volatility(values: list[float]) -> float | None:
        return annual_volatility(values)

    @staticmethod
    def _sharpe(values: list[float]) -> float | None:
        return sharpe(values)

    @staticmethod
    def _max_drawdown(values: list[float]) -> float | None:
        return max_drawdown(values)

    @staticmethod
    def _hit_rate(values: list[float]) -> float | None:
        return hit_rate(values)

    @staticmethod
    def _mean(values: list[float | None]) -> float | None:
        return mean(values)

    @staticmethod
    def _std(values: list[float]) -> float | None:
        return std(values)

    @staticmethod
    def _exclude(
        symbol: str,
        reason: str,
        excluded_symbols: list[str],
        exclusion_reasons: dict[str, str],
        warnings: list[str],
    ) -> None:
        exclude_symbol(symbol, reason, excluded_symbols, exclusion_reasons, warnings)

    def _factor_coverage(
        self,
        factor: str,
        symbols: list[str],
        observations: list[FactorBacktestObservation],
    ) -> dict | None:
        return factor_coverage(self.factor_registry, factor, symbols, observations)

    @staticmethod
    def _factor_coverage_warnings(factor: str, coverage: dict | None) -> list[str]:
        return factor_coverage_warnings(factor, coverage)

    @staticmethod
    def _normalize_symbols(symbols: list[str]) -> list[str]:
        return normalize_symbols(symbols)

    @staticmethod
    def _validate(
        factor: str,
        start: str | None,
        end: str | None,
        holding_period: int,
        quantiles: int,
        long_quantile: int,
        short_quantile: int,
    ) -> None:
        if factor not in SUPPORTED_FACTORS:
            raise ValueError(f"factor must be one of: {', '.join(sorted(SUPPORTED_FACTORS))}")
        if start and end and start > end:
            raise ValueError("start must be before or equal to end")
        if holding_period <= 0:
            raise ValueError("holding_period must be positive")
        if quantiles < 2:
            raise ValueError("quantiles must be at least 2")
        if not 1 <= long_quantile <= quantiles:
            raise ValueError("long_quantile must be between 1 and quantiles")
        if not 1 <= short_quantile <= quantiles:
            raise ValueError("short_quantile must be between 1 and quantiles")
        if long_quantile == short_quantile:
            raise ValueError("long_quantile and short_quantile must differ")

    def _write_report(self, result: FactorBacktestResult) -> Path:
        return write_factor_report(self.report_dir, "factor_backtest", result.factor, result.to_report())


# ── Module-level caches for parallel _periods (COW shared via fork) ──
_periods_symbols = None
_periods_quantile = None
_periods_returns = None
_periods_future = None
_periods_quantiles: int = 5
_periods_long_q: int = 1
_periods_short_q: int = 1


def _compute_period_single(
    signal_date: str,
    idxs,
) -> dict:
    """Compute per-date period data from module-level arrays (COW shared)."""
    import numpy as np

    idxs = np.asarray(idxs, dtype=int)
    symbols_arr = _periods_symbols
    quantile_arr = _periods_quantile
    returns_arr = _periods_returns
    future_arr = _periods_future
    quantiles = _periods_quantiles
    long_quantile = _periods_long_q
    short_quantile = _periods_short_q

    q_returns: dict[str, float | None] = {}
    for q in range(1, quantiles + 1):
        mask = quantile_arr[idxs] == q
        if mask.any():
            vals = returns_arr[idxs][mask]
            valid = vals[~np.isnan(vals)]
            q_returns[f"q{q}"] = float(valid.mean()) if len(valid) > 0 else None
        else:
            q_returns[f"q{q}"] = None

    long_mask = quantile_arr[idxs] == long_quantile
    short_mask = quantile_arr[idxs] == short_quantile

    long_vals = returns_arr[idxs][long_mask]
    long_valid = long_vals[~np.isnan(long_vals)]
    long_return = float(long_valid.mean()) if len(long_valid) > 0 else None

    short_vals = returns_arr[idxs][short_mask]
    short_valid = short_vals[~np.isnan(short_vals)]
    short_return = float(short_valid.mean()) if len(short_valid) > 0 else None

    long_short_return = (
        long_return - short_return
        if long_return is not None and short_return is not None
        else None
    )

    long_syms = sorted(symbols_arr[idxs][long_mask].tolist())
    short_syms = sorted(symbols_arr[idxs][short_mask].tolist())

    long_weight = 1.0 / len(long_syms) if long_syms else 0.0
    short_weight = -1.0 / len(short_syms) if short_syms else 0.0
    long_weights = {sym: long_weight for sym in long_syms}
    short_weights = {sym: short_weight for sym in short_syms}

    return {
        "signal_date": str(signal_date),
        "future_date": str(future_arr[idxs].max()),
        "long_symbols": long_syms,
        "short_symbols": short_syms,
        "long_weights": dict(sorted(long_weights.items())),
        "short_weights": dict(sorted(short_weights.items())),
        "long_weight_sum": sum(long_weights.values()),
        "short_weight_sum": sum(short_weights.values()),
        "net_exposure": sum(long_weights.values()) + sum(short_weights.values()),
        "gross_exposure": sum(abs(w) for w in list(long_weights.values()) + list(short_weights.values())),
        "quantile_returns": q_returns,
        "long_return": long_return,
        "short_return": short_return,
        "long_short_return": long_short_return,
    }


def _compute_periods_sequential(
    date_indices: list,
) -> list[dict]:
    """Sequential fallback for single-worker path."""
    results = []
    for signal_date, idxs in date_indices:
        results.append(_compute_period_single(signal_date, idxs))
    return results


def _compute_periods_chunk(
    date_indices: list,
) -> list[dict]:
    """Process a chunk of dates in a subprocess.

    Reads module-level _periods_* arrays inherited via COW fork.
    Only date_indices is serialized (small).
    """
    return _compute_periods_sequential(date_indices)
