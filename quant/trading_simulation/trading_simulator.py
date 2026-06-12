"""Historical account-style trading simulator."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Mapping

import pandas as pd

from quant.alpha.alpha_engine import AlphaEngine
from quant.config import DEFAULT_SYMBOLS
from quant.cost.cost_engine import CostEngine, DEFAULT_COST_CONFIG, TradeInput
from quant.fundamental_data.fundamental_store import FundamentalStore
from quant.portfolio_construction.portfolio_construction import (
    SUPPORTED_METHODS,
    PortfolioConstructionEngine,
)
from quant.storage.sqlite_store import SQLitePriceStore
from quant.trading_simulation.portfolio_account import PortfolioAccount


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
                event_result = self._execute_rebalance_event(account, event, prices, cost_config or {})
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
            warnings=all_warnings,
            no_lookahead=True,
            report_path="",
        )
        report_path = self._write_report(result)
        return TradingSimulationResult(**(asdict(result) | {"report_path": str(report_path)}))

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
    ) -> dict:
        signal_config = dict(alpha_parameters)
        signal_config["as_of_date"] = signal_date
        alpha_result = self.alpha_engine.generate(signal_config)
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
                event["warnings"].append(f"missing execution price for {symbol}")
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
        cost_engine = CostEngine(dict(cost_config), report_dir=self.report_dir)
        for trade in sells:
            cost_report = cost_engine.estimate([trade], write_report=False)
            event["warnings"].extend(cost_report.warnings)
            estimate = cost_report.trades[0]
            applied = account.apply_trade(
                trade.symbol,
                trade.side,
                trade.shares,
                trade.price,
                estimate.total_cost,
                event["execution_date"],
                signal_date=event["signal_date"],
                execution_date=event["execution_date"],
            )
            executed.append(applied.to_dict() | {"total_cost": estimate.total_cost})

        for trade in buys:
            affordable = trade.shares
            estimate = None
            while affordable > 0:
                candidate = TradeInput(trade.symbol, trade.side, affordable, trade.price)
                candidate_report = cost_engine.estimate([candidate], write_report=False)
                event["warnings"].extend(candidate_report.warnings)
                estimate = candidate_report.trades[0]
                if estimate.notional + estimate.total_cost <= account.cash + 1e-9:
                    break
                affordable -= 1
            if affordable <= 0 or estimate is None:
                event["warnings"].append(f"insufficient cash to buy {trade.symbol}")
                continue
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
            executed.append(applied.to_dict() | {"total_cost": estimate.total_cost})

        after = account.mark_to_market(event["execution_date"], prices)
        return event | {
            "executed_trades": executed,
            "cash_before": before.cash,
            "cash_after": after.cash,
            "equity_before": before.total_equity,
            "equity_after": after.total_equity,
            "cost_paid": round(sum(trade.get("total_cost", 0.0) for trade in executed), 6),
            "warnings": self._dedupe(event["warnings"]),
        }

    def _load_price_frame(self, symbols: list[str], start: str, end: str, price_column: str) -> pd.DataFrame:
        frames = []
        for symbol in symbols:
            history = self.price_store.get_price_history(symbol, start=start, end=end)
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
        series = pd.Series(
            [row["equity"] for row in equity_curve],
            index=pd.to_datetime([row["date"] for row in equity_curve]),
            dtype="float64",
        )
        final_equity = float(series.iloc[-1])
        total_return = final_equity / initial_cash - 1.0
        returns = series.pct_change().dropna()
        years = max((series.index[-1] - series.index[0]).days / 365.25, 1 / 365.25)
        annual_return = (final_equity / initial_cash) ** (1 / years) - 1.0 if final_equity > 0 else -1.0
        volatility = float(returns.std() * (252 ** 0.5)) if len(returns) > 1 else None
        sharpe = float((returns.mean() / returns.std()) * (252 ** 0.5)) if len(returns) > 1 and returns.std() > 0 else None
        running_max = series.cummax()
        drawdowns = series / running_max - 1.0
        max_drawdown = float(drawdowns.min()) if not drawdowns.empty else None
        return {
            "total_return": round(total_return, 10),
            "annual_return": round(float(annual_return), 10),
            "volatility": round(volatility, 10) if volatility is not None else None,
            "sharpe": round(sharpe, 10) if sharpe is not None else None,
            "max_drawdown": round(max_drawdown, 10) if max_drawdown is not None else None,
            "total_cost": round(total_cost, 6),
        }

    @staticmethod
    def _normalize_symbols(symbols: list[str]) -> list[str]:
        normalized = []
        seen = set()
        for symbol in symbols:
            ticker = str(symbol).upper().strip()
            if ticker and ticker not in seen and ticker != "CASH":
                normalized.append(ticker)
                seen.add(ticker)
        if not normalized:
            raise ValueError("at least one symbol is required")
        return normalized

    @staticmethod
    def _dedupe(values: list[str]) -> list[str]:
        output = []
        seen = set()
        for value in values:
            text = str(value)
            if text and text not in seen:
                output.append(text)
                seen.add(text)
        return output

    def _write_report(self, result: TradingSimulationResult) -> Path:
        self.report_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = self.report_dir / f"trade_sim_{timestamp}.json"
        path.write_text(json.dumps(result.to_report(), indent=2), encoding="utf-8")
        return path
