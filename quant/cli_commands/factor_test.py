"""factor-test: Quick factor validation returning compact JSON.

Usage:
    python -m quant.cli factor-test --factor momentum_20d --max-symbols 20 --pretty
    python -m quant.cli factor-test --factors momentum_20d,momentum_60d --max-symbols 20 --pretty
    python -m quant.cli factor-test --factor momentum_20d --max-symbols 20 --write-report
"""

from __future__ import annotations

import json
import time
from argparse import ArgumentParser, Namespace
from typing import Any

from quant.engines.output_modes import score_factor


def register_parser(subparsers) -> None:
    parser: ArgumentParser = subparsers.add_parser(
        "factor-test",
        help="Quick factor validation: eval + backtest returning compact JSON.",
    )
    parser.add_argument(
        "--factor",
        default=None,
        help="Single factor name to test.",
    )
    parser.add_argument(
        "--factors",
        default=None,
        help="Comma-separated factor names to test.",
    )
    parser.add_argument(
        "--factor-family",
        default=None,
        choices=["price", "fundamental", "all"],
        help="Factor family to enumerate from store.",
    )
    parser.add_argument("--start", default=None, help="Start date YYYY-MM-DD.")
    parser.add_argument("--end", default=None, help="End date YYYY-MM-DD.")
    parser.add_argument("--max-symbols", type=int, default=200, help="Universe size.")
    parser.add_argument("--workers", type=int, default=4, help="Max parallel workers.")
    parser.add_argument(
        "--mode",
        default="quick",
        choices=["quick", "standard"],
        help="quick=one horizon, standard=multi-horizon.",
    )
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON output.")
    parser.add_argument(
        "--write-report",
        action="store_true",
        default=False,
        help="Write JSON report to reports/ directory.",
    )
    parser.add_argument(
        "--include-observations",
        action="store_true",
        default=False,
        help="Include full observations in output.",
    )
    parser.add_argument(
        "--no-bulk-matrix",
        action="store_true",
        help="Use serial reference path (for debug / correctness).",
    )
    parser.add_argument(
        "--include-costs",
        action="store_true",
        default=False,
        help="Apply cost sensitivity / transaction costs.",
    )
    parser.add_argument("--output", default=None, help="Write result JSON to file path.")


