"""Shared CLI context and helpers."""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from quant.alpha.alpha_engine import AlphaEngine
from quant.agent_export.agent_exporter import AgentExporter
from quant.backtest.backtest_engine import PortfolioBacktestEngine
from quant.cost.cost_engine import CostEngine, TradeInput
from quant.data_layer.data_quality import DataQualityAnalyzer, DataRefreshManager
from quant.data_layer.symbol_metadata import SymbolMetadataStore
from quant.data_layer.universe_manager import UniverseManager
from quant.data_providers import DataProvider, ProviderRegistry, create_default_registry
from quant.execution.execution_engine import ExecutionEngine
from quant.factor_backtest.factor_backtest import FactorBacktest
from quant.factor_eval.factor_evaluation import FactorEvaluation
from quant.optimizer.optimizer_engine import OptimizerEngine
from quant.portfolio_construction.portfolio_construction import PortfolioConstructionEngine
from quant.rebalance.rebalance_engine import RebalanceEngine
from quant.risk.risk_engine import RiskEngine
from quant.services.backtest_service import BacktestService
from quant.services.portfolio_service import PortfolioService
from quant.services.price_service import PriceService
from quant.storage.portfolio_store import SQLitePortfolioStore
from quant.storage.sqlite_store import SQLitePriceStore
from quant.strategy_eval.strategy_evaluation import StrategyEvaluation
from quant.trading_simulation.trading_simulator import TradingSimulator
from quant.visualization.report_visualizer import ReportVisualizer
from quant.walk_forward.walk_forward import WalkForwardEngine


@dataclass(frozen=True)
class CLIContext:
    db_path: Path
    price_store: SQLitePriceStore
    portfolio_store: SQLitePortfolioStore
    metadata_store: SymbolMetadataStore
    provider_registry: ProviderRegistry
    data_provider: DataProvider
    price_service: PriceService
    portfolio_service: PortfolioService
    backtest_service: BacktestService
    portfolio_backtest_engine: PortfolioBacktestEngine
    rebalance_engine: RebalanceEngine
    risk_engine: RiskEngine
    optimizer_engine: OptimizerEngine
    portfolio_construction_engine: PortfolioConstructionEngine
    execution_engine: ExecutionEngine
    alpha_engine: AlphaEngine
    factor_evaluation: FactorEvaluation
    factor_backtest_engine: FactorBacktest
    strategy_evaluation: StrategyEvaluation
    universe_manager: UniverseManager
    data_quality_analyzer: DataQualityAnalyzer
    data_refresh_manager: DataRefreshManager
    agent_exporter: AgentExporter
    walk_forward_engine: WalkForwardEngine
    trading_simulator: TradingSimulator
    report_visualizer: ReportVisualizer


def create_context(db_path: Path) -> CLIContext:
    price_store = SQLitePriceStore(db_path)
    portfolio_store = SQLitePortfolioStore(db_path)
    metadata_store = SymbolMetadataStore(db_path)
    provider_registry = create_default_registry()
    data_provider = provider_registry.default_provider()
    price_service = PriceService(price_store, data_source=data_provider)
    return CLIContext(
        db_path=db_path,
        price_store=price_store,
        portfolio_store=portfolio_store,
        metadata_store=metadata_store,
        provider_registry=provider_registry,
        data_provider=data_provider,
        price_service=price_service,
        portfolio_service=PortfolioService(portfolio_store),
        backtest_service=BacktestService(price_store),
        portfolio_backtest_engine=PortfolioBacktestEngine(price_store),
        rebalance_engine=RebalanceEngine(portfolio_store),
        risk_engine=RiskEngine(portfolio_store),
        optimizer_engine=OptimizerEngine(price_store, portfolio_store),
        portfolio_construction_engine=PortfolioConstructionEngine(price_store),
        execution_engine=ExecutionEngine(price_store, portfolio_store),
        alpha_engine=AlphaEngine(price_store),
        factor_evaluation=FactorEvaluation(price_store),
        factor_backtest_engine=FactorBacktest(price_store),
        strategy_evaluation=StrategyEvaluation(),
        universe_manager=UniverseManager(metadata_store, data_provider),
        data_quality_analyzer=DataQualityAnalyzer(price_store, metadata_store),
        data_refresh_manager=DataRefreshManager(price_store, data_provider),
        agent_exporter=AgentExporter(),
        walk_forward_engine=WalkForwardEngine(price_store),
        trading_simulator=TradingSimulator(price_store),
        report_visualizer=ReportVisualizer(),
    )


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
    values: dict[str, float | None] = {}
    for symbol in symbols:
        ticker = symbol.upper().strip()
        history = price_store.get_price_history(ticker, end=as_of_date)
        if history.empty:
            values[ticker] = None
            continue
        history = history.sort_values("date")
        closes = pd.to_numeric(history["close"], errors="coerce").dropna()
        values[ticker] = FactorEvaluation._factor_value(closes, factor)
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
