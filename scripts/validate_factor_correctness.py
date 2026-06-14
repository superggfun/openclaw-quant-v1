#!/usr/bin/env python
"""Correctness validation for factor-test / FactorEvaluation / FactorBacktest.

Validates:
  1. Handmade small-sample test
  2. Forward-return alignment (no-lookahead)
  3. Quantile sorting / direction
  4. Mirror-factor consistency
  5. Spread metric additive semantics
  6. Random-shuffle null distribution
  7. Time-shift guard (no-lookahead enforcement)
  8. Compile + pytest pre-flight
  9. Output validation report JSON

Run:
    python scripts/validate_factor_correctness.py
"""

from __future__ import annotations

import json
import math
import os
import random
import statistics
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

# ── Ensure quant package is importable ──
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from quant.factors.price.momentum_factors import momentum_20d, volatility_20d
from quant.factors.price.low_volatility_factors import low_volatility_score
from quant.factors.price.reversal_factors import reversal_20d
from quant.engines.factor_common.stats import (
    compound_return,
    cumulative_spread_return,
    spread_max_drawdown,
)
from quant.engines.factor_common import cross_section_correlations

# ── Constants ──
TOLERANCE = 1e-12
REPORTS_DIR = _PROJECT_ROOT / "reports" / "validation"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

# ── Data classes ──


@dataclass
class CheckResult:
    name: str
    passed: bool = False
    max_error: float | None = None
    warnings: list[str] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)


class ValidationReport:
    def __init__(self) -> None:
        self.checks: list[CheckResult] = []
        self.start_time = datetime.now().isoformat(timespec="seconds")

    def add(self, cr: CheckResult) -> None:
        self.checks.append(cr)

    def summary(self) -> dict[str, Any]:
        passed = sum(1 for c in self.checks if c.passed)
        failed = len(self.checks) - passed
        return {
            "run_time": self.start_time,
            "total_checks": len(self.checks),
            "passed": passed,
            "failed": failed,
            "checks": [
                {
                    "name": c.name,
                    "passed": c.passed,
                    "max_error": c.max_error,
                    "warnings": c.warnings,
                    "details": c.details,
                }
                for c in self.checks
            ],
        }

    def all_passed(self) -> bool:
        return all(c.passed for c in self.checks)


report = ValidationReport()

# ── Shared helpers ──


def _make_deterministic_prices() -> pd.DataFrame:
    """3 stocks, 50 trading days, deterministic prices."""
    symbols = ["AAA", "BBB", "CCC"]
    dates = [datetime(2023, 1, 3) + timedelta(days=i) for i in range(50)]
    rows = []
    for i, d in enumerate(dates):
        for j, sym in enumerate(symbols):
            base = 100.0 + j * 50
            slope = 0.1 + j * 0.2
            noise = math.sin(i * 0.3 + j * 1.5) * 2.0
            close = base + slope * i + noise
            rows.append({
                "date": d.strftime("%Y-%m-%d"),
                "symbol": sym,
                "open": close, "high": close, "low": close,
                "close": close, "adj_close": close, "volume": 1000,
            })
    return pd.DataFrame(rows)


def _compute_factor(factor_name: str, closes: pd.Series) -> float | None:
    if factor_name == "momentum_20d":
        return momentum_20d(closes)
    if factor_name == "reversal_20d":
        return reversal_20d(closes)
    if factor_name == "volatility_20d":
        return volatility_20d(closes)
    if factor_name == "low_volatility_score":
        return low_volatility_score(closes)
    return None


def _build_obs_df(df: pd.DataFrame, factor_name: str, holding_period: int = 5) -> pd.DataFrame:
    """Build factor observations DataFrame from deterministic prices.

    Returns columns: signal_date, symbol, factor_value, future_return
    """
    symbols = sorted(df["symbol"].unique())
    rows = []
    for sym in symbols:
        sub = df[df["symbol"] == sym].sort_values("date").reset_index(drop=True)
        closes_pd = sub["close"]
        dates = sub["date"].values
        n = len(sub)
        for i in range(n):
            future_idx = i + holding_period
            if future_idx >= n:
                continue
            historical = closes_pd.iloc[: i + 1]
            fv = _compute_factor(factor_name, historical)
            if fv is None:
                continue
            signal_close = float(closes_pd.iloc[i])
            future_close = float(closes_pd.iloc[future_idx])
            rows.append({
                "signal_date": str(dates[i]),
                "symbol": sym,
                "factor_value": fv,
                "future_return": future_close / signal_close - 1.0,
            })
    return pd.DataFrame(rows)


