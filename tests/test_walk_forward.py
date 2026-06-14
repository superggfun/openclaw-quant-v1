from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import pytest

from quant.reports.agent_export.agent_exporter import AgentExporter
from quant.cli import main
from quant.engines.walk_forward.fold_runner import factor_stability_worker
from quant.storage.sqlite_store import SQLitePriceStore
from quant.engines.walk_forward.rolling_validation import RollingValidation
from quant.engines.walk_forward.walk_forward import WalkForwardEngine, WalkForwardFold


def seed_walk_forward_prices(db_path: Path, symbols: list[str], days: int = 210) -> None:
    rows = []
    start = date(2023, 1, 1)
    for symbol_index, symbol in enumerate(symbols):
        base = 80 + symbol_index * 9
        slope = 0.05 + symbol_index * 0.03
        for offset in range(days):
            wave = ((offset % (6 + symbol_index)) - 3) * 0.10 * (symbol_index + 1)
            regime = 0.03 * symbol_index if offset > days // 2 else 0.0
            close = base + offset * (slope + regime) + wave
            rows.append(
                {
                    "symbol": symbol,
                    "date": (start + timedelta(days=offset)).isoformat(),
                    "open": close,
                    "high": close * 1.01,
                    "low": close * 0.99,
                    "close": close,
                    "adj_close": close,
                    "volume": 1000 + offset,
                }
            )
    SQLitePriceStore(db_path).upsert_prices(pd.DataFrame(rows))


def test_window_generation() -> None:
    windows = WalkForwardEngine.generate_windows(
        "2020-01-01",
        "2023-12-31",
        train_years=2,
        test_years=1,
    )
    again = WalkForwardEngine.generate_windows(
        "2020-01-01",
        "2023-12-31",
        train_years=2,
        test_years=1,
    )

    assert windows[0]["train_start"] == "2020-01-01"
    assert windows[0]["test_start"] > windows[0]["train_end"]
    assert windows == again
    assert all(window["train_end"] < window["test_start"] for window in windows)
    assert len(windows) >= 1


def test_factor_long_short_fold_generation_and_report(tmp_path: Path) -> None:
    db_path = tmp_path / "quant.db"
    seed_walk_forward_prices(db_path, ["AAA", "BBB", "CCC", "DDD", "EEE"])

    result = WalkForwardEngine(SQLitePriceStore(db_path), report_dir=tmp_path / "reports").run(
        strategy="factor_long_short",
        factor="momentum_20d",
        train_years=0.25,
        test_years=0.08,
        universe=["AAA", "BBB", "CCC", "DDD", "EEE"],
        max_folds=2,
    )

    assert len(result.folds) == 2
    assert result.summary["fold_count"] == 2
    assert result.metadata["no_lookahead"] is True
    assert Path(result.report_path).exists()
    payload = json.loads(Path(result.report_path).read_text(encoding="utf-8"))
    assert {"metadata", "strategy", "parameters", "folds", "summary", "stability_analysis", "warnings", "recommendations"} <= set(payload)
    assert {"fold_id", "train_start", "train_end", "test_start", "test_end", "fold_warnings"} <= set(payload["folds"][0])


def test_alpha_strategy_compatibility(tmp_path: Path) -> None:
    db_path = tmp_path / "quant.db"
    seed_walk_forward_prices(db_path, ["SPY", "QQQ", "AAPL"], days=180)

    result = WalkForwardEngine(SQLitePriceStore(db_path), report_dir=tmp_path / "reports").run(
        strategy="alpha",
        train_years=0.25,
        test_years=0.08,
        universe=["SPY", "QQQ", "AAPL"],
        alpha_config={
            "universe": ["SPY", "QQQ", "AAPL"],
            "top_n": 2,
            "min_cash_weight": 0.1,
            "max_position_weight": 0.5,
        },
        max_folds=1,
    )

    assert result.folds
    assert result.folds[0].no_lookahead is True
    assert result.folds[0].test_report is not None


def test_rolling_validation() -> None:
    result = RollingValidation.analyze(
        {"2024-01-01": 0.01, "2024-01-02": -0.02, "2024-01-03": 0.03},
        {"2024-01-01": 0.1, "2024-01-02": 0.0, "2024-01-03": -0.1},
        {"2024-01-01": 0.2, "2024-01-02": 0.1, "2024-01-03": 0.0},
        window=2,
    )

    assert result["rolling_return"]
    assert result["rolling_ic"]
    assert result["rolling_drawdown"]


