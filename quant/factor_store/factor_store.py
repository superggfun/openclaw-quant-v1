"""SQLite factor research persistence."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from quant.factor_store.factor_analytics import FactorAnalytics
from quant.storage.sqlite_store import SQLitePriceStore


class FactorStore:
    """Persist factor definitions, values, evaluations, backtests, and stability."""

    def __init__(self, db_path: str | Path, report_dir: str | Path = "reports") -> None:
        self.db_path = Path(db_path)
        self.report_dir = Path(report_dir)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def initialize(self) -> None:
        with self.connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS factor_definitions (
                    factor_name TEXT PRIMARY KEY,
                    category TEXT,
                    description TEXT,
                    higher_is_better INTEGER NOT NULL,
                    fundamental_required INTEGER NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS factor_values (
                    factor_name TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    signal_date TEXT NOT NULL,
                    value REAL,
                    coverage REAL,
                    version TEXT NOT NULL DEFAULT 'v1',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (factor_name, symbol, signal_date, version)
                );

                CREATE TABLE IF NOT EXISTS factor_evaluation_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    factor_name TEXT NOT NULL,
                    ic REAL,
                    rank_ic REAL,
                    icir REAL,
                    ic_count INTEGER,
                    rank_ic_count INTEGER,
                    coverage REAL,
                    missing_pct REAL,
                    warnings TEXT,
                    report_path TEXT,
                    evaluation_date TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS factor_backtest_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    factor_name TEXT NOT NULL,
                    long_short_return REAL,
                    sharpe REAL,
                    drawdown REAL,
                    turnover REAL,
                    coverage REAL,
                    warnings TEXT,
                    report_path TEXT,
                    evaluation_date TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS factor_walk_forward_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    factor_name TEXT NOT NULL,
                    fold TEXT,
                    train_return REAL,
                    test_return REAL,
                    train_sharpe REAL,
                    test_sharpe REAL,
                    warnings TEXT,
                    report_path TEXT,
                    evaluation_date TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS factor_stability_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    factor_name TEXT NOT NULL,
                    stability_score REAL,
                    coverage_score REAL,
                    confidence_score REAL,
                    factor_decay_score REAL,
                    overall_score REAL,
                    timestamp TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS factor_versions (
                    factor_name TEXT NOT NULL,
                    version TEXT NOT NULL,
                    description TEXT,
                    change_reason TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (factor_name, version)
                );
                """
            )

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
            counts = {
                table: connection.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()["count"]
                for table in (
                    "factor_definitions",
                    "factor_values",
                    "factor_evaluation_history",
                    "factor_backtest_history",
                    "factor_walk_forward_history",
                    "factor_stability_history",
                    "factor_versions",
                )
            }
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
                LEFT JOIN factor_evaluation_history e ON e.id = (
                    SELECT id FROM factor_evaluation_history
                    WHERE factor_name = d.factor_name
                    ORDER BY evaluation_date DESC LIMIT 1
                )
                LEFT JOIN factor_backtest_history b ON b.id = (
                    SELECT id FROM factor_backtest_history
                    WHERE factor_name = d.factor_name
                    ORDER BY evaluation_date DESC LIMIT 1
                )
                LEFT JOIN factor_stability_history s ON s.id = (
                    SELECT id FROM factor_stability_history
                    WHERE factor_name = d.factor_name
                    ORDER BY timestamp DESC LIMIT 1
                )
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

    def _with_report_path(self, report: dict, prefix: str, write_report: bool) -> dict:
        if not write_report:
            return report | {"report_path": ""}
        self.report_dir.mkdir(parents=True, exist_ok=True)
        path = self.report_dir / f"{prefix}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
        return report | {"report_path": str(path)}

    @staticmethod
    def _fetch_all(connection: sqlite3.Connection, query: str, params: list[Any]) -> list[dict]:
        rows = connection.execute(query, params).fetchall()
        return [dict(row) for row in rows]

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
