# Roadmap

## v0.23.0-visualization-reports

- Adds `quant/visualization` for report charts and dashboards.
- Adds `visualize-report` CLI.
- Generates PNG, SVG, and HTML outputs under `reports/charts/`.
- Supports trade simulation, backtest, strategy evaluation, factor evaluation, factor backtest, portfolio construction, walk-forward, and risk reports.
- Integrates chart path discovery into Agent Export through `visualization_paths`.
- Visualization-only: no quant calculation, factor, broker, live-trading, or ML changes.

## v0.22.0-maintenance-cleanup

- Removes unused placeholders and stale references.
- Aligns documentation with the current v0.x release sequence.
- Adds lightweight project hygiene checks for command documentation, ignored generated files, stale version references, and empty package directories.
- No new strategies, factors, broker integrations, report schemas, or live-trading behavior.

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

## v0.10.0-backtest-no-lookahead

- Alpha strategy integration in the Backtest Engine.
- Signal generation uses only signal-date and earlier prices.
- Execution occurs on the next available trading date.
- Trade records include signal date, execution date, signal price, execution price, costs, and cash after trade.
- Equity curve records last signal and execution dates.
- Reports include `no_lookahead`, `signal_execution_lag`, `alpha_config`, and excluded symbols per rebalance.
- Legacy simple portfolio modes remain available but are documented as same-day-close smoke modes.

## v0.11.0-factor-evaluation

- Factor Evaluation Framework module.
- No-lookahead IC and Rank IC evaluation.
- ICIR calculation.
- Quintile return and spread analysis.
- Factor decay curve for 1, 5, 10, 20, and 60 day forward windows.
- JSON factor evaluation reports under `reports/`.
- CLI command: `python -m quant.cli factor-eval --factor momentum_20d`.
- Tests for IC, Rank IC, ICIR, quintiles, decay, missing prices, empty samples, no-lookahead, and single-symbol behavior.

## v0.12.0-factor-pipeline

- Factor Pipeline module.
- Missing value handling, winsorization, z-score standardization, rank normalization, and sector neutralization.
- Market/beta neutralization placeholder.
- Alpha Engine integration through `--pipeline`.
- Factor Evaluation integration through `--pipeline`.
- JSON factor pipeline reports under `reports/`.
- CLI command: `python -m quant.cli factor-pipeline --factor momentum_20d`.
- Tests for preprocessing steps, alpha compatibility, factor-eval compatibility, and no-lookahead behavior.

## v0.13.0-factor-research-suite

- Long-Short Factor Backtest module.
- No-lookahead single-factor return testing.
- Equal-weight long top quantile and short bottom quantile.
- Optional Factor Pipeline preprocessing before quantile grouping.
- Outputs quantile returns, long-short return, annual return, volatility, Sharpe, max drawdown, hit rate, turnover, IC, Rank IC, and ICIR.
- JSON factor backtest reports under `reports/`.
- CLI command: `python -m quant.cli factor-backtest --factor momentum_20d`.
- Tests for no-lookahead behavior, quantile grouping, long-short return calculation, pipeline integration, exclusions, zero-volatility handling, and CLI smoke.

Strategy Evaluation / Performance Attribution is not implemented in v0.13. It is intentionally left for v0.14 or later.

## v0.14.0-strategy-evaluation

- Strategy Evaluation module.
- Reads factor backtest and portfolio backtest reports.
- Can generate a fresh `factor_long_short` or `alpha` source report before evaluating it.
- Outputs summary metrics, benchmark metrics, return attribution, cost attribution, turnover attribution, return concentration, risk attribution, drawdown attribution, rolling metrics, monthly returns, and yearly returns.
- Emits robustness warnings for low observation count, high turnover, high cost drag, negative compounded return with positive arithmetic Sharpe, large drawdown, benchmark underperformance, symbol concentration, long/short imbalance, and missing no-lookahead metadata.
- JSON strategy evaluation reports under `reports/`.
- CLI commands include `python -m quant.cli strategy-eval --factor-backtest-report reports/factor_backtest_*.json` and `python -m quant.cli strategy-eval --strategy factor_long_short --factor momentum_20d`.
- Tests for summary metrics, Sortino, Calmar, benchmark information ratio, return attribution, cost attribution, concentration diagnostics, high turnover/cost warnings, benchmark warnings, no-lookahead compatibility, factor backtest compatibility, and backtest compatibility.

## v0.15.0-cli-refactor

- CLI parser registration and command execution split under `quant/cli_commands/`.
- `quant/cli.py` remains the public `python -m quant.cli` entry point.
- Shared CLI context centralizes service and engine initialization.
- No command names, arguments, outputs, or report schemas intentionally changed.
- Tests for parser registration, command coverage, representative smoke commands, unknown command behavior, and `--db-path`.

## v0.16.0-portfolio-construction

