"""Command line interface for OpenClaw Quant."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from quant.config import DB_PATH, DEFAULT_SYMBOLS
from quant.rebalance.rebalance_engine import DEFAULT_COMMISSION_RATE, RebalanceEngine
from quant.risk.risk_engine import RiskEngine
from quant.services.backtest_service import BacktestService
from quant.services.portfolio_service import PortfolioService
from quant.services.price_service import PriceService
from quant.storage.portfolio_store import SQLitePortfolioStore
from quant.storage.sqlite_store import SQLitePriceStore


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

    subparsers.add_parser("risk", help="Calculate portfolio risk metrics.")

    backtest = subparsers.add_parser("backtest", help="Run an SMA crossover backtest.")
    backtest.add_argument("--symbol", required=True)
    backtest.add_argument("--start", required=True, help="Inclusive start date YYYY-MM-DD.")
    backtest.add_argument("--end", required=True, help="Inclusive end date YYYY-MM-DD.")
    backtest.add_argument("--cash", type=float, default=100000.0)
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
    rebalance_engine = RebalanceEngine(portfolio_store)
    risk_engine = RiskEngine(portfolio_store)

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

        if args.command == "backtest":
            result = backtest_service.run_sma_crossover(
                symbol=args.symbol,
                start=args.start,
                end=args.end,
                initial_cash=args.cash,
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


def _format_optional_money(value: float | None) -> str:
    return "N/A" if value is None else f"{value:.2f}"


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


if __name__ == "__main__":
    raise SystemExit(main())
