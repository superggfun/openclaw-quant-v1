"""Pure calculation engine for portfolio allocation and rebalance plans."""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Mapping

from quant.storage.portfolio_store import DEFAULT_ACCOUNT_NAME, SQLitePortfolioStore


DEFAULT_COMMISSION_RATE = 0.001


@dataclass(frozen=True)
class AllocationItem:
    symbol: str
    current_value: float
    current_weight: float
    qty: float
    price: float | None


@dataclass(frozen=True)
class AllocationSnapshot:
    cash: float
    total_assets: float
    items: list[AllocationItem]


@dataclass(frozen=True)
class RebalanceItem:
    symbol: str
    current_value: float
    current_weight: float
    target_weight: float
    target_value: float
    difference: float
    price: float | None
    action: str
    qty: int
    estimated_trade_cost: float


@dataclass(frozen=True)
class RebalancePlan:
    total_assets: float
    cash_before: float
    cash_after_rebalance: float
    commission_rate: float
    estimated_total_commission: float
    items: list[RebalanceItem]
    warnings: list[str]
    report_path: str

    def to_report(self) -> dict:
        return {
            "total_assets": self.total_assets,
            "cash_before": self.cash_before,
            "cash_after_rebalance": self.cash_after_rebalance,
            "commission_rate": self.commission_rate,
            "estimated_total_commission": self.estimated_total_commission,
            "items": [asdict(item) for item in self.items],
            "warnings": self.warnings,
        }


