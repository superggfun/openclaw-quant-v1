from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from quant.agent_export.agent_exporter import AgentExporter
from quant.factor_eval.factor_evaluation import FactorEvaluation
from quant.factor_store.factor_store import FactorStore
from quant.regime_detection.market_regime import MarketRegime
from quant.regime_detection.regime_analytics import RegimeAnalytics
from quant.regime_detection.regime_classification import classify_regime
from quant.regime_detection.regime_detector import RegimeDetector
from quant.regime_detection.regime_history import RegimeHistoryStore
from quant.storage.sqlite_store import SQLitePriceStore
from quant.visualization.report_visualizer import ReportVisualizer


def seed_regime_prices(db_path: Path) -> None:
    rows = []
    dates = pd.bdate_range("2022-01-03", periods=320)
    price = 100.0
    for index, date in enumerate(dates):
        if index < 120:
            price *= 1.002
        elif index < 190:
            price *= 0.995
        elif index < 240:
            price *= 1.0 + ((-1) ** index) * 0.025
        else:
            price *= 1.003
        rows.append(
            {
                "symbol": "SPY",
                "date": date.strftime("%Y-%m-%d"),
                "open": price,
                "high": price * 1.01,
                "low": price * 0.99,
                "close": price,
                "adj_close": price,
                "volume": 1000000,
            }
        )
        for symbol, offset in {"QQQ": 1.5, "NVDA": 3.0}.items():
            close = price + offset + index * 0.01
            rows.append(
                {
                    "symbol": symbol,
                    "date": date.strftime("%Y-%m-%d"),
                    "open": close,
                    "high": close * 1.01,
                    "low": close * 0.99,
                    "close": close,
                    "adj_close": close,
                    "volume": 1000000,
                }
            )
    SQLitePriceStore(db_path).upsert_prices(pd.DataFrame(rows))


def test_regime_rule_classification() -> None:
    bull_input = dict(close=120, moving_average=100, volatility=0.15, trend_strength=0.10, drawdown=0, market_return=0.01)
    assert classify_regime(**bull_input) == classify_regime(**bull_input)
    assert classify_regime(**bull_input)[0] == MarketRegime.BULL
    assert classify_regime(close=80, moving_average=100, volatility=0.15, trend_strength=-0.10, drawdown=-0.15, market_return=-0.01)[0] == MarketRegime.BEAR
    assert classify_regime(close=105, moving_average=100, volatility=0.35, trend_strength=0.02, drawdown=-0.05, market_return=0.01)[0] == MarketRegime.HIGH_VOL
    assert classify_regime(close=100, moving_average=100, volatility=0.05, trend_strength=0.01, drawdown=0, market_return=0.0)[0] == MarketRegime.LOW_VOL
    assert classify_regime(close=70, moving_average=100, volatility=0.40, trend_strength=-0.20, drawdown=-0.30, market_return=-0.10)[0] == MarketRegime.CRISIS
    assert classify_regime(close=92, moving_average=100, volatility=0.16, trend_strength=0.08, drawdown=-0.15, market_return=0.02)[0] == MarketRegime.RECOVERY


def test_regime_detection_does_not_use_future_prices_after_end(tmp_path: Path) -> None:
    db_path = tmp_path / "quant.db"
    seed_regime_prices(db_path)
    price_store = SQLitePriceStore(db_path)
    cutoff = "2022-10-03"
    baseline = RegimeDetector(price_store, long_window=60, trend_window=20).detect(end=cutoff)[-1].to_dict()

    future_rows = []
    for date in pd.bdate_range("2022-10-04", periods=30):
        future_rows.append(
            {
                "symbol": "SPY",
                "date": date.strftime("%Y-%m-%d"),
                "open": 1000,
                "high": 1200,
                "low": 800,
                "close": 1000,
                "adj_close": 1000,
                "volume": 1,
            }
        )
    price_store.upsert_prices(pd.DataFrame(future_rows))
    changed_future = RegimeDetector(price_store, long_window=60, trend_window=20).detect(end=cutoff)[-1].to_dict()

    assert baseline == changed_future


def test_regime_history_persistence(tmp_path: Path) -> None:
    db_path = tmp_path / "quant.db"
    seed_regime_prices(db_path)
    price_store = SQLitePriceStore(db_path)
    detector = RegimeDetector(price_store, long_window=60, trend_window=20)
    history = RegimeHistoryStore(db_path, report_dir=tmp_path / "reports")

    observations = detector.detect()
    saved = history.save(observations)

    assert saved == len(observations)
    assert history.latest() is not None
    assert sum(history.counts().values()) == len(observations)


