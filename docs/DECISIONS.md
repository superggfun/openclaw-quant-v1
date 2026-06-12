# Decisions

## 2026-06-11: Start With SQLite

SQLite is the local source of truth for v0.1.0 because it is simple, durable, testable, and easy for AI assistants to inspect.

## 2026-06-11: Keep Broker Integration Out of Scope

The portfolio module is a simulated state engine only. It does not connect to brokers, manage credentials, or place orders.

## 2026-06-11: Use Services as Boundaries

CLI commands should call service classes. Services should coordinate rules and persistence. Storage classes should own SQL and schema details.

## 2026-06-11: Use Latest Close for Portfolio Valuation

Portfolio valuation reads the latest `close` from the existing `prices` table. If no price exists for a held symbol, the CLI displays `N/A` for current price, market value, and unrealized PnL.

## 2026-06-11: Backtests Use Stored Prices Only

The backtest engine reads from the existing `prices` table and never downloads data. Data refresh remains the job of `update-prices`.

## 2026-06-11: Deterministic Position Sizing

The V0.2 SMA crossover backtest uses deterministic code to calculate trade quantity from available cash, close price, and commission. LLMs and future OpenClaw callers must not directly decide quantities.

## 2026-06-11: Generated Reports Stay Out of Git

Backtest JSON reports are written under `reports/` and ignored by git. The repository keeps only `reports/.gitkeep`.

## 2026-06-11: Rebalance Engine Is Pure Calculation

The V0.3 rebalance engine calculates current allocation and suggested trades only. It does not update cash, positions, or trades. Future Risk Engine, OpenClaw, and AI research callers should use this boundary.

## 2026-06-11: Rebalance Uses Integer Shares

Suggested buy and sell quantities are integer shares calculated by deterministic code from target value differences, latest prices, cash, and commission.

## 2026-06-11: Rebalance Commission Defaults to 0.1%

The default rebalance commission rate is `0.001`. It is configurable from the CLI through `--commission`.

## 2026-06-11: Risk Engine Uses Rebalance Allocation

The V0.4 risk engine reuses the Rebalance Engine allocation source so portfolio value calculations stay consistent across allocation, rebalance, and risk commands.

## 2026-06-11: Risk Score Is Deterministic

Risk score is a deterministic 0-100 heuristic based on single-stock concentration, industry concentration, Top 5 holdings concentration, and cash exposure. It is not an AI judgment and is not investment advice.

## 2026-06-11: Optimizer Generates Targets, Not Trades

The V0.5 optimizer produces target allocations only. Rebalance Engine remains responsible for turning targets into buy and sell suggestions.

## 2026-06-11: Optimizer Avoids Heavy Math Dependencies

V0.5 uses deterministic rules for equal-weight, risk-adjusted, and constrained target generation. It does not introduce complex optimization libraries yet.

## 2026-06-11: Cost Engine Estimates Only

The V0.6 cost engine estimates transaction costs from suggested trades. It does not filter, execute, or modify trades.

## 2026-06-11: Cost Models Stay Simple

V0.6 supports fixed, linear, and combined costs with simple slippage in basis points. Complex market impact is intentionally out of scope.

## 2026-06-11: Portfolio Backtests Are In-Memory And Deterministic

The V0.7 portfolio backtest engine simulates cash, positions, rebalance decisions, and costs in memory. It does not modify the persistent simulated portfolio state, and the same stored prices and parameters produce the same metrics and trades.

## 2026-06-11: Execution Simulator Is Not Broker Execution

The V0.8 execution simulator models fills from rebalance suggestions, including immediate, next-day open, TWAP, and partial-fill modes. It writes reports only and does not update persistent portfolio state, connect to brokers, or place orders.

## 2026-06-11: Alpha Engine Generates Signals, Not Orders

The V0.9 alpha engine calculates deterministic factors from stored prices and produces target weights. Rebalance Engine remains responsible for suggested trades, and no AI model directly decides quantities.

## 2026-06-11: Alpha Uses Signal-Date Data Only

Alpha factors use rows at or before `as_of_date`. Alpha targets are treated as next-session targets, and the report exposes `suggested_execution_date` when stored data can identify the following trading date.

## 2026-06-11: Alpha Backtests Must Execute After Signal Date

The v0.10 alpha backtest path generates signals on T with T-and-earlier data and executes on the next available trading day. Legacy same-day-close portfolio modes remain available only as simple smoke paths.

## 2026-06-11: Factor Evaluation Compares Past Signals To Future Returns