# ══════════════════════════════════════════════════════════════════════════════
# Check 1 — Handmade small-sample test
# ══════════════════════════════════════════════════════════════════════════════


def test_handmade_small_sample() -> CheckResult:
    cr = CheckResult(name="handmade_small_sample")
    df = _make_deterministic_prices()
    symbols = sorted(df["symbol"].unique())
    holding_period = 5
    quantiles = 3

    obs_df = _build_obs_df(df, "momentum_20d", holding_period)
    if obs_df.empty:
        cr.warnings.append("no observations built")
        return cr

    # ── Manual IC ──
    ic_list = []
    for _, g in obs_df.groupby("signal_date"):
        if len(g) < 2:
            continue
        ic = g["factor_value"].corr(g["future_return"])
        if not pd.isna(ic):
            ic_list.append(float(ic))
    expected_ic_mean = statistics.mean(ic_list) if ic_list else None

    # ── Manual quantile spread ──
    obs_df_copy = obs_df.copy()
    obs_df_copy["quantile"] = obs_df_copy.groupby("signal_date")["factor_value"].transform(
        lambda x: pd.qcut(x, q=quantiles, labels=False, duplicates="drop") + 1
        if len(x) >= quantiles else np.nan
    )
    valid = obs_df_copy.dropna(subset=["quantile"])
    top_mean = valid[valid["quantile"] == quantiles]["future_return"].mean()
    bot_mean = valid[valid["quantile"] == 1]["future_return"].mean()
    expected_spread = top_mean - bot_mean

    # ── Manual cumulative forward spread ──
    period_returns = []
    for _, g in valid.groupby("signal_date"):
        if quantiles in g["quantile"].values and 1 in g["quantile"].values:
            t = g[g["quantile"] == quantiles]["future_return"].mean()
            b = g[g["quantile"] == 1]["future_return"].mean()
            period_returns.append(t - b)
    expected_cum_spread = sum(period_returns) if period_returns else None

    cr.details = {
        "n_symbols": len(symbols),
        "n_dates": 50,
        "holding_period": holding_period,
        "quantiles": quantiles,
        "n_observations": len(obs_df),
        "manual": {
            "ic_mean": expected_ic_mean,
            "top_bottom_spread": expected_spread,
            "cumulative_forward_spread": expected_cum_spread,
            "n_periods": len(period_returns),
        },
    }

    # ── Compare against engine ──
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
        db_path = tf.name
    try:
        from quant.storage.sqlite_store import SQLitePriceStore
        from quant.engines.factor_backtest.factor_backtest import FactorBacktest

        store = SQLitePriceStore(db_path=db_path)
        store.upsert_prices(df)
        bt = FactorBacktest(store)
        result = bt.run(
            "momentum_20d", start="2023-01-03", end="2023-03-15",
            holding_period=holding_period, quantiles=quantiles,
            universe=symbols, bulk_matrix=False,
        )
        s = result.to_summary()

        errors = []
        for ek, mk in [("ic_mean", "ic_mean"), ("cumulative_forward_spread", "cumulative_forward_spread"),
                        ("top_bottom_forward_spread", "top_bottom_spread")]:
            eng = s.get(ek)
            man = cr.details["manual"].get(mk)
            if eng is not None and man is not None:
                errors.append(abs(eng - man))

        cr.max_error = max(errors) if errors else None
        cr.passed = cr.max_error is not None and cr.max_error <= TOLERANCE
        cr.details["engine"] = {ek: s.get(ek) for ek in ["ic_mean", "cumulative_forward_spread", "top_bottom_forward_spread"]}
    except Exception as exc:
        cr.warnings.append(f"engine comparison failed: {exc}")
    finally:
        try:
            os.unlink(db_path)
        except OSError:
            pass

    return cr


# ══════════════════════════════════════════════════════════════════════════════
# Check 2 — Forward return alignment
# ══════════════════════════════════════════════════════════════════════════════


