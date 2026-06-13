"""Backtest CLI command."""

from __future__ import annotations

import logging
from pathlib import Path

from quant.cli_commands.common import load_alpha_config

logger = logging.getLogger(__name__)


def register_parser(subparsers) -> None:
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


def handle(args, context) -> int:
    initial_cash = args.initial_cash if args.initial_cash is not None else args.cash
    if args.symbol is None:
        alpha_config = load_alpha_config(Path(args.alpha_config)) if args.strategy == "alpha" else None
        result = context.portfolio_backtest_engine.run(
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
        logger.info("Portfolio Backtest Summary")
        logger.info("period: %s to %s", result.start, result.end)
        logger.info("strategy: %s", result.strategy)
        logger.info("mode: %s", result.mode)
        logger.info("rebalance_frequency: %s", result.rebalance_frequency)
        logger.info("no_lookahead: %s", str(result.no_lookahead).lower())
        logger.info("signal_execution_lag: %s", result.signal_execution_lag)
        logger.info("initial_cash: %.2f", result.initial_cash)
        logger.info("final_value: %.2f", metrics.final_value)
        logger.info("total_return: %.4f", metrics.total_return)
        logger.info("annual_return: %.4f", metrics.annual_return)
        logger.info("max_drawdown: %.4f", metrics.max_drawdown)
        logger.info("volatility: %.4f", metrics.volatility)
        logger.info("sharpe_ratio: %.4f", metrics.sharpe_ratio)
        logger.info("trade_count: %s", metrics.trade_count)
        logger.info("turnover: %.4f", metrics.turnover)
        logger.info("total_cost: %.2f", metrics.total_cost)
        logger.info("cash_ratio: %.4f", metrics.cash_ratio)
        logger.info("report: %s", result.report_path)
        return 0

    result = context.backtest_service.run_sma_crossover(
        symbol=args.symbol,
        start=args.start,
        end=args.end,
        initial_cash=initial_cash,
        short_window=args.short_window,
        long_window=args.long_window,
        commission=args.commission,
    )
    metrics = result.metrics
    logger.info("Backtest Summary")
    logger.info("symbol: %s", metrics.symbol)
    logger.info("period: %s to %s", metrics.start, metrics.end)
    logger.info("initial_cash: %.2f", metrics.initial_cash)
    logger.info("final_value: %.2f", metrics.final_value)
    logger.info("total_return_pct: %.2f", metrics.total_return_pct)
    logger.info("max_drawdown_pct: %.2f", metrics.max_drawdown_pct)
    logger.info("sharpe_ratio: %.4f", metrics.sharpe_ratio)
    logger.info("number_of_trades: %s", metrics.number_of_trades)
    logger.info("win_rate_pct: %.2f", metrics.win_rate_pct)
    logger.info("report: %s", result.report_path)
    return 0

