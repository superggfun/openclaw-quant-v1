"""Build reusable no-lookahead factor observation matrices."""

from __future__ import annotations

import math
import time
from concurrent.futures import ProcessPoolExecutor, as_completed

import numpy as np
import pandas as pd

from quant.data.research_data_store import InMemoryResearchDataStore, multiprocessing_start_method, platform_label
from quant.factor_acceleration.bulk_price_loader import BulkPriceLoader
from quant.factor_acceleration.in_memory_provider import InMemoryPriceMatrixProvider
from quant.factor_acceleration.observation_matrix import ObservationMatrixResult, ObservationMatrixRow
from quant.factor_acceleration.price_factor_kernels import price_factor_series
from quant.factors.price.factor_registry import FactorRegistry
from quant.storage.sqlite_store import SQLitePriceStore

# ── Module-level price cache ──
#   Loaded by parent process before ProcessPoolExecutor fork;
#   child processes inherit it via COW shared memory, avoiding
#   per-worker SQLite reads.
_price_cache: dict[str, pd.DataFrame] | None = None


def preload_price_cache(histories: dict[str, pd.DataFrame]) -> None:
    """Pre-load price histories into module cache before forking workers.

    Call this in the parent process before ProcessPoolExecutor.
    Child processes inherit the cache via COW shared memory.
    """
    global _price_cache
    _price_cache = dict(histories)  # shallow copy — DataFrames are COW


def release_price_cache() -> None:
    """Release the module-level price cache to free memory."""
    global _price_cache
    _price_cache = None


