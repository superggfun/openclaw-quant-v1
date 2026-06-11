"""SQLite persistence for OHLCV price data."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd


class SQLitePriceStore:
    """Store normalized daily prices in SQLite."""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def initialize(self) -> None:
        with sqlite3.connect(self.db_path) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS prices (
                    symbol TEXT NOT NULL,
                    date TEXT NOT NULL,
                    open REAL NOT NULL,
                    high REAL NOT NULL,
                    low REAL NOT NULL,
                    close REAL NOT NULL,
                    adj_close REAL NOT NULL,
                    volume INTEGER NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (symbol, date)
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_prices_symbol_date
                ON prices (symbol, date)
                """
            )

    def upsert_prices(self, prices: pd.DataFrame) -> int:
        if prices.empty:
            return 0

        rows = [
            (
                str(row.symbol).upper(),
                str(row.date),
                float(row.open),
                float(row.high),
                float(row.low),
                float(row.close),
                float(row.adj_close),
                int(row.volume),
            )
            for row in prices.itertuples(index=False)
        ]

        with self.connect() as connection:
            before = connection.total_changes
            connection.executemany(
                """
                INSERT INTO prices (
                    symbol, date, open, high, low, close, adj_close, volume
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(symbol, date) DO UPDATE SET
                    open = excluded.open,
                    high = excluded.high,
                    low = excluded.low,
                    close = excluded.close,
                    adj_close = excluded.adj_close,
                    volume = excluded.volume,
                    updated_at = CURRENT_TIMESTAMP
                """,
                rows,
            )
            return connection.total_changes - before

    def get_prices(
        self,
        symbol: str,
        limit: int = 10,
        ascending: bool = False,
    ) -> list[dict]:
        order = "ASC" if ascending else "DESC"
        with self.connect() as connection:
            rows = connection.execute(
                f"""
                SELECT symbol, date, open, high, low, close, adj_close, volume
                FROM prices
                WHERE symbol = ?
                ORDER BY date {order}
                LIMIT ?
                """,
                (symbol.upper(), limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def list_symbols(self) -> list[str]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT DISTINCT symbol FROM prices ORDER BY symbol"
            ).fetchall()
        return [row["symbol"] for row in rows]

    def latest_date(self, symbol: str) -> str | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT MAX(date) AS latest_date FROM prices WHERE symbol = ?",
                (symbol.upper(),),
            ).fetchone()
        return row["latest_date"] if row and row["latest_date"] else None