- Portfolio Construction module.
- CLI command: `python -m quant.cli portfolio-construct`.
- Methods: `equal_weight`, `inverse_volatility`, `risk_parity`, and `min_variance`.
- Uses stored close prices only and respects the requested end/as-of date.
- Computes volatility, covariance, correlation, portfolio volatility, marginal risk contribution, total risk contribution, and risk contribution percentage.
- Applies long-only constraints for minimum cash, maximum position weight, and known-sector caps.
- Writes rebalance-compatible target JSON when `--output-targets` is supplied.
- JSON portfolio construction reports under `reports/`.
- Tests for methods, constraints, no-lookahead behavior, data exclusions, rebalance compatibility, report schema, and CLI smoke.

## v0.17.0-data-layer-universe

- Data Layer module for universe management, symbol metadata, coverage, quality, and readiness diagnostics.
- Continues to use Yahoo Finance / `yfinance` daily data; AkShare, Tushare, and A-share providers are not implemented in this version.
- Static `symbol_metadata` SQLite table bootstrapped from project metadata.
- Universe workflows for default, custom, sector, ETF, and large-cap universes.
- CLI commands: `universe-list`, `universe-build`, `data-refresh`, `data-coverage`, and `research-readiness`.
- Data quality diagnostics for missing ratio, duplicates, price outliers, zero-volume days, short history, and data gaps.
- Research readiness score from 0 to 100 with recommendations.
- JSON reports under `reports/` for quality, coverage, and readiness.
- Tests for universe creation, exclusions, metadata lookup, missing data detection, duplicate diagnostics, coverage, and readiness.
- No changes to factor evaluation or backtest semantics.

## v0.18.0-agent-export

- Agent Export module for compact summaries from existing reports.
- CLI command: `python -m quant.cli export-for-agent`.
- Supports text, Markdown, and compact JSON output.
- Auto-detects report type from schema keys, not file names.
- Supports alpha, factor evaluation, factor backtest, strategy evaluation, portfolio construction, risk, rebalance, execution, and backtest reports.
- Emits deterministic key metrics, findings, warnings, next steps, action candidates, and data quality notes.
- Adds approximate `--max-tokens` trimming for LLM context windows.
- Export-only: no report schema changes and no quant/backtest/factor logic changes.

## Next

- Add richer portfolio reporting.
- Add configurable universe files and metadata maintenance commands.
- Add provider abstraction for future AkShare, Tushare, and A-share research data after separate design.
- Add realized PnL tracking.
- Add basic performance metrics.
- Add benchmark and buy-and-hold comparison metrics.
- Add more backtest strategy templates.
- Add Rebalance Engine constraints for minimum trade size, max position size, and cash buffers.
- Add risk checks for max position size, cash usage, and symbol allowlists.
- Add configurable industry maps and risk score thresholds.
- Add optimizer modes based on expected returns, volatility budgets, and drawdown constraints.
- Add richer portfolio construction methods, explicit risk budgets, and configurable sector maps.
- Add benchmark comparisons and richer backtest attribution.
- Add alpha factor normalization, factor blending, and signal stability checks.
- Add factor turnover, coverage, stability, and per-sector diagnostics.
- Add regression-based beta neutralization once benchmark return inputs are explicitly modeled.
- Add execution report and portfolio report adapters for Strategy Evaluation.
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

## v0.19.0-factor-expansion

- Adds `quant/factors` with a central `FactorRegistry`.
- Adds value, quality, growth, reversal, and low-volatility price-history factor proxies.
- Adds `factor-list` CLI.
- Integrates registered factors with factor evaluation, factor pipeline, factor backtest, and alpha generation.
- Adds composite alpha scoring through normalized `factor_weights`.
- Preserves no-lookahead semantics and does not add machine learning, news sentiment, broker APIs, or live trading.

## v0.20.0-walk-forward-validation

- Adds `quant/walk_forward` for walk-forward and rolling validation.
- Supports `alpha` and `factor_long_short` strategies using existing engines.
- Adds out-of-sample train/test fold metrics, overfit warnings, factor decay warnings, regime sensitivity warnings, rolling validation, and factor stability ranking.
- Adds `walk-forward` CLI and `reports/walk_forward_*.json`.
- Validation layer only: no new factors, ML, broker integration, live trading, or no-lookahead changes.

## v0.21.0-trading-simulation

- Adds `quant/trading_simulation` for offline historical account-style simulation.
- Adds reusable `PortfolioAccount` with cash, positions, trade history, realized PnL, unrealized PnL, cost tracking, and mark-to-market snapshots.
- Adds `trade-sim` CLI for alpha-driven simulation with equal weight, inverse volatility, risk parity, or minimum variance portfolio construction.
- Uses no-lookahead signal generation on the signal date and next available trading date execution by default.
- Integrates Alpha Engine, Portfolio Construction, Cost Engine, and account state in one historical loop.
- Adds `reports/trade_sim_*.json` and Agent Export support for trade simulation reports.
- Offline simulation only: no broker API, no live execution, no high-frequency trading, and no change to existing backtest semantics.
