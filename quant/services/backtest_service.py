"""Minimal SMA crossover backtest engine."""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

import pandas as pd

from quant.storage.sqlite_store import SQLitePriceStore


@dataclass(frozen=True)
class BacktestTrade:
    date: str
    symbol: str
    side: str
    qty: int
    price: float
    commission: float
    cash_after: float
    position_after: int
    pnl: float | None = None


@dataclass(frozen=True)
class BacktestMetrics:
    symbol: str
    start: str
    end: str
    initial_cash: float
    final_value: float
    total_return_pct: float
    max_drawdown_pct: float
    sharpe_ratio: float
    number_of_trades: int
    win_rate_pct: float


@dataclass(frozen=True)
class BacktestResult:
    metrics: BacktestMetrics
    trades: list[BacktestTrade]
    equity_curve: list[dict]
    report_path: str

    def to_report(self) -> dict:
        return {
            "metrics": asdict(self.metrics),
            "trades": [asdict(trade) for trade in self.trades],
            "equity_curve": self.equity_curve,
        }


class BacktestService:
    """Run deterministic long-only SMA crossover backtests from stored prices."""

    def __init__(
        self,
        price_store: SQLitePriceStore,
        report_dir: str | Path = "reports",
    ) -> None:
        self.price_store = price_store
        self.report_dir = Path(report_dir)

    def run_sma_crossover(
        self,
        symbol: str,
        start: str,
        end: str,
        initial_cash: float = 100000.0,
        short_window: int = 20,
        long_window: int = 50,
        commission: float = 0.0,
    ) -> BacktestResult:
        ticker = symbol.upper().strip()
        self._validate_inputs(ticker, start, end, initial_cash, short_window, long_window, commission)

        prices = self.price_store.get_price_history(ticker, start=start, end=end)
        if prices.empty:
            raise ValueError(f"no price data found for {ticker} between {start} and {end}")

        prices = prices.copy()
        prices["date"] = pd.to_datetime(prices["date"])
        prices["close"] = pd.to_numeric(prices["close"], errors="coerce")
        prices = prices.dropna(subset=["close"]).sort_values("date").reset_index(drop=True)
        if prices.empty:
            raise ValueError(f"no valid close prices found for {ticker} between {start} and {end}")

        prices["short_sma"] = prices["close"].rolling(short_window).mean()
        prices["long_sma"] = prices["close"].rolling(long_window).mean()

        cash = float(initial_cash)
        position = 0
        entry_cost: float | None = None
        trades: list[BacktestTrade] = []
        closed_trade_pnls: list[float] = []
        equity_curve: list[dict] = []

        for index, row in prices.iterrows():
            date_text = row["date"].strftime("%Y-%m-%d")
            close = float(row["close"])

            if index > 0:
                previous = prices.iloc[index - 1]
                if self._crossed_above(previous, row) and position == 0:
                    qty = math.floor((cash - commission) / close)
                    if qty > 0:
                        amount = qty * close
                        cash -= amount + commission
                        position = qty
                        entry_cost = amount + commission
                        trades.append(
                            BacktestTrade(
                                date=date_text,
                                symbol=ticker,
                                side="BUY",
                                qty=qty,
                                price=close,
                                commission=commission,
                                cash_after=cash,
                                position_after=position,
                            )
                        )
                elif self._crossed_below(previous, row) and position > 0:
                    amount = position * close
                    pnl = amount - commission - (entry_cost or 0.0)
                    cash += amount - commission
                    trades.append(
                        BacktestTrade(
                            date=date_text,
                            symbol=ticker,
                            side="SELL",
                            qty=position,
                            price=close,
                            commission=commission,
                            cash_after=cash,
                            position_after=0,
                            pnl=pnl,
                        )
                    )
                    closed_trade_pnls.append(pnl)
                    position = 0
                    entry_cost = None

            equity = cash + (position * close)
            equity_curve.append(
                {
                    "date": date_text,
                    "close": close,
                    "cash": cash,
                    "position": position,
                    "equity": equity,
                }
            )

        final_value = equity_curve[-1]["equity"]
        metrics = BacktestMetrics(
            symbol=ticker,
            start=start,
            end=end,
            initial_cash=float(initial_cash),
            final_value=final_value,
            total_return_pct=((final_value / initial_cash) - 1.0) * 100.0,
            max_drawdown_pct=self._max_drawdown_pct(equity_curve),
            sharpe_ratio=self._sharpe_ratio(equity_curve),
            number_of_trades=len(trades),
            win_rate_pct=self._win_rate_pct(closed_trade_pnls),
        )

        report_path = self._write_report(ticker, BacktestResult(metrics, trades, equity_curve, ""))
        return BacktestResult(metrics, trades, equity_curve, str(report_path))

    @staticmethod
    def _validate_inputs(
        symbol: str,
        start: str,
        end: str,
        initial_cash: float,
        short_window: int,
        long_window: int,
        commission: float,
    ) -> None:
        if not symbol:
            raise ValueError("symbol must not be empty")
        if not start or not end:
            raise ValueError("start and end are required")
        if initial_cash <= 0:
            raise ValueError("cash must be positive")
        if short_window <= 0 or long_window <= 0:
            raise ValueError("SMA windows must be positive")
        if short_window >= long_window:
            raise ValueError("short_window must be less than long_window")
        if commission < 0:
            raise ValueError("commission must be non-negative")

    @staticmethod
    def _crossed_above(previous: pd.Series, current: pd.Series) -> bool:
        if pd.isna(previous["short_sma"]) or pd.isna(previous["long_sma"]):
            return False
        if pd.isna(current["short_sma"]) or pd.isna(current["long_sma"]):
            return False
        return previous["short_sma"] <= previous["long_sma"] and current["short_sma"] > current["long_sma"]

    @staticmethod
    def _crossed_below(previous: pd.Series, current: pd.Series) -> bool:
        if pd.isna(previous["short_sma"]) or pd.isna(previous["long_sma"]):
            return False
        if pd.isna(current["short_sma"]) or pd.isna(current["long_sma"]):
            return False
        return previous["short_sma"] >= previous["long_sma"] and current["short_sma"] < current["long_sma"]

    @staticmethod
    def _max_drawdown_pct(equity_curve: list[dict]) -> float:
        equities = pd.Series([point["equity"] for point in equity_curve], dtype="float64")
        drawdowns = (equities / equities.cummax()) - 1.0
        return abs(float(drawdowns.min() * 100.0))

    @staticmethod
    def _sharpe_ratio(equity_curve: list[dict]) -> float:
        equities = pd.Series([point["equity"] for point in equity_curve], dtype="float64")
        returns = equities.pct_change().dropna()
        if returns.empty:
            return 0.0
        std = returns.std()
        if std == 0 or pd.isna(std):
            return 0.0
        return float((returns.mean() / std) * math.sqrt(252))

    @staticmethod
    def _win_rate_pct(closed_trade_pnls: list[float]) -> float:
        if not closed_trade_pnls:
            return 0.0
        wins = sum(1 for pnl in closed_trade_pnls if pnl > 0)
        return (wins / len(closed_trade_pnls)) * 100.0

    def _write_report(self, symbol: str, result: BacktestResult) -> Path:
        self.report_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = self.report_dir / f"backtest_{symbol}_{timestamp}.json"
        path.write_text(json.dumps(result.to_report(), indent=2), encoding="utf-8")
        return path

