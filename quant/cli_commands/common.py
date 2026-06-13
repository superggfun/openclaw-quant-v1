"""Shared CLI context and helpers."""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path

import pandas as pd

from quant.engines.alpha.alpha_engine import AlphaEngine
from quant.reports.agent_export.agent_exporter import AgentExporter
from quant.engines.backtest.backtest_engine import PortfolioBacktestEngine
from quant.engines.execution.cost_engine import CostEngine, TradeInput
from quant.data.layer.data_quality import DataQualityAnalyzer, DataRefreshManager
from quant.data.layer.symbol_metadata import SymbolMetadataStore
from quant.data.layer.universe_manager import UniverseManager
from quant.data.providers import DataProvider, ProviderRegistry, create_default_registry
from quant.engines.execution.execution_engine import ExecutionEngine
from quant.engines.factor_backtest.factor_backtest import FactorBacktest
from quant.engines.factor_eval.factor_evaluation import FactorEvaluation
from quant.factors.store.factor_history import FactorHistory
from quant.factors.store.factor_registry_store import FactorRegistryStore
from quant.factors.store.factor_store import FactorStore
from quant.data.fundamental.fundamental_service import FundamentalService
from quant.data.fundamental.fundamental_store import FundamentalStore
from quant.engines.portfolio.optimizer_engine import OptimizerEngine
from quant.engines.portfolio.portfolio_construction import PortfolioConstructionEngine
from quant.engines.portfolio.rebalance_engine import RebalanceEngine
from quant.engines.regime.regime_analytics import RegimeAnalytics
from quant.engines.regime.regime_detector import RegimeDetector
from quant.engines.regime.regime_history import RegimeHistoryStore
from quant.engines.risk.risk_engine import RiskEngine
from quant.services.backtest_service import BacktestService
from quant.services.portfolio_service import PortfolioService
from quant.services.price_service import PriceService
from quant.storage.portfolio_store import SQLitePortfolioStore
from quant.storage.sqlite_store import SQLitePriceStore
from quant.engines.strategy_eval.strategy_evaluation import StrategyEvaluation
from quant.engines.trading_simulation.trading_simulator import TradingSimulator
from quant.reports.visualization.report_visualizer import ReportVisualizer
from quant.engines.walk_forward.walk_forward import WalkForwardEngine


