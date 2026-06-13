"""No-lookahead factor evaluation framework."""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass, replace
from pathlib import Path

import numpy as np
import pandas as pd

from quant.config import DEFAULT_SYMBOLS
from quant.factor_acceleration import FactorMatrixBuilder
from quant.factor_cache import FactorCacheKey, FactorEvalCache, FactorMatrixResult, make_universe_hash
from quant.engines.factor_common import (
    apply_factor_pipeline,
    cross_section_correlations,
    factor_coverage,
    factor_coverage_warnings,
    mean,
    normalize_symbols,
    positive_rate,
    std,
    write_factor_report,
)
from quant.engines.factor_pipeline.factor_pipeline import FactorPipeline
from quant.factors.price.factor_registry import FactorRegistry
from quant.data.fundamental.fundamental_store import FundamentalStore
from quant.storage.sqlite_store import SQLitePriceStore


FACTOR_REGISTRY = FactorRegistry()
SUPPORTED_FACTORS = set(FACTOR_REGISTRY.factor_names())
DEFAULT_DECAY_DAYS = [1, 5, 10, 20, 60]


def _estimate_half_life(decay: dict) -> float | None:
    '''Estimate signal half-life from IC decay curve using exponential fit.
    Expects decay dict format: {"20d": {"ic": 0.05, "rank_ic": 0.06, ...}}'''
    horizons = []
    ic_values = []
    for label, entry in decay.items():
        # Parse horizon from label like "20d" or "60d"
        if not isinstance(label, str) or not label.endswith("d"):
            continue
        try:
            horizon = int(label[:-1])
        except (ValueError, TypeError):
            continue
        ic = entry.get("ic")  # Use standard IC (not rank IC)
        if ic is not None and abs(float(ic)) > 1e-9:
            ic_abs = abs(float(ic))
            horizons.append(float(horizon))
            ic_values.append(ic_abs)

    if len(horizons) < 3:
        return None

    try:
        h_arr = np.array(horizons)
        y_arr = np.log(np.array(ic_values))
        slope, intercept = np.polyfit(h_arr, y_arr, 1)
        lambda_est = -slope
        if lambda_est <= 1e-12:
            return None
        half_life = float(np.log(2) / lambda_est)
        return round(half_life, 1)
    except Exception:
        return None

SUPPORTED_FACTORS = set(FACTOR_REGISTRY.factor_names())
DEFAULT_DECAY_DAYS = [1, 5, 10, 20, 60]


@dataclass(frozen=True)
class FactorObservation:
    signal_date: str
    future_date: str
    symbol: str
    factor_value: float
    future_return: float
    forward_days: int


