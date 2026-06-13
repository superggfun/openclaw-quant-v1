"""Alpha scoring, ranking, and target-weight computation."""

from __future__ import annotations

from dataclasses import replace
from typing import Mapping

import pandas as pd

from quant.factors.price.factor_registry import FactorRegistry
from quant.engines.alpha.models import AlphaFactorRow


def copy_alpha_row(row: AlphaFactorRow, **kwargs) -> AlphaFactorRow:
    """Create a copy of row with optional fields overridden."""
    return replace(row, **kwargs)


def row_factor_value(row: AlphaFactorRow, factor: str) -> float | None:
    """Return the factor value for a row by factor name."""
    if factor == "momentum_20d":
        return row.momentum_20d
    if factor == "momentum_60d":
        return row.momentum_60d
    if factor == "volatility_20d":
        return row.volatility_20d
    if factor == "risk_adjusted_momentum":
        return row.risk_adjusted_momentum
    if factor == "composite_alpha_score":
        return row.composite_alpha_score
    if factor == "multi_factor_alpha":
        return row.composite_alpha_score
    if row.factor_values and factor in row.factor_values:
        return row.factor_values[factor]
    valid = sorted(FactorRegistry().factor_names() + ["composite_alpha_score", "multi_factor_alpha"])
    raise ValueError(f"pipeline factor must be one of: {', '.join(valid)}")


def apply_composite_scores(
    rows: list[AlphaFactorRow],
    factor_weights: dict[str, float],
    warnings: list[str],
) -> tuple[list[AlphaFactorRow], dict[str, float]]:
    """Apply weighted composite factor scores to rows."""
    valid_rows = [row for row in rows if not row.excluded]
    normalized_scores_by_factor: dict[str, dict[str, float]] = {}
    for factor in factor_weights:
        raw_values = {
            row.symbol: (row.factor_values or {}).get(factor)
            for row in valid_rows
        }
        clean_values = {
            symbol: float(value)
            for symbol, value in raw_values.items()
            if value is not None and pd.notna(value)
        }
        if not clean_values:
            warnings.append(f"composite factor {factor} has no valid values")
            normalized_scores_by_factor[factor] = {}
            continue
        missing_symbols = sorted(set(raw_values) - set(clean_values))
        if missing_symbols and FactorRegistry().metadata(factor).get("data_source") == "fundamental":
            warnings.append(
                f"PARTIAL_FUNDAMENTAL_DATA: {factor} missing for {', '.join(missing_symbols[:5])}"
            )
        series = pd.Series(clean_values, dtype="float64").sort_index()
        if len(series) == 1 or float(series.std()) == 0:
            normalized_scores_by_factor[factor] = {symbol: 1.0 for symbol in series.index}
        else:
            ranks = series.rank(method="average", pct=True)
            normalized_scores_by_factor[factor] = {
                str(symbol): float(value)
                for symbol, value in ranks.items()
            }

    updated_rows: list[AlphaFactorRow] = []
    composite_score_by_symbol: dict[str, float] = {}
    for row in rows:
        contributions = {}
        composite_score = 0.0
        has_signal = False
        if not row.excluded:
            for factor, weight in factor_weights.items():
                normalized_score = normalized_scores_by_factor.get(factor, {}).get(row.symbol)
                if normalized_score is None:
                    contributions[factor] = 0.0
                    continue
                contribution = float(weight) * float(normalized_score)
                contributions[factor] = contribution
                composite_score += contribution
                has_signal = True
        excluded = row.excluded or not has_signal
        reason = row.exclusion_reason
        if not row.excluded and not has_signal:
            reason = "no valid composite alpha factors"
            warnings.append(f"excluded {row.symbol}: {reason}")
        final_score = composite_score if has_signal else None
        if final_score is not None:
            composite_score_by_symbol[row.symbol] = final_score
        updated_rows.append(
            copy_alpha_row(
                row,
                excluded=excluded,
                exclusion_reason=reason,
                factor_contributions=contributions if contributions else None,
                composite_alpha_score=final_score,
            )
        )
    return updated_rows, composite_score_by_symbol