@dataclass(frozen=True)
class CLIContext:
    db_path: Path

    @cached_property
    def price_store(self) -> SQLitePriceStore:
        return SQLitePriceStore(self.db_path)

    @cached_property
    def portfolio_store(self) -> SQLitePortfolioStore:
        return SQLitePortfolioStore(self.db_path)

    @cached_property
    def metadata_store(self) -> SymbolMetadataStore:
        return SymbolMetadataStore(self.db_path)

    @cached_property
    def fundamental_store(self) -> FundamentalStore:
        return FundamentalStore(self.db_path)

    @cached_property
    def provider_registry(self) -> ProviderRegistry:
        return create_default_registry()

    @cached_property
    def data_provider(self) -> DataProvider:
        return self.provider_registry.default_provider()

    @cached_property
    def price_service(self) -> PriceService:
        return PriceService(self.price_store, data_source=self.data_provider)

    @cached_property
    def portfolio_service(self) -> PortfolioService:
        return PortfolioService(self.portfolio_store)

    @cached_property
    def backtest_service(self) -> BacktestService:
        return BacktestService(self.price_store)

    @cached_property
    def portfolio_backtest_engine(self) -> PortfolioBacktestEngine:
        return PortfolioBacktestEngine(self.price_store)

    @cached_property
    def rebalance_engine(self) -> RebalanceEngine:
        return RebalanceEngine(self.portfolio_store)

    @cached_property
    def risk_engine(self) -> RiskEngine:
        return RiskEngine(self.portfolio_store)

    @cached_property
    def optimizer_engine(self) -> OptimizerEngine:
        return OptimizerEngine(self.price_store, self.portfolio_store)

    @cached_property
    def portfolio_construction_engine(self) -> PortfolioConstructionEngine:
        return PortfolioConstructionEngine(self.price_store)

    @cached_property
    def execution_engine(self) -> ExecutionEngine:
        return ExecutionEngine(self.price_store, self.portfolio_store)

    @cached_property
    def alpha_engine(self) -> AlphaEngine:
        return AlphaEngine(self.price_store, self.fundamental_store)

    @cached_property
    def factor_evaluation(self) -> FactorEvaluation:
        return FactorEvaluation(self.price_store, self.fundamental_store)

    @cached_property
    def factor_backtest_engine(self) -> FactorBacktest:
        return FactorBacktest(self.price_store, self.fundamental_store)

    @cached_property
    def factor_store(self) -> FactorStore:
        return FactorStore(self.db_path)

    @cached_property
    def factor_history(self) -> FactorHistory:
        return FactorHistory(self.factor_store)

    @cached_property
    def factor_registry_store(self) -> FactorRegistryStore:
        return FactorRegistryStore(self.factor_store)

    @cached_property
    def regime_detector(self) -> RegimeDetector:
        return RegimeDetector(self.price_store)

    @cached_property
    def regime_history_store(self) -> RegimeHistoryStore:
        return RegimeHistoryStore(self.db_path)

    @cached_property
    def regime_analytics(self) -> RegimeAnalytics:
        return RegimeAnalytics(self.regime_detector, self.regime_history_store, self.factor_store)

    @cached_property
    def strategy_evaluation(self) -> StrategyEvaluation:
        return StrategyEvaluation()

    @cached_property
    def universe_manager(self) -> UniverseManager:
        return UniverseManager(self.metadata_store, self.data_provider)

    @cached_property
    def data_quality_analyzer(self) -> DataQualityAnalyzer:
        return DataQualityAnalyzer(self.price_store, self.metadata_store)

    @cached_property
    def data_refresh_manager(self) -> DataRefreshManager:
        return DataRefreshManager(self.price_store, self.data_provider)

    @cached_property
    def fundamental_service(self) -> FundamentalService:
        return FundamentalService(self.fundamental_store)

    @cached_property
    def agent_exporter(self) -> AgentExporter:
        return AgentExporter()

    @cached_property
    def walk_forward_engine(self) -> WalkForwardEngine:
        return WalkForwardEngine(self.price_store, self.fundamental_store)

    @cached_property
    def trading_simulator(self) -> TradingSimulator:
        return TradingSimulator(self.price_store, self.fundamental_store)

    @cached_property
    def report_visualizer(self) -> ReportVisualizer:
        return ReportVisualizer()


def create_context(db_path: Path) -> CLIContext:
    return CLIContext(db_path=db_path)


def format_optional_money(value: float | None) -> str:
    return "N/A" if value is None else f"{value:.2f}"


def format_optional_number(value: float | None) -> str:
    return "N/A" if value is None else f"{value:.6f}"


def format_optional_pct(value: float | None) -> str:
    return "N/A" if value is None else f"{value * 100:.2f}%"


def format_optional_rank(value: int | None) -> str:
    return "N/A" if value is None else str(value)


