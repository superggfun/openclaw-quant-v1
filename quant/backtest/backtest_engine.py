"""Deterministic daily portfolio backtest engine."""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

import pandas as pd

from quant.alpha.alpha_engine import AlphaEngine
from quant.config import DEFAULT_SYMBOLS
from quant.cost.cost_engine import CostEngine, TradeInput
from quant.optimizer.optimizer_engine import DEFAULT_CONSTRAINTS
from quant.risk.risk_engine import DEFAULT_INDUSTRY_MAP
from quant.storage.sqlite_store import SQLitePriceStore


@dataclass(frozen=True)
class PortfolioBacktestTrade:
    date: str
    symbol: str
    side: str
    shares: int
    price: float
    notional: float
    total_cost: float
    cash_after: float
    signal_date: str | None = None
    execution_date: str | None = None
    signal_price: float | None = None
    execution_price: float | None = None


@dataclass(frozen=True)
class PortfolioBacktestMetrics:
    final_value: float
    total_return: float
    annual_return: float
    max_drawdown: float
    volatility: float
    sharpe_ratio: float
    trade_count: int
    turnover: float
    total_cost: float
    cash_ratio: float


@dataclass(frozen=True)
class PortfolioBacktestResult:
    start: str
    end: str
    initial_cash: float
    mode: str
    rebalance_frequency: str
    metrics: PortfolioBacktestMetrics
    trades: list[PortfolioBacktestTrade]
    equity_curve: list[dict]
    report_path: str
    strategy: str = "portfolio"
    no_lookahead: bool = False
    signal_execution_lag: str | None = None
    alpha_config: dict | None = None
    excluded_symbols_per_rebalance: dict[str, dict[str, str]] | None = None

    def to_report(self) -> dict:
        return {
            "start": self.start,
            "end": self.end,
            "initial_cash": self.initial_cash,
            "strategy": self.strategy,
            "mode": self.mode,
            "rebalance_frequency": self.rebalance_frequency,
            "no_lookahead": self.no_lookahead,
            "signal_execution_lag": self.signal_execution_lag,
            "alpha_config": self.alpha_config,
            "excluded_symbols_per_rebalance": self.excluded_symbols_per_rebalance or {},
            "metrics": asdict(self.metrics),
            "trades": [asdict(trade) for trade in self.trades],
            "equity_curve": self.equity_curve,
        }


