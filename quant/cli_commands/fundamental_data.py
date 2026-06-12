"""Fundamental data CLI commands."""

from __future__ import annotations

from pathlib import Path


def register_parser(subparsers) -> None:
    importer = subparsers.add_parser("fundamental-import", help="Import fundamental data from CSV.")
    importer.add_argument("--file", required=True, help="CSV file path.")
    importer.add_argument("--statement", choices=["income", "income_statement", "balance", "balance_sheet", "cash-flow", "cash_flow", "metrics", "fundamental_metrics"], default=None)
    importer.add_argument("--force", action="store_true", help="Allow older report_date rows to overwrite existing rows.")

    show = subparsers.add_parser("fundamental-show", help="Show stored fundamental rows for a symbol.")
    show.add_argument("--symbol", required=True)
    show.add_argument("--latest", action="store_true")
    show.add_argument("--statement", choices=["income", "income_statement", "balance", "balance_sheet", "cash-flow", "cash_flow", "metrics", "fundamental_metrics"], default=None)
    show.add_argument("--limit", type=int, default=10)

    coverage = subparsers.add_parser("fundamental-coverage", help="Report fundamental coverage.")
    coverage.add_argument("--symbols", default=None, help="Comma or space separated symbols.")
    coverage.add_argument("--universe", default="default")
    coverage.add_argument("--sector", default=None)
    coverage.add_argument("--max-symbols", type=int, default=None)

    quality = subparsers.add_parser("fundamental-quality", help="Run fundamental data quality checks.")
    quality.add_argument("--symbol", default=None)
    quality.add_argument("--symbols", default=None, help="Comma or space separated symbols.")
    quality.add_argument("--universe", default="default")
    quality.add_argument("--sector", default=None)
    quality.add_argument("--max-symbols", type=int, default=None)


def handle(args, context) -> int:
    if args.command == "fundamental-import":
        result = context.fundamental_service.import_csv(Path(args.file), statement=args.statement, force=args.force)
        summary = result["summary"]
        print("Fundamental Import Summary")
        print(f"inserted: {summary['inserted']}")
        print(f"updated: {summary['updated']}")
        print(f"skipped: {summary['skipped']}")
        print(f"errors: {summary['errors']}")
        for warning in result["warnings"]:
            print(f"warning: {warning}")
        print(f"report: {result['report_path']}")
        return 0

    if args.command == "fundamental-show":
        rows = context.fundamental_service.show(args.symbol, statement=args.statement, latest=args.latest, limit=args.limit)
        if not rows:
            print(f"No fundamental data found for {args.symbol.upper()}.")
            return 0
        print("Fundamental Rows")
        for row in rows:
            print(
                f"{row['statement_type']} {row['symbol']} "
                f"fiscal_period_end={row['fiscal_period_end']} report_date={row.get('report_date')} "
                f"fiscal_year={row.get('fiscal_year')} fiscal_quarter={row.get('fiscal_quarter')} currency={row.get('currency')}"
            )
        return 0

    if args.command == "fundamental-coverage":
        symbols = _symbols_for_fundamental_command(args, context)
        result = context.fundamental_service.coverage(symbols, parameters=_parameters(args, symbols))
        coverage = result["coverage"]
        print("Fundamental Coverage Summary")
        print(f"total_symbols: {coverage['total_symbols']}")
        print(f"symbols_with_any_fundamental_data: {coverage['symbols_with_any_fundamental_data']}")
        print(f"symbols_missing_fundamental_data: {coverage['symbols_missing_fundamental_data']}")
        print(f"readiness_score: {coverage['readiness_score']}")
        print(f"latest_report_date: {coverage['latest_report_date']}")
        print("statement_coverage:")
        for statement, count in coverage["statement_coverage"].items():
            print(f"- {statement}: {count}")
        print(f"report: {result['report_path']}")
        return 0

    if args.command == "fundamental-quality":
        symbols = _symbols_for_fundamental_command(args, context)
        result = context.fundamental_service.quality(symbols, parameters=_parameters(args, symbols))
        print("Fundamental Quality Summary")
        print(f"status: {result['summary']['status']}")
        print(f"symbols_checked: {result['summary']['symbols_checked']}")
        print(f"warnings: {result['summary']['warnings']}")
        for warning in result["warnings"][:20]:
            print(f"- {warning}")
        print(f"report: {result['report_path']}")
        return 0

    raise ValueError(f"Unknown fundamental command: {args.command}")


def _symbols_for_fundamental_command(args, context) -> list[str]:
    if getattr(args, "symbol", None):
        return [args.symbol.upper().strip()]
    if getattr(args, "symbols", None):
        return [symbol.upper().strip() for symbol in args.symbols.replace(",", " ").split() if symbol.strip()]
    result = context.universe_manager.build_universe(
        universe=getattr(args, "universe", None) or "default_universe",
        sector=getattr(args, "sector", None),
        max_symbols=getattr(args, "max_symbols", None),
    )
    return result.selected_symbols


def _parameters(args, symbols: list[str]) -> dict:
    return {
        "symbols": symbols,
        "universe": getattr(args, "universe", None),
        "sector": getattr(args, "sector", None),
        "max_symbols": getattr(args, "max_symbols", None),
    }
