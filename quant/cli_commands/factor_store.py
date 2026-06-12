"""Factor store CLI commands."""

from __future__ import annotations

from quant.cli_commands.common import format_optional_number, format_optional_pct


def register_parser(subparsers) -> None:
    summary = subparsers.add_parser("factor-store-summary", help="Show persistent factor store summary.")
    summary.add_argument("--sync-definitions", action="store_true", help="Sync current factor registry before summarizing.")

    history = subparsers.add_parser("factor-history", help="Show persisted factor history.")
    history.add_argument("--factor", default=None)
    history.add_argument("--limit", type=int, default=20)

    rank = subparsers.add_parser("factor-rank", help="Rank persisted factors by health, stability, and coverage.")
    rank.add_argument("--limit", type=int, default=10)


def handle(args, context) -> int:
    if args.command == "factor-store-summary":
        if args.sync_definitions:
            synced = context.factor_registry_store.sync()
            print(f"synced_factor_definitions: {synced}")
        result = context.factor_store.summary()
        print("Factor Store Summary")
        for table, count in result["counts"].items():
            print(f"{table}: {count}")
        print(f"factor_count: {len(result['factors'])}")
        print(f"report: {result['report_path']}")
        return 0

    if args.command == "factor-history":
        result = context.factor_store.factor_history(factor=args.factor, limit=args.limit)
        print("Factor History")
        print(f"factor: {args.factor or 'all'}")
        print(f"evaluation_rows: {len(result['evaluation_history'])}")
        print(f"backtest_rows: {len(result['backtest_history'])}")
        print(f"walk_forward_rows: {len(result['walk_forward_history'])}")
        print(f"stability_rows: {len(result['stability_history'])}")
        if result["evaluation_history"]:
            latest = result["evaluation_history"][0]
            print(
                "latest_eval: "
                f"ic={format_optional_number(latest.get('ic'))} "
                f"rank_ic={format_optional_number(latest.get('rank_ic'))} "
                f"icir={format_optional_number(latest.get('icir'))} "
                f"coverage={format_optional_pct(latest.get('coverage'))}"
            )
        if result["backtest_history"]:
            latest = result["backtest_history"][0]
            print(
                "latest_backtest: "
                f"return={format_optional_number(latest.get('long_short_return'))} "
                f"sharpe={format_optional_number(latest.get('sharpe'))} "
                f"drawdown={format_optional_number(latest.get('drawdown'))}"
            )
        print(f"report: {result['report_path']}")
        return 0

    if args.command == "factor-rank":
        result = context.factor_store.rank_factors(limit=args.limit)
        print("Factor Rank")
        print("top_factors:")
        for row in result["top_factors"]:
            print(
                f"{row['factor_name']}: health={format_optional_number(row.get('health_score'))} "
                f"ic={format_optional_number(row.get('ic'))} "
                f"rank_ic={format_optional_number(row.get('rank_ic'))} "
                f"coverage={format_optional_pct(row.get('coverage'))}"
            )
        print("worst_factors:")
        for row in result["worst_factors"][:5]:
            print(f"{row['factor_name']}: health={format_optional_number(row.get('health_score'))}")
        print("most_stable_factors:")
        for row in result["most_stable_factors"][:5]:
            print(f"{row['factor_name']}: stability={format_optional_number(row.get('stability_score'))}")
        print(f"report: {result['report_path']}")
        return 0

    raise ValueError(f"unsupported factor store command: {args.command}")
