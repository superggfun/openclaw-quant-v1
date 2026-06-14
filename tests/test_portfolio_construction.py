from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from quant.cli import main
from quant.engines.portfolio.portfolio_construction import PortfolioConstructionEngine
from quant.storage.portfolio_store import SQLitePortfolioStore
from quant.storage.sqlite_store import SQLitePriceStore


def seed_prices(db_path: Path, shocks: dict[str, float] | None = None, days: int = 90) -> None:
    shocks = shocks or {}
    rows = []
    for index in range(days):
        for symbol, slope in {"LOW": 0.05, "MID": 0.15, "HIGH": 0.40, "SPY": 0.10, "QQQ": 0.20, "NVDA": 0.35}.items():
            close = 100 + index * slope
            if index % 7 == 0:
                close += shocks.get(symbol, 0.0)
            date_value = pd.Timestamp("2024-01-01") + pd.Timedelta(days=index)
            rows.append(
                {
                    "symbol": symbol,
                    "date": date_value.strftime("%Y-%m-%d"),
                    "open": close,
                    "high": close,
                    "low": close,
                    "close": close,
                    "adj_close": close,
                    "volume": 1000,
                }
            )
    SQLitePriceStore(db_path).upsert_prices(pd.DataFrame(rows))


def engine(db_path: Path, sector_map: dict[str, str] | None = None) -> PortfolioConstructionEngine:
    return PortfolioConstructionEngine(SQLitePriceStore(db_path), report_dir=db_path.parent / "reports", sector_map=sector_map)


def test_equal_weight_sum_to_one_and_cash(tmp_path: Path) -> None:
    db_path = tmp_path / "quant.db"
    seed_prices(db_path)

    result = engine(db_path).construct("equal_weight", ["LOW", "MID", "HIGH"], min_cash_weight=0.10, max_position_weight=0.50)

    assert sum(result.target_weights.values()) == pytest.approx(1.0)
    assert result.target_weights["cash"] == pytest.approx(0.10)
    assert result.target_weights["LOW"] == pytest.approx(0.30)
    assert result.no_lookahead is False


def test_inverse_volatility_lower_vol_gets_higher_weight(tmp_path: Path) -> None:
    db_path = tmp_path / "quant.db"
    seed_prices(db_path, shocks={"HIGH": 8.0, "MID": 2.0})

    result = engine(db_path).construct("inverse_volatility", ["LOW", "MID", "HIGH"], max_position_weight=0.90)

    assert result.target_weights["LOW"] > result.target_weights["MID"] > result.target_weights["HIGH"]


def test_risk_parity_contributions_are_closer_than_equal_when_possible(tmp_path: Path) -> None:
    db_path = tmp_path / "quant.db"
    seed_prices(db_path, shocks={"HIGH": 8.0, "MID": 2.0})
    constructor = engine(db_path)

    equal = constructor.construct("equal_weight", ["LOW", "MID", "HIGH"], max_position_weight=0.90)
    parity = constructor.construct("risk_parity", ["LOW", "MID", "HIGH"], max_position_weight=0.90)

    equal_spread = max(equal.risk_contribution_pct.values()) - min(equal.risk_contribution_pct.values())
    parity_spread = max(parity.risk_contribution_pct.values()) - min(parity.risk_contribution_pct.values())
    assert parity_spread < equal_spread


def test_min_variance_creates_valid_long_only_weights(tmp_path: Path) -> None:
    db_path = tmp_path / "quant.db"
    seed_prices(db_path, shocks={"HIGH": 8.0, "MID": 2.0})

    result = engine(db_path).construct("min_variance", ["LOW", "MID", "HIGH"], max_position_weight=0.90)

    assert sum(result.target_weights.values()) == pytest.approx(1.0)
    assert all(weight >= 0 for weight in result.target_weights.values())
    assert result.target_weights.get("LOW", 0.0) > result.target_weights.get("HIGH", 0.0)


