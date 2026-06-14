"""HPC research matrix benchmark command."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

from quant.cli_commands.common import CLIContext, format_optional_number
from quant.engines.factor_eval.factor_evaluation import SUPPORTED_FACTORS


def register_parser(subparsers: argparse._SubParsersAction) -> None:
    benchmark = subparsers.add_parser(
        "hpc-benchmark",
        help="Compare serial, SQLite bulk, and InMemory bulk factor-eval paths.",
    )
    benchmark.add_argument("--factor", choices=sorted(SUPPORTED_FACTORS), default="momentum_20d")
    benchmark.add_argument("--start", default=None, help="Inclusive signal start date YYYY-MM-DD.")
    benchmark.add_argument("--end", default=None, help="Inclusive signal end date YYYY-MM-DD.")
    benchmark.add_argument("--forward-days", type=int, default=20)
    benchmark.add_argument("--max-symbols", type=int, default=20)
    benchmark.add_argument("--workers", action="append", type=int, default=None, help="InMemory worker count; repeatable.")
    benchmark.add_argument("--output", default=None, help="Optional JSON output path.")


def handle(args: argparse.Namespace, context: CLIContext) -> int:
    workers = args.workers or [1, 4]
    symbols = _select_symbols(context, args.max_symbols)
    rows: list[dict[str, Any]] = []

    rows.append(
        _run_factor_eval_leg(
            context,
            name="serial_reference",
            factor=args.factor,
            symbols=symbols,
            start=args.start,
            end=args.end,
            forward_days=args.forward_days,
            bulk_matrix=False,
            workers=1,
            prefer_in_memory=False,
            strict_in_memory=False,
        )
    )
    rows.append(
        _run_factor_eval_leg(
            context,
            name="sqlite_bulk",
            factor=args.factor,
            symbols=symbols,
            start=args.start,
            end=args.end,
            forward_days=args.forward_days,
            bulk_matrix=True,
            workers=1,
            prefer_in_memory=False,
            strict_in_memory=False,
        )
    )
    for worker_count in workers:
        rows.append(
            _run_factor_eval_leg(
                context,
                name=f"in_memory_bulk_workers_{worker_count}",
                factor=args.factor,
                symbols=symbols,
                start=args.start,
                end=args.end,
                forward_days=args.forward_days,
                bulk_matrix=True,
                workers=worker_count,
                prefer_in_memory=True,
                strict_in_memory=True,
            )
        )

    baseline = rows[0]["wall_time"]
    for row in rows:
        row["speedup"] = round(baseline / row["wall_time"], 6) if row["wall_time"] else None

    report = {
        "target": "factor_eval",
        "factor": args.factor,
        "forward_days": args.forward_days,
        "symbol_count": len(symbols),
        "symbols": symbols,
        "rows": rows,
    }
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
        report["output_path"] = str(output_path)

    _print_report(report)
    return 0


def _run_factor_eval_leg(
    context: CLIContext,
    *,
    name: str,
    factor: str,
    symbols: list[str],
    start: str | None,
    end: str | None,
    forward_days: int,
    bulk_matrix: bool,
    workers: int,
    prefer_in_memory: bool,
    strict_in_memory: bool,
) -> dict[str, Any]:
    started = time.perf_counter()
    result = context.factor_evaluation.evaluate(
        factor=factor,
        universe=symbols,
        start=start,
        end=end,
        forward_days=forward_days,
        bulk_matrix=bulk_matrix,
        max_workers=workers,
        prefer_in_memory=prefer_in_memory,
        strict_in_memory=strict_in_memory,
        cache_stats=bulk_matrix,
        write_report=False,
    )
    wall_time = time.perf_counter() - started
    metadata = result.performance_metadata or {}
    return {
        "scenario": name,
        "wall_time": round(wall_time, 6),
        "speedup": None,
        "observations": len(result.observations),
        "ic_mean": result.ic_mean,
        "rank_ic_mean": result.rank_ic_mean,
        "decay_ic": {
            horizon: values.get("ic")
            for horizon, values in result.decay.items()
        },
        "decay_rank_ic": {
            horizon: values.get("rank_ic")
            for horizon, values in result.decay.items()
        },
        "provider_type": metadata.get("provider_type") or ("serial_reference" if not bulk_matrix else "unknown"),
        "cache_strategy": metadata.get("cache_strategy") or ("serial_reference" if not bulk_matrix else "unknown"),
        "fallback_used": metadata.get("fallback_used", False),
        "fallback_reason": metadata.get("fallback_reason"),
        "requested_workers": metadata.get("requested_workers", workers if bulk_matrix else 1),
        "matrix_workers": metadata.get("matrix_workers", workers if bulk_matrix else 1),
        "matrix_build_seconds": metadata.get("matrix_build_seconds"),
        "eval_seconds": metadata.get("eval_seconds", round(wall_time, 6)),
    }


def _select_symbols(context: CLIContext, max_symbols: int) -> list[str]:
    symbols = context.price_store.list_symbols()
    selected = []
    for symbol in symbols:
        history = context.price_store.get_price_history(symbol)
        if not history.empty and len(history["close"].dropna()) >= 60:
            selected.append(symbol)
        if len(selected) >= max_symbols:
            break
    return selected or symbols[:max_symbols]


def _print_report(report: dict[str, Any]) -> None:
    print("HPC Benchmark")
    print(f"target: {report['target']}")
    print(f"factor: {report['factor']}")
    print(f"forward_days: {report['forward_days']}")
    print(f"symbol_count: {report['symbol_count']}")
    print("scenario wall_time speedup observations ic_mean rank_ic_mean provider_type cache_strategy fallback_used requested_workers matrix_workers matrix_build_seconds eval_seconds")
    for row in report["rows"]:
        print(
            f"{row['scenario']} "
            f"{format_optional_number(row['wall_time'])} "
            f"{format_optional_number(row['speedup'])} "
            f"{row['observations']} "
            f"{format_optional_number(row['ic_mean'])} "
            f"{format_optional_number(row['rank_ic_mean'])} "
            f"{row['provider_type']} "
            f"{row['cache_strategy']} "
            f"{str(row['fallback_used']).lower()} "
            f"{row['requested_workers']} "
            f"{row['matrix_workers']} "
            f"{format_optional_number(row['matrix_build_seconds'])} "
            f"{format_optional_number(row['eval_seconds'])}"
        )
    worker_notes = [
        row for row in report["rows"]
        if row.get("requested_workers") != row.get("matrix_workers")
    ]
    if worker_notes:
        print("worker_notes:")
        for row in worker_notes:
            print(
                f"- {row['scenario']}: requested_workers={row.get('requested_workers')} "
                f"matrix_workers={row.get('matrix_workers')}"
            )
    print("decay_ic:")
    for row in report["rows"]:
        decay = " ".join(f"{horizon}={format_optional_number(value)}" for horizon, value in row["decay_ic"].items())
        print(f"{row['scenario']}: {decay}")
    if report.get("output_path"):
        print(f"output: {report['output_path']}")
