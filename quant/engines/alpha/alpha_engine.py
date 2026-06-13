"""Alpha factor engine for target allocation generation."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Mapping

import pandas as pd

from quant.config import DEFAULT_SYMBOLS
from quant.core.symbols import normalize_symbols
from quant.engines.factor_pipeline.factor_pipeline import FactorPipeline
from quant.factors.price.factor_registry import FactorRegistry
from quant.data.fundamental.fundamental_store import FundamentalStore
from quant.engines.multi_factor.multi_factor_model import MultiFactorModel
from quant.reports.report_io import generate_report_path, write_json_report
from quant.storage.sqlite_store import SQLitePriceStore

from quant.engines.alpha.models import AlphaFactorRow, AlphaResult
from quant.engines.alpha import scoring


DEFAULT_ALPHA_CONFIG = {
    "universe": list(DEFAULT_SYMBOLS),
    "as_of_date": None,
    "lookback_short": 20,
    "lookback_long": 60,
    "top_n": 5,
    "weighting_mode": "equal_weight",
    "min_cash_weight": 0.10,
    "max_position_weight": 0.20,
    "factor_weights": None,
    "multi_factor": None,
    "family_weights": None,
}


class AlphaEngine:
    """Generate alpha factors and target weights from stored price history."""

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

    def generate(
        self,
        config: Mapping | None = None,
        output_targets: str | Path | None = None,
        pipeline_config: Mapping | None = None,
        write_report: bool = True,
    ) -> AlphaResult:
        normalized_config = self._normalize_config(config or {})
        warnings: list[str] = []
        lookback_used = self._lookback_used(normalized_config)
        pipeline_score_by_symbol: dict[str, float] | None = None
        pipeline_report_path: str | None = None
        pipeline_factor = "risk_adjusted_momentum"
        normalized_pipeline_config = None
        multi_factor_report_path: str | None = None
        multi_factor_summary: dict | None = None

        row_factor_names = self._row_factor_names(normalized_config, pipeline_config)
        price_histories = self._price_histories(normalized_config["universe"], end=normalized_config["as_of_date"])
        factor_rows = [
            self._factor_row(symbol, normalized_config, warnings, row_factor_names, history=self._history_for_symbol(price_histories, symbol))
            for symbol in normalized_config["universe"]
        ]
        composite_score_by_symbol: dict[str, float] | None = None
        multi_factor_config = self._multi_factor_config(normalized_config)
        if multi_factor_config is not None:
            factor_rows, composite_score_by_symbol, multi_factor_report_path, multi_factor_summary, mf_warnings = (
                self._apply_multi_factor_scores(
                    factor_rows,
                    multi_factor_config,
                    as_of_date=self._max_date(row.data_end_date for row in factor_rows),
                    write_report=write_report,
                )
            )
            warnings.extend(mf_warnings)
            pipeline_factor = "multi_factor_alpha"
        elif normalized_config.get("factor_weights"):
            factor_rows, composite_score_by_symbol = scoring.apply_composite_scores(
                factor_rows,
                normalized_config["factor_weights"],
                warnings,
            )
            pipeline_factor = "composite_alpha_score"
        if pipeline_config is not None:
            normalized_pipeline_config = FactorPipeline.normalize_config(pipeline_config)
            pipeline_factor = str(dict(pipeline_config).get("factor", pipeline_factor)).strip().lower()
            raw_values = {
                row.symbol: scoring.row_factor_value(row, pipeline_factor)
                for row in factor_rows
            }
            pipeline_result = FactorPipeline(normalized_pipeline_config, report_dir=self.report_dir).run(
                raw_values,
                factor=pipeline_factor,
                as_of_date=self._max_date(row.data_end_date for row in factor_rows),
            )
            pipeline_score_by_symbol = pipeline_result.cleaned_factor_values
            pipeline_report_path = pipeline_result.report_path
            warnings.extend(pipeline_result.warnings)

        ranked_rows = scoring.rank_alpha_rows(
            factor_rows,
            ranking_factor=pipeline_factor,
            score_by_symbol=pipeline_score_by_symbol or composite_score_by_symbol,
        )
        selected_symbols = [
            row.symbol
            for row in sorted(
                [row for row in ranked_rows if row.rank is not None and row.rank <= normalized_config["top_n"]],
                key=lambda row: row.rank or 0,
            )
        ]
        ranked_rows = scoring.mark_selected(ranked_rows, selected_symbols)
        selected_rows = sorted(
            [row for row in ranked_rows if row.selected],
            key=lambda row: row.rank or 0,
        )
        if not selected_rows:
            raise ValueError("no symbols have enough price history for alpha generation")

        target_weights = scoring.compute_target_weights(
            selected_rows,
            normalized_config["target_weighting_mode"],
            normalized_config["min_cash_weight"],
            normalized_config["max_position_weight"],
            warnings,
            score_by_symbol=pipeline_score_by_symbol,
        )
        scoring.validate_targets(target_weights, normalized_config)
        excluded_symbols = [row.symbol for row in ranked_rows if row.excluded]
        exclusion_reasons = {
            row.symbol: row.exclusion_reason or "excluded"
            for row in ranked_rows
            if row.excluded
        }
        as_of_date = self._result_as_of_date(selected_rows)
        data_start_date = self._min_date(row.data_start_date for row in selected_rows)
        data_end_date = self._max_date(row.data_end_date for row in selected_rows)
        execution_histories = self._price_histories([row.symbol for row in selected_rows], start=as_of_date) if as_of_date else {}
        suggested_execution_date = self._suggested_execution_date(selected_rows, as_of_date, histories=execution_histories)
        target_output = self._write_targets(target_weights, output_targets) if output_targets else None

        result = AlphaResult(
            config=normalized_config,
            as_of_date=as_of_date,
            data_start_date=data_start_date,
            data_end_date=data_end_date,
            lookback_used=lookback_used,
            factors=ranked_rows,
            selected_symbols=selected_symbols,
            target_weights=target_weights,
            excluded_symbols=excluded_symbols,
            exclusion_reasons=exclusion_reasons,
            suggested_execution_date=suggested_execution_date,
            pipeline_config=normalized_pipeline_config,
            pipeline_report_path=pipeline_report_path,
            multi_factor_report_path=multi_factor_report_path,
            multi_factor_summary=multi_factor_summary,
            warnings=warnings,
            report_path="",
            targets_path=str(target_output) if target_output else None,
        )
        report_path = self._write_report(result) if write_report else ""
        return replace(result, report_path=str(report_path))

    def _factor_row(
        self,
        symbol: str,
        config: dict,
        warnings: list[str],
        factor_names: list[str] | None = None,
        history: pd.DataFrame | None = None,
    ) -> AlphaFactorRow:
        if history is None:
            history = self.price_store.get_price_history(symbol, end=config["as_of_date"])
        if history.empty:
            return self._excluded_row(symbol, "no price data", warnings)

        history = history.sort_values("date")
        closes = pd.to_numeric(history["close"], errors="coerce").dropna()
        if len(closes) <= config["lookback_long"]:
            return self._excluded_row(
                symbol,
                f"need at least {config['lookback_long'] + 1} closes",
                warnings,
            )

        momentum_20d = self._momentum(closes, config["lookback_short"])
        momentum_60d = self._momentum(closes, config["lookback_long"])
        volatility_20d = self._volatility(closes, config["lookback_short"])
        risk_adjusted_momentum = (
            momentum_20d / volatility_20d if volatility_20d and volatility_20d > 0 else None
        )

        factor_values: dict[str, float | None] = {
            "momentum_20d": momentum_20d,
            "momentum_60d": momentum_60d,
            "volatility_20d": volatility_20d,
            "risk_adjusted_momentum": risk_adjusted_momentum,
        }
        if factor_names:
            definitions = self._factor_definitions_for_row(factor_names)
            for definition in definitions:
                name = definition.name
                if name in factor_values:
                    continue
                factor_fn = self.factor_registry.factor_function(name)
                if factor_fn is None:
                    factor_values[name] = None
                    continue
                try:
                    value = factor_fn(name, closes)
                    factor_values[name] = value
                except Exception:
                    factor_values[name] = None

        return AlphaFactorRow(
            symbol=symbol,
            as_of_date=config["as_of_date"],
            data_start_date=str(closes.index[0]) if len(closes) > 0 else None,
            data_end_date=str(closes.index[-1]) if len(closes) > 0 else None,
            lookback_used=config.get("lookback_used", {}),
            momentum_20d=momentum_20d,
            momentum_60d=momentum_60d,
            volatility_20d=volatility_20d,
            risk_adjusted_momentum=risk_adjusted_momentum,
            rank=None,
            selected=False,
            excluded=False,
            exclusion_reason=None,
            factor_values=factor_values,
        )

    def _apply_multi_factor_scores(
        self,
        rows: list[AlphaFactorRow],
        multi_factor_config: dict,
        as_of_date: str | None,
        write_report: bool,
    ) -> tuple[list[AlphaFactorRow], dict[str, float], str | None, dict, list[str]]:
        raw_values = {
            row.symbol: row.factor_values or {}
            for row in rows
            if not row.excluded
        }
        result = MultiFactorModel(self.factor_registry, report_dir=self.report_dir).run(
            raw_values,
            config=multi_factor_config,
            as_of_date=as_of_date,
            write_report=write_report,
        )
        score_by_symbol = {
            score.symbol: score.final_alpha_score
            for score in result.scores
            if score.final_alpha_score is not None
        }
        detail_by_symbol = {score.symbol: score for score in result.scores}
        updated_rows: list[AlphaFactorRow] = []
        warnings: list[str] = list(result.warnings)
        for row in rows:
            detail = detail_by_symbol.get(row.symbol)
            if row.excluded:
                updated_rows.append(row)
                continue
            excluded = detail is None or detail.final_alpha_score is None
            reason = row.exclusion_reason
            if excluded:
                reason = "no valid multi-factor alpha score"
                warnings.append(f"excluded {row.symbol}: {reason}")
            updated_rows.append(
                scoring.copy_alpha_row(
                    row,
                    excluded=excluded,
                    exclusion_reason=reason,
                    factor_contributions=(detail.factor_contributions if detail else None),
                    family_contributions=(detail.family_contributions if detail else None),
                    factor_confidence=(detail.factor_confidence if detail else None),
                    overall_confidence=(detail.overall_confidence if detail else None),
                    composite_alpha_score=(detail.final_alpha_score if detail else None),
                )
            )
        summary = {
            "factors": result.factors,
            "factor_families": result.factor_families,
            "weighting_mode": result.weighting_mode,
            "factor_weights": result.factor_weights,
            "factor_weights_by_family": result.factor_weights_by_family,
            "family_weights": result.family_weights,
            "coverage": result.coverage,
            "confidence": result.confidence,
            "stability": result.stability,
        }
        return updated_rows, score_by_symbol, result.report_path or None, summary, warnings

    @staticmethod
    def _momentum(closes: pd.Series, lookback: int) -> float:
        return float((closes.iloc[-1] / closes.iloc[-(lookback + 1)]) - 1.0)

    @staticmethod
    def _volatility(closes: pd.Series, lookback: int) -> float | None:
        returns = closes.pct_change().dropna().tail(lookback)
        if returns.empty:
            return None
        return float(returns.std())

    def _excluded_row(
        self,
        symbol: str,
        reason: str,
        warnings: list[str],
        data_start_date: str | None = None,
        data_end_date: str | None = None,
    ) -> AlphaFactorRow:
        warnings.append(f"excluded {symbol}: {reason}")
        return AlphaFactorRow(
            symbol=symbol,
            as_of_date=data_end_date,
            data_start_date=data_start_date,
            data_end_date=data_end_date,
            lookback_used={},
            momentum_20d=None,
            momentum_60d=None,
            volatility_20d=None,
            risk_adjusted_momentum=None,
            rank=None,
            selected=False,
            excluded=True,
            exclusion_reason=reason,
            factor_values=None,
            factor_contributions=None,
            family_contributions=None,
            factor_confidence=None,
            overall_confidence=None,
            composite_alpha_score=None,
        )

    @staticmethod
    def _normalize_config(config: Mapping) -> dict:
        merged = dict(DEFAULT_ALPHA_CONFIG)
        merged.update(dict(config))
        universe = merged.get("universe") or list(DEFAULT_SYMBOLS)
        merged["universe"] = AlphaEngine._normalize_symbols(list(universe))
        merged["as_of_date"] = merged.get("as_of_date") or None
        merged["lookback_short"] = int(merged["lookback_short"])
        merged["lookback_long"] = int(merged["lookback_long"])
        merged["top_n"] = int(merged["top_n"])
        merged["weighting_mode"] = str(merged["weighting_mode"]).lower()
        merged["target_weighting_mode"] = merged["weighting_mode"]
        if merged["weighting_mode"] in {"custom_weight", "ic_weighted", "stability_weighted"}:
            multi_factor = dict(merged.get("multi_factor") or {})
            multi_factor.setdefault("weighting_mode", merged["weighting_mode"])
            if merged.get("family_weights"):
                multi_factor.setdefault("family_weights", merged["family_weights"])
            merged["multi_factor"] = multi_factor
            merged["target_weighting_mode"] = "equal_weight"
        merged["min_cash_weight"] = float(merged["min_cash_weight"])
        merged["max_position_weight"] = float(merged["max_position_weight"])
        merged["factor_weights"] = AlphaEngine._normalize_factor_weights(merged.get("factor_weights"))
        merged["multi_factor"] = AlphaEngine._normalize_multi_factor_config(merged.get("multi_factor"), merged)

        if not merged["universe"]:
            raise ValueError("alpha universe must not be empty")
        if merged["lookback_short"] <= 0:
            raise ValueError("lookback_short must be positive")
        if merged["lookback_long"] <= merged["lookback_short"]:
            raise ValueError("lookback_long must be greater than lookback_short")
        if merged["top_n"] <= 0:
            raise ValueError("top_n must be positive")
        if merged["target_weighting_mode"] not in {"equal_weight", "score_weighted"}:
            raise ValueError("weighting_mode must be one of: equal_weight, score_weighted, custom_weight, ic_weighted, stability_weighted")
        if not 0 <= merged["min_cash_weight"] <= 1:
            raise ValueError("min_cash_weight must be between 0 and 1")
        if not 0 < merged["max_position_weight"] <= 1:
            raise ValueError("max_position_weight must be between 0 and 1")
        return merged

    @staticmethod
    def _lookback_used(config: Mapping) -> dict[str, int]:
        lookbacks = {
            "momentum_20d": int(config["lookback_short"]),
            "momentum_60d": int(config["lookback_long"]),
            "volatility_20d": int(config["lookback_short"]),
        }
        factor_weights = config.get("factor_weights") if isinstance(config, Mapping) else None
        if factor_weights:
            registry = FactorRegistry()
            for factor in factor_weights:
                lookbacks[factor] = registry.describe(factor).lookback_days
        multi_factor = config.get("multi_factor") if isinstance(config, Mapping) else None
        if multi_factor:
            registry = FactorRegistry()
            for factor in multi_factor.get("factors", []):
                lookbacks[factor] = registry.describe(factor).lookback_days
        return dict(sorted(lookbacks.items()))

    @staticmethod
    def _normalize_factor_weights(factor_weights) -> dict[str, float] | None:
        if factor_weights is None or factor_weights == "":
            return None
        registry = FactorRegistry()
        raw = dict(factor_weights)
        normalized = {}
        for factor, weight in raw.items():
            name = str(factor).strip().lower()
            registry.describe(name)
            numeric_weight = float(weight)
            if numeric_weight < 0:
                raise ValueError("factor_weights must be non-negative")
            if numeric_weight > 0:
                normalized[name] = numeric_weight
        if not normalized:
            return None
        total = sum(normalized.values())
        return {
            factor: weight / total
            for factor, weight in sorted(normalized.items())
        }

    @staticmethod
    def _normalize_multi_factor_config(config, merged_config: Mapping) -> dict | None:
        if config is None and not merged_config.get("family_weights"):
            return None
        raw = dict(config or {})
        if merged_config.get("family_weights"):
            raw.setdefault("family_weights", merged_config["family_weights"])
        if merged_config.get("factor_weights") and raw.get("weighting_mode") == "custom_weight":
            raw.setdefault("factor_weights", merged_config["factor_weights"])
        return MultiFactorModel.normalize_config(raw)

    @staticmethod
    def _multi_factor_config(config: Mapping) -> dict | None:
        value = config.get("multi_factor") if isinstance(config, Mapping) else None
        return dict(value) if value else None

    @staticmethod
    def _result_as_of_date(rows: list[AlphaFactorRow]) -> str | None:
        return AlphaEngine._max_date(row.data_end_date for row in rows)

    @staticmethod
    def _min_date(values) -> str | None:
        dates = [value for value in values if value is not None]
        return min(dates) if dates else None

    @staticmethod
    def _max_date(values) -> str | None:
        dates = [value for value in values if value is not None]
        return max(dates) if dates else None

    def _suggested_execution_date(
        self,
        selected_rows: list[AlphaFactorRow],
        as_of_date: str | None,
        histories: dict[str, pd.DataFrame] | None = None,
    ) -> str | None:
        if as_of_date is None:
            return None

        candidates = []
        for row in selected_rows:
            history = None
            if histories is not None:
                history = self._history_for_symbol(histories, row.symbol)
            if history is None:
                history = self.price_store.get_price_history(row.symbol, start=as_of_date)
            if history.empty:
                continue
            future = history[history["date"] > as_of_date]
            if not future.empty:
                candidates.append(str(future.iloc[0]["date"]))
        return min(candidates) if candidates else None

    def _price_histories(
        self,
        symbols: list[str],
        start: str | None = None,
        end: str | None = None,
    ) -> dict[str, pd.DataFrame]:
        if hasattr(self.price_store, "get_price_history_many"):
            return self.price_store.get_price_history_many(symbols, start=start, end=end)
        return {
            symbol: self.price_store.get_price_history(symbol, start=start, end=end)
            for symbol in symbols
        }

    @staticmethod
    def _history_for_symbol(histories: dict[str, pd.DataFrame], symbol: str) -> pd.DataFrame | None:
        history = histories.get(symbol)
        if history is not None:
            return history
        return histories.get(symbol.upper())

    @staticmethod
    def _normalize_symbols(symbols: list[str]) -> list[str]:
        return normalize_symbols(symbols)

    def _factor_definitions_for_row(self, factor_names: list[str] | None):
        if factor_names is None:
            return self.factor_registry.list_factors()
        return [self.factor_registry.describe(factor) for factor in factor_names]

    def _row_factor_names(self, config: dict, pipeline_config: Mapping | None) -> list[str] | None:
        names = set((config.get("factor_weights") or {}).keys())
        if config.get("multi_factor"):
            names.update(config["multi_factor"].get("factors", []))
        if pipeline_config is not None:
            factor = str(dict(pipeline_config).get("factor", "")).strip().lower()
            if factor and factor not in {
                "momentum_20d",
                "momentum_60d",
                "volatility_20d",
                "risk_adjusted_momentum",
                "composite_alpha_score",
                "multi_factor_alpha",
            }:
                names.add(factor)
        return sorted(names) if names else None

    def _write_report(self, result: AlphaResult) -> Path:
        return write_json_report(
            generate_report_path(self.report_dir, "alpha", unique=True),
            result.to_report(),
        )

    @staticmethod
    def _write_targets(targets: dict[str, float], path: str | Path) -> Path:
        return write_json_report(path, targets, trailing_newline=True)
