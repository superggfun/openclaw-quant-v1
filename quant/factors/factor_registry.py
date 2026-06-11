"""Central registry for deterministic no-lookahead factor definitions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import pandas as pd

from quant.factors.growth_factors import growth_score
from quant.factors.low_volatility_factors import low_volatility_score
from quant.factors.quality_factors import quality_score
from quant.factors.reversal_factors import reversal_5d, reversal_20d
from quant.factors.value_factors import value_score

FactorFunction = Callable[[pd.Series], float | None]


@dataclass(frozen=True)
class FactorDefinition:
    name: str
    category: str
    description: str
    required_inputs: list[str]
    lookback_days: int
    factor_type: str
    higher_is_better: bool
    no_lookahead: bool
    compute: FactorFunction


def _clean_closes(closes: pd.Series) -> pd.Series:
    return pd.to_numeric(closes, errors="coerce").dropna()


def _momentum_20d(closes: pd.Series) -> float | None:
    closes = _clean_closes(closes)
    if len(closes) <= 20:
        return None
    return float((closes.iloc[-1] / closes.iloc[-21]) - 1.0)


def _momentum_60d(closes: pd.Series) -> float | None:
    closes = _clean_closes(closes)
    if len(closes) <= 60:
        return None
    return float((closes.iloc[-1] / closes.iloc[-61]) - 1.0)


def _volatility_20d(closes: pd.Series) -> float | None:
    closes = _clean_closes(closes)
    returns = closes.pct_change().dropna().tail(20)
    if len(returns) < 20:
        return None
    volatility = float(returns.std())
    return volatility if volatility > 0 else None


def _risk_adjusted_momentum(closes: pd.Series) -> float | None:
    momentum = _momentum_60d(closes)
    volatility = _volatility_20d(closes)
    if momentum is None or volatility is None or volatility <= 0:
        return None
    return momentum / volatility


class FactorRegistry:
    """Resolve factor metadata and price-only computations."""

    def __init__(self) -> None:
        self._definitions = self._build_definitions()

    def list_factors(self) -> list[FactorDefinition]:
        return [self._definitions[name] for name in sorted(self._definitions)]

    def factor_names(self) -> list[str]:
        return [definition.name for definition in self.list_factors()]

    def describe(self, factor: str) -> FactorDefinition:
        name = self._normalize(factor)
        if name not in self._definitions:
            raise ValueError(f"unsupported factor: {factor}")
        return self._definitions[name]

    def resolve(self, factor: str) -> FactorFunction:
        return self.describe(factor).compute

    def factor_value(self, closes: pd.Series, factor: str) -> float | None:
        return self.resolve(factor)(closes)

    def metadata(self, factor: str) -> dict:
        definition = self.describe(factor)
        return {
            "factor_category": definition.category,
            "factor_family": definition.category,
            "factor_type": definition.factor_type,
            "factor_description": definition.description,
            "factor_inputs": definition.required_inputs,
            "lookback_days": definition.lookback_days,
            "higher_is_better": definition.higher_is_better,
            "no_lookahead": definition.no_lookahead,
        }

    @staticmethod
    def _normalize(factor: str) -> str:
        return str(factor).strip().lower()

    @staticmethod
    def _build_definitions() -> dict[str, FactorDefinition]:
        definitions = [
            FactorDefinition(
                name="momentum_20d",
                category="momentum",
                description="20-day close-to-close price momentum.",
                required_inputs=["close"],
                lookback_days=20,
                factor_type="price_momentum",
                higher_is_better=True,
                no_lookahead=True,
                compute=_momentum_20d,
            ),
            FactorDefinition(
                name="momentum_60d",
                category="momentum",
                description="60-day close-to-close price momentum.",
                required_inputs=["close"],
                lookback_days=60,
                factor_type="price_momentum",
                higher_is_better=True,
                no_lookahead=True,
                compute=_momentum_60d,
            ),
            FactorDefinition(
                name="volatility_20d",
                category="risk",
                description="20-day realized close-to-close volatility.",
                required_inputs=["close"],
                lookback_days=20,
                factor_type="realized_volatility",
                higher_is_better=False,
                no_lookahead=True,
                compute=_volatility_20d,
            ),
            FactorDefinition(
                name="risk_adjusted_momentum",
                category="momentum",
                description="60-day momentum divided by 20-day realized volatility.",
                required_inputs=["close"],
                lookback_days=60,
                factor_type="risk_adjusted_price_momentum",
                higher_is_better=True,
                no_lookahead=True,
                compute=_risk_adjusted_momentum,
            ),
            FactorDefinition(
                name="value_score",
                category="value",
                description="Price-only value proxy that favors long-term relative underperformance.",
                required_inputs=["close"],
                lookback_days=120,
                factor_type="price_proxy",
                higher_is_better=True,
                no_lookahead=True,
                compute=value_score,
            ),
            FactorDefinition(
                name="quality_score",
                category="quality",
                description="Price-only quality proxy using consistency, volatility, and drawdown resistance.",
                required_inputs=["close"],
                lookback_days=60,
                factor_type="price_proxy",
                higher_is_better=True,
                no_lookahead=True,
                compute=quality_score,
            ),
            FactorDefinition(
                name="growth_score",
                category="growth",
                description="Price-only growth proxy using multi-horizon trend persistence.",
                required_inputs=["close"],
                lookback_days=60,
                factor_type="price_proxy",
                higher_is_better=True,
                no_lookahead=True,
                compute=growth_score,
            ),
            FactorDefinition(
                name="reversal_5d",
                category="reversal",
                description="5-day mean-reversion score; recent underperformance ranks higher.",
                required_inputs=["close"],
                lookback_days=5,
                factor_type="mean_reversion",
                higher_is_better=True,
                no_lookahead=True,
                compute=reversal_5d,
            ),
            FactorDefinition(
                name="reversal_20d",
                category="reversal",
                description="20-day mean-reversion score; recent underperformance ranks higher.",
                required_inputs=["close"],
                lookback_days=20,
                factor_type="mean_reversion",
                higher_is_better=True,
                no_lookahead=True,
                compute=reversal_20d,
            ),
            FactorDefinition(
                name="low_volatility_score",
                category="low_volatility",
                description="Low-volatility score based on negative 20-day realized volatility.",
                required_inputs=["close"],
                lookback_days=20,
                factor_type="risk_proxy",
                higher_is_better=True,
                no_lookahead=True,
                compute=low_volatility_score,
            ),
        ]
        return {definition.name: definition for definition in definitions}
