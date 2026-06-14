#!/usr/bin/env python
"""Diagnostic: universe size, quantile assignment, spread direction."""
from __future__ import annotations

import json, random, statistics, sys
from pathlib import Path

import numpy as np
import pandas as pd

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from quant.engines.factor_backtest.factor_backtest import FactorBacktest
from quant.engines.factor_eval.factor_evaluation import FactorEvaluation
from quant.storage.sqlite_store import SQLitePriceStore
from quant.engines.factor_common.stats import cumulative_spread_return, spread_max_drawdown

DB = _PROJECT_ROOT / "data" / "quant.db"


def main():
    store = SQLitePriceStore(DB)
    bt = FactorBacktest(store)

    # Step 0: total symbols
    total_syms = store.list_symbols()
    print(f"Price store total symbols: {len(total_syms)}")
    print(f"  First 10: {total_syms[:10]}")
    print(f"  Last  10: {total_syms[-10:]}")


    top20 = total_syms[:20]
    top200 = total_syms[:200]

    # Step 1: Compare 20 vs 200 stock runs (serial reference path, bulk_matrix=False)
    print(f"\n{'='*60}")
    print("1. 20 vs 200 stock comparison (bulk_matrix=False, serial)")
    print(f"{'='*60}")

    results = {}
    for label, u in [("20", top20), ("200", top200), ("none", None)]:
        r = bt.run("volatility_20d", start="2020-06-01", end="2026-06-11",
                   holding_period=20, quantiles=5, universe=u, bulk_matrix=False)
        s = r.to_summary()
        all_syms = set()
        for p in r.periods:
            all_syms.update(p.long_symbols)
            all_syms.update(p.short_symbols)
        results[label] = {"result": r, "summary": s, "unique_syms": all_syms}

    for label in ["20", "200", "none"]:
        r = results[label]
        s = r["summary"]
        u = r["unique_syms"]
        print(f"\n  [{label} stock]")
        print(f"    unique symbols (periods): {len(u)}")
        print(f"    observation_count: {s.get('observation_count')}")
        print(f"    period_count: {s.get('period_count')}")
        print(f"    cumulative_forward_spread: {s.get('cumulative_forward_spread'):.4f}")
        print(f"    spread_max_drawdown: {s.get('spread_max_drawdown'):.4f}")
        print(f"    ic_mean: {s.get('ic_mean', 'N/A')}")
        print(f"    first 3 symbols: {sorted(u)[:3]}")
        print(f"    last  3 symbols: {sorted(u)[-3:]}")

    # Check if 20 and 200 are identical (bug)
    s20 = results["20"]["summary"]
    s200 = results["200"]["summary"]
    keys = ['cumulative_forward_spread', 'spread_max_drawdown', 'ic_mean', 'observation_count']
    same = all(s20.get(k) == s200.get(k) for k in keys)
    if same:
        print("\n  ⚠️  WARNING: 20 and 200 produce IDENTICAL metrics!")
        print("     This suggests the engine disregards universe size.")
    else:
        print("\n  ✅ 20 and 200 produce DIFFERENT metrics (as expected)")

    # Also check: does universe=None match 200? (It should NOT; None = all symbols)
    s_none = results["none"]["summary"]
    u_none_ct = len(results["none"]["unique_syms"])
    u200_ct = len(results["200"]["unique_syms"])
    print(f"\n  universe=None → {u_none_ct} unique symbols (vs 200:{u200_ct})")
    if u_none_ct == u200_ct:
        print("  ⚠️  universe=None returned same count as 200. Might be coalescing to same default.")

    # Step 2: Quantile direction — spot-check 3 signal dates
    print(f"\n{'='*60}")
    print("2. Quantile direction spot-check (volatility_20d, 200 stock)")
    print(f"{'='*60}")

    r200 = results["200"]["result"]
    print(f"  factor_higher_is_better: {r200.factor_higher_is_better}")
    print(f"  (higher_is_better=False → Q5=lowest vol, Q1=highest vol)")

    random.seed(42)
    samp = random.sample([p for p in r200.periods if p.long_symbols and p.short_symbols], 3)
    for p in samp:
        lr = getattr(p, 'long_return', getattr(p, 'long_mean_forward_return', None))
        sr = getattr(p, 'short_return', getattr(p, 'short_mean_forward_return', None))
        print(f"\n  signal_date: {p.signal_date}")
        print(f"    long  (Q5=low vol): {p.long_symbols}")
        print(f"    short (Q1=high vol): {p.short_symbols}")
        print(f"    long_mean_forward_return:  {lr:.6f}")
        print(f"    short_mean_forward_return: {sr:.6f}")
        print(f"    period_spread (long - short): {lr - sr:.6f}")

    # Step 3: Reconstruct spread from periods to verify formula
    print(f"\n{'='*60}")
    print("3. Spread formula verification")
    print(f"{'='*60}")

    spreads = []
    for p in r200.periods:
        lr = getattr(p, 'long_return', getattr(p, 'long_mean_forward_return', None))
        sr = getattr(p, 'short_return', getattr(p, 'short_mean_forward_return', None))
        if lr is not None and sr is not None:
            spreads.append(lr - sr)

    cumsum_spread = sum(spreads)
    dd = spread_max_drawdown(spreads) if spreads else None
    cs = cumulative_spread_return(spreads) if spreads else None
    reported_cs = s200.get('cumulative_forward_spread')
    reported_dd = s200.get('spread_max_drawdown')

    print(f"  Spread formula: long_mean_forward_return - short_mean_forward_return")
    print(f"  Periods with spread: {len(spreads)}")
    print(f"  Manual cumulative_spread (sum): {cumsum_spread:.6f}")
    print(f"  Reported cumulative_forward_spread: {reported_cs:.6f}")
    match_cs = abs(cumsum_spread - reported_cs) < 1e-10
    print(f"  Match: {'✅' if match_cs else '❌'}")
    print(f"  Manual spread_max_drawdown: {dd:.6f}")
    print(f"  Reported spread_max_drawdown: {reported_dd:.6f}")
    match_dd = abs(dd - reported_dd) < 1e-10
    print(f"  Match: {'✅' if match_dd else '❌'}")

    # Step 4: Factor registry universe
    print(f"\n{'='*60}")
    print("4. Factor registry universe")
    print(f"{'='*60}")
    try:
        from quant.factors.price.factor_registry import FactorRegistry
        reg = FactorRegistry()
        for fn in ["volatility_20d", "momentum_20d", "low_volatility_score"]:
            meta = reg.metadata(fn)
            uv = meta.get("universe", []) if meta else []
            print(f"  {fn}: universe_size={len(uv)}, first3={uv[:3]}")
    except Exception as exc:
        print(f"  Error: {exc}")

    # Step 5: Check bulk_matrix path
    print(f"\n{'='*60}")
    print("5. bulk_matrix=True comparison")
    print(f"{'='*60}")
    r_bulk = bt.run("volatility_20d", start="2020-06-01", end="2026-06-11",
                    holding_period=20, quantiles=5, universe=top200, bulk_matrix=True)
    s_bulk = r_bulk.to_summary()
    for k in ['cumulative_forward_spread', 'spread_max_drawdown', 'observation_count', 'ic_mean']:
        vb = s_bulk.get(k)
        vs = s200.get(k)
        match = "✅" if vb == vs else "⚠️ DIFFER"
        print(f"  {k}: serial={vs}, bulk={vb} {match}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
