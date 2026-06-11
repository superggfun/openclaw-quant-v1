"""No-lookahead long-short factor backtest."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

import pandas as pd

from quant.config import DEFAULT_SYMBOLS
from quant.factor_eval.factor_evaluation import SUPPORTED_FACTORS, FactorEvaluation
from quant.factor_pipeline.factor_pipeline import FactorPipeline
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
        report_dir: str | Path = "reports",
    ) -> None:
        self.price_store = price_store
        self.report_dir = Path(report_dir)

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
    ) -> FactorBacktestResult:
        factor = factor.strip().lower()
        long_quantile = long_quantile or quantiles
        self._validate(factor, start, end, holding_period, quantiles, long_quantile, short_quantile)
        symbols = self._normalize_symbols(universe or list(DEFAULT_SYMBOLS))
        normalized_pipeline_config = (
            FactorPipeline.normalize_config(pipeline_config)
            if pipeline_config is not None
            else None
        )

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

        observations = self._assign_quantiles(observations, quantiles)
        periods = self._periods(observations, quantiles, long_quantile, short_quantile)
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
        )
        report_path = self._write_report(result)
        return FactorBacktestResult(
            factor=result.factor,
            start_date=result.start_date,
            end_date=result.end_date,
            holding_period=result.holding_period,
            quantiles=result.quantiles,
            long_quantile=result.long_quantile,
            short_quantile=result.short_quantile,
            observations=result.observations,
            rebalance_dates=result.rebalance_dates,
            quantile_returns=result.quantile_returns,
            top_quantile_return=result.top_quantile_return,
            bottom_quantile_return=result.bottom_quantile_return,
            long_symbols_by_date=result.long_symbols_by_date,
            short_symbols_by_date=result.short_symbols_by_date,
            long_leg_return=result.long_leg_return,
            short_leg_return=result.short_leg_return,
            long_short_return=result.long_short_return,
            annual_return=result.annual_return,
            long_short_annual_return=result.long_short_annual_return,
            volatility=result.volatility,
            long_short_volatility=result.long_short_volatility,
            sharpe=result.sharpe,
            long_short_sharpe=result.long_short_sharpe,
            max_drawdown=result.max_drawdown,
            hit_rate=result.hit_rate,
            turnover=result.turnover,
            gross_exposure=result.gross_exposure,
            net_exposure=result.net_exposure,
            ic_mean=result.ic_mean,
            rank_ic_mean=result.rank_ic_mean,
            icir=result.icir,
            ic_count=result.ic_count,
            excluded_symbols=result.excluded_symbols,
            exclusion_reasons=result.exclusion_reasons,
            no_lookahead=result.no_lookahead,
            signal_execution_lag=result.signal_execution_lag,
            pipeline_enabled=result.pipeline_enabled,
            pipeline_config_path=result.pipeline_config_path,
            pipeline_config=result.pipeline_config,
            periods=result.periods,
            warnings=result.warnings,
            report_path=str(report_path),
        )

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

        for symbol in symbols:
            history = self.price_store.get_price_history(symbol)
            if history.empty:
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

    def _symbol_observations(
        self,
        factor: str,
        symbol: str,
        history: pd.DataFrame,
        start: str | None,
        end: str | None,
        holding_period: int,
    ) -> list[FactorBacktestObservation]:
        observations = []
        for index in range(len(history)):
            signal_date = str(history.iloc[index]["date"])
            if start and signal_date < start:
                continue
            if end and signal_date > end:
                continue
            future_index = index + holding_period
            if future_index >= len(history):
                continue
            historical = history.iloc[: index + 1]
            factor_value = FactorEvaluation._factor_value(historical["close"], factor)
            if factor_value is None:
                continue
            signal_close = float(history.iloc[index]["close"])
            future_close = float(history.iloc[future_index]["close"])
            observations.append(
                FactorBacktestObservation(
                    signal_date=signal_date,
                    future_date=str(history.iloc[future_index]["date"]),
                    symbol=symbol,
                    factor_value=float(factor_value),
                    future_return=(future_close / signal_close) - 1.0,
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
        if pipeline_config is None or not observations:
            return observations, []
        frame = pd.DataFrame([asdict(observation) for observation in observations])
        pipeline = FactorPipeline(pipeline_config, report_dir=self.report_dir)
        processed: list[FactorBacktestObservation] = []
        warnings = []
        for signal_date, group in frame.groupby("signal_date"):
            pipeline_result = pipeline.run(
                {str(row.symbol): float(row.factor_value) for row in group.itertuples(index=False)},
                factor=factor,
                as_of_date=str(signal_date),
                write_report=False,
            )
            warnings.extend(pipeline_result.warnings)
            for row in group.itertuples(index=False):
                cleaned_value = pipeline_result.cleaned_factor_values.get(str(row.symbol))
                if cleaned_value is None:
                    continue
                processed.append(
                    FactorBacktestObservation(
                        signal_date=str(row.signal_date),
                        future_date=str(row.future_date),
                        symbol=str(row.symbol),
                        factor_value=float(cleaned_value),
                        future_return=float(row.future_return),
                        quantile=None,
                    )
                )
        processed.sort(key=lambda row: (row.signal_date, row.symbol))
        return processed, sorted(set(warnings))

    @staticmethod
    def _assign_quantiles(
        observations: list[FactorBacktestObservation],
        quantiles: int,
    ) -> list[FactorBacktestObservation]:
        assigned = []
        frame = pd.DataFrame([asdict(observation) for observation in observations])
        for _, group in frame.groupby("signal_date"):
            group = group.sort_values(["factor_value", "symbol"], ascending=[True, True]).reset_index(drop=True)
            count = len(group)
            if count == 1:
                quantile_values = [quantiles]
            else:
                quantile_values = [
                    int(round(index * (quantiles - 1) / (count - 1))) + 1
                    for index in range(count)
                ]
            for row, quantile in zip(group.itertuples(index=False), quantile_values, strict=True):
                assigned.append(
                    FactorBacktestObservation(
                        signal_date=str(row.signal_date),
                        future_date=str(row.future_date),
                        symbol=str(row.symbol),
                        factor_value=float(row.factor_value),
                        future_return=float(row.future_return),
                        quantile=int(quantile),
                    )
                )
        assigned.sort(key=lambda row: (row.signal_date, row.symbol))
        return assigned

    def _periods(
        self,
        observations: list[FactorBacktestObservation],
        quantiles: int,
        long_quantile: int,
        short_quantile: int,
    ) -> list[FactorBacktestPeriod]:
        periods = []
        previous_weights: dict[str, float] | None = None
        frame = pd.DataFrame([asdict(observation) for observation in observations])
        for signal_date, group in frame.groupby("signal_date"):
            quantile_returns = {
                f"q{quantile}": self._mean(group.loc[group["quantile"] == quantile, "future_return"].tolist())
                for quantile in range(1, quantiles + 1)
            }
            long_group = group[group["quantile"] == long_quantile]
            short_group = group[group["quantile"] == short_quantile]
            long_return = self._mean(long_group["future_return"].tolist())
            short_return = self._mean(short_group["future_return"].tolist())
            long_short_return = (
                long_return - short_return
                if long_return is not None and short_return is not None
                else None
            )
            weights: dict[str, float] = {}
            long_weights: dict[str, float] = {}
            short_weights: dict[str, float] = {}
            if not long_group.empty:
                long_weight = 1.0 / len(long_group)
                long_weights = {symbol: long_weight for symbol in long_group["symbol"].tolist()}
                weights.update(long_weights)
            if not short_group.empty:
                short_weight = -1.0 / len(short_group)
                short_weights = {symbol: short_weight for symbol in short_group["symbol"].tolist()}
                weights.update(short_weights)
            long_weight_sum = sum(long_weights.values())
            short_weight_sum = sum(short_weights.values())
            net_exposure = sum(weights.values())
            gross_exposure = sum(abs(weight) for weight in weights.values())
            turnover = self._turnover(previous_weights, weights) if previous_weights is not None else None
            previous_weights = weights
            periods.append(
                FactorBacktestPeriod(
                    signal_date=str(signal_date),
                    future_date=str(group["future_date"].max()),
                    long_symbols=sorted(long_group["symbol"].tolist()),
                    short_symbols=sorted(short_group["symbol"].tolist()),
                    long_weights=dict(sorted(long_weights.items())),
                    short_weights=dict(sorted(short_weights.items())),
                    long_weight_sum=long_weight_sum,
                    short_weight_sum=short_weight_sum,
                    net_exposure=net_exposure,
                    gross_exposure=gross_exposure,
                    quantile_returns=quantile_returns,
                    long_return=long_return,
                    short_return=short_return,
                    long_short_return=long_short_return,
                    turnover=turnover,
                )
            )
        return periods

    @staticmethod
    def _correlations(observations: list[FactorBacktestObservation]) -> tuple[list[float], list[float]]:
        frame = pd.DataFrame([asdict(observation) for observation in observations])
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
        return ic_values, rank_ic_values

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
        if not values:
            return None
        total = 1.0
        for value in values:
            total *= 1.0 + value
        return total - 1.0

    @staticmethod
    def _annual_return(values: list[float]) -> float | None:
        compounded = FactorBacktest._compound_return(values)
        if compounded is None or not values:
            return None
        return (1.0 + compounded) ** (252.0 / len(values)) - 1.0

    @staticmethod
    def _annual_volatility(values: list[float]) -> float | None:
        if len(values) < 2:
            return None
        return float(pd.Series(values, dtype="float64").std() * (252.0 ** 0.5))

    @staticmethod
    def _sharpe(values: list[float]) -> float | None:
        if len(values) < 2:
            return None
        series = pd.Series(values, dtype="float64")
        std = float(series.std())
        if std <= 0 or pd.isna(std):
            return None
        return float((series.mean() / std) * (252.0 ** 0.5))

    @staticmethod
    def _max_drawdown(values: list[float]) -> float | None:
        if not values:
            return None
        equity = pd.Series([(1.0 + pd.Series(values[: index + 1], dtype="float64")).prod() for index in range(len(values))])
        drawdowns = equity / equity.cummax() - 1.0
        return float(drawdowns.min())

    @staticmethod
    def _hit_rate(values: list[float]) -> float | None:
        if not values:
            return None
        return sum(1 for value in values if value > 0) / len(values)

    @staticmethod
    def _mean(values: list[float | None]) -> float | None:
        clean = [value for value in values if value is not None and pd.notna(value)]
        if not clean:
            return None
        return float(pd.Series(clean, dtype="float64").mean())

    @staticmethod
    def _std(values: list[float]) -> float | None:
        if len(values) < 2:
            return None
        return float(pd.Series(values, dtype="float64").std())

    @staticmethod
    def _exclude(
        symbol: str,
        reason: str,
        excluded_symbols: list[str],
        exclusion_reasons: dict[str, str],
        warnings: list[str],
    ) -> None:
        excluded_symbols.append(symbol)
        exclusion_reasons[symbol] = reason
        warnings.append(f"excluded {symbol}: {reason}")

    @staticmethod
    def _normalize_symbols(symbols: list[str]) -> list[str]:
        normalized = []
        seen = set()
        for symbol in symbols:
            ticker = str(symbol).upper().strip()
            if ticker and ticker not in seen:
                normalized.append(ticker)
                seen.add(ticker)
        return normalized

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
        self.report_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = self.report_dir / f"factor_backtest_{timestamp}.json"
        path.write_text(json.dumps(result.to_report(), indent=2), encoding="utf-8")
        return path