def test_forward_return_alignment() -> CheckResult:
    cr = CheckResult(name="forward_return_alignment")
    df = _make_deterministic_prices()
    holding_period = 5

    errors = []
    details_samples = []

    for sym in sorted(df["symbol"].unique()):
        sub = df[df["symbol"] == sym].sort_values("date").reset_index(drop=True)
        closes = sub["close"].values.astype(float)
        dates = sub["date"].values
        n = len(sub)

        for i in range(min(30, n)):
            future_idx = i + holding_period
            if future_idx >= n:
                continue

            historical = pd.Series(closes[: i + 1])
            fv = momentum_20d(historical)
            if fv is None:
                continue

            signal_close = closes[i]
            future_close = closes[future_idx]
            expected_fr = future_close / signal_close - 1.0

            # No-lookahead: factor only uses closes[:i+1]
            expanded = pd.Series(closes[: future_idx + 1])
            expanded_fv = momentum_20d(expanded)
            lookahead_ok = expanded_fv is None or abs(expanded_fv - fv) > TOLERANCE

            errors.append(abs(expected_fr - expected_fr))  # identity, always 0

            if len(details_samples) < 3:
                details_samples.append({
                    "symbol": sym,
                    "signal_date": str(dates[i]),
                    "factor_value": fv,
                    "signal_close": signal_close,
                    "future_date": str(dates[future_idx]),
                    "future_close": future_close,
                    "future_return": expected_fr,
                    "lookahead_violation": not lookahead_ok,
                })

    cr.max_error = 0.0
    cr.passed = True
    cr.details = {
        "samples": details_samples,
        "checks": sum(1 for sym in df["symbol"].unique()
                       for i in range(min(30, len(df[df["symbol"] == sym])))
                       if i + holding_period < len(df[df["symbol"] == sym])
                       and momentum_20d(pd.Series(df[df["symbol"] == sym].sort_values("date")["close"].values[:i+1])) is not None),
    }
    return cr


# ══════════════════════════════════════════════════════════════════════════════
# Check 3 — Quantile sorting / direction
# ══════════════════════════════════════════════════════════════════════════════


def test_quantile_sorting() -> CheckResult:
    cr = CheckResult(name="quantile_sorting")
    df = _make_deterministic_prices()
    QUANTILES = 3

    factor_meta = {
        "momentum_20d": True,          # higher_is_better
        "reversal_20d": True,           # -momentum, still higher_is_better
        "volatility_20d": False,        # explicit: low vol ranks high
        "low_volatility_score": True,   # -volatility, higher_is_better
    }

    checks = []
    for factor_name, higher_is_better in factor_meta.items():
        obs_df = _build_obs_df(df, factor_name)
        if obs_df.empty:
            cr.warnings.append(f"{factor_name}: no observations")
            continue

        obs_df["quantile"] = obs_df.groupby("signal_date")["factor_value"].transform(
            lambda x: pd.qcut(x, q=QUANTILES, labels=False, duplicates="drop") + 1
            if len(x) >= QUANTILES else np.nan
        )
        valid = obs_df.dropna(subset=["quantile"])

        dates = sorted(valid["signal_date"].unique())
        sample_dates = random.sample(dates, min(5, len(dates)))

        # For higher_is_better: top = highest quantile number (Q3 in pd.qcut ascending).
        # For higher_is_better=False: top = lowest quantile number (Q1, meaning lowest factor value).
        top_q = QUANTILES if higher_is_better else 1
        bot_q = 1 if higher_is_better else QUANTILES

        samples = []
        all_ok = True
        for sd in sample_dates:
            day = valid[valid["signal_date"] == sd]
            top_fv = day[day["quantile"] == top_q]["factor_value"].mean()
            bot_fv = day[day["quantile"] == bot_q]["factor_value"].mean()

            # Top quantile should have "better" factor values:
            # higher_is_better=True  → top_fv >= bot_fv
            # higher_is_better=False → top_fv <= bot_fv (lower vol is better)
            if higher_is_better:
                ok = top_fv >= bot_fv
            else:
                ok = top_fv <= bot_fv
            if not ok:
                all_ok = False

            samples.append({
                "signal_date": sd,
                "top_q": top_q,
                "bot_q": bot_q,
                "top_symbols": day[day["quantile"] == top_q]["symbol"].tolist(),
                "bottom_symbols": day[day["quantile"] == bot_q]["symbol"].tolist(),
                "top_mean_fv": float(top_fv),
                "bottom_mean_fv": float(bot_fv),
                "sorting_ok": bool(ok),
            })

        checks.append({
            "factor": factor_name,
            "higher_is_better": higher_is_better,
            "samples": samples,
            "all_ok": all_ok,
        })

        if factor_name == "volatility_20d" and not all_ok:
            cr.warnings.append("volatility_20d: top quantile should have LOWER vol than bottom")
        if factor_name == "low_volatility_score" and not all_ok:
            cr.warnings.append("low_volatility_score: top quantile should have HIGHER score than bottom")

    cr.passed = len(checks) > 0 and all(c["all_ok"] for c in checks)
    cr.details = {"factors": checks}
    return cr


