"""Simulated execution engine for rebalance suggestions."""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Mapping

from quant.cost.cost_engine import CostEngine, TradeInput
from quant.core_protocols.fill import Fill
from quant.core_protocols.order import Order
from quant.core_protocols.protocol_validation import validate_fill_references_order
from quant.rebalance.rebalance_engine import RebalanceEngine
from quant.storage.portfolio_store import DEFAULT_ACCOUNT_NAME, SQLitePortfolioStore
from quant.storage.sqlite_store import SQLitePriceStore


EXECUTION_MODES = {"immediate", "next_day_open", "twap", "partial_fill"}


@dataclass(frozen=True)
class IntendedTrade:
    symbol: str
    side: str
    shares: int
    price: float
    notional: float


@dataclass(frozen=True)
class ExecutedTrade:
    symbol: str
    side: str
    shares: int
    price: float
    notional: float
    fixed_fee: float
    commission: float
    slippage_cost: float
    total_cost: float
    cost_ratio: float
    batch: int
    executed_at: str


@dataclass(frozen=True)
class UnfilledTrade:
    symbol: str
    side: str
    shares: int
    price: float
    reason: str


@dataclass(frozen=True)
class ExecutionResult:
    mode: str
    target_allocation: dict[str, float]
    intended_trades: list[IntendedTrade]
    executed_trades: list[ExecutedTrade]
    unfilled_trades: list[UnfilledTrade]
    execution_costs: dict
    slippage_estimate: float
    final_cash: float
    final_positions: dict[str, float]
    warnings: list[str]
    report_path: str

    def to_report(self) -> dict:
        return {
            "mode": self.mode,
            "target_allocation": self.target_allocation,
            "intended_trades": [asdict(trade) for trade in self.intended_trades],
            "executed_trades": [asdict(trade) for trade in self.executed_trades],
            "unfilled_trades": [asdict(trade) for trade in self.unfilled_trades],
            "execution_costs": self.execution_costs,
            "slippage_estimate": self.slippage_estimate,
            "final_cash": self.final_cash,
            "final_positions": self.final_positions,
            "warnings": self.warnings,
        }


