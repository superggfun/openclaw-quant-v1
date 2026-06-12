"""Formal multi-factor model for price and fundamental factor combination."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping

from quant.factors.factor_registry import FactorRegistry
from quant.multi_factor.factor_combiner import FactorCombiner
from quant.multi_factor.factor_stability import FactorStability
from quant.multi_factor.factor_weighting import FactorWeighting


DEFAULT_MULTI_FACTOR_FACTORS = [
    "momentum_60d",
    "risk_adjusted_momentum",
    "low_volatility_score",
    "fundamental_value_score",
    "fundamental_quality_score",
    "fundamental_growth_score",
    "fundamental_health_score",
]

DEFAULT_FAMILY_WEIGHTS = {
    "PRICE": 0.25,
    "VALUE": 0.20,
    "QUALITY": 0.20,
    "GROWTH": 0.15,
    "HEALTH": 0.10,
    "LOW_VOL": 0.05,
    "REVERSAL": 0.05,
}


@dataclass(frozen=True)
class MultiFactorSymbolScore:
    symbol: str
    factor_scores: dict[str, float | None]
    factor_contributions: dict[str, float]
    family_scores: dict[str, float]
    family_contributions: dict[str, float]
    final_alpha_score: float | None
    factor_confidence: dict[str, float]
    overall_confidence: float


@dataclass(frozen=True)
class MultiFactorResult:
    as_of_date: str | None
    factors: list[str]
    factor_families: dict[str, str]
    weighting_mode: str
    normalization: dict[str, Any]
    factor_weights: dict[str, float]
    factor_weights_by_family: dict[str, dict[str, float]]
    family_weights: dict[str, float]
    coverage: dict[str, float]
    confidence: dict[str, Any]
    stability: dict[str, Any]
    scores: list[MultiFactorSymbolScore]
    warnings: list[str]
    report_path: str

    def to_report(self) -> dict[str, Any]:
        return {
            "metadata": {
                "report_type": "multi_factor",
                "created_at": datetime.now().isoformat(timespec="seconds"),
                "no_lookahead": True,
            },
            "as_of_date": self.as_of_date,
            "factors": self.factors,
            "factor_families": self.factor_families,
            "weighting_mode": self.weighting_mode,
            "normalization": self.normalization,
            "factor_weights": self.factor_weights,
            "factor_weights_by_family": self.factor_weights_by_family,
            "family_weights": self.family_weights,
            "coverage": self.coverage,
            "confidence": self.confidence,
            "stability": self.stability,
            "scores": [asdict(score) for score in self.scores],
            "warnings": self.warnings,
        }


class MultiFactorModel:
    """Combine normalized factors into one coverage-aware alpha score."""

    def __init__(
        self,
        factor_registry: FactorRegistry | None = None,
        report_dir: str | Path = "reports",
    ) -> None:
        self.factor_registry = factor_registry or FactorRegistry()
        self.report_dir = Path(report_dir)

    def run(
        self,
        raw_factor_values: Mapping[str, Mapping[str, float | None]],
        config: Mapping | None = None,
        as_of_date: str | None = None,
        write_report: bool = True,
    ) -> MultiFactorResult:
        cfg = self.normalize_config(config or {})
        factors = cfg["factors"]
        symbols = sorted(str(symbol).upper() for symbol in raw_factor_values)
        warnings: list[str] = []
        factor_families = {factor: self.factor_family(factor, self.factor_registry) for factor in factors}
        coverage = {
            factor: self._coverage(raw_factor_values, factor, symbols)
            for factor in factors
        }
        factor_weights, weight_warnings = FactorWeighting.weights(
            factors=factors,
            mode=cfg["weighting_mode"],
            custom_weights=cfg.get("factor_weights"),
            ic_metrics=cfg.get("ic_metrics"),
            stability_scores=cfg.get("stability_scores"),
            coverage=coverage,
        )
        warnings.extend(weight_warnings)

        family_weights = self._family_weights(cfg.get("family_weights"), factor_families)
        normalized_by_factor: dict[str, dict[str, float]] = {}
        confidence_by_factor: dict[str, float] = {}
        stability_by_factor: dict[str, dict[str, Any]] = {}
        for factor in factors:
            raw_values = {
                symbol: (raw_factor_values.get(symbol) or {}).get(factor)
                for symbol in symbols
            }
            normalized = FactorCombiner.normalize(
                raw_values,
                method=cfg["normalization_method"],
                winsorize_pct=cfg.get("winsorize_pct"),
                missing=cfg["missing"],
            )
            normalized_by_factor[factor] = normalized.values
            warnings.extend(f"{factor}: {warning}" for warning in normalized.warnings)
            if coverage[factor] < cfg["low_coverage_threshold"]:
                warnings.append(f"LOW_FACTOR_COVERAGE: {factor} coverage {coverage[factor]:.2%}")
            stability_score = FactorStability.score(
                ic_history=(cfg.get("ic_history") or {}).get(factor),
                rank_ic_history=(cfg.get("rank_ic_history") or {}).get(factor),
                decay=(cfg.get("factor_decay") or {}).get(factor),
                walk_forward_score=(cfg.get("stability_scores") or {}).get(factor),
                coverage=coverage[factor],
            )
            stability_by_factor[factor] = {
                "score": stability_score,
                "classification": FactorStability.label(stability_score),
            }
            confidence_by_factor[factor] = round(coverage[factor] * stability_score, 6)

        scores: list[MultiFactorSymbolScore] = []
        for symbol in symbols:
            factor_contributions = {}
            family_scores: dict[str, float] = {}
            family_weight_totals: dict[str, float] = {}
            for factor in factors:
                normalized_score = normalized_by_factor.get(factor, {}).get(symbol)
                if normalized_score is None:
                    continue
                factor_weight = factor_weights[factor]
                family = factor_families[factor]
                factor_contributions[factor] = round(float(normalized_score) * factor_weight, 12)
                family_scores[family] = family_scores.get(family, 0.0) + float(normalized_score) * factor_weight
                family_weight_totals[family] = family_weight_totals.get(family, 0.0) + factor_weight
            family_scores = {
                family: (score / family_weight_totals[family])
                for family, score in family_scores.items()
                if family_weight_totals.get(family, 0.0) > 0
            }
            family_contributions = {
                family: round(score * family_weights.get(family, 0.0), 12)
                for family, score in sorted(family_scores.items())
            }
            final_score = sum(family_contributions.values()) if family_contributions else None
            symbol_factor_confidence = {
                factor: confidence_by_factor[factor]
                for factor in factors
                if symbol in normalized_by_factor.get(factor, {})
            }
            overall_confidence = (
                sum(symbol_factor_confidence.values()) / len(symbol_factor_confidence)
                if symbol_factor_confidence
                else 0.0
            )
            scores.append(
                MultiFactorSymbolScore(
                    symbol=symbol,
                    factor_scores={
                        factor: normalized_by_factor.get(factor, {}).get(symbol)
                        for factor in factors
                    },
                    factor_contributions=dict(sorted(factor_contributions.items())),
                    family_scores=dict(sorted(family_scores.items())),
                    family_contributions=dict(sorted(family_contributions.items())),
                    final_alpha_score=round(final_score, 12) if final_score is not None else None,
                    factor_confidence=dict(sorted(symbol_factor_confidence.items())),
                    overall_confidence=round(overall_confidence, 6),
                )
            )

        overall_confidence = self._overall_confidence(scores)
        result = MultiFactorResult(
            as_of_date=as_of_date,
            factors=factors,
            factor_families=factor_families,
            weighting_mode=cfg["weighting_mode"],
            normalization={
                "method": cfg["normalization_method"],
                "winsorize_pct": cfg.get("winsorize_pct"),
                "missing": cfg["missing"],
            },
            factor_weights=factor_weights,
            factor_weights_by_family=self._factor_weights_by_family(factor_weights, factor_families),
            family_weights=family_weights,
            coverage=coverage,
            confidence={
                "factor_confidence": confidence_by_factor,
                "overall_confidence": overall_confidence,
            },
            stability=stability_by_factor,
            scores=scores,
            warnings=warnings,
            report_path="",
        )
        path = self._write_report(result) if write_report else ""
        return MultiFactorResult(
            as_of_date=result.as_of_date,
            factors=result.factors,
            factor_families=result.factor_families,
            weighting_mode=result.weighting_mode,
            normalization=result.normalization,
            factor_weights=result.factor_weights,
            factor_weights_by_family=result.factor_weights_by_family,
            family_weights=result.family_weights,
            coverage=result.coverage,
            confidence=result.confidence,
            stability=result.stability,
            scores=result.scores,
            warnings=result.warnings,
            report_path=str(path),
        )

    @staticmethod
    def normalize_config(config: Mapping) -> dict[str, Any]:
        cfg = dict(config)
        registry = FactorRegistry()
        factors = [str(factor).strip().lower() for factor in (cfg.get("factors") or DEFAULT_MULTI_FACTOR_FACTORS)]
        for factor in factors:
            registry.describe(factor)
        weighting_mode = str(cfg.get("weighting_mode") or "equal_weight").strip().lower()
        normalization_method = str(cfg.get("normalization") or cfg.get("normalization_method") or "rank").strip().lower()
        missing = str(cfg.get("missing") or cfg.get("missing_handling") or "drop").strip().lower()
        normalized = {
            "factors": sorted(dict.fromkeys(factors)),
            "weighting_mode": weighting_mode,
            "normalization_method": normalization_method,
            "winsorize_pct": cfg.get("winsorize_pct"),
            "missing": missing,
            "factor_weights": cfg.get("factor_weights") or {},
            "family_weights": cfg.get("family_weights") or DEFAULT_FAMILY_WEIGHTS,
            "ic_metrics": cfg.get("ic_metrics") or {},
            "ic_history": cfg.get("ic_history") or {},
            "rank_ic_history": cfg.get("rank_ic_history") or {},
            "factor_decay": cfg.get("factor_decay") or {},
            "stability_scores": cfg.get("stability_scores") or {},
            "low_coverage_threshold": float(cfg.get("low_coverage_threshold", 0.8)),
        }
        FactorWeighting.weights(
            normalized["factors"],
            mode=weighting_mode,
            custom_weights=normalized["factor_weights"],
        )
        FactorCombiner.normalize({"CHECK": 1.0}, method=normalization_method, missing=missing)
        return normalized

    @staticmethod
    def factor_family(factor: str, registry: FactorRegistry | None = None) -> str:
        metadata = (registry or FactorRegistry()).metadata(factor)
        category = str(metadata.get("factor_category") or "").lower()
        factor_type = str(metadata.get("factor_type") or "").lower()
        if "fundamental_value" in category:
            return "VALUE"
        if "fundamental_quality" in category:
            return "QUALITY"
        if "fundamental_growth" in category:
            return "GROWTH"
        if "fundamental_health" in category:
            return "HEALTH"
        if "fundamental_composite" in category:
            return "QUALITY"
        if "low_volatility" in category:
            return "LOW_VOL"
        if "reversal" in category:
            return "REVERSAL"
        if "value" in category:
            return "VALUE"
        if "quality" in category:
            return "QUALITY"
        if "growth" in category:
            return "GROWTH"
        if "volatility" in category and "low" in factor:
            return "LOW_VOL"
        if "momentum" in category or "momentum" in factor_type or category == "risk":
            return "PRICE"
        return "PRICE"

    @staticmethod
    def _coverage(raw_factor_values: Mapping[str, Mapping[str, float | None]], factor: str, symbols: list[str]) -> float:
        if not symbols:
            return 0.0
        valid = 0
        for symbol in symbols:
            value = (raw_factor_values.get(symbol) or {}).get(factor)
            try:
                if value is not None and float(value) == float(value):
                    valid += 1
            except (TypeError, ValueError):
                pass
        return round(valid / len(symbols), 6)

    @staticmethod
    def _family_weights(raw_weights: Mapping[str, float] | None, factor_families: Mapping[str, str]) -> dict[str, float]:
        active_families = sorted(set(factor_families.values()))
        raw = {
            family: max(float((raw_weights or {}).get(family, 0.0)), 0.0)
            for family in active_families
        }
        if sum(raw.values()) <= 0:
            raw = {family: 1.0 for family in active_families}
        total = sum(raw.values())
        return {family: raw[family] / total for family in sorted(raw)}

    @staticmethod
    def _factor_weights_by_family(
        factor_weights: Mapping[str, float],
        factor_families: Mapping[str, str],
    ) -> dict[str, dict[str, float]]:
        grouped: dict[str, dict[str, float]] = {}
        for factor, weight in factor_weights.items():
            family = factor_families[factor]
            grouped.setdefault(family, {})[factor] = float(weight)
        output: dict[str, dict[str, float]] = {}
        for family, weights in grouped.items():
            total = sum(weights.values())
            if total <= 0:
                continue
            output[family] = {
                factor: weight / total
                for factor, weight in sorted(weights.items())
            }
        return dict(sorted(output.items()))

    @staticmethod
    def _overall_confidence(scores: list[MultiFactorSymbolScore]) -> float:
        if not scores:
            return 0.0
        return round(sum(score.overall_confidence for score in scores) / len(scores), 6)

    def _write_report(self, result: MultiFactorResult) -> Path:
        self.report_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = self.report_dir / f"multi_factor_{timestamp}.json"
        path.write_text(json.dumps(result.to_report(), indent=2), encoding="utf-8")
        return path