def test_lightweight_factor_ic_respects_lower_is_better_direction(tmp_path: Path, monkeypatch) -> None:
    class Row:
        def __init__(self, signal_date: str, symbol: str, factor_value: float, future_return: float) -> None:
            self.signal_date = signal_date
            self.symbol = symbol
            self.factor_value = factor_value
            self.future_return = future_return

    class Matrix:
        valid_rows = [
            Row("2024-01-02", "AAA", 1.0, 0.03),
            Row("2024-01-02", "BBB", 2.0, 0.02),
            Row("2024-01-02", "CCC", 3.0, 0.01),
        ]

    class FakeFactorMatrixBuilder:
        def __init__(self, price_store, factor_registry) -> None:
            pass

        def build(self, **kwargs) -> Matrix:
            return Matrix()

    monkeypatch.setattr("quant.factor_acceleration.FactorMatrixBuilder", FakeFactorMatrixBuilder)

    engine = WalkForwardEngine(SQLitePriceStore(tmp_path / "quant.db"), report_dir=tmp_path / "reports")
    ic, rank_ic = engine._lightweight_factor_ic(
        factor="volatility_20d",
        higher_is_better=False,
        symbols=["AAA", "BBB", "CCC"],
        start="2024-01-01",
        end="2024-01-31",
        forward_days=20,
    )

    assert ic == pytest.approx(1.0)
    assert rank_ic == pytest.approx(1.0)


def test_parallel_factor_stability_worker_respects_lower_is_better_direction(tmp_path: Path, monkeypatch) -> None:
    class Row:
        def __init__(self, signal_date: str, symbol: str, factor_value: float, future_return: float) -> None:
            self.signal_date = signal_date
            self.symbol = symbol
            self.factor_value = factor_value
            self.future_return = future_return

    class Matrix:
        valid_rows = [
            Row("2024-01-02", "AAA", 1.0, 0.03),
            Row("2024-01-02", "BBB", 2.0, 0.02),
            Row("2024-01-02", "CCC", 3.0, 0.01),
        ]

    class FakeFactorMatrixBuilder:
        def __init__(self, price_store, factor_registry) -> None:
            pass

        def build(self, **kwargs) -> Matrix:
            return Matrix()

    monkeypatch.setattr("quant.factor_acceleration.FactorMatrixBuilder", FakeFactorMatrixBuilder)

    factor, window_idx, ic, rank_ic = factor_stability_worker(
        {
            "factor": "volatility_20d",
            "higher_is_better": False,
            "window_idx": 3,
            "symbols": ["AAA", "BBB", "CCC"],
            "start": "2024-01-01",
            "end": "2024-01-31",
            "forward_days": 20,
            "db_path": str(tmp_path / "quant.db"),
        }
    )

    assert factor == "volatility_20d"
    assert window_idx == 3
    assert ic == pytest.approx(1.0)
    assert rank_ic == pytest.approx(1.0)


def test_stability_metrics_keep_directional_and_absolute_scores_separate() -> None:
    metrics = WalkForwardEngine._stability_metrics([-0.08, -0.07], [-0.09, -0.08])

    assert metrics["score"] == metrics["directional_stability_score"]
    assert metrics["directional_stability_score"] < 0
    assert metrics["absolute_stability_score"] > 0.05
    assert metrics["mean_directional_ic"] == pytest.approx(-0.075)
    assert metrics["mean_abs_ic"] == pytest.approx(0.075)
    assert metrics["direction_consistency"] == pytest.approx(0.0)
    assert metrics["classification"] == "unstable"


def test_overfit_and_factor_decay_detection(tmp_path: Path) -> None:
    engine = WalkForwardEngine(SQLitePriceStore(tmp_path / "quant.db"), report_dir=tmp_path / "reports")
    folds = [
        WalkForwardFold(
            fold=1,
            fold_id="fold_001",
            train_start="2020-01-01",
            train_end="2020-12-31",
            test_start="2021-01-01",
            test_end="2021-12-31",
            train_return=0.4,
            test_return=-0.1,
            train_sharpe=2.5,
            test_sharpe=0.1,
            train_max_drawdown=-0.05,
            test_max_drawdown=-0.2,
            ic=0.001,
            rank_ic=0.0,
            icir=0.01,
            turnover=0.5,
            cost=0.0,
            train_report=None,
            test_report=None,
            no_lookahead=True,
            fold_warnings=[],
        )
    ]

    warnings = engine._warnings(folds)
    codes = {warning["code"] for warning in warnings}

    assert "WARN_OVERFIT" in codes
    assert "WARN_FACTOR_DECAY" in codes
    assert "WARN_REGIME_DEPENDENT" in codes


