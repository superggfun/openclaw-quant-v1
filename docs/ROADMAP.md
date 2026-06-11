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

## Next

- Add richer portfolio reporting.
- Add realized PnL tracking.
- Add basic performance metrics.
- Add benchmark and buy-and-hold comparison metrics.
- Add more backtest strategy templates.
- Add Rebalance Engine constraints for minimum trade size, max position size, and cash buffers.
- Add risk checks for max position size, cash usage, and symbol allowlists.
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

