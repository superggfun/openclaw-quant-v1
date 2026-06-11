# AI Development Guide

This document is the long-lived context entry point for AI assistants working on `openclaw-quant-v1`.

## Current Version

`v0.17.0-data-layer-universe`

The project currently includes:

- A market data layer using `yfinance` for US stock and ETF daily OHLCV data.
- SQLite storage for normalized price data.
- A `yfinance`-based offline data layer for universe management, static metadata, coverage, quality, and readiness diagnostics.
- A simulated portfolio state module with accounts, positions, and trades.
- An alpha engine that calculates deterministic factors and target weights from stored prices.
- A factor pipeline that preprocesses same-date factor cross-sections before alpha generation or evaluation.
- A factor evaluation framework that calculates no-lookahead IC, Rank IC, ICIR, quintile, and decay metrics.
- A long-short factor backtest that checks single-factor return streams without modifying portfolio state.
- A strategy evaluation layer that explains return, risk, drawdown, rolling metrics, and attribution from generated reports.
- A minimal SMA crossover backtest engine that uses stored prices.
- A portfolio rebalance engine that calculates allocation drift and suggested trades.
- A risk engine that calculates portfolio concentration, cash exposure, Top 5 holdings exposure, and a 0-100 risk score.
- A portfolio optimizer that generates target allocations for the Rebalance Engine.
- A portfolio construction layer that generates equal weight, inverse volatility, risk parity, and minimum variance target weights.
- A cost engine that estimates fixed, linear, combined, and slippage costs for suggested trades.
- A deterministic daily portfolio backtest engine that combines stored prices, optimizer targets, rebalance logic, and costs.
- An execution simulator that models intended, executed, and unfilled trades with costs.
- CLI commands for price updates, price inspection, account initialization, simulated buys and sells, portfolio snapshots, trade history, alpha, factor pipeline, factor evaluation, factor backtest, strategy evaluation, backtests, allocation, rebalance plans, cost estimates, optimization, risk, and execution simulation.
- A modular CLI implementation under `quant/cli_commands/`.

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
- Alpha features must avoid lookahead bias: factor calculations may use only rows at or before `as_of_date`, and generated targets are next-trading-day signals.
- Alpha backtest features must keep `signal_date < execution_date`; do not use the same close to create a signal and execute a trade.
- Factor evaluation features must keep factor values and future returns separate: factor values use signal-date-and-earlier data, while returns come from later stored price rows.
- Factor pipeline features must transform one signal-date cross-section at a time and must not read future prices, future returns, or future metadata.
- Factor backtest features must remain no-lookahead and must not be described as Strategy Evaluation or Performance Attribution until those modules are explicitly designed.
- Strategy evaluation features must read or generate supported offline source reports, then explain them without introducing new strategies, modifying portfolio state, or executing trades.
- Strategy evaluation warning codes are research diagnostics. Do not treat them as automatic trade instructions.
- Portfolio construction features must use stored prices only, respect the requested end/as-of date, generate target weights only, and leave rebalance or execution simulation to downstream modules.
- Data layer features must not change factor evaluation or backtest semantics. They should improve metadata, coverage, quality, and readiness only.
- AkShare, Tushare, A-share data, and real-time market data are future provider additions and are not part of v0.17.

## Important Files

- `quant/config.py`: project defaults and symbol universe.
- `quant/data_source/yfinance_client.py`: external market data adapter.
- `quant/data_layer/`: universe, metadata, data quality, coverage, and readiness modules.
- `quant/storage/sqlite_store.py`: price table persistence.
- `quant/storage/portfolio_store.py`: account, position, and trade persistence.
- `quant/services/price_service.py`: price update orchestration.
- `quant/services/portfolio_service.py`: simulated portfolio business rules.
- `quant/services/backtest_service.py`: SMA crossover backtest engine and metrics.
- `quant/alpha/alpha_engine.py`: pure factor and target-weight engine.
- `quant/factor_backtest/factor_backtest.py`: pure long-short factor backtest engine.
- `quant/factor_pipeline/factor_pipeline.py`: pure factor preprocessing pipeline.
- `quant/factor_eval/factor_evaluation.py`: pure no-lookahead factor evaluation framework.
- `quant/strategy_eval/strategy_evaluation.py`: pure strategy explanation and attribution engine.
- `quant/backtest/backtest_engine.py`: deterministic daily portfolio backtest engine.
- `quant/rebalance/rebalance_engine.py`: pure allocation and rebalance calculation engine.
- `quant/risk/risk_engine.py`: pure portfolio risk calculation engine.
- `quant/optimizer/optimizer_engine.py`: pure target allocation optimizer.
- `quant/portfolio_construction/portfolio_construction.py`: pure portfolio construction and risk contribution engine.
- `quant/cost/cost_engine.py`: pure transaction cost estimator.
- `quant/execution/execution_engine.py`: pure simulated execution engine.
- `quant/cli.py`: command line entry point and dispatcher.
- `quant/cli_commands/`: command-specific parser registration and handlers.
- `tests/`: pytest coverage for data, portfolio, alpha, factor pipeline, factor evaluation, factor backtest, strategy evaluation, backtest, rebalance, optimizer, risk, cost, and execution behavior.

## Recommended Workflow

1. Run `pytest`.
2. Read `README.md`.
3. Read `docs/ARCHITECTURE.md`.
4. Inspect the relevant service, engine, and storage modules.
5. Add or update tests before changing behavior.
6. Run `pytest` again.
7. For CLI changes, run a temporary database smoke test with `--db-path /tmp/...`.

## Boundaries

Future work may add strategy research and OpenClaw integration. Those modules should consume data, alpha targets, factor pipeline reports, factor evaluation reports, factor backtest reports, strategy evaluation reports, portfolio state, rebalance plans, risk reports, optimizer targets, cost estimates, and execution simulation reports through service or engine boundaries rather than reaching directly into unrelated internals.

Broker APIs, credentials, live execution, OpenClaw, Claude, GPT, and automatic trading must stay out of this repo until explicitly requested and designed.
