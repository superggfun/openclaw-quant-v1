"""Build reusable no-lookahead factor observation matrices."""

from __future__ import annotations

import time

import pandas as pd

from quant.factor_acceleration.bulk_price_loader import BulkPriceLoader
from quant.factor_acceleration.observation_matrix import ObservationMatrixResult, ObservationMatrixRow
from quant.factors.price.factor_registry import FactorRegistry
from quant.storage.sqlite_store import SQLitePriceStore


class FactorMatrixBuilder:
    """Build factor values once, then attach one or more future-return horizons."""

    def __init__(self, price_store: SQLitePriceStore, factor_registry: FactorRegistry) -> None:
        self.price_store = price_store
        self.factor_registry = factor_registry

    def build(
        self,
        factor: str,
        symbols: list[str],
        start: str | None,
        end: str | None,
        forward_days: int,
    ) -> ObservationMatrixResult:
        return self.build_many_horizons(factor, symbols, start, end, [forward_days])[forward_days]

    def build_many_horizons(
        self,
        factor: str,
        symbols: list[str],
        start: str | None,
        end: str | None,
        horizons: list[int],
    ) -> dict[int, ObservationMatrixResult]:
        normalized_horizons = sorted({int(horizon) for horizon in horizons if int(horizon) > 0})
        if not normalized_horizons:
            raise ValueError("at least one positive horizon is required")
        started = time.monotonic()
        histories = BulkPriceLoader(self.price_store).load(symbols)
        rows_by_horizon: dict[int, list[ObservationMatrixRow]] = {horizon: [] for horizon in normalized_horizons}
        excluded: dict[int, list[str]] = {horizon: [] for horizon in normalized_horizons}
        exclusion_reasons: dict[int, dict[str, str]] = {horizon: {} for horizon in normalized_horizons}
        warnings: dict[int, list[str]] = {horizon: [] for horizon in normalized_horizons}

        for symbol in symbols:
            history = histories.histories.get(symbol)
            if history is None or history.empty:
                self._exclude_all(symbol, "no price data", normalized_horizons, excluded, exclusion_reasons, warnings)
                continue

            history = self._normalize_history(history)
            if history.empty:
                self._exclude_all(symbol, "no valid close prices", normalized_horizons, excluded, exclusion_reasons, warnings)
                continue

            factor_values = self._factor_values(factor, symbol, history, start, end)
            for horizon in normalized_horizons:
                symbol_rows = self._rows_for_horizon(factor, symbol, history, factor_values, horizon)
                if not symbol_rows:
                    excluded[horizon].append(symbol)
                    exclusion_reasons[horizon][symbol] = "no valid factor and future-return pairs"
                    warnings[horizon].append(f"excluded {symbol}: no valid factor and future-return pairs")
                    continue
                rows_by_horizon[horizon].extend(symbol_rows)

        build_seconds = time.monotonic() - started
        output = {}
        for horizon in normalized_horizons:
            rows = sorted(rows_by_horizon[horizon], key=lambda row: (row.signal_date, row.symbol, row.forward_days))
            output[horizon] = ObservationMatrixResult(
                factor_name=factor,
                universe=list(symbols),
                start=start,
                end=end,
                forward_days=horizon,
                rows=rows,
                excluded_symbols=excluded[horizon],
                exclusion_reasons=exclusion_reasons[horizon],
                warnings=warnings[horizon],
                bulk_read_seconds=histories.read_seconds,
                matrix_build_seconds=build_seconds,
            )
        return output

    @staticmethod
    def _normalize_history(history: pd.DataFrame) -> pd.DataFrame:
        normalized = history.sort_values("date").reset_index(drop=True).copy()
        normalized["close"] = pd.to_numeric(normalized["close"], errors="coerce")
        return normalized.dropna(subset=["close"]).reset_index(drop=True)

    def _factor_values(
        self,
        factor: str,
        symbol: str,
        history: pd.DataFrame,
        start: str | None,
        end: str | None,
    ) -> dict[int, float]:
        price_series = self._price_factor_series(factor, history)
        if price_series is not None:
            return self._valid_series_values(price_series, history, start, end)

        values: dict[int, float] = {}
        for index in range(len(history)):
            signal_date = str(history.iloc[index]["date"])
            if start and signal_date < start:
                continue
            if end and signal_date > end:
                continue
            value = self.factor_registry.factor_value(
                history.iloc[: index + 1]["close"],
                factor,
                symbol=symbol,
                as_of_date=signal_date,
            )
            if value is None or pd.isna(value):
                continue
            values[index] = float(value)
        return values

    @staticmethod
    def _valid_series_values(
        values: pd.Series,
        history: pd.DataFrame,
        start: str | None,
        end: str | None,
    ) -> dict[int, float]:
        output: dict[int, float] = {}
        for index, value in values.items():
            signal_date = str(history.iloc[int(index)]["date"])
            if start and signal_date < start:
                continue
            if end and signal_date > end:
                continue
            if value is None or pd.isna(value):
                continue
            output[int(index)] = float(value)
        return output

    @staticmethod
    def _price_factor_series(factor: str, history: pd.DataFrame) -> pd.Series | None:
        closes = pd.to_numeric(history["close"], errors="coerce")
        returns = closes.pct_change()

        if factor == "momentum_20d":
            return (closes / closes.shift(20)) - 1.0
        if factor == "momentum_60d":
            return (closes / closes.shift(60)) - 1.0
        if factor == "volatility_20d":
            volatility = FactorMatrixBuilder._rolling_std_exact(returns, 20)
            return volatility.where(volatility > 0)
        if factor == "risk_adjusted_momentum":
            momentum = (closes / closes.shift(60)) - 1.0
            volatility = FactorMatrixBuilder._rolling_std_exact(returns, 20)
            return (momentum / volatility).where(volatility > 0)
        if factor == "reversal_5d":
            return -((closes / closes.shift(5)) - 1.0)
        if factor == "reversal_20d":
            return -((closes / closes.shift(20)) - 1.0)
        if factor == "low_volatility_score":
            volatility = FactorMatrixBuilder._rolling_std_exact(returns, 20)
            return (-volatility).where(volatility > 0)
        if factor == "growth_score":
            momentum_20d = (closes / closes.shift(20)) - 1.0
            momentum_60d = (closes / closes.shift(60)) - 1.0
            consistency = (closes.diff() > 0).rolling(20).mean()
            return 0.35 * momentum_20d + 0.45 * momentum_60d + 0.20 * consistency
        if factor == "value_score":
            long_return = (closes / closes.shift(120)) - 1.0
            volatility = FactorMatrixBuilder._rolling_std_exact(returns, 60)
            return (-long_return / volatility).where(volatility > 0)
        if factor == "quality_score":
            return closes.rolling(61).apply(FactorMatrixBuilder._quality_window_score, raw=True)
        return None

    @staticmethod
    def _rolling_std_exact(values: pd.Series, window: int) -> pd.Series:
        return values.rolling(window).apply(
            lambda rows: float(pd.Series(rows, dtype="float64").std()),
            raw=True,
        )

    @staticmethod
    def _quality_window_score(values) -> float:
        series = pd.Series(values, dtype="float64")
        returns = series.pct_change().dropna()
        if len(returns) < 60:
            return float("nan")
        volatility = float(returns.std())
        if volatility <= 0 or pd.isna(volatility):
            return float("nan")
        positive_rate = float((returns > 0).mean())
        cumulative = (1.0 + returns).cumprod()
        max_drawdown = float((cumulative / cumulative.cummax() - 1.0).min())
        mean_return = float(returns.mean())
        return (mean_return / volatility) + positive_rate + max_drawdown

    @staticmethod
    def _rows_for_horizon(
        factor: str,
        symbol: str,
        history: pd.DataFrame,
        factor_values: dict[int, float],
        horizon: int,
    ) -> list[ObservationMatrixRow]:
        rows = []
        for index, factor_value in factor_values.items():
            future_index = index + horizon
            if future_index >= len(history):
                continue
            signal_close = float(history.iloc[index]["close"])
            future_close = float(history.iloc[future_index]["close"])
            rows.append(
                ObservationMatrixRow(
                    factor_name=factor,
                    symbol=symbol,
                    signal_date=str(history.iloc[index]["date"]),
                    future_date=str(history.iloc[future_index]["date"]),
                    factor_value=factor_value,
                    future_return=(future_close / signal_close) - 1.0,
                    forward_days=horizon,
                    valid=True,
                    exclusion_reason=None,
                )
            )
        return rows

    @staticmethod
    def _exclude_all(
        symbol: str,
        reason: str,
        horizons: list[int],
        excluded: dict[int, list[str]],
        exclusion_reasons: dict[int, dict[str, str]],
        warnings: dict[int, list[str]],
    ) -> None:
        for horizon in horizons:
            excluded[horizon].append(symbol)
            exclusion_reasons[horizon][symbol] = reason
            warnings[horizon].append(f"excluded {symbol}: {reason}")