def test_low_sample_warnings_and_confidence_discount(tmp_path: Path) -> None:
    db_path = tmp_path / "quant.db"
    seed_regime_prices(db_path)
    price_store = SQLitePriceStore(db_path)
    detector = RegimeDetector(price_store, long_window=60, trend_window=20)
    history = RegimeHistoryStore(db_path, report_dir=tmp_path / "reports")
    store = FactorStore(db_path, report_dir=tmp_path / "reports")
    analytics = RegimeAnalytics(detector, history, store)
    report = analytics.detect_and_save()

    assert any("WARN_LOW_REGIME_SAMPLE" in warning for warning in report["warnings"])
    low_row = analytics._factor_rows(
        "toy",
        [
            {"regime": "TRENDING", "factor_value": 1.0, "future_return": 0.01},
            {"regime": "TRENDING", "factor_value": 2.0, "future_return": 0.02},
        ],
        value_key="factor_value",
        return_key="future_return",
    )[0]
    assert low_row["stability"] < 1.0
    assert low_row["warnings"]


def test_factor_regime_analytics_and_rank(tmp_path: Path) -> None:
    db_path = tmp_path / "quant.db"
    seed_regime_prices(db_path)
    price_store = SQLitePriceStore(db_path)
    detector = RegimeDetector(price_store, long_window=60, trend_window=20)
    history = RegimeHistoryStore(db_path, report_dir=tmp_path / "reports")
    store = FactorStore(db_path, report_dir=tmp_path / "reports")
    analytics = RegimeAnalytics(detector, history, store)
    analytics.detect_and_save()
    result = FactorEvaluation(price_store, report_dir=tmp_path / "reports").evaluate(
        "momentum_20d",
        forward_days=5,
        universe=["SPY", "QQQ", "NVDA"],
    )

    saved = analytics.save_factor_evaluation_by_regime(result)
    ranking = analytics.regime_rank(limit=5)

    assert saved["saved_regime_rows"] > 0
    assert ranking["best_by_regime"]
    assert ranking["metadata"]["report_type"] == "regime_rank"
    low_sample_rows = [
        row
        for rows in (ranking.get("best_by_regime") or {}).values()
        for row in rows
        if row.get("regime_sample_support", 1.0) < 1.0
    ]
    assert low_sample_rows
    assert low_sample_rows[0]["health_score"] <= low_sample_rows[0]["raw_health_score"]


def test_factor_regime_grouping_uses_signal_date(tmp_path: Path) -> None:
    db_path = tmp_path / "quant.db"
    seed_regime_prices(db_path)
    price_store = SQLitePriceStore(db_path)
    detector = RegimeDetector(price_store, long_window=60, trend_window=20)
    history = RegimeHistoryStore(db_path, report_dir=tmp_path / "reports")
    store = FactorStore(db_path, report_dir=tmp_path / "reports")
    analytics = RegimeAnalytics(detector, history, store)
    observations = detector.detect()
    history.save(observations)
    result = FactorEvaluation(price_store, report_dir=tmp_path / "reports").evaluate(
        "momentum_20d",
        forward_days=20,
        universe=["SPY", "QQQ", "NVDA"],
    )

    rows = analytics.factor_regime_rows_from_evaluation(result)
    signal_regimes = {history.regime_for_date(obs.signal_date) for obs in result.observations}

    assert {row["regime"] for row in rows} <= signal_regimes


def test_regime_agent_export_and_visualization(tmp_path: Path) -> None:
    db_path = tmp_path / "quant.db"
    seed_regime_prices(db_path)
    price_store = SQLitePriceStore(db_path)
    detector = RegimeDetector(price_store, long_window=60, trend_window=20)
    history = RegimeHistoryStore(db_path, report_dir=tmp_path / "reports")
    store = FactorStore(db_path, report_dir=tmp_path / "reports")
    analytics = RegimeAnalytics(detector, history, store)
    report = analytics.detect_and_save()

    export = AgentExporter().export_file(report["report_path"], output_format="json")
    visual = ReportVisualizer(output_dir=tmp_path / "charts").visualize_file(report["report_path"])

    assert json.loads(export)["report_type"] == "regime_detection"
    assert visual.report_type == "regime_detection"
    assert visual.charts
