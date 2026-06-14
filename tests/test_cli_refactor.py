from __future__ import annotations

import pkgutil
from pathlib import Path

import pandas as pd
import pytest

import quant.cli_commands as cli_commands_package
from quant.cli import COMMAND_HANDLERS, COMMAND_MODULES, SKIPPED_COMMAND_MODULES, build_parser, main
from quant.cli_commands.common import create_context
from quant.storage.sqlite_store import SQLitePriceStore


EXPECTED_COMMANDS = {
    "update-prices",
    "show-prices",
    "list-symbols",
    "universe-list",
    "universe-build",
    "data-refresh",
    "data-coverage",
    "research-readiness",
    "provider-list",
    "provider-health",
    "provider-info",
    "export-for-agent",
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
    "performance-profile",
    "performance-report",
    "performance-summary",
    "hpc-benchmark",
    "detect-regime",
    "regime-history",
    "regime-report",
    "regime-rank",
    "research-validation",
    "research-run",
    "research-status",
    "research-history",
    "research-report",
    "strategy-list",
    "strategy-show",
    "strategy-validate",
    "strategy-run",
    "strategy-gate",
    "strategy-gate-report",
    "stability",
    "alpha",
    "factor-eval",
    "factor-list",
    "factor-pipeline",
    "factor-store-summary",
    "factor-history",
    "factor-rank",
    "fundamental-import",
    "fundamental-show",
    "fundamental-coverage",
    "fundamental-quality",
    "mcp-list-tools",
    "mcp-tool-info",
    "mcp-smoke",
    "factor-backtest",
    "strategy-eval",
    "walk-forward",
    "trade-sim",
    "visualize-report",
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


def test_command_modules_are_auto_discovered() -> None:
    expected_modules = sorted(
        module_info.name
        for module_info in pkgutil.iter_modules(cli_commands_package.__path__)
        if not module_info.ispkg and module_info.name not in SKIPPED_COMMAND_MODULES
    )
    actual_modules = sorted(module.__name__.rsplit(".", 1)[-1] for module in COMMAND_MODULES)

    assert actual_modules == expected_modules


def test_db_path_still_works(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    db_path = tmp_path / "custom.db"

    exit_code = main(["--db-path", str(db_path), "list-symbols"])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "SPY" in output
    assert db_path.exists()


def test_cli_context_initializes_engines_lazily(tmp_path: Path) -> None:
    context = create_context(tmp_path / "quant.db")

    assert set(context.__dict__) == {"db_path"}

    alpha_engine = context.alpha_engine

    assert context.alpha_engine is alpha_engine
    assert "alpha_engine" in context.__dict__
    assert "risk_engine" not in context.__dict__


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
