"""Historical account-style trading simulator."""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import Mapping

import pandas as pd

from quant.engines.alpha.alpha_engine import AlphaEngine
from quant.config import DEFAULT_SYMBOLS
from quant.core.collections import dedupe_text
from quant.core.equity import equity_curve_stats
from quant.engines.execution.cost_engine import CostEngine, DEFAULT_COST_CONFIG, TradeInput
from quant.core.protocols.fill import Fill
from quant.core.protocols.order import Order
from quant.core.symbols import normalize_symbols
from quant.data.fundamental.fundamental_store import FundamentalStore
from quant.engines.execution.execution_constraints import DEFAULT_MARKET_REALISM_CONFIG, ExecutionConstraints
from quant.engines.execution.liquidity_model import LiquidityModel
from quant.engines.portfolio.portfolio_construction import (
    SUPPORTED_METHODS,
    PortfolioConstructionEngine,
)
from quant.reports.report_io import generate_report_path, write_json_report
from quant.storage.sqlite_store import SQLitePriceStore
from quant.engines.trading_simulation.portfolio_account import PortfolioAccount


SUPPORTED_REBALANCE_FREQUENCIES = {"daily", "weekly", "monthly"}


@dataclass(frozen=True)
class TradingSimulationResult:
    metadata: dict
    parameters: dict
    strategy: str
    portfolio_method: str
    initial_cash: float
    final_equity: float
    total_return: float
    annual_return: float | None
    volatility: float | None
    sharpe: float | None
    max_drawdown: float | None
    total_cost: float
    turnover: float
    trade_count: int
    equity_curve: list[dict]
    cash_curve: list[dict]
    positions_by_date: list[dict]
    trades: list[dict]
    rebalance_events: list[dict]
    rejected_trades: list[dict]
    market_realism: dict
    warnings: list[str]
    no_lookahead: bool
    report_path: str

    def to_report(self) -> dict:
        return asdict(self) | {"report_path": self.report_path}


