"""In-memory price matrix provider for factor observation builds."""

from __future__ import annotations

import math
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from typing import Any

import numpy as np
import pandas as pd

from quant.data.research_data_store import InMemoryResearchDataStore, multiprocessing_start_method
from quant.factor_acceleration.observation_matrix import ObservationMatrixResult, ObservationMatrixRow
from quant.factors.price.factor_registry import FactorRegistry


_research_data_store: InMemoryResearchDataStore | None = None


def preload_research_data_store(data_store: InMemoryResearchDataStore) -> None:
    """Preload the NumPy research store before forking workers."""

    global _research_data_store
    _research_data_store = data_store


def release_research_data_store() -> None:
    """Release the module-level research store reference."""

    global _research_data_store
    _research_data_store = None


class InMemoryPriceMatrixProvider:
    """Build observation matrices from ``InMemoryResearchDataStore``."""

    def __init__(
        self,
        data_store: InMemoryResearchDataStore,
        factor_registry: FactorRegistry,
    ) -> None:
        self.data_store = data_store
        self.factor_registry = factor_registry

    @property
    def supports_fork_cow(self) -> bool:
        return multiprocessing_start_method() == "fork"

    def build_many_horizons(
        self,
        factor: str,
        symbols: list[str],
        start: str | None,
        end: str | None,
        horizons: list[int],
        max_workers: int = 1,
    ) -> dict[int, ObservationMatrixResult]:
        started = time.monotonic()
        normalized_horizons = sorted({int(h) for h in horizons if int(h) > 0})
        data_store = self.data_store.ensure_horizons(normalized_horizons)
        n_workers = max(1, min(int(max_workers), len(symbols))) if symbols else 1
        if not self.supports_fork_cow:
            n_workers = 1

        if n_workers <= 1:
            rows_by_horizon, excluded, reasons, warnings = self._build_symbols(
                factor, symbols, start, end, normalized_horizons, data_store, self.factor_registry,
            )
        else:
            preload_research_data_store(data_store)
            try:
                rows_by_horizon = {h: [] for h in normalized_horizons}
                excluded = {h: [] for h in normalized_horizons}
                reasons = {h: {} for h in normalized_horizons}
                warnings = {h: [] for h in normalized_horizons}
                chunk_size = math.ceil(len(symbols) / n_workers)
                chunks = [symbols[i:i + chunk_size] for i in range(0, len(symbols), chunk_size)]
                with ProcessPoolExecutor(max_workers=n_workers) as executor:
                    futures = {
                        executor.submit(_build_in_memory_chunk, factor, chunk, start, end, normalized_horizons): chunk
                        for chunk in chunks
                    }
                    for future in as_completed(futures):
                        chunk_result = future.result()
                        for horizon in normalized_horizons:
                            rows_by_horizon[horizon].extend(chunk_result["rows"][horizon])
                            excluded[horizon].extend(chunk_result["excluded"][horizon])
                            reasons[horizon].update(chunk_result["reasons"][horizon])
                            warnings[horizon].extend(chunk_result["warnings"][horizon])
            finally:
                release_research_data_store()

        build_seconds = time.monotonic() - started
        return self._assemble_results(
            factor,
            symbols,
            start,
            end,
            normalized_horizons,
            rows_by_horizon,
            excluded,
            reasons,
            warnings,
            data_store,
            max_workers,
            n_workers,
            build_seconds,
        )

    @staticmethod
    def _build_symbols(
        factor: str,
        symbols: list[str],
        start: str | None,
        end: str | None,
        horizons: list[int],
        data_store: InMemoryResearchDataStore,
        factor_registry: FactorRegistry,
    ) -> tuple[dict[int, list[ObservationMatrixRow]], dict[int, list[str]], dict[int, dict[str, str]], dict[int, list[str]]]:
        rows_by_horizon: dict[int, list[ObservationMatrixRow]] = {h: [] for h in horizons}
        excluded: dict[int, list[str]] = {h: [] for h in horizons}
        reasons: dict[int, dict[str, str]] = {h: {} for h in horizons}
        warnings: dict[int, list[str]] = {h: [] for h in horizons}

        for symbol in symbols:
            col = data_store.symbol_to_col.get(symbol.upper())
            if col is None:
                _exclude_all(symbol, "no price data", horizons, excluded, reasons, warnings)
                continue
            valid_rows = data_store.valid_row_indices_by_col.get(col, np.array([], dtype=np.int64))
            if len(valid_rows) == 0:
                msg = "no price data" if symbol in data_store.symbols_without_data else "no valid close prices"
                _exclude_all(symbol, msg, horizons, excluded, reasons, warnings)
                continue
            factor_values = _factor_values(factor, symbol, col, valid_rows, start, end, data_store, factor_registry)
            for horizon in horizons:
                symbol_rows = _rows_for_horizon(factor, symbol, col, factor_values, horizon, data_store)
                if not symbol_rows:
                    excluded[horizon].append(symbol)
                    reasons[horizon][symbol] = "no valid factor and future-return pairs"
                    warnings[horizon].append(f"excluded {symbol}: no valid factor and future-return pairs")
                    continue
                rows_by_horizon[horizon].extend(symbol_rows)
        return rows_by_horizon, excluded, reasons, warnings

    @staticmethod
    def _assemble_results(
        factor: str,
        symbols: list[str],
        start: str | None,
        end: str | None,
        horizons: list[int],
        rows_by_horizon: dict[int, list[ObservationMatrixRow]],
        excluded: dict[int, list[str]],
        reasons: dict[int, dict[str, str]],
        warnings: dict[int, list[str]],
        data_store: InMemoryResearchDataStore,
        requested_workers: int,
        matrix_workers: int,
        build_seconds: float,
    ) -> dict[int, ObservationMatrixResult]:
        output: dict[int, ObservationMatrixResult] = {}
        start_method = multiprocessing_start_method()
        supports_cow_fork = start_method == "fork"
        uses_cow = matrix_workers > 1 and supports_cow_fork
        provider_type = "cow_memory" if uses_cow else "in_memory"
        cache_strategy = "fork_cow_readonly" if uses_cow else "single_process_memory"
        for horizon in horizons:
            rows = sorted(rows_by_horizon[horizon], key=lambda row: (row.signal_date, row.symbol, row.forward_days))
            metadata = dict(data_store.metadata)
            metadata.update(
                {
                    "provider_type": provider_type,
                    "cache_strategy": cache_strategy,
                    "supports_cow_fork": supports_cow_fork,
                    "requested_workers": requested_workers,
                    "matrix_workers": matrix_workers,
                    "matrix_build_seconds": round(build_seconds, 6),
                    "bulk_read_seconds": data_store.metadata.get("bulk_read_seconds"),
                }
            )
            output[horizon] = ObservationMatrixResult(
                factor_name=factor,
                universe=list(symbols),
                start=start,
                end=end,
                forward_days=horizon,
                rows=rows,
                excluded_symbols=excluded[horizon],
                exclusion_reasons=reasons[horizon],
                warnings=warnings[horizon],
                bulk_read_seconds=float(data_store.metadata.get("bulk_read_seconds") or 0.0),
                matrix_build_seconds=build_seconds,
                performance_metadata=metadata,
            )
        return output


