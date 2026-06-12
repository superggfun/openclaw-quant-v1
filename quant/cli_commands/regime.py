"""Regime detection CLI commands."""

from __future__ import annotations

from quant.cli_commands.common import format_optional_number, format_optional_pct


def register_parser(subparsers) -> None:
    detect = subparsers.add_parser("detect-regime", help="Detect and persist deterministic market regimes.")
    detect.add_argument("--benchmark", default="SPY")
    detect.add_argument("--start", default=None)
    detect.add_argument("--end", default=None)

    history = subparsers.add_parser("regime-history", help="Show persisted market regime history.")
    history.add_argument("--limit", type=int, default=30)
    history.add_argument("--regime", default=None)

    report = subparsers.add_parser("regime-report", help="Generate regime diagnostics report.")
    report.add_argument("--ensure-history", action="store_true", help="Detect regimes first if history is empty.")

    rank = subparsers.add_parser("regime-rank", help="Rank persisted factors by regime.")
    rank.add_argument("--limit", type=int, default=10)
    rank.add_argument("--ensure-history", action="store_true", help="Detect regimes first if history is empty.")


def handle(args, context) -> int:
    if args.command == "detect-regime":
        context.regime_detector.benchmark = args.benchmark.upper()
        report = context.regime_analytics.detect_and_save(start=args.start, end=args.end)
        current = report.get("current_regime") or {}
        print("Regime Detection Summary")
        print(f"benchmark: {report['benchmark']}")
        print(f"current_regime: {current.get('regime', 'UNKNOWN')}")
        print(f"date: {current.get('date', 'N/A')}")
        print(f"volatility: {format_optional_number(current.get('volatility'))}")
        print(f"trend_strength: {format_optional_number(current.get('trend_strength'))}")
        print(f"drawdown: {format_optional_number(current.get('drawdown'))}")
        print(f"confidence: {format_optional_pct(current.get('confidence'))}")
        print(f"saved_rows: {report['saved_rows']}")
        print(f"report: {report['report_path']}")
        return 0

    if args.command == "regime-history":
        report = context.regime_analytics.history_report(limit=args.limit, regime=args.regime)
        current = report.get("current_regime") or {}
        print("Regime History")
        print(f"current_regime: {current.get('regime', 'UNKNOWN')}")
        print(f"history_rows: {len(report['history'])}")
        print("regime_counts:")
        for regime, count in sorted((report.get("regime_counts") or {}).items()):
            print(f"{regime}: {count}")
        print(f"report: {report['report_path']}")
        return 0

    if args.command == "regime-report":
        _ensure_history(context, args.ensure_history)
        report = context.regime_analytics.regime_report()
        current = report.get("current_regime") or {}
        print("Regime Report")
        print(f"current_regime: {current.get('regime', 'UNKNOWN')}")
        print("regime_counts:")
        for regime, count in sorted((report.get("regime_counts") or {}).items()):
            print(f"{regime}: {count}")
        print(f"factor_regimes: {len(report.get('factor_performance_by_regime') or {})}")
        print(f"report: {report['report_path']}")
        return 0

    if args.command == "regime-rank":
        _ensure_history(context, args.ensure_history)
        report = context.regime_analytics.regime_rank(limit=args.limit)
        current = report.get("current_regime") or {}
        print("Regime Rank")
        print(f"current_regime: {current.get('regime', 'UNKNOWN')}")
        for regime, rows in sorted((report.get("best_by_regime") or {}).items()):
            if not rows:
                continue
            top = rows[0]
            print(
                f"best_{regime}: {top.get('factor_name')} "
                f"health={format_optional_number(top.get('health_score'))} "
                f"ic={format_optional_number(top.get('ic'))}"
            )
        if not report.get("best_by_regime"):
            print("best_by_regime: none")
        print(f"report: {report['report_path']}")
        return 0

    raise ValueError(f"unsupported regime command: {args.command}")


def _ensure_history(context, enabled: bool) -> None:
    if enabled and context.regime_history_store.latest() is None:
        context.regime_analytics.detect_and_save()