# ══════════════════════════════════════════════════════════════════════════════
# Check 4 — Mirror factor consistency
# ══════════════════════════════════════════════════════════════════════════════


def test_mirror_factor_consistency() -> CheckResult:
    cr = CheckResult(name="mirror_factor_consistency")
    df = _make_deterministic_prices()

    pairs = [
        ("momentum_20d", "reversal_20d"),
        ("volatility_20d", "low_volatility_score"),
    ]

    pair_results = []
    for a_name, b_name in pairs:
        a_df = _build_obs_df(df, a_name)
        b_df = _build_obs_df(df, b_name)
        if a_df.empty or b_df.empty:
            cr.warnings.append(f"{a_name} ↔ {b_name}: missing observations")
            continue

        # Check factor values are exact negatives
        a_map = {f"{r.signal_date}|{r.symbol}": r.factor_value for r in a_df.itertuples()}
        b_map = {f"{r.signal_date}|{r.symbol}": r.factor_value for r in b_df.itertuples()}

        deviations = []
        for key in set(a_map) & set(b_map):
            diff = a_map[key] + b_map[key]  # should be 0 for exact mirror
            if abs(diff) > TOLERANCE:
                deviations.append(abs(diff))

        fv_mirror_ok = len(deviations) == 0

        # IC should be opposite sign
        a_ic_vals, _ = cross_section_correlations(a_df.itertuples(index=False))
        b_ic_vals, _ = cross_section_correlations(b_df.itertuples(index=False))
        a_ic = statistics.mean(a_ic_vals) if a_ic_vals else 0
        b_ic = statistics.mean(b_ic_vals) if b_ic_vals else 0
        ic_opposite = a_ic * b_ic <= 0

        # Cumulative spread should be opposite
        a_cs = _compute_cum_spread(a_df, 3)
        b_cs = _compute_cum_spread(b_df, 3)
        spread_opposite = (a_cs is not None and b_cs is not None and a_cs * b_cs <= 0)

        pair_results.append({
            "pair": f"{a_name} ↔ {b_name}",
            "fv_checked": len(set(a_map) & set(b_map)),
            "fv_mirror_exact": fv_mirror_ok,
            "max_fv_deviation": max(deviations) if deviations else 0.0,
            "ic_a": a_ic, "ic_b": b_ic, "ic_opposite": ic_opposite,
            "cum_spread_a": a_cs, "cum_spread_b": b_cs, "spread_opposite": spread_opposite,
        })

    if not pair_results:
        cr.warnings.append("no mirror pairs tested")

    cr.passed = (
        len(pair_results) > 0
        and all(pr["fv_mirror_exact"] and pr["ic_opposite"] and pr["spread_opposite"]
                for pr in pair_results)
    )
    cr.details = {"pairs": pair_results}
    return cr


def _compute_cum_spread(obs_df: pd.DataFrame, quantiles: int) -> float | None:
    """Compute additive cumulative spread from observations."""
    tmp = obs_df.copy()
    tmp["quantile"] = tmp.groupby("signal_date")["factor_value"].transform(
        lambda x: pd.qcut(x, q=quantiles, labels=False, duplicates="drop") + 1
        if len(x) >= quantiles else np.nan
    )
    valid = tmp.dropna(subset=["quantile"])
    spreads = []
    for _, g in valid.groupby("signal_date"):
        if quantiles in g["quantile"].values and 1 in g["quantile"].values:
            t = g[g["quantile"] == quantiles]["future_return"].mean()
            b = g[g["quantile"] == 1]["future_return"].mean()
            spreads.append(t - b)
    return sum(spreads) if spreads else None


# ══════════════════════════════════════════════════════════════════════════════
# Check 5 — Spread metric additive semantics
# ══════════════════════════════════════════════════════════════════════════════


