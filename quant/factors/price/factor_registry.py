"""Registry for deterministic no-lookahead factor definitions."""

from __future__ import annotations

import pandas as pd

from quant.data.fundamental.fundamental_store import FundamentalStore
from quant.factors.registry import FACTOR_DEFINITIONS
from quant.factors.specs import FactorDefinition, FactorFunction


class FactorRegistry:
    """Resolve factor metadata and deterministic no-lookahead computations."""

    def __init__(self, fundamental_store: FundamentalStore | None = None) -> None:
        self.fundamental_store = fundamental_store
        self._fundamental_rows_cache: dict[tuple[str, str], list[dict]] = {}
        self._definitions = dict(FACTOR_DEFINITIONS)

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

    def factor_value(
        self,
        closes: pd.Series,
        factor: str,
        symbol: str | None = None,
        as_of_date: str | None = None,
    ) -> float | None:
        definition = self.describe(factor)
        if definition.data_source == "fundamental":
            return self._fundamental_value(definition, symbol=symbol, as_of_date=as_of_date)
        # Enforce no-lookahead for price factors: slice to as_of_date before computing
        if as_of_date is not None and isinstance(closes.index, pd.DatetimeIndex):
            closes = closes.loc[:pd.Timestamp(as_of_date)]
        return definition.compute(closes)

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
            "data_source": definition.data_source,
            "fundamental_data_required": definition.fundamental_data_required,
            "fundamental_statement": definition.fundamental_statement,
            "fundamental_metrics_used": definition.fundamental_metrics_used or [],
        }

    def is_fundamental(self, factor: str) -> bool:
        return self.describe(factor).data_source == "fundamental"

    def _fundamental_value(
        self,
        definition: FactorDefinition,
        symbol: str | None,
        as_of_date: str | None,
    ) -> float | None:
        if self.fundamental_store is None or symbol is None or as_of_date is None:
            return None
        statement = definition.fundamental_statement or "fundamental_metrics"
        row = self.latest_fundamental_row(symbol, statement, as_of_date)
        if not row:
            return None
        # Double-check: the returned row must not be after as_of_date
        raw = row.get("report_date")
        if raw is not None:
            try:
                report_date = pd.Timestamp(raw)
                if report_date > pd.Timestamp(as_of_date):
                    return None
            except (ValueError, TypeError):
                pass
        return definition.compute(row)

    def latest_fundamental_row(self, symbol: str, statement: str, as_of_date: str) -> dict | None:
        if self.fundamental_store is None:
            return None
        if hasattr(self.fundamental_store, "latest_as_of"):
            return self.fundamental_store.latest_as_of(symbol, statement, as_of_date)
        key = (statement, symbol.upper())
        if key not in self._fundamental_rows_cache:
            rows = self.fundamental_store.rows(statement, [symbol])
            self._fundamental_rows_cache[key] = sorted(
                [row for row in rows if row.get("report_date")],
                key=lambda row: (str(row.get("report_date") or ""), str(row.get("fiscal_period_end") or "")),
                reverse=True,
            )
        cutoff = pd.Timestamp(as_of_date)
        for row in self._fundamental_rows_cache[key]:
            raw = row.get("report_date")
            if raw is None:
                continue
            try:
                report_date = pd.Timestamp(raw)
            except (ValueError, TypeError):
                continue
            if report_date <= cutoff:
                return row
        return None

    @staticmethod
    def _normalize(factor: str) -> str:
        return str(factor).strip().lower()


__all__ = ["FactorDefinition", "FactorFunction", "FactorRegistry"]