def load_targets(path: Path) -> dict:
    try:
        with path.open("r", encoding="utf-8") as file:
            targets = json.load(file)
    except FileNotFoundError as exc:
        raise ValueError(f"targets file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"targets file is not valid JSON: {path}") from exc

    if not isinstance(targets, dict):
        raise ValueError("targets file must contain a JSON object")
    return targets


def load_cost_config(path: Path) -> dict:
    if not path.exists():
        return {}
    return _load_json_object(path, "cost config")


def load_market_realism_config(path: Path) -> dict:
    if not path.exists():
        return {}
    return _load_json_object(path, "market realism config")


def apply_cost_overrides(config: dict, args) -> None:
    if args.model is not None:
        config["model"] = args.model
    if args.fixed_fee is not None:
        config["fixed_fee"] = args.fixed_fee
    if args.commission_rate is not None:
        config["commission_rate"] = args.commission_rate
    if args.min_commission is not None:
        config["min_commission"] = args.min_commission
    if args.slippage_bps is not None:
        config["slippage_bps"] = args.slippage_bps
    if args.min_trade_notional is not None:
        config["min_trade_notional"] = args.min_trade_notional


def load_optimizer_config(path: Path) -> dict:
    if not path.exists():
        return {}
    return _load_json_object(path, "optimizer config")


def load_alpha_config(path: Path) -> dict:
    if not path.exists():
        return {}
    return _load_json_object(path, "alpha config")


def load_factor_pipeline_config(path: Path) -> dict:
    try:
        return _load_json_object(path, "factor pipeline config")
    except FileNotFoundError as exc:
        raise ValueError(f"factor pipeline config file not found: {path}") from exc


def trades_from_rebalance_plan(plan) -> list[TradeInput]:
    return [
        TradeInput(
            symbol=item.symbol,
            side=item.action,
            shares=item.qty,
            price=float(item.price),
        )
        for item in plan.items
        if item.action in {"BUY", "SELL"} and item.qty > 0 and item.price is not None
    ]


def print_cost_report(report) -> None:
    print("cost_estimate:")
    print(f"model: {report.model}")
    print(f"currency: {report.currency}")
    print(f"gross_trade_value: {report.gross_trade_value:.2f}")
    print(f"total_commission: {report.total_commission:.2f}")
    print(f"total_slippage: {report.total_slippage:.2f}")
    print(f"total_market_impact: {getattr(report, 'total_market_impact', 0.0):.2f}")
    print(f"total_liquidity_cost: {getattr(report, 'total_liquidity_cost', 0.0):.2f}")
    print(f"total_cost: {report.total_cost:.2f}")
    print(f"total_cost_ratio: {report.total_cost_ratio:.6f}")
    print("trades:")
    for trade in report.trades:
        print(
            f"{trade.side:<4} {trade.symbol:<6} shares={trade.shares} "
            f"notional={trade.notional:.2f} total_cost={trade.total_cost:.2f} "
            f"cost_ratio={trade.cost_ratio:.6f}"
        )
    for warning in report.warnings:
        print(f"warning: {warning}", file=sys.stderr)
    print(f"cost_report: {report.report_path}")


def factor_values_for_pipeline(
    price_store: SQLitePriceStore,
    factor: str,
    symbols: list[str],
    as_of_date: str | None,
) -> dict[str, float | None]:
    fundamental_store = FundamentalStore(price_store.db_path)
    factor_registry = FactorEvaluation(price_store, fundamental_store).factor_registry
    values: dict[str, float | None] = {}
    for symbol in symbols:
        ticker = symbol.upper().strip()
        history = price_store.get_price_history(ticker, end=as_of_date)
        if history.empty:
            values[ticker] = None
            continue
        history = history.sort_values("date")
        closes = pd.to_numeric(history["close"], errors="coerce").dropna()
        signal_date = as_of_date or str(history.iloc[-1]["date"])
        values[ticker] = FactorEvaluation._factor_value(
            closes,
            factor,
            symbol=ticker,
            signal_date=signal_date,
            registry=factor_registry,
        )
    return values


def benchmark_returns_for_report(
    price_store: SQLitePriceStore,
    benchmark: str,
    report_path: Path,
) -> dict[str, float] | None:
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"benchmark source report not found: {report_path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"benchmark source report is not valid JSON: {report_path}") from exc

    start, end = report_date_window(report)
    history = price_store.get_price_history(benchmark.upper(), start=start, end=end)
    if history.empty or len(history) < 2:
        return None
    history = history.sort_values("date")
    closes = pd.to_numeric(history["close"], errors="coerce")
    returns = closes.pct_change()
    output: dict[str, float] = {}
    for date_value, value in zip(history["date"], returns, strict=False):
        if pd.notna(value):
            output[str(date_value)] = float(value)
    return output


def report_date_window(report: dict) -> tuple[str | None, str | None]:
    if "start" in report or "end" in report:
        return report.get("start"), report.get("end")
    if "start_date" in report or "end_date" in report:
        return report.get("start_date"), report.get("end_date")
    periods = report.get("periods") or []
    dates = [
        str(period.get("signal_date"))
        for period in periods
        if isinstance(period, dict) and period.get("signal_date")
    ]
    if dates:
        return min(dates), max(dates)
    return None, None


def _load_json_object(path: Path, label: str) -> dict:
    try:
        with path.open("r", encoding="utf-8") as file:
            config = json.load(file)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{label} is not valid JSON: {path}") from exc

    if not isinstance(config, dict):
        raise ValueError(f"{label} must contain a JSON object")
    return config


def estimate_costs(config: dict, trades: list[TradeInput]):
    return CostEngine(config).estimate(trades)