@dataclass(frozen=True)
class FactorEvaluationResult:
    factor: str
    start_date: str | None
    end_date: str | None
    forward_days: int
    universe: list[str]
    no_lookahead: bool
    ic_mean: float | None
    ic_std: float | None
    ic_positive_rate: float | None
    ic_count: int
    rank_ic_mean: float | None
    rank_ic_std: float | None
    rank_ic_positive_rate: float | None
    rank_ic_count: int
    icir: float | None
    quintiles: dict[str, float | None]
    spread_return: float | None
    decay: dict[str, dict[str, float | int | None]]
    half_life_days: float | None
    observations: list[FactorObservation]
    excluded_symbols: list[str]
    exclusion_reasons: dict[str, str]
    factor_family: str
    factor_type: str
    factor_category: str
    factor_description: str
    factor_inputs: list[str]
    factor_higher_is_better: bool
    factor_no_lookahead: bool
    factor_coverage: dict | None
    warnings: list[str]
    pipeline_config: dict | None
    report_path: str
    performance_metadata: dict | None = None

    def to_report(self) -> dict:
        report = {
            "factor": self.factor,
            "start_date": self.start_date,
            "end_date": self.end_date,
            "forward_days": self.forward_days,
            "universe": self.universe,
            "no_lookahead": self.no_lookahead,
            "ic_mean": self.ic_mean,
            "ic_std": self.ic_std,
            "ic_positive_rate": self.ic_positive_rate,
            "ic_count": self.ic_count,
            "rank_ic_mean": self.rank_ic_mean,
            "rank_ic_std": self.rank_ic_std,
            "rank_ic_positive_rate": self.rank_ic_positive_rate,
            "rank_ic_count": self.rank_ic_count,
            "icir": self.icir,
            "quintiles": self.quintiles,
            "spread_return": self.spread_return,
            "decay": self.decay,
            "observations": [asdict(observation) for observation in self.observations],
            "excluded_symbols": self.excluded_symbols,
            "exclusion_reasons": self.exclusion_reasons,
            "factor_family": self.factor_family,
            "factor_type": self.factor_type,
            "factor_category": self.factor_category,
            "factor_description": self.factor_description,
            "factor_inputs": self.factor_inputs,
            "factor_higher_is_better": self.factor_higher_is_better,
            "factor_no_lookahead": self.factor_no_lookahead,
            "factor_coverage": self.factor_coverage,
            "warnings": self.warnings,
            "pipeline_config": self.pipeline_config,
        }
        if self.performance_metadata:
            report["performance_metadata"] = self.performance_metadata
            report["cache_enabled"] = self.performance_metadata.get("cache_enabled")
            report["cache_hits"] = self.performance_metadata.get("cache_hits")
            report["cache_misses"] = self.performance_metadata.get("cache_misses")
            report["matrix_rows"] = self.performance_metadata.get("matrix_rows")
            report["matrix_build_seconds"] = self.performance_metadata.get("matrix_build_seconds")
            report["eval_seconds"] = self.performance_metadata.get("eval_seconds")
            report["speedup_estimate"] = self.performance_metadata.get("speedup_estimate")
        return report


