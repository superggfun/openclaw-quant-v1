"""Lightweight output modes, scoring, and classification for factor research.

This module provides compact scoring for factor evaluation + backtest results
without generating large reports or Markdown files.
"""

from __future__ import annotations

from enum import Enum
from typing import Any


class OutputMode(str, Enum):
    COMPACT = "compact"
    FULL = "full"
    ARCHIVE = "archive"


class FactorStatus(str, Enum):
    PASS = "PASS"
    WATCH = "WATCH"
    REJECT = "REJECT"
    ERROR = "ERROR"


def score_factor(
    eval_result: dict[str, Any],
    backtest_result: dict[str, Any],
) -> dict[str, Any]:
    """Compute a 0-100 score from factor evaluation + backtest results.

    Scoring weights:
        IC / rank_IC:       30%
        return / Sharpe:    30%
        drawdown / risk:    20%
        turnover / cost:    10%
        data quality:       10%
    """
    score = 0.0
    details: dict[str, Any] = {}

    # ── IC component (30%) ──
    ic_mean = _float_or_none(eval_result.get("ic_mean"))
    icir = _float_or_none(eval_result.get("icir"))
    rank_ic_mean = _float_or_none(eval_result.get("rank_ic_mean"))
    ic_positive_rate = _float_or_none(eval_result.get("ic_positive_rate"))

    ic_score = _ic_component(ic_mean, icir, ic_positive_rate, rank_ic_mean)
    score += ic_score * 0.30
    details["ic_score"] = round(ic_score, 1)

    # ── Return component (30%) ──
    # Use spread metrics (additive, correct for overlapping forward spread)
    cumulative_spread = _float_or_none(backtest_result.get("cumulative_forward_spread"))
    mean_spread = _float_or_none(backtest_result.get("mean_forward_spread"))
    spread_sharpe = _float_or_none(backtest_result.get("spread_sharpe_like") or backtest_result.get("sharpe"))
    ret_score = _return_component(cumulative_spread, mean_spread, spread_sharpe)
    score += ret_score * 0.30
    details["return_score"] = round(ret_score, 1)

    # ── Risk component (20%) ──
    spread_max_dd = _float_or_none(backtest_result.get("spread_max_drawdown"))
    cumulative_spread_val = _float_or_none(backtest_result.get("cumulative_forward_spread"))
    hit_rate = _float_or_none(backtest_result.get("forward_spread_hit_rate") or backtest_result.get("hit_rate"))
    risk_score = _risk_component(spread_max_dd, hit_rate, cumulative_spread_val)
    score += risk_score * 0.20
    details["risk_score"] = round(risk_score, 1)

    # ── Turnover / cost robustness (10%) ──
    turnover = _float_or_none(backtest_result.get("turnover"))
    cost_score = _turnover_component(turnover)
    score += cost_score * 0.10
    details["cost_score"] = round(cost_score, 1)

    # ── Data quality (10%) ──
    obs_count = _int_or_none(eval_result.get("observation_count") or eval_result.get("ic_count"))
    warnings = eval_result.get("warnings", []) or []
    fallback_used = _bool_or_false(
        (eval_result.get("performance_metadata") or {}).get("fallback_used")
    )
    quality_score = _quality_component(obs_count, len(warnings), fallback_used)
    score += quality_score * 0.10
    details["quality_score"] = round(quality_score, 1)

    details["score"] = round(score, 1)

    # ── Classification ──
    status, reason = _classify(score, eval_result, backtest_result)
    details["status"] = status.value
    details["reason"] = reason

    return details


def _ic_component(
    ic_mean: float | None,
    icir: float | None,
    ic_positive_rate: float | None,
    rank_ic_mean: float | None,
) -> float:
    """Score IC component 0-100."""
    score = 0.0
    best_ic = ic_mean
    if rank_ic_mean is not None and (best_ic is None or abs(rank_ic_mean) > abs(best_ic)):
        best_ic = rank_ic_mean

    if best_ic is None:
        return 0.0

    # IC magnitude: 0.04+ gets full marks, 0.01 gets 50
    abs_ic = abs(best_ic)
    score += min(abs_ic / 0.04, 1.0) * 50

    # ICIR: 0.5+ gets full marks
    if icir is not None:
        score += min(icir / 0.5, 1.0) * 30

    # Positive rate: 55%+ gets full marks
    if ic_positive_rate is not None:
        score += min(max(ic_positive_rate - 0.45, 0) / 0.15, 1.0) * 20

    return min(score, 100.0)


def _return_component(
    cumulative_spread: float | None,
    mean_spread: float | None,
    sharpe: float | None,
) -> float:
    """Score return component 0-100 for additive spread returns.

    cumulative_spread is an additive sum of period returns (not compound).
    mean_spread is the mean per-period forward spread.
    """
    score = 0.0

    # Cumulative spread (additive sum over all periods)
    if cumulative_spread is not None:
        if cumulative_spread > 3.0:
            score += 30
        elif cumulative_spread > 1.0:
            score += 20
        elif cumulative_spread > 0.5:
            score += 10
        elif cumulative_spread > 0.1:
            score += 5

    # Mean per-period forward spread
    if mean_spread is not None:
        if mean_spread > 0.02:
            score += 20
        elif mean_spread > 0.01:
            score += 15
        elif mean_spread > 0.005:
            score += 10
        elif mean_spread > 0.001:
            score += 5

    # Sharpe / spread t-stat
    if sharpe is not None:
        if sharpe > 1.5:
            score += 50
        elif sharpe > 1.0:
            score += 40
        elif sharpe > 0.5:
            score += 30
        elif sharpe > 0.2:
            score += 20
        elif sharpe > 0:
            score += 10

    return min(score, 100.0)