class RebalanceEngine:
    """Calculate allocation snapshots and rebalance suggestions.

    The engine is deliberately side-effect free for portfolio state: it does not
    update positions, cash, or trades. Its only write is an optional JSON report.
    """

    def __init__(
        self,
        store: SQLitePortfolioStore,
        account_name: str = DEFAULT_ACCOUNT_NAME,
        report_dir: str | Path = "reports",
    ) -> None:
        self.store = store
        self.account_name = account_name
        self.report_dir = Path(report_dir)

    def allocation(self) -> AllocationSnapshot:
        account = self._require_account()
        cash = float(account["cash"])
        position_rows = self.store.list_positions(account["id"])
        items: list[AllocationItem] = []
        position_value = 0.0

        for position in position_rows:
            symbol = position["symbol"]
            price = self.store.latest_close(symbol)
            if price is None:
                raise ValueError(f"latest price is missing for {symbol}")
            current_value = float(position["qty"]) * price
            position_value += current_value
            items.append(
                AllocationItem(
                    symbol=symbol,
                    current_value=current_value,
                    current_weight=0.0,
                    qty=float(position["qty"]),
                    price=price,
                )
            )

        total_assets = cash + position_value
        weighted_items = [
            AllocationItem(
                symbol=item.symbol,
                current_value=item.current_value,
                current_weight=self._weight(item.current_value, total_assets),
                qty=item.qty,
                price=item.price,
            )
            for item in items
        ]
        weighted_items.insert(
            0,
            AllocationItem(
                symbol="cash",
                current_value=cash,
                current_weight=self._weight(cash, total_assets),
                qty=0.0,
                price=None,
            ),
        )
        return AllocationSnapshot(cash=cash, total_assets=total_assets, items=weighted_items)

    def plan(
        self,
        targets: Mapping[str, float],
        commission_rate: float = DEFAULT_COMMISSION_RATE,
    ) -> RebalancePlan:
        if commission_rate < 0:
            raise ValueError("commission must be non-negative")

        normalized_targets = self._normalize_targets(targets)
        snapshot = self.allocation()

        symbols = sorted(
            {
                item.symbol
                for item in snapshot.items
                if item.symbol != "cash"
            }
            | {symbol for symbol in normalized_targets if symbol != "cash"}
        )
        current_by_symbol = {item.symbol: item for item in snapshot.items}
        items: list[RebalanceItem] = []
        sell_proceeds = 0.0
        buy_spend = 0.0
        estimated_total_commission = 0.0
        warnings: list[str] = []

        for symbol in symbols:
            current = current_by_symbol.get(symbol)
            price = current.price if current else self.store.latest_close(symbol)
            if price is None:
                raise ValueError(f"latest price is missing for {symbol}")

            current_value = current.current_value if current else 0.0
            current_weight = current.current_weight if current else 0.0
            target_weight = normalized_targets.get(symbol, 0.0)
            target_value = snapshot.total_assets * target_weight
            difference = target_value - current_value
            action = "HOLD"
            qty = 0
            estimated_trade_cost = 0.0

            if difference > 0:
                qty = math.floor(difference / (price * (1.0 + commission_rate)))
                if qty > 0:
                    action = "BUY"
                    notional = qty * price
                    estimated_trade_cost = notional * commission_rate
                    buy_spend += notional
                    estimated_total_commission += estimated_trade_cost
                    remaining_difference = difference - notional
                    if remaining_difference + 1e-9 >= price:
                        warnings.append(f"insufficient cash to fully reach target allocation for {symbol}")
            elif difference < 0:
                max_qty = math.floor((current.qty if current else 0.0))
                qty = min(max_qty, math.floor(abs(difference) / price))
                if qty > 0:
                    action = "SELL"
                    notional = qty * price
                    estimated_trade_cost = notional * commission_rate
                    sell_proceeds += notional
                    estimated_total_commission += estimated_trade_cost

            items.append(
                RebalanceItem(
                    symbol=symbol,
                    current_value=current_value,
                    current_weight=current_weight,
                    target_weight=target_weight,
                    target_value=target_value,
                    difference=difference,
                    price=price,
                    action=action,
                    qty=qty,
                    estimated_trade_cost=estimated_trade_cost,
                )
            )

        cash_target_value = snapshot.total_assets * normalized_targets.get("cash", 0.0)
        cash_after = snapshot.cash + sell_proceeds - buy_spend - estimated_total_commission
        if cash_after < 0:
            warnings.append("insufficient cash for estimated buys and commissions")
        if cash_after + 1e-9 < cash_target_value:
            warnings.append("cash_after_rebalance is below target cash allocation")

        items.insert(
            0,
            RebalanceItem(
                symbol="cash",
                current_value=snapshot.cash,
                current_weight=self._weight(snapshot.cash, snapshot.total_assets),
                target_weight=normalized_targets.get("cash", 0.0),
                target_value=cash_target_value,
                difference=cash_target_value - snapshot.cash,
                price=None,
                action="HOLD",
                qty=0,
                estimated_trade_cost=0.0,
            ),
        )

        report_path = self._write_report(
            RebalancePlan(
                total_assets=snapshot.total_assets,
                cash_before=snapshot.cash,
                cash_after_rebalance=cash_after,
                commission_rate=commission_rate,
                estimated_total_commission=estimated_total_commission,
                items=items,
                warnings=warnings,
                report_path="",
            )
        )

        return RebalancePlan(
            total_assets=snapshot.total_assets,
            cash_before=snapshot.cash,
            cash_after_rebalance=cash_after,
            commission_rate=commission_rate,
            estimated_total_commission=estimated_total_commission,
            items=items,
            warnings=warnings,
            report_path=str(report_path),
        )

    def _require_account(self) -> dict:
        account = self.store.get_account(self.account_name)
        if account is None:
            raise ValueError("account is not initialized")
        return account

    @staticmethod
    def _normalize_targets(targets: Mapping[str, float]) -> dict[str, float]:
        if not targets:
            raise ValueError("targets must not be empty")

        normalized: dict[str, float] = {}
        for symbol, weight in targets.items():
            ticker = symbol.lower() if symbol.lower() == "cash" else symbol.upper().strip()
            value = float(weight)
            if not ticker:
                raise ValueError("target symbol must not be empty")
            if value < 0:
                raise ValueError("target weights must be non-negative")
            normalized[ticker] = value

        total_weight = sum(normalized.values())
        if abs(total_weight - 1.0) > 0.000001:
            raise ValueError("target weights must sum to 1.0")

        return normalized

    @staticmethod
    def _weight(value: float, total_assets: float) -> float:
        if total_assets <= 0:
            return 0.0
        return value / total_assets

    def _write_report(self, plan: RebalancePlan) -> Path:
        self.report_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = self.report_dir / f"rebalance_{timestamp}.json"
        path.write_text(json.dumps(plan.to_report(), indent=2), encoding="utf-8")
        return path