def _build_in_memory_chunk(
    factor: str,
    symbols: list[str],
    start: str | None,
    end: str | None,
    horizons: list[int],
) -> dict[str, Any]:
    if _research_data_store is None:
        raise RuntimeError("in-memory research data store is not preloaded")
    registry = FactorRegistry(_research_data_store.fundamental_store)
    rows, excluded, reasons, warnings = InMemoryPriceMatrixProvider._build_symbols(
        factor, symbols, start, end, horizons, _research_data_store, registry,
    )
    return {"rows": rows, "excluded": excluded, "reasons": reasons, "warnings": warnings}


def _factor_values(
    factor: str,
    symbol: str,
    col: int,
    valid_rows: np.ndarray,
    start: str | None,
    end: str | None,
    data_store: InMemoryResearchDataStore,
    factor_registry: FactorRegistry,
) -> dict[int, float]:
    price_series = _price_factor_series(factor, col, valid_rows, data_store)
    if price_series is not None:
        return _valid_series_values(price_series, valid_rows, start, end, data_store)

    values: dict[int, float] = {}
    is_fundamental = factor_registry.is_fundamental(factor)
    closes_dummy = pd.Series(dtype=float)
    for row_index in valid_rows:
        signal_date = data_store.dates[int(row_index)]
        if start and signal_date < start:
            continue
        if end and signal_date > end:
            continue
        if is_fundamental:
            value = factor_registry.factor_value(closes_dummy, factor, symbol=symbol, as_of_date=signal_date)
        else:
            close_values = data_store.close_matrix[valid_rows[valid_rows <= row_index], col]
            value = factor_registry.factor_value(
                pd.Series(close_values),
                factor,
                symbol=symbol,
                as_of_date=signal_date,
            )
        if value is not None and not pd.isna(value):
            values[int(row_index)] = float(value)
    return values


def _price_factor_series(
    factor: str,
    col: int,
    valid_rows: np.ndarray,
    data_store: InMemoryResearchDataStore,
) -> pd.Series | None:
    from quant.factor_acceleration.price_factor_kernels import price_factor_series as pfs

    closes = pd.Series(data_store.close_matrix[valid_rows, col], index=valid_rows)
    return pfs(factor, pd.DataFrame({"close": closes}))


def _valid_series_values(
    values: pd.Series,
    valid_rows: np.ndarray,
    start: str | None,
    end: str | None,
    data_store: InMemoryResearchDataStore,
) -> dict[int, float]:
    output: dict[int, float] = {}
    finite_vals = values.dropna()
    finite_vals = finite_vals[np.isfinite(finite_vals.to_numpy(dtype=float, na_value=float("nan")))]
    for row_index, value in finite_vals.items():
        row = int(row_index)
        signal_date = data_store.dates[row]
        if start and signal_date < start:
            continue
        if end and signal_date > end:
            continue
        output[row] = float(value)
    return output


def _rows_for_horizon(
    factor: str,
    symbol: str,
    col: int,
    factor_values: dict[int, float],
    horizon: int,
    data_store: InMemoryResearchDataStore,
) -> list[ObservationMatrixRow]:
    returns = data_store.forward_return_matrices[horizon]
    future_rows = data_store.forward_date_index_matrices[horizon]
    rows: list[ObservationMatrixRow] = []
    for row_index, factor_value in factor_values.items():
        future_return = returns[row_index, col]
        future_row = int(future_rows[row_index, col])
        if not np.isfinite(future_return) or future_row < 0:
            continue
        rows.append(
            ObservationMatrixRow(
                factor_name=factor,
                symbol=symbol,
                signal_date=data_store.dates[row_index],
                future_date=data_store.dates[future_row],
                factor_value=factor_value,
                future_return=float(future_return),
                forward_days=horizon,
                valid=True,
                exclusion_reason=None,
            )
        )
    return rows


def _exclude_all(
    symbol: str,
    reason: str,
    horizons: list[int],
    excluded: dict[int, list[str]],
    reasons: dict[int, dict[str, str]],
    warnings: dict[int, list[str]],
) -> None:
    for horizon in horizons:
        excluded[horizon].append(symbol)
        reasons[horizon][symbol] = reason
        warnings[horizon].append(f"excluded {symbol}: {reason}")