def handle(args: Namespace, context) -> int:

    # Resolve factor list
    factors: list[str] = []
    if args.factor:
        factors = [args.factor]
    elif args.factors:
        factors = [f.strip() for f in args.factors.split(",") if f.strip()]
    elif args.factor_family:
        # Enumerate from store
        factors = _enumerate_family(context, args.factor_family)

    if not factors:
        print("ERROR: No factors specified. Use --factor, --factors, or --factor-family.", flush=True)
        return 1

    horizon_days = [20] if args.mode == "quick" else [5, 10, 20, 40, 60]
    bulk = not args.no_bulk_matrix

    factored_universe = _resolve_universe(context, factors, args.max_symbols)
    results: list[dict[str, Any]] = []
    summary = {"pass": 0, "watch": 0, "reject": 0, "error": 0, "top_factors": []}

    for factor_name in factors:
        started = time.monotonic()
        try:
            eval_result = context.factor_evaluation.evaluate(
                factor=factor_name,
                start=args.start,
                end=args.end,
                forward_days=20,
                universe=factored_universe,
                pipeline_config=None,
                use_cache=False,
                bulk_matrix=bulk,
                max_workers=args.workers,
                write_report=args.write_report,
            )
            bt_result = context.factor_backtest_engine.run(
                factor=factor_name,
                start=args.start,
                end=args.end,
                holding_period=20,
                universe=factored_universe,
                pipeline_config=None,
                bulk_matrix=bulk,
                max_workers=args.workers,
                write_report=args.write_report,
            )
        except Exception as exc:
            results.append({
                "factor": factor_name,
                "status": "ERROR",
                "score": 0,
                "metrics": {
                    "ic_mean": None,
                    "rank_ic_mean": None,
                    "icir": None,
                    "decay_ic": None,
                    "total_return": None,
                    "annualized_return": None,
                    "sharpe": None,
                    "max_drawdown": None,
                    "turnover": None,
                    "long_short_return": None,
                    "long_leg_return": None,
                    "short_leg_return": None,
                },
                "decision": {"useful": False, "reason": str(exc)[:200]},
                "warnings": [str(exc)[:200]],
                "metadata": {
                    "bulk_matrix_enabled": bulk,
                    "serial_reference": False,
                    "provider_type": None,
                    "fallback_used": False,
                    "runtime_seconds": round(time.monotonic() - started, 3),
                },
            })
            summary["error"] += 1
            continue

        eval_summary = eval_result.to_summary(include_observations=args.include_observations)
        bt_summary = bt_result.to_summary(include_observations=args.include_observations)
        scoring = score_factor(eval_summary, bt_summary)
        perf_meta = eval_summary.get("performance_metadata") or {}
        elapsed = round(time.monotonic() - started, 3)

        item = {
            "factor": factor_name,
            "status": scoring["status"],
            "score": scoring["score"],
            "metrics": {
                "ic_mean": eval_summary.get("ic_mean"),
                "rank_ic_mean": eval_summary.get("rank_ic_mean"),
                "icir": eval_summary.get("icir"),
                "decay_ic": eval_summary.get("decay"),
                "total_return": bt_summary.get("total_return"),
                "annualized_return": bt_summary.get("annualized_return"),
                "sharpe": bt_summary.get("sharpe"),
                "max_drawdown": bt_summary.get("max_drawdown"),
                "turnover": bt_summary.get("turnover"),
                "long_short_return": bt_summary.get("long_short_return"),
                "long_leg_return": bt_summary.get("long_leg_return"),
                "short_leg_return": bt_summary.get("short_leg_return"),
            },
            "decision": {
                "useful": scoring["status"] == "PASS",
                "reason": scoring["reason"],
            },
            "scoring": scoring,
            "warnings": eval_summary.get("warnings", []),
            "metadata": {
                "bulk_matrix_enabled": perf_meta.get("bulk_matrix_enabled", bulk),
                "serial_reference": False,
                "provider_type": perf_meta.get("provider_type"),
                "fallback_used": perf_meta.get("fallback_used", False),
                "runtime_seconds": elapsed,
            },
        }

        if scoring["status"] == "PASS":
            summary["pass"] += 1
        elif scoring["status"] == "WATCH":
            summary["watch"] += 1
        elif scoring["status"] == "REJECT":
            summary["reject"] += 1
        else:
            summary["error"] += 1

        if scoring["status"] == "PASS" or scoring["status"] == "WATCH":
            summary["top_factors"].append({
                "factor": factor_name,
                "score": scoring["score"],
                "status": scoring["status"],
                "sharpe": bt_summary.get("sharpe"),
                "icir": eval_summary.get("icir"),
            })

        results.append(item)

    # Sort top factors by score descending
    summary["top_factors"].sort(key=lambda x: x["score"], reverse=True)
    summary["top_factors"] = summary["top_factors"][:10]

    actual_symbols = len(factored_universe) if factored_universe else 0
    output = {
        "run_type": "factor_test",
        "mode": args.mode,
        "start": args.start or "(auto)",
        "end": args.end or "(auto)",
        "requested_max_symbols": args.max_symbols,
        "actual_symbol_count": actual_symbols,
        "results": results,
        "summary": summary,
    }

    json_text = json.dumps(output, indent=2 if args.pretty else None, default=str)
    print(json_text, flush=True)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as fh:
            fh.write(json_text)
            fh.write("\n")

    return 0


def _resolve_universe(context, factors: list[str], max_symbols: int) -> list[str] | None:
    """Resolve a universe from factor store or price store, capped at max_symbols."""
    # 1. Try factor store universe
    try:
        store = context.factor_store if hasattr(context, "factor_store") else None
        if store is not None:
            summary = store.summary(write_report=False)
            factor_info = summary.get("factors", {}) if isinstance(summary, dict) else {}
            if factor_info:
                symbols: set[str] = set()
                for f in factors:
                    info = factor_info.get(f, {})
                    universe_list = info.get("universe", []) if isinstance(info, dict) else []
                    symbols.update(universe_list)
                if symbols:
                    return list(symbols)[:max_symbols]
    except Exception:
        pass

    # 2. Fallback to price store
    try:
        price_store = context.price_store if hasattr(context, "price_store") else None
        if price_store is not None:
            all_symbols = price_store.list_symbols()
            if all_symbols:
                return all_symbols[:max_symbols]
    except Exception:
        pass

    # 3. Let engine use its own default
    return None


def _enumerate_family(context, family: str) -> list[str]:
    """Enumerate factor names from a given family."""
    try:
        store = context.factor_store
        if store is None:
            return []
        summary = store.summary(write_report=False)
        factor_info = summary.get("factors", {}) if isinstance(summary, dict) else {}
        matched: list[str] = []
        for name, info in factor_info.items():
            if not isinstance(info, dict):
                continue
            cat = info.get("category", info.get("type", ""))
            if family == "all" or cat == family:
                matched.append(name)
        return matched[:50]
    except Exception:
        return []