def test_max_position_and_min_cash_respected(tmp_path: Path) -> None:
    db_path = tmp_path / "quant.db"
    seed_prices(db_path)

    result = engine(db_path).construct(
        "equal_weight",
        ["LOW", "MID", "HIGH"],
        min_cash_weight=0.25,
        max_position_weight=0.20,
    )

    assert result.target_weights["cash"] >= 0.25
    assert all(weight <= 0.20 for symbol, weight in result.target_weights.items() if symbol != "cash")


def test_sector_cap_respected(tmp_path: Path) -> None:
    db_path = tmp_path / "quant.db"
    seed_prices(db_path)
    sector_map = {"LOW": "Tech", "MID": "Tech", "HIGH": "Other"}

    result = engine(db_path, sector_map=sector_map).construct(
        "equal_weight",
        ["LOW", "MID", "HIGH"],
        min_cash_weight=0.10,
        max_position_weight=0.50,
        max_sector_weight=0.35,
    )

    assert result.target_weights["LOW"] + result.target_weights["MID"] <= 0.350001
    assert any("scaled Tech sector" in warning for warning in result.warnings)


def test_no_lookahead_end_date_controls_inputs(tmp_path: Path) -> None:
    db_path = tmp_path / "quant.db"
    seed_prices(db_path, shocks={"HIGH": 8.0, "MID": 2.0}, days=100)
    constructor = engine(db_path)

    before = constructor.construct("inverse_volatility", ["LOW", "MID", "HIGH"], end="2024-03-01", max_position_weight=0.90)
    store = SQLitePriceStore(db_path)
    store.upsert_prices(
        pd.DataFrame(
            [
                {
                    "symbol": "LOW",
                    "date": "2024-03-15",
                    "open": 1,
                    "high": 1,
                    "low": 1,
                    "close": 1,
                    "adj_close": 1,
                    "volume": 1000,
                }
            ]
        )
    )
    after = constructor.construct("inverse_volatility", ["LOW", "MID", "HIGH"], end="2024-03-01", max_position_weight=0.90)

    assert before.target_weights == after.target_weights


def test_insufficient_data_exclusion(tmp_path: Path) -> None:
    db_path = tmp_path / "quant.db"
    seed_prices(db_path)
    SQLitePriceStore(db_path).upsert_prices(
        pd.DataFrame(
            [
                {
                    "symbol": "NEW",
                    "date": "2024-01-01",
                    "open": 100,
                    "high": 100,
                    "low": 100,
                    "close": 100,
                    "adj_close": 100,
                    "volume": 1000,
                }
            ]
        )
    )

    result = engine(db_path).construct("equal_weight", ["LOW", "NEW"], max_position_weight=0.90)

    assert "NEW" in result.excluded_symbols
    assert result.exclusion_reasons["NEW"] == "insufficient close history"


def test_one_valid_symbol_only(tmp_path: Path) -> None:
    db_path = tmp_path / "quant.db"
    seed_prices(db_path)

    result = engine(db_path).construct("equal_weight", ["SPY", "MISSING"], max_position_weight=0.90, max_sector_weight=1.0)

    assert result.symbols_used == ["SPY"]
    assert result.excluded_symbols == ["MISSING"]
    assert result.target_weights["SPY"] == pytest.approx(0.90)
    assert result.target_weights["cash"] == pytest.approx(0.10)


def test_all_symbols_invalid_raises_clear_error(tmp_path: Path) -> None:
    db_path = tmp_path / "quant.db"
    SQLitePriceStore(db_path)

    with pytest.raises(ValueError, match="no valid return history"):
        engine(db_path).construct("equal_weight", ["BAD", "MISSING"])


def test_zero_volatility_symbol_is_excluded(tmp_path: Path) -> None:
    db_path = tmp_path / "quant.db"
    seed_prices(db_path)
    rows = []
    for index in range(10):
        date_value = pd.Timestamp("2024-01-01") + pd.Timedelta(days=index)
        rows.append(
            {
                "symbol": "FLAT",
                "date": date_value.strftime("%Y-%m-%d"),
                "open": 100,
                "high": 100,
                "low": 100,
                "close": 100,
                "adj_close": 100,
                "volume": 1000,
            }
        )
    SQLitePriceStore(db_path).upsert_prices(pd.DataFrame(rows))

    result = engine(db_path).construct("inverse_volatility", ["LOW", "FLAT"], max_position_weight=0.90)

    assert "FLAT" in result.excluded_symbols
    assert result.exclusion_reasons["FLAT"] == "zero volatility"
    assert all(weight >= 0 for weight in result.target_weights.values())


