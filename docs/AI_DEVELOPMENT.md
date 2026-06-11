# AI Development Guide

This document is the long-lived context entry point for AI assistants working on `openclaw-quant-v1`.

## Current Version

`v0.2.0-backtest-engine`

The project currently includes:

- A market data layer using `yfinance` for US stock and ETF daily OHLCV data.
- SQLite storage for normalized price data.
- A simulated portfolio state module with accounts, positions, and trades.
- A minimal SMA crossover backtest engine that uses stored prices.
- CLI commands for price updates, price inspection, account initialization, simulated buys and sells, portfolio snapshots, trade history, and backtests.

The project intentionally does not include:

- AI trading decisions.
- Automated trading.
- Broker connectivity.
- Live order execution.

## Development Principles

- Keep modules small and explicit.
- Preserve SQLite as the local source of truth until a later migration is intentionally planned.
- Add tests for every state transition and failure path.
- Run `pytest` before starting later development and again before committing.
- Do not introduce live trading or broker integration without a separate design document and risk review.
- Prefer deterministic service tests with temporary SQLite databases.
- Keep CLI behavior backward compatible unless the README and tests are updated together.
- Do not commit `.venv/`, `data/quant.db`, `__pycache__/`, `.pytest_cache/`, generated backtest JSON, or other cache files.
- New features must include both a stable CLI path and pytest coverage.
- LLMs must not directly decide trade quantities. Trade quantities are computed by deterministic code from inputs such as cash, price, risk rules, and configuration.
- Future OpenClaw integrations should call only stable CLI commands or explicitly designed API boundaries.

## Important Files

- `quant/config.py`: project defaults and symbol universe.
- `quant/data_source/yfinance_client.py`: external market data adapter.
- `quant/storage/sqlite_store.py`: price table persistence.
- `quant/storage/portfolio_store.py`: account, position, and trade persistence.
- `quant/services/price_service.py`: price update orchestration.
- `quant/services/portfolio_service.py`: simulated portfolio business rules.
- `quant/services/backtest_service.py`: SMA crossover backtest engine and metrics.
- `quant/cli.py`: command line interface.
- `tests/`: pytest coverage for data and portfolio behavior.

## Recommended Workflow

1. Read `README.md`.
2. Read `docs/ARCHITECTURE.md`.
3. Inspect the relevant service and storage modules.
4. Add or update tests before changing behavior.
5. Run `pytest`.
6. For CLI changes, run a temporary database smoke test with `--db-path /tmp/...`.

## Boundaries

Future work may add backtesting, risk, strategy research, and OpenClaw integration. Those modules should consume data and portfolio state through service boundaries rather than reaching directly into unrelated internals.

Broker APIs, credentials, and live execution must stay out of this repo until explicitly requested and designed.
