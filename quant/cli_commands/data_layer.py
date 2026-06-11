"""Data layer CLI commands."""

from __future__ import annotations

from quant.config import DEFAULT_SYMBOLS


def register_parser(subparsers) -> None:
    subparsers.add_parser("universe-list", help="List available research universes.")

    universe_build = subparsers.add_parser("universe-build", help="Build a research universe.")
    universe_build.add_argument("--symbols", default=None, help="Comma or space separated symbols.")
    universe_build.add_argument("--sector", default=None, help="Sector name for a sector universe.")
    universe_build.add_argument("--universe", default="default_universe", help="default_universe, etf_universe, large_cap_universe, or all.")
    universe_build.add_argument("--max-symbols", type=int, default=None)

    refresh = subparsers.add_parser("data-refresh", help="Refresh historical daily prices and report coverage.")
    refresh.add_argument("--symbols", default=None, help="Comma or space separated symbols.")
    refresh.add_argument("--universe", default=None, help="Universe to refresh. Defaults to configured symbols.")
    refresh.add_argument("--sector", default=None)
    refresh.add_argument("--max-symbols", type=int, default=None)
    refresh.add_argument("--start-date", default=None)
    refresh.add_argument("--end-date", default=None)

    coverage = subparsers.add_parser("data-coverage", help="Show stored price coverage.")
    coverage.add_argument("--symbols", default=None, help="Comma or space separated symbols.")
    coverage.add_argument("--universe", default="default_universe")
    coverage.add_argument("--sector", default=None)
    coverage.add_argument("--max-symbols", type=int, default=None)

    readiness = subparsers.add_parser("research-readiness", help="Score data readiness for factor research.")
    readiness.add_argument("--symbols", default=None, help="Comma or space separated symbols.")
    readiness.add_argument("--universe", default="default_universe")
    readiness.add_argument("--sector", default=None)
    readiness.add_argument("--max-symbols", type=int, default=None)


def handle(args, context) -> int:
    if args.command == "universe-list":
        universes = context.universe_manager.list_universes()
        print("Universes")
        for name, values in universes.items():
            print(f"{name}: {', '.join(values) if values else 'custom via --symbols'}")
        return 0

    if args.command == "universe-build":
        result = context.universe_manager.build_universe(
            symbols=args.symbols,
            sector=args.sector,
            universe=args.universe,
            max_symbols=args.max_symbols,
        )
        _print_universe_result(result)
        return 0

    if args.command == "data-refresh":
        symbols = _symbols_for_data_command(args, context, default_to_config=True)
        refresh = context.data_refresh_manager.refresh(symbols, start_date=args.start_date, end_date=args.end_date)
        print("Data Refresh Summary")
        for symbol, item in refresh.per_symbol.items():
            line = (
                f"{symbol}: inserted={item['inserted']} updated={item['updated']} "
                f"skipped={item['skipped']} fetched={item['fetched']} status={item['status']}"
            )
            if item["error"]:
                line += f" error={item['error']}"
            print(line)
        print(
            "summary: "
            f"inserted={refresh.summary['inserted']} updated={refresh.summary['updated']} "
            f"skipped={refresh.summary['skipped']} errors={refresh.summary['errors']}"
        )
        print(f"refresh_report: {refresh.report_path}")
        coverage = context.data_quality_analyzer.coverage(refresh.symbols)
        _print_coverage(coverage)
        return 0

    if args.command == "data-coverage":
        symbols = _symbols_for_data_command(args, context)
        coverage = context.data_quality_analyzer.coverage(symbols)
        _print_coverage(coverage)
        return 0

    if args.command == "research-readiness":
        symbols = _symbols_for_data_command(args, context)
        readiness = context.data_quality_analyzer.readiness(symbols)
        print("Research Readiness Summary")
        print(f"readiness_score: {readiness['readiness_score']}")
        print(f"universe_size: {readiness['universe_size']}")
        print(f"history_depth_average: {readiness['history_depth_average']}")
        print(f"sector_count: {readiness['sector_count']}")
        print(f"factor_coverage_symbols: {readiness['factor_coverage_symbols']}")
        print(f"data_quality_status: {readiness['data_quality_status']}")
        print("recommendations:")
        for recommendation in readiness["recommendations"]:
            print(f"- {recommendation}")
        print(f"report: {readiness['report_path']}")
        return 0

    raise ValueError(f"Unknown data layer command: {args.command}")


def _symbols_for_data_command(args, context, default_to_config: bool = False) -> list[str]:
    if default_to_config and not args.symbols and not args.universe and not args.sector:
        return list(DEFAULT_SYMBOLS)
    result = context.universe_manager.build_universe(
        symbols=args.symbols,
        sector=args.sector,
        universe=getattr(args, "universe", None) or "default_universe",
        max_symbols=args.max_symbols,
    )
    return result.selected_symbols


def _print_universe_result(result) -> None:
    print("Universe Build Summary")
    print(f"universe_type: {result.universe_type}")
    print("selected_symbols:")
    for symbol in result.selected_symbols:
        print(symbol)
    print("excluded_symbols:")
    for symbol in result.excluded_symbols:
        print(f"{symbol}: {result.exclusion_reasons[symbol]}")


def _print_coverage(coverage: dict) -> None:
    print("Data Coverage Summary")
    print(f"total_symbols: {coverage['total_symbols']}")
    print(f"symbols_with_price_data: {coverage['symbols_with_price_data']}")
    print(f"symbols_without_price_data: {coverage['symbols_without_price_data']}")
    print(f"average_history_length: {coverage['average_history_length']}")
    print(f"oldest_date: {coverage['oldest_date']}")
    print(f"newest_date: {coverage['newest_date']}")
    print(f"report: {coverage['report_path']}")