class ExecutionEngine:
    """Simulate how rebalance suggestions would be filled.

    The engine is side-effect free for portfolio state. It reads the simulated
    account, positions, target allocation, and prices, then writes a JSON report.
    """

    def __init__(
        self,
        price_store: SQLitePriceStore,
        portfolio_store: SQLitePortfolioStore,
        account_name: str = DEFAULT_ACCOUNT_NAME,
        report_dir: str | Path = "reports",
    ) -> None:
        self.price_store = price_store
        self.portfolio_store = portfolio_store
        self.account_name = account_name
        self.report_dir = Path(report_dir)
        self.rebalance_engine = RebalanceEngine(
            portfolio_store,
            account_name=account_name,
            report_dir=report_dir,
        )

    def run(
        self,
        targets: Mapping[str, float],
        mode: str = "immediate",
        execution_date: str | None = None,
        cost_config: dict | None = None,
        twap_slices: int = 4,
        fill_ratio: float = 0.5,
    ) -> ExecutionResult:
        mode = mode.lower()
        self._validate(mode, twap_slices, fill_ratio)

        normalized_targets = self._normalize_targets(targets)
        account = self._require_account()
        positions = self._current_positions(account["id"])
        cash = float(account["cash"])
        cost_engine = CostEngine(cost_config or {}, report_dir=self.report_dir)
        plan = self.rebalance_engine.plan(normalized_targets)

        intended_trades = self._intended_trades(plan)
        executed_trades: list[ExecutedTrade] = []
        unfilled_trades: list[UnfilledTrade] = []
        warnings = list(plan.warnings)
        protocol_orders: list[Order] = []
        protocol_fills: list[Fill] = []

        for intended in intended_trades:
            price, executed_at = self._execution_details(intended, mode, execution_date, warnings)
            for batch, shares in enumerate(self._fill_batches(intended.shares, mode, twap_slices, fill_ratio), start=1):
                if shares <= 0:
                    continue

                fillable_shares = shares
                if intended.side == "SELL":
                    fillable_shares = min(fillable_shares, math.floor(positions.get(intended.symbol, 0.0)))
                    if fillable_shares <= 0:
                        unfilled_trades.append(
                            UnfilledTrade(intended.symbol, intended.side, shares, price, "insufficient position")
                        )
                        warnings.append(f"{intended.symbol} sell was not fully filled because position is insufficient")
                        continue
                else:
                    fillable_shares = self._affordable_shares(
                        intended.symbol,
                        intended.side,
                        fillable_shares,
                        price,
                        cash,
                        cost_engine,
                    )
                    if fillable_shares <= 0:
                        unfilled_trades.append(
                            UnfilledTrade(intended.symbol, intended.side, shares, price, "insufficient cash")
                        )
                        warnings.append(f"{intended.symbol} buy was not filled because cash is insufficient")
                        continue

                if fillable_shares < shares:
                    unfilled_trades.append(
                        UnfilledTrade(
                            intended.symbol,
                            intended.side,
                            shares - fillable_shares,
                            price,
                            "partial execution limit",
                        )
                    )

                trade_cost = cost_engine.estimate(
                    [TradeInput(intended.symbol, intended.side, fillable_shares, price)],
                    write_report=False,
                )
                if trade_cost.warnings:
                    warnings.extend(trade_cost.warnings)
                cost = trade_cost.trades[0]
                order = Order(
                    order_id=f"execution-{len(protocol_orders) + 1}-{intended.symbol}-{intended.side}",
                    symbol=intended.symbol,
                    side=intended.side,
                    quantity=float(cost.shares),
                    target_weight=normalized_targets.get(intended.symbol),
                    signal_date=executed_at,
                    created_at=executed_at,
                    status="FILLED",
                    reason=f"{mode} execution simulation",
                    metadata={"source": "ExecutionEngine", "batch": batch},
                )
                fill = Fill(
                    fill_id=f"{order.order_id}-fill",
                    order_id=order.order_id,
                    symbol=cost.symbol,
                    side=cost.side,
                    quantity=float(cost.shares),
                    price=float(cost.price),
                    cost=float(cost.total_cost),
                    fill_time=executed_at,
                    signal_date=executed_at,
                    execution_date=executed_at,
                )
                validation_errors = order.validate() + fill.validate() + validate_fill_references_order(fill, [order])
                warnings.extend(f"protocol validation: {error}" for error in validation_errors)
                protocol_orders.append(order)
                protocol_fills.append(fill)
                executed_trades.append(
                    ExecutedTrade(
                        symbol=cost.symbol,
                        side=cost.side,
                        shares=cost.shares,
                        price=cost.price,
                        notional=cost.notional,
                        fixed_fee=cost.fixed_fee,
                        commission=cost.commission,
                        slippage_cost=cost.slippage_cost,
                        total_cost=cost.total_cost,
                        cost_ratio=cost.cost_ratio,
                        batch=batch,
                        executed_at=executed_at,
                    )
                )

                if intended.side == "SELL":
                    cash += cost.notional - cost.total_cost
                    positions[intended.symbol] = max(0.0, positions.get(intended.symbol, 0.0) - cost.shares)
                else:
                    cash -= cost.notional + cost.total_cost
                    positions[intended.symbol] = positions.get(intended.symbol, 0.0) + cost.shares

            if mode == "partial_fill":
                filled = sum(
                    trade.shares
                    for trade in executed_trades
                    if trade.symbol == intended.symbol and trade.side == intended.side
                )
                remaining = intended.shares - filled
                if remaining > 0 and not any(
                    trade.symbol == intended.symbol and trade.side == intended.side and trade.shares == remaining
                    for trade in unfilled_trades
                ):
                    unfilled_trades.append(
                        UnfilledTrade(intended.symbol, intended.side, remaining, price, "partial fill simulation")
                    )

        if not intended_trades:
            warnings.append("rebalance produced no executable trades")

        final_positions = {
            symbol: qty
            for symbol, qty in sorted(positions.items())
            if qty > 0
        }
        execution_costs = self._cost_summary(executed_trades)
        result = ExecutionResult(
            mode=mode,
            target_allocation=normalized_targets,
            intended_trades=intended_trades,
            executed_trades=executed_trades,
            unfilled_trades=unfilled_trades,
            execution_costs=execution_costs,
            slippage_estimate=execution_costs["total_slippage"],
            final_cash=cash,
            final_positions=final_positions,
            warnings=warnings,
            report_path="",
        )
        report_path = self._write_report(result)
        return ExecutionResult(
            mode=result.mode,
            target_allocation=result.target_allocation,
            intended_trades=result.intended_trades,
            executed_trades=result.executed_trades,
            unfilled_trades=result.unfilled_trades,
            execution_costs=result.execution_costs,
            slippage_estimate=result.slippage_estimate,
            final_cash=result.final_cash,
            final_positions=result.final_positions,
            warnings=result.warnings,
            report_path=str(report_path),
        )

    def _require_account(self) -> dict:
        account = self.portfolio_store.get_account(self.account_name)
        if account is None:
            raise ValueError("account is not initialized")
        return account

    def _current_positions(self, account_id: int) -> dict[str, float]:
        return {
            row["symbol"]: float(row["qty"])
            for row in self.portfolio_store.list_positions(account_id)
        }

    @staticmethod
    def _normalize_targets(targets: Mapping[str, float]) -> dict[str, float]:
        normalized: dict[str, float] = {}
        for symbol, weight in targets.items():
            ticker = symbol.lower() if symbol.lower() == "cash" else symbol.upper().strip()
            normalized[ticker] = float(weight)
        return normalized

    @staticmethod
    def _intended_trades(plan) -> list[IntendedTrade]:
        trades = []
        for item in plan.items:
            if item.action not in {"BUY", "SELL"} or item.qty <= 0 or item.price is None:
                continue
            trades.append(
                IntendedTrade(
                    symbol=item.symbol,
                    side=item.action,
                    shares=int(item.qty),
                    price=float(item.price),
                    notional=float(item.qty) * float(item.price),
                )
            )
        return trades

    def _execution_details(
        self,
        intended: IntendedTrade,
        mode: str,
        execution_date: str | None,
        warnings: list[str],
    ) -> tuple[float, str]:
        if mode == "next_day_open":
            next_open = self._next_day_open(intended.symbol, execution_date)
            if next_open is not None:
                return next_open
            warnings.append(f"next-day open price is missing for {intended.symbol}; using rebalance price")
            return intended.price, self._fallback_executed_at(intended.symbol, execution_date)

        if execution_date is not None:
            price = self._price_on_date(intended.symbol, execution_date, "close")
            if price is not None:
                return price, execution_date
            warnings.append(f"close price on {execution_date} is missing for {intended.symbol}; using rebalance price")
        return intended.price, self._fallback_executed_at(intended.symbol, execution_date)

    def _price_on_date(self, symbol: str, date_text: str, field: str) -> float | None:
        rows = self.price_store.get_price_history(symbol, start=date_text, end=date_text)
        if rows.empty:
            return None
        return float(rows.iloc[0][field])

    def _next_day_open(self, symbol: str, execution_date: str | None) -> tuple[float, str] | None:
        if execution_date is None:
            rows = self.price_store.get_prices(symbol, limit=1)
            return (float(rows[0]["open"]), str(rows[0]["date"])) if rows else None

        rows = self.price_store.get_price_history(symbol, start=execution_date)
        if rows.empty:
            return None
        rows = rows[rows["date"] > execution_date]
        if rows.empty:
            return None
        return float(rows.iloc[0]["open"]), str(rows.iloc[0]["date"])

    @staticmethod
    def _fill_batches(shares: int, mode: str, twap_slices: int, fill_ratio: float) -> list[int]:
        if mode == "twap":
            base = shares // twap_slices
            remainder = shares % twap_slices
            return [base + (1 if index < remainder else 0) for index in range(twap_slices)]
        if mode == "partial_fill":
            return [math.floor(shares * fill_ratio)]
        return [shares]

    @staticmethod
    def _affordable_shares(
        symbol: str,
        side: str,
        shares: int,
        price: float,
        cash: float,
        cost_engine: CostEngine,
    ) -> int:
        low = 0
        high = shares
        affordable = 0
        while low <= high:
            mid = (low + high) // 2
            if mid == 0:
                low = mid + 1
                continue
            estimate = cost_engine.estimate([TradeInput(symbol, side, mid, price)], write_report=False)
            required_cash = estimate.trades[0].notional + estimate.trades[0].total_cost
            if required_cash <= cash + 1e-9:
                affordable = mid
                low = mid + 1
            else:
                high = mid - 1
        return affordable

    @staticmethod
    def _cost_summary(trades: list[ExecutedTrade]) -> dict:
        gross_trade_value = sum(trade.notional for trade in trades)
        total_commission = sum(trade.fixed_fee + trade.commission for trade in trades)
        total_slippage = sum(trade.slippage_cost for trade in trades)
        total_cost = sum(trade.total_cost for trade in trades)
        return {
            "gross_trade_value": gross_trade_value,
            "total_commission": total_commission,
            "total_slippage": total_slippage,
            "total_cost": total_cost,
            "total_cost_ratio": total_cost / gross_trade_value if gross_trade_value else 0.0,
        }

    def _fallback_executed_at(self, symbol: str, execution_date: str | None) -> str:
        if execution_date is not None:
            return execution_date
        return self.price_store.latest_date(symbol) or "latest"

    @staticmethod
    def _validate(mode: str, twap_slices: int, fill_ratio: float) -> None:
        if mode not in EXECUTION_MODES:
            raise ValueError("execution mode must be one of: immediate, next_day_open, twap, partial_fill")
        if twap_slices <= 0:
            raise ValueError("twap_slices must be positive")
        if not 0 <= fill_ratio <= 1:
            raise ValueError("fill_ratio must be between 0 and 1")

    def _write_report(self, result: ExecutionResult) -> Path:
        self.report_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = self.report_dir / f"execution_{timestamp}.json"
        path.write_text(json.dumps(result.to_report(), indent=2), encoding="utf-8")
        return path
