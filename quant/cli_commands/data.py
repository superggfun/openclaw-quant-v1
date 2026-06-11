"""Price data CLI commands."""

from __future__ import annotations

from quant.config import DEFAULT_SYMBOLS


def register_parser(subparsers) -> None:
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


def handle(args, context) -> int:
    if args.command == "update-prices":
        results = context.price_service.update_prices(args.symbols, start=args.start, end=args.end)
        for symbol, changed in results.items():
            print(f"{symbol}: {changed} rows inserted/updated")
        return 0

    if args.command == "show-prices":
        rows = context.price_service.show_prices(args.symbol, limit=args.limit)
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
        for symbol in context.price_service.list_symbols():
            print(symbol)
        return 0

    raise ValueError(f"Unknown data command: {args.command}")

