"""Reusable in-memory portfolio account for historical simulation."""

from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class AccountTrade:
    date: str
    symbol: str
    side: str
    shares: int
    price: float
    notional: float
    cost: float
    cash_after: float
    realized_pnl: float
    signal_date: str | None = None
    execution_date: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class AccountSnapshot:
    date: str
    cash: float
    positions: dict[str, int]
    prices: dict[str, float]
    market_value: float
    total_equity: float
    realized_pnl: float
    unrealized_pnl: float
    cost_paid: float

    def to_dict(self) -> dict:
        return asdict(self)


class PortfolioAccount:
    """Track cash, positions, costs, and PnL through simulated time."""

    def __init__(self, initial_cash: float) -> None:
        if initial_cash <= 0:
            raise ValueError("initial_cash must be positive")
        self.initial_cash = float(initial_cash)
        self.cash = float(initial_cash)
        self.positions: dict[str, int] = {}
        self.average_cost: dict[str, float] = {}
        self.trades: list[AccountTrade] = []
        self.realized_pnl = 0.0
        self.cost_paid = 0.0

    def mark_to_market(self, date: str, prices: dict[str, float]) -> AccountSnapshot:
        normalized_prices = {
            symbol.upper(): float(price)
            for symbol, price in prices.items()
            if price is not None and float(price) > 0
        }
        market_value = 0.0
        unrealized = 0.0
        for symbol, shares in self.positions.items():
            price = normalized_prices.get(symbol)
            if price is None:
                continue
            market_value += shares * price
            unrealized += (price - self.average_cost.get(symbol, price)) * shares
        return AccountSnapshot(
            date=str(date),
            cash=round(self.cash, 6),
            positions=dict(sorted(self.positions.items())),
            prices=dict(sorted(normalized_prices.items())),
            market_value=round(market_value, 6),
            total_equity=round(self.cash + market_value, 6),
            realized_pnl=round(self.realized_pnl, 6),
            unrealized_pnl=round(unrealized, 6),
            cost_paid=round(self.cost_paid, 6),
        )

    def apply_trade(
        self,
        symbol: str,
        side: str,
        shares: int,
        price: float,
        cost: float,
        date: str,
        signal_date: str | None = None,
        execution_date: str | None = None,
    ) -> AccountTrade:
        ticker = symbol.upper().strip()
        normalized_side = side.upper().strip()
        quantity = int(shares)
        trade_price = float(price)
        trade_cost = float(cost)
        if not ticker:
            raise ValueError("symbol is required")
        if normalized_side not in {"BUY", "SELL"}:
            raise ValueError("side must be BUY or SELL")
        if quantity <= 0:
            raise ValueError("shares must be positive")
        if trade_price <= 0:
            raise ValueError("price must be positive")
        if trade_cost < 0:
            raise ValueError("cost must be non-negative")

        notional = quantity * trade_price
        realized = 0.0
        if normalized_side == "BUY":
            required_cash = notional + trade_cost
            if required_cash > self.cash + 1e-9:
                raise ValueError("insufficient cash for buy trade")
            previous_shares = self.positions.get(ticker, 0)
            previous_cost = self.average_cost.get(ticker, trade_price)
            new_shares = previous_shares + quantity
            self.average_cost[ticker] = (
                (previous_shares * previous_cost + notional) / new_shares
                if new_shares
                else trade_price
            )
            self.positions[ticker] = new_shares
            self.cash -= required_cash
        else:
            held = self.positions.get(ticker, 0)
            if quantity > held:
                raise ValueError("insufficient position for sell trade")
            average_cost = self.average_cost.get(ticker, trade_price)
            realized = (trade_price - average_cost) * quantity - trade_cost
            self.positions[ticker] = held - quantity
            if self.positions[ticker] == 0:
                del self.positions[ticker]
                self.average_cost.pop(ticker, None)
            self.cash += notional - trade_cost
            self.realized_pnl += realized

        self.cost_paid += trade_cost
        trade = AccountTrade(
            date=str(date),
            symbol=ticker,
            side=normalized_side,
            shares=quantity,
            price=round(trade_price, 6),
            notional=round(notional, 6),
            cost=round(trade_cost, 6),
            cash_after=round(self.cash, 6),
            realized_pnl=round(realized, 6),
            signal_date=signal_date,
            execution_date=execution_date,
        )
        self.trades.append(trade)
        return trade
