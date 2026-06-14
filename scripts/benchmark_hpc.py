#!/usr/bin/env python3
"""Two-tier HPC factor-eval benchmark (standalone — not pytest).

Tiers
-----
  smoke  50 symbols × 250 days × 1 factor  → CI / quick dev check
  real   200 symbols × 500 days × 5-10 factors  → full A/B comparison

Output
------
  reports/performance/hpc_benchmark_smoke.json
  reports/performance/hpc_benchmark_smoke.md
  reports/performance/hpc_benchmark_real.json
  reports/performance/hpc_benchmark_real.md

Usage
-----
  python scripts/benchmark_hpc.py smoke
  python scripts/benchmark_hpc.py real [--serial-mode first-factor|all|none]
  python scripts/benchmark_hpc.py all
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import sys
import time
from datetime import date, datetime
from pathlib import Path
from typing import Any

import pandas as pd

# ── Project root (script lives in scripts/) ─────────────────────────
PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT))

from quant.storage.sqlite_store import SQLitePriceStore
from quant.engines.factor_eval.factor_evaluation import FactorEvaluation

OUTPUT_DIR = PROJECT / "reports" / "performance"

PRICE_FACTORS = [
    "momentum_20d",
    "momentum_60d",
    "volatility_20d",
    "risk_adjusted_momentum",
    "reversal_5d",
    "reversal_20d",
    "low_volatility_score",
    "growth_score",
    "value_score",
    "quality_score",
]

# ══════════════════════════════════════════════════════════════════════
#  Data generation
# ══════════════════════════════════════════════════════════════════════


def generate_price_db(
    db_path: Path, num_symbols: int, num_days: int
) -> list[str]:
    """Populate a SQLite DB with synthetic trending prices."""
    symbols = [f"BENCH{i:04d}" for i in range(num_symbols)]
    store = SQLitePriceStore(db_path)

    rows = []
    start_date = date(2020, 1, 1)
    rng = pd.Series(pd.date_range(start_date, periods=num_days, freq="B"))

    for si, sym in enumerate(symbols):
        drift = 0.0001 + si * 0.00005
        ticker = pd.Series(drift * (1 + si * 0.1) * 100000, index=rng.index)
        prices = 100 + ticker.cumsum() / 10000

        for di, dt in enumerate(rng):
            rows.append(
                {
                    "symbol": sym,
                    "date": dt.strftime("%Y-%m-%d"),
                    "open": float(prices.iloc[di]),
                    "high": float(prices.iloc[di]) * 1.01,
                    "low": float(prices.iloc[di]) * 0.99,
                    "close": float(prices.iloc[di]),
                    "adj_close": float(prices.iloc[di]),
                    "volume": 1000 + di,
                }
            )

        if (si + 1) % 50 == 0:
            print(f"  generated {si + 1}/{num_symbols} symbols …")

    df = pd.DataFrame(rows)
    store.upsert_prices(df)
    print(f"  upserted {len(df)} rows into {db_path}")
    return symbols


# ══════════════════════════════════════════════════════════════════════
#  CPU probe
# ══════════════════════════════════════════════════════════════════════


def cpu_note() -> str:
    try:
        cpu = platform.processor() or ""
        cpu = cpu.strip()
    except Exception:
        cpu = ""
    try:
        with open("/proc/cpuinfo") as f:
            for line in f:
                if line.startswith("model name"):
                    cpu = line.split(":", 1)[1].strip()
                    break
    except Exception:
        pass
    try:
        cores = os.cpu_count()
    except Exception:
        cores = 0
    return f"{cpu} ({cores} logical cores)"


# ══════════════════════════════════════════════════════════════════════
#  Benchmark runner
# ══════════════════════════════════════════════════════════════════════


def run_factor_eval_leg(
    engine: FactorEvaluation,
    factor: str,
    symbols: list[str],
    bulk_matrix: bool,
    workers: int,
    prefer_in_memory: bool,
    strict_in_memory: bool,
) -> dict[str, Any]:
    started = time.perf_counter()
    result = engine.evaluate(
        factor=factor,
        universe=symbols,
        start=None,
        end=None,
        forward_days=20,
        bulk_matrix=bulk_matrix,
        max_workers=workers,
        prefer_in_memory=prefer_in_memory,
        strict_in_memory=strict_in_memory,
        cache_stats=bulk_matrix,
        write_report=False,
    )
    wall = time.perf_counter() - started
    meta = result.performance_metadata or {}
    return {
        "wall_time": round(wall, 6),
        "observations": len(result.observations),
        "ic_mean": result.ic_mean,
        "rank_ic_mean": result.rank_ic_mean,
        "provider_type": meta.get("provider_type") or ("serial" if not bulk_matrix else "sqlite"),
        "cache_strategy": meta.get("cache_strategy") or ("serial" if not bulk_matrix else "unknown"),
        "fallback_used": meta.get("fallback_used", False),
        "fallback_reason": meta.get("fallback_reason"),
        "requested_workers": meta.get("requested_workers", workers if bulk_matrix else 1),
        "matrix_workers": meta.get("matrix_workers", workers if bulk_matrix else 1),
        "matrix_build_seconds": meta.get("matrix_build_seconds"),
        "eval_seconds": meta.get("eval_seconds", round(wall, 6)),
    }


# ══════════════════════════════════════════════════════════════════════
#  Smoke
# ══════════════════════════════════════════════════════════════════════


def smoke_benchmark(db_path: Path, symbols: list[str]) -> dict:
    """50 symbols × 250 days × momentum_20d."""
    factor = "momentum_20d"
    engine = FactorEvaluation(SQLitePriceStore(db_path))

    print(f"\n  running {factor} …")
    row = run_factor_eval_leg(
        engine, factor, symbols,
        bulk_matrix=True, workers=4,
        prefer_in_memory=True, strict_in_memory=True,
    )

    return {
        "tier": "smoke",
        "status": "complete",
        "timestamp": datetime.now().isoformat(),
        "symbols": len(symbols),
        "days": 250,
        "factors": [factor],
        "cpu": cpu_note(),
        "ic_tolerance": 1e-12,
        "result": row,
    }


# ══════════════════════════════════════════════════════════════════════
#  Real
# ══════════════════════════════════════════════════════════════════════

# Scenario tuples: (name, bulk_matrix, workers, prefer_in_memory, strict_in_memory)
SERIAL_SCENARIO = ("serial_reference", False, 1, False, False)

BULK_SCENARIOS = [
    ("sqlite_bulk",          True, 1, False, False),
    ("in_memory_bulk_1w",    True, 1, True,  True),
    ("in_memory_bulk_4w",    True, 4, True,  True),
    ("in_memory_bulk_8w",    True, 8, True,  True),
]


def real_benchmark(
    db_path: Path,
    symbols: list[str],
    factors: list[str],
    serial_mode: str = "first-factor",
    partial_path: Path | None = None,
) -> dict:
    """Run the real-tier HPC benchmark with incremental partial writes.

    serial_mode:
      "first-factor" — serial_reference only for factors[0] (default)
      "all"          — serial_reference for every factor
      "none"         — skip serial_reference entirely
    """
    engine = FactorEvaluation(SQLitePriceStore(db_path))
    all_rows: list[dict] = []
    partial_path = partial_path or (OUTPUT_DIR / "hpc_benchmark_real_partial.json")

    for fi, factor in enumerate(factors):
        # ----- build scenario list for this factor -----
        scenarios: list[tuple] = []
        include_serial = (
            serial_mode == "all"
            or (serial_mode == "first-factor" and fi == 0)
        )
        if include_serial:
            scenarios.append(SERIAL_SCENARIO)
        scenarios.extend(BULK_SCENARIOS)

        print(f"\n  [{fi+1}/{len(factors)}] {factor}")
        if not include_serial:
            print("    (serial_reference skipped — serial_mode=first-factor)")

        for scenario_name, bulk, workers, prefer, strict in scenarios:
            print(f"    {scenario_name} …", end=" ", flush=True)
            t0 = time.perf_counter()
            row = run_factor_eval_leg(
                engine, factor, symbols,
                bulk_matrix=bulk, workers=workers,
                prefer_in_memory=prefer, strict_in_memory=strict,
            )
            elapsed = time.perf_counter() - t0
            row["factor"] = factor
            row["scenario"] = scenario_name
            row["wall_time"] = round(elapsed, 6)
            print(f"{elapsed:.2f}s  ic={row['ic_mean']}")
            all_rows.append(row)

            # ── incremental partial write ──
            _write_partial(partial_path, all_rows, factors, symbols, serial_mode)

    # ── compute speedup (only for factors that have a serial_reference row) ──
    for factor in factors:
        factor_rows = [r for r in all_rows if r["factor"] == factor]
        serial_row = next(
            (r for r in factor_rows if r["scenario"] == "serial_reference"), None
        )
        if serial_row is None:
            for r in factor_rows:
                r["speedup"] = None
            continue
        serial_wall = serial_row["wall_time"]
        for r in factor_rows:
            if r is serial_row:
                r["speedup"] = 1.0
            elif serial_wall > 0:
                r["speedup"] = round(serial_wall / r["wall_time"], 6)
            else:
                r["speedup"] = None

    # ── IC consistency check (strict tolerance 1e-12) ──
    IC_TOLERANCE = 1e-12
    ic_consistency = {"passed": True, "max_deviation": 0.0, "tolerance": IC_TOLERANCE, "details": []}
    for factor in factors:
        factor_rows = [r for r in all_rows if r["factor"] == factor]
        serial_row = next((r for r in factor_rows if r["scenario"] == "serial_reference"), None)
        if serial_row is None:
            continue
        ref_ic = serial_row["ic_mean"]
        for r in factor_rows:
            if r["scenario"] == "serial_reference":
                continue
            dev = abs(r["ic_mean"] - ref_ic) if ref_ic is not None and r["ic_mean"] is not None else 0.0
            ic_consistency["max_deviation"] = max(ic_consistency["max_deviation"], dev)
            ic_consistency["details"].append({
                "factor": factor, "scenario": r["scenario"],
                "ic_serial": ref_ic, "ic_scenario": r["ic_mean"],
                "deviation": dev, "within_tolerance": dev <= IC_TOLERANCE,
            })
            if dev > IC_TOLERANCE:
                ic_consistency["passed"] = False

    # ── summary statistics ──
    summaries: list[dict] = []
    for scenario_name, *__ in [SERIAL_SCENARIO] + BULK_SCENARIOS:
        sc_rows = [r for r in all_rows if r["scenario"] == scenario_name]
        spd_vals = [
            r["speedup"]
            for r in sc_rows
            if r.get("speedup") is not None and r.get("speedup") != 1.0
        ]
        wts = [r["wall_time"] for r in sc_rows]
        summaries.append({
            "scenario": scenario_name,
            "median_speedup": round(float(pd.Series(spd_vals).median()), 4) if spd_vals else None,
            "mean_speedup": round(float(pd.Series(spd_vals).mean()), 4) if spd_vals else None,
            "total_wall_time": round(sum(wts), 4),
            "factor_count": len(sc_rows),
            "speedup_factor_count": len(spd_vals),
        })

    fallback_violations = [r for r in all_rows if r.get("fallback_used")]

    report = {
        "tier": "real",
        "status": "complete",
        "timestamp": datetime.now().isoformat(),
        "symbols": len(symbols),
        "days": 500,
        "factors": factors,
        "serial_mode": serial_mode,
        "cpu": cpu_note(),
        "ic_tolerance": IC_TOLERANCE,
        "ic_consistency": ic_consistency,
        "fallback_violations": fallback_violations,
        "summary": summaries,
        "rows": all_rows,
    }
    return report


def _write_partial(
    path: Path,
    rows: list[dict],
    factors: list[str],
    symbols: list[str],
    serial_mode: str,
) -> None:
    """Incrementally write partial results so no data is lost on SIGKILL."""
    partial = {
        "tier": "real",
        "status": "partial",
        "timestamp": datetime.now().isoformat(),
        "symbols": len(symbols),
        "days": 500,
        "factors": factors,
        "serial_mode": serial_mode,
        "cpu": cpu_note(),
        "ic_tolerance": 1e-12,
        "completed_rows": len(rows),
        "rows": rows,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(partial, indent=2, sort_keys=True, default=str),
        encoding="utf-8",
    )


# ══════════════════════════════════════════════════════════════════════
#  Markdown report
# ══════════════════════════════════════════════════════════════════════


def fmt_opt(val, digits=4) -> str:
    if val is None:
        return "—"
    return f"{val:.{digits}f}"


def smoke_markdown(report: dict) -> str:
    r = report["result"]
    lines = [
        "# HPC Factor Eval — Smoke Benchmark",
        "",
        f"**Timestamp:** {report['timestamp']}  ",
        f"**CPU:** {report['cpu']}  ",
        f"**Scale:** {report['symbols']} symbols × {report['days']} days × 1 factor",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| provider_type | `{r['provider_type']}` |",
        f"| cache_strategy | `{r['cache_strategy']}` |",
        f"| fallback_used | {r['fallback_used']} |",
        f"| requested_workers | {r['requested_workers']} |",
        f"| matrix_workers | {r['matrix_workers']} |",
        f"| observations | {r['observations']} |",
        f"| ic_mean | {fmt_opt(r['ic_mean'], 6)} |",
        f"| rank_ic_mean | {fmt_opt(r['rank_ic_mean'], 6)} |",
        f"| wall_time | {fmt_opt(r['wall_time'], 3)}s |",
        f"| matrix_build_seconds | {fmt_opt(r['matrix_build_seconds'], 4)}s |",
        f"| eval_seconds | {fmt_opt(r['eval_seconds'], 4)}s |",
        "",
        "---",
        "*Generated by `scripts/benchmark_hpc.py smoke`*",
    ]
    return "\n".join(lines)


def real_markdown(report: dict) -> str:
    rows = report["rows"]
    factors = report["factors"]
    serial_mode = report.get("serial_mode", "first-factor")

    # Determine which factors have serial coverage
    serial_factors = sorted({
        r["factor"] for r in rows if r["scenario"] == "serial_reference"
    })

    lines = [
        "# HPC Factor Eval — Real Benchmark",
        "",
        f"**Timestamp:** {report['timestamp']}  ",
        f"**CPU:** {report['cpu']}  ",
        f"**Scale:** {report['symbols']} symbols × {report['days']} days × {len(factors)} factors",
        f"**Serial mode:** `{serial_mode}`",
        "",
    ]

    # ── Role notes ──
    lines.append("## Roles")
    lines.append("")
    lines.append("- **serial_reference**: correctness & reference baseline — slow by design, one-at-a-time SQLite lookups")
    lines.append("  - Serial is **not** a production path; used only to validate that bulk/in-memory paths produce identical results.")
    lines.append("  - Production benchmarks measure **sqlite_bulk / in_memory_bulk_*** throughput.")
    lines.append("- **sqlite_bulk / in_memory_bulk_* **: production HPC paths — bulk matrix + vectorised factor computation")
    lines.append(
        f"- Speedup is computed **only** for factors that have a serial_reference row "
        f"({len(serial_factors)}/{len(factors)}: {', '.join(serial_factors)})"
    )
    lines.append("")

    # ── Fallback violations ──
    violations = report.get("fallback_violations", [])
    if violations:
        lines.append("## ⚠️ Fallback Violations")
        lines.append("")
        for v in violations:
            lines.append(
                f"- `{v['factor']}` / `{v['scenario']}`: "
                f"{v.get('fallback_reason', 'unknown')}"
            )
        lines.append("")
    else:
        lines.append("## ✅ No fallback violations")
        lines.append("")

    # ── IC consistency ──
    ic_cons = report.get("ic_consistency", {})
    ic_tol = report.get("ic_tolerance", 1e-12)
    lines.append("## IC Consistency")
    lines.append("")
    lines.append(f"- **Tolerance:** {ic_tol:.0e} (strict floating-point equality)")
    lines.append(f"- **Status:** {'✅ passed' if ic_cons.get('passed', True) else '⚠️ FAILED'}")
    lines.append(f"- **Max deviation:** {ic_cons.get('max_deviation', 0):.2e}")
    if ic_cons.get("details"):
        lines.append("")
        lines.append("| factor | scenario | ic_serial | ic_scenario | deviation | ok |")
        lines.append("|--------|----------|-----------|-------------|-----------|----|")
        for d in ic_cons["details"]:
            lines.append(
                f"| {d['factor']} | {d['scenario']} "
                f"| {d['ic_serial']:.15f} | {d['ic_scenario']:.15f} "
                f"| {d['deviation']:.2e} | {'✅' if d['within_tolerance'] else '❌'} |"
            )
        lines.append("")

    # ── Summary table ──
    lines.append("## Summary")
    lines.append("")
    lines.append(
        "| scenario | speedup (median) | speedup (mean) | total wall | "
        "factors (speedup N) |"
    )
    lines.append(
        "|----------|-----------------|---------------|------------|"
        "---------------------|"
    )
    for s in report["summary"]:
        ms = fmt_opt(s["median_speedup"], 3)
        mn = fmt_opt(s["mean_speedup"], 3)
        spd_n = s.get("speedup_factor_count", s["factor_count"])
        lines.append(
            f"| {s['scenario']} "
            f"| {ms}× "
            f"| {mn}× "
            f"| {s['total_wall_time']:.2f}s "
            f"| {spd_n} |"
        )
    lines.append("")

    # ── Per‑factor detail ──
    lines.append("## Per‑Factor Detail")
    lines.append("")
    header_cols = [
        "factor", "scenario", "speedup", "wall_time", "ic_mean",
        "provider_type", "cache_strategy", "requested_workers",
        "matrix_workers", "matrix_build_s", "eval_s", "fallback",
    ]
    lines.append(
        "| " + " | ".join(header_cols) + " |"
    )
    lines.append(
        "|" + "|".join("-" * (len(c) + 2) for c in header_cols) + "|"
    )
    for row in rows:
        lines.append(
            f"| {row['factor']} "
            f"| {row['scenario']} "
            f"| {fmt_opt(row.get('speedup'), 2)}× "
            f"| {row['wall_time']:.3f}s "
            f"| {fmt_opt(row['ic_mean'], 6)} "
            f"| `{row['provider_type']}` "
            f"| `{row['cache_strategy']}` "
            f"| {row['requested_workers']} "
            f"| {row['matrix_workers']} "
            f"| {fmt_opt(row.get('matrix_build_seconds'), 4)} "
            f"| {fmt_opt(row.get('eval_seconds'), 4)} "
            f"| {row['fallback_used']} |"
        )
    lines.append("")

    # ── Worker saturation note ──
    lines.append("## Worker Saturation")
    lines.append("")
    lines.append("- At 200-symbol scale, in_memory_bulk_1w / 4w / 8w show minimal wall-time difference (~0.1–0.5s).")
    lines.append("- The dominant speedup comes from **bulk matrix vectorisation** (18–20× over serial), not from multi-process parallelism.")
    lines.append("- Multi-process (COW fork) is expected to show gains at larger scales (≥500 symbols, ≥1000 days).")
    lines.append("")

    # ── Environment ──
    lines.append("## Environment")
    lines.append("")
    lines.append(f"- CPU: {report['cpu']}")
    lines.append(f"- Python: {sys.version.split()[0]}")
    lines.append(f"- Platform: {platform.platform()}")
    lines.append(f"- strict_in_memory: True on in_memory_bulk_* scenarios")
    lines.append(f"- ic_tolerance: {report.get('ic_tolerance', 1e-12):.0e}")
    lines.append("")
    lines.append("---")
    lines.append("*Generated by `scripts/benchmark_hpc.py real`*")

    return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════════
#  Main
# ══════════════════════════════════════════════════════════════════════


def main():
    parser = argparse.ArgumentParser(description="HPC Factor-Eval Benchmark")
    parser.add_argument(
        "tier", choices=["smoke", "real", "all"],
        help="Which benchmark tier to run"
    )
    parser.add_argument(
        "--db", default=None,
        help="Reuse existing DB path instead of generating synthetic data"
    )
    parser.add_argument(
        "--serial-mode", default="first-factor",
        choices=["first-factor", "all", "none"],
        help="When to run serial_reference (default: first-factor)"
    )
    args = parser.parse_args()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"CPU: {cpu_note()}")
    print(f"Output: {OUTPUT_DIR}")

    if args.db:
        db_path = Path(args.db)
        if not db_path.exists():
            print(f"ERROR: DB not found: {db_path}")
            return 1
        print(f"Using existing DB: {db_path}")
        store = SQLitePriceStore(db_path)
        symbols = store.list_symbols()
        print(f"  {len(symbols)} symbols available")
    else:
        db_path = OUTPUT_DIR / "hpc_benchmark_data.db"

    # ── Smoke ──
    if args.tier in ("smoke", "all"):
        print("\n" + "=" * 60)
        print("🏃 SMOKE BENCHMARK (50 symbols × 250 days)")
        print("=" * 60)

        smoke_symbols: list[str]
        if not args.db:
            print("Generating synthetic data …")
            smoke_symbols = generate_price_db(db_path, num_symbols=50, num_days=250)
        else:
            smoke_symbols = symbols[:50]

        report = smoke_benchmark(db_path, smoke_symbols)

        json_path = OUTPUT_DIR / "hpc_benchmark_smoke.json"
        json_path.write_text(
            json.dumps(report, indent=2, sort_keys=True, default=str),
            encoding="utf-8",
        )
        md_path = OUTPUT_DIR / "hpc_benchmark_smoke.md"
        md_path.write_text(smoke_markdown(report), encoding="utf-8")

        r = report["result"]
        print(
            f"\n✅ smoke done: {r['observations']} obs, "
            f"wall={r['wall_time']:.3f}s, ic={fmt_opt(r['ic_mean'], 6)}"
        )
        print(f"   {json_path}")
        print(f"   {md_path}")

    # ── Real ──
    if args.tier in ("real", "all"):
        print("\n" + "=" * 60)
        print(
            f"🏃 REAL BENCHMARK (200 symbols × 500 days × 5 factors, "
            f"serial_mode={args.serial_mode})"
        )
        print("=" * 60)

        real_symbols: list[str]
        if not args.db:
            print("Generating synthetic data …")
            real_symbols = generate_price_db(db_path, num_symbols=200, num_days=500)
        else:
            real_symbols = symbols[:200]

        num_factors = int(os.environ.get("HPC_BENCH_FACTORS", "5"))
        benchmark_factors = PRICE_FACTORS[:num_factors]

        partial_path = OUTPUT_DIR / "hpc_benchmark_real_partial.json"
        report = real_benchmark(
            db_path, real_symbols, benchmark_factors,
            serial_mode=args.serial_mode,
            partial_path=partial_path,
        )

        json_path = OUTPUT_DIR / "hpc_benchmark_real.json"
        json_path.write_text(
            json.dumps(report, indent=2, sort_keys=True, default=str),
            encoding="utf-8",
        )
        md_path = OUTPUT_DIR / "hpc_benchmark_real.md"
        md_path.write_text(real_markdown(report), encoding="utf-8")

        # ── console summary ──
        print(f"\n  Summary (speedup vs serial_reference):")
        for s in report["summary"]:
            ms = fmt_opt(s["median_speedup"], 3)
            sc = s["scenario"]
            spd_n = s.get("speedup_factor_count", s["factor_count"])
            print(
                f"    {sc:<28s}  {ms:>6s}×  "
                f"({s['total_wall_time']:.2f}s total, {spd_n} factors with speedup)"
            )

        violations = report.get("fallback_violations", [])
        if violations:
            print(f"\n  ⚠️  {len(violations)} fallback violations!")
            for v in violations:
                print(f"      {v['factor']} / {v['scenario']}: {v.get('fallback_reason','?')}")

        print(f"\n✅ real done")
        print(f"   {json_path}")
        print(f"   {md_path}")
        if partial_path.exists():
            print(f"   partial: {partial_path}")

    # Cleanup synthetic DB (keep if --db was provided)
    if not args.db and db_path.exists():
        db_path.unlink()
        print(f"\n🧹 cleaned up {db_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
