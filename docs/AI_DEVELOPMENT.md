# AI Development Guide

This document is the long-lived context entry point for AI assistants working on `openclaw-quant-v1`.

## Current Version

`v0.8.0-execution-simulator`

The project currently includes:

- A market data layer using `yfinance` for US stock and ETF daily OHLCV data.
- SQLite storage for normalized price data.
- A simulated portfolio state module with accounts, positions, and trades.
- A minimal SMA crossover backtest engine that uses stored prices.
- A portfolio rebalance engine that calculates allocation drift and suggested trades.
- A risk engine that calculates portfolio concentration, cash exposure, Top 5 holdings exposure, and a 0-100 risk score.
- A portfolio optimizer that generates target allocations for the Rebalance Engine.
- A cost engine that estimates fixed, linear, combined, and slippage costs for suggested trades.
- A deterministic daily portfolio backtest engine that combines stored prices, optimizer targets, rebalance logic, and costs.
- An execution simulator that models intended, executed, and unfilled trades with costs.
- CLI commands for price updates, price inspection, account initialization, simulated buys and sells, portfolio snapshots, trade history, backtests, allocation, rebalance plans, cost estimates, optimization, risk, and execution simulation.

The project intentionally does not include:

- AI trading decisions.
- Automated trading.
- Broker connectivity.
- Live order execution.
- OpenClaw integration.
- Claude, GPT, or other LLM execution paths.

## Development Principles

- Run `pytest` before starting later development and again before committing.
- Keep modules small and explicit.
- Preserve SQLite as the local source of truth until a later migration is intentionally planned.
- Add tests for every state transition and failure path.
- Do not introduce live trading or broker integration without a separate design document and risk review.
- Prefer deterministic service and engine tests with temporary SQLite databases.
- Keep CLI behavior backward compatible unless the README and tests are updated together.
- Do not commit `.venv/`, `data/quant.db`, `__pycache__/`, `.pytest_cache/`, generated reports, or other cache files.
- New features must include both a stable CLI path and pytest coverage.
- LLMs must not directly decide trade quantities. Trade quantities are computed by deterministic code from inputs such as cash, price, risk rules, targets, and configuration.
- Future OpenClaw integrations should call only stable CLI commands or explicitly designed API boundaries.
- Future Risk Engine, OpenClaw, and AI research agents should call the Rebalance Engine rather than duplicate allocation logic.

## Important Files

- `quant/config.py`: project defaults and symbol universe.
- `quant/data_source/yfinance_client.py`: external market data adapter.
- `quant/storage/sqlite_store.py`: price table persistence.
- `quant/storage/portfolio_store.py`: account, position, and trade persistence.
- `quant/services/price_service.py`: price update orchestration.
- `quant/services/portfolio_service.py`: simulated portfolio business rules.
- `quant/services/backtest_service.py`: SMA crossover backtest engine and metrics.
- `quant/backtest/backtest_engine.py`: deterministic daily portfolio backtest engine.
- `quant/rebalance/rebalance_engine.py`: pure allocation and rebalance calculation engine.
- `quant/risk/risk_engine.py`: pure portfolio risk calculation engine.
- `quant/optimizer/optimizer_engine.py`: pure target allocation optimizer.
- `quant/cost/cost_engine.py`: pure transaction cost estimator.
- `quant/execution/execution_engine.py`: pure simulated execution engine.
- `quant/cli.py`: command line interface.
- `tests/`: pytest coverage for data, portfolio, backtest, and rebalance behavior.

## Recommended Workflow

1. Run `pytest`.
2. Read `README.md`.
3. Read `docs/ARCHITECTURE.md`.
4. Inspect the relevant service, engine, and storage modules.
5. Add or update tests before changing behavior.
6. Run `pytest` again.
7. For CLI changes, run a temporary database smoke test with `--db-path /tmp/...`.

## Boundaries

Future work may add strategy research and OpenClaw integration. Those modules should consume data, portfolio state, rebalance plans, risk reports, optimizer targets, cost estimates, and execution simulation reports through service or engine boundaries rather than reaching directly into unrelated internals.

Broker APIs, credentials, live execution, OpenClaw, Claude, GPT, and automatic trading must stay out of this repo until explicitly requested and designed.
