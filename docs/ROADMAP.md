# Roadmap

## v0.1.0-data-portfolio

- Market data ingestion with `yfinance`.
- SQLite price storage.
- Idempotent incremental price updates.
- Simulated account state.
- Simulated positions and trades.
- CLI and pytest coverage.

## Next

- Add richer portfolio reporting.
- Add realized PnL tracking.
- Add basic performance metrics.
- Add backtesting module scaffolding with deterministic test fixtures.
- Add risk checks for max position size, cash usage, and symbol allowlists.
- Add CSV export for prices, trades, and portfolio snapshots.

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