def test_fold_level_metric_interpretation_warnings(tmp_path: Path) -> None:
    fold = WalkForwardFold(
        fold=1,
        fold_id="fold_001",
        train_start="2020-01-01",
        train_end="2020-12-31",
        test_start="2021-01-01",
        test_end="2021-12-31",
        train_return=0.1,
        test_return=2.0,
        train_sharpe=1.0,
        test_sharpe=0.1,
        train_max_drawdown=-0.1,
        test_max_drawdown=-0.5,
        ic=0.1,
        rank_ic=0.1,
        icir=0.2,
        turnover=0.5,
        cost=0.0,
        train_report=None,
        test_report=None,
        no_lookahead=True,
        fold_warnings=[],
    )

    warned = WalkForwardEngine._with_fold_warnings(fold, strategy="factor_long_short")
    codes = {warning["code"] for warning in warned.fold_warnings}

    assert "WARN_COMPOUNDED_RETURN_WEAK_SHARPE" in codes


def test_spread_wipeout_warning(tmp_path: Path) -> None:
    fold = WalkForwardFold(
        fold=1,
        fold_id="fold_001",
        train_start="2020-01-01",
        train_end="2020-12-31",
        test_start="2021-01-01",
        test_end="2021-12-31",
        train_return=0.1,
        test_return=-1.0,
        train_sharpe=1.0,
        test_sharpe=-1.0,
        train_max_drawdown=-0.1,
        test_max_drawdown=-1.0,
        ic=0.1,
        rank_ic=0.1,
        icir=0.2,
        turnover=0.5,
        cost=0.0,
        train_report=None,
        test_report=None,
        no_lookahead=True,
        fold_warnings=[],
    )

    warned = WalkForwardEngine._with_fold_warnings(fold, strategy="factor_long_short")

    assert any(warning["code"] == "WARN_SPREAD_RETURN_WIPEOUT" for warning in warned.fold_warnings)


def test_no_lookahead_fold_dates(tmp_path: Path) -> None:
    db_path = tmp_path / "quant.db"
    seed_walk_forward_prices(db_path, ["AAA", "BBB", "CCC", "DDD", "EEE"])

    result = WalkForwardEngine(SQLitePriceStore(db_path), report_dir=tmp_path / "reports").run(
        strategy="factor_long_short",
        factor="momentum_20d",
        train_years=0.25,
        test_years=0.08,
        universe=["AAA", "BBB", "CCC", "DDD", "EEE"],
        max_folds=1,
    )
    fold = result.folds[0]

    assert fold.train_end < fold.test_start
    assert fold.no_lookahead is True


def test_agent_export_detects_walk_forward() -> None:
    export = AgentExporter().export_report(
        {
            "strategy": "factor_long_short",
            "folds": [],
            "summary": {"fold_count": 0},
            "stability_analysis": {"factor_stability_ranking": [{"factor": "quality_score", "classification": "stable"}]},
            "warnings": [{"code": "WARN_OVERFIT", "reason": "example"}],
        }
    )

    assert export.report_type == "walk_forward"
    assert "quality_score" in export.key_findings[0]


def test_cli_smoke(tmp_path: Path, capsys) -> None:
    db_path = tmp_path / "quant.db"
    seed_walk_forward_prices(db_path, ["AAA", "BBB", "CCC", "DDD", "EEE"])

    exit_code = main(
        [
            "--db-path",
            str(db_path),
            "walk-forward",
            "--strategy",
            "factor_long_short",
            "--factor",
            "momentum_20d",
            "--train-years",
            "0.25",
            "--test-years",
            "0.08",
            "--max-folds",
            "1",
            "--symbols",
            "AAA",
            "BBB",
            "CCC",
            "DDD",
            "EEE",
        ]
    )
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "Walk Forward Summary" in output
    assert "fold_count: 1" in output