class FactorMatrixBuilder:
    """Build factor values once, then attach one or more future-return horizons."""

    def __init__(
        self,
        price_store: SQLitePriceStore,
        factor_registry: FactorRegistry,
        research_data_store: InMemoryResearchDataStore | None = None,
        prefer_in_memory: bool = True,
        strict_in_memory: bool = False,
    ) -> None:
        self.price_store = price_store
        self.factor_registry = factor_registry
        self.research_data_store = research_data_store
        self.prefer_in_memory = prefer_in_memory
        self.strict_in_memory = strict_in_memory

    def build(
        self,
        factor: str,
        symbols: list[str],
        start: str | None,
        end: str | None,
        forward_days: int,
        max_workers: int = 1,
    ) -> ObservationMatrixResult:
        return self.build_many_horizons(
            factor, symbols, start, end, [forward_days], max_workers=max_workers,
        )[forward_days]

    def build_many_horizons(
        self,
        factor: str,
        symbols: list[str],
        start: str | None,
        end: str | None,
        horizons: list[int],
        max_workers: int = 1,
    ) -> dict[int, ObservationMatrixResult]:
        normalized_horizons = sorted({int(h) for h in horizons if int(h) > 0})
        if not normalized_horizons:
            raise ValueError("at least one positive horizon is required")
        started = time.monotonic()
        fallback_reason = None
        if self.prefer_in_memory:
            try:
                data_store = self.research_data_store
                if data_store is None:
                    data_store = InMemoryResearchDataStore.from_stores(
                        self.price_store,
                        getattr(self.factor_registry, "fundamental_store", None),
                        symbols=symbols,
                        horizons=normalized_horizons,
                    )
                return InMemoryPriceMatrixProvider(data_store, self.factor_registry).build_many_horizons(
                    factor=factor,
                    symbols=symbols,
                    start=start,
                    end=end,
                    horizons=normalized_horizons,
                    max_workers=max_workers,
                )
            except Exception as exc:
                if self.strict_in_memory:
                    raise
                fallback_reason = repr(exc)
        histories = BulkPriceLoader(self.price_store).load(symbols)

        n_workers = max(1, min(int(max_workers), len(symbols)))
        if n_workers <= 1:
            return self._build_sequential(
                factor, symbols, start, end, normalized_horizons, histories, started,
                fallback_used=fallback_reason is not None,
                fallback_reason=fallback_reason,
                requested_workers=max_workers,
            )

        # ── Pre-load price cache before fork so children inherit it via COW ──
        start_method = multiprocessing_start_method()
        if start_method == "fork":
            preload_price_cache(histories.histories)

        # ── Parallel: split symbols into chunks, each worker processes their chunk ──
        chunk_size = math.ceil(len(symbols) / n_workers)
        chunks = [symbols[i:i + chunk_size] for i in range(0, len(symbols), chunk_size)]
        db_path = self.price_store.db_path

        rows_by_horizon: dict[int, list[ObservationMatrixRow]] = {h: [] for h in normalized_horizons}
        excluded: dict[int, list[str]] = {h: [] for h in normalized_horizons}
        exclusion_reasons: dict[int, dict[str, str]] = {h: {} for h in normalized_horizons}
        warnings: dict[int, list[str]] = {h: [] for h in normalized_horizons}

        try:
            with ProcessPoolExecutor(max_workers=n_workers) as executor:
                futures = {
                    executor.submit(
                        _build_symbol_chunk,
                        db_path, factor, chunk, start, end, list(normalized_horizons),
                    ): chunk
                    for chunk in chunks
                }
                for future in as_completed(futures):
                    chunk_result = future.result()
                    for h in normalized_horizons:
                        rows_by_horizon[h].extend(chunk_result["rows"][h])
                        excluded[h].extend(chunk_result["excluded"][h])
                        exclusion_reasons[h].update(chunk_result["reasons"][h])
                        warnings[h].extend(chunk_result["warnings"][h])
        finally:
            release_price_cache()

        return self._assemble_result(factor, symbols, start, end, normalized_horizons,
                                     rows_by_horizon, excluded, exclusion_reasons, warnings,
                                     histories.read_seconds, started,
                                     provider_type="sqlite",
                                     cache_strategy="sqlite_bulk_with_fork_cow" if start_method == "fork" else "sqlite_bulk_spawn_workers",
                                     matrix_workers=n_workers,
                                     fallback_used=fallback_reason is not None,
                                     fallback_reason=fallback_reason,
                                     requested_workers=max_workers)

    def _build_sequential(
        self,
        factor: str,
        symbols: list[str],
        start: str | None,
        end: str | None,
        normalized_horizons: list[int],
        histories,
        started: float,
        fallback_used: bool = False,
        fallback_reason: str | None = None,
        requested_workers: int = 1,
    ) -> dict[int, ObservationMatrixResult]:
        rows_by_horizon: dict[int, list[ObservationMatrixRow]] = {h: [] for h in normalized_horizons}
        excluded: dict[int, list[str]] = {h: [] for h in normalized_horizons}
        exclusion_reasons: dict[int, dict[str, str]] = {h: {} for h in normalized_horizons}
        warnings: dict[int, list[str]] = {h: [] for h in normalized_horizons}

        for symbol in symbols:
            local = self._process_one_symbol(factor, symbol, start, end, normalized_horizons, histories)
            for h in normalized_horizons:
                rows_by_horizon[h].extend(local["rows"][h])
                excluded[h].extend(local["excluded"][h])
                exclusion_reasons[h].update(local["reasons"][h])
                warnings[h].extend(local["warnings"][h])

        return self._assemble_result(factor, symbols, start, end, normalized_horizons,
                                     rows_by_horizon, excluded, exclusion_reasons, warnings,
                                     histories.read_seconds, started,
                                     provider_type="sqlite",
                                     cache_strategy="sqlite_bulk_single_process",
                                     matrix_workers=1,
                                     fallback_used=fallback_used,
                                     fallback_reason=fallback_reason,
                                     requested_workers=requested_workers)

    def _process_one_symbol(
        self,
        factor: str,
        symbol: str,
        start: str | None,
        end: str | None,
        normalized_horizons: list[int],
        histories,
    ) -> dict:
        """Process a single symbol: normalize → factor_values → rows.  Thread-safe (read-only on self)."""
        local_rows: dict[int, list[ObservationMatrixRow]] = {h: [] for h in normalized_horizons}
        local_excluded: dict[int, list[str]] = {h: [] for h in normalized_horizons}
        local_reasons: dict[int, dict[str, str]] = {h: {} for h in normalized_horizons}
        local_warnings: dict[int, list[str]] = {h: [] for h in normalized_horizons}

        history = histories.histories.get(symbol)
        if history is None or history.empty:
            self._exclude_all(symbol, "no price data", normalized_horizons,
                              local_excluded, local_reasons, local_warnings)
            return {"rows": local_rows, "excluded": local_excluded,
                    "reasons": local_reasons, "warnings": local_warnings}

        history = self._normalize_history(history)
        if history.empty:
            self._exclude_all(symbol, "no valid close prices", normalized_horizons,
                              local_excluded, local_reasons, local_warnings)
            return {"rows": local_rows, "excluded": local_excluded,
                    "reasons": local_reasons, "warnings": local_warnings}

        factor_values = self._factor_values(factor, symbol, history, start, end)
        for horizon in normalized_horizons:
            symbol_rows = self._rows_for_horizon(factor, symbol, history, factor_values, horizon)
            if not symbol_rows:
                local_excluded[horizon].append(symbol)
                local_reasons[horizon][symbol] = "no valid factor and future-return pairs"
                local_warnings[horizon].append(f"excluded {symbol}: no valid factor and future-return pairs")
                continue
            local_rows[horizon].extend(symbol_rows)

        return {"rows": local_rows, "excluded": local_excluded,
                "reasons": local_reasons, "warnings": local_warnings}

    def _assemble_result(
        self,
        factor: str,
        symbols: list[str],
        start: str | None,
        end: str | None,
        normalized_horizons: list[int],
        rows_by_horizon: dict[int, list[ObservationMatrixRow]],
        excluded: dict[int, list[str]],
        exclusion_reasons: dict[int, dict[str, str]],
        warnings: dict[int, list[str]],
        read_seconds: float,
        started: float,
        provider_type: str = "sqlite",
        cache_strategy: str = "sqlite_bulk",
        matrix_workers: int = 1,
        fallback_used: bool = False,
        fallback_reason: str | None = None,
        requested_workers: int = 1,
    ) -> dict[int, ObservationMatrixResult]:
        build_seconds = time.monotonic() - started
        output = {}
        for horizon in normalized_horizons:
            rows = sorted(rows_by_horizon[horizon], key=lambda row: (row.signal_date, row.symbol, row.forward_days))
            matrix_warnings = list(warnings[horizon])
            if fallback_reason:
                matrix_warnings.append(f"IN_MEMORY_FALLBACK: {fallback_reason}")
            output[horizon] = ObservationMatrixResult(
                factor_name=factor,
                universe=list(symbols),
                start=start,
                end=end,
                forward_days=horizon,
                rows=rows,
                excluded_symbols=excluded[horizon],
                exclusion_reasons=exclusion_reasons[horizon],
                warnings=matrix_warnings,
                bulk_read_seconds=read_seconds,
                matrix_build_seconds=build_seconds,
                performance_metadata={
                    "provider_type": provider_type,
                    "platform": platform_label(),
                    "multiprocessing_start_method": multiprocessing_start_method(),
                    "memory_preload_enabled": False,
                    "memory_preload_seconds": 0.0,
                    "estimated_matrix_memory_mb": None,
                    "requested_workers": requested_workers,
                    "matrix_workers": matrix_workers,
                    "matrix_build_seconds": round(build_seconds, 6),
                    "bulk_read_seconds": round(read_seconds, 6),
                    "cache_strategy": cache_strategy,
                    "fallback_used": fallback_used,
                    "fallback_reason": fallback_reason,
                    "no_lookahead": True,
                },
            )
        return output

    # ── static helpers ──

    @staticmethod
    def _fundamental_factor_values(
        registry,
        factor: str,
        symbol: str,
        history: pd.DataFrame,
        start: str | None,
        end: str | None,
    ) -> dict[int, float]:
        """Per-row factor computation for fundamental factors.

        Fundamental factors only need ``symbol + as_of_date`` to look up
        financial data — the close series is purely diagnostic.  This method
        avoids constructing a growing close series per iteration.
        """
        closes_dummy = history["close"].iloc[:0]
        dates = history["date"].values
        values: dict[int, float] = {}
        for index in range(len(history)):
            signal_date = str(dates[index])
            if start and signal_date < start:
                continue
            if end and signal_date > end:
                continue
            value = registry.factor_value(
                closes_dummy, factor, symbol=symbol, as_of_date=signal_date
            )
            if value is not None and not pd.isna(value):
                values[index] = float(value)
        return values

    @staticmethod
    def _normalize_history(history: pd.DataFrame) -> pd.DataFrame:
        normalized = history.sort_values("date").reset_index(drop=True).copy()
        normalized["close"] = pd.to_numeric(normalized["close"], errors="coerce")
        return normalized.dropna(subset=["close"]).reset_index(drop=True)

    def _factor_values(
        self,
        factor: str,
        symbol: str,
        history: pd.DataFrame,
        start: str | None,
        end: str | None,
    ) -> dict[int, float]:
        price_series = price_factor_series(factor, history)
        if price_series is not None:
            return self._valid_series_values(price_series, history, start, end)

        values: dict[int, float] = {}
        is_fundamental = self.factor_registry.is_fundamental(factor)
        if is_fundamental:
            return FactorMatrixBuilder._fundamental_factor_values(
                self.factor_registry, factor, symbol, history, start, end
            )

        for index in range(len(history)):
            signal_date = str(history.iloc[index]["date"])
            if start and signal_date < start:
                continue
            if end and signal_date > end:
                continue
            value = self.factor_registry.factor_value(
                history.iloc[: index + 1]["close"],
                factor,
                symbol=symbol,
                as_of_date=signal_date,
            )
            if value is None or pd.isna(value):
                continue
            values[index] = float(value)
        return values

    @staticmethod
    def _valid_series_values(
        values: pd.Series,
        history: pd.DataFrame,
        start: str | None,
        end: str | None,
    ) -> dict[int, float]:
        mask = values.notna()
        dates = history["date"].astype(str)
        if start:
            mask &= dates >= start
        if end:
            mask &= dates <= end
        valid = values[mask]
        return {int(i): float(v) for i, v in valid.items()}

    @staticmethod
    def _rows_for_horizon(
        factor: str,
        symbol: str,
        history: pd.DataFrame,
        factor_values: dict[int, float],
        horizon: int,
    ) -> list[ObservationMatrixRow]:
        dates_arr = history["date"].to_numpy()
        closes_arr = history["close"].to_numpy(dtype=float, na_value=float("nan"))
        max_index = len(history)
        rows = []
        for index, factor_value in factor_values.items():
            future_index = index + horizon
            if future_index >= max_index:
                continue
            signal_close = closes_arr[index]
            future_close = closes_arr[future_index]
            if np.isnan(signal_close) or np.isnan(future_close):
                continue
            rows.append(
                ObservationMatrixRow(
                    factor_name=factor,
                    symbol=symbol,
                    signal_date=str(dates_arr[index]),
                    future_date=str(dates_arr[future_index]),
                    factor_value=factor_value,
                    future_return=(float(future_close) / float(signal_close)) - 1.0,
                    forward_days=horizon,
                    valid=True,
                    exclusion_reason=None,
                )
            )
        return rows

    @staticmethod
    def _exclude_all(
        symbol: str,
        reason: str,
        horizons: list[int],
        excluded: dict[int, list[str]],
        exclusion_reasons: dict[int, dict[str, str]],
        warnings: dict[int, list[str]],
    ) -> None:
        for horizon in horizons:
            excluded[horizon].append(symbol)
            exclusion_reasons[horizon][symbol] = reason
            warnings[horizon].append(f"excluded {symbol}: {reason}")


