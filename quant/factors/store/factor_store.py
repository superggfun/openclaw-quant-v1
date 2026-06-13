"""SQLite factor research persistence."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from quant.factors.store.factor_analytics import FactorAnalytics
from quant.reports.report_io import generate_report_path, write_json_report
from quant.storage.sqlite_connection import connect_sqlite
from quant.storage.sqlite_store import SQLitePriceStore


FACTOR_STORE_SCHEMA_PATH = Path(__file__).resolve().parent / "sql" / "factor_store_schema.sql"
FACTOR_STORE_TABLES = (
    "factor_definitions",
    "factor_values",
    "factor_evaluation_history",
    "factor_backtest_history",
    "factor_walk_forward_history",
    "factor_stability_history",
    "factor_versions",
    "factor_regime_history",
)


class FactorStore:
    """Persist factor definitions, values, evaluations, backtests, and stability."""

    def __init__(self, db_path: str | Path, report_dir: str | Path = "reports") -> None:
        self.db_path = Path(db_path)
        self.report_dir = Path(report_dir)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    def connect(self) -> sqlite3.Connection:
        return connect_sqlite(self.db_path)

    def initialize(self) -> None:
        with self.connect() as connection:
            connection.executescript(FACTOR_STORE_SCHEMA_PATH.read_text(encoding="utf-8"))

    def upsert_factor_definition(
        self,
        factor_name: str,
        category: str,
        description: str,
        higher_is_better: bool,
        fundamental_required: bool,
    ) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO factor_definitions (
                    factor_name, category, description, higher_is_better, fundamental_required
                )
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(factor_name) DO UPDATE SET
                    category = excluded.category,
                    description = excluded.description,
                    higher_is_better = excluded.higher_is_better,
                    fundamental_required = excluded.fundamental_required,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    factor_name,
                    category,
                    description,
                    int(bool(higher_is_better)),
                    int(bool(fundamental_required)),
                ),
            )

    def upsert_factor_version(self, factor_name: str, version: str, description: str, change_reason: str) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO factor_versions (factor_name, version, description, change_reason)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(factor_name, version) DO UPDATE SET
                    description = excluded.description,
                    change_reason = excluded.change_reason
                """,
                (factor_name, version, description, change_reason),
            )

    def save_factor_evaluation(self, result, version: str = "v1") -> dict:
        self.upsert_factor_definition(
            result.factor,
            result.factor_category,
            result.factor_description,
            result.factor_higher_is_better,
            bool((result.factor_coverage or {}).get("no_lookahead_filter")),
        )
        self.upsert_factor_version(result.factor, version, result.factor_description, "factor evaluation persistence")
        coverage = self._coverage_pct(result.factor_coverage)
        inserted_values = self._save_factor_values(result.factor, result.observations, coverage, version)
        evaluation_date = self._now()
        warnings = json.dumps(result.warnings, sort_keys=True)
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO factor_evaluation_history (
                    factor_name, ic, rank_ic, icir, ic_count, rank_ic_count,
                    coverage, missing_pct, warnings, report_path, evaluation_date
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    result.factor,
                    result.ic_mean,
                    result.rank_ic_mean,
                    result.icir,
                    result.ic_count,
                    result.rank_ic_count,
                    coverage,
                    self._missing_pct(result.factor_coverage),
                    warnings,
                    result.report_path,
                    evaluation_date,
                ),
            )
        stability = FactorAnalytics.consistency_score([result.ic_mean, result.rank_ic_mean])
        confidence = FactorAnalytics.confidence_score(coverage, stability, result.ic_count)
        decay = FactorAnalytics.decay_score(result.decay)
        overall = FactorAnalytics.health_score(
            {
                "icir": result.icir,
                "coverage": coverage,
                "stability_score": stability,
                "drawdown": None,
            }
        )
        self.save_stability(result.factor, stability, coverage, confidence, decay, overall)
        return {
            "factor": result.factor,
            "saved_factor_values": inserted_values,
            "saved_evaluation_history": 1,
            "coverage": coverage,
            "confidence": confidence,
        }

    def save_factor_evaluations(self, results: list, version: str = "v1") -> list[dict]:
        if not results:
            return []
        self._ensure_column("factor_regime_history", "samples", "INTEGER")
        saved: list[dict] = []
        with self.connect() as connection:
            for result in results:
                self._upsert_factor_definition_connection(
                    connection,
                    result.factor,
                    result.factor_category,
                    result.factor_description,
                    result.factor_higher_is_better,
                    bool((result.factor_coverage or {}).get("no_lookahead_filter")),
                )
                self._upsert_factor_version_connection(
                    connection,
                    result.factor,
                    version,
                    result.factor_description,
                    "factor evaluation persistence",
                )
            value_rows = []
            for result in results:
                coverage = self._coverage_pct(result.factor_coverage)
                value_rows.extend(
                    (
                        result.factor,
                        observation.symbol,
                        observation.signal_date,
                        observation.factor_value,
                        coverage,
                        version,
                    )
                    for observation in result.observations
                )
            before_values = connection.total_changes
            if value_rows:
                connection.executemany(
                    """
                    INSERT INTO factor_values (factor_name, symbol, signal_date, value, coverage, version)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(factor_name, symbol, signal_date, version) DO UPDATE SET
                        value = excluded.value,
                        coverage = excluded.coverage
                    """,
                    value_rows,
                )
            inserted_values_total = connection.total_changes - before_values
            evaluation_rows = []
            stability_rows = []
            for result in results:
                coverage = self._coverage_pct(result.factor_coverage)
                evaluation_rows.append(
                    (
                        result.factor,
                        result.ic_mean,
                        result.rank_ic_mean,
                        result.icir,
                        result.ic_count,
                        result.rank_ic_count,
                        coverage,
                        self._missing_pct(result.factor_coverage),
                        json.dumps(result.warnings, sort_keys=True),
                        result.report_path,
                        self._now(),
                    )
                )
                stability = FactorAnalytics.consistency_score([result.ic_mean, result.rank_ic_mean])
                confidence = FactorAnalytics.confidence_score(coverage, stability, result.ic_count)
                decay = FactorAnalytics.decay_score(result.decay)
                overall = FactorAnalytics.health_score(
                    {
                        "icir": result.icir,
                        "coverage": coverage,
                        "stability_score": stability,
                        "drawdown": None,
                    }
                )
                stability_rows.append((result.factor, stability, coverage, confidence, decay, overall, self._now()))
                saved.append(
                    {
                        "factor": result.factor,
                        "saved_factor_values": len(result.observations),
                        "saved_evaluation_history": 1,
                        "coverage": coverage,
                        "confidence": confidence,
                    }
                )
            connection.executemany(
                """
                INSERT INTO factor_evaluation_history (
                    factor_name, ic, rank_ic, icir, ic_count, rank_ic_count,
                    coverage, missing_pct, warnings, report_path, evaluation_date
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                evaluation_rows,
            )
            connection.executemany(
                """
                INSERT INTO factor_stability_history (
                    factor_name, stability_score, coverage_score, confidence_score,
                    factor_decay_score, overall_score, timestamp
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                stability_rows,
            )
        if saved:
            scale = inserted_values_total / max(sum(row["saved_factor_values"] for row in saved), 1)
            for row in saved:
                row["saved_factor_values"] = int(round(row["saved_factor_values"] * scale))
        return saved

    def save_factor_backtest(self, result, version: str = "v1") -> dict:
        self.upsert_factor_definition(
            result.factor,
            result.factor_category,
            result.factor_description,
            result.factor_higher_is_better,
            bool(result.factor_coverage),
        )
        self.upsert_factor_version(result.factor, version, result.factor_description, "factor backtest persistence")
        coverage = self._coverage_pct(result.factor_coverage)
        evaluation_date = self._now()
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO factor_backtest_history (
                    factor_name, long_short_return, sharpe, drawdown, turnover,
                    coverage, warnings, report_path, evaluation_date
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    result.factor,
                    result.long_short_return,
                    result.long_short_sharpe,
                    result.max_drawdown,
                    result.turnover,
                    coverage,
                    json.dumps(result.warnings, sort_keys=True),
                    result.report_path,
                    evaluation_date,
                ),
            )
        stability = FactorAnalytics.consistency_score([result.ic_mean, result.rank_ic_mean, result.long_short_return])
        confidence = FactorAnalytics.confidence_score(coverage, stability, result.ic_count)
        overall = FactorAnalytics.health_score(
            {
                "icir": result.icir,
                "coverage": coverage,
                "stability_score": stability,
                "drawdown": result.max_drawdown,
            }
        )
        self.save_stability(result.factor, stability, coverage, confidence, None, overall)
        return {
            "factor": result.factor,
            "saved_backtest_history": 1,
            "coverage": coverage,
            "confidence": confidence,
        }

    def save_factor_backtests(self, results: list, version: str = "v1") -> list[dict]:
        if not results:
            return []
        saved: list[dict] = []
        with self.connect() as connection:
            for result in results:
                self._upsert_factor_definition_connection(
                    connection,
                    result.factor,
                    result.factor_category,
                    result.factor_description,
                    result.factor_higher_is_better,
                    bool(result.factor_coverage),
                )
                self._upsert_factor_version_connection(
                    connection,
                    result.factor,
                    version,
                    result.factor_description,
                    "factor backtest persistence",
                )
            backtest_rows = []
            stability_rows = []
            for result in results:
                coverage = self._coverage_pct(result.factor_coverage)
                backtest_rows.append(
                    (
                        result.factor,
                        result.long_short_return,
                        result.long_short_sharpe,
                        result.max_drawdown,
                        result.turnover,
                        coverage,
                        json.dumps(result.warnings, sort_keys=True),
                        result.report_path,
                        self._now(),
                    )
                )
                stability = FactorAnalytics.consistency_score([result.ic_mean, result.rank_ic_mean, result.long_short_return])
                confidence = FactorAnalytics.confidence_score(coverage, stability, result.ic_count)
                overall = FactorAnalytics.health_score(
                    {
                        "icir": result.icir,
                        "coverage": coverage,
                        "stability_score": stability,
                        "drawdown": result.max_drawdown,
                    }
                )
                stability_rows.append((result.factor, stability, coverage, confidence, None, overall, self._now()))
                saved.append(
                    {
                        "factor": result.factor,
                        "saved_backtest_history": 1,
                        "coverage": coverage,
                        "confidence": confidence,
                    }
                )
            connection.executemany(
                """
                INSERT INTO factor_backtest_history (
                    factor_name, long_short_return, sharpe, drawdown, turnover,
                    coverage, warnings, report_path, evaluation_date
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                backtest_rows,
            )
            connection.executemany(
                """
                INSERT INTO factor_stability_history (
                    factor_name, stability_score, coverage_score, confidence_score,
                    factor_decay_score, overall_score, timestamp
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                stability_rows,
            )
        return saved

    def save_walk_forward(self, result, factor: str | None = None) -> dict:
        factor_name = factor or result.parameters.get("factor") or "alpha"
        evaluation_date = self._now()
        rows = []
        with self.connect() as connection:
            for fold in result.folds:
                rows.append(
                    (
                        factor_name,
                        fold.fold_id,
                        fold.train_return,
                        fold.test_return,
                        fold.train_sharpe,
                        fold.test_sharpe,
                        json.dumps(fold.fold_warnings, sort_keys=True),
                        result.report_path,
                        evaluation_date,
                    )
                )
            connection.executemany(
                """
                INSERT INTO factor_walk_forward_history (
                    factor_name, fold, train_return, test_return, train_sharpe,
                    test_sharpe, warnings, report_path, evaluation_date
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )
        for row in result.stability_analysis.get("factor_stability_ranking", []):
            if not isinstance(row, dict):
                continue
            score = row.get("score")
            self.save_stability(
                row.get("factor") or factor_name,
                score,
                None,
                FactorAnalytics.confidence_score(None, score, row.get("fold_count")),
                None,
                score,
            )
        return {"factor": factor_name, "saved_walk_forward_folds": len(rows)}

    def save_stability(
        self,
        factor_name: str,
        stability_score: float | None,
        coverage_score: float | None,
        confidence_score: float | None,
        factor_decay_score: float | None,
        overall_score: float | None,
    ) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO factor_stability_history (
                    factor_name, stability_score, coverage_score, confidence_score,
                    factor_decay_score, overall_score, timestamp
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    factor_name,
                    stability_score,
                    coverage_score,
                    confidence_score,
                    factor_decay_score,
                    overall_score,
                    self._now(),
                ),
            )

    def summary(self, write_report: bool = True) -> dict:
        with self.connect() as connection:
            counts = self._table_counts(connection, FACTOR_STORE_TABLES)
            factors = [row["factor_name"] for row in connection.execute("SELECT factor_name FROM factor_definitions ORDER BY factor_name").fetchall()]
        warnings = []
        if not counts["factor_values"]:
            warnings.append("WARN_FACTOR_STORE_EMPTY_VALUES")
        report = {
            "metadata": {"report_type": "factor_store_summary", "generated_at": self._now()},
            "table_counts": counts,
            "counts": counts,
            "factors": factors,
            "warnings": warnings,
        }
        return self._with_report_path(report, "factor_store_summary", write_report)

    def factor_history(self, factor: str | None = None, limit: int = 20, write_report: bool = True) -> dict:
        params: list[Any] = []
        where = ""
        if factor:
            where = "WHERE factor_name = ?"
            params.append(factor.strip().lower())
        with self.connect() as connection:
            evaluations = self._fetch_all(
                connection,
                f"SELECT * FROM factor_evaluation_history {where} ORDER BY evaluation_date DESC LIMIT ?",
                params + [limit],
            )
            backtests = self._fetch_all(
                connection,
                f"SELECT * FROM factor_backtest_history {where} ORDER BY evaluation_date DESC LIMIT ?",
                params + [limit],
            )
            walk_forward = self._fetch_all(
                connection,
                f"SELECT * FROM factor_walk_forward_history {where} ORDER BY evaluation_date DESC LIMIT ?",
                params + [limit],
            )
            stability = self._fetch_all(
                connection,
                f"SELECT * FROM factor_stability_history {where} ORDER BY timestamp DESC LIMIT ?",
                params + [limit],
            )
        warnings = []
        if not evaluations and not backtests and not walk_forward and not stability:
            warnings.append("WARN_FACTOR_HISTORY_EMPTY")
        report = {
            "metadata": {"report_type": "factor_history", "generated_at": self._now()},
            "factor": factor,
            "limit": limit,
            "evaluation_history": evaluations,
            "backtest_history": backtests,
            "walk_forward_history": walk_forward,
            "stability_history": stability,
            "warnings": warnings,
        }
        return self._with_report_path(report, "factor_history", write_report)

    def rank_factors(self, limit: int = 10, write_report: bool = True) -> dict:
        with self.connect() as connection:
            rows = self._fetch_all(
                connection,
                """
                WITH latest_eval AS (
                    SELECT *
                    FROM (
                        SELECT e.*,
                               ROW_NUMBER() OVER (
                                   PARTITION BY factor_name
                                   ORDER BY evaluation_date DESC, id DESC
                               ) AS row_rank
                        FROM factor_evaluation_history e
                    )
                    WHERE row_rank = 1
                ),
                latest_backtest AS (
                    SELECT *
                    FROM (
                        SELECT b.*,
                               ROW_NUMBER() OVER (
                                   PARTITION BY factor_name
                                   ORDER BY evaluation_date DESC, id DESC
                               ) AS row_rank
                        FROM factor_backtest_history b
                    )
                    WHERE row_rank = 1
                ),
                latest_stability AS (
                    SELECT *
                    FROM (
                        SELECT s.*,
                               ROW_NUMBER() OVER (
                                   PARTITION BY factor_name
                                   ORDER BY timestamp DESC, id DESC
                               ) AS row_rank
                        FROM factor_stability_history s
                    )
                    WHERE row_rank = 1
                )
                SELECT
                    d.factor_name,
                    d.category,
                    d.description,
                    COALESCE(e.ic, 0.0) AS ic,
                    COALESCE(e.rank_ic, 0.0) AS rank_ic,
                    COALESCE(e.icir, 0.0) AS icir,
                    COALESCE(e.coverage, b.coverage, s.coverage_score, 0.0) AS coverage,
                    COALESCE(s.stability_score, 0.0) AS stability_score,
                    COALESCE(s.confidence_score, 0.0) AS confidence_score,
                    COALESCE(b.long_short_return, 0.0) AS long_short_return,
                    COALESCE(b.sharpe, 0.0) AS sharpe,
                    COALESCE(b.drawdown, 0.0) AS drawdown,
                    COALESCE(b.turnover, 0.0) AS turnover
                FROM factor_definitions d
                LEFT JOIN latest_eval e ON e.factor_name = d.factor_name
                LEFT JOIN latest_backtest b ON b.factor_name = d.factor_name
                LEFT JOIN latest_stability s ON s.factor_name = d.factor_name
                ORDER BY d.factor_name
                """,
                [],
            )
        scored = []
        for row in rows:
            item = dict(row)
            item["health_score"] = FactorAnalytics.health_score(item)
            scored.append(item)
        top = sorted(scored, key=lambda row: (row["health_score"], row["factor_name"]), reverse=True)[:limit]
        worst = sorted(scored, key=lambda row: (row["health_score"], row["factor_name"]))[:limit]
        most_stable = sorted(scored, key=lambda row: (row["stability_score"], row["factor_name"]), reverse=True)[:limit]
        most_unstable = sorted(scored, key=lambda row: (row["stability_score"], row["factor_name"]))[:limit]
        warnings = []
        if not scored:
            warnings.append("WARN_FACTOR_RANK_EMPTY")
        report = {
            "metadata": {"report_type": "factor_rank", "generated_at": self._now()},
            "limit": limit,
            "top_factors": top,
            "worst_factors": worst,
            "most_stable_factors": most_stable,
            "most_unstable_factors": most_unstable,
            "methodology": "health_score blends ICIR, coverage, stability, and drawdown diagnostics",
            "warnings": warnings,
        }
        return self._with_report_path(report, "factor_rank", write_report)

    def save_factor_regime_history(
        self,
        factor_name: str,
        rows: list[dict],
        report_path: str = "",
    ) -> dict:
        if not rows:
            return {"factor": factor_name, "saved_regime_rows": 0}
        self._ensure_column("factor_regime_history", "samples", "INTEGER")
        evaluation_date = self._now()
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
        with self.connect() as connection:
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

    def save_factor_regime_history_many(self, items: list[tuple[str, list[dict], str]]) -> dict:
        if not items:
            return {"saved_regime_rows": 0, "factors": []}
        self._ensure_column("factor_regime_history", "samples", "INTEGER")
        evaluation_date = self._now()
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
        with self.connect() as connection:
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

    def factor_regime_rank(self, limit: int = 10) -> dict:
        self._ensure_column("factor_regime_history", "samples", "INTEGER")
        with self.connect() as connection:
            rows = self._fetch_all(
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
            "metadata": {"report_type": "regime_rank", "generated_at": self._now()},
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

    def _save_factor_values(self, factor: str, observations: list, coverage: float | None, version: str) -> int:
        rows = [
            (
                factor,
                observation.symbol,
                observation.signal_date,
                observation.factor_value,
                coverage,
                version,
            )
            for observation in observations
        ]
        if not rows:
            return 0
        with self.connect() as connection:
            before = connection.total_changes
            connection.executemany(
                """
                INSERT INTO factor_values (factor_name, symbol, signal_date, value, coverage, version)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(factor_name, symbol, signal_date, version) DO UPDATE SET
                    value = excluded.value,
                    coverage = excluded.coverage
                """,
                rows,
            )
            return connection.total_changes - before

    @staticmethod
    def _upsert_factor_definition_connection(
        connection: sqlite3.Connection,
        factor_name: str,
        category: str,
        description: str,
        higher_is_better: bool,
        fundamental_required: bool,
    ) -> None:
        connection.execute(
            """
            INSERT INTO factor_definitions (
                factor_name, category, description, higher_is_better, fundamental_required
            )
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(factor_name) DO UPDATE SET
                category = excluded.category,
                description = excluded.description,
                higher_is_better = excluded.higher_is_better,
                fundamental_required = excluded.fundamental_required,
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                factor_name,
                category,
                description,
                int(bool(higher_is_better)),
                int(bool(fundamental_required)),
            ),
        )

    @staticmethod
    def _upsert_factor_version_connection(
        connection: sqlite3.Connection,
        factor_name: str,
        version: str,
        description: str,
        change_reason: str,
    ) -> None:
        connection.execute(
            """
            INSERT INTO factor_versions (factor_name, version, description, change_reason)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(factor_name, version) DO UPDATE SET
                description = excluded.description,
                change_reason = excluded.change_reason
            """,
            (factor_name, version, description, change_reason),
        )

    def _with_report_path(self, report: dict, prefix: str, write_report: bool) -> dict:
        if not write_report:
            return report | {"report_path": ""}
        path = generate_report_path(self.report_dir, prefix, unique=True)
        write_json_report(path, report, sort_keys=True)
        return report | {"report_path": str(path)}

    @staticmethod
    def _fetch_all(connection: sqlite3.Connection, query: str, params: list[Any]) -> list[dict]:
        rows = connection.execute(query, params).fetchall()
        return [dict(row) for row in rows]

    @staticmethod
    def _table_counts(connection: sqlite3.Connection, tables: tuple[str, ...]) -> dict[str, int]:
        query = "\nUNION ALL\n".join(
            f"SELECT '{table}' AS table_name, COUNT(*) AS count FROM {table}"
            for table in tables
        )
        return {
            row["table_name"]: int(row["count"])
            for row in connection.execute(query).fetchall()
        }

    def _ensure_column(self, table: str, column: str, column_type: str) -> None:
        with self.connect() as connection:
            columns = {
                row["name"]
                for row in connection.execute(f"PRAGMA table_info({table})").fetchall()
            }
            if column not in columns:
                connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {column_type}")

    @staticmethod
    def _coverage_pct(coverage: dict | None) -> float | None:
        if not coverage:
            return None
        return coverage.get("coverage_percentage")

    @staticmethod
    def _missing_pct(coverage: dict | None) -> float | None:
        if not coverage:
            return None
        return coverage.get("missing_percentage")

    @staticmethod
    def _now() -> str:
        return datetime.now().isoformat(timespec="seconds")


def ensure_factor_store_for_price_store(price_store: SQLitePriceStore, report_dir: str | Path = "reports") -> FactorStore:
    return FactorStore(price_store.db_path, report_dir=report_dir)
