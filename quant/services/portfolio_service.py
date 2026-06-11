"""Simulated portfolio state management."""

from __future__ import annotations

from dataclasses import dataclass

from quant.storage.portfolio_store import DEFAULT_ACCOUNT_NAME, SQLitePortfolioStore


@dataclass(frozen=True)
class PortfolioPosition:
    symbol: str
    qty: float
    avg_cost: float
    current_price: float | None
    market_value: float | None
    unrealized_pnl: float | None


@dataclass(frozen=True)
class PortfolioSnapshot:
    cash: float
    initial_cash: float
    positions: list[PortfolioPosition]
    total_assets: float


class PortfolioService:
    """Apply simulated buy/sell rules and build portfolio snapshots."""

    def __init__(
        self,
        store: SQLitePortfolioStore,
        account_name: str = DEFAULT_ACCOUNT_NAME,
    ) -> None:
        self.store = store
        self.account_name = account_name

    def init_account(self, cash: float) -> dict:
        return self.store.init_account(cash, name=self.account_name, reset=True)

    def buy(self, symbol: str, qty: float, price: float) -> dict:
        self._validate_order(symbol, qty, price)
        account = self._require_account()
        return self.store.buy(account_id=account["id"], symbol=symbol, qty=qty, price=price)

    def sell(self, symbol: str, qty: float, price: float) -> dict | None:
        self._validate_order(symbol, qty, price)
        account = self._require_account()
        return self.store.sell(account_id=account["id"], symbol=symbol, qty=qty, price=price)

    def trades(self) -> list[dict]:
        account = self._require_account()
        return self.store.list_trades(account_id=account["id"])

    def portfolio(self) -> PortfolioSnapshot:
        account = self._require_account()
        positions = []
        total_market_value = 0.0

        for position in self.store.list_positions(account["id"]):
            current_price = self.store.latest_close(position["symbol"])
            market_value = None
            unrealized_pnl = None
            if current_price is not None:
                market_value = float(position["qty"]) * current_price
                unrealized_pnl = market_value - (float(position["qty"]) * float(position["avg_cost"]))
                total_market_value += market_value

            positions.append(
                PortfolioPosition(
                    symbol=position["symbol"],
                    qty=float(position["qty"]),
                    avg_cost=float(position["avg_cost"]),
                    current_price=current_price,
                    market_value=market_value,
                    unrealized_pnl=unrealized_pnl,
                )
            )

        return PortfolioSnapshot(
            cash=float(account["cash"]),
            initial_cash=float(account["initial_cash"]),
            positions=positions,
            total_assets=float(account["cash"]) + total_market_value,
        )

    def _require_account(self) -> dict:
        account = self.store.get_account(self.account_name)
        if account is None:
            raise ValueError("account is not initialized")
        return account

    @staticmethod
    def _validate_order(symbol: str, qty: float, price: float) -> None:
        if not symbol.strip():
            raise ValueError("symbol must not be empty")
        if qty <= 0:
            raise ValueError("qty must be positive")
        if price <= 0:
            raise ValueError("price must be positive")

