"""Static symbol metadata and SQLite persistence."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SymbolMetadata:
    symbol: str
    name: str
    asset_type: str
    sector: str
    industry: str
    currency: str = "USD"
    exchange: str = "NASDAQ"


DEFAULT_SYMBOL_METADATA: tuple[SymbolMetadata, ...] = (
    SymbolMetadata("SPY", "SPDR S&P 500 ETF Trust", "ETF", "ETF", "Broad Market ETF", "USD", "NYSEARCA"),
    SymbolMetadata("QQQ", "Invesco QQQ Trust", "ETF", "ETF", "Technology ETF", "USD", "NASDAQ"),
    SymbolMetadata("DIA", "SPDR Dow Jones Industrial Average ETF", "ETF", "ETF", "Broad Market ETF", "USD", "NYSEARCA"),
    SymbolMetadata("IWM", "iShares Russell 2000 ETF", "ETF", "ETF", "Small Cap ETF", "USD", "NYSEARCA"),
    SymbolMetadata("TLT", "iShares 20+ Year Treasury Bond ETF", "ETF", "ETF", "Bond ETF", "USD", "NASDAQ"),
    SymbolMetadata("GLD", "SPDR Gold Shares", "ETF", "ETF", "Commodity ETF", "USD", "NYSEARCA"),
    SymbolMetadata("XLK", "Technology Select Sector SPDR Fund", "ETF", "ETF", "Sector ETF", "USD", "NYSEARCA"),
    SymbolMetadata("XLF", "Financial Select Sector SPDR Fund", "ETF", "ETF", "Sector ETF", "USD", "NYSEARCA"),
    SymbolMetadata("XLV", "Health Care Select Sector SPDR Fund", "ETF", "ETF", "Sector ETF", "USD", "NYSEARCA"),
    SymbolMetadata("XLE", "Energy Select Sector SPDR Fund", "ETF", "ETF", "Sector ETF", "USD", "NYSEARCA"),
    SymbolMetadata("AAPL", "Apple Inc.", "Equity", "Technology", "Consumer Electronics", "USD", "NASDAQ"),
    SymbolMetadata("MSFT", "Microsoft Corporation", "Equity", "Technology", "Software", "USD", "NASDAQ"),
    SymbolMetadata("NVDA", "NVIDIA Corporation", "Equity", "Technology", "Semiconductors", "USD", "NASDAQ"),
    SymbolMetadata("AMD", "Advanced Micro Devices, Inc.", "Equity", "Technology", "Semiconductors", "USD", "NASDAQ"),
    SymbolMetadata("GOOGL", "Alphabet Inc.", "Equity", "Communication Services", "Internet Content", "USD", "NASDAQ"),
    SymbolMetadata("META", "Meta Platforms, Inc.", "Equity", "Communication Services", "Internet Content", "USD", "NASDAQ"),
    SymbolMetadata("AMZN", "Amazon.com, Inc.", "Equity", "Consumer Discretionary", "Internet Retail", "USD", "NASDAQ"),
    SymbolMetadata("TSLA", "Tesla, Inc.", "Equity", "Consumer Discretionary", "Automobiles", "USD", "NASDAQ"),
    SymbolMetadata("JPM", "JPMorgan Chase & Co.", "Equity", "Financials", "Banks", "USD", "NYSE"),
    SymbolMetadata("V", "Visa Inc.", "Equity", "Financials", "Payments", "USD", "NYSE"),
    SymbolMetadata("MA", "Mastercard Incorporated", "Equity", "Financials", "Payments", "USD", "NYSE"),
    SymbolMetadata("UNH", "UnitedHealth Group Incorporated", "Equity", "Health Care", "Managed Health Care", "USD", "NYSE"),
    SymbolMetadata("JNJ", "Johnson & Johnson", "Equity", "Health Care", "Pharmaceuticals", "USD", "NYSE"),
    SymbolMetadata("LLY", "Eli Lilly and Company", "Equity", "Health Care", "Pharmaceuticals", "USD", "NYSE"),
    SymbolMetadata("XOM", "Exxon Mobil Corporation", "Equity", "Energy", "Integrated Oil & Gas", "USD", "NYSE"),
    SymbolMetadata("CVX", "Chevron Corporation", "Equity", "Energy", "Integrated Oil & Gas", "USD", "NYSE"),
    SymbolMetadata("PG", "Procter & Gamble Company", "Equity", "Consumer Staples", "Household Products", "USD", "NYSE"),
    SymbolMetadata("COST", "Costco Wholesale Corporation", "Equity", "Consumer Staples", "Retail", "USD", "NASDAQ"),
    SymbolMetadata("HD", "Home Depot, Inc.", "Equity", "Consumer Discretionary", "Home Improvement Retail", "USD", "NYSE"),
    SymbolMetadata("WMT", "Walmart Inc.", "Equity", "Consumer Staples", "Retail", "USD", "NYSE"),
)


class SymbolMetadataStore:
    """Persist and query static symbol metadata."""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()
        self.bootstrap_defaults()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def initialize(self) -> None:
        with sqlite3.connect(self.db_path) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS symbol_metadata (
                    symbol TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    asset_type TEXT NOT NULL,
                    sector TEXT NOT NULL,
                    industry TEXT NOT NULL,
                    currency TEXT NOT NULL,
                    exchange TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )

    def bootstrap_defaults(self) -> int:
        return self.upsert_many(DEFAULT_SYMBOL_METADATA)

    def upsert_many(self, rows: tuple[SymbolMetadata, ...] | list[SymbolMetadata]) -> int:
        values = [
            (
                item.symbol.upper(),
                item.name,
                item.asset_type,
                item.sector,
                item.industry,
                item.currency,
                item.exchange,
            )
            for item in rows
        ]
        with self.connect() as connection:
            before = connection.total_changes
            connection.executemany(
                """
                INSERT INTO symbol_metadata (
                    symbol, name, asset_type, sector, industry, currency, exchange
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(symbol) DO UPDATE SET
                    name = excluded.name,
                    asset_type = excluded.asset_type,
                    sector = excluded.sector,
                    industry = excluded.industry,
                    currency = excluded.currency,
                    exchange = excluded.exchange,
                    updated_at = CURRENT_TIMESTAMP
                """,
                values,
            )
            return connection.total_changes - before

    def get(self, symbol: str) -> dict | None:
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT symbol, name, asset_type, sector, industry, currency, exchange
                FROM symbol_metadata
                WHERE symbol = ?
                """,
                (symbol.upper(),),
            ).fetchone()
        return dict(row) if row else None

    def list_all(self) -> list[dict]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT symbol, name, asset_type, sector, industry, currency, exchange
                FROM symbol_metadata
                ORDER BY symbol
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def list_by_sector(self, sector: str) -> list[dict]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT symbol, name, asset_type, sector, industry, currency, exchange
                FROM symbol_metadata
                WHERE lower(sector) = lower(?)
                ORDER BY symbol
                """,
                (sector,),
            ).fetchall()
        return [dict(row) for row in rows]

    def list_by_asset_type(self, asset_type: str) -> list[dict]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT symbol, name, asset_type, sector, industry, currency, exchange
                FROM symbol_metadata
                WHERE lower(asset_type) = lower(?)
                ORDER BY symbol
                """,
                (asset_type,),
            ).fetchall()
        return [dict(row) for row in rows]
