"""Backtest CLI command."""

from __future__ import annotations

from pathlib import Path

from quant.cli_commands.common import load_alpha_config


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

