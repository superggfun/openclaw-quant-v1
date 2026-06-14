"""Reusable no-lookahead factor preprocessing pipeline."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Mapping

import pandas as pd

from quant.engines.risk.risk_engine import DEFAULT_INDUSTRY_MAP
from quant.reports.report_io import generate_report_path, write_json_report


DEFAULT_FACTOR_PIPELINE_CONFIG = {
    "missing": "drop",
    "fill_value": 0.0,
    "winsorization": {
        "enabled": True,
        "lower_quantile": 0.05,
        "upper_quantile": 0.95,
    },
    "zscore": True,
    "rank_normalization": False,
    "sector_neutralization": {
        "enabled": False,
        "sector_map": DEFAULT_INDUSTRY_MAP,
    },
    "market_beta_neutralization": {
        "enabled": False,
    },
}


@dataclass(frozen=True)
class FactorPipelineResult:
    factor: str
    as_of_date: str | None
    raw_factor_values: dict[str, float | None]
    cleaned_factor_values: dict[str, float]
    excluded_symbols: list[str]
    exclusion_reasons: dict[str, str]
    preprocessing_steps_applied: list[str]
    before_summary_statistics: dict[str, float | int | None]
    after_summary_statistics: dict[str, float | int | None]
    sector_neutralization_result: dict[str, dict[str, float | int]]
    warnings: list[str]
    no_lookahead: bool
    report_path: str

    def to_report(self) -> dict:
        return {
            "factor": self.factor,
            "as_of_date": self.as_of_date,
            "raw_factor_values": self.raw_factor_values,
            "cleaned_factor_values": self.cleaned_factor_values,
            "excluded_symbols": self.excluded_symbols,
            "exclusion_reasons": self.exclusion_reasons,
            "preprocessing_steps_applied": self.preprocessing_steps_applied,
            "before_summary_statistics": self.before_summary_statistics,
            "after_summary_statistics": self.after_summary_statistics,
            "sector_neutralization_result": self.sector_neutralization_result,
            "warnings": self.warnings,
            "no_lookahead": self.no_lookahead,
        }


class FactorPipeline:
    """Clean a factor cross-section without reading future price data."""

    def __init__(
        self,
        config: Mapping | None = None,
        report_dir: str | Path = "reports",
    ) -> None:
        self.config = self.normalize_config(config or {})
        self.report_dir = Path(report_dir)

    def run(
        self,
        factor_values: Mapping[str, float | int | None],
        factor: str,
        as_of_date: str | None = None,
        write_report: bool = True,
    ) -> FactorPipelineResult:
        raw_values = {
            str(symbol).upper().strip(): self._to_float(value)
            for symbol, value in factor_values.items()
            if str(symbol).upper().strip()
        }
        before_stats = self._summary(raw_values)
        cleaned = dict(raw_values)
        excluded_symbols: list[str] = []
        exclusion_reasons: dict[str, str] = {}
        warnings: list[str] = []
        steps: list[str] = []
        sector_result: dict[str, dict[str, float | int]] = {}

        cleaned = self._handle_missing(cleaned, excluded_symbols, exclusion_reasons, steps)
        cleaned = self._winsorize(cleaned, steps)
        cleaned = self._zscore(cleaned, steps)
        cleaned, sector_result = self._sector_neutralize(cleaned, warnings, steps)
        cleaned = self._rank_normalize(cleaned, steps)
        cleaned = self._apply_factor_direction(cleaned, factor, steps)

        if self.config["market_beta_neutralization"]["enabled"]:
            steps.append("market_beta_neutralization_placeholder")
            warnings.append("market/beta neutralization is a placeholder and was not applied")

        after_stats = self._summary(cleaned)
        result = FactorPipelineResult(
            factor=factor,
            as_of_date=as_of_date,
            raw_factor_values=raw_values,
            cleaned_factor_values=cleaned,
            excluded_symbols=excluded_symbols,
            exclusion_reasons=exclusion_reasons,
            preprocessing_steps_applied=steps,
            before_summary_statistics=before_stats,
            after_summary_statistics=after_stats,
            sector_neutralization_result=sector_result,
            warnings=warnings,
            no_lookahead=True,
            report_path="",
        )
        if not write_report:
            return result
        report_path = self._write_report(result)
        return replace(result, report_path=str(report_path))

    def _handle_missing(
        self,
        values: dict[str, float | None],
        excluded_symbols: list[str],
        exclusion_reasons: dict[str, str],
        steps: list[str],
    ) -> dict[str, float]:
        mode = self.config["missing"]
        steps.append(f"missing:{mode}")
        cleaned: dict[str, float] = {}
        for symbol, value in values.items():
            if value is None or pd.isna(value):
                if mode == "fill":
                    cleaned[symbol] = float(self.config["fill_value"])
                else:
                    excluded_symbols.append(symbol)
                    exclusion_reasons[symbol] = "missing factor value"
                continue
            cleaned[symbol] = float(value)
        return cleaned

    def _winsorize(self, values: dict[str, float], steps: list[str]) -> dict[str, float]:
        config = self.config["winsorization"]
        if not config["enabled"] or not values:
            return values
        lower = float(pd.Series(values, dtype="float64").quantile(config["lower_quantile"]))
        upper = float(pd.Series(values, dtype="float64").quantile(config["upper_quantile"]))
        steps.append("winsorization")
        return {
            symbol: min(max(value, lower), upper)
            for symbol, value in values.items()
        }

    def _zscore(self, values: dict[str, float], steps: list[str]) -> dict[str, float]:
        if not self.config["zscore"] or not values:
            return values
        series = pd.Series(values, dtype="float64")
        std = float(series.std())
        steps.append("zscore")
        if std <= 0 or pd.isna(std):
            return {symbol: 0.0 for symbol in values}
        mean = float(series.mean())
        return {
            symbol: float((value - mean) / std)
            for symbol, value in values.items()
        }

    def _sector_neutralize(
        self,
        values: dict[str, float],
        warnings: list[str],
        steps: list[str],
    ) -> tuple[dict[str, float], dict[str, dict[str, float | int]]]:
        config = self.config["sector_neutralization"]
        if not config["enabled"] or not values:
            return values, {}
        sector_map = config["sector_map"]
        frame = pd.DataFrame(
            [
                {
                    "symbol": symbol,
                    "sector": sector_map.get(symbol, "Unknown"),
                    "value": value,
                }
                for symbol, value in values.items()
            ]
        )
        if (frame["sector"] == "Unknown").any():
            unknown = sorted(frame.loc[frame["sector"] == "Unknown", "symbol"].tolist())
            warnings.append(f"sector is unknown for: {', '.join(unknown)}")
        sector_means = frame.groupby("sector")["value"].mean().to_dict()
        steps.append("sector_neutralization")
        neutralized = {
            row.symbol: float(row.value - sector_means[row.sector])
            for row in frame.itertuples(index=False)
        }
        sector_result = {
            sector: {
                "mean_before": float(group["value"].mean()),
                "mean_after": float(
                    pd.Series([neutralized[symbol] for symbol in group["symbol"]], dtype="float64").mean()
                ),
                "count": int(len(group)),
            }
            for sector, group in frame.groupby("sector")
        }
        return neutralized, sector_result

    def _rank_normalize(self, values: dict[str, float], steps: list[str]) -> dict[str, float]:
        if not self.config["rank_normalization"] or not values:
            return values
        steps.append("rank_normalization")
        series = pd.Series(values, dtype="float64")
        ranks = series.rank(method="average", pct=True)
        if len(ranks) <= 1:
            return {symbol: 0.0 for symbol in values}
        return {
            symbol: float((rank - 0.5) * 2.0)
            for symbol, rank in ranks.items()
        }

    @staticmethod
    def _apply_factor_direction(
        values: dict[str, float],
        factor: str,
        steps: list[str],
    ) -> dict[str, float]:
        """Flip sign for factors where higher raw value is worse (e.g. volatility)."""
        from quant.factors.price.factor_registry import FactorRegistry

        meta = FactorRegistry().metadata(factor)
        if meta.get("higher_is_better", True):
            return values
        steps.append("direction_adjusted")
        return {symbol: -value for symbol, value in values.items()}

    @staticmethod
    def _summary(values: Mapping[str, float | None]) -> dict[str, float | int | None]:
        series = pd.Series(
            [value for value in values.values() if value is not None and not pd.isna(value)],
            dtype="float64",
        )
        missing_count = sum(1 for value in values.values() if value is None or pd.isna(value))
        if series.empty:
            return {
                "count": 0,
                "missing_count": missing_count,
                "mean": None,
                "std": None,
                "min": None,
                "max": None,
            }
        return {
            "count": int(series.count()),
            "missing_count": missing_count,
            "mean": float(series.mean()),
            "std": float(series.std()) if len(series) > 1 else None,
            "min": float(series.min()),
            "max": float(series.max()),
        }

    @staticmethod
    def _to_float(value: float | int | None) -> float | None:
        if value is None or pd.isna(value):
            return None
        return float(value)

    @staticmethod
    def normalize_config(config: Mapping) -> dict:
        merged = json.loads(json.dumps(DEFAULT_FACTOR_PIPELINE_CONFIG))
        merged.update(dict(config))
        merged["missing"] = str(merged.get("missing", "drop")).lower()
        if merged["missing"] not in {"drop", "fill"}:
            raise ValueError("factor pipeline missing must be one of: drop, fill")
        merged["fill_value"] = float(merged.get("fill_value", 0.0))

        winsor = dict(DEFAULT_FACTOR_PIPELINE_CONFIG["winsorization"])
        winsor.update(dict(merged.get("winsorization", {})))
        winsor["enabled"] = bool(winsor.get("enabled", True))
        winsor["lower_quantile"] = float(winsor["lower_quantile"])
        winsor["upper_quantile"] = float(winsor["upper_quantile"])
        if not 0 <= winsor["lower_quantile"] <= winsor["upper_quantile"] <= 1:
            raise ValueError("winsorization quantiles must satisfy 0 <= lower <= upper <= 1")
        merged["winsorization"] = winsor

        merged["zscore"] = bool(merged.get("zscore", True))
        merged["rank_normalization"] = bool(merged.get("rank_normalization", False))

        sector = dict(DEFAULT_FACTOR_PIPELINE_CONFIG["sector_neutralization"])
        sector.update(dict(merged.get("sector_neutralization", {})))
        sector["enabled"] = bool(sector.get("enabled", False))
        sector["sector_map"] = {
            str(symbol).upper().strip(): str(industry)
            for symbol, industry in dict(sector.get("sector_map", {})).items()
        }
        merged["sector_neutralization"] = sector

        market_beta = dict(DEFAULT_FACTOR_PIPELINE_CONFIG["market_beta_neutralization"])
        market_beta.update(dict(merged.get("market_beta_neutralization", {})))
        market_beta["enabled"] = bool(market_beta.get("enabled", False))
        merged["market_beta_neutralization"] = market_beta
        return merged

    def _write_report(self, result: FactorPipelineResult) -> Path:
        return write_json_report(
            generate_report_path(self.report_dir, "factor_pipeline", timestamp_format="%Y%m%d_%H%M%S_%f"),
            result.to_report(),
        )
