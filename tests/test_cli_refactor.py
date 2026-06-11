from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from quant.cli import COMMAND_HANDLERS, build_parser, main
from quant.storage.sqlite_store import SQLitePriceStore


EXPECTED_COMMANDS = {
    "update-prices",
    "show-prices",
    "list-symbols",
    "init-account",
    "buy",
    "sell",
    "portfolio",
    "trades",
    "allocation",
    "rebalance",
    "risk",
    "optimize",
    "portfolio-construct",
    "alpha",
    "factor-eval",
    "factor-pipeline",
    "factor-backtest",
    "strategy-eval",
    "cost",
    "execute-sim",
    "backtest",
}


def seed_prices(db_path: Path) -> None:
    rows = []
    for index in range(90):
        for symbol, slope in {"SPY": 0.1, "QQQ": 0.2, "NVDA": 0.3, "AAPL": 0.4, "MSFT": 0.5}.items():
            close = 100 + index * slope
            rows.append(
                {
                    "symbol": symbol,
                    "date": f"2024-01-{index + 1:02d}" if index < 31 else pd.Timestamp("2024-01-01") + pd.Timedelta(days=index),
                    "open": close,
                    "high": close,
                    "low": close,
                    "close": close,
                    "adj_close": close,
                    "volume": 1000,
                }
            )
    frame = pd.DataFrame(rows)
    frame["date"] = pd.to_datetime(frame["date"]).dt.strftime("%Y-%m-%d")
    SQLitePriceStore(db_path).upsert_prices(frame)


def test_parser_builds_successfully() -> None:
    parser = build_parser()
    args = parser.parse_args(["list-symbols"])

    assert parser.prog == "openclaw-quant"
    assert args.command == "list-symbols"


def test_each_command_is_registered() -> None:
    parser = build_parser()
    subparsers_action = next(action for action in parser._actions if action.dest == "command")

    assert set(subparsers_action.choices) == EXPECTED_COMMANDS
    assert set(COMMAND_HANDLERS) == EXPECTED_COMMANDS


def test_db_path_still_works(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    db_path = tmp_path / "custom.db"

    exit_code = main(["--db-path", str(db_path), "list-symbols"])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "SPY" in output
    assert db_path.exists()


def test_representative_cli_smoke_commands(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    db_path = tmp_path / "quant.db"
    seed_prices(db_path)

    assert main(["--db-path", str(db_path), "show-prices", "SPY", "--limit", "1"]) == 0
    assert "symbol date" in capsys.readouterr().out

    assert main(["--db-path", str(db_path), "factor-eval", "--factor", "momentum_20d", "--forward-days", "1"]) == 0
    assert "Factor Evaluation Summary" in capsys.readouterr().out

    assert main(
        [
            "--db-path",
            str(db_path),
            "factor-backtest",
            "--factor",
            "momentum_20d",
            "--holding-period",
            "1",
        ]
    ) == 0
    assert "Factor Backtest Summary" in capsys.readouterr().out


def test_unknown_command_behavior_unchanged(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["not-a-command"])

    assert exc.value.code == 2
    assert "invalid choice" in capsys.readouterr().err
