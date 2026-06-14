"""Factor preprocessing and cross-sectional combination helpers."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Mapping

import pandas as pd


@dataclass(frozen=True)
class NormalizationResult:
    values: dict[str, float]
    excluded_symbols: list[str]
    missing_symbols: list[str]
    warnings: list[str]


class FactorCombiner:
    """Normalize cross-sectional factor values before weighted combination."""

    @staticmethod
    def normalize(
        raw_values: Mapping[str, float | None],
        method: str = "rank",
        winsorize_pct: float | None = None,
        missing: str = "drop",
        **kwargs,
    ) -> NormalizationResult:
        method = method.strip().lower()
        missing = missing.strip().lower()
        if method not in {"rank", "zscore"}:
            raise ValueError("normalization method must be one of: rank, zscore")
        if missing not in {"drop", "neutral"}:
            raise ValueError("missing handling must be one of: drop, neutral")
        # Default True so existing callers (including external) are unaffected.
        higher_is_better = kwargs.get("higher_is_better", True)

        warnings: list[str] = []
        clean = {
            str(symbol).upper(): float(value)
            for symbol, value in raw_values.items()
            if FactorCombiner._finite(value)
        }
        missing_symbols = sorted(str(symbol).upper() for symbol in raw_values if str(symbol).upper() not in clean)
        if not clean:
            return NormalizationResult({}, sorted(missing_symbols), sorted(missing_symbols), ["no finite factor values"])

        series = pd.Series(clean, dtype="float64").sort_index()
        if winsorize_pct is not None and winsorize_pct > 0 and len(series) > 1:
            pct = min(max(float(winsorize_pct), 0.0), 0.49)
            lower = float(series.quantile(pct))
            upper = float(series.quantile(1.0 - pct))
            series = series.clip(lower=lower, upper=upper)

        if len(series) == 1 or float(series.std(ddof=0)) == 0.0:
            normalized = {str(symbol): 0.5 for symbol in series.index}
        elif method == "rank":
            rank = series.rank(method="average")
            if len(series) > 1:
                scores = (rank - 1.0) / (len(series) - 1.0)
            else:
                scores = pd.Series(0.5, index=series.index)
            if not higher_is_better:
                scores = 1.0 - scores
            normalized = {str(symbol): float(value) for symbol, value in scores.items()}
        else:
            zscores = (series - float(series.mean())) / float(series.std(ddof=0))
            if not higher_is_better:
                zscores = -zscores
            normalized = {str(symbol): float(value) for symbol, value in zscores.items()}

        if missing == "neutral":
            neutral = 0.5 if method == "rank" else 0.0
            for symbol in missing_symbols:
                normalized[symbol] = neutral
        elif missing_symbols:
            warnings.append(f"missing factor values for {', '.join(missing_symbols[:5])}")

        return NormalizationResult(
            values=dict(sorted(normalized.items())),
            excluded_symbols=[] if missing == "neutral" else missing_symbols,
            missing_symbols=missing_symbols,
            warnings=warnings,
        )

    @staticmethod
    def _finite(value) -> bool:
        try:
            number = float(value)
            return math.isfinite(number)
        except (TypeError, ValueError):
            return False