class FactorEvaluation:
    """Evaluate factor values against future returns without future leakage."""

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

    def evaluate(
        self,
        factor: str,
        start: str | None = None,
        end: str | None = None,
        forward_days: int = 20,
        universe: list[str] | None = None,
        pipeline_config: dict | None = None,
        use_cache: bool = False,
        factor_cache: FactorEvalCache | None = None,
        bulk_matrix: bool = False,
        cache_stats: bool = False,
        write_report: bool = True,
    ) -> FactorEvaluationResult:
        eval_started = time.monotonic()
        factor = factor.strip().lower()
        self._validate(factor, start, end, forward_days)
        factor_metadata = self.factor_registry.metadata(factor)
        symbols = normalize_symbols(universe or list(DEFAULT_SYMBOLS))
        normalized_pipeline_config = (
            FactorPipeline.normalize_config(pipeline_config)
            if pipeline_config is not None
            else None
        )
        cache = factor_cache or (FactorEvalCache() if use_cache else None)
        cache_before = cache.snapshot() if cache else {}
        matrix_metadata = None
        if use_cache:
            observations, excluded_symbols, exclusion_reasons, warnings, matrix_metadata = self._observations_with_cache(
                factor=factor,
                symbols=symbols,
                start=start,
                end=end,
                forward_days=forward_days,
                factor_cache=cache,
            )
        elif bulk_matrix:
            matrix = self._build_factor_matrix(factor, symbols, start, end, forward_days)
            observations = matrix.observations
            excluded_symbols = matrix.excluded_symbols
            exclusion_reasons = matrix.exclusion_reasons
            warnings = matrix.warnings
            matrix_metadata = matrix.to_metadata()
        else:
            observations, excluded_symbols, exclusion_reasons, warnings = self._observations(
                factor=factor,
                symbols=symbols,
                start=start,
                end=end,
                forward_days=forward_days,
            )
        observations, pipeline_warnings = self._apply_pipeline(
            observations,
            factor=factor,
            pipeline_config=normalized_pipeline_config,
        )
        warnings.extend(pipeline_warnings)
        if not observations:
            raise ValueError("no factor observations available for evaluation")
        factor_coverage = self._factor_coverage(factor, symbols, observations)
        warnings.extend(self._factor_coverage_warnings(factor, factor_coverage))

        ic_values, rank_ic_values = self._correlations(observations)
        quintiles = self._quintiles(observations)
        spread_return = self._spread_return(quintiles)
        ic_mean = self._mean(ic_values)
        ic_std = self._std(ic_values)
        rank_ic_mean = self._mean(rank_ic_values)
        rank_ic_std = self._std(rank_ic_values)
        if bulk_matrix:
            decay = self._decay_bulk(factor, symbols, start, end, DEFAULT_DECAY_DAYS, normalized_pipeline_config)
        else:
            decay = self._decay(
                factor=factor,
                symbols=symbols,
                start=start,
                end=end,
                horizons=DEFAULT_DECAY_DAYS,
                pipeline_config=normalized_pipeline_config,
                factor_cache=cache if use_cache else None,
            )
        half_life_days = _estimate_half_life(decay)
        performance_metadata = self._performance_metadata(
            cache=cache,
            cache_before=cache_before,
            matrix_metadata=matrix_metadata,
            cache_enabled=use_cache,
            bulk_matrix=bulk_matrix,
            cache_stats=cache_stats,
            eval_seconds=time.monotonic() - eval_started,
            matrix_rows=len(observations),
        )

        result = FactorEvaluationResult(
            factor=factor,
            start_date=start,
            end_date=end,
            forward_days=forward_days,
            universe=symbols,
            no_lookahead=True,
            ic_mean=ic_mean,
            ic_std=ic_std,
            ic_positive_rate=self._positive_rate(ic_values),
            ic_count=len(ic_values),
            rank_ic_mean=rank_ic_mean,
            rank_ic_std=rank_ic_std,
            rank_ic_positive_rate=self._positive_rate(rank_ic_values),
            rank_ic_count=len(rank_ic_values),
            icir=(ic_mean / ic_std) if ic_mean is not None and ic_std not in {None, 0.0} else None,
            quintiles=quintiles,
            spread_return=spread_return,
            decay=decay,
            half_life_days=half_life_days,
            observations=observations,
            excluded_symbols=excluded_symbols,
            exclusion_reasons=exclusion_reasons,
            factor_family=str(factor_metadata["factor_family"]),
            factor_type=str(factor_metadata["factor_type"]),
            factor_category=str(factor_metadata["factor_category"]),
            factor_description=str(factor_metadata["factor_description"]),
            factor_inputs=list(factor_metadata["factor_inputs"]),
            factor_higher_is_better=bool(factor_metadata["higher_is_better"]),
            factor_no_lookahead=bool(factor_metadata["no_lookahead"]),
            factor_coverage=factor_coverage,
            warnings=warnings,
            pipeline_config=normalized_pipeline_config,
            report_path="",
            performance_metadata=performance_metadata,
        )
        report_path = self._write_report(result) if write_report else ""
        return replace(result, report_path=str(report_path))

    def _observations_with_cache(
        self,
        factor: str,
        symbols: list[str],
        start: str | None,
        end: str | None,
        forward_days: int,
        factor_cache: FactorEvalCache,
    ) -> tuple[list[FactorObservation], list[str], dict[str, str], list[str], dict]:
        key = self._cache_key(factor, symbols, start, end, forward_days)
        matrix, hit = factor_cache.get_or_build(
            key,
            lambda: self._build_factor_matrix(factor, symbols, start, end, forward_days),
        )
        warnings = list(matrix.warnings)
        return (
            list(matrix.observations),
            list(matrix.excluded_symbols),
            dict(matrix.exclusion_reasons),
            warnings,
            matrix.to_metadata() | {"cache_key": key.to_dict(), "cache_hit": hit},
        )

    def _build_factor_matrix(
        self,
        factor: str,
        symbols: list[str],
        start: str | None,
        end: str | None,
        forward_days: int,
    ) -> FactorMatrixResult:
        started = time.monotonic()
        matrix = FactorMatrixBuilder(self.price_store, self.factor_registry).build(
            factor=factor,
            symbols=symbols,
            start=start,
            end=end,
            forward_days=forward_days,
        )
        observations = [
            FactorObservation(
                signal_date=row.signal_date,
                future_date=str(row.future_date),
                symbol=row.symbol,
                factor_value=float(row.factor_value),
                future_return=float(row.future_return),
                forward_days=row.forward_days,
            )
            for row in matrix.valid_rows
            if row.factor_value is not None and row.future_return is not None and row.future_date is not None
        ]
        return FactorMatrixResult(
            factor_name=factor,
            universe=list(symbols),
            start=start,
            end=end,
            forward_days=forward_days,
            observations=observations,
            excluded_symbols=matrix.excluded_symbols,
            exclusion_reasons=matrix.exclusion_reasons,
            warnings=matrix.warnings,
            matrix_build_seconds=time.monotonic() - started,
            bulk_read_seconds=matrix.bulk_read_seconds,
        )

    def _cache_key(
        self,
        factor: str,
        symbols: list[str],
        start: str | None,
        end: str | None,
        forward_days: int,
    ) -> FactorCacheKey:
        return FactorCacheKey(
            factor_name=factor,
            universe_hash=make_universe_hash(symbols),
            start=start,
            end=end,
            forward_days=forward_days,
            factor_version=str(self.factor_registry.metadata(factor).get("version") or "v1"),
            data_newest_date=self._data_newest_date(symbols),
            no_lookahead=True,
        )

    def _data_newest_date(self, symbols: list[str]) -> str | None:
        if hasattr(self.price_store, "latest_dates"):
            latest_dates = list(self.price_store.latest_dates(symbols).values())
        else:
            latest_dates = [self.price_store.latest_date(symbol) for symbol in symbols]
        latest_dates = [date for date in latest_dates if date]
        return max(latest_dates) if latest_dates else None

    @staticmethod
    def _performance_metadata(
        cache: FactorEvalCache | None,
        cache_before: dict,
        matrix_metadata: dict | None,
        cache_enabled: bool,
        bulk_matrix: bool,
        cache_stats: bool,
        eval_seconds: float,
        matrix_rows: int,
    ) -> dict | None:
        if not (cache_enabled or bulk_matrix or cache_stats):
            return None
        after = cache.snapshot() if cache else {}
        delta = {
            key: int(after.get(key, 0)) - int(cache_before.get(key, 0))
            for key in (
                "factor_value_hits",
                "factor_value_misses",
                "future_return_hits",
                "future_return_misses",
                "matrix_hits",
                "matrix_misses",
                "invalidations",
            )
        }
        delta["cache_memory_estimate"] = int(after.get("cache_memory_estimate", 0))
        delta["cached_matrices"] = int(after.get("cached_matrices", 0))
        matrix_build_seconds = (matrix_metadata or {}).get("matrix_build_seconds")
        bulk_read_seconds = (matrix_metadata or {}).get("bulk_read_seconds")
        return {
            "cache_enabled": cache_enabled,
            "bulk_matrix": bulk_matrix,
            "bulk_matrix_enabled": bulk_matrix,
            "parallel_enabled": False,
            "workers": 1,
            "bulk_read_seconds": bulk_read_seconds,
            "cache_hits": delta.get("matrix_hits", 0),
            "cache_misses": delta.get("matrix_misses", 0),
            "matrix_rows": matrix_rows,
            "matrix_build_seconds": matrix_build_seconds,
            "eval_seconds": round(eval_seconds, 6),
            "speedup_estimate": None,
            "cache_stats": delta,
            "matrix": matrix_metadata,
            "no_lookahead": True,
        }

    def _observations(
        self,
        factor: str,
        symbols: list[str],
        start: str | None,
        end: str | None,
        forward_days: int,
    ) -> tuple[list[FactorObservation], list[str], dict[str, str], list[str]]:
        observations: list[FactorObservation] = []
        excluded_symbols = []
        exclusion_reasons = {}
        warnings = []
        histories = self._price_histories(symbols)

        for symbol in symbols:
            history = histories.get(symbol)
            if history is None:
                history = histories.get(symbol.upper())
            if history is None or history.empty:
                excluded_symbols.append(symbol)
                exclusion_reasons[symbol] = "no price data"
                warnings.append(f"excluded {symbol}: no price data")
                continue

            history = history.sort_values("date").reset_index(drop=True)
            history["close"] = pd.to_numeric(history["close"], errors="coerce")
            history = history.dropna(subset=["close"]).reset_index(drop=True)
            if history.empty:
                excluded_symbols.append(symbol)
                exclusion_reasons[symbol] = "no valid close prices"
                warnings.append(f"excluded {symbol}: no valid close prices")
                continue

            symbol_observations = self._symbol_observations(
                factor=factor,
                symbol=symbol,
                history=history,
                start=start,
                end=end,
                forward_days=forward_days,
            )
            if not symbol_observations:
                excluded_symbols.append(symbol)
                exclusion_reasons[symbol] = "no valid factor and future-return pairs"
                warnings.append(f"excluded {symbol}: no valid factor and future-return pairs")
                continue
            observations.extend(symbol_observations)

        observations.sort(key=lambda row: (row.signal_date, row.symbol, row.forward_days))
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
        forward_days: int,
    ) -> list[FactorObservation]:
        observations = []
        for index in range(len(history)):
            signal_date = str(history.iloc[index]["date"])
            if start and signal_date < start:
                continue
            if end and signal_date > end:
                continue
            future_index = index + forward_days
            if future_index >= len(history):
                continue

            historical = history.iloc[: index + 1]
            factor_value = self._factor_value(
                historical["close"],
                factor,
                symbol=symbol,
                signal_date=signal_date,
                registry=self.factor_registry,
            )
            if factor_value is None:
                continue

            signal_close = float(history.iloc[index]["close"])
            future_close = float(history.iloc[future_index]["close"])
            observations.append(
                FactorObservation(
                    signal_date=signal_date,
                    future_date=str(history.iloc[future_index]["date"]),
                    symbol=symbol,
                    factor_value=float(factor_value),
                    future_return=(future_close / signal_close) - 1.0,
                    forward_days=forward_days,
                )
            )
        return observations

    @staticmethod
    def _factor_value(
        closes: pd.Series,
        factor: str,
        symbol: str | None = None,
        signal_date: str | None = None,
        registry: FactorRegistry | None = None,
    ) -> float | None:
        factor_registry = registry or FACTOR_REGISTRY
        return factor_registry.factor_value(closes, factor, symbol=symbol, as_of_date=signal_date)

    def _factor_coverage(
        self,
        factor: str,
        symbols: list[str],
        observations: list[FactorObservation],
    ) -> dict | None:
        return factor_coverage(self.factor_registry, factor, symbols, observations)

    def _factor_coverage_warnings(self, factor: str, coverage: dict | None) -> list[str]:
        return factor_coverage_warnings(factor, coverage)

    @staticmethod
    def _correlations(observations: list[FactorObservation]) -> tuple[list[float], list[float]]:
        return cross_section_correlations(observations)

    @staticmethod
    def _quintiles(observations: list[FactorObservation]) -> dict[str, float | None]:
        frame = pd.DataFrame([asdict(observation) for observation in observations])
        if frame.empty:
            return {f"q{index}": None for index in range(1, 6)}
        frame["rank_pct"] = frame.groupby("signal_date")["factor_value"].rank(pct=True, method="first")
        frame["quintile"] = (frame["rank_pct"] * 5).apply(lambda value: min(max(int(value + 0.999999), 1), 5))
        return {
            f"q{index}": FactorEvaluation._mean(frame.loc[frame["quintile"] == index, "future_return"].tolist())
            for index in range(1, 6)
        }

    @staticmethod
    def _spread_return(quintiles: dict[str, float | None]) -> float | None:
        q1 = quintiles.get("q1")
        q5 = quintiles.get("q5")
        if q1 is None or q5 is None:
            return None
        return q5 - q1

    def _decay(
        self,
        factor: str,
        symbols: list[str],
        start: str | None,
        end: str | None,
        horizons: list[int],
        pipeline_config: dict | None,
        factor_cache: FactorEvalCache | None = None,
    ) -> dict[str, dict[str, float | int | None]]:
        decay = {}
        for horizon in horizons:
            if factor_cache is not None:
                observations, _, _, _, _ = self._observations_with_cache(factor, symbols, start, end, horizon, factor_cache)
            else:
                observations, _, _, _ = self._observations(factor, symbols, start, end, horizon)
            observations, _ = self._apply_pipeline(
                observations,
                factor=factor,
                pipeline_config=pipeline_config,
            )
            ic_values, rank_ic_values = self._correlations(observations)
            decay[f"{horizon}d"] = {
                "ic": self._mean(ic_values),
                "rank_ic": self._mean(rank_ic_values),
                "ic_count": len(ic_values),
                "rank_ic_count": len(rank_ic_values),
            }
        return decay

    def _decay_bulk(
        self,
        factor: str,
        symbols: list[str],
        start: str | None,
        end: str | None,
        horizons: list[int],
        pipeline_config: dict | None,
    ) -> dict[str, dict[str, float | int | None]]:
        matrices = FactorMatrixBuilder(self.price_store, self.factor_registry).build_many_horizons(
            factor=factor,
            symbols=symbols,
            start=start,
            end=end,
            horizons=horizons,
        )
        decay = {}
        for horizon in horizons:
            matrix = matrices[int(horizon)]
            observations = [
                FactorObservation(
                    signal_date=row.signal_date,
                    future_date=str(row.future_date),
                    symbol=row.symbol,
                    factor_value=float(row.factor_value),
                    future_return=float(row.future_return),
                    forward_days=row.forward_days,
                )
                for row in matrix.valid_rows
                if row.factor_value is not None and row.future_return is not None and row.future_date is not None
            ]
            observations, _ = self._apply_pipeline(
                observations,
                factor=factor,
                pipeline_config=pipeline_config,
            )
            ic_values, rank_ic_values = self._correlations(observations)
            decay[f"{horizon}d"] = {
                "ic": self._mean(ic_values),
                "rank_ic": self._mean(rank_ic_values),
                "ic_count": len(ic_values),
                "rank_ic_count": len(rank_ic_values),
            }
        return decay

    def _apply_pipeline(
        self,
        observations: list[FactorObservation],
        factor: str,
        pipeline_config: dict | None,
    ) -> tuple[list[FactorObservation], list[str]]:
        return apply_factor_pipeline(
            observations,
            factor=factor,
            pipeline_config=pipeline_config,
            report_dir=self.report_dir,
            rebuild_observation=lambda row, cleaned_value: FactorObservation(
                signal_date=str(row.signal_date),
                future_date=str(row.future_date),
                symbol=str(row.symbol),
                factor_value=cleaned_value,
                future_return=float(row.future_return),
                forward_days=int(row.forward_days),
            ),
            sort_key=lambda row: (row.signal_date, row.symbol, row.forward_days),
        )

    @staticmethod
    def _mean(values: list[float]) -> float | None:
        return mean(values)

    @staticmethod
    def _std(values: list[float]) -> float | None:
        return std(values)

    @staticmethod
    def _positive_rate(values: list[float]) -> float | None:
        return positive_rate(values)

    @staticmethod
    def _normalize_symbols(symbols: list[str]) -> list[str]:
        return normalize_symbols(symbols)

    @staticmethod
    def _validate(factor: str, start: str | None, end: str | None, forward_days: int) -> None:
        if factor not in SUPPORTED_FACTORS:
            raise ValueError(f"factor must be one of: {', '.join(sorted(SUPPORTED_FACTORS))}")
        if start and end and start > end:
            raise ValueError("start must be before or equal to end")
        if forward_days <= 0:
            raise ValueError("forward_days must be positive")

    def _write_report(self, result: FactorEvaluationResult) -> Path:
        return write_factor_report(self.report_dir, "factor_eval", result.factor, result.to_report())
