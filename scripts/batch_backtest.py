"""Batch walk-forward backtest on key factors to validate effectiveness."""

import json, time, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from quant.engines.walk_forward.walk_forward import WalkForwardEngine
from quant.storage.sqlite_store import SQLitePriceStore

FACTORS = [
    "momentum_20d",          # 经典趋势
    "momentum_60d",          # 中长期趋势
    "reversal_5d",           # 短期反转
    "reversal_20d",          # 中期反转
    "value_score",           # 价值因子（市净/市销）
    "quality_score",         # 质量因子（一致性/波动）
    "low_volatility_score",  # 低波动
    "growth_score",          # 增长代理
    "risk_adjusted_momentum",# 风险调整动量
    "volatility_20d",        # 波动率（危险因子）
]

store = SQLitePriceStore("data/quant.db")
engine = WalkForwardEngine(store, report_dir="data/reports/purge_validation")

results = {}
for factor in FACTORS:
    t0 = time.time()
    print(f"\n{'='*60}")
    print(f"Testing: {factor}")
    print(f"{'='*60}")
    try:
        r = engine.run(
            strategy="alpha",
            factor=factor,
            train_years=3, test_years=2,
            start="2015-01-01", end="2025-12-31",
            initial_cash=100_000,
            rebalance_frequency="monthly",
            max_folds=5,
            workers=1,
            purge_days=0, embargo_days=0,
            write_report=False,
        )

        folds = r.folds
        if not folds:
            print(f"  ⚠ No folds generated")
            continue

        test_returns = [f.test_return for f in folds if f.test_return is not None]
        test_sharpes = [f.test_sharpe for f in folds if f.test_sharpe is not None]
        ics = [f.ic for f in folds if f.ic is not None]
        rank_ics = [f.rank_ic for f in folds if f.rank_ic is not None]

        metrics = {
            "folds": len(folds),
            "avg_return": round(sum(test_returns)/len(test_returns), 4) if test_returns else None,
            "avg_sharpe": round(sum(test_sharpes)/len(test_sharpes), 2) if test_sharpes else None,
            "avg_ic": round(sum(ics)/len(ics), 4) if ics else None,
            "avg_rank_ic": round(sum(rank_ics)/len(rank_ics), 4) if rank_ics else None,
            "win_rate": round(sum(1 for r in test_returns if r and r > 0) / len(test_returns), 2) if test_returns else None,
            "returns": [round(r, 4) for r in test_returns],
            "sharpes": [round(s, 2) for s in test_sharpes],
        }
        results[factor] = metrics
        print(f"  ✅ {len(folds)} folds | avg_return={metrics['avg_return']} | sharpe={metrics['avg_sharpe']} | rank_ic={metrics['avg_rank_ic']} | win_rate={metrics['win_rate']}")
        print(f"     returns: {metrics['returns']}")
        print(f"     sharpes: {metrics['sharpes']}")

    except Exception as e:
        print(f"  ❌ Failed: {e}")
        results[factor] = {"error": str(e)}
    print(f"  ⏱ {time.time()-t0:.1f}s")

print(f"\n{'='*60}")
print("FINAL SCOREBOARD")
print(f"{'='*60}")
print(f"{'Factor':<28} {'Folds':>5} {'Ret':>8} {'Sharpe':>7} {'IC':>8} {'RankIC':>8} {'Win%':>6}")
print(f"{'-'*28} {'-'*5} {'-'*8} {'-'*7} {'-'*8} {'-'*8} {'-'*6}")
for factor in FACTORS:
    m = results.get(factor, {})
    if "error" in m:
        print(f"{factor:<28} {'ERR':>5} {m['error'][:50]}")
    else:
        print(f"{factor:<28} {m.get('folds','?'):>5} {m.get('avg_return','?'):>8} {m.get('avg_sharpe','?'):>7} {m.get('avg_ic','?'):>8} {m.get('avg_rank_ic','?'):>8} {m.get('win_rate','?'):>6}")

print(f"\nFull results: {json.dumps(results, indent=2)}")
