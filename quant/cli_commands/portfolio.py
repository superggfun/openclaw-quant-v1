"""Simulated portfolio state CLI commands."""

from __future__ import annotations

from quant.cli_commands.common import format_optional_money


def register_parser(subparsers) -> None:
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


def handle(args, context) -> int:
    portfolio_service = context.portfolio_service

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
                f"{format_optional_money(position.current_price):>10} "
                f"{format_optional_money(position.market_value):>12} "
                f"{format_optional_money(position.unrealized_pnl):>14}"
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

    raise ValueError(f"Unknown portfolio command: {args.command}")