class TradingSimulator:
    """Simulate a real account over historical daily bars without live execution."""

    def __init__(
        self,
        price_store: SQLitePriceStore,
        fundamental_store: FundamentalStore | None = None,
        report_dir: str | Path = "reports",
    ) -> None:
        self.price_store = price_store
        self.report_dir = Path(report_dir)
        self.fundamental_store = fundamental_store or FundamentalStore(price_store.db_path)
        self.alpha_engine = AlphaEngine(price_store, self.fundamental_store, report_dir=report_dir)
        self.portfolio_constructor = PortfolioConstructionEngine(price_store, report_dir=report_dir)

    def run(
        self,
        strategy: str = "alpha",
        start: str = "2024-01-01",
        end: str = "2025-01-01",
        initial_cash: float = 100000.0,
        rebalance_frequency: str = "monthly",
        portfolio_method: str = "equal_weight",
        cost_config: Mapping | None = None,
        alpha_config: Mapping | None = None,
        execution_price: str = "close",
        symbols: list[str] | None = None,
        portfolio_lookback: int = 60,
        market_realism_config: Mapping | None = None,
        write_report: bool = True,
        write_intermediate_reports: bool = True,
    ) -> TradingSimulationResult:
        normalized_strategy = strategy.lower().strip()
        normalized_frequency = rebalance_frequency.lower().strip()
        normalized_method = portfolio_method.lower().strip()
        normalized_price = execution_price.lower().strip()
        if normalized_strategy != "alpha":
            raise ValueError("trade-sim currently supports only strategy alpha")
        if normalized_frequency not in SUPPORTED_REBALANCE_FREQUENCIES:
            raise ValueError("rebalance_frequency must be one of: daily, weekly, monthly")
        if normalized_method not in SUPPORTED_METHODS:
            raise ValueError("portfolio_method must be one of: equal_weight, inverse_volatility, risk_parity, min_variance")
        if normalized_price not in {"close", "open"}:
            raise ValueError("execution_price must be close or open")

        warnings: list[str] = []
        realism_config = self._normalize_market_realism_config(market_realism_config, cost_config)
        runtime_cost_config = dict(cost_config or {})
        runtime_cost_config["market_realism"] = realism_config
        alpha_parameters = dict(alpha_config or {})
        universe = self._normalize_symbols(symbols or alpha_parameters.get("universe") or list(DEFAULT_SYMBOLS))
        alpha_parameters["universe"] = universe

        price_frame = self._load_price_frame(universe, start, end, normalized_price)
        if price_frame.empty or len(price_frame) < 2:
            raise ValueError("not enough stored price data for trading simulation")

        account = PortfolioAccount(initial_cash)
        dates = list(price_frame.index)
        rebalance_dates = self._rebalance_dates(dates, normalized_frequency)
        pending_events: list[dict] = []
        executed_events: list[dict] = []
        equity_curve: list[dict] = []
        cash_curve: list[dict] = []
        positions_by_date: list[dict] = []

        for index, date in enumerate(dates):
            date_text = date.strftime("%Y-%m-%d")
            prices = self._prices_for_date(price_frame, date)

            due_events = [event for event in pending_events if event["execution_date"] == date_text]
            for event in due_events:
                event_result = self._execute_rebalance_event(account, event, prices, runtime_cost_config)
                executed_events.append(event_result)
            pending_events = [event for event in pending_events if event["execution_date"] != date_text]

            if date in rebalance_dates and index + 1 < len(dates):
                execution_date = dates[index + 1].strftime("%Y-%m-%d")
                event = self._create_rebalance_event(
                    signal_date=date_text,
                    execution_date=execution_date,
                    account=account,
                    prices=prices,
                    alpha_parameters=alpha_parameters,
                    portfolio_method=normalized_method,
                    portfolio_lookback=portfolio_lookback,
                    warnings=warnings,
                    write_intermediate_reports=write_intermediate_reports,
                )
                pending_events.append(event)

            snapshot = account.mark_to_market(date_text, prices)
            equity_curve.append({"date": date_text, "equity": snapshot.total_equity})
            cash_curve.append({"date": date_text, "cash": snapshot.cash})
            positions_by_date.append(
                {
                    "date": date_text,
                    "positions": snapshot.positions,
                    "market_value": snapshot.market_value,
                    "total_equity": snapshot.total_equity,
                }
            )

        final_snapshot = account.mark_to_market(dates[-1].strftime("%Y-%m-%d"), self._prices_for_date(price_frame, dates[-1]))
        metrics = self._metrics(equity_curve, float(initial_cash), account.cost_paid)
        gross_trade_value = sum(trade.notional for trade in account.trades)
        all_warnings = self._dedupe(
            warnings
            + [
                warning
                for event in executed_events
                for warning in event.get("warnings", [])
            ]
        )
        result = TradingSimulationResult(
            metadata={
                "generated_at": datetime.now().isoformat(timespec="seconds"),
                "report_type": "trade_sim",
                "offline_historical_simulation": True,
                "live_trading": False,
                "broker_integration": False,
            },
            parameters={
                "start": start,
                "end": end,
                "rebalance_frequency": normalized_frequency,
                "execution_price": normalized_price,
                "portfolio_lookback": portfolio_lookback,
                "symbols": universe,
                "cost_config": dict(DEFAULT_COST_CONFIG) | dict(cost_config or {}),
                "market_realism_config": realism_config,
                "alpha_config": alpha_parameters,
            },
            strategy=normalized_strategy,
            portfolio_method=normalized_method,
            initial_cash=round(float(initial_cash), 6),
            final_equity=final_snapshot.total_equity,
            total_return=metrics["total_return"],
            annual_return=metrics["annual_return"],
            volatility=metrics["volatility"],
            sharpe=metrics["sharpe"],
            max_drawdown=metrics["max_drawdown"],
            total_cost=round(account.cost_paid, 6),
            turnover=round(gross_trade_value / float(initial_cash), 6) if initial_cash else 0.0,
            trade_count=len(account.trades),
            equity_curve=equity_curve,
            cash_curve=cash_curve,
            positions_by_date=positions_by_date,
            trades=[trade.to_dict() for trade in account.trades],
            rebalance_events=executed_events,
            rejected_trades=[
                rejected
                for event in executed_events
                for rejected in event.get("rejected_trades", [])
            ],
            market_realism=self._market_realism_summary(executed_events, realism_config),
            warnings=all_warnings,
            no_lookahead=True,
            report_path="",
        )
        report_path = self._write_report(result) if write_report else ""
        return replace(result, report_path=str(report_path))

    def _create_rebalance_event(
        self,
        signal_date: str,
        execution_date: str,
        account: PortfolioAccount,
        prices: dict[str, float],
        alpha_parameters: dict,
        portfolio_method: str,
        portfolio_lookback: int,
        warnings: list[str],
        write_intermediate_reports: bool,
    ) -> dict:
        signal_config = dict(alpha_parameters)
        signal_config["as_of_date"] = signal_date
        alpha_result = self.alpha_engine.generate(signal_config, write_report=write_intermediate_reports)
        selected = alpha_result.selected_symbols
        min_cash = float(signal_config.get("min_cash_weight", 0.10))
        max_weight = float(signal_config.get("max_position_weight", 0.20))

        try:
            construction = self.portfolio_constructor.construct(
                method=portfolio_method,
                symbols=selected,
                end=signal_date,
                lookback=portfolio_lookback,
                min_cash_weight=min_cash,
                max_position_weight=max_weight,
                write_report=write_intermediate_reports,
            )
            targets = construction.target_weights
            construction_report_path = construction.report_path
            construction_warnings = construction.warnings
        except ValueError as exc:
            targets = dict(alpha_result.target_weights)
            construction_report_path = None
            construction_warnings = [f"portfolio construction fallback to alpha targets: {exc}"]
            warnings.extend(construction_warnings)

        return {
            "signal_date": signal_date,
            "execution_date": execution_date,
            "alpha_report_path": alpha_result.report_path,
            "portfolio_construction_report_path": construction_report_path,
            "target_weights": targets,
            "selected_symbols": selected,
            "signal_prices": {symbol: prices.get(symbol) for symbol in selected if symbol in prices},
            "warnings": self._dedupe(list(alpha_result.warnings) + construction_warnings),
        }

    def _execute_rebalance_event(
        self,
        account: PortfolioAccount,
        event: dict,
        prices: dict[str, float],
        cost_config: Mapping,
    ) -> dict:
        before = account.mark_to_market(event["execution_date"], prices)
        realism_config = dict(DEFAULT_MARKET_REALISM_CONFIG)
        if isinstance(cost_config.get("market_realism"), Mapping):
            realism_config.update(dict(cost_config["market_realism"]))
        liquidity_model = LiquidityModel(self.price_store, lookback_days=int(realism_config["adv_lookback_days"]))
        constraints = ExecutionConstraints(realism_config)
        target_weights = {
            symbol.upper(): float(weight)
            for symbol, weight in event["target_weights"].items()
            if symbol.lower() != "cash"
        }
        sells: list[TradeInput] = []
        buys: list[TradeInput] = []
        current_symbols = set(account.positions) | set(target_weights)
        for symbol in sorted(current_symbols):
            price = prices.get(symbol)
            if price is None or price <= 0:
                event["warnings"].append(f"WARN_NO_PRICE: missing execution price for {symbol}")
                side = "SELL" if account.positions.get(symbol, 0) > 0 and target_weights.get(symbol, 0.0) == 0 else "UNKNOWN"
                event.setdefault("rejected_trades", []).append(
                    {
                        "symbol": symbol,
                        "side": side,
                        "requested_quantity": None,
                        "executed_quantity": 0,
                        "rejected_quantity": None,
                        "execution_status": "SKIPPED_NO_PRICE",
                        "execution_reason": "SKIPPED_NO_PRICE",
                    }
                )
                continue
            current_value = account.positions.get(symbol, 0) * price
            target_value = before.total_equity * target_weights.get(symbol, 0.0)
            difference = target_value - current_value
            shares = int(abs(difference) // price)
            if shares <= 0:
                continue
            trade = TradeInput(symbol=symbol, side="BUY" if difference > 0 else "SELL", shares=shares, price=price)
            if difference < 0:
                sells.append(trade)
            else:
                buys.append(trade)

        executed = []
        rejected_trades = list(event.get("rejected_trades", []))
        liquidity_snapshots: dict[str, dict] = {}
        protocol_orders: list[Order] = []
        protocol_fills: list[Fill] = []
        cost_engine = CostEngine(dict(cost_config), report_dir=self.report_dir)
        for trade in sells:
            constrained, liquidity = self._constrain_trade(
                constraints,
                liquidity_model,
                event,
                trade,
                before.total_equity,
                account.positions.get(trade.symbol, 0),
            )
            liquidity_snapshots[trade.symbol] = liquidity.to_dict()
            event["warnings"].extend(liquidity.warnings + constrained.warnings)
            if not constrained.allowed or constrained.adjusted_quantity <= 0:
                rejected_trades.append(self._rejected_trade(trade, constrained))
                continue
            executable = TradeInput(
                trade.symbol,
                trade.side,
                constrained.adjusted_quantity,
                trade.price,
                average_daily_volume=liquidity.average_daily_volume,
                volatility=liquidity.volatility,
            )
            if constrained.rejected_quantity:
                rejected_trades.append(self._rejected_trade(trade, constrained))
            cost_report = cost_engine.estimate([executable], write_report=False)
            event["warnings"].extend(cost_report.warnings)
            estimate = cost_report.trades[0]
            order = self._protocol_order(event, executable, len(protocol_orders) + 1)
            applied = account.apply_trade(
                executable.symbol,
                executable.side,
                executable.shares,
                executable.price,
                estimate.total_cost,
                event["execution_date"],
                signal_date=event["signal_date"],
                execution_date=event["execution_date"],
            )
            protocol_orders.append(order)
            protocol_fills.append(self._protocol_fill(event, order, applied, len(protocol_fills) + 1))
            executed.append(self._executed_trade_dict(applied.to_dict(), estimate, constrained, liquidity))

        for trade in buys:
            constrained, liquidity = self._constrain_trade(
                constraints,
                liquidity_model,
                event,
                trade,
                before.total_equity,
                account.positions.get(trade.symbol, 0),
            )
            liquidity_snapshots[trade.symbol] = liquidity.to_dict()
            event["warnings"].extend(liquidity.warnings + constrained.warnings)
            if not constrained.allowed or constrained.adjusted_quantity <= 0:
                rejected_trades.append(self._rejected_trade(trade, constrained))
                continue
            if constrained.rejected_quantity:
                rejected_trades.append(self._rejected_trade(trade, constrained))
            affordable, estimate, estimate_warnings = self._max_affordable_buy(
                cost_engine=cost_engine,
                trade=trade,
                max_shares=constrained.adjusted_quantity,
                cash=account.cash,
                average_daily_volume=liquidity.average_daily_volume,
                volatility=liquidity.volatility,
            )
            event["warnings"].extend(estimate_warnings)
            if affordable <= 0 or estimate is None:
                event["warnings"].append(f"insufficient cash to buy {trade.symbol}")
                rejected_trades.append(
                    {
                        "symbol": trade.symbol,
                        "side": trade.side,
                        "requested_quantity": constrained.adjusted_quantity,
                        "executed_quantity": 0,
                        "rejected_quantity": constrained.adjusted_quantity,
                        "execution_status": "REJECTED",
                        "execution_reason": "INSUFFICIENT_CASH",
                    }
                )
                continue
            executable = TradeInput(
                trade.symbol,
                trade.side,
                affordable,
                trade.price,
                average_daily_volume=liquidity.average_daily_volume,
                volatility=liquidity.volatility,
            )
            order = self._protocol_order(event, executable, len(protocol_orders) + 1)
            applied = account.apply_trade(
                trade.symbol,
                trade.side,
                affordable,
                trade.price,
                estimate.total_cost,
                event["execution_date"],
                signal_date=event["signal_date"],
                execution_date=event["execution_date"],
            )
            protocol_orders.append(order)
            protocol_fills.append(self._protocol_fill(event, order, applied, len(protocol_fills) + 1))
            adjusted_constraint = constrained.__class__(**(constrained.to_dict() | {"adjusted_quantity": affordable, "rejected_quantity": constrained.requested_quantity - affordable}))
            executed.append(self._executed_trade_dict(applied.to_dict(), estimate, adjusted_constraint, liquidity))

        after = account.mark_to_market(event["execution_date"], prices)
        account_state = account.to_protocol_state(
            event["execution_date"],
            prices,
            account_id="trade-sim",
            orders=protocol_orders,
            fills=protocol_fills,
        )
        event["warnings"].extend(f"protocol validation: {error}" for error in account_state.validate())
        deduped_warnings = self._dedupe(event["warnings"])
        return event | {
            "executed_trades": executed,
            "cash_before": before.cash,
            "cash_after": after.cash,
            "equity_before": before.total_equity,
            "equity_after": after.total_equity,
            "cost_paid": round(sum(trade.get("total_cost", 0.0) for trade in executed), 6),
            "liquidity": liquidity_snapshots,
            "rejected_trades": rejected_trades,
            "execution_warnings": deduped_warnings,
            "warnings": deduped_warnings,
        }

    @staticmethod
    def _max_affordable_buy(
        cost_engine: CostEngine,
        trade: TradeInput,
        max_shares: int,
        cash: float,
        average_daily_volume: float | None,
        volatility: float | None,
    ):
        if max_shares <= 0:
            return 0, None, []
        best_estimate = None
        best_warnings: list[str] = []
        low = 1
        high = int(max_shares)
        while low <= high:
            shares = (low + high) // 2
            candidate = TradeInput(
                trade.symbol,
                trade.side,
                shares,
                trade.price,
                average_daily_volume=average_daily_volume,
                volatility=volatility,
            )
            candidate_report = cost_engine.estimate([candidate], write_report=False)
            estimate = candidate_report.trades[0]
            if estimate.notional + estimate.total_cost <= cash + 1e-9:
                best_estimate = estimate
                best_warnings = list(candidate_report.warnings)
                low = shares + 1
            else:
                high = shares - 1
        return high, best_estimate, best_warnings

    def _constrain_trade(
        self,
        constraints: ExecutionConstraints,
        liquidity_model: LiquidityModel,
        event: dict,
        trade: TradeInput,
        equity: float,
        current_shares: int,
    ):
        liquidity = liquidity_model.snapshot(
            trade.symbol,
            event["signal_date"],
            lookback_days=int(constraints.config["adv_lookback_days"]),
            include_as_of=True,
        )
        result = constraints.apply(
            symbol=trade.symbol,
            side=trade.side,
            requested_quantity=trade.shares,
            price=trade.price,
            average_daily_volume=liquidity.average_daily_volume,
            current_shares=current_shares,
            current_equity=equity,
        )
        return result, liquidity

    @staticmethod
    def _executed_trade_dict(applied: dict, estimate, constraint, liquidity) -> dict:
        return applied | {
            "requested_quantity": constraint.requested_quantity,
            "executed_quantity": constraint.adjusted_quantity,
            "rejected_quantity": constraint.rejected_quantity,
            "execution_status": "FILLED" if constraint.rejected_quantity == 0 else "PARTIALLY_FILLED",
            "execution_reason": constraint.reason,
            "average_daily_volume": liquidity.average_daily_volume,
            "adv_participation": estimate.adv_participation,
            "slippage_cost": estimate.slippage_cost,
            "market_impact_cost": estimate.market_impact_cost,
            "liquidity_cost": estimate.liquidity_cost,
            "total_cost": estimate.total_cost,
        }

    @staticmethod
    def _rejected_trade(trade: TradeInput, constraint) -> dict:
        return {
            "symbol": trade.symbol,
            "side": trade.side,
            "requested_quantity": constraint.requested_quantity,
            "executed_quantity": constraint.adjusted_quantity if constraint.allowed else 0,
            "rejected_quantity": constraint.rejected_quantity,
            "execution_status": "PARTIALLY_FILLED" if constraint.allowed and constraint.adjusted_quantity > 0 else "REJECTED",
            "execution_reason": constraint.reason,
            "average_daily_volume": constraint.average_daily_volume,
            "adv_participation": constraint.adv_participation,
        }

    @staticmethod
    def _protocol_order(event: dict, trade: TradeInput, sequence: int) -> Order:
        return Order(
            order_id=f"{event['signal_date']}-{event['execution_date']}-{sequence}-{trade.symbol}-{trade.side}",
            symbol=trade.symbol,
            side=trade.side,
            quantity=float(trade.shares),
            target_weight=float((event.get("target_weights") or {}).get(trade.symbol, 0.0)),
            signal_date=event["signal_date"],
            created_at=event["signal_date"],
            status="FILLED",
            reason="historical rebalance simulation",
            metadata={"source": "TradingSimulator"},
        )

    @staticmethod
    def _protocol_fill(event: dict, order: Order, trade: object, sequence: int) -> Fill:
        return Fill(
            fill_id=f"{order.order_id}-fill-{sequence}",
            order_id=order.order_id,
            symbol=order.symbol,
            side=order.side,
            quantity=float(getattr(trade, "shares")),
            price=float(getattr(trade, "price")),
            cost=float(getattr(trade, "cost")),
            fill_time=event["execution_date"],
            signal_date=event["signal_date"],
            execution_date=event["execution_date"],
        )

    def _load_price_frame(self, symbols: list[str], start: str, end: str, price_column: str) -> pd.DataFrame:
        frames = []
        histories = self._price_histories(symbols, start, end)
        for symbol in symbols:
            history = histories.get(symbol)
            if history is None:
                history = histories.get(symbol.upper())
            if history is None:
                continue
            if history.empty or price_column not in history.columns:
                continue
            series = pd.Series(
                pd.to_numeric(history[price_column], errors="coerce").to_numpy(dtype="float64"),
                index=pd.to_datetime(history["date"]),
                name=symbol,
            ).dropna()
            frames.append(series[series > 0])
        if not frames:
            return pd.DataFrame()
        return pd.concat(frames, axis=1, join="outer").sort_index().ffill().dropna(how="all")

    def _price_histories(self, symbols: list[str], start: str, end: str) -> dict[str, pd.DataFrame]:
        if hasattr(self.price_store, "get_price_history_many"):
            return self.price_store.get_price_history_many(symbols, start=start, end=end)
        return {
            symbol: self.price_store.get_price_history(symbol, start=start, end=end)
            for symbol in symbols
        }

    @staticmethod
    def _rebalance_dates(dates: list[pd.Timestamp], frequency: str) -> set[pd.Timestamp]:
        if frequency == "daily":
            return set(dates[:-1])
        frame = pd.DataFrame({"date": dates})
        if frequency == "weekly":
            groups = frame.groupby(frame["date"].dt.to_period("W"))
        else:
            groups = frame.groupby(frame["date"].dt.to_period("M"))
        return {group.iloc[0]["date"] for _, group in groups if len(group) > 0}

    @staticmethod
    def _prices_for_date(frame: pd.DataFrame, date: pd.Timestamp) -> dict[str, float]:
        row = frame.loc[date].dropna()
        return {str(symbol): float(value) for symbol, value in row.items() if float(value) > 0}

    @staticmethod
    def _metrics(equity_curve: list[dict], initial_cash: float, total_cost: float) -> dict:
        if not equity_curve:
            return {
                "total_return": 0.0,
                "annual_return": None,
                "volatility": None,
                "sharpe": None,
                "max_drawdown": None,
                "total_cost": total_cost,
            }
        stats = equity_curve_stats(
            equity_curve,
            initial_cash,
            min_return_count_for_volatility=2,
            empty_volatility=None,
            empty_sharpe=None,
            nonpositive_annual_return=-1.0,
        )
        return {
            "total_return": round(stats.total_return, 10),
            "annual_return": round(stats.annual_return, 10),
            "volatility": round(stats.volatility, 10) if stats.volatility is not None else None,
            "sharpe": round(stats.sharpe, 10) if stats.sharpe is not None else None,
            "max_drawdown": round(stats.max_drawdown, 10) if stats.max_drawdown is not None else None,
            "total_cost": round(total_cost, 6),
        }

    @staticmethod
    def _normalize_symbols(symbols: list[str]) -> list[str]:
        return normalize_symbols(symbols, exclude={"CASH"}, require_non_empty=True)

    @staticmethod
    def _dedupe(values: list[str]) -> list[str]:
        return dedupe_text(values)

    @staticmethod
    def _normalize_market_realism_config(market_realism_config: Mapping | None, cost_config: Mapping | None) -> dict:
        merged = dict(DEFAULT_MARKET_REALISM_CONFIG)
        cost_values = dict(cost_config or {})
        nested = cost_values.get("market_realism")
        if isinstance(nested, Mapping):
            merged.update(dict(nested))
        merged.update(dict(market_realism_config or {}))
        if "min_trade_notional" in cost_values and not (isinstance(nested, Mapping) and "min_trade_notional" in nested) and not (market_realism_config and "min_trade_notional" in market_realism_config):
            merged["min_trade_notional"] = cost_values["min_trade_notional"]
        return merged

    @staticmethod
    def _market_realism_summary(events: list[dict], config: dict) -> dict:
        executed = [trade for event in events for trade in event.get("executed_trades", [])]
        rejected = [trade for event in events for trade in event.get("rejected_trades", [])]
        return {
            "config": config,
            "executed_trade_count": len(executed),
            "rejected_trade_count": len(rejected),
            "total_requested_quantity": sum(int(trade.get("requested_quantity") or trade.get("shares") or 0) for trade in executed + rejected),
            "total_executed_quantity": sum(int(trade.get("executed_quantity") or trade.get("shares") or 0) for trade in executed),
            "total_rejected_quantity": sum(int(trade.get("rejected_quantity") or 0) for trade in executed + rejected),
            "total_slippage": round(sum(float(trade.get("slippage_cost") or 0.0) for trade in executed), 6),
            "total_market_impact": round(sum(float(trade.get("market_impact_cost") or 0.0) for trade in executed), 6),
            "total_liquidity_cost": round(sum(float(trade.get("liquidity_cost") or 0.0) for trade in executed), 6),
            "largest_constrained_trades": sorted(
                rejected,
                key=lambda item: int(item.get("rejected_quantity") or 0),
                reverse=True,
            )[:5],
        }

    def _write_report(self, result: TradingSimulationResult) -> Path:
        return write_json_report(
            generate_report_path(self.report_dir, "trade_sim"),
            result.to_report(),
        )
