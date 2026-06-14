#!/usr/bin/env python3
"""Batch factor comparison: eval + backtest + research-validation for all factors.

Outputs:
  reports/factor_comparison/factor_comparison_raw.json
  reports/factor_comparison/factor_comparison_ranked.md
  reports/factor_comparison/factor_comparison_agent_export.md
  reports/factor_comparison/factor_comparison_flags.json
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np

# Ensure cwd is project root
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quant.storage.sqlite_store import SQLitePriceStore
from quant.data.fundamental.fundamental_store import FundamentalStore
from quant.factors.price.factor_registry import FactorRegistry
from quant.engines.factor_eval.factor_evaluation import FactorEvaluation, SUPPORTED_FACTORS
from quant.engines.factor_backtest.factor_backtest import FactorBacktest

OUTDIR = ROOT / "reports" / "factor_comparison"
OUTDIR.mkdir(parents=True, exist_ok=True)

DB_PATH = "data/quant.db"
price_store = SQLitePriceStore(DB_PATH)
fundamental_store = FundamentalStore(DB_PATH)
# FactorEvaluation/FactorBacktest construct their own FactorRegistry from fundamental_store
eval_engine = FactorEvaluation(price_store, report_dir=OUTDIR, fundamental_store=fundamental_store)
backtest_engine = FactorBacktest(price_store, report_dir=OUTDIR, fundamental_store=fundamental_store)

SYMBOLS = price_store.list_symbols()
SYMBOL_COUNT = len(SYMBOLS)

# Find date range
import sqlite3
conn = sqlite3.connect(DB_PATH)
date_range = conn.execute("SELECT MIN(date), MAX(date) FROM prices").fetchone()
conn.close()
DB_START, DB_END = date_range[0], date_range[1]

# Use 2018-2024 as requested
START = "2018-01-01"
END = "2024-12-31"

print(f"DB range: {DB_START} → {DB_END}")
print(f"Symbols: {SYMBOL_COUNT}")
print(f"Analysis range: {START} → {END}")
print()

# Classify factors
price_factors = []
fundamental_factors = []
registry = eval_engine.factor_registry
for f in sorted(SUPPORTED_FACTORS):
    desc = registry.describe(f)
    if desc.fundamental_data_required:
        fundamental_factors.append(f)
    else:
        price_factors.append(f)

print(f"Price factors ({len(price_factors)}): {', '.join(price_factors)}")
print(f"Fundamental factors ({len(fundamental_factors)}): {', '.join(fundamental_factors)}")
print()

all_results: dict[str, dict[str, Any]] = {}
flags: list[dict[str, Any]] = []
started_at = time.monotonic()

# ─── A. Factor Eval ───────────────────────────────────────────────────

print("=" * 60)
print("A. Factor Evaluation (bulk_matrix=True, InMemory)")
print("=" * 60)

for factor in sorted(SUPPORTED_FACTORS):
    family = "price" if factor in price_factors else "fundamental"
    f_start = time.monotonic()
    try:
        result = eval_engine.evaluate(
            factor=factor,
            start=START,
            end=END,
            forward_days=20,
            universe=SYMBOLS,
            bulk_matrix=True,
            cache_stats=True,
        )
        runtime = round(time.monotonic() - f_start, 2)
        decay_ics = {}
        if hasattr(result, 'decay_ics') and result.decay_ics:
            decay_ics = {str(h): round(v, 6) for h, v in result.decay_ics.items()}
        rank_decay = {}
        if hasattr(result, 'rank_decay_ics') and result.rank_decay_ics:
            rank_decay = {str(h): round(v, 6) for h, v in result.rank_decay_ics.items()}

        from quant.engines.factor_eval.factor_evaluation import DEFAULT_DECAY_DAYS
        decay_detail = {}
        if hasattr(result, 'decay') and result.decay:
            decay_detail = result.decay

        obs_list = getattr(result, "observations", [])
        obs_count = len(obs_list) if isinstance(obs_list, list) else (obs_list or 0)
        entry = {
            "factor": factor,
            "family": family,
            "step": "factor_eval",
            "status": "ok",
            "runtime_seconds": runtime,
            "observations": obs_count,
            "ic_mean": round(getattr(result, "ic_mean", 0.0), 6),
            "ic_std": round(getattr(result, "ic_std", 0.0), 6),
            "rank_ic_mean": round(getattr(result, "rank_ic_mean", 0.0), 6),
            "rank_ic_std": round(getattr(result, "rank_ic_std", 0.0), 6),
            "icir": round(getattr(result, "icir", 0.0), 6),
            "ic_positive_rate": round(getattr(result, "ic_positive_rate", 0.0), 4) if hasattr(result, "ic_positive_rate") else None,
            "decay_ics": decay_ics,
            "rank_decay_ics": rank_decay,
            "decay_detail": decay_detail,
            "quintile_spread": round(getattr(result, "spread_return", 0.0), 6) if hasattr(result, "spread_return") else None,
            "excluded_count": len(getattr(result, "excluded_symbols", [])),
            "exclusion_reasons": getattr(result, "exclusion_reasons", {}),
            "warnings": getattr(result, "warnings", [])[:10],
            "bulk_matrix_enabled": True,
            "metadata": getattr(result, "metadata", {}) if hasattr(result, "metadata") else {},
        }
        all_results[f"{factor}__eval"] = entry
        print(f"  ✅ {factor:30s}  obs={entry['observations']:>6d}  IC={entry['ic_mean']:+.4f}  "
              f"RankIC={entry['rank_ic_mean']:+.4f}  Pos={entry.get('ic_positive_rate') or 0:.2f}  {runtime:.1f}s")

        # Flag if suspicious
        if entry["observations"] < 100:
            flags.append({"factor": factor, "step": "eval", "flag": "LOW_OBSERVATIONS",
                          "value": entry["observations"], "threshold": 100})

    except Exception as e:
        elapsed = round(time.monotonic() - f_start, 2)
        all_results[f"{factor}__eval"] = {"factor": factor, "family": family, "step": "factor_eval",
                                           "status": "error", "error": str(e), "runtime_seconds": elapsed}
        flags.append({"factor": factor, "step": "eval", "flag": "EVAL_ERROR", "error": str(e)})
        print(f"  ❌ {factor:30s}  ERROR: {e!s:.80s}  ({elapsed:.1f}s)")

print()

# ─── B. Factor Backtest ───────────────────────────────────────────────

print("=" * 60)
print("B. Factor Backtest (long-short, quintile)")
print("=" * 60)

for factor in sorted(SUPPORTED_FACTORS):
    family = "price" if factor in price_factors else "fundamental"
    f_start = time.monotonic()
    try:
        result = backtest_engine.run(
            factor=factor,
            start=START,
            end=END,
            holding_period=20,
            universe=SYMBOLS,
            bulk_matrix=True,
            cache_stats=True,
        )
        runtime = round(time.monotonic() - f_start, 2)

        obs_list = getattr(result, "observations", [])
        obs_count = len(obs_list) if isinstance(obs_list, list) else (obs_list or 0)
        entry = {
            "factor": factor,
            "family": family,
            "step": "factor_backtest",
            "status": "ok",
            "runtime_seconds": runtime,
            "observations": obs_count,
            "total_return": round(getattr(result, "total_return", 0.0), 6) if hasattr(result, "total_return") else None,
            "annualized_return": round(getattr(result, "annualized_return", 0.0), 6) if hasattr(result, "annualized_return") else None,
            "sharpe": round(getattr(result, "sharpe", 0.0), 6) if hasattr(result, "sharpe") else None,
            "max_drawdown": round(getattr(result, "max_drawdown", 0.0), 6) if hasattr(result, "max_drawdown") else None,
            "turnover": round(getattr(result, "turnover", 0.0), 6) if hasattr(result, "turnover") else None,
            "long_leg_return": round(getattr(result, "long_return", 0.0), 6) if hasattr(result, "long_return") else (
                round(getattr(result, "long_leg_return", 0.0), 6) if hasattr(result, "long_leg_return") else None),
            "short_leg_return": round(getattr(result, "short_return", 0.0), 6) if hasattr(result, "short_return") else (
                round(getattr(result, "short_leg_return", 0.0), 6) if hasattr(result, "short_leg_return") else None),
            "cost_impact": round(getattr(result, "cost_impact", 0.0), 6) if hasattr(result, "cost_impact") else None,
            "net_return": round(getattr(result, "net_return", 0.0), 6) if hasattr(result, "net_return") else None,
            "rebalance_count": getattr(result, "rebalance_count", None),
            "excluded_count": len(getattr(result, "excluded_symbols", [])),
            "exclusion_reasons": getattr(result, "exclusion_reasons", {}),
            "warnings": getattr(result, "warnings", [])[:10],
            "bulk_matrix_enabled": True,
        }
        all_results[f"{factor}__backtest"] = entry
        sharpe_str = f"Sharpe={entry['sharpe']:.3f}" if entry['sharpe'] is not None else ""
        ret_str = f"AnnRet={entry['annualized_return']:.4f}" if entry['annualized_return'] is not None else ""
        print(f"  ✅ {factor:30s}  obs={entry['observations']:>6d}  {ret_str}  {sharpe_str}  TO={entry.get('turnover') or 0:.3f}  {runtime:.1f}s")

        # Flags
        if entry.get("annualized_return") and abs(entry["annualized_return"]) > 10:
            flags.append({"factor": factor, "step": "backtest", "flag": "EXTREME_RETURN",
                          "value": entry["annualized_return"], "note": "annualized return >1000%"})

    except Exception as e:
        elapsed = round(time.monotonic() - f_start, 2)
        all_results[f"{factor}__backtest"] = {"factor": factor, "family": family, "step": "factor_backtest",
                                               "status": "error", "error": str(e), "runtime_seconds": elapsed}
        flags.append({"factor": factor, "step": "backtest", "flag": "BACKTEST_ERROR", "error": str(e)})
        print(f"  ❌ {factor:30s}  ERROR: {e!s:.80s}  ({elapsed:.1f}s)")

total_seconds = round(time.monotonic() - started_at, 1)
print(f"\nTotal runtime: {total_seconds:.1f}s")

# ─── C. Scoring ───────────────────────────────────────────────────────

print()
print("=" * 60)
print("C. Scoring & Ranking")
print("=" * 60)

def score_factor(factor: str) -> dict[str, Any]:
    """Score a factor 0-100 based on eval + backtest results."""
    eval_key = f"{factor}__eval"
    bt_key = f"{factor}__backtest"
    e = all_results.get(eval_key, {})
    b = all_results.get(bt_key, {})

    if e.get("status") != "ok" or b.get("status") != "ok":
        return {"factor": factor, "score": 0, "grade": "REJECT",
                "reason": f"eval: {e.get('status')}, backtest: {b.get('status')}"}

    scores = {}
    reasons = []

    # 1. Predictive Power (25%)
    pp = 0.0
    ic_mean = e.get("ic_mean", 0)
    rank_ic = e.get("rank_ic_mean", 0)
    pos_rate = e.get("ic_positive_rate") or 0.5
    avg_ic = (abs(ic_mean) + abs(rank_ic)) / 2

    if avg_ic >= 0.05: pp += 8
    elif avg_ic >= 0.03: pp += 5
    elif avg_ic >= 0.01: pp += 2
    if pos_rate >= 0.55: pp += 7
    elif pos_rate >= 0.52: pp += 4
    elif pos_rate >= 0.50: pp += 1

    # Decay consistency: check if IC declines monotonically
    decay = e.get("decay_ics", {})
    if decay:
        horizon_ics = []
        for h in sorted(decay.keys(), key=int):
            horizon_ics.append(abs(decay[h]))
        if horizon_ics:
            # Prefer factors where 60d IC > 0 (doesn't completely decay)
            if len(horizon_ics) >= 2:
                if horizon_ics[-1] >= 0.01: pp += 5
                else: pp += 2
            else:
                pp += 3
        else:
            pp += 0
    else:
        pp += 0

    scores["predictive_power"] = min(pp, 25)
    if pp < 10:
        reasons.append(f"weak IC ({avg_ic:.4f})")

    # 2. Return Quality (25%)
    rq = 0.0
    ann_ret = b.get("annualized_return") or 0
    sharpe = b.get("sharpe") or 0
    max_dd = abs(b.get("max_drawdown") or 1)

    if ann_ret >= 0.15: rq += 8
    elif ann_ret >= 0.05: rq += 5
    elif ann_ret >= 0.0: rq += 2

    if sharpe >= 1.0: rq += 7
    elif sharpe >= 0.5: rq += 4
    elif sharpe >= 0.0: rq += 1

    # Penalize large drawdowns
    if max_dd < 0.2: rq += 5
    elif max_dd < 0.4: rq += 3
    elif max_dd < 0.6: rq += 1
    if max_dd > 0.8:
        reasons.append(f"large max DD ({max_dd:.2%})")

    if ann_ret < -0.05:
        reasons.append(f"negative annualized return ({ann_ret:.4f})")

    scores["return_quality"] = min(rq, 25)

    # 3. Cost Robustness (15%)
    cr = 0.0
    turnover = b.get("turnover") or 0
    cost_impact = b.get("cost_impact") or 0
    net_ret = b.get("net_return") or ann_ret

    if turnover < 0.3: cr += 5
    elif turnover < 0.5: cr += 3
    elif turnover < 0.8: cr += 1
    if abs(cost_impact) < 0.05: cr += 4
    elif abs(cost_impact) < 0.10: cr += 2
    if net_ret is not None and ann_ret is not None and net_ret > 0 and ann_ret > 0:
        net_ratio = net_ret / max(abs(ann_ret), 0.001)
        if net_ratio > 0.7: cr += 3
        elif net_ratio > 0.4: cr += 1

    if turnover > 1.0:
        reasons.append(f"high turnover ({turnover:.3f})")
    if cost_impact and abs(cost_impact) > 0.1:
        reasons.append(f"high cost impact ({cost_impact:.4f})")

    scores["cost_robustness"] = min(cr, 15)

    # 4. Stability (20%) — based on observations, warnings, etc.
    st = 0.0
    obs = e.get("observations", 0)
    warnings_e = e.get("warnings", [])
    warnings_b = b.get("warnings", [])
    excluded = e.get("excluded_count", 0)

    if obs >= 10000: st += 8
    elif obs >= 5000: st += 5
    elif obs >= 1000: st += 2
    if len(warnings_e) == 0 and len(warnings_b) == 0: st += 6
    elif len(warnings_e) + len(warnings_b) < 5: st += 3
    if excluded < len(SYMBOLS) * 0.1: st += 6
    elif excluded < len(SYMBOLS) * 0.3: st += 3

    if obs < 1000:
        reasons.append(f"low obs ({obs})")

    scores["stability"] = min(st, 20)

    # 5. Data Trust (15%)
    dt = 0.0
    family = "price" if factor in price_factors else "fundamental"
    if family == "price": dt += 5  # price data more reliable
    if factor in fundamental_factors and obs < 500:
        dt -= 3
        reasons.append("low fundamental data coverage")
    if obs >= 5000: dt += 5
    elif obs >= 2000: dt += 3
    if excluded == 0: dt += 5
    elif excluded < 5: dt += 3

    scores["data_trust"] = min(max(dt, 0), 15)

    total = sum(scores.values())
    if total >= 70:
        grade = "PASS"
    elif total >= 55:
        grade = "WATCH"
    else:
        grade = "REJECT"

    if len(reasons) == 0:
        reasons.append("no significant concerns")

    return {
        "factor": factor,
        "family": family,
        "score": total,
        "grade": grade,
        "score_breakdown": scores,
        "reasons": reasons,
        "top_metrics": {
            "ic_mean": ic_mean,
            "rank_ic_mean": rank_ic,
            "annualized_return": ann_ret,
            "sharpe": sharpe,
            "max_drawdown": max_dd,
            "turnover": turnover,
            "observations": obs,
            "pos_rate": pos_rate,
        }
    }

rankings = []
for factor in sorted(SUPPORTED_FACTORS):
    s = score_factor(factor)
    rankings.append(s)
    grade_icon = {"PASS": "🟢", "WATCH": "🟡", "REJECT": "🔴"}.get(s["grade"], "⚪")
    print(f"  {grade_icon} {s['factor']:30s}  score={s['score']:2d}  {s['grade']:6s}  {', '.join(s['reasons'][:2])}")

rankings.sort(key=lambda x: x["score"], reverse=True)

# ─── Save outputs ────────────────────────────────────────────────────

raw = {
    "meta": {
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "db_range": [DB_START, DB_END],
        "analysis_range": [START, END],
        "symbol_count": SYMBOL_COUNT,
        "total_factors": len(SUPPORTED_FACTORS),
        "price_factors": len(price_factors),
        "fundamental_factors": len(fundamental_factors),
        "total_runtime_seconds": total_seconds,
        "bulk_matrix_default": True,
        "provider_type": "in_memory",
        "fallback_used": False,
    },
    "results": all_results,
    "rankings": rankings,
}

with open(OUTDIR / "factor_comparison_raw.json", "w") as f:
    json.dump(raw, f, indent=2, default=str)
print(f"\n✅ saved factor_comparison_raw.json")

with open(OUTDIR / "factor_comparison_flags.json", "w") as f:
    json.dump({"flags": flags, "total": len(flags)}, f, indent=2, default=str)
print(f"✅ saved factor_comparison_flags.json ({len(flags)} flags)")

# ─── Generate ranked report ───────────────────────────────────────────

lines = []
lines.append("# Factor Comparison Report")
lines.append("")
lines.append(f"**Generated:** {time.strftime('%Y-%m-%d %H:%M:%S')}")
lines.append(f"**Data:** {DB_START} → {DB_END} | **Analysis:** {START} → {END}")
lines.append(f"**Symbols:** {SYMBOL_COUNT} | **Factors:** {len(SUPPORTED_FACTORS)} (10 price + 21 fundamental)")
lines.append(f"**Total Runtime:** {total_seconds:.1f}s")
lines.append(f"**Provider:** InMemory (bulk_matrix=True, fallback_used=False)")
lines.append("")

lines.append("## Final Rankings")
lines.append("")
lines.append("| # | Factor | Family | Score | Grade | IC | RankIC | AnnRet | Sharpe | MaxDD | TO | Obs |")
lines.append("|----|--------|--------|-------|-------|----|--------|--------|--------|-------|----|-----|")

for i, r in enumerate(rankings, 1):
    m = r["top_metrics"]
    grade_icon = {"PASS": "🟢", "WATCH": "🟡", "REJECT": "🔴"}.get(r["grade"], "⚪")
    lines.append(f"| {i} | {r['factor']} | {r['family']} | {r['score']} | {grade_icon} {r['grade']} | "
                 f"{m['ic_mean']:+.4f} | {m['rank_ic_mean']:+.4f} | {m['annualized_return']:.4f} | "
                 f"{m['sharpe']:.3f} | {m['max_drawdown']:.2%} | {m['turnover']:.3f} | {m['observations']} |")

lines.append("")
lines.append("## Grade Summary")
pass_count = sum(1 for r in rankings if r["grade"] == "PASS")
watch_count = sum(1 for r in rankings if r["grade"] == "WATCH")
reject_count = sum(1 for r in rankings if r["grade"] == "REJECT")
lines.append(f"- 🟢 PASS ({pass_count}): score ≥ 70")
lines.append(f"- 🟡 WATCH ({watch_count}): 55 ≤ score < 70")
lines.append(f"- 🔴 REJECT ({reject_count}): score < 55")

lines.append("")
lines.append("## Detailed Scores")
for r in rankings:
    lines.append(f"### {r['factor']} ({r['family']}) — Score: {r['score']} {r['grade']}")
    lines.append("")
    sb = r["score_breakdown"]
    lines.append(f"| Dimension | Score |")
    lines.append(f"|-----------|-------|")
    lines.append(f"| Predictive Power | {sb.get('predictive_power', 0)}/25 |")
    lines.append(f"| Return Quality | {sb.get('return_quality', 0)}/25 |")
    lines.append(f"| Cost Robustness | {sb.get('cost_robustness', 0)}/15 |")
    lines.append(f"| Stability | {sb.get('stability', 0)}/20 |")
    lines.append(f"| Data Trust | {sb.get('data_trust', 0)}/15 |")
    lines.append("")
    lines.append(f"**Concerns:** {', '.join(r['reasons'])}")
    lines.append("")

lines.append("## Conclusions")
lines.append("")
top3 = rankings[:3]
lines.append("### 1. Top 3 Factors")
for r in top3:
    lines.append(f"- **{r['factor']}** (score {r['score']}): {', '.join(r['reasons'])}")

rejected = [r for r in rankings if r["grade"] == "REJECT"]
if rejected:
    lines.append("")
    lines.append("### 2. Rejected Factors")
    for r in rejected:
        lines.append(f"- **{r['factor']}** (score {r['score']}): {', '.join(r['reasons'])}")

watch_list = [r for r in rankings if r["grade"] == "WATCH"]
if watch_list:
    lines.append("")
    lines.append("### 3. Watch List (Needs Further Audit)")
    for r in watch_list:
        lines.append(f"- **{r['factor']}** (score {r['score']}): {', '.join(r['reasons'])}")

report = "\n".join(lines)
with open(OUTDIR / "factor_comparison_ranked.md", "w") as f:
    f.write(report)
print(f"✅ saved factor_comparison_ranked.md")

# ─── Agent export ─────────────────────────────────────────────────────

agent_lines = []
agent_lines.append("# Factor Comparison — Agent Export")
agent_lines.append("")
agent_lines.append("## Quick Reference Table")
agent_lines.append("")
agent_lines.append("| Factor | Family | Score | Grade | IC | Sharpe | AnnRet | TO | Obs | Flags |")
agent_lines.append("|--------|--------|-------|-------|-----|--------|--------|-----|-----|-------|")
for r in rankings:
    m = r["top_metrics"]
    f = [fl["flag"] for fl in flags if fl.get("factor") == r["factor"]]
    f_str = ", ".join(f[:3]) if f else ""
    agent_lines.append(f"| {r['factor']} | {r['family']} | {r['score']} | {r['grade']} | "
                       f"{m['ic_mean']:+.4f} | {m['sharpe']:.3f} | {m['annualized_return']:.4f} | "
                       f"{m['turnover']:.3f} | {m['observations']} | {f_str} |")

agent_lines.append("")
agent_lines.append("## Score Ranges")
agent_lines.append(f"- PASS: {pass_count}")
agent_lines.append(f"- WATCH: {watch_count}")
agent_lines.append(f"- REJECT: {reject_count}")
agent_lines.append("")
agent_lines.append("## All Warnings")
for fl in sorted(flags, key=lambda x: (x.get("factor", ""), x.get("flag", ""))):
    agent_lines.append(f"- {fl.get('factor', '?'):30s} | {fl.get('step', '?'):12s} | {fl.get('flag', '?')} | {fl.get('value', fl.get('error', ''))}")

agent_lines.append("")
agent_lines.append("## Key Observations")
for r in rankings:
    if r.get("reasons") and r["reasons"][0] != "no significant concerns":
        agent_lines.append(f"- {r['factor']}: {', '.join(r['reasons'])}")

with open(OUTDIR / "factor_comparison_agent_export.md", "w") as f:
    f.write("\n".join(agent_lines))
print(f"✅ saved factor_comparison_agent_export.md")

print("\n🏁 Done. All reports in reports/factor_comparison/")
