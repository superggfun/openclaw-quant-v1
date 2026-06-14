"""CLI command for Alpha Stability Audit."""

from __future__ import annotations

import argparse

from quant.cli_commands.common import CLIContext, format_optional_number
from quant.engines.alpha_stability import AlphaStabilityAudit
from quant.engines.factor_eval.factor_evaluation import SUPPORTED_FACTORS


def register_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(
        "stability",
        help="Run alpha stability audit for factors.",
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--factor", type=str, help="Single factor to audit.")
    group.add_argument("--all", action="store_true", dest="all_factors", help="Audit all supported factors.")
    parser.add_argument("--start", default=None, help="Start date (YYYY-MM-DD).")
    parser.add_argument("--end", default=None, help="End date (YYYY-MM-DD).")
    parser.add_argument(
        "--universe-sizes",
        type=str,
        default=None,
        help="Comma-separated universe sizes (e.g. 20,50,100,200).",
    )
    parser.add_argument(
        "--cost-levels",
        type=str,
        default=None,
        help="Comma-separated cost levels in bps (e.g. 0,5,10,20,50).",
    )
    parser.add_argument("--output", default=None, help="Report output directory.")
    parser.add_argument("--holding-period", type=int, default=20)
    parser.add_argument("--quantiles", type=int, default=5)


def handle(args: argparse.Namespace, context: CLIContext) -> int:
    report_dir = args.output or "reports"
    audit = AlphaStabilityAudit(
        context.price_store,
        context.fundamental_store,
        report_dir=report_dir,
    )

    universe_sizes = None
    if args.universe_sizes:
        universe_sizes = [int(s.strip()) for s in args.universe_sizes.split(",")]

    cost_levels = None
    if args.cost_levels:
        cost_levels = [int(s.strip()) for s in args.cost_levels.split(",")]

    if args.all_factors:
        results = audit.run_all(
            start=args.start,
            end=args.end,
            holding_period=args.holding_period,
            quantiles=args.quantiles,
            universe_sizes=universe_sizes,
            cost_levels_bps=cost_levels,
        )
    else:
        factor = args.factor.strip().lower()
        if factor not in SUPPORTED_FACTORS:
            print(f"Error: unknown factor '{factor}'. Supported: {', '.join(sorted(SUPPORTED_FACTORS))}")
            return 1
        single = audit.run(
            factor,
            start=args.start,
            end=args.end,
            holding_period=args.holding_period,
            quantiles=args.quantiles,
            universe_sizes=universe_sizes,
            cost_levels_bps=cost_levels,
        )
        results = [single]

    print("Alpha Stability Audit")
    print(f"factors_audited: {len(results)}")
    for r in results:
        print(f"\nfactor: {r.factor}")
        print(f"  composite_score: {format_optional_number(r.composite_score)}")
        print(f"  status: {r.status}")
        print(f"  runtime: {format_optional_number(r.runtime_seconds)}s")
        for name, mod in r.modules.items():
            print(f"  {name}: score={format_optional_number(mod.score)} status={mod.status}")
            for w in mod.warnings[:3]:
                print(f"    warning: {w}")
            for rec in mod.recommendations[:2]:
                print(f"    recommendation: {rec}")
        if r.report_path:
            print(f"  report: {r.report_path}")

    return 0 if all(r.status in {"pass", "warn"} for r in results) else 1