def rank_alpha_rows(
    rows: list[AlphaFactorRow],
    ranking_factor: str = "risk_adjusted_momentum",
    score_by_symbol: dict[str, float] | None = None,
) -> list[AlphaFactorRow]:
    """Rank rows by factor score descending."""
    valid = sorted(
        [
            row
            for row in rows
            if not row.excluded
            and get_ranking_score(row, ranking_factor, score_by_symbol) is not None
        ],
        key=lambda r: (get_ranking_score(r, ranking_factor, score_by_symbol), r.symbol),
        reverse=True,
    )
    rank_by_symbol = {row.symbol: rank for rank, row in enumerate(valid, start=1)}
    return [
        copy_alpha_row(
            row,
            rank=rank_by_symbol.get(row.symbol),
            selected=False,
        )
        for row in rows
    ]


def get_ranking_score(
    row: AlphaFactorRow,
    ranking_factor: str,
    score_by_symbol: dict[str, float] | None = None,
) -> float | None:
    """Get the ranking score for a row."""
    if score_by_symbol is not None:
        return score_by_symbol.get(row.symbol)
    return row_factor_value(row, ranking_factor)


def mark_selected(rows: list[AlphaFactorRow], selected_symbols: list[str]) -> list[AlphaFactorRow]:
    """Mark rows as selected if their symbol is in the selected set."""
    selected = set(selected_symbols)
    return [
        copy_alpha_row(row, selected=row.symbol in selected)
        for row in rows
    ]


def compute_target_weights(
    selected_rows: list[AlphaFactorRow],
    weighting_mode: str,
    min_cash_weight: float,
    max_position_weight: float,
    warnings: list[str],
    score_by_symbol: dict[str, float] | None = None,
) -> dict[str, float]:
    """Compute target weights for selected symbols."""
    investable_weight = max(1.0 - min_cash_weight, 0.0)
    if weighting_mode == "equal_weight":
        raw_weights = {
            row.symbol: investable_weight / len(selected_rows)
            for row in selected_rows
        }
    else:
        positive_scores = {
            row.symbol: max(
                (
                    score_by_symbol.get(row.symbol)
                    if score_by_symbol is not None
                    else (
                        row.composite_alpha_score
                        if row.composite_alpha_score is not None
                        else row.risk_adjusted_momentum
                    )
                )
                or 0.0,
                0.0,
            )
            for row in selected_rows
        }
        total_score = sum(positive_scores.values())
        if total_score <= 0:
            warnings.append("score_weighted fallback to equal_weight because selected scores are not positive")
            raw_weights = {
                row.symbol: investable_weight / len(selected_rows)
                for row in selected_rows
            }
        else:
            raw_weights = {
                symbol: (score / total_score) * investable_weight
                for symbol, score in positive_scores.items()
            }

    capped_weights = {}
    for symbol, weight in raw_weights.items():
        capped = min(weight, max_position_weight)
        if capped < weight:
            warnings.append(f"capped {symbol} to max_position_weight {max_position_weight:.4f}")
        capped_weights[symbol] = capped

    targets = round_targets(capped_weights, min_cash_weight)
    return targets


def round_targets(raw_weights: dict[str, float], min_cash_weight: float) -> dict[str, float]:
    """Round target weights and add cash allocation."""
    targets = {
        symbol: round(weight, 6)
        for symbol, weight in sorted(raw_weights.items())
        if weight > 0
    }
    cash_weight = max(min_cash_weight, 1.0 - sum(targets.values()))
    targets["cash"] = round(cash_weight, 6)
    total = round(sum(targets.values()), 6)
    if total != 1.0:
        targets["cash"] = round(targets["cash"] + (1.0 - total), 6)
    return targets


def validate_targets(targets: dict[str, float], config: dict) -> None:
    """Validate target weights satisfy constraints."""
    total_weight = round(sum(targets.values()), 6)
    if abs(total_weight - 1.0) > 1e-6:
        raise ValueError("alpha target weights must sum to 1.0")
    if targets.get("cash", 0.0) + 1e-6 < config["min_cash_weight"]:
        raise ValueError("alpha cash target is below min_cash_weight")
    for symbol, weight in targets.items():
        if symbol != "cash" and weight > config["max_position_weight"] + 1e-12:
            raise ValueError(f"alpha target for {symbol} exceeds max_position_weight")
