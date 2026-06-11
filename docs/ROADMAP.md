# Roadmap

## v0.1.0-data-portfolio

- Market data ingestion with `yfinance`.
- SQLite price storage.
- Idempotent incremental price updates.
- Simulated account state.
- Simulated positions and trades.
- CLI and pytest coverage.

## v0.2.0-backtest-engine

- SMA crossover backtest engine.
- Backtests read from the existing `prices` table.
- Configurable symbol, date range, initial cash, SMA windows, and commission.
- JSON reports under `reports/`.
- Backtest tests for normal runs, signals, metrics, invalid inputs, and missing data.

## v0.3.0-rebalance-engine

- Current allocation command.
- Portfolio rebalance engine.
- Target allocation JSON input.
- Integer-share buy and sell suggestions.
- Configurable commission rate.
- JSON rebalance reports under `reports/`.
- Tests for target values, empty accounts, 100% single-symbol targets, multi-symbol rebalances, cash warnings, and commission calculation.

## v0.4.0-risk-engine

- Risk Engine module.
- Single-stock concentration.
- Industry concentration.
- Cash allocation.
- Top 5 holdings concentration.
- 0-100 risk score.
- JSON risk reports under `reports/`.
- CLI command: `python -m quant.cli risk`.
- Tests for metrics, industry aggregation, cash-only accounts, unknown industries, and rebalance allocation integration.

## v0.5.0-portfolio-optimizer

- Portfolio Optimizer module.
- Equal-weight target generation.
- Risk-adjusted target generation from stored price volatility.
- Constrained target generation with position, cash, sector, long-only, and total weight rules.
- Optimized targets written to `examples/optimized_targets.json`.
- JSON optimizer reports under `reports/`.
- CLI command: `python -m quant.cli optimize`.
- Tests for optimizer modes, constraints, rebalance compatibility, and missing price data.

## Next

- Add richer portfolio reporting.
- Add realized PnL tracking.
- Add basic performance metrics.
- Add benchmark and buy-and-hold comparison metrics.
- Add more backtest strategy templates.
- Add Rebalance Engine constraints for minimum trade size, max position size, and cash buffers.
- Add risk checks for max position size, cash usage, and symbol allowlists.
- Add configurable industry maps and risk score thresholds.
- Add optimizer modes based on expected returns, volatility budgets, and drawdown constraints.
- Add CSV export for prices, trades, allocation snapshots, and rebalance plans.

## Later

- Strategy research interfaces.
- OpenClaw-facing API boundary.
- Configurable universes and data ranges.
- Scheduled local data refresh.
- More robust market calendar handling.

## Out of Scope Until Explicitly Designed

- Broker integration.
- Live trading.
- Automated order execution.
- AI decision execution.
- Credential storage.