The v0.11 factor evaluation framework calculates factors using only signal-date-and-earlier prices, then evaluates those values against future returns. It is a research diagnostic layer only and does not generate trades or target allocations.

## 2026-06-11: Factor Pipeline Transforms Same-Date Cross-Sections Only

The v0.12 factor pipeline receives factor values already calculated for one signal date and applies deterministic preprocessing to that cross-section. It does not read future prices, future returns, or dated future metadata.

## 2026-06-11: Long-Short Factor Backtest Is Not Strategy Attribution

The v0.13 factor backtest checks whether one factor can produce an equal-weight long-short return stream. It does not update portfolio state and does not implement Strategy Evaluation or Performance Attribution, which remain future work.

## 2026-06-11: Strategy Evaluation Reads Reports

The v0.14 strategy evaluation layer explains returns and risk from supported generated reports. The CLI may generate an alpha or factor long-short source report before evaluation, but the evaluation layer itself does not recalculate alpha signals, introduce new strategies, modify portfolio state, or execute trades.

## 2026-06-11: Strategy Diagnostics Are Warnings

Robustness diagnostics such as high turnover, high cost drag, symbol concentration, benchmark underperformance, or unstable Sharpe are emitted as warning codes for research review. They are not trade signals and they do not alter backtest, factor backtest, rebalance, or portfolio state semantics.

## 2026-06-11: CLI Commands Are Split By Area

The `v0.15.0` CLI refactor keeps `python -m quant.cli` as the public entry point while moving parser registration and command handlers into `quant/cli_commands/`. This is a maintainability change only: command names, arguments, output text, report schemas, and engine behavior should remain backward compatible.

## 2026-06-11: Portfolio Construction Generates Targets Only

The `v0.16.0` portfolio construction layer uses stored close prices to generate long-only target weights and risk contribution diagnostics. It does not update portfolio state, execute trades, call brokers, or make AI decisions. Rebalance and execution simulation remain separate downstream layers.

## 2026-06-12: Data Layer Expands Research Coverage Without Changing Research Semantics

The `v0.17.0` data layer adds static symbol metadata, universe construction, coverage reports, data quality diagnostics, and research readiness scoring. It does not change existing factor evaluation, factor backtest, portfolio backtest, or no-lookahead semantics.

## 2026-06-12: Agent Export Is Read-Only

The `v0.18.0` agent export layer converts existing reports into compact summaries for LLM and OpenClaw-style agents. It must not modify source report schemas, quant logic, factor evaluation logic, backtest logic, portfolio state, or execution behavior.

## 2026-06-12: Factor Expansion Is Price-Only

The `v0.19.0` factor library adds value, quality, growth, reversal, and low-volatility proxies using stored price history only. These are deterministic research factors, not paid-fundamental, sentiment, machine-learning, or live-trading features. New factors must be registered centrally and tested through factor evaluation/backtest compatibility.

## 2026-06-12: Walk Forward Is Validation Only

The `v0.20.0` walk-forward layer orchestrates existing alpha, backtest, factor evaluation, and factor backtest engines to measure out-of-sample behavior. It must not add factors, change strategy semantics, connect brokers, place trades, or weaken no-lookahead guarantees.

## 2026-06-12: Trading Simulation Uses In-Memory Account State

The `v0.21.0` trading simulation layer tracks cash, positions, PnL, costs, and trades in an in-memory `PortfolioAccount`. It writes reports only and does not mutate the persistent `accounts`, `positions`, or `trades` tables. Signals use signal-date-and-earlier data, execution is scheduled for the next available trading date, and the feature remains offline historical research only.

## 2026-06-12: Data Providers Are An Abstraction Boundary

The `v0.24.0` provider layer introduces `DataProvider` and `ProviderRegistry` so price refresh and diagnostics no longer depend directly on yfinance. `yfinance` remains the default provider. CSV and mock providers are for offline imports and tests. AkShare, Tushare, Alpha Vantage, and Polygon are registered only as not-installed placeholders. This release does not change factor evaluation, backtest semantics, report schemas, or no-lookahead rules.

## 2026-06-12: Fundamental Data Is Storage Only

The `v0.25.0` fundamental data layer imports, stores, queries, and validates statement and metric data. It preserves `report_date` separately from `fiscal_period_end` for future no-lookahead factor alignment. It does not implement PE, PB, ROE, ROA, revenue growth, EPS growth, or other fundamental factor scoring yet.