def test_target_ordering_is_deterministic(tmp_path: Path) -> None:
    db_path = tmp_path / "quant.db"
    seed_prices(db_path)

    result = engine(db_path).construct("equal_weight", ["HIGH", "LOW", "MID"], max_position_weight=0.90)

    assert list(result.target_weights) == ["HIGH", "LOW", "MID", "cash"]


def test_risk_parity_fallback_warning(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    db_path = tmp_path / "quant.db"
    seed_prices(db_path)
    constructor = engine(db_path)

    monkeypatch.setattr(constructor, "_risk_contributions", lambda weights, covariance: (None, {}, {}, {}))
    result = constructor.construct("risk_parity", ["LOW", "MID", "HIGH"], max_position_weight=0.90)

    assert sum(result.target_weights.values()) == pytest.approx(1.0)
    assert any("risk parity fell back" in warning for warning in result.warnings)


def test_min_variance_fallback_warning(tmp_path: Path) -> None:
    db_path = tmp_path / "quant.db"
    seed_prices(db_path)
    constructor = engine(db_path)
    warnings: list[str] = []
    covariance = pd.DataFrame([[float("nan")]], index=["LOW"], columns=["LOW"])

    weights = constructor._min_variance(["LOW"], covariance, 0.10, warnings)

    assert weights == {"LOW": pytest.approx(0.90)}
    assert any("min_variance fell back" in warning for warning in warnings)


def test_output_targets_compatible_with_rebalance(tmp_path: Path) -> None:
    db_path = tmp_path / "quant.db"
    seed_prices(db_path)
    store = SQLitePortfolioStore(db_path)
    store.init_account(cash=100000)
    output_path = tmp_path / "targets.json"

    result = engine(db_path).construct("equal_weight", ["SPY", "QQQ", "NVDA"], output_targets=output_path)
    targets = json.loads(output_path.read_text(encoding="utf-8"))
    exit_code = main(["--db-path", str(db_path), "rebalance", "--targets", str(output_path)])

    assert exit_code == 0
    assert targets == result.target_weights


def test_report_schema_includes_risk_fields(tmp_path: Path) -> None:
    db_path = tmp_path / "quant.db"
    seed_prices(db_path)

    result = engine(db_path).construct("risk_parity", ["LOW", "MID", "HIGH"], max_position_weight=0.90)
    report = json.loads(Path(result.report_path).read_text(encoding="utf-8"))

    assert "covariance_matrix" in report
    assert "input_symbols" in report
    assert "selected_symbols" in report
    assert "covariance_window" in report
    assert "volatility_by_symbol" in report
    assert "covariance_matrix_metadata" in report
    assert "expected_portfolio_volatility" in report
    assert "correlation_matrix" in report
    assert "marginal_risk_contributions" in report
    assert "risk_contribution_by_symbol" in report
    assert "risk_contributions" in report
    assert "risk_contribution_pct_by_symbol" in report
    assert "risk_contribution_pct" in report
    assert "interpretation_notes" in report


def test_portfolio_construct_cli_smoke(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    db_path = tmp_path / "quant.db"
    seed_prices(db_path)
    output_path = tmp_path / "targets.json"

    exit_code = main(
        [
            "--db-path",
            str(db_path),
            "portfolio-construct",
            "--method",
            "equal_weight",
            "--symbols",
            "SPY",
            "QQQ",
            "NVDA",
            "--output-targets",
            str(output_path),
        ]
    )
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "Portfolio Construction Summary" in output
    assert output_path.exists()


def test_portfolio_construct_cli_uses_default_symbols(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    db_path = tmp_path / "quant.db"
    seed_prices(db_path)

    exit_code = main(["--db-path", str(db_path), "portfolio-construct", "--method", "equal_weight"])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "Portfolio Construction Summary" in output
    assert "SPY" in output
