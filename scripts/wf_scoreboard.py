#!/usr/bin/env python
"""Alpha strategy walk-forward scoreboard: 20 stocks, 2018-2024, 3yr train / 2yr test.

Runs walk_forward for each factor and prints a scoreboard.
"""
from __future__ import annotations

import sys, time, json
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from quant.storage.sqlite_store import SQLitePriceStore
from quant.data.fundamental.fundamental_store import FundamentalStore
from quant.factors.price.factor_registry import FactorRegistry
from quant.engines.walk_forward.walk_forward import WalkForwardEngine

DB = _PROJECT_ROOT / "data" / "quant.db"

FACTORS = [
    "momentum_20d",
    "momentum_60d",
    "quality_score",
    "growth_score",
    "low_volatility_score",
    "value_score",
    "reversal_5d",
    "reversal_20d",
    "risk_adjusted_momentum",
    "volatility_20d",
]

START = "2018-01-01"
END = "2024-12-31"
TRAIN_YEARS = 3.0
TEST_YEARS = 2.0
N_SYMBOLS = 20

def main():
    price_store = SQLitePriceStore(DB)
    fundamental_store = FundamentalStore(DB)
    factor_registry = FactorRegistry(fundamental_store)

    # Get 20 symbols
    all_symbols = price_store.list_symbols()
    universe = all_symbols[:N_SYMBOLS]
    print(f"Universe: {len(universe)} stocks ({universe[0]} ... {universe[-1]})")
    print(f"Date range: {START} to {END}")
    print(f"Train/Test: {TRAIN_YEARS}yr / {TEST_YEARS}yr")

    engine = WalkForwardEngine(price_store, fundamental_store)

    results = []
    for i, factor in enumerate(FACTORS):
        t0 = time.monotonic()
        try:
            result = engine.run(
                strategy="alpha",
                factor=factor,
                train_years=TRAIN_YEARS,
                test_years=TEST_YEARS,
                start=START,
                end=END,
                universe=universe,
                initial_cash=100000.0,
                rebalance_frequency="monthly",
                alpha_config={"rebalance_frequency": "monthly"},
                max_folds=None,  # all folds
                parallel=False,
            )
        except Exception as exc:
            results.append({
                "factor": factor,
                "error": str(exc)[:200],
            })
            print(f"  [{i+1}/{len(FACTORS)}] {factor:30s} ERROR: {exc}")
            continue

        elapsed = time.monotonic() - t0

        # Collect fold-level results
        folds = []
        all_folds_positive = True
        for fold in result.folds:
            tr = fold.test_return
            ts = fold.test_sharpe
            folds.append({
                "fold": fold.fold_id,
                "train": f"{fold.train_start}..{fold.train_end}",
                "test": f"{fold.test_start}..{fold.test_end}",
                "test_return": tr,
                "test_sharpe": ts,
            })
            if tr is not None and tr < 0:
                all_folds_positive = False

        summary = result.summary
        avg_test = summary.get("average_test_return")
        avg_sharpe = summary.get("average_test_sharpe")
        avg_ic = summary.get("average_ic")

        # Get max drawdown from fold reports if available
        max_dd = None
        for fold in result.folds:
            if hasattr(fold, 'max_drawdown') and fold.max_drawdown is not None:
                if max_dd is None or fold.max_drawdown < max_dd:
                    max_dd = fold.max_drawdown

        results.append({
            "factor": factor,
            "avg_test_return": avg_test,
            "avg_sharpe": avg_sharpe,
            "avg_ic": avg_ic,
            "max_drawdown": max_dd,
            "fold_count": summary.get("fold_count"),
            "folds": folds,
            "all_folds_positive": all_folds_positive,
            "runtime_s": round(elapsed, 1),
        })
        status = "✅" if all_folds_positive else ""
        print(f"  [{i+1}/{len(FACTORS)}] {factor:30s} return={str(avg_test):>10s} sharpe={str(avg_sharpe):>8s} dd={str(max_dd):>8s} folds={len(folds)} {status}  ({elapsed:.1f}s)")

    # Print scoreboard
    print()
    print("=" * 100)
    print(f"  Alpha Walk-Forward Scoreboard  ({len(universe)} stocks, {START}~{END}, {TRAIN_YEARS}yr train / {TEST_YEARS}yr test)")
    print("=" * 100)
    print(f"  {'Rank':4s} {'Factor':30s} {'Return':>8s} {'Sharpe':>8s} {'Max DD':>8s} {'Folds':>6s} {'All+':>5s}")
    print("  " + "-" * 75)

    # Sort by avg_test_return
    sorted_results = sorted(
        [r for r in results if "error" not in r],
        key=lambda r: r.get("avg_test_return") or 0,
        reverse=True,
    )

    for rank, r in enumerate(sorted_results, 1):
        ret = r["avg_test_return"]
        sharpe = r["avg_sharpe"]
        dd = r["max_drawdown"]
        medals = {1: "🥇", 2: "🥈", 3: "🥉"}.get(rank, "")
        all_ok = "✅" if r["all_folds_positive"] else "  "
        ret_str = f"{ret*100:+.1f}%" if ret is not None else "N/A"
        sharpe_str = f"{sharpe:.2f}" if sharpe is not None else "N/A"
        dd_str = f"{dd*100:.0f}%" if dd is not None else "N/A"
        print(f"  {medals}{rank:2d}  {r['factor']:30s} {ret_str:>8s} {sharpe_str:>8s} {dd_str:>8s} {r['fold_count']:>5}  {all_ok}")

    # Print errors
    errors = [r for r in results if "error" in r]
    if errors:
        print()
        print("  Errors:")
        for e in errors:
            print(f"    {e['factor']}: {e['error']}")

    # Fold details
    print()
    print("=" * 100)
    print("  Fold Details")
    print("=" * 100)
    for r in sorted_results:
        print(f"  {r['factor']}:")
        for f in r["folds"]:
            tr = f"{f['test_return']*100:+.1f}%" if f["test_return"] is not None else "N/A"
            ts = f"{f['test_sharpe']:.2f}" if f["test_sharpe"] is not None else "N/A"
            print(f"    Fold {f['fold']}: test={f['test']}  return={tr}  sharpe={ts}")

    return 0

if __name__ == "__main__":
    sys.exit(main())
