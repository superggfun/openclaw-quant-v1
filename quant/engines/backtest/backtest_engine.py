"""Deterministic daily portfolio backtest engine."""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, replace
from pathlib import Path

import pandas as pd

from quant.engines.alpha.alpha_engine import AlphaEngine
from quant.config import DEFAULT_SYMBOLS
from quant.core.equity import equity_curve_stats
from quant.core.symbols import normalize_symbols
from quant.engines.execution.cost_engine import CostEngine, TradeInput
from quant.engines.portfolio.optimizer_engine import DEFAULT_CONSTRAINTS
from quant.engines.risk.risk_engine import DEFAULT_INDUSTRY_MAP
from quant.reports.report_io import generate_report_path, write_json_report
from quant.storage.sqlite_store import SQLitePriceStore


SAME_DAY_CLOSE_RESEARCH_LABEL = "Research-only, same-day-close, not tradable."
SAME_DAY_CLOSE_WARNING = {
    "code": "RESEARCH_ONLY_SAME_DAY_CLOSE",
    "reason": SAME_DAY_CLOSE_RESEARCH_LABEL,
}
STALE_MARK_LIMIT_DAYS = 5


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
    alpha_pipeline_config: dict | None = None
    execution_price: str | None = None
    price_column: str | None = None
    effective_universe: list[str] | None = None
    excluded_symbols_per_rebalance: dict[str, dict[str, str]] | None = None
    tradability_label: str | None = None
    warnings: list[dict] | None = None

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
            "tradability_label": self.tradability_label,
            "alpha_config": self.alpha_config,
            "alpha_pipeline_config": self.alpha_pipeline_config,
            "execution_price": self.execution_price,
            "price_column": self.price_column,
            "effective_universe": self.effective_universe or [],
            "excluded_symbols_per_rebalance": self.excluded_symbols_per_rebalance or {},
            "warnings": self.warnings or [],
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
        allow_same_day_close_simple_mode: bool = False,
        allow_alpha_failures: bool = False,
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
                symbols=symbols,
                allow_alpha_failures=allow_alpha_failures,
            )
        if not allow_same_day_close_simple_mode:
            raise ValueError(
                "strategy='portfolio' uses same-day close weights and fills, so it is disabled by default. "
                "Use strategy='alpha' for no-lookahead backtests or pass "
                "allow_same_day_close_simple_mode=True for research-only smoke checks."
            )
        if execution_price != "close":
            raise ValueError("portfolio simple mode only supports close execution.")

        universe = self._normalize_symbols(symbols or list(DEFAULT_SYMBOLS))
        raw_price_frame = self._load_raw_price_frame(universe, start, end, "close")
        price_frame = self._mark_price_frame(raw_price_frame)
        active_symbols = list(price_frame.columns)
        if not active_symbols:
            raise ValueError("no price data found for backtest universe")
        execution_price_frame = self._load_execution_price_frame(active_symbols, start, end, "close")

        constraints = self._normalize_constraints(constraints or {})
        cost_engine = CostEngine(cost_config or {})
        cash = float(initial_cash)
        positions = {symbol: 0 for symbol in active_symbols}
        trades: list[PortfolioBacktestTrade] = []
        equity_curve: list[dict] = []
        gross_trade_value = 0.0
        total_cost = 0.0
        execution_warnings: list[dict] = []
        execution_warnings.extend(self._stale_mark_warnings(raw_price_frame[active_symbols], price_frame))

        for index, (date_value, prices) in enumerate(price_frame.iterrows()):
            date_text = date_value.strftime("%Y-%m-%d")
            price_map = {symbol: float(prices[symbol]) for symbol in active_symbols}
            execution_price_map = self._prices_for_date(execution_price_frame, date_value)

            if self._is_rebalance_date(price_frame.index, index, rebalance_frequency):
                target_weights = self._target_weights(
                    mode=mode,
                    symbols=active_symbols,
                    price_frame=price_frame.loc[:date_value],
                    constraints=constraints,
                    warnings=execution_warnings,
                    date_text=date_text,
                )
                day_trades, cash, positions = self._rebalance(
                    date_text=date_text,
                    cash=cash,
                    positions=positions,
                    prices=price_map,
                    execution_prices=execution_price_map,
                    target_weights=target_weights,
                    cost_engine=cost_engine,
                    warnings=execution_warnings,
                )
                trades.extend(day_trades)
                gross_trade_value += sum(trade.notional for trade in day_trades)
                total_cost += sum(trade.total_cost for trade in day_trades)

            equity_curve.append(
                self._equity_point(
                    date_text=date_text,
                    cash=cash,
                    positions=positions,
                    prices=price_map,
                    symbols=active_symbols,
                    last_signal_date=date_text,
                    last_execution_date=date_text,
                )
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
            alpha_pipeline_config=None,
            execution_price=execution_price,
            price_column="close",
            effective_universe=active_symbols,
            excluded_symbols_per_rebalance={},
            tradability_label=SAME_DAY_CLOSE_RESEARCH_LABEL,
            warnings=[dict(SAME_DAY_CLOSE_WARNING), *execution_warnings],
        )
        report_path = self._write_report(result)
        return replace(result, report_path=str(report_path))

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
        symbols: list[str] | None = None,
        allow_alpha_failures: bool = False,
    ) -> PortfolioBacktestResult:
        merged_alpha_config = dict(alpha_config)
        if symbols is not None and "universe" in merged_alpha_config:
            raise ValueError("Pass universe either via symbols or alpha_config['universe'], not both.")
        if symbols is not None:
            merged_alpha_config["universe"] = symbols
        universe = self._normalize_symbols(merged_alpha_config.get("universe") or list(DEFAULT_SYMBOLS))
        merged_alpha_config["universe"] = universe
        raw_price_frame = self._load_raw_price_frame(universe, start, end, "close")
        price_frame = self._mark_price_frame(raw_price_frame)
        active_symbols = list(price_frame.columns)
        if not active_symbols:
            raise ValueError("no price data found for backtest universe")

        execution_price_frame = self._load_execution_price_frame(active_symbols, start, end, execution_price)
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
        execution_warnings: list[dict] = []
        execution_warnings.extend(self._stale_mark_warnings(raw_price_frame[active_symbols], price_frame))
        required_alpha_rows = self._alpha_required_history_rows(merged_alpha_config)

        for index, (date_value, prices) in enumerate(price_frame.iterrows()):
            date_text = date_value.strftime("%Y-%m-%d")

            due = [event for event in pending_rebalances if event["execution_date"] == date_text]
            pending_rebalances = [event for event in pending_rebalances if event["execution_date"] != date_text]
            for event in due:
                execution_prices = self._prices_for_date(execution_price_frame, date_value)
                day_trades, cash, positions = self._rebalance_alpha(
                    signal_date=event["signal_date"],
                    execution_date=date_text,
                    cash=cash,
                    positions=positions,
                    signal_prices=event["signal_prices"],
                    execution_prices=execution_prices,
                    target_weights=event["target_weights"],
                    cost_engine=cost_engine,
                    warnings=execution_warnings,
                )
                trades.extend(day_trades)
                gross_trade_value += sum(trade.notional for trade in day_trades)
                total_cost += sum(trade.total_cost for trade in day_trades)
                if day_trades:
                    last_execution_date = date_text

            if self._is_rebalance_date(price_frame.index, index, rebalance_frequency) and index + 1 < len(price_frame.index):
                signal_date = date_text
                execution_date = price_frame.index[index + 1].strftime("%Y-%m-%d")
                available_alpha_rows = len(price_frame.loc[:date_value])
                if available_alpha_rows < required_alpha_rows:
                    execution_warnings.append(
                        {
                            "code": "ALPHA_SIGNAL_SKIPPED_INSUFFICIENT_HISTORY",
                            "signal_date": signal_date,
                            "available_rows": available_alpha_rows,
                            "required_rows": required_alpha_rows,
                            "reason": "not enough historical rows to compute alpha signal",
                        }
                    )
                    continue
                signal_alpha_config = dict(merged_alpha_config)
                signal_alpha_config["universe"] = active_symbols
                signal_alpha_config["as_of_date"] = signal_date
                try:
                    alpha_result = alpha_engine.generate(
                        config=signal_alpha_config,
                        pipeline_config=alpha_pipeline_config,
                        write_report=False,
                    )
                except ValueError as exc:
                    warning = {
                        "code": "ALPHA_GENERATION_FAILED",
                        "signal_date": signal_date,
                        "reason": str(exc),
                    }
                    if allow_alpha_failures:
                        execution_warnings.append(warning)
                        alpha_result = None
                    else:
                        raise ValueError(
                            f"alpha generation failed on {signal_date}: {exc}"
                        ) from exc

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

            equity_curve.append(
                self._equity_point(
                    date_text=date_text,
                    cash=cash,
                    positions=positions,
                    prices={symbol: float(prices[symbol]) for symbol in active_symbols},
                    symbols=active_symbols,
                    last_signal_date=last_signal_date,
                    last_execution_date=last_execution_date,
                )
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
            alpha_pipeline_config=alpha_pipeline_config,
            execution_price=execution_price,
            price_column="close",
            effective_universe=active_symbols,
            excluded_symbols_per_rebalance=excluded_symbols_per_rebalance,
            tradability_label=None,
            warnings=execution_warnings,
        )
        report_path = self._write_report(result)
        return replace(result, report_path=str(report_path))

    def _load_price_frame(self, symbols: list[str], start: str, end: str) -> pd.DataFrame:
        prices = self._load_raw_price_frame(symbols, start, end, "close")
        return self._mark_price_frame(prices)

    @staticmethod
    def _mark_price_frame(prices: pd.DataFrame) -> pd.DataFrame:
        if prices.empty:
            raise ValueError("no price data found for backtest universe")

        marked = prices.ffill().dropna(how="any")
        if marked.empty:
            raise ValueError("no complete price data found for backtest universe")
        return marked

    def _load_execution_price_frame(self, symbols: list[str], start: str, end: str, price_column: str) -> pd.DataFrame:
        return self._load_raw_price_frame(symbols, start, end, price_column)

    def _load_raw_price_frame(self, symbols: list[str], start: str, end: str, price_column: str) -> pd.DataFrame:
        frames = []
        histories = self._price_histories(symbols, start, end)
        for symbol in symbols:
            history = histories.get(symbol)
            if history is None:
                history = histories.get(symbol.upper())
            if history is None or history.empty:
                continue
            if price_column not in history.columns:
                continue
            frame = history[["date", price_column]].copy()
            frame["date"] = pd.to_datetime(frame["date"])
            frame[price_column] = pd.to_numeric(frame[price_column], errors="coerce")
            frame = frame.dropna(subset=[price_column]).rename(columns={price_column: symbol})
            frames.append(frame.set_index("date"))

        if not frames:
            return pd.DataFrame()
        return pd.concat(frames, axis=1).sort_index()

    def _price_histories(self, symbols: list[str], start: str, end: str) -> dict[str, pd.DataFrame]:
        if hasattr(self.price_store, "get_price_history_many"):
            return self.price_store.get_price_history_many(symbols, start=start, end=end)
        return {
            symbol: self.price_store.get_price_history(symbol, start=start, end=end)
            for symbol in symbols
        }

    @staticmethod
    def _equity_point(
        date_text: str,
        cash: float,
        positions: dict[str, int],
        prices: dict[str, float],
        symbols: list[str],
        last_signal_date: str | None,
        last_execution_date: str | None,
    ) -> dict:
        return {
            "date": date_text,
            "cash": cash,
            "equity": cash + sum(positions[symbol] * prices[symbol] for symbol in symbols),
            "positions": dict(positions),
            "last_signal_date": last_signal_date,
            "last_execution_date": last_execution_date,
        }

    def _target_weights(
        self,
        mode: str,
        symbols: list[str],
        price_frame: pd.DataFrame,
        constraints: dict,
        warnings: list[dict] | None = None,
        date_text: str | None = None,
    ) -> dict[str, float]:
        min_cash_weight = constraints["min_cash_weight"]
        investable_weight = max(1.0 - min_cash_weight, 0.0)
        if mode in {"equal_weight", "constrained"}:
            raw_weights = {symbol: investable_weight / len(symbols) for symbol in symbols}
        else:
            inverse_risks = {}
            insufficient_history = True
            for symbol in symbols:
                returns = price_frame[symbol].pct_change().dropna()
                if not returns.empty:
                    insufficient_history = False
                volatility = float(returns.std()) if not returns.empty else 0.0
                inverse_risks[symbol] = 1.0 / max(volatility, 0.0001)
            if insufficient_history and warnings is not None:
                warning = {
                    "code": "RISK_ADJUSTED_INSUFFICIENT_HISTORY",
                    "date": date_text,
                    "reason": "risk_adjusted rebalance has insufficient return history; weights fall back to equal-risk/equal-weight behavior.",
                }
                if warning not in warnings:
                    warnings.append(warning)
            total_inverse = sum(inverse_risks.values())
            raw_weights = {
                symbol: (inverse_risks[symbol] / total_inverse) * investable_weight
                for symbol in symbols
            }

        return self._apply_constraints(raw_weights, constraints, warnings=warnings)

    def _apply_constraints(
        self,
        raw_weights: dict[str, float],
        constraints: dict,
        warnings: list[dict] | None = None,
    ) -> dict[str, float]:
        adjusted = {
            symbol: min(max(weight, 0.0), constraints["max_position_weight"])
            for symbol, weight in raw_weights.items()
        }

        sector_totals: dict[str, float] = {}
        unknown_symbols = []
        for symbol, weight in adjusted.items():
            sector = self.industry_map.get(symbol, "Unknown")
            if sector == "Unknown":
                unknown_symbols.append(symbol)
                continue
            sector_totals[sector] = sector_totals.get(sector, 0.0) + weight
        if unknown_symbols and warnings is not None:
            warning = {
                "code": "UNKNOWN_INDUSTRY_SYMBOLS",
                "symbols": sorted(unknown_symbols),
                "reason": "Symbols with unknown industry were excluded from sector cap grouping.",
            }
            if warning not in warnings:
                warnings.append(warning)

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
        execution_prices: dict[str, float],
        target_weights: dict[str, float],
        cost_engine: CostEngine,
        warnings: list[dict] | None = None,
    ) -> tuple[list[PortfolioBacktestTrade], float, dict[str, int]]:
        return self._rebalance_with_prices(
            trade_date=date_text,
            cash=cash,
            positions=positions,
            valuation_prices=prices,
            execution_prices=execution_prices,
            target_weights=target_weights,
            cost_engine=cost_engine,
            warnings=warnings,
        )

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
        warnings: list[dict] | None = None,
    ) -> tuple[list[PortfolioBacktestTrade], float, dict[str, int]]:
        return self._rebalance_with_prices(
            trade_date=execution_date,
            cash=cash,
            positions=positions,
            valuation_prices=signal_prices,
            execution_prices=execution_prices,
            target_weights=target_weights,
            cost_engine=cost_engine,
            signal_date=signal_date,
            execution_date=execution_date,
            warnings=warnings,
        )

    def _rebalance_with_prices(
        self,
        trade_date: str,
        cash: float,
        positions: dict[str, int],
        valuation_prices: dict[str, float],
        execution_prices: dict[str, float],
        target_weights: dict[str, float],
        cost_engine: CostEngine,
        signal_date: str | None = None,
        execution_date: str | None = None,
        warnings: list[dict] | None = None,
    ) -> tuple[list[PortfolioBacktestTrade], float, dict[str, int]]:
        total_value = cash + sum(positions[symbol] * valuation_prices[symbol] for symbol in positions)
        trades: list[PortfolioBacktestTrade] = []
        updated_positions = dict(positions)

        for symbol in sorted(positions):
            valuation_price = valuation_prices[symbol]
            current_value = updated_positions[symbol] * valuation_price
            target_value = total_value * target_weights.get(symbol, 0.0)
            difference = target_value - current_value
            if difference >= 0:
                continue
            shares = min(updated_positions[symbol], math.floor(abs(difference) / valuation_price))
            if shares <= 0:
                continue
            execution_price = execution_prices.get(symbol)
            if execution_price is None or execution_price <= 0:
                self._append_not_tradable_warning(warnings, symbol, trade_date)
                continue
            trade_input = TradeInput(symbol=symbol, side="SELL", shares=shares, price=execution_price)
            cost = cost_engine.estimate([trade_input], write_report=False).trades[0].total_cost
            notional = shares * execution_price
            cash += notional - cost
            updated_positions[symbol] -= shares
            trades.append(
                self._trade(
                    date_text=trade_date,
                    trade_input=trade_input,
                    notional=notional,
                    total_cost=cost,
                    cash_after=cash,
                    signal_date=signal_date,
                    execution_date=execution_date,
                    signal_price=valuation_price if signal_date is not None else None,
                    execution_price=execution_price if execution_date is not None else None,
                )
            )

        for symbol in sorted(positions):
            valuation_price = valuation_prices[symbol]
            current_value = updated_positions[symbol] * valuation_price
            target_value = total_value * target_weights.get(symbol, 0.0)
            difference = target_value - current_value
            if difference <= 0:
                continue
            shares = math.floor(difference / valuation_price)
            if shares <= 0:
                continue
            execution_price = execution_prices.get(symbol)
            if execution_price is None or execution_price <= 0:
                self._append_not_tradable_warning(warnings, symbol, trade_date)
                continue
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
                    date_text=trade_date,
                    trade_input=trade_input,
                    notional=notional,
                    total_cost=cost,
                    cash_after=cash,
                    signal_date=signal_date,
                    execution_date=execution_date,
                    signal_price=valuation_price if signal_date is not None else None,
                    execution_price=execution_price if execution_date is not None else None,
                )
            )

        return trades, cash, updated_positions

    @staticmethod
    def _prices_for_date(frame: pd.DataFrame, date_value: pd.Timestamp) -> dict[str, float]:
        if frame.empty or date_value not in frame.index:
            return {}
        row = frame.loc[date_value].dropna()
        return {str(symbol): float(value) for symbol, value in row.items() if float(value) > 0}

    @staticmethod
    def _append_not_tradable_warning(warnings: list[dict] | None, symbol: str, execution_date: str) -> None:
        if warnings is None:
            return
        warning = {
            "code": "NOT_TRADABLE_ON_EXECUTION_DATE",
            "symbol": symbol,
            "execution_date": execution_date,
            "reason": f"{symbol} has no real execution price on {execution_date}; ffilled mark price was not used for trading.",
        }
        if warning not in warnings:
            warnings.append(warning)

    @staticmethod
    def _stale_mark_warnings(raw_prices: pd.DataFrame, marked_prices: pd.DataFrame) -> list[dict]:
        warnings: list[dict] = []
        if raw_prices.empty or marked_prices.empty:
            return warnings
        raw_aligned = raw_prices.reindex(marked_prices.index)
        for symbol in marked_prices.columns:
            stale_days = 0
            for date_value in marked_prices.index:
                raw_value = raw_aligned.at[date_value, symbol] if symbol in raw_aligned.columns else None
                if pd.isna(raw_value):
                    stale_days += 1
                else:
                    stale_days = 0
                if stale_days > STALE_MARK_LIMIT_DAYS:
                    warnings.append(
                        {
                            "code": "STALE_MARK_PRICE",
                            "symbol": symbol,
                            "date": date_value.strftime("%Y-%m-%d"),
                            "days_stale": stale_days,
                            "reason": (
                                f"{symbol} mark price has been forward-filled for {stale_days} "
                                "consecutive trading rows; equity may be optimistic for halted/delisted/missing data."
                            ),
                        }
                    )
        return warnings

    @staticmethod
    def _alpha_required_history_rows(alpha_config: Mapping[str, Any]) -> int:
        try:
            lookback_short = int(alpha_config.get("lookback_short", 20))
            lookback_long = int(alpha_config.get("lookback_long", 60))
        except (TypeError, ValueError):
            return 1
        return max(1, lookback_short, lookback_long) + 1

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
        stats = equity_curve_stats(
            equity_curve,
            initial_cash,
            min_return_count_for_volatility=1,
            empty_volatility=0.0,
            empty_sharpe=0.0,
        )

        return PortfolioBacktestMetrics(
            final_value=stats.final_value,
            total_return=stats.total_return,
            annual_return=stats.annual_return,
            max_drawdown=abs(float(stats.max_drawdown or 0.0)),
            volatility=float(stats.volatility or 0.0),
            sharpe_ratio=float(stats.sharpe or 0.0),
            trade_count=trade_count,
            turnover=float(gross_trade_value / initial_cash),
            total_cost=float(total_cost),
            cash_ratio=float(equity_curve[-1]["cash"] / stats.final_value) if stats.final_value else 0.0,
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
        return normalize_symbols(symbols)

    @staticmethod
    def _normalize_constraints(constraints: dict) -> dict:
        merged = dict(DEFAULT_CONSTRAINTS)
        merged.update(constraints)
        merged["max_position_weight"] = float(merged["max_position_weight"])
        merged["min_cash_weight"] = float(merged["min_cash_weight"])
        merged["max_sector_weight"] = float(merged["max_sector_weight"])
        for key in ("max_position_weight", "min_cash_weight", "max_sector_weight"):
            if not math.isfinite(merged[key]) or not 0.0 <= merged[key] <= 1.0:
                raise ValueError(f"{key} must be between 0 and 1")
        if merged["max_position_weight"] <= 0:
            raise ValueError("max_position_weight must be positive")
        return merged

    def _write_report(self, result: PortfolioBacktestResult) -> Path:
        return write_json_report(
            generate_report_path(self.report_dir, f"backtest_{result.strategy}", unique=True),
            result.to_report(),
        )
