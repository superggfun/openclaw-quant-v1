"""Regime-specific persistence extracted from FactorStore."""

from __future__ import annotations

from typing import TYPE_CHECKING

from quant.factors.store.factor_analytics import FactorAnalytics
from quant.factors.store.factor_store_sql import ensure_column, fetch_all, now_iso

if TYPE_CHECKING:
    from quant.factors.store.factor_store import FactorStore


def save_factor_regime_history(
    runner: FactorStore,
    factor_name: str,
    rows: list[dict],
    report_path: str = "",
) -> dict:
    """Persist regime evaluation rows for a single factor."""
    if not rows:
        return {"factor": factor_name, "saved_regime_rows": 0}
    evaluation_date = now_iso()
    payload = [
        (
            factor_name,
            row.get("regime"),
            row.get("ic"),
            row.get("rank_ic"),
            row.get("icir"),
            row.get("coverage"),
            row.get("stability"),
            row.get("samples"),
            evaluation_date,
            report_path,
        )
        for row in rows
        if row.get("regime")
    ]
    with runner.connect() as connection:
        ensure_column(connection, "factor_regime_history", "samples", "INTEGER")
        connection.executemany(
            """
            INSERT INTO factor_regime_history (
                factor_name, regime, ic, rank_ic, icir, coverage, stability, samples, evaluation_date, report_path
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            payload,
        )
    return {"factor": factor_name, "saved_regime_rows": len(payload)}


def save_factor_regime_history_many(
    runner: FactorStore,
    items: list[tuple[str, list[dict], str]],
) -> dict:
    """Persist regime evaluation rows for many factors in a single connection."""
    if not items:
        return {"saved_regime_rows": 0, "factors": []}
    evaluation_date = now_iso()
    payload = []
    factors = []
    for factor_name, rows, report_path in items:
        factors.append(factor_name)
        payload.extend(
            (
                factor_name,
                row.get("regime"),
                row.get("ic"),
                row.get("rank_ic"),
                row.get("icir"),
                row.get("coverage"),
                row.get("stability"),
                row.get("samples"),
                evaluation_date,
                report_path,
            )
            for row in rows
            if row.get("regime")
        )
    if not payload:
        return {"saved_regime_rows": 0, "factors": sorted(set(factors))}
    with runner.connect() as connection:
        ensure_column(connection, "factor_regime_history", "samples", "INTEGER")
        connection.executemany(
            """
            INSERT INTO factor_regime_history (
                factor_name, regime, ic, rank_ic, icir, coverage, stability, samples, evaluation_date, report_path
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            payload,
        )
    return {"saved_regime_rows": len(payload), "factors": sorted(set(factors))}


def factor_regime_rank(runner: FactorStore, limit: int = 10) -> dict:
    """Rank factors by health score within each regime using stored history."""
    with runner.connect() as connection:
        ensure_column(connection, "factor_regime_history", "samples", "INTEGER")
        rows = fetch_all(
            connection,
            """
            SELECT factor_name, regime,
                   AVG(ic) AS ic,
                   AVG(rank_ic) AS rank_ic,
                   AVG(icir) AS icir,
                   AVG(coverage) AS coverage,
                   AVG(stability) AS stability,
                   SUM(COALESCE(samples, 0)) AS samples,
                   COUNT(*) AS history_rows
            FROM factor_regime_history
            GROUP BY factor_name, regime
            ORDER BY regime, factor_name
            """,
            [],
        )
    scored = []
    for row in rows:
        item = dict(row)
        support = min(max(float(item.get("samples") or 0.0) / 30.0, 0.0), 1.0)
        item["sample_support"] = round(support, 6)
        item["health_score"] = FactorAnalytics.health_score(
            {
                "icir": item.get("icir"),
                "coverage": item.get("coverage"),
                "stability_score": item.get("stability"),
                "drawdown": None,
            }
        ) * item["sample_support"]
        item["health_score"] = round(item["health_score"], 6)
        scored.append(item)
    by_regime: dict[str, list[dict]] = {}
    for row in scored:
        by_regime.setdefault(row["regime"], []).append(row)
    best = {
        regime: sorted(items, key=lambda item: (item["health_score"], item["factor_name"]), reverse=True)[:limit]
        for regime, items in by_regime.items()
    }
    worst = {
        regime: sorted(items, key=lambda item: (item["health_score"], item["factor_name"]))[:limit]
        for regime, items in by_regime.items()
    }
    stable = sorted(
        scored,
        key=lambda item: (item.get("stability") or 0.0, item["factor_name"]),
        reverse=True,
    )[:limit]
    return {
        "metadata": {"report_type": "regime_rank", "generated_at": now_iso()},
        "best_by_regime": best,
        "worst_by_regime": worst,
        "most_stable_across_regimes": stable,
        "warnings": ([] if scored else ["WARN_REGIME_FACTOR_HISTORY_EMPTY"]) + [
            f"WARN_LOW_REGIME_SAMPLE: {row['regime']} {row['factor_name']} has {row.get('samples', 0)} samples"
            for row in scored
            if (row.get("samples") or 0) < 30
        ],
        "interpretation_notes": [
            "Regime rankings are diagnostics from stored factor/regime history, not return guarantees.",
            "Low coverage and weak stability reduce factor health scores.",
            "Low regime sample counts reduce factor health through sample_support.",
        ],
    }
