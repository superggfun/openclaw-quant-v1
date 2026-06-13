"""Strategy evaluation CLI command."""

from __future__ import annotations

import sys
from pathlib import Path

from quant.cli_commands.common import (
    benchmark_returns_for_report,
    format_optional_number,
    load_alpha_config,
    load_factor_pipeline_config,
)
from quant.engines.factor_eval.factor_evaluation import SUPPORTED_FACTORS


def register_parser(subparsers) -> None:
    strategy_eval = subparsers.add_parser("strategy-eval", help="Evaluate and attribute a generated strategy report.")
    strategy_eval.add_argument("--report", default=None, help="Legacy alias for a source report JSON.")
    strategy_eval.add_argument("--backtest-report", default=None, help="Path to a portfolio backtest JSON report.")
    strategy_eval.add_argument("--factor-backtest-report", default=None, help="Path to a factor backtest JSON report.")
    strategy_eval.add_argument("--strategy", choices=["alpha", "factor_long_short"], default=None)
    strategy_eval.add_argument("--factor", choices=sorted(SUPPORTED_FACTORS), default="momentum_20d")
    strategy_eval.add_argument("--pipeline", default=None, help="Optional factor pipeline config JSON.")
    strategy_eval.add_argument("--benchmark", default=None, help="Optional benchmark symbol, for example SPY.")
    strategy_eval.add_argument("--output", default=None, help="Optional strategy evaluation report output path.")


def handle(args, context) -> int:
    source_report = _strategy_eval_source_report(args, context)
    benchmark_returns = (
        benchmark_returns_for_report(context.price_store, args.benchmark, Path(source_report))
        if args.benchmark
        else None
    )
    result = context.strategy_evaluation.evaluate(
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
        print(f"{key}: {format_optional_number(result.summary_metrics.get(key))}")
    if result.benchmark_metrics:
        print("benchmark_metrics:")
        for key in ["benchmark", "benchmark_return", "excess_return", "information_ratio"]:
            value = result.benchmark_metrics.get(key)
            print(f"{key}: {value if isinstance(value, str) else format_optional_number(value)}")
    print("return_attribution:")
    for key in ["long_leg_return", "short_leg_return", "long_short_return", "cash_drag", "cost_drag"]:
        print(f"{key}: {format_optional_number(result.return_attribution.get(key))}")
    print("risk_attribution:")
    for key in ["gross_exposure", "net_exposure", "average_cash", "average_turnover"]:
        print(f"{key}: {format_optional_number(result.risk_attribution.get(key))}")
    concentration = result.risk_attribution.get("concentration", {})
    if concentration:
        print(f"largest_position: {concentration.get('largest_position')}")
        print(f"top_3_weight: {format_optional_number(concentration.get('top_3_weight'))}")
        print(f"top_5_weight: {format_optional_number(concentration.get('top_5_weight'))}")
    print("drawdown:")
    print(f"max_drawdown: {format_optional_number(result.drawdown.get('max_drawdown'))}")
    print(f"drawdown_start: {result.drawdown.get('drawdown_start')}")
    print(f"drawdown_end: {result.drawdown.get('drawdown_end')}")
    print(f"drawdown_duration: {result.drawdown.get('drawdown_duration')}")
    print("top_contributors:")
    for row in result.attribution.get("top_positive_contributors", [])[:3]:
        print(f"{row['symbol']}: {format_optional_number(row['contribution'])}")
    print("top_detractors:")
    for row in result.attribution.get("top_negative_contributors", [])[:3]:
        print(f"{row['symbol']}: {format_optional_number(row['contribution'])}")
    concentration = result.attribution.get("return_concentration", {})
    if concentration:
        print("return_concentration:")
        print(f"top_1_pct: {format_optional_number(concentration.get('top_1_pct'))}")
        print(f"top_3_pct: {format_optional_number(concentration.get('top_3_pct'))}")
    print("monthly_returns:")
    for period, value in list(result.monthly_returns.items())[:6]:
        print(f"{period}: {format_optional_number(value)}")
    print("yearly_returns:")
    for period, value in result.yearly_returns.items():
        print(f"{period}: {format_optional_number(value)}")
    for warning in result.warnings:
        print(f"warning: {warning['code']}: {warning['reason']}", file=sys.stderr)
    print(f"report: {result.report_path}")
    return 0


def _strategy_eval_source_report(args, context) -> str:
    explicit_report = args.factor_backtest_report or args.backtest_report or args.report
    if explicit_report:
        return str(explicit_report)

    if args.strategy == "factor_long_short":
        result = context.factor_backtest_engine.run(
            factor=args.factor,
            pipeline_config=load_factor_pipeline_config(Path(args.pipeline)) if args.pipeline else None,
            pipeline_config_path=args.pipeline,
        )
        return result.report_path

    if args.strategy == "alpha":
        alpha_config = load_alpha_config(Path("examples/alpha_config.json"))
        result = context.portfolio_backtest_engine.run(
            start="2024-01-01",
            end="2025-01-01",
            initial_cash=100000.0,
            mode="equal_weight",
            rebalance_frequency="monthly",
            strategy="alpha",
            execution_price="close",
            alpha_config=alpha_config,
            alpha_pipeline_config=load_factor_pipeline_config(Path(args.pipeline)) if args.pipeline else None,
        )
        return result.report_path

    raise ValueError(
        "strategy-eval requires --report, --backtest-report, --factor-backtest-report, "
        "or --strategy alpha/factor_long_short"
    )