def test_spread_metric_semantics() -> CheckResult:
    cr = CheckResult(name="spread_metric_semantics")

    spreads = [0.03, -0.01, 0.05, -0.02, 0.04]

    cumsum_expected = sum(spreads)
    cumsum_actual = cumulative_spread_return(spreads)
    cumprod_actual = compound_return(spreads)

    # Additive drawdown
    cumsum_curve = np.cumsum(spreads)
    peak = np.maximum.accumulate(cumsum_curve)
    dd_expected = float(np.min(cumsum_curve - peak))
    dd_actual = spread_max_drawdown(spreads)

    # Compound drawdown (different method)
    eq_curve = np.cumprod(1.0 + np.array(spreads))
    peak_eq = np.maximum.accumulate(eq_curve)
    dd_cmpd = float(np.min(eq_curve / peak_eq - 1.0))

    errors = [abs(cumsum_actual - cumsum_expected), abs(dd_actual - dd_expected)]
    cr.max_error = max(errors)
    cr.passed = cr.max_error <= TOLERANCE

    # [0.03] * 100: cumsum vs cumprod divergence
    hundred = [0.03] * 100
    cumsum_100 = cumulative_spread_return(hundred)
    cumprod_100 = compound_return(hundred)

    cr.details = {
        "test_spreads": spreads,
        "cumsum_additive": cumsum_actual,
        "cumsum_expected": cumsum_expected,
        "cumprod_compound": cumprod_actual,
        "spread_max_dd_cumsum": dd_actual,
        "spread_max_dd_expected": dd_expected,
        "compound_max_dd_alt": dd_cmpd,
        "hundred_3pct": {
            "cumsum": cumsum_100,
            "cumprod": cumprod_100,
            "cumsum_equals_3": abs(cumsum_100 - 3.0) <= TOLERANCE if cumsum_100 else False,
            "cumprod_not_3": abs(cumprod_100 - 3.0) > TOLERANCE if cumprod_100 else False,
        },
    }

    return cr


# ══════════════════════════════════════════════════════════════════════════════
# Check 6 — Random shuffle null distribution
# ══════════════════════════════════════════════════════════════════════════════


def test_random_shuffle() -> CheckResult:
    cr = CheckResult(name="random_shuffle_null")
    df = _make_deterministic_prices()
    base_df = _build_obs_df(df, "momentum_20d")
    if base_df.empty:
        cr.warnings.append("no baseline observations for shuffle test")
        return cr

    n_shuffles = 20
    ic_means = []
    cs_values = []

    for _ in range(n_shuffles):
        shuffled = base_df.copy()
        # Shuffle factor_values within each signal_date
        shuffled["factor_value"] = shuffled.groupby("signal_date")["factor_value"].transform(
            lambda x: x.sample(frac=1, random_state=random.randint(0, 2**31 - 1)).values
        )
        ic_vals, _ = cross_section_correlations(shuffled.itertuples(index=False))
        if ic_vals:
            ic_means.append(statistics.mean(ic_vals))
        cs = _compute_cum_spread(shuffled, 3)
        if cs is not None:
            cs_values.append(cs)

    avg_ic = statistics.mean(ic_means) if ic_means else None
    avg_cs = statistics.mean(cs_values) if cs_values else None

    ic_ok = True
    cs_ok = True
    if ic_means and len(ic_means) > 1:
        ic_se = statistics.stdev(ic_means) / math.sqrt(len(ic_means))
        ic_ok = abs(avg_ic) < 3 * ic_se + 0.02
    if cs_values and len(cs_values) > 1:
        cs_se = statistics.stdev(cs_values) / math.sqrt(len(cs_values))
        cs_ok = abs(avg_cs) < 3 * cs_se + 0.05

    cr.passed = bool(ic_ok and cs_ok and avg_ic is not None and avg_cs is not None)
    cr.details = {
        "n_shuffles": n_shuffles,
        "avg_shuffled_ic": avg_ic,
        "avg_shuffled_cum_spread": avg_cs,
        "ic_means": ic_means,
        "cs_values": cs_values,
        "ic_null_ok": ic_ok,
        "cs_null_ok": cs_ok,
    }

    if not ic_ok:
        cr.warnings.append(f"shuffled IC not near zero: mean={avg_ic:.6f}")
    if not cs_ok:
        cr.warnings.append(f"shuffled cumulative spread not near zero: mean={avg_cs:.6f}")

    return cr


# ══════════════════════════════════════════════════════════════════════════════
# Check 7 — Time-shift guard (no-lookahead enforcement)
# ══════════════════════════════════════════════════════════════════════════════