def _risk_component(
    spread_max_dd: float | None,
    hit_rate: float | None,
    cumulative_spread: float | None = None,
) -> float:
    """Score risk component 0-100 for additive spread drawdown.

    spread_max_dd is normalized by abs(cumulative_spread) to make it
    comparable across different test lengths and universe sizes.
    """
    score = 50.0  # Start at 50

    if spread_max_dd is not None and cumulative_spread is not None and abs(cumulative_spread) > 0.01:
        # Normalize drawdown relative to cumulative spread
        rel_dd = spread_max_dd / abs(cumulative_spread)
        # 0 = no drawdown (full score), -1.0 = wiped out all gains (0 score)
        dd_clamped = max(-1.0, min(rel_dd, 0.0))
        score += (dd_clamped + 1.0) * 30
    elif spread_max_dd is not None:
        # No cumulative spread available, use raw value with fallback threshold
        dd_clamped = max(-0.5, min(spread_max_dd, 0.0))
        score += (dd_clamped / 0.5 + 1.0) * 30

    if hit_rate is not None:
        # Hit rate: 60%+ = full bonus
        score += min(max(hit_rate - 0.45, 0) / 0.15, 1.0) * 20

    return max(min(score, 100.0), 0.0)


def _turnover_component(turnover: float | None) -> float:
    """Score turnover component 0-100. Lower turnover is better."""
    if turnover is None:
        return 50.0
    # < 20% turnover = full score, > 100% = 0
    clamped = max(0.0, min(turnover, 1.0))
    return (1.0 - clamped) * 100.0


def _quality_component(
    obs_count: int | None,
    warning_count: int,
    fallback_used: bool,
) -> float:
    """Score data quality 0-100."""
    score = 60.0

    # Observation count
    if obs_count is None or obs_count == 0:
        return 0.0
    if obs_count >= 500:
        score += 20
    elif obs_count >= 100:
        score += 10

    # Warnings penalty
    if warning_count > 5:
        score -= 30
    elif warning_count > 2:
        score -= 20
    elif warning_count > 0:
        score -= 10

    # Fallback penalty
    if fallback_used:
        score -= 20

    return max(min(score, 100.0), 0.0)


def _classify(
    score: float,
    eval_result: dict[str, Any],
    backtest_result: dict[str, Any],
) -> tuple[FactorStatus, str]:
    """Classify factor based on score and specific criteria."""
    # Check for major issues first
    warnings = (eval_result.get("warnings") or []) + (backtest_result.get("warnings") or [])
    has_fallback = _bool_or_false(
        (eval_result.get("performance_metadata") or {}).get("fallback_used")
    )
    ic_mean = _float_or_none(eval_result.get("ic_mean"))
    turnover = _float_or_none(backtest_result.get("turnover"))
    obs_count = _int_or_none(eval_result.get("observation_count") or eval_result.get("ic_count"))
    spread_dd = _float_or_none(
        backtest_result.get("spread_max_drawdown") or backtest_result.get("max_drawdown")
    )
    cum_spread = _float_or_none(backtest_result.get("cumulative_forward_spread"))

    # Hard reject: no observations
    if obs_count is not None and obs_count == 0:
        return FactorStatus.ERROR, "no observations"

    # Hard reject: extreme spread drawdown (normalized by cumulative spread)
    if spread_dd is not None and cum_spread is not None and abs(cum_spread) > 0.01:
        rel_dd = spread_dd / abs(cum_spread)
        if rel_dd < -1.0:
            return FactorStatus.REJECT, f"spread drawdown exceeds cumulative spread ({rel_dd:.1%})"

    # Hard reject: near-zero IC
    if ic_mean is not None and abs(ic_mean) < 0.005:
        return FactorStatus.REJECT, f"near-zero IC ({ic_mean:.4f})"

    # Hard reject: extreme turnover
    if turnover is not None and turnover > 2.0:
        return FactorStatus.REJECT, f"excessive turnover ({turnover:.1%})"

    if score >= 70 and not has_fallback:
        return FactorStatus.PASS, f"strong signal (score={int(score)})"
    elif score >= 50:
        msg = "moderate signal"
        if has_fallback:
            msg += ", serial fallback detected"
        return FactorStatus.WATCH, f"{msg} (score={int(score)})"
    else:
        return FactorStatus.REJECT, f"weak signal (score={int(score)})"


def _float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int_or_none(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _bool_or_false(value: Any) -> bool:
    if value is None:
        return False
    try:
        return bool(value)
    except (TypeError, ValueError):
        return False
