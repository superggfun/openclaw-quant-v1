from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from quant.agent_export.agent_exporter import AgentExporter
from quant.factor_eval.factor_evaluation import FactorEvaluation
from quant.factor_store.factor_analytics import FactorAnalytics
from quant.factor_store.factor_registry_store import FactorRegistryStore
from quant.factor_store.factor_store import FactorStore
from quant.storage.sqlite_store import SQLitePriceStore
from quant.visualization.report_visualizer import ReportVisualizer


def seed_factor_prices(db_path: Path) -> None:
    rows = []
    for index, date in enumerate(pd.bdate_range("2024-01-02", periods=90)):
        for symbol, slope in {"SPY": 0.10, "QQQ": 0.15, "NVDA": 0.25}.items():
            close = 100 + index * slope + (index % 7) * 0.1
            rows.append(
                {
                    "symbol": symbol,
                    "date": date.strftime("%Y-%m-%d"),
                    "open": close,
                    "high": close * 1.01,
                    "low": close * 0.99,
                    "close": close,
                    "adj_close": close,
                    "volume": 1000,
                }
            )
    SQLitePriceStore(db_path).upsert_prices(pd.DataFrame(rows))


def test_factor_store_table_creation(tmp_path: Path) -> None:
    store = FactorStore(tmp_path / "quant.db", report_dir=tmp_path / "reports")

    with store.connect() as connection:
        tables = {
            row["name"]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }

    assert {
        "factor_definitions",
        "factor_values",
        "factor_evaluation_history",
        "factor_backtest_history",
        "factor_walk_forward_history",
        "factor_stability_history",
        "factor_versions",
        "factor_regime_history",
    } <= tables


def test_registry_sync_and_version_storage(tmp_path: Path) -> None:
    store = FactorStore(tmp_path / "quant.db", report_dir=tmp_path / "reports")
    count = FactorRegistryStore(store).sync()

    summary = store.summary(write_report=False)

    assert count > 0
    assert summary["counts"]["factor_definitions"] == count
    assert summary["counts"]["factor_versions"] == count


def test_factor_evaluation_persistence_and_history(tmp_path: Path) -> None:
    db_path = tmp_path / "quant.db"
    seed_factor_prices(db_path)
    price_store = SQLitePriceStore(db_path)
    result = FactorEvaluation(price_store, report_dir=tmp_path / "reports").evaluate(
        "momentum_20d",
        forward_days=5,
        universe=["SPY", "QQQ", "NVDA"],
    )
    store = FactorStore(db_path, report_dir=tmp_path / "reports")
    FactorRegistryStore(store).sync()

    saved = store.save_factor_evaluation(result)
    history = store.factor_history("momentum_20d", write_report=False)

    assert saved["saved_factor_values"] > 0
    assert history["evaluation_history"]
    assert history["evaluation_history"][0]["factor_name"] == "momentum_20d"
    assert history["stability_history"]


def test_factor_values_are_idempotent_and_history_appends(tmp_path: Path) -> None:
    db_path = tmp_path / "quant.db"
    seed_factor_prices(db_path)
    price_store = SQLitePriceStore(db_path)
    result = FactorEvaluation(price_store, report_dir=tmp_path / "reports").evaluate(
        "momentum_20d",
        forward_days=5,
        universe=["SPY", "QQQ", "NVDA"],
    )
    store = FactorStore(db_path, report_dir=tmp_path / "reports")

    store.save_factor_evaluation(result)
    store.save_factor_evaluation(result)

    with store.connect() as connection:
        value_count = connection.execute(
            "SELECT COUNT(*) FROM factor_values WHERE factor_name = 'momentum_20d'"
        ).fetchone()[0]
        history_count = connection.execute(
            "SELECT COUNT(*) FROM factor_evaluation_history WHERE factor_name = 'momentum_20d'"
        ).fetchone()[0]
        version_count = connection.execute(
            "SELECT COUNT(*) FROM factor_versions WHERE factor_name = 'momentum_20d'"
        ).fetchone()[0]

    assert value_count == len(result.observations)
    assert history_count == 2
    assert version_count == 1


def test_factor_ranking_and_analytics(tmp_path: Path) -> None:
    db_path = tmp_path / "quant.db"
    seed_factor_prices(db_path)
    price_store = SQLitePriceStore(db_path)
    result = FactorEvaluation(price_store, report_dir=tmp_path / "reports").evaluate(
        "momentum_20d",
        forward_days=5,
        universe=["SPY", "QQQ", "NVDA"],
    )
    store = FactorStore(db_path, report_dir=tmp_path / "reports")
    FactorRegistryStore(store).sync()
    store.save_factor_evaluation(result)

    ranking = store.rank_factors(limit=5, write_report=False)

    assert ranking["top_factors"]
    assert "health_score" in ranking["top_factors"][0]
    assert FactorAnalytics.confidence_score(0.5, 0.5, 10) > 0


def test_factor_reports_agent_export_and_visualization(tmp_path: Path) -> None:
    store = FactorStore(tmp_path / "quant.db", report_dir=tmp_path / "reports")
    FactorRegistryStore(store).sync()
    ranking = store.rank_factors(limit=3)
    report_path = ranking["report_path"]

    export = AgentExporter().export_file(report_path, output_format="json")
    visual = ReportVisualizer(output_dir=tmp_path / "charts").visualize_file(report_path)

    assert json.loads(export)["report_type"] == "factor_rank"
    assert visual.report_type == "factor_rank"
    assert visual.charts