class PortfolioBacktestEngine:
    """Backtest optimizer -> rebalance -> cost flow using stored daily prices."""

    def __init__(
        self,
        price_store: SQLitePriceStore,
        report_dir: str | Path = "reports",
        industry_map: dict[str, str] | None = None,
    ) -> None:
        self.price_store = price_store
        self.report_dir = Path(report_dir)
        self.industry_map = industry_map or DEFAULT_INDUSTRY_MAP

    def run(
        self,
        start: str,
        end: str,
        initial_cash: float = 100000.0,
        mode: str = "equal_weight",
        rebalance_frequency: str = "monthly",
        symbols: list[str] | None = None,
        constraints: dict | None = None,
        cost_config: dict | None = None,
        strategy: str = "portfolio",
        execution_price: str = "close",
        alpha_config: dict | None = None,
        alpha_pipeline_config: dict | None = None,
    ) -> PortfolioBacktestResult:
        self._validate(start, end, initial_cash, mode, rebalance_frequency, strategy, execution_price)
        if strategy == "alpha":
            return self._run_alpha_strategy(
                start=start,
                end=end,
                initial_cash=initial_cash,
                rebalance_frequency=rebalance_frequency,
                cost_config=cost_config,
                execution_price=execution_price,
                alpha_config=alpha_config or {},
                alpha_pipeline_config=alpha_pipeline_config,
            )

        universe = self._normalize_symbols(symbols or list(DEFAULT_SYMBOLS))
        price_frame = self._load_price_frame(universe, start, end)
        active_symbols = list(price_frame.columns)
        if not active_symbols:
            raise ValueError("no price data found for backtest universe")

        constraints = self._normalize_constraints(constraints or {})
        cost_engine = CostEngine(cost_config or {})
        cash = float(initial_cash)
        positions = {symbol: 0 for symbol in active_symbols}
        trades: list[PortfolioBacktestTrade] = []
        equity_curve: list[dict] = []
        gross_trade_value = 0.0
        total_cost = 0.0

        for index, (date_value, prices) in enumerate(price_frame.iterrows()):
            date_text = date_value.strftime("%Y-%m-%d")
            price_map = {symbol: float(prices[symbol]) for symbol in active_symbols}

            if self._is_rebalance_date(price_frame.index, index, rebalance_frequency):
                target_weights = self._target_weights(
                    mode=mode,
                    symbols=active_symbols,
                    price_frame=price_frame.loc[:date_value],
                    constraints=constraints,
                )
                day_trades, cash, positions = self._rebalance(
                    date_text=date_text,
                    cash=cash,
                    positions=positions,
                    prices=price_map,
                    target_weights=target_weights,
                    cost_engine=cost_engine,
                )
                trades.extend(day_trades)
                gross_trade_value += sum(trade.notional for trade in day_trades)
                total_cost += sum(trade.total_cost for trade in day_trades)

            equity = cash + sum(positions[symbol] * price_map[symbol] for symbol in active_symbols)
            equity_curve.append(
                {
                    "date": date_text,
                    "cash": cash,
                    "equity": equity,
                    "positions": dict(positions),
                    "last_signal_date": date_text,
                    "last_execution_date": date_text,
                }
            )

        metrics = self._metrics(
            equity_curve=equity_curve,
            initial_cash=initial_cash,
            gross_trade_value=gross_trade_value,
            total_cost=total_cost,
            trade_count=len(trades),
        )
        result = PortfolioBacktestResult(
            start=start,
            end=end,
            initial_cash=float(initial_cash),
            mode=mode,
            rebalance_frequency=rebalance_frequency,
            metrics=metrics,
            trades=trades,
            equity_curve=equity_curve,
            report_path="",
            strategy=strategy,
            no_lookahead=False,
            signal_execution_lag="same_day_close_simple_mode",
            alpha_config=None,
            excluded_symbols_per_rebalance={},
        )
        report_path = self._write_report(result)
        return PortfolioBacktestResult(
            start=result.start,
            end=result.end,
            initial_cash=result.initial_cash,
            mode=result.mode,
            rebalance_frequency=result.rebalance_frequency,
            metrics=result.metrics,
            trades=result.trades,
            equity_curve=result.equity_curve,
            report_path=str(report_path),
            strategy=result.strategy,
            no_lookahead=result.no_lookahead,
            signal_execution_lag=result.signal_execution_lag,
            alpha_config=result.alpha_config,
            excluded_symbols_per_rebalance=result.excluded_symbols_per_rebalance,
        )

    def _run_alpha_strategy(
        self,
        start: str,
        end: str,
        initial_cash: float,
        rebalance_frequency: str,
        cost_config: dict | None,
        execution_price: str,
        alpha_config: dict,
        alpha_pipeline_config: dict | None = None,
    ) -> PortfolioBacktestResult:
        merged_alpha_config = dict(alpha_config)
        universe = self._normalize_symbols(merged_alpha_config.get("universe") or list(DEFAULT_SYMBOLS))
        price_frame = self._load_price_frame(universe, start, end)
        active_symbols = list(price_frame.columns)
        if not active_symbols:
            raise ValueError("no price data found for backtest universe")

        price_lookup = self._load_price_lookup(active_symbols, start, end)
        alpha_engine = AlphaEngine(self.price_store, report_dir=self.report_dir)
        cost_engine = CostEngine(cost_config or {})
        cash = float(initial_cash)
        positions = {symbol: 0 for symbol in active_symbols}
        trades: list[PortfolioBacktestTrade] = []
        equity_curve: list[dict] = []
        gross_trade_value = 0.0
        total_cost = 0.0
        pending_rebalances: list[dict] = []
        excluded_symbols_per_rebalance: dict[str, dict[str, str]] = {}
        last_signal_date: str | None = None
        last_execution_date: str | None = None

        for index, (date_value, prices) in enumerate(price_frame.iterrows()):
            date_text = date_value.strftime("%Y-%m-%d")

            due = [event for event in pending_rebalances if event["execution_date"] == date_text]
            pending_rebalances = [event for event in pending_rebalances if event["execution_date"] != date_text]
            for event in due:
                execution_prices = {
                    symbol: price_lookup[date_text][symbol][execution_price]
                    for symbol in active_symbols
                }
                day_trades, cash, positions = self._rebalance_alpha(
                    signal_date=event["signal_date"],
                    execution_date=date_text,
                    cash=cash,
                    positions=positions,
                    signal_prices=event["signal_prices"],
                    execution_prices=execution_prices,
                    target_weights=event["target_weights"],
                    cost_engine=cost_engine,
                )
                trades.extend(day_trades)
                gross_trade_value += sum(trade.notional for trade in day_trades)
                total_cost += sum(trade.total_cost for trade in day_trades)
                if day_trades:
                    last_execution_date = date_text

            if self._is_rebalance_date(price_frame.index, index, rebalance_frequency) and index + 1 < len(price_frame.index):
                signal_date = date_text
                execution_date = price_frame.index[index + 1].strftime("%Y-%m-%d")
                signal_alpha_config = dict(merged_alpha_config)
                signal_alpha_config["universe"] = active_symbols
                signal_alpha_config["as_of_date"] = signal_date
                try:
                    alpha_result = alpha_engine.generate(
                        config=signal_alpha_config,
                        pipeline_config=alpha_pipeline_config,
                    )
                except ValueError:
                    alpha_result = None

                if alpha_result is not None:
                    target_weights = {
                        symbol: weight
                        for symbol, weight in alpha_result.target_weights.items()
                        if symbol == "cash" or symbol in active_symbols
                    }
                    excluded_symbols_per_rebalance[signal_date] = dict(alpha_result.exclusion_reasons)
                    pending_rebalances.append(
                        {
                            "signal_date": signal_date,
                            "execution_date": execution_date,
                            "target_weights": target_weights,
                            "signal_prices": {symbol: float(prices[symbol]) for symbol in active_symbols},
                        }
                    )
                    last_signal_date = signal_date

            price_map = {symbol: float(prices[symbol]) for symbol in active_symbols}
            equity = cash + sum(positions[symbol] * price_map[symbol] for symbol in active_symbols)
            equity_curve.append(
                {
                    "date": date_text,
                    "cash": cash,
                    "equity": equity,
                    "positions": dict(positions),
                    "last_signal_date": last_signal_date,
                    "last_execution_date": last_execution_date,
                }
            )

        metrics = self._metrics(
            equity_curve=equity_curve,
            initial_cash=initial_cash,
            gross_trade_value=gross_trade_value,
            total_cost=total_cost,
            trade_count=len(trades),
        )
        result = PortfolioBacktestResult(
            start=start,
            end=end,
            initial_cash=float(initial_cash),
            mode="alpha",
            rebalance_frequency=rebalance_frequency,
            metrics=metrics,
            trades=trades,
            equity_curve=equity_curve,
            report_path="",
            strategy="alpha",
            no_lookahead=True,
            signal_execution_lag="next_trading_day",
            alpha_config=merged_alpha_config,
            excluded_symbols_per_rebalance=excluded_symbols_per_rebalance,
        )
        report_path = self._write_report(result)
        return PortfolioBacktestResult(
            start=result.start,
            end=result.end,
            initial_cash=result.initial_cash,
            mode=result.mode,
            rebalance_frequency=result.rebalance_frequency,
            metrics=result.metrics,
            trades=result.trades,
            equity_curve=result.equity_curve,
            report_path=str(report_path),
            strategy=result.strategy,
            no_lookahead=result.no_lookahead,
            signal_execution_lag=result.signal_execution_lag,
            alpha_config=result.alpha_config,
            excluded_symbols_per_rebalance=result.excluded_symbols_per_rebalance,
        )

    def _load_price_frame(self, symbols: list[str], start: str, end: str) -> pd.DataFrame:
        frames = []
        for symbol in symbols:
            history = self.price_store.get_price_history(symbol, start=start, end=end)
            if history.empty:
                continue
            frame = history[["date", "close"]].copy()
            frame["date"] = pd.to_datetime(frame["date"])
            frame["close"] = pd.to_numeric(frame["close"], errors="coerce")
            frame = frame.dropna(subset=["close"]).rename(columns={"close": symbol})
            frames.append(frame.set_index("date"))

        if not frames:
            raise ValueError("no price data found for backtest universe")

        prices = pd.concat(frames, axis=1).sort_index().ffill().dropna(how="any")
        if prices.empty:
            raise ValueError("no complete price data found for backtest universe")
        return prices

    def _load_price_lookup(self, symbols: list[str], start: str, end: str) -> dict[str, dict[str, dict[str, float]]]:
        lookup: dict[str, dict[str, dict[str, float]]] = {}
        for symbol in symbols:
            history = self.price_store.get_price_history(symbol, start=start, end=end)
            for row in history.to_dict("records"):
                date_text = str(row["date"])
                lookup.setdefault(date_text, {})[symbol] = {
                    "open": float(row["open"]),
                    "close": float(row["close"]),
                }
        return lookup

    def _target_weights(
        self,
        mode: str,
        symbols: list[str],
        price_frame: pd.DataFrame,
        constraints: dict,
    ) -> dict[str, float]:
        min_cash_weight = constraints["min_cash_weight"]
        investable_weight = max(1.0 - min_cash_weight, 0.0)
        if mode in {"equal_weight", "constrained"}:
            raw_weights = {symbol: investable_weight / len(symbols) for symbol in symbols}
        else:
            inverse_risks = {}
            for symbol in symbols:
                returns = price_frame[symbol].pct_change().dropna()
                volatility = float(returns.std()) if not returns.empty else 0.0
                inverse_risks[symbol] = 1.0 / max(volatility, 0.0001)
            total_inverse = sum(inverse_risks.values())
            raw_weights = {
                symbol: (inverse_risks[symbol] / total_inverse) * investable_weight
                for symbol in symbols
            }

        return self._apply_constraints(raw_weights, constraints)

    def _apply_constraints(self, raw_weights: dict[str, float], constraints: dict) -> dict[str, float]:
        adjusted = {
            symbol: min(max(weight, 0.0), constraints["max_position_weight"])
            for symbol, weight in raw_weights.items()
        }

        sector_totals: dict[str, float] = {}
        for symbol, weight in adjusted.items():
            sector = self.industry_map.get(symbol, "Unknown")
            sector_totals[sector] = sector_totals.get(sector, 0.0) + weight

        for sector, sector_weight in sector_totals.items():
            if sector_weight > constraints["max_sector_weight"]:
                scale = constraints["max_sector_weight"] / sector_weight
                for symbol in list(adjusted):
                    if self.industry_map.get(symbol, "Unknown") == sector:
                        adjusted[symbol] *= scale

        total_asset_weight = sum(adjusted.values())
        cash_weight = max(1.0 - total_asset_weight, constraints["min_cash_weight"])
        if total_asset_weight + cash_weight > 1.0 and total_asset_weight > 0:
            scale = (1.0 - cash_weight) / total_asset_weight
            adjusted = {symbol: weight * scale for symbol, weight in adjusted.items()}

        targets = {symbol: weight for symbol, weight in adjusted.items() if weight > 0}
        targets["cash"] = 1.0 - sum(targets.values())
        return targets

    def _rebalance(
        self,
        date_text: str,
        cash: float,
        positions: dict[str, int],
        prices: dict[str, float],
        target_weights: dict[str, float],
        cost_engine: CostEngine,
    ) -> tuple[list[PortfolioBacktestTrade], float, dict[str, int]]:
        total_value = cash + sum(positions[symbol] * prices[symbol] for symbol in positions)
        trades: list[PortfolioBacktestTrade] = []
        updated_positions = dict(positions)

        for symbol in sorted(positions):
            current_value = updated_positions[symbol] * prices[symbol]
            target_value = total_value * target_weights.get(symbol, 0.0)
            difference = target_value - current_value
            if difference >= 0:
                continue
            shares = min(updated_positions[symbol], math.floor(abs(difference) / prices[symbol]))
            if shares <= 0:
                continue
            trade_input = TradeInput(symbol=symbol, side="SELL", shares=shares, price=prices[symbol])
            cost = cost_engine.estimate([trade_input], write_report=False).trades[0].total_cost
            notional = shares * prices[symbol]
            cash += notional - cost
            updated_positions[symbol] -= shares
            trades.append(self._trade(date_text, trade_input, notional, cost, cash))

        for symbol in sorted(positions):
            current_value = updated_positions[symbol] * prices[symbol]
            target_value = total_value * target_weights.get(symbol, 0.0)
            difference = target_value - current_value
            if difference <= 0:
                continue
            shares = math.floor(difference / prices[symbol])
            while shares > 0:
                trade_input = TradeInput(symbol=symbol, side="BUY", shares=shares, price=prices[symbol])
                cost = cost_engine.estimate([trade_input], write_report=False).trades[0].total_cost
                notional = shares * prices[symbol]
                if notional + cost <= cash:
                    break
                shares -= 1
            if shares <= 0:
                continue
            trade_input = TradeInput(symbol=symbol, side="BUY", shares=shares, price=prices[symbol])
            cost = cost_engine.estimate([trade_input], write_report=False).trades[0].total_cost
            notional = shares * prices[symbol]
            cash -= notional + cost
            updated_positions[symbol] += shares
            trades.append(self._trade(date_text, trade_input, notional, cost, cash))

        return trades, cash, updated_positions

    def _rebalance_alpha(
        self,
        signal_date: str,
        execution_date: str,
        cash: float,
        positions: dict[str, int],
        signal_prices: dict[str, float],
        execution_prices: dict[str, float],
        target_weights: dict[str, float],
        cost_engine: CostEngine,
    ) -> tuple[list[PortfolioBacktestTrade], float, dict[str, int]]:
        total_value = cash + sum(positions[symbol] * signal_prices[symbol] for symbol in positions)
        trades: list[PortfolioBacktestTrade] = []
        updated_positions = dict(positions)

        for symbol in sorted(positions):
            current_value = updated_positions[symbol] * signal_prices[symbol]
            target_value = total_value * target_weights.get(symbol, 0.0)
            difference = target_value - current_value
            if difference >= 0:
                continue
            signal_price = signal_prices[symbol]
            execution_price = execution_prices[symbol]
            shares = min(updated_positions[symbol], math.floor(abs(difference) / signal_price))
            if shares <= 0:
                continue
            trade_input = TradeInput(symbol=symbol, side="SELL", shares=shares, price=execution_price)
            cost = cost_engine.estimate([trade_input], write_report=False).trades[0].total_cost
            notional = shares * execution_price
            cash += notional - cost
            updated_positions[symbol] -= shares
            trades.append(
                self._trade(
                    date_text=execution_date,
                    trade_input=trade_input,
                    notional=notional,
                    total_cost=cost,
                    cash_after=cash,
                    signal_date=signal_date,
                    execution_date=execution_date,
                    signal_price=signal_price,
                    execution_price=execution_price,
                )
            )

        for symbol in sorted(positions):
            current_value = updated_positions[symbol] * signal_prices[symbol]
            target_value = total_value * target_weights.get(symbol, 0.0)
            difference = target_value - current_value
            if difference <= 0:
                continue
            signal_price = signal_prices[symbol]
            execution_price = execution_prices[symbol]
            shares = math.floor(difference / signal_price)
            while shares > 0:
                trade_input = TradeInput(symbol=symbol, side="BUY", shares=shares, price=execution_price)
                cost = cost_engine.estimate([trade_input], write_report=False).trades[0].total_cost
                notional = shares * execution_price
                if notional + cost <= cash:
                    break
                shares -= 1
            if shares <= 0:
                continue
            trade_input = TradeInput(symbol=symbol, side="BUY", shares=shares, price=execution_price)
            cost = cost_engine.estimate([trade_input], write_report=False).trades[0].total_cost
            notional = shares * execution_price
            cash -= notional + cost
            updated_positions[symbol] += shares
            trades.append(
                self._trade(
                    date_text=execution_date,
                    trade_input=trade_input,
                    notional=notional,
                    total_cost=cost,
                    cash_after=cash,
                    signal_date=signal_date,
                    execution_date=execution_date,
                    signal_price=signal_price,
                    execution_price=execution_price,
                )
            )

        return trades, cash, updated_positions

    @staticmethod
    def _trade(
        date_text: str,
        trade_input: TradeInput,
        notional: float,
        total_cost: float,
        cash_after: float,
        signal_date: str | None = None,
        execution_date: str | None = None,
        signal_price: float | None = None,
        execution_price: float | None = None,
    ) -> PortfolioBacktestTrade:
        return PortfolioBacktestTrade(
            date=date_text,
            symbol=trade_input.symbol,
            side=trade_input.side,
            shares=trade_input.shares,
            price=trade_input.price,
            notional=notional,
            total_cost=total_cost,
            cash_after=cash_after,
            signal_date=signal_date,
            execution_date=execution_date,
            signal_price=signal_price,
            execution_price=execution_price,
        )

    @staticmethod
    def _is_rebalance_date(index: pd.DatetimeIndex, position: int, frequency: str) -> bool:
        if position == 0:
            return True
        if frequency == "daily":
            return True
        current = index[position]
        previous = index[position - 1]
        if frequency == "weekly":
            return current.isocalendar().week != previous.isocalendar().week
        return current.month != previous.month or current.year != previous.year

    @staticmethod
    def _metrics(
        equity_curve: list[dict],
        initial_cash: float,
        gross_trade_value: float,
        total_cost: float,
        trade_count: int,
    ) -> PortfolioBacktestMetrics:
        equities = pd.Series([point["equity"] for point in equity_curve], dtype="float64")
        returns = equities.pct_change().dropna()
        final_value = float(equities.iloc[-1])
        total_return = (final_value / initial_cash) - 1.0
        start_date = pd.to_datetime(equity_curve[0]["date"])
        end_date = pd.to_datetime(equity_curve[-1]["date"])
        years = max((end_date - start_date).days / 365.25, 1 / 365.25)
        annual_return = (final_value / initial_cash) ** (1 / years) - 1.0
        drawdowns = (equities / equities.cummax()) - 1.0
        volatility = float(returns.std() * math.sqrt(252)) if not returns.empty else 0.0
        sharpe_ratio = 0.0
        if not returns.empty and returns.std() != 0 and not pd.isna(returns.std()):
            sharpe_ratio = float((returns.mean() / returns.std()) * math.sqrt(252))

        return PortfolioBacktestMetrics(
            final_value=final_value,
            total_return=float(total_return),
            annual_return=float(annual_return),
            max_drawdown=abs(float(drawdowns.min())),
            volatility=volatility,
            sharpe_ratio=sharpe_ratio,
            trade_count=trade_count,
            turnover=float(gross_trade_value / initial_cash),
            total_cost=float(total_cost),
            cash_ratio=float(equity_curve[-1]["cash"] / final_value) if final_value else 0.0,
        )

    @staticmethod
    def _validate(
        start: str,
        end: str,
        initial_cash: float,
        mode: str,
        rebalance_frequency: str,
        strategy: str,
        execution_price: str,
    ) -> None:
        if not start or not end:
            raise ValueError("start and end are required")
        if pd.to_datetime(start) > pd.to_datetime(end):
            raise ValueError("start must be before or equal to end")
        if initial_cash <= 0:
            raise ValueError("initial_cash must be positive")
        if mode not in {"equal_weight", "risk_adjusted", "constrained"}:
            raise ValueError("mode must be one of: equal_weight, risk_adjusted, constrained")
        if rebalance_frequency not in {"monthly", "weekly", "daily"}:
            raise ValueError("rebalance_frequency must be one of: monthly, weekly, daily")
        if strategy not in {"portfolio", "alpha"}:
            raise ValueError("strategy must be one of: portfolio, alpha")
        if execution_price not in {"close", "open"}:
            raise ValueError("execution_price must be one of: close, open")

    @staticmethod
    def _normalize_symbols(symbols: list[str]) -> list[str]:
        normalized = []
        seen = set()
        for symbol in symbols:
            ticker = symbol.upper().strip()
            if ticker and ticker not in seen:
                normalized.append(ticker)
                seen.add(ticker)
        return normalized

    @staticmethod
    def _normalize_constraints(constraints: dict) -> dict:
        merged = dict(DEFAULT_CONSTRAINTS)
        merged.update(constraints)
        merged["max_position_weight"] = float(merged["max_position_weight"])
        merged["min_cash_weight"] = float(merged["min_cash_weight"])
        merged["max_sector_weight"] = float(merged["max_sector_weight"])
        return merged

    def _write_report(self, result: PortfolioBacktestResult) -> Path:
        self.report_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = self.report_dir / f"backtest_{timestamp}.json"
        payload = result.to_report()
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return path
