"""Walk-forward validation CLI command."""

from __future__ import annotations

from pathlib import Path

from quant.cli_commands.common import (
    format_optional_number,
    load_alpha_config,
    load_factor_pipeline_config,
)
from quant.factor_eval.factor_evaluation import SUPPORTED_FACTORS


def register_parser(subparsers) -> None:
    walk_forward = subparsers.add_parser("walk-forward", help="Run walk-forward or rolling validation.")
    walk_forward.add_argument("--strategy", choices=["alpha", "factor_long_short"], default="alpha")
    walk_forward.add_argument("--factor", choices=sorted(SUPPORTED_FACTORS), default="momentum_20d")
    walk_forward.add_argument("--train-years", type=float, default=3.0)
    walk_forward.add_argument("--test-years", type=float, default=1.0)
    walk_forward.add_argument("--start", default=None)
    walk_forward.add_argument("--end", default=None)
    walk_forward.add_argument("--symbols", nargs="+", default=None, help="Optional validation universe symbols.")
    walk_forward.add_argument("--initial-cash", type=float, default=100000.0)
    walk_forward.add_argument("--rebalance-frequency", choices=["monthly", "weekly", "daily"], default="monthly")
    walk_forward.add_argument("--alpha-config", default="examples/alpha_config.json")
    walk_forward.add_argument("--pipeline", default=None, help="Optional factor pipeline config JSON.")
    walk_forward.add_argument("--max-folds", type=int, default=5, help="Limit folds for CLI runtime; use 0 for all folds.")
    walk_forward.add_argument("--save-factor-history", action="store_true", help="Persist walk-forward factor history.")


def handle(args, context) -> int:
    result = context.walk_forward_engine.run(
        strategy=args.strategy,
        factor=args.factor,
        train_years=args.train_years,
        test_years=args.test_years,
        start=args.start,
        end=args.end,
        universe=args.symbols,
        initial_cash=args.initial_cash,
        rebalance_frequency=args.rebalance_frequency,
        alpha_config=load_alpha_config(Path(args.alpha_config)) if args.strategy == "alpha" else None,
        pipeline_config=load_factor_pipeline_config(Path(args.pipeline)) if args.pipeline else None,
        max_folds=None if args.max_folds == 0 else args.max_folds,
    )
    print("Walk Forward Summary")
    print(f"strategy: {result.strategy}")
    print(f"fold_count: {result.summary['fold_count']}")
    print(f"average_train_return: {format_optional_number(result.summary.get('average_train_return'))}")
    print(f"average_test_return: {format_optional_number(result.summary.get('average_test_return'))}")
    print(f"average_train_sharpe: {format_optional_number(result.summary.get('average_train_sharpe'))}")
    print(f"average_test_sharpe: {format_optional_number(result.summary.get('average_test_sharpe'))}")
    print(f"average_ic: {format_optional_number(result.summary.get('average_ic'))}")
    print(f"average_rank_ic: {format_optional_number(result.summary.get('average_rank_ic'))}")
    print(f"average_icir: {format_optional_number(result.summary.get('average_icir'))}")
    print("folds:")
    for fold in result.folds:
        print(
            f"{fold.fold_id}: train={fold.train_start}..{fold.train_end} "
            f"test={fold.test_start}..{fold.test_end} "
            f"train_return={format_optional_number(fold.train_return)} "
            f"test_return={format_optional_number(fold.test_return)} "
            f"test_sharpe={format_optional_number(fold.test_sharpe)} "
            f"ic={format_optional_number(fold.ic)}"
        )
        for warning in fold.fold_warnings:
            print(f"  {warning['code']}: {warning['reason']}")
    print("warnings:")
    for warning in result.warnings:
        print(f"{warning['code']}: {warning['reason']}")
    print("factor_stability_ranking:")
    for row in result.stability_analysis.get("factor_stability_ranking", [])[:5]:
        print(
            f"{row['factor']}: {row['classification']} "
            f"score={format_optional_number(row.get('score'))} "
            f"avg_ic={format_optional_number(row.get('average_ic'))}"
        )
    print("recommendations:")
    for recommendation in result.recommendations:
        print(f"- {recommendation}")
    if args.save_factor_history:
        context.factor_registry_store.sync()
        saved = context.factor_store.save_walk_forward(
            result,
            factor=args.factor if args.strategy == "factor_long_short" else "alpha",
        )
        print("saved_factor_history:")
        print(f"walk_forward_folds: {saved['saved_walk_forward_folds']}")
    print(f"report: {result.report_path}")
    return 0
