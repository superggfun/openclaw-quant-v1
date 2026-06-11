"""Command line interface for OpenClaw Quant."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

from quant.alpha.alpha_engine import AlphaEngine
from quant.backtest.backtest_engine import PortfolioBacktestEngine
from quant.config import DB_PATH, DEFAULT_SYMBOLS
from quant.cost.cost_engine import CostEngine, TradeInput
from quant.execution.execution_engine import ExecutionEngine
from quant.factor_backtest.factor_backtest import FactorBacktest
from quant.factor_eval.factor_evaluation import FactorEvaluation, SUPPORTED_FACTORS
from quant.factor_pipeline.factor_pipeline import FactorPipeline
from quant.optimizer.optimizer_engine import DEFAULT_CONSTRAINTS, OptimizerEngine
from quant.rebalance.rebalance_engine import DEFAULT_COMMISSION_RATE, RebalanceEngine
from quant.risk.risk_engine import RiskEngine
from quant.services.backtest_service import BacktestService
from quant.services.portfolio_service import PortfolioService
from quant.services.price_service import PriceService
from quant.storage.portfolio_store import SQLitePortfolioStore
from quant.storage.sqlite_store import SQLitePriceStore
from quant.strategy_eval.strategy_evaluation import StrategyEvaluation


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="openclaw-quant")
    parser.add_argument(
        "--db-path",
        default=str(DB_PATH),
        help="SQLite database path. Defaults to data/quant.db.",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    update = subparsers.add_parser("update-prices", help="Download and store daily prices.")
    update.add_argument(
        "--symbols",
        nargs="+",
        default=list(DEFAULT_SYMBOLS),
        help="Symbols to update. Defaults to the configured stock pool.",
    )
    update.add_argument("--start", default=None, help="Optional inclusive start date YYYY-MM-DD.")
    update.add_argument("--end", default=None, help="Optional exclusive end date YYYY-MM-DD.")

    show = subparsers.add_parser("show-prices", help="Show recent prices for one symbol.")
    show.add_argument("symbol")
    show.add_argument("--limit", type=int, default=10)

    subparsers.add_parser("list-symbols", help="List configured and stored symbols.")

    init_account = subparsers.add_parser(
        "init-account",
        help="Initialize or reset the default simulated account.",
    )
    init_account.add_argument("--cash", type=float, required=True)

    buy = subparsers.add_parser("buy", help="Record a simulated buy.")
    buy.add_argument("symbol")
    buy.add_argument("--qty", type=float, required=True)
    buy.add_argument("--price", type=float, required=True)

    sell = subparsers.add_parser("sell", help="Record a simulated sell.")
    sell.add_argument("symbol")
    sell.add_argument("--qty", type=float, required=True)
    sell.add_argument("--price", type=float, required=True)

    subparsers.add_parser("portfolio", help="Show simulated portfolio state.")
    subparsers.add_parser("trades", help="Show simulated trade history.")

    subparsers.add_parser("allocation", help="Show current portfolio allocation.")

    rebalance = subparsers.add_parser("rebalance", help="Calculate a portfolio rebalance plan.")
    rebalance.add_argument("--targets", required=True, help="Path to target allocation JSON.")
    rebalance.add_argument("--commission", type=float, default=DEFAULT_COMMISSION_RATE)
    rebalance.add_argument("--with-costs", action="store_true", help="Include transaction cost estimate.")
    rebalance.add_argument("--cost-config", default="examples/cost_config.json")

    subparsers.add_parser("risk", help="Calculate portfolio risk metrics.")

    optimize = subparsers.add_parser("optimize", help="Generate an optimized target allocation.")
    optimize.add_argument("--config", default="examples/optimizer_config.json")
    optimize.add_argument("--mode", choices=["equal_weight", "risk_adjusted", "constrained"], default=None)
    optimize.add_argument("--output-targets", default=None)
    optimize.add_argument("--max-position-weight", type=float, default=None)
    optimize.add_argument("--min-cash-weight", type=float, default=None)
    optimize.add_argument("--max-sector-weight", type=float, default=None)

    alpha = subparsers.add_parser("alpha", help="Generate alpha factors and target weights.")
    alpha.add_argument("--config", default="examples/alpha_config.json")
    alpha.add_argument("--output-targets", default=None)
    alpha.add_argument("--pipeline", default=None, help="Optional factor pipeline config JSON.")

    factor_eval = subparsers.add_parser("factor-eval", help="Evaluate alpha factor predictive quality.")
    factor_eval.add_argument("--factor", choices=sorted(SUPPORTED_FACTORS), required=True)
    factor_eval.add_argument("--start", default=None, help="Inclusive signal start date YYYY-MM-DD.")
    factor_eval.add_argument("--end", default=None, help="Inclusive signal end date YYYY-MM-DD.")
    factor_eval.add_argument("--forward-days", type=int, default=20)
    factor_eval.add_argument("--pipeline", default=None, help="Optional factor pipeline config JSON.")

    factor_backtest = subparsers.add_parser("factor-backtest", help="Run a long-short factor backtest.")
    factor_backtest.add_argument("--factor", choices=sorted(SUPPORTED_FACTORS), required=True)
    factor_backtest.add_argument("--start", default=None, help="Inclusive signal start date YYYY-MM-DD.")
    factor_backtest.add_argument("--end", default=None, help="Inclusive signal end date YYYY-MM-DD.")
    factor_backtest.add_argument("--holding-period", type=int, default=20)
    factor_backtest.add_argument("--quantiles", type=int, default=5)
    factor_backtest.add_argument("--long-quantile", type=int, default=None)
    factor_backtest.add_argument("--short-quantile", type=int, default=1)
    factor_backtest.add_argument("--pipeline", default=None, help="Optional factor pipeline config JSON.")
    factor_backtest.add_argument("--report", action="store_true", help="Write JSON report. Reports are written by default.")

    factor_pipeline = subparsers.add_parser("factor-pipeline", help="Run factor preprocessing for one signal date.")
    factor_pipeline.add_argument("--factor", choices=sorted(SUPPORTED_FACTORS), required=True)
    factor_pipeline.add_argument("--config", default="examples/factor_pipeline_config.json")
    factor_pipeline.add_argument("--as-of-date", default=None)
    factor_pipeline.add_argument("--symbols", nargs="+", default=list(DEFAULT_SYMBOLS))

    strategy_eval = subparsers.add_parser("strategy-eval", help="Evaluate and attribute a generated strategy report.")
    strategy_eval.add_argument("--report", default=None, help="Legacy alias for a source report JSON.")
    strategy_eval.add_argument("--backtest-report", default=None, help="Path to a portfolio backtest JSON report.")
    strategy_eval.add_argument("--factor-backtest-report", default=None, help="Path to a factor backtest JSON report.")
    strategy_eval.add_argument("--strategy", choices=["alpha", "factor_long_short"], default=None)
    strategy_eval.add_argument("--factor", choices=sorted(SUPPORTED_FACTORS), default="momentum_20d")
    strategy_eval.add_argument("--pipeline", default=None, help="Optional factor pipeline config JSON.")
    strategy_eval.add_argument("--benchmark", default=None, help="Optional benchmark symbol, for example SPY.")
    strategy_eval.add_argument("--output", default=None, help="Optional strategy evaluation report output path.")

    cost = subparsers.add_parser("cost", help="Estimate transaction costs for rebalance suggestions.")
    cost.add_argument("--targets", default="examples/optimized_targets.json")
    cost.add_argument("--config", default="examples/cost_config.json")
    cost.add_argument("--model", choices=["fixed", "linear", "combined"], default=None)
    cost.add_argument("--fixed-fee", type=float, default=None)
    cost.add_argument("--commission-rate", type=float, default=None)
    cost.add_argument("--min-commission", type=float, default=None)
    cost.add_argument("--slippage-bps", type=float, default=None)
    cost.add_argument("--min-trade-notional", type=float, default=None)

    execute_sim = subparsers.add_parser("execute-sim", help="Simulate execution of rebalance suggestions.")
    execute_sim.add_argument("--targets", required=True, help="Path to target allocation JSON.")
    execute_sim.add_argument(
        "--mode",
        choices=["immediate", "next_day_open", "twap", "partial_fill"],
        default="immediate",
    )
    execute_sim.add_argument("--date", default=None, help="Optional execution reference date YYYY-MM-DD.")
    execute_sim.add_argument("--cost-config", default="examples/cost_config.json")
    execute_sim.add_argument("--twap-slices", type=int, default=4)
    execute_sim.add_argument("--fill-ratio", type=float, default=0.5)

    backtest = subparsers.add_parser("backtest", help="Run a portfolio backtest.")
    backtest.add_argument("--symbol", default=None, help="Optional legacy SMA symbol backtest.")
    backtest.add_argument("--start", required=True, help="Inclusive start date YYYY-MM-DD.")
    backtest.add_argument("--end", required=True, help="Inclusive end date YYYY-MM-DD.")
    backtest.add_argument("--cash", type=float, default=100000.0)
    backtest.add_argument("--initial-cash", type=float, default=None)
    backtest.add_argument("--strategy", choices=["portfolio", "alpha"], default="portfolio")
    backtest.add_argument("--mode", choices=["equal_weight", "risk_adjusted", "constrained"], default="equal_weight")
    backtest.add_argument("--rebalance-frequency", choices=["monthly", "weekly", "daily"], default="monthly")
    backtest.add_argument("--execution-price", choices=["close", "open"], default="close")
    backtest.add_argument("--alpha-config", default="examples/alpha_config.json")
    backtest.add_argument("--short-window", type=int, default=20)
    backtest.add_argument("--long-window", type=int, default=50)
    backtest.add_argument("--commission", type=float, default=0.0)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    db_path = Path(args.db_path)
    price_store = SQLitePriceStore(db_path)
    price_service = PriceService(price_store)
    portfolio_store = SQLitePortfolioStore(db_path)
    portfolio_service = PortfolioService(portfolio_store)
    backtest_service = BacktestService(price_store)
    portfolio_backtest_engine = PortfolioBacktestEngine(price_store)
    rebalance_engine = RebalanceEngine(portfolio_store)
    risk_engine = RiskEngine(portfolio_store)
    optimizer_engine = OptimizerEngine(price_store, portfolio_store)
    execution_engine = ExecutionEngine(price_store, portfolio_store)
    alpha_engine = AlphaEngine(price_store)
    factor_evaluation = FactorEvaluation(price_store)
    factor_backtest_engine = FactorBacktest(price_store)
    strategy_evaluation = StrategyEvaluation()

    if args.command == "update-prices":
        results = price_service.update_prices(args.symbols, start=args.start, end=args.end)
        for symbol, changed in results.items():
            print(f"{symbol}: {changed} rows inserted/updated")
        return 0

    if args.command == "show-prices":
        rows = price_service.show_prices(args.symbol, limit=args.limit)
        if not rows:
            print(f"No prices found for {args.symbol.upper()}.")
            return 0
        print("symbol date       open       high       low        close      adj_close  volume")
        for row in rows:
            print(
                f"{row['symbol']:<6} {row['date']} "
                f"{row['open']:>10.2f} {row['high']:>10.2f} {row['low']:>10.2f} "
                f"{row['close']:>10.2f} {row['adj_close']:>10.2f} {row['volume']:>10}"
            )
        return 0

    if args.command == "list-symbols":
        for symbol in price_service.list_symbols():
            print(symbol)
        return 0

    try:
        if args.command == "init-account":
            account = portfolio_service.init_account(args.cash)
            print(
                f"Initialized account {account['name']} "
                f"with cash {account['cash']:.2f}"
            )
            return 0

        if args.command == "buy":
            position = portfolio_service.buy(args.symbol, qty=args.qty, price=args.price)
            print(
                f"BUY {position['symbol']} position_qty={position['qty']:.6g} "
                f"avg_cost={position['avg_cost']:.2f}"
            )
            return 0

        if args.command == "sell":
            position = portfolio_service.sell(args.symbol, qty=args.qty, price=args.price)
            if position is None:
                print(f"SELL {args.symbol.upper()} position closed")
            else:
                print(
                    f"SELL {position['symbol']} remaining_qty={position['qty']:.6g} "
                    f"avg_cost={position['avg_cost']:.2f}"
                )
            return 0

        if args.command == "portfolio":
            snapshot = portfolio_service.portfolio()
            print(f"cash: {snapshot.cash:.2f}")
            print("symbol qty        avg_cost   current    market_value unrealized_pnl")
            for position in snapshot.positions:
                print(
                    f"{position.symbol:<6} {position.qty:>10.6g} "
                    f"{position.avg_cost:>10.2f} "
                    f"{_format_optional_money(position.current_price):>10} "
                    f"{_format_optional_money(position.market_value):>12} "
                    f"{_format_optional_money(position.unrealized_pnl):>14}"
                )
            print(f"total_assets: {snapshot.total_assets:.2f}")
            return 0

        if args.command == "trades":
            rows = portfolio_service.trades()
            if not rows:
                print("No trades found.")
                return 0
            print("id side symbol qty        price      amount     created_at")
            for row in rows:
                print(
                    f"{row['id']:<3} {row['side']:<4} {row['symbol']:<6} "
                    f"{row['qty']:>10.6g} {row['price']:>10.2f} "
                    f"{row['amount']:>10.2f} {row['created_at']}"
                )
            return 0

        if args.command == "allocation":
            snapshot = rebalance_engine.allocation()
            print(f"total_assets: {snapshot.total_assets:.2f}")
            print("symbol current_value current_weight_pct qty        price")
            for item in snapshot.items:
                print(
                    f"{item.symbol:<6} {item.current_value:>13.2f} "
                    f"{item.current_weight * 100:>18.2f} "
                    f"{item.qty:>10.6g} {_format_optional_money(item.price):>10}"
                )
            return 0

        if args.command == "rebalance":
            targets = _load_targets(Path(args.targets))
            plan = rebalance_engine.plan(targets, commission_rate=args.commission)
            print("Rebalance Plan")
            print(f"total_assets: {plan.total_assets:.2f}")
            print(f"cash_before: {plan.cash_before:.2f}")
            print(f"cash_after_rebalance: {plan.cash_after_rebalance:.2f}")
            print(f"estimated_total_commission: {plan.estimated_total_commission:.2f}")
            print(
                "symbol current_value target_value difference "
                "current_pct target_pct action qty est_trade_cost"
            )
            for item in plan.items:
                print(
                    f"{item.symbol:<6} {item.current_value:>13.2f} "
                    f"{item.target_value:>12.2f} {item.difference:>10.2f} "
                    f"{item.current_weight * 100:>11.2f} {item.target_weight * 100:>10.2f} "
                    f"{item.action:<6} {item.qty:>5} {item.estimated_trade_cost:>14.2f}"
                )
            suggestions = [item for item in plan.items if item.action in {"BUY", "SELL"} and item.qty > 0]
            if suggestions:
                print("suggestions:")
                for item in suggestions:
                    print(f"{item.action} {item.symbol} {item.qty} shares")
            else:
                print("suggestions: no trades")
            for warning in plan.warnings:
                print(f"warning: {warning}", file=sys.stderr)
            if args.with_costs:
                cost_config = _load_cost_config(Path(args.cost_config))
                cost_report = CostEngine(cost_config).estimate(_trades_from_rebalance_plan(plan))
                _print_cost_report(cost_report)
            print(f"report: {plan.report_path}")
            return 0

        if args.command == "risk":
            report = risk_engine.analyze()
            print("Risk Summary")
            print(f"total_assets: {report.total_assets:.2f}")
            print(f"cash_weight_pct: {report.cash_weight_pct:.2f}")
            print(f"single_stock_concentration_pct: {report.single_stock_concentration_pct:.2f}")
            print(f"industry_concentration_pct: {report.industry_concentration_pct:.2f}")
            print(f"top_5_holdings_pct: {report.top_5_holdings_pct:.2f}")
            print(f"risk_score: {report.risk_score:.2f}")
            print("holdings:")
            for holding in report.holdings:
                print(
                    f"{holding.symbol:<6} {holding.industry:<24} "
                    f"value={holding.value:.2f} weight_pct={holding.weight_pct:.2f}"
                )
            print("industries:")
            for industry in report.industries:
                print(
                    f"{industry.industry:<24} value={industry.value:.2f} "
                    f"weight_pct={industry.weight_pct:.2f}"
                )
            for warning in report.warnings:
                print(f"warning: {warning}", file=sys.stderr)
            print(f"report: {report.report_path}")
            return 0

        if args.command == "optimize":
            config = _load_optimizer_config(Path(args.config))
            mode = args.mode or config.get("mode", "equal_weight")
            constraints = dict(DEFAULT_CONSTRAINTS)
            constraints.update(config.get("constraints", {}))
            if args.max_position_weight is not None:
                constraints["max_position_weight"] = args.max_position_weight
            if args.min_cash_weight is not None:
                constraints["min_cash_weight"] = args.min_cash_weight
            if args.max_sector_weight is not None:
                constraints["max_sector_weight"] = args.max_sector_weight

            targets_path = args.output_targets or config.get("output_targets", "examples/optimized_targets.json")
            result = optimizer_engine.optimize(
                mode=mode,
                symbols=config.get("symbols"),
                constraints=constraints,
                targets_path=targets_path,
            )
            print("Optimizer Summary")
            print(f"mode: {result.mode}")
            print(f"risk_score_before: {result.risk_score_before:.2f}")
            print(f"estimated_risk_score_after: {result.estimated_risk_score_after:.2f}")
            print("optimized_allocation:")
            for symbol, weight in result.optimized_allocation.items():
                print(f"{symbol:<6} {weight * 100:>8.2f}%")
            for warning in result.warnings:
                print(f"warning: {warning}", file=sys.stderr)
            print(f"targets: {result.targets_path}")
            print(f"report: {result.report_path}")
            return 0

        if args.command == "alpha":
            config = _load_alpha_config(Path(args.config))
            pipeline_config = _load_factor_pipeline_config(Path(args.pipeline)) if args.pipeline else None
            result = alpha_engine.generate(
                config=config,
                output_targets=args.output_targets,
                pipeline_config=pipeline_config,
            )
            print("Alpha Summary")
            print(f"as_of_date: {result.as_of_date or 'latest'}")
            print(f"data_start_date: {result.data_start_date or 'N/A'}")
            print(f"data_end_date: {result.data_end_date or 'N/A'}")
            print(f"lookback_used: {json.dumps(result.lookback_used, sort_keys=True)}")
            print(f"suggested_execution_date: {result.suggested_execution_date or 'next_available_session'}")
            print(f"weighting_mode: {result.config['weighting_mode']}")
            print("factors:")
            print("symbol rank selected excluded momentum_20d momentum_60d volatility_20d risk_adjusted_momentum")
            for row in result.factors:
                print(
                    f"{row.symbol:<6} {_format_optional_rank(row.rank):>4} "
                    f"{str(row.selected):<8} "
                    f"{str(row.excluded):<8} "
                    f"{_format_optional_number(row.momentum_20d):>12} "
                    f"{_format_optional_number(row.momentum_60d):>12} "
                    f"{_format_optional_number(row.volatility_20d):>14} "
                    f"{_format_optional_number(row.risk_adjusted_momentum):>23}"
                )
            if result.excluded_symbols:
                print("excluded_symbols:")
                for symbol in result.excluded_symbols:
                    print(f"{symbol}: {result.exclusion_reasons[symbol]}")
            print("selected_symbols:")
            for symbol in result.selected_symbols:
                print(symbol)
            print("target_weights:")
            for symbol, weight in result.target_weights.items():
                print(f"{symbol:<6} {weight * 100:>8.2f}%")
            for warning in result.warnings:
                print(f"warning: {warning}", file=sys.stderr)
            if result.pipeline_report_path:
                print(f"pipeline_report: {result.pipeline_report_path}")
            if result.targets_path:
                print(f"targets: {result.targets_path}")
            print(f"report: {result.report_path}")
            return 0

        if args.command == "factor-pipeline":
            pipeline_config = _load_factor_pipeline_config(Path(args.config))
            raw_values = _factor_values_for_pipeline(
                price_store=price_store,
                factor=args.factor,
                symbols=args.symbols,
                as_of_date=args.as_of_date,
            )
            result = FactorPipeline(pipeline_config).run(
                raw_values,
                factor=args.factor,
                as_of_date=args.as_of_date or "latest",
            )
            print("Factor Pipeline Summary")
            print(f"factor: {result.factor}")
            print(f"as_of_date: {result.as_of_date}")
            print(f"no_lookahead: {str(result.no_lookahead).lower()}")
            print(f"preprocessing_steps_applied: {', '.join(result.preprocessing_steps_applied)}")
            print("raw_factor_values:")
            for symbol, value in sorted(result.raw_factor_values.items()):
                print(f"{symbol:<6} {_format_optional_number(value)}")
            print("cleaned_factor_values:")
            for symbol, value in sorted(result.cleaned_factor_values.items()):
                print(f"{symbol:<6} {value:.6f}")
            print(f"before_summary_statistics: {json.dumps(result.before_summary_statistics, sort_keys=True)}")
            print(f"after_summary_statistics: {json.dumps(result.after_summary_statistics, sort_keys=True)}")
            if result.sector_neutralization_result:
                print("sector_neutralization_result:")
                for sector, metrics in sorted(result.sector_neutralization_result.items()):
                    print(f"{sector}: {json.dumps(metrics, sort_keys=True)}")
            if result.excluded_symbols:
                print("excluded_symbols:")
                for symbol in result.excluded_symbols:
                    print(f"{symbol}: {result.exclusion_reasons[symbol]}")
            for warning in result.warnings:
                print(f"warning: {warning}", file=sys.stderr)
            print(f"report: {result.report_path}")
            return 0

        if args.command == "factor-backtest":
            result = factor_backtest_engine.run(
                factor=args.factor,
                start=args.start,
                end=args.end,
                holding_period=args.holding_period,
                quantiles=args.quantiles,
                long_quantile=args.long_quantile,
                short_quantile=args.short_quantile,
                pipeline_config=_load_factor_pipeline_config(Path(args.pipeline)) if args.pipeline else None,
                pipeline_config_path=args.pipeline,
            )
            print("Factor Backtest Summary")
            print(f"factor: {result.factor}")
            print(f"period: {result.start_date or 'earliest'} to {result.end_date or 'latest'}")
            print(f"holding_period: {result.holding_period}")
            print(f"quantiles: {result.quantiles}")
            print(f"long_quantile: {result.long_quantile}")
            print(f"short_quantile: {result.short_quantile}")
            print(f"no_lookahead: {str(result.no_lookahead).lower()}")
            print(f"signal_execution_lag: {result.signal_execution_lag}")
            print(f"observations: {result.observations}")
            print("quantile_returns:")
            for quantile, value in result.quantile_returns.items():
                print(f"{quantile}: {_format_optional_number(value)}")
            print(f"top_quantile_return: {_format_optional_number(result.top_quantile_return)}")
            print(f"bottom_quantile_return: {_format_optional_number(result.bottom_quantile_return)}")
            print(f"long_short_return: {_format_optional_number(result.long_short_return)}")
            print(f"long_short_annual_return: {_format_optional_number(result.long_short_annual_return)}")
            print(f"long_short_volatility: {_format_optional_number(result.long_short_volatility)}")
            print(f"long_short_sharpe: {_format_optional_number(result.long_short_sharpe)}")
            print(f"max_drawdown: {_format_optional_number(result.max_drawdown)}")
            print(f"hit_rate: {_format_optional_pct(result.hit_rate)}")
            print(f"turnover: {_format_optional_number(result.turnover)}")
            print(f"gross_exposure: {_format_optional_number(result.gross_exposure)}")
            print(f"net_exposure: {_format_optional_number(result.net_exposure)}")
            print(f"ic_mean: {_format_optional_number(result.ic_mean)}")
            print(f"rank_ic_mean: {_format_optional_number(result.rank_ic_mean)}")
            print(f"icir: {_format_optional_number(result.icir)}")
            if result.excluded_symbols:
                print("excluded_symbols:")
                for symbol in result.excluded_symbols:
                    print(f"{symbol}: {result.exclusion_reasons[symbol]}")
            for warning in result.warnings:
                print(f"warning: {warning}", file=sys.stderr)
            print(f"report: {result.report_path}")
            return 0

        if args.command == "strategy-eval":
            source_report = _strategy_eval_source_report(
                args=args,
                price_store=price_store,
                factor_backtest_engine=factor_backtest_engine,
                portfolio_backtest_engine=portfolio_backtest_engine,
            )
            benchmark_returns = (
                _benchmark_returns_for_report(price_store, args.benchmark, Path(source_report))
                if args.benchmark
                else None
            )
            result = strategy_evaluation.evaluate(
                source_report,
                benchmark_returns=benchmark_returns,
                benchmark_name=args.benchmark,
                output_path=args.output,
            )
            print("Strategy Evaluation Summary")
            print(f"source_report: {result.source_report}")
            print(f"strategy_type: {result.strategy_type}")
            print("summary_metrics:")
            for key in [
                "total_return",
                "annual_return",
                "annual_volatility",
                "sharpe_ratio",
                "sortino_ratio",
                "max_drawdown",
                "calmar_ratio",
                "hit_rate",
                "win_loss_ratio",
                "turnover",
                "total_cost",
                "cost_to_return_ratio",
                "gross_exposure",
                "net_exposure",
                "cash_drag",
            ]:
                print(f"{key}: {_format_optional_number(result.summary_metrics.get(key))}")
            if result.benchmark_metrics:
                print("benchmark_metrics:")
                for key in ["benchmark", "benchmark_return", "excess_return", "information_ratio"]:
                    value = result.benchmark_metrics.get(key)
                    print(f"{key}: {value if isinstance(value, str) else _format_optional_number(value)}")
            print("return_attribution:")
            for key in ["long_leg_return", "short_leg_return", "long_short_return", "cash_drag", "cost_drag"]:
                print(f"{key}: {_format_optional_number(result.return_attribution.get(key))}")
            print("risk_attribution:")
            for key in ["gross_exposure", "net_exposure", "average_cash", "average_turnover"]:
                print(f"{key}: {_format_optional_number(result.risk_attribution.get(key))}")
            concentration = result.risk_attribution.get("concentration", {})
            if concentration:
                print(f"largest_position: {concentration.get('largest_position')}")
                print(f"top_3_weight: {_format_optional_number(concentration.get('top_3_weight'))}")
                print(f"top_5_weight: {_format_optional_number(concentration.get('top_5_weight'))}")
            print("drawdown:")
            print(f"max_drawdown: {_format_optional_number(result.drawdown.get('max_drawdown'))}")
            print(f"drawdown_start: {result.drawdown.get('drawdown_start')}")
            print(f"drawdown_end: {result.drawdown.get('drawdown_end')}")
            print(f"drawdown_duration: {result.drawdown.get('drawdown_duration')}")
            print("top_contributors:")
            for row in result.attribution.get("top_positive_contributors", [])[:3]:
                print(f"{row['symbol']}: {_format_optional_number(row['contribution'])}")
            print("top_detractors:")
            for row in result.attribution.get("top_negative_contributors", [])[:3]:
                print(f"{row['symbol']}: {_format_optional_number(row['contribution'])}")
            concentration = result.attribution.get("return_concentration", {})
            if concentration:
                print("return_concentration:")
                print(f"top_1_pct: {_format_optional_number(concentration.get('top_1_pct'))}")
                print(f"top_3_pct: {_format_optional_number(concentration.get('top_3_pct'))}")
            print("monthly_returns:")
            for period, value in list(result.monthly_returns.items())[:6]:
                print(f"{period}: {_format_optional_number(value)}")
            print("yearly_returns:")
            for period, value in result.yearly_returns.items():
                print(f"{period}: {_format_optional_number(value)}")
            for warning in result.warnings:
                print(f"warning: {warning['code']}: {warning['reason']}", file=sys.stderr)
            print(f"report: {result.report_path}")
            return 0

        if args.command == "cost":
            targets = _load_targets(Path(args.targets))
            plan = rebalance_engine.plan(targets)
            cost_config = _load_cost_config(Path(args.config))
            _apply_cost_overrides(cost_config, args)
            cost_report = CostEngine(cost_config).estimate(_trades_from_rebalance_plan(plan))
            _print_cost_report(cost_report)
            return 0

        if args.command == "factor-eval":
            result = factor_evaluation.evaluate(
                factor=args.factor,
                start=args.start,
                end=args.end,
                forward_days=args.forward_days,
                pipeline_config=_load_factor_pipeline_config(Path(args.pipeline)) if args.pipeline else None,
            )
            print("Factor Evaluation Summary")
            print(f"factor: {result.factor}")
            print(f"period: {result.start_date or 'earliest'} to {result.end_date or 'latest'}")
            print(f"forward_days: {result.forward_days}")
            print(f"no_lookahead: {str(result.no_lookahead).lower()}")
            print(f"observations: {len(result.observations)}")
            print(f"ic_mean: {_format_optional_number(result.ic_mean)}")
            print(f"ic_std: {_format_optional_number(result.ic_std)}")
            print(f"ic_positive_rate: {_format_optional_pct(result.ic_positive_rate)}")
            print(f"ic_count: {result.ic_count}")
            print(f"rank_ic_mean: {_format_optional_number(result.rank_ic_mean)}")
            print(f"rank_ic_std: {_format_optional_number(result.rank_ic_std)}")
            print(f"rank_ic_positive_rate: {_format_optional_pct(result.rank_ic_positive_rate)}")
            print(f"icir: {_format_optional_number(result.icir)}")
            print("quintiles:")
            for quintile in ["q1", "q2", "q3", "q4", "q5"]:
                print(f"{quintile}: {_format_optional_number(result.quintiles.get(quintile))}")
            print(f"spread_return: {_format_optional_number(result.spread_return)}")
            print("decay:")
            for horizon, metrics in result.decay.items():
                print(
                    f"{horizon}: ic={_format_optional_number(metrics['ic'])} "
                    f"rank_ic={_format_optional_number(metrics['rank_ic'])} "
                    f"ic_count={metrics['ic_count']}"
                )
            if result.excluded_symbols:
                print("excluded_symbols:")
                for symbol in result.excluded_symbols:
                    print(f"{symbol}: {result.exclusion_reasons[symbol]}")
            for warning in result.warnings:
                print(f"warning: {warning}", file=sys.stderr)
            print(f"report: {result.report_path}")
            return 0

        if args.command == "execute-sim":
            targets = _load_targets(Path(args.targets))
            cost_config = _load_cost_config(Path(args.cost_config))
            result = execution_engine.run(
                targets=targets,
                mode=args.mode,
                execution_date=args.date,
                cost_config=cost_config,
                twap_slices=args.twap_slices,
                fill_ratio=args.fill_ratio,
            )
            print("Execution Simulation Summary")
            print(f"mode: {result.mode}")
            print(f"intended_trades: {len(result.intended_trades)}")
            print(f"executed_trades: {len(result.executed_trades)}")
            print(f"unfilled_trades: {len(result.unfilled_trades)}")
            print(f"total_cost: {result.execution_costs['total_cost']:.2f}")
            print(f"slippage_estimate: {result.slippage_estimate:.2f}")
            print(f"final_cash: {result.final_cash:.2f}")
            print("executed:")
            for trade in result.executed_trades:
                print(
                    f"{trade.side:<4} {trade.symbol:<6} shares={trade.shares} "
                    f"price={trade.price:.2f} notional={trade.notional:.2f} "
                    f"cost={trade.total_cost:.2f} batch={trade.batch}"
                )
            if result.unfilled_trades:
                print("unfilled:")
                for trade in result.unfilled_trades:
                    print(
                        f"{trade.side:<4} {trade.symbol:<6} shares={trade.shares} "
                        f"price={trade.price:.2f} reason={trade.reason}"
                    )
            print("final_positions:")
            for symbol, qty in result.final_positions.items():
                print(f"{symbol:<6} {qty:.6g}")
            for warning in result.warnings:
                print(f"warning: {warning}", file=sys.stderr)
            print(f"report: {result.report_path}")
            return 0

        if args.command == "backtest":
            initial_cash = args.initial_cash if args.initial_cash is not None else args.cash
            if args.symbol is None:
                alpha_config = _load_alpha_config(Path(args.alpha_config)) if args.strategy == "alpha" else None
                result = portfolio_backtest_engine.run(
                    start=args.start,
                    end=args.end,
                    initial_cash=initial_cash,
                    mode=args.mode,
                    rebalance_frequency=args.rebalance_frequency,
                    strategy=args.strategy,
                    execution_price=args.execution_price,
                    alpha_config=alpha_config,
                    alpha_pipeline_config=None,
                )
                metrics = result.metrics
                print("Portfolio Backtest Summary")
                print(f"period: {result.start} to {result.end}")
                print(f"strategy: {result.strategy}")
                print(f"mode: {result.mode}")
                print(f"rebalance_frequency: {result.rebalance_frequency}")
                print(f"no_lookahead: {str(result.no_lookahead).lower()}")
                print(f"signal_execution_lag: {result.signal_execution_lag}")
                print(f"initial_cash: {result.initial_cash:.2f}")
                print(f"final_value: {metrics.final_value:.2f}")
                print(f"total_return: {metrics.total_return:.4f}")
                print(f"annual_return: {metrics.annual_return:.4f}")
                print(f"max_drawdown: {metrics.max_drawdown:.4f}")
                print(f"volatility: {metrics.volatility:.4f}")
                print(f"sharpe_ratio: {metrics.sharpe_ratio:.4f}")
                print(f"trade_count: {metrics.trade_count}")
                print(f"turnover: {metrics.turnover:.4f}")
                print(f"total_cost: {metrics.total_cost:.2f}")
                print(f"cash_ratio: {metrics.cash_ratio:.4f}")
                print(f"report: {result.report_path}")
                return 0

            result = backtest_service.run_sma_crossover(
                symbol=args.symbol,
                start=args.start,
                end=args.end,
                initial_cash=initial_cash,
                short_window=args.short_window,
                long_window=args.long_window,
                commission=args.commission,
            )
            metrics = result.metrics
            print("Backtest Summary")
            print(f"symbol: {metrics.symbol}")
            print(f"period: {metrics.start} to {metrics.end}")
            print(f"initial_cash: {metrics.initial_cash:.2f}")
            print(f"final_value: {metrics.final_value:.2f}")
            print(f"total_return_pct: {metrics.total_return_pct:.2f}")
            print(f"max_drawdown_pct: {metrics.max_drawdown_pct:.2f}")
            print(f"sharpe_ratio: {metrics.sharpe_ratio:.4f}")
            print(f"number_of_trades: {metrics.number_of_trades}")
            print(f"win_rate_pct: {metrics.win_rate_pct:.2f}")
            print(f"report: {result.report_path}")
            return 0
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    raise ValueError(f"Unknown command: {args.command}")


def _strategy_eval_source_report(
    args,
    price_store: SQLitePriceStore,
    factor_backtest_engine: FactorBacktest,
    portfolio_backtest_engine: PortfolioBacktestEngine,
) -> str:
    explicit_report = args.factor_backtest_report or args.backtest_report or args.report
    if explicit_report:
        return str(explicit_report)

    if args.strategy == "factor_long_short":
        result = factor_backtest_engine.run(
            factor=args.factor,
            pipeline_config=_load_factor_pipeline_config(Path(args.pipeline)) if args.pipeline else None,
            pipeline_config_path=args.pipeline,
        )
        return result.report_path

    if args.strategy == "alpha":
        alpha_config = _load_alpha_config(Path("examples/alpha_config.json"))
        result = portfolio_backtest_engine.run(
            start="2024-01-01",
            end="2025-01-01",
            initial_cash=100000.0,
            mode="equal_weight",
            rebalance_frequency="monthly",
            strategy="alpha",
            execution_price="close",
            alpha_config=alpha_config,
            alpha_pipeline_config=_load_factor_pipeline_config(Path(args.pipeline)) if args.pipeline else None,
        )
        return result.report_path

    raise ValueError(
        "strategy-eval requires --report, --backtest-report, --factor-backtest-report, "
        "or --strategy alpha/factor_long_short"
    )


def _benchmark_returns_for_report(
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

    start, end = _report_date_window(report)
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


def _report_date_window(report: dict) -> tuple[str | None, str | None]:
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


def _format_optional_money(value: float | None) -> str:
    return "N/A" if value is None else f"{value:.2f}"


def _format_optional_number(value: float | None) -> str:
    return "N/A" if value is None else f"{value:.6f}"


def _format_optional_pct(value: float | None) -> str:
    return "N/A" if value is None else f"{value * 100:.2f}%"


def _format_optional_rank(value: int | None) -> str:
    return "N/A" if value is None else str(value)


def _trades_from_rebalance_plan(plan) -> list[TradeInput]:
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


def _print_cost_report(report) -> None:
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


def _load_targets(path: Path) -> dict:
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


def _load_cost_config(path: Path) -> dict:
    if not path.exists():
        return {}

    try:
        with path.open("r", encoding="utf-8") as file:
            config = json.load(file)
    except json.JSONDecodeError as exc:
        raise ValueError(f"cost config is not valid JSON: {path}") from exc

    if not isinstance(config, dict):
        raise ValueError("cost config must contain a JSON object")
    return config


def _apply_cost_overrides(config: dict, args) -> None:
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


def _load_optimizer_config(path: Path) -> dict:
    if not path.exists():
        return {}

    try:
        with path.open("r", encoding="utf-8") as file:
            config = json.load(file)
    except json.JSONDecodeError as exc:
        raise ValueError(f"optimizer config is not valid JSON: {path}") from exc

    if not isinstance(config, dict):
        raise ValueError("optimizer config must contain a JSON object")
    return config


def _load_alpha_config(path: Path) -> dict:
    if not path.exists():
        return {}

    try:
        with path.open("r", encoding="utf-8") as file:
            config = json.load(file)
    except json.JSONDecodeError as exc:
        raise ValueError(f"alpha config is not valid JSON: {path}") from exc

    if not isinstance(config, dict):
        raise ValueError("alpha config must contain a JSON object")
    return config


def _load_factor_pipeline_config(path: Path) -> dict:
    try:
        with path.open("r", encoding="utf-8") as file:
            config = json.load(file)
    except FileNotFoundError as exc:
        raise ValueError(f"factor pipeline config file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"factor pipeline config is not valid JSON: {path}") from exc

    if not isinstance(config, dict):
        raise ValueError("factor pipeline config must contain a JSON object")
    return config


def _factor_values_for_pipeline(
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


if __name__ == "__main__":
    raise SystemExit(main())