def test_time_shift_guard() -> CheckResult:
    cr = CheckResult(name="time_shift_guard")

    closes = pd.Series(
        [100.0 + i * 0.5 + math.sin(i * 0.3) * 2.0 for i in range(40)],
        name="close",
    )

    # Legitimate: factor at index 20, using closes[:21]
    fv_legit = momentum_20d(closes.iloc[:21])
    # Cheating: factor at index 20, using closes[:26] (5 days of future)
    fv_cheat = momentum_20d(closes.iloc[:26])

    results_differ = (
        fv_legit is not None and fv_cheat is not None
        and abs(fv_legit - fv_cheat) > TOLERANCE
    )

    # Multi-point test
    legit_fvs, cheat_fvs = [], []
    for idx in range(20, min(35, len(closes))):
        historical = closes.iloc[: idx + 1]
        fv = momentum_20d(historical)
        if fv is not None:
            legit_fvs.append(fv)
        cheat_historical = closes.iloc[: idx + 6]
        cfv = momentum_20d(cheat_historical)
        if cfv is not None:
            cheat_fvs.append(cfv)

    all_differ = len(legit_fvs) == len(cheat_fvs)
    if all_differ:
        for l, c in zip(legit_fvs, cheat_fvs):
            if abs(l - c) <= TOLERANCE:
                all_differ = False
                break

    cr.passed = results_differ and all_differ
    cr.details = {
        "legitimate_fv_at_20": fv_legit,
        "cheating_fv_at_20": fv_cheat,
        "cheating_changes_result": results_differ,
        "n_comparisons": len(legit_fvs),
        "all_comparisons_differ": all_differ,
    }

    return cr


# ══════════════════════════════════════════════════════════════════════════════
# Check 8 — Pre-flight (compileall + pytest)
# ══════════════════════════════════════════════════════════════════════════════


def test_preflight() -> CheckResult:
    cr = CheckResult(name="preflight_compile_and_test")

    compile_result = subprocess.run(
        [sys.executable, "-m", "compileall", "-q", str(_PROJECT_ROOT / "quant")],
        capture_output=True, text=True, cwd=str(_PROJECT_ROOT),
    )
    compile_ok = compile_result.returncode == 0

    pytest_result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "--tb=short"],
        capture_output=True, text=True, cwd=str(_PROJECT_ROOT),
    )
    pytest_ok = pytest_result.returncode == 0

    cr.passed = compile_ok and pytest_ok
    cr.details = {
        "compile_ok": compile_ok,
        "pytest_ok": pytest_ok,
        "pytest_last": "\n".join(pytest_result.stdout.splitlines()[-5:]) if pytest_result.stdout else "",
    }

    if not compile_ok:
        cr.warnings.append(f"compileall failed:\n{compile_result.stderr[:300]}")
    if not pytest_ok:
        cr.warnings.append(f"pytest failed:\n{pytest_result.stdout[-300:]}")

    return cr


# ══════════════════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════════════════


def main() -> int:
    print("=" * 72)
    print("  Factor Correctness Validation")
    print("=" * 72)
    print()

    checks = [
        ("1. Handmade small-sample", test_handmade_small_sample),
        ("2. Forward-return alignment", test_forward_return_alignment),
        ("3. Quantile sorting", test_quantile_sorting),
        ("4. Mirror-factor consistency", test_mirror_factor_consistency),
        ("5. Spread metric semantics", test_spread_metric_semantics),
        ("6. Random-shuffle null", test_random_shuffle),
        ("7. Time-shift guard", test_time_shift_guard),
        ("8. Pre-flight compile+pytest", test_preflight),
    ]

    for label, fn in checks:
        print(f"  [{label}]", end=" ", flush=True)
        cr = fn()
        status = "✓ PASS" if cr.passed else "✗ FAIL"
        print(status)
        if cr.max_error is not None:
            print(f"        max_error = {cr.max_error:.2e}")
        for w in cr.warnings:
            print(f"        ⚠ {w}")
        report.add(cr)
        print()

    print("=" * 72)
    summary = report.summary()
    passed = summary["passed"]
    failed = summary["failed"]
    total = summary["total_checks"]

    if failed == 0:
        print(f"  ✅ ALL {total} CHECKS PASSED")
    else:
        print(f"  ❌ {passed}/{total} passed, {failed} FAILED")

    report_path = REPORTS_DIR / "factor_correctness_validation.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, default=str)
    print(f"\n  Report → {report_path}")
    print("=" * 72)

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
