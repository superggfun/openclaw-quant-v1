"""No-lookahead factor evaluation framework."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

import pandas as pd

from quant.config import DEFAULT_SYMBOLS
from quant.factor_pipeline.factor_pipeline import FactorPipeline
from quant.factors.factor_registry import FactorRegistry
from quant.fundamental_data.fundamental_store import FundamentalStore
from quant.storage.sqlite_store import SQLitePriceStore


FACTOR_REGISTRY = FactorRegistry()
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

    def to_report(self) -> dict:
        return {
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
    ) -> FactorEvaluationResult:
        factor = factor.strip().lower()
        self._validate(factor, start, end, forward_days)
        factor_metadata = self.factor_registry.metadata(factor)
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
        decay = self._decay(
            factor=factor,
            symbols=symbols,
            start=start,
            end=end,
            horizons=DEFAULT_DECAY_DAYS,
            pipeline_config=normalized_pipeline_config,
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
        )
        report_path = self._write_report(result)
        return FactorEvaluationResult(
            factor=result.factor,
            start_date=result.start_date,
            end_date=result.end_date,
            forward_days=result.forward_days,
            universe=result.universe,
            no_lookahead=result.no_lookahead,
            ic_mean=result.ic_mean,
            ic_std=result.ic_std,
            ic_positive_rate=result.ic_positive_rate,
            ic_count=result.ic_count,
            rank_ic_mean=result.rank_ic_mean,
            rank_ic_std=result.rank_ic_std,
            rank_ic_positive_rate=result.rank_ic_positive_rate,
            rank_ic_count=result.rank_ic_count,
            icir=result.icir,
            quintiles=result.quintiles,
            spread_return=result.spread_return,
            decay=result.decay,
            observations=result.observations,
            excluded_symbols=result.excluded_symbols,
            exclusion_reasons=result.exclusion_reasons,
            factor_family=result.factor_family,
            factor_type=result.factor_type,
            factor_category=result.factor_category,
            factor_description=result.factor_description,
            factor_inputs=result.factor_inputs,
            factor_higher_is_better=result.factor_higher_is_better,
            factor_no_lookahead=result.factor_no_lookahead,
            factor_coverage=result.factor_coverage,
            warnings=result.warnings,
            pipeline_config=result.pipeline_config,
            report_path=str(report_path),
        )

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

        for symbol in symbols:
            history = self.price_store.get_price_history(symbol)
            if history.empty:
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
        if not self.factor_registry.is_fundamental(factor):
            return None
        covered_symbols = sorted({observation.symbol for observation in observations})
        missing_symbols = sorted(set(symbols) - set(covered_symbols))
        total_symbols = len(symbols)
        covered_count = len(covered_symbols)
        coverage_pct = (covered_count / total_symbols) if total_symbols else 0.0
        metadata = self.factor_registry.metadata(factor)
        report_dates = []
        for observation in observations:
            row = self.factor_registry.latest_fundamental_row(
                observation.symbol,
                str(metadata.get("fundamental_statement") or "fundamental_metrics"),
                observation.signal_date,
            )
            if row and row.get("report_date"):
                report_dates.append(str(row["report_date"]))
        return {
            "coverage_percentage": coverage_pct,
            "missing_percentage": 1.0 - coverage_pct,
            "covered_symbols": covered_symbols,
            "missing_symbols": missing_symbols,
            "fundamental_metrics_used": metadata.get("fundamental_metrics_used") or [],
            "report_date_coverage": {
                "earliest_report_date": min(report_dates) if report_dates else None,
                "latest_report_date": max(report_dates) if report_dates else None,
                "observations_with_report_date": len(report_dates),
            },
            "no_lookahead_filter": "report_date <= signal_date",
        }

    def _factor_coverage_warnings(self, factor: str, coverage: dict | None) -> list[str]:
        if coverage is None:
            return []
        warnings = []
        if not coverage["covered_symbols"]:
            warnings.append(f"MISSING_FUNDAMENTAL_DATA: {factor} has no symbols with usable report_date-filtered fundamentals")
        elif coverage["missing_symbols"]:
            warnings.append(
                f"PARTIAL_FUNDAMENTAL_DATA: {factor} covers {coverage['coverage_percentage']:.2%} of the universe"
            )
        return warnings

    @staticmethod
    def _correlations(observations: list[FactorObservation]) -> tuple[list[float], list[float]]:
        if not observations:
            return [], []
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
    ) -> dict[str, dict[str, float | int | None]]:
        decay = {}
        for horizon in horizons:
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

    def _apply_pipeline(
        self,
        observations: list[FactorObservation],
        factor: str,
        pipeline_config: dict | None,
    ) -> tuple[list[FactorObservation], list[str]]:
        if pipeline_config is None or not observations:
            return observations, []

        processed: list[FactorObservation] = []
        warnings: list[str] = []
        frame = pd.DataFrame([asdict(observation) for observation in observations])
        pipeline = FactorPipeline(pipeline_config, report_dir=self.report_dir)
        for signal_date, group in frame.groupby("signal_date"):
            raw_values = {
                str(row.symbol): float(row.factor_value)
                for row in group.itertuples(index=False)
            }
            pipeline_result = pipeline.run(
                raw_values,
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
                    FactorObservation(
                        signal_date=str(row.signal_date),
                        future_date=str(row.future_date),
                        symbol=str(row.symbol),
                        factor_value=float(cleaned_value),
                        future_return=float(row.future_return),
                        forward_days=int(row.forward_days),
                    )
                )

        processed.sort(key=lambda row: (row.signal_date, row.symbol, row.forward_days))
        return processed, sorted(set(warnings))

    @staticmethod
    def _mean(values: list[float]) -> float | None:
        if not values:
            return None
        return float(pd.Series(values, dtype="float64").mean())

    @staticmethod
    def _std(values: list[float]) -> float | None:
        if len(values) < 2:
            return None
        return float(pd.Series(values, dtype="float64").std())

    @staticmethod
    def _positive_rate(values: list[float]) -> float | None:
        if not values:
            return None
        return sum(1 for value in values if value > 0) / len(values)

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
    def _validate(factor: str, start: str | None, end: str | None, forward_days: int) -> None:
        if factor not in SUPPORTED_FACTORS:
            raise ValueError(f"factor must be one of: {', '.join(sorted(SUPPORTED_FACTORS))}")
        if start and end and start > end:
            raise ValueError("start must be before or equal to end")
        if forward_days <= 0:
            raise ValueError("forward_days must be positive")

    def _write_report(self, result: FactorEvaluationResult) -> Path:
        self.report_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = self.report_dir / f"factor_eval_{timestamp}.json"
        path.write_text(json.dumps(result.to_report(), indent=2), encoding="utf-8")
        return path
