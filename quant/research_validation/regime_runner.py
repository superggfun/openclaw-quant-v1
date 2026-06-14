"""Extracted regime detection / regime-by-factor runner logic."""

from __future__ import annotations

from bisect import bisect_right
from pathlib import Path
from typing import Any

from quant.factors.store.factor_analytics import FactorAnalytics
from quant.factors.store.factor_store import FactorStore
from quant.engines.regime.regime_analytics import RegimeAnalytics
from quant.engines.regime.regime_history import RegimeHistoryStore


def run_regime_detection(runner, report_dir: str | Path, write_report: bool) -> dict[str, Any]:
    if write_report:
        history_store = RegimeHistoryStore(runner.context.db_path, report_dir=report_dir)
        factor_store = FactorStore(runner.context.db_path, report_dir=report_dir)
        return RegimeAnalytics(runner.context.regime_detector, history_store, factor_store).detect_and_save(write_report=True)
    return runner.context.regime_analytics.detect_and_save(write_report=False)


def factor_regime_rows_from_evaluation(runner, result) -> list[dict]:
    observations = []
    for obs in result.observations:
        regime = regime_for_date(runner, obs.signal_date)
        if not regime:
            continue
        observations.append(
            {
                "regime": regime,
                "signal_date": obs.signal_date,
                "factor_value": obs.factor_value,
                "future_return": obs.future_return,
            }
        )
    return runner.context.regime_analytics._factor_rows(
        result.factor,
        observations,
        value_key="factor_value",
        return_key="future_return",
    )


def factor_regime_rows_from_backtest(runner, result) -> list[dict]:
    observations = []
    for period in result.periods:
        regime = regime_for_date(runner, period.signal_date)
        if not regime:
            continue
        observations.append({"regime": regime, "spread_return": period.long_short_return})
    rows = []
    for regime, items in runner.context.regime_analytics._group(observations).items():
        returns = [runner.context.regime_analytics._num(item.get("spread_return")) for item in items]
        clean = [value for value in returns if value is not None]
        if not clean:
            continue
        mean = sum(clean) / len(clean)
        std = runner.context.regime_analytics._std(clean)
        rows.append(
            {
                "factor_name": result.factor,
                "regime": regime,
                "ic": mean,
                "rank_ic": None,
                "icir": mean / std if std and std > 0 else None,
                "coverage": len(clean) / max(len(result.periods), 1),
                "stability": FactorAnalytics.consistency_score(clean),
                "samples": len(clean),
                "metric_note": "factor_backtest spread-return proxy stored in ic field for regime diagnostics",
            }
        )
    return rows


def regime_for_date(runner, date: str) -> str | None:
    if runner._regime_dates is None or runner._regime_values is None:
        with runner.context.regime_history_store.connect() as connection:
            rows = connection.execute("SELECT date, regime FROM regime_history ORDER BY date").fetchall()
        runner._regime_dates = [row["date"] for row in rows]
        runner._regime_values = [row["regime"] for row in rows]
    index = bisect_right(runner._regime_dates, date) - 1
    if index < 0:
        return None
    return runner._regime_values[index]
