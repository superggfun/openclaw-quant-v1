"""SQLite persistence for simulated portfolio state."""

from __future__ import annotations

import sqlite3
from pathlib import Path


DEFAULT_ACCOUNT_NAME = "default"


class SQLitePortfolioStore:
    """Store simulated account cash, positions, and trades in SQLite."""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def initialize(self) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS accounts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    cash REAL NOT NULL,
                    initial_cash REAL NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS positions (
                    account_id INTEGER NOT NULL,
                    symbol TEXT NOT NULL,
                    qty REAL NOT NULL,
                    avg_cost REAL NOT NULL,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (account_id, symbol),
                    FOREIGN KEY (account_id) REFERENCES accounts(id) ON DELETE CASCADE
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS trades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    account_id INTEGER NOT NULL,
                    symbol TEXT NOT NULL,
                    side TEXT NOT NULL CHECK(side IN ('BUY', 'SELL')),
                    qty REAL NOT NULL,
                    price REAL NOT NULL,
                    amount REAL NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (account_id) REFERENCES accounts(id) ON DELETE CASCADE
                )
                """
            )

    def init_account(
        self,
        cash: float,
        name: str = DEFAULT_ACCOUNT_NAME,
        reset: bool = True,
    ) -> dict:
        if cash < 0:
            raise ValueError("cash must be non-negative")

        with self.connect() as connection:
            row = connection.execute(
                "SELECT id FROM accounts WHERE name = ?",
                (name,),
            ).fetchone()

            if row:
                account_id = int(row["id"])
                connection.execute(
                    """
                    UPDATE accounts
                    SET cash = ?, initial_cash = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                    """,
                    (cash, cash, account_id),
                )
            else:
                cursor = connection.execute(
                    "INSERT INTO accounts (name, cash, initial_cash) VALUES (?, ?, ?)",
                    (name, cash, cash),
                )
                account_id = int(cursor.lastrowid)

            if reset:
                connection.execute("DELETE FROM trades WHERE account_id = ?", (account_id,))
                connection.execute("DELETE FROM positions WHERE account_id = ?", (account_id,))

        account = self.get_account(name)
        if account is None:
            raise RuntimeError("failed to initialize account")
        return account

    def get_account(self, name: str = DEFAULT_ACCOUNT_NAME) -> dict | None:
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT id, name, cash, initial_cash, created_at, updated_at
                FROM accounts
                WHERE name = ?
                """,
                (name,),
            ).fetchone()
        return dict(row) if row else None

    def get_position(self, account_id: int, symbol: str) -> dict | None:
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT account_id, symbol, qty, avg_cost, updated_at
                FROM positions
                WHERE account_id = ? AND symbol = ?
                """,
                (account_id, symbol.upper()),
            ).fetchone()
        return dict(row) if row else None

    def list_positions(self, account_id: int) -> list[dict]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT account_id, symbol, qty, avg_cost, updated_at
                FROM positions
                WHERE account_id = ? AND qty > 0
                ORDER BY symbol
                """,
                (account_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def list_trades(self, account_id: int | None = None) -> list[dict]:
        query = """
            SELECT id, account_id, symbol, side, qty, price, amount, created_at
            FROM trades
        """
        params: tuple = ()
        if account_id is not None:
            query += " WHERE account_id = ?"
            params = (account_id,)
        query += " ORDER BY id"

        with self.connect() as connection:
            rows = connection.execute(query, params).fetchall()
        return [dict(row) for row in rows]

    def buy(self, account_id: int, symbol: str, qty: float, price: float) -> dict:
        ticker = symbol.upper()
        amount = qty * price

        with self.connect() as connection:
            account = self._get_account_by_id(connection, account_id)
            position = self._get_position(connection, account_id, ticker)

            if account["cash"] < amount:
                raise ValueError("insufficient cash")

            old_qty = float(position["qty"]) if position else 0.0
            old_avg_cost = float(position["avg_cost"]) if position else 0.0
            new_qty = old_qty + qty
            new_avg_cost = ((old_qty * old_avg_cost) + amount) / new_qty

            connection.execute(
                """
                UPDATE accounts
                SET cash = cash - ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (amount, account_id),
            )
            connection.execute(
                """
                INSERT INTO positions (account_id, symbol, qty, avg_cost)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(account_id, symbol) DO UPDATE SET
                    qty = excluded.qty,
                    avg_cost = excluded.avg_cost,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (account_id, ticker, new_qty, new_avg_cost),
            )
            self._insert_trade(connection, account_id, ticker, "BUY", qty, price, amount)

        position = self.get_position(account_id, ticker)
        if position is None:
            raise RuntimeError("failed to update position")
        return position

    def sell(self, account_id: int, symbol: str, qty: float, price: float) -> dict | None:
        ticker = symbol.upper()
        amount = qty * price

        with self.connect() as connection:
            self._get_account_by_id(connection, account_id)
            position = self._get_position(connection, account_id, ticker)
            if position is None or float(position["qty"]) < qty:
                raise ValueError("insufficient position")

            new_qty = float(position["qty"]) - qty

            connection.execute(
                """
                UPDATE accounts
                SET cash = cash + ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (amount, account_id),
            )
            if new_qty == 0:
                connection.execute(
                    "DELETE FROM positions WHERE account_id = ? AND symbol = ?",
                    (account_id, ticker),
                )
            else:
                connection.execute(
                    """
                    UPDATE positions
                    SET qty = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE account_id = ? AND symbol = ?
                    """,
                    (new_qty, account_id, ticker),
                )
            self._insert_trade(connection, account_id, ticker, "SELL", qty, price, amount)

        return self.get_position(account_id, ticker)

    def latest_close(self, symbol: str) -> float | None:
        try:
            with self.connect() as connection:
                row = connection.execute(
                    """
                    SELECT close
                    FROM prices
                    WHERE symbol = ?
                    ORDER BY date DESC
                    LIMIT 1
                    """,
                    (symbol.upper(),),
                ).fetchone()
        except sqlite3.OperationalError:
            return None
        return float(row["close"]) if row else None

    @staticmethod
    def _insert_trade(
        connection: sqlite3.Connection,
        account_id: int,
        symbol: str,
        side: str,
        qty: float,
        price: float,
        amount: float,
    ) -> None:
        connection.execute(
            """
            INSERT INTO trades (account_id, symbol, side, qty, price, amount)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (account_id, symbol, side, qty, price, amount),
        )

    @staticmethod
    def _get_account_by_id(connection: sqlite3.Connection, account_id: int) -> sqlite3.Row:
        row = connection.execute(
            "SELECT id, name, cash, initial_cash FROM accounts WHERE id = ?",
            (account_id,),
        ).fetchone()
        if row is None:
            raise ValueError("account is not initialized")
        return row

    @staticmethod
    def _get_position(
        connection: sqlite3.Connection,
        account_id: int,
        symbol: str,
    ) -> sqlite3.Row | None:
        return connection.execute(
            """
            SELECT account_id, symbol, qty, avg_cost
            FROM positions
            WHERE account_id = ? AND symbol = ?
            """,
            (account_id, symbol),
        ).fetchone()

