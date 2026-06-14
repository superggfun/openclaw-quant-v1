"""Memory-first research data structures backed by SQLite persistence."""

from __future__ import annotations

import multiprocessing as mp
import platform as platform_module
import time
from dataclasses import dataclass, field
from typing import Any, Protocol

import numpy as np
import pandas as pd

from quant.data.fundamental.fundamental_models import STATEMENT_FIELDS
from quant.data.fundamental.fundamental_store import FundamentalStore
from quant.storage.sqlite_store import SQLitePriceStore


DEFAULT_FORWARD_RETURN_HORIZONS = (1, 5, 10, 20, 40, 60)


def multiprocessing_start_method() -> str:
    """Return the effective multiprocessing start method for metadata."""

    method = mp.get_start_method(allow_none=True)
    if method:
        return method
    return "spawn" if platform_module.system().lower() == "windows" else "fork"


def platform_label() -> str:
    """Return a compact platform label, distinguishing WSL from native Linux."""

    system = platform_module.system()
    release = platform_module.release().lower()
    if system == "Linux" and ("microsoft" in release or "wsl" in release):
        return "wsl"
    return system.lower()


@dataclass(frozen=True)
class InMemoryFundamentalTable:
    available_dates: np.ndarray
    rows: list[dict[str, Any]]


class InMemoryFundamentalStore:
    """Read-only report-date aware fundamental lookup cache.

    Rows are sorted by tradable availability date.  ``latest_as_of`` uses
    ``searchsorted`` so a signal date can only see rows with
    ``report_date <= signal_date``.
    """

    def __init__(self, rows_by_key: dict[tuple[str, str], InMemoryFundamentalTable]) -> None:
        self._rows_by_key = rows_by_key

    @classmethod
    def from_store(
        cls,
        store: FundamentalLookupStore | FundamentalStore | None,
        symbols: list[str] | None = None,
    ) -> "InMemoryFundamentalStore | None":
        if store is None:
            return None
        rows_by_key: dict[tuple[str, str], InMemoryFundamentalTable] = {}
        normalized = [symbol.upper() for symbol in symbols] if symbols else None
        for statement in STATEMENT_FIELDS:
            for row in store.rows(statement, normalized):
                report_date = row.get("report_date")
                if not report_date:
                    continue
                symbol = str(row.get("symbol") or "").upper()
                key = (statement, symbol)
                bucket = rows_by_key.setdefault(
                    key,
                    InMemoryFundamentalTable(
                        available_dates=np.array([], dtype="U10"),
                        rows=[],
                    ),
                )
                bucket.rows.append(dict(row))

        sorted_tables: dict[tuple[str, str], InMemoryFundamentalTable] = {}
        for key, table in rows_by_key.items():
            rows = sorted(
                table.rows,
                key=lambda item: (
                    str(item.get("report_date") or ""),
                    str(item.get("fiscal_period_end") or ""),
                ),
            )
            sorted_tables[key] = InMemoryFundamentalTable(
                available_dates=np.array([str(row["report_date"]) for row in rows], dtype="U10"),
                rows=rows,
            )
        return cls(sorted_tables)

    def rows(self, statement: str, symbols: list[str] | None = None) -> list[dict]:
        normalized = {symbol.upper() for symbol in symbols} if symbols else None
        output: list[dict] = []
        for (table_name, symbol), table in self._rows_by_key.items():
            if table_name != statement:
                continue
            if normalized is not None and symbol not in normalized:
                continue
            output.extend(dict(row) for row in table.rows)
        return output

    def latest_as_of(self, symbol: str, statement: str, as_of_date: str) -> dict | None:
        table = self._rows_by_key.get((statement, symbol.upper()))
        if table is None or len(table.available_dates) == 0:
            return None
        index = int(np.searchsorted(table.available_dates, str(as_of_date), side="right")) - 1
        if index < 0:
            return None
        return dict(table.rows[index])


class FundamentalLookupStore(Protocol):
    def rows(self, statement: str, symbols: list[str] | None = None) -> list[dict]:
        ...

    def latest_as_of(self, symbol: str, statement: str, as_of_date: str) -> dict | None:
        ...


