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

## v0.6.0-cost-engine

- Cost Engine module.
- Fixed, linear, and combined cost models.
- Per-trade fixed fee, commission, slippage, total cost, and cost ratio.
- Summary gross trade value, commission, slippage, total cost, and warnings.
- CLI command: `python -m quant.cli cost`.
- Rebalance integration through `--with-costs`.
- Tests for models, slippage, minimum commission, warnings, and rebalance cost output.

## v0.7.0-backtest-engine

- Daily portfolio backtest engine.
- Uses stored historical prices only.
- Integrates optimizer-style targets, rebalance simulation, and Cost Engine estimates.
- Supports monthly, weekly, and daily rebalance frequencies.
- Outputs final value, returns, drawdown, volatility, Sharpe ratio, trade count, turnover, total cost, and cash ratio.
- JSON reports under `reports/`.
- Tests for completion, metrics, costs, reproducibility, and missing data.

## v0.8.0-execution-simulator

- Execution Simulator module.
- Immediate, next-day open, TWAP, and partial-fill simulation modes.
- Rebalance Engine integration for intended trades.
- Cost Engine integration for every simulated fill.
- Outputs intended trades, executed trades, unfilled trades, execution costs, slippage estimate, final cash, final positions, and warnings.
- JSON execution reports under `reports/`.
- CLI command: `python -m quant.cli execute-sim --targets examples/optimized_targets.json`.
- Tests for execution modes, partial fills, and cost accounting.

## v0.9.0-alpha-engine

- Alpha Engine module.
- Momentum, volatility, and risk-adjusted momentum factors.
- Symbol ranking and Top N selection.
- Equal-weight and score-weighted target generation.
- Alpha targets written to `examples/alpha_targets.json` when requested.
- JSON alpha reports under `reports/`.
- CLI command: `python -m quant.cli alpha`.
- Tests for factor generation, target generation, rebalance compatibility, invalid config, and missing price data.

## v1.0.0-backtest-no-lookahead

- Alpha strategy integration in the Backtest Engine.
- Signal generation uses only signal-date and earlier prices.
- Execution occurs on the next available trading date.
- Trade records include signal date, execution date, signal price, execution price, costs, and cash after trade.
- Equity curve records last signal and execution dates.
- Reports include `no_lookahead`, `signal_execution_lag`, `alpha_config`, and excluded symbols per rebalance.
- Legacy simple portfolio modes remain available but are documented as same-day-close smoke modes.

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
- Add benchmark comparisons and richer backtest attribution.
- Add alpha factor normalization, factor blending, and signal stability checks.
- Add richer execution assumptions and market calendar support.
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
