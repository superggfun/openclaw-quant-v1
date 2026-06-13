"""Scope planning for research validation runs."""

from __future__ import annotations

import math
import os
from typing import Any

from quant.research_validation.config import (
    DEFAULT_FORWARD_DAYS,
    DEFAULT_HOLDING_PERIOD,
    QUICK_DEFAULT_START,
    QUICK_FACTOR_PRIORITY,
    QUICK_UNIVERSE,
)
from quant.strategy_dsl.strategy_registry import StrategyRegistry


class ResearchValidationScopePlanner:
    def __init__(self, context, factor_registry) -> None:
        self.context = context
        self.factor_registry = factor_registry

    def preview(
        self,
        mode: str = "quick",
        start: str | None = None,
        end: str | None = None,
        max_factors: int | None = None,
        max_strategies: int | None = None,
        max_folds: int | None = None,
        batch_size: int | None = None,
        max_symbols: int | None = None,
        factor_family: str = "all",
        parallel: bool = False,
        workers: int | None = None,
    ) -> dict[str, Any]:
        mode = mode.strip().lower()
        family = factor_family.strip().lower()
        worker_count = self.worker_count(parallel=parallel, workers=workers)
        factors = self.select_factors(mode, max_factors, family)
        strategies = self.select_strategies(mode, max_strategies)
        symbol_diagnostics = self.select_and_filter_symbols(mode, max_symbols, factors)
        universe = symbol_diagnostics["selected_symbols"]
        effective_start, effective_end = self.effective_date_range(mode, start, end, universe)
        if mode == "quick" and (effective_start is None or effective_end is None):
            raise ValueError("BLOCKED_UNBOUNDED_QUICK_VALIDATION: quick mode requires bounded start and end dates")
        effective_batch_size = self.effective_batch_size(
            symbol_count=len(universe),
            mode=mode,
            requested_batch_size=batch_size,
            parallel=parallel,
            workers=worker_count,
        )
        batches = self.symbol_batches(universe, effective_batch_size)
        trading_day_count = self.trading_day_count(universe, effective_start, effective_end)
        factor_count = len(factors)
        symbol_count = len(universe)
        return {
            "mode": mode,
            "start_date": start,
            "end_date": end,
            "effective_start_date": effective_start,
            "effective_end_date": effective_end,
            "frequency": "daily",
            "forward_days": DEFAULT_FORWARD_DAYS,
            "holding_period": DEFAULT_HOLDING_PERIOD,
            "trading_day_count": trading_day_count,
            "symbol_count": symbol_count,
            "factor_count": factor_count,
            "estimated_observation_count": trading_day_count * symbol_count * factor_count,
            "factors": factors,
            "strategies": strategies,
            "symbol_diagnostics": symbol_diagnostics,
            "universe": universe,
            "batch_size": effective_batch_size,
            "batch_count": len(batches),
            "batches": batches,
            "workers": worker_count,
            "expected_task_count": len(factors) * len(batches) * 2,
            "max_folds": max_folds if max_folds is not None else (1 if mode == "quick" else 5),
        }

    @staticmethod
    def worker_count(parallel: bool, workers: int | None = None) -> int:
        return max(1, int(workers or (min(16, os.cpu_count() or 1) if parallel else 1)))

    def select_factors(self, mode: str, max_factors: int | None, factor_family: str = "all") -> list[str]:
        all_factors = sorted(self.factor_registry.factor_names())
        if factor_family == "price":
            all_factors = [factor for factor in all_factors if not self.factor_registry.describe(factor).fundamental_data_required]
        elif factor_family == "fundamental":
            all_factors = [factor for factor in all_factors if self.factor_registry.describe(factor).fundamental_data_required]
        if mode == "full":
            selected = all_factors
        else:
            priority = [factor for factor in QUICK_FACTOR_PRIORITY if factor in all_factors]
            selected = priority + [factor for factor in all_factors if factor not in priority]
        limit = max_factors if max_factors is not None else (1 if mode == "quick" else len(selected))
        return selected[: max(int(limit), 0)]

    def select_and_filter_symbols(self, mode: str, max_symbols: int | None, factors: list[str]) -> dict[str, Any]:
        requested = QUICK_UNIVERSE if mode == "quick" and max_symbols is None else self.context.price_store.list_symbols()
        min_history = self.minimum_history_days(factors)
        selected: list[str] = []
        skipped: list[dict[str, str | int]] = []
        for symbol in requested:
            history = self.context.price_store.get_price_history(symbol)
            close_count = 0 if history.empty else int(history["close"].dropna().shape[0])
            if history.empty:
                skipped.append({"symbol": symbol, "reason": "no price data", "close_history": close_count})
                continue
            if close_count < min_history:
                skipped.append({"symbol": symbol, "reason": "insufficient close history", "close_history": close_count})
                continue
            selected.append(symbol)
            if max_symbols is not None and len(selected) >= max_symbols:
                break
        if not selected and mode == "quick":
            selected = QUICK_UNIVERSE[: max_symbols or len(QUICK_UNIVERSE)]
        return {
            "requested_symbol_count": len(requested),
            "selected_symbol_count": len(selected),
            "selected_symbols": selected,
            "skipped_symbol_count": len(skipped),
            "skipped_symbols": skipped[:200],
            "missing_price_symbols": [row["symbol"] for row in skipped if row["reason"] == "no price data"],
            "price_coverage": {
                "symbols_with_price_data": len(selected),
                "symbols_without_price_data": sum(1 for row in skipped if row["reason"] == "no price data"),
                "coverage_pct": len(selected) / len(requested) if requested else None,
            },
            "minimum_close_history_required": min_history,
            "fundamental_coverage": self.fundamental_coverage(selected),
        }

    def effective_date_range(self, mode: str, start: str | None, end: str | None, symbols: list[str]) -> tuple[str | None, str | None]:
        effective_start = start
        effective_end = end
        if mode == "quick":
            effective_start = effective_start or QUICK_DEFAULT_START
            effective_end = effective_end or self.latest_price_date(symbols) or effective_start
        else:
            effective_start = effective_start or self.earliest_price_date(symbols)
            effective_end = effective_end or self.latest_price_date(symbols)
        if effective_start and effective_end and effective_start > effective_end:
            raise ValueError("start must be before or equal to end")
        return effective_start, effective_end

    def latest_price_date(self, symbols: list[str]) -> str | None:
        return self.price_date_bound(symbols, "MAX")

    def earliest_price_date(self, symbols: list[str]) -> str | None:
        return self.price_date_bound(symbols, "MIN")

    def price_date_bound(self, symbols: list[str], aggregate: str) -> str | None:
        aggregate = aggregate.upper()
        if aggregate not in {"MIN", "MAX"}:
            raise ValueError("aggregate must be MIN or MAX")
        normalized = [str(symbol).upper() for symbol in symbols if str(symbol).strip()]
        params: list[str] = []
        where = ""
        if normalized:
            placeholders = ",".join("?" for _ in normalized)
            where = f"WHERE symbol IN ({placeholders})"
            params = normalized
        with self.context.price_store.connect() as connection:
            row = connection.execute(f"SELECT {aggregate}(date) AS date_bound FROM prices {where}", params).fetchone()
        return row["date_bound"] if row and row["date_bound"] else None

    def trading_day_count(self, symbols: list[str], start: str | None, end: str | None) -> int:
        conditions = []
        params: list[str] = []
        normalized = [str(symbol).upper() for symbol in symbols if str(symbol).strip()]
        if normalized:
            placeholders = ",".join("?" for _ in normalized)
            conditions.append(f"symbol IN ({placeholders})")
            params.extend(normalized)
        if start:
            conditions.append("date >= ?")
            params.append(start)
        if end:
            conditions.append("date <= ?")
            params.append(end)
        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        with self.context.price_store.connect() as connection:
            row = connection.execute(f"SELECT COUNT(DISTINCT date) AS count FROM prices {where}", params).fetchone()
        return int(row["count"] if row else 0)

    def minimum_history_days(self, factors: list[str]) -> int:
        lookbacks = [self.factor_registry.describe(factor).lookback_days for factor in factors if factor in self.factor_registry.factor_names()]
        return max([80, *lookbacks]) + 20

    @staticmethod
    def symbol_batches(symbols: list[str], batch_size: int) -> list[list[str]]:
        size = max(int(batch_size), 1)
        return [symbols[index : index + size] for index in range(0, len(symbols), size)] or [[]]

    @staticmethod
    def effective_batch_size(
        symbol_count: int,
        mode: str,
        requested_batch_size: int | None,
        parallel: bool,
        workers: int,
    ) -> int:
        if requested_batch_size is not None:
            return max(int(requested_batch_size), 1)
        if not parallel:
            return 10 if mode == "quick" else 25
        target_batches = max(workers * 2, 1)
        return max(1, math.ceil(max(symbol_count, 1) / target_batches))

    def fundamental_coverage(self, symbols: list[str]) -> dict[str, Any]:
        if not symbols:
            return {"symbols_with_fundamentals": 0, "symbols_missing_fundamentals": 0, "coverage_pct": None}
        rows = self.context.fundamental_store.rows("fundamental_metrics", symbols)
        covered = sorted({str(row.get("symbol", "")).upper() for row in rows if row.get("report_date")})
        missing = sorted(set(symbols) - set(covered))
        return {
            "symbols_with_fundamentals": len(covered),
            "symbols_missing_fundamentals": len(missing),
            "coverage_pct": len(covered) / len(symbols) if symbols else None,
            "covered_symbols": covered,
            "missing_symbols": missing[:200],
        }

    def select_strategies(self, mode: str, max_strategies: int | None) -> list[str]:
        rows = StrategyRegistry(self.context).list_strategies().get("strategies") or []
        strategies = [row["name"] for row in rows if row.get("valid") and row.get("name")]
        limit = max_strategies if max_strategies is not None else (1 if mode == "quick" else len(strategies))
        return strategies[: max(int(limit), 0)]