@dataclass(frozen=True)
class InMemoryResearchDataStore:
    """Compact price and fundamental research cache.

    SQLite remains the source of truth.  This object is a read-only runtime
    projection optimized for factor research matrix construction.
    """

    symbols: list[str]
    dates: list[str]
    close_matrix: np.ndarray
    valid_mask: np.ndarray
    forward_return_matrices: dict[int, np.ndarray]
    forward_date_index_matrices: dict[int, np.ndarray]
    symbol_to_col: dict[str, int]
    date_to_row: dict[str, int]
    valid_row_indices_by_col: dict[int, np.ndarray]
    fundamental_store: InMemoryFundamentalStore | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_stores(
        cls,
        price_store: SQLitePriceStore,
        fundamental_store: FundamentalLookupStore | FundamentalStore | None = None,
        symbols: list[str] | None = None,
        horizons: list[int] | None = None,
    ) -> "InMemoryResearchDataStore":
        started = time.monotonic()
        normalized_symbols = _normalize_symbols(symbols or price_store.list_symbols())
        load_started = time.monotonic()
        histories = price_store.get_price_history_many(normalized_symbols)
        bulk_read_seconds = time.monotonic() - load_started
        return cls.from_histories(
            histories,
            fundamental_store=fundamental_store,
            symbols=normalized_symbols,
            horizons=horizons,
            preload_started=started,
            bulk_read_seconds=bulk_read_seconds,
        )

    @classmethod
    def from_histories(
        cls,
        histories: dict[str, pd.DataFrame],
        fundamental_store: FundamentalLookupStore | FundamentalStore | None = None,
        symbols: list[str] | None = None,
        horizons: list[int] | None = None,
        preload_started: float | None = None,
        bulk_read_seconds: float = 0.0,
    ) -> "InMemoryResearchDataStore":
        started = preload_started or time.monotonic()
        normalized_symbols = _normalize_symbols(symbols or list(histories))
        normalized_histories: dict[str, pd.DataFrame] = {}
        all_dates: set[str] = set()
        for symbol in normalized_symbols:
            history = histories.get(symbol)
            if history is None:
                history = histories.get(symbol.upper())
            frame = _normalize_history(history)
            normalized_histories[symbol] = frame
            all_dates.update(frame["date"].astype(str).tolist())

        dates = sorted(all_dates)
        symbol_to_col = {symbol: index for index, symbol in enumerate(normalized_symbols)}
        date_to_row = {date: index for index, date in enumerate(dates)}
        close_matrix = np.full((len(dates), len(normalized_symbols)), np.nan, dtype=np.float64)
        valid_row_indices_by_col: dict[int, np.ndarray] = {}

        for symbol, col in symbol_to_col.items():
            frame = normalized_histories.get(symbol)
            if frame is None or frame.empty:
                valid_row_indices_by_col[col] = np.array([], dtype=np.int64)
                continue
            rows = np.array([date_to_row[str(value)] for value in frame["date"].astype(str)], dtype=np.int64)
            close_matrix[rows, col] = frame["close"].to_numpy(dtype=np.float64)
            valid_row_indices_by_col[col] = rows

        valid_mask = np.isfinite(close_matrix)
        normalized_horizons = sorted({int(h) for h in (horizons or DEFAULT_FORWARD_RETURN_HORIZONS) if int(h) > 0})
        forward_return_matrices: dict[int, np.ndarray] = {}
        forward_date_index_matrices: dict[int, np.ndarray] = {}
        for horizon in normalized_horizons:
            returns = np.full(close_matrix.shape, np.nan, dtype=np.float64)
            future_rows = np.full(close_matrix.shape, -1, dtype=np.int64)
            for col, rows in valid_row_indices_by_col.items():
                if len(rows) <= horizon:
                    continue
                signal_rows = rows[:-horizon]
                target_rows = rows[horizon:]
                signal_close = close_matrix[signal_rows, col]
                future_close = close_matrix[target_rows, col]
                valid = np.isfinite(signal_close) & np.isfinite(future_close)
                returns[signal_rows[valid], col] = (future_close[valid] / signal_close[valid]) - 1.0
                future_rows[signal_rows[valid], col] = target_rows[valid]
            forward_return_matrices[horizon] = returns
            forward_date_index_matrices[horizon] = future_rows

        memory_bytes = close_matrix.nbytes + valid_mask.nbytes
        memory_bytes += sum(matrix.nbytes for matrix in forward_return_matrices.values())
        memory_bytes += sum(matrix.nbytes for matrix in forward_date_index_matrices.values())
        start_method = multiprocessing_start_method()
        metadata = {
            "platform": platform_label(),
            "multiprocessing_start_method": start_method,
            "provider_type": "cow_memory" if start_method == "fork" else "in_memory",
            "cache_strategy": "fork_cow_readonly" if start_method == "fork" else "single_process_memory",
            "memory_preload_enabled": True,
            "memory_preload_seconds": round(time.monotonic() - started, 6),
            "estimated_matrix_memory_mb": round(memory_bytes / (1024 * 1024), 6),
            "bulk_read_seconds": round(bulk_read_seconds, 6),
            "fallback_used": False,
            "no_lookahead": True,
        }
        return cls(
            symbols=normalized_symbols,
            dates=dates,
            close_matrix=close_matrix,
            valid_mask=valid_mask,
            forward_return_matrices=forward_return_matrices,
            forward_date_index_matrices=forward_date_index_matrices,
            symbol_to_col=symbol_to_col,
            date_to_row=date_to_row,
            valid_row_indices_by_col=valid_row_indices_by_col,
            fundamental_store=InMemoryFundamentalStore.from_store(fundamental_store, normalized_symbols),
            metadata=metadata,
        )

    def ensure_horizons(self, horizons: list[int]) -> "InMemoryResearchDataStore":
        missing = [int(h) for h in horizons if int(h) > 0 and int(h) not in self.forward_return_matrices]
        if not missing:
            return self
        all_horizons = sorted({*self.forward_return_matrices, *missing})
        histories = {}
        for symbol, col in self.symbol_to_col.items():
            rows = self.valid_row_indices_by_col[col]
            histories[symbol] = pd.DataFrame(
                {
                    "symbol": symbol,
                    "date": [self.dates[int(row)] for row in rows],
                    "close": self.close_matrix[rows, col],
                }
            )
        return InMemoryResearchDataStore.from_histories(
            histories,
            fundamental_store=self.fundamental_store,
            symbols=self.symbols,
            horizons=all_horizons,
            bulk_read_seconds=float(self.metadata.get("bulk_read_seconds") or 0.0),
        )


def _normalize_symbols(symbols: list[str]) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for symbol in symbols:
        normalized = str(symbol).upper().strip()
        if normalized and normalized not in seen:
            output.append(normalized)
            seen.add(normalized)
    return output


def _normalize_history(history: pd.DataFrame | None) -> pd.DataFrame:
    columns = ["symbol", "date", "close"]
    if history is None or history.empty:
        return pd.DataFrame(columns=columns)
    frame = history.copy()
    frame["date"] = frame["date"].astype(str)
    frame["close"] = pd.to_numeric(frame["close"], errors="coerce")
    return frame.sort_values("date").dropna(subset=["close"]).reset_index(drop=True)