def _build_symbol_chunk(
    db_path: str,
    factor: str,
    symbols: list[str],
    start: str | None,
    end: str | None,
    horizons: list[int],
) -> dict:
    """Process a chunk of symbols in a subprocess.  Returns picklable dict.

    If the parent loaded _price_cache before fork, child processes inherit it
    via COW shared memory and skip SQLite reads entirely.
    """
    from quant.data.fundamental.fundamental_store import FundamentalStore
    from quant.factors.price.factor_registry import FactorRegistry

    # ── Use COW cache if parent pre-loaded it ──
    if _price_cache is not None:
        return _build_from_cache(factor, symbols, start, end, horizons, db_path)

    price_store = SQLitePriceStore(db_path)
    fundamental_store = FundamentalStore(db_path)
    registry = FactorRegistry(fundamental_store)
    builder = FactorMatrixBuilder(price_store, registry)

    result = builder.build_many_horizons(factor, symbols, start, end, horizons, max_workers=1)

    return {
        "rows": {h: result[h].rows for h in horizons},
        "excluded": {h: result[h].excluded_symbols for h in horizons},
        "reasons": {h: result[h].exclusion_reasons for h in horizons},
        "warnings": {h: result[h].warnings for h in horizons},
    }


def _build_from_cache(
    factor: str,
    symbols: list[str],
    start: str | None,
    end: str | None,
    horizons: list[int],
    db_path: str,
) -> dict:
    """Build observations from the pre-loaded COW cache — no SQLite price reads.

    Fundamental factors still need FundamentalStore (cheap metadata lookups
    via SQLite, not bulk price reads).  db_path is provided so the worker can
    open its own FundamentalStore connection.
    """
    from quant.data.fundamental.fundamental_store import FundamentalStore
    from quant.factors.price.factor_registry import FactorRegistry

    fundamental_store = FundamentalStore(db_path)
    registry = FactorRegistry(fundamental_store)
    normalized_horizons = sorted({int(h) for h in horizons if int(h) > 0})

    rows_by_horizon: dict[int, list[ObservationMatrixRow]] = {h: [] for h in normalized_horizons}
    excluded: dict[int, list[str]] = {h: [] for h in normalized_horizons}
    reasons: dict[int, dict[str, str]] = {h: {} for h in normalized_horizons}
    warnings_list: dict[int, list[str]] = {h: [] for h in normalized_horizons}

    for symbol in symbols:
        history = _price_cache.get(symbol) if _price_cache else None
        if history is None or history.empty:
            for h in normalized_horizons:
                excluded[h].append(symbol)
                reasons[h][symbol] = "no price data"
                warnings_list[h].append(f"excluded {symbol}: no price data")
            continue

        history = history.copy()
        history = FactorMatrixBuilder._normalize_history(history)
        if history.empty:
            for h in normalized_horizons:
                excluded[h].append(symbol)
                reasons[h][symbol] = "no valid close prices"
                warnings_list[h].append(f"excluded {symbol}: no valid close prices")
            continue

        factor_values = price_factor_series(factor, history)
        if factor_values is not None:
            factor_dict = FactorMatrixBuilder._valid_series_values(factor_values, history, start, end)
        else:
            # Slow path: per-row factor computation for non-price factors
            is_fundamental = registry.is_fundamental(factor)
            if is_fundamental:
                factor_dict = FactorMatrixBuilder._fundamental_factor_values(
                    registry, factor, symbol, history, start, end
                )
            else:
                factor_dict = {}
                for index in range(len(history)):
                    signal_date = str(history.iloc[index]["date"])
                    if start and signal_date < start:
                        continue
                    if end and signal_date > end:
                        continue
                    value = registry.factor_value(
                        history.iloc[: index + 1]["close"],
                        factor,
                        symbol=symbol,
                        as_of_date=signal_date,
                    )
                    if value is not None and not pd.isna(value):
                        factor_dict[index] = float(value)

        for horizon in normalized_horizons:
            symbol_rows = FactorMatrixBuilder._rows_for_horizon(factor, symbol, history, factor_dict, horizon)
            if not symbol_rows:
                excluded[horizon].append(symbol)
                reasons[horizon][symbol] = "no valid factor and future-return pairs"
                warnings_list[horizon].append(f"excluded {symbol}: no valid factor and future-return pairs")
                continue
            rows_by_horizon[horizon].extend(symbol_rows)

    return {
        "rows": rows_by_horizon,
        "excluded": excluded,
        "reasons": reasons,
        "warnings": warnings_list,
    }
