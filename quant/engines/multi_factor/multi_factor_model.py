"""Formal multi-factor model for price and fundamental factor combination."""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping

import numpy as np

from quant.factors.price.factor_registry import FactorRegistry
from quant.engines.multi_factor.factor_combiner import FactorCombiner
from quant.engines.multi_factor.factor_stability import FactorStability
from quant.engines.multi_factor.factor_weighting import FactorWeighting
from quant.reports.report_io import generate_report_path, write_json_report


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
    collinearity: dict[str, Any]
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
            "collinearity": self.collinearity,
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
        min_confidence: float = 0.0,
    ) -> MultiFactorResult:
        cfg = self.normalize_config(config or {}, self.factor_registry)
        factors = cfg["factors"]
        raw = {
            str(symbol).upper(): {
                str(factor_key).strip().lower(): value
                for factor_key, value in (values or {}).items()
            }
            for symbol, values in raw_factor_values.items()
        }
        symbols = sorted(raw)
        warnings: list[str] = []
        factor_families = {factor: self.factor_family(factor, self.factor_registry) for factor in factors}
        coverage = {
            factor: self._coverage(raw, factor, symbols)
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
                symbol: raw.get(symbol, {}).get(factor)
                for symbol in symbols
            }
            meta = self.factor_registry.metadata(factor)
            normalized = FactorCombiner.normalize(
                raw_values,
                method=cfg["normalization_method"],
                winsorize_pct=cfg.get("winsorize_pct"),
                missing=cfg["missing"],
                higher_is_better=meta.get("higher_is_better", True),
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

        # P0: Factor collinearity analysis
        collinearity_warnings, factor_correlations = self._analyze_collinearity(
            normalized_by_factor, factor_families, factors, symbols
        )
        warnings.extend(collinearity_warnings)

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
            if final_score is not None and overall_confidence < min_confidence:
                final_score = None
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
            collinearity={
                "factor_correlations": factor_correlations,
                "warnings": collinearity_warnings,
                "methodology": "Pearson correlation across symbol-normalized factor values; |r| > 0.7 flagged",
            },
            scores=scores,
            warnings=warnings,
            report_path="",
        )
        path = self._write_report(result) if write_report else ""
        return replace(result, report_path=str(path))

    @staticmethod
    def normalize_config(config: Mapping, registry: FactorRegistry | None = None) -> dict[str, Any]:
        cfg = dict(config)
        registry = registry or FactorRegistry()
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
        if "min_confidence" not in normalized:
            normalized["min_confidence"] = float(cfg.get("min_confidence", 0.0))
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
    def _analyze_collinearity(
        normalized_by_factor, factor_families, factors, symbols,
    ):
        warnings_list = []
        correlations = {}
        # Build factor->symbol mapping from normalized_by_factor (factor->symbol->value)
        factor_by_symbol: dict[str, dict[str, float]] = {}
        for factor in factors:
            factor_values = normalized_by_factor.get(factor, {})
            factor_by_symbol[factor] = {sym: factor_values.get(sym) for sym in symbols}
        factor_list = [f for f in factors if f in factor_by_symbol]
        if len(factor_list) < 2:
            return warnings_list, correlations
        for i, f1 in enumerate(factor_list):
            correlations[f1] = {}
            vals1 = [factor_by_symbol[f1].get(s) for s in symbols]
            for j, f2 in enumerate(factor_list):
                if i >= j:
                    continue
                vals2 = [factor_by_symbol[f2].get(s) for s in symbols]
                paired = [(v1, v2) for v1, v2 in zip(vals1, vals2) if v1 is not None and v2 is not None]
                if len(paired) < 5:
                    correlations[f1][f2] = None
                    continue
                a = np.array([p[0] for p in paired])
                b = np.array([p[1] for p in paired])
                if np.std(a) < 1e-12 or np.std(b) < 1e-12:
                    correlations[f1][f2] = None
                    continue
                r = float(np.corrcoef(a, b)[0, 1])
                correlations[f1][f2] = round(r, 6)
                family1 = factor_families.get(f1, "UNKNOWN")
                family2 = factor_families.get(f2, "UNKNOWN")
                if family1 == family2 and abs(r) > 0.70:
                    warnings_list.append(
                        f"COLLINEARITY: {f1} and {f2} (both {family1}) "
                        f"correlated at r={r:.3f}"
                    )
                elif abs(r) > 0.85:
                    warnings_list.append(
                        f"COLLINEARITY: {f1} ({family1}) and {f2} ({family2}) "
                        f"highly correlated at r={r:.3f}"
                    )
        return warnings_list, correlations

    @staticmethod
    def _coverage(raw_factor_values: Mapping[str, Mapping[str, float | None]], factor: str, symbols: list[str]) -> float:
        if not symbols:
            return 0.0
        valid = 0
        for symbol in symbols:
            value = (raw_factor_values.get(symbol) or {}).get(factor)
            try:
                if value is not None:
                    fv = float(value)
                    if math.isfinite(fv):
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
        return write_json_report(
            generate_report_path(self.report_dir, "multi_factor"),
            result.to_report(),
        )
