# AI Development Guide

This document is the long-lived context entry point for AI assistants working on `openclaw-quant-v1`.

## Current Version

`v0.35.0-mcp-server-foundation`

The project currently includes:

- A market data layer using a `DataProvider` abstraction with `yfinance` as the default US stock and ETF daily OHLCV provider.
- SQLite storage for normalized price data.
- An offline data layer for universe management, static metadata, coverage, quality, and readiness diagnostics.
- A fundamental data layer for CSV import, storage, query, coverage, and quality diagnostics.
- Report-date-aware accounting fundamental factors for value, quality, growth, and financial health.
- An agent export layer that compresses existing reports for LLM and OpenClaw-style agent context windows.
- A simulated portfolio state module with accounts, positions, and trades.
- An alpha engine that calculates deterministic factors and target weights from stored prices.
- A factor pipeline that preprocesses same-date factor cross-sections before alpha generation or evaluation.
- A factor evaluation framework that calculates no-lookahead IC, Rank IC, ICIR, quintile, and decay metrics.
- A long-short factor backtest that checks single-factor return streams without modifying portfolio state.
- A persistent factor store for definitions, factor values, IC/Rank IC history, backtest history, walk-forward history, stability, coverage, confidence, and versions.
- A deterministic regime detection layer for market-state history and factor-by-regime diagnostics.
- A strategy evaluation layer that explains return, risk, drawdown, rolling metrics, and attribution from generated reports.
- A minimal SMA crossover backtest engine that uses stored prices.
- A portfolio rebalance engine that calculates allocation drift and suggested trades.
- A risk engine that calculates portfolio concentration, cash exposure, Top 5 holdings exposure, and a 0-100 risk score.
- A portfolio optimizer that generates target allocations for the Rebalance Engine.
- A portfolio construction layer that generates equal weight, inverse volatility, risk parity, and minimum variance target weights.
- A cost engine that estimates fixed, linear, combined, and slippage costs for suggested trades.
- A deterministic daily portfolio backtest engine that combines stored prices, optimizer targets, rebalance logic, and costs.
- An execution simulator that models intended, executed, and unfilled trades with costs.
- A historical trading simulator that tracks in-memory account cash, positions, costs, trades, and equity through time.
- A market realism layer that estimates ADV liquidity, slippage, market impact, rejected quantities, and missing-price skips for historical simulation.
- Walk-forward and rolling validation for offline research robustness checks.
- A visualization layer that turns existing JSON reports into PNG, SVG, and HTML dashboards.
- CLI commands for price updates, price inspection, account initialization, simulated buys and sells, portfolio snapshots, trade history, alpha, factor pipeline, factor evaluation, factor backtest, strategy evaluation, backtests, allocation, rebalance plans, cost estimates, optimization, risk, and execution simulation.
- A modular CLI implementation under `quant/cli_commands/`.
- A layered package layout under `quant/core`, `quant/data`, `quant/factors`, `quant/engines`, `quant/services`, `quant/reports`, `quant/interfaces`, and `quant/adapters`.
- A local MCP-compatible research interface under `quant/interfaces/mcp_server`.
- A Strategy DSL layer under `quant/strategy_dsl` for versioned offline research definitions.

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
- Data layer and provider features must not change factor evaluation or backtest semantics. They should improve metadata, coverage, quality, provider boundaries, and readiness only.
- AkShare, Tushare, A-share data, real-time market data, Alpha Vantage, and Polygon are future provider additions unless explicitly implemented in a later release.
- Optional provider dependencies must stay isolated. Missing `yfinance` may mark the yfinance provider as `NOT_INSTALLED`, but it must not break CLI startup, project audit, provider listing, CSV/mock tests, or `--help` commands.
- Agent export features must remain read-only and export-only. Do not change source report schemas, quant logic, factor evaluation, backtest behavior, portfolio state, or execution behavior.
- Fundamental data features must remain storage/import/query/quality only until a later explicit factor-scoring release. Do not change existing price-only factor semantics.
- Fundamental factors must use `report_date <= signal_date`; never use `fiscal_period_end` alone for tradable availability.
- Multi-factor work should stay inside `quant/multi_factor` or Alpha integration. Do not add ML, news sentiment, broker APIs, or live execution under the multi-factor label.
- Multi-factor confidence is coverage-aware. Missing fundamentals should lower confidence or produce warnings, not be silently treated as true zero signals.
- Multi-factor confidence is diagnostic only. Do not present it as expected return, investment advice, or a guarantee.

## Important Files

- `quant/config.py`: project defaults and symbol universe.
- `quant/data_providers/`: provider interface, registry, yfinance provider, CSV provider, mock provider, and future-provider placeholders.
- `quant/data/providers/`: preferred layered import path for data providers. `quant/data_providers/` remains compatibility-supported.
- `quant/fundamental_data/`: fundamental store, importer, service, coverage, and quality checks.
- `quant/fundamental_factors/`: accounting factor functions and registry extension metadata.
- `quant/multi_factor/`: factor normalization, weighting, confidence, family contribution, and final alpha score model.
- `quant/data_source/yfinance_client.py`: legacy yfinance normalization client used by the yfinance provider.
- `quant/data_layer/`: universe, metadata, data quality, coverage, and readiness modules.
- `quant/agent_export/agent_exporter.py`: compact report export layer for LLM/agent consumers.
- `quant/reports/agent_export/`: preferred layered import path for agent export. `quant/agent_export/` remains compatibility-supported.
- `quant/storage/sqlite_store.py`: price table persistence.
- `quant/storage/portfolio_store.py`: account, position, and trade persistence.
- `quant/services/price_service.py`: price update orchestration.
- `quant/services/portfolio_service.py`: simulated portfolio business rules.
- `quant/services/backtest_service.py`: SMA crossover backtest engine and metrics.
- `quant/alpha/alpha_engine.py`: pure factor and target-weight engine.
- `quant/factor_backtest/factor_backtest.py`: pure long-short factor backtest engine.
- `quant/factor_store/`: persistent factor research history, registry sync, rankings, stability, coverage, and confidence analytics.
- `quant/regime_detection/`: deterministic regime classification, regime history, factor-by-regime analytics, and regime-aware rankings.
- `quant/factor_pipeline/factor_pipeline.py`: pure factor preprocessing pipeline.
- `quant/factor_eval/factor_evaluation.py`: pure no-lookahead factor evaluation framework.
- `quant/strategy_eval/strategy_evaluation.py`: pure strategy explanation and attribution engine.
- `quant/backtest/backtest_engine.py`: deterministic daily portfolio backtest engine.
- `quant/rebalance/rebalance_engine.py`: pure allocation and rebalance calculation engine.
- `quant/risk/risk_engine.py`: pure portfolio risk calculation engine.
- `quant/optimizer/optimizer_engine.py`: pure target allocation optimizer.
- `quant/portfolio_construction/portfolio_construction.py`: pure portfolio construction and risk contribution engine.
- `quant/cost/cost_engine.py`: pure transaction cost estimator.
- `quant/market_realism/`: deterministic slippage, liquidity, marketability, and position-size constraints.
- `quant/execution/execution_engine.py`: pure simulated execution engine.
- `quant/trading_simulation/`: offline historical account-style simulation.
- `quant/walk_forward/`: offline walk-forward and rolling validation.
- `quant/visualization/`: report charts and dashboards from existing JSON reports.
- `quant/reports/visualization/`: preferred layered import path for visualization. `quant/visualization/` remains compatibility-supported.
- `quant/core_protocols/`: JSON-safe account, order, fill, position, signal, recommendation, trade, and snapshot protocol objects.
- `quant/core/protocols/`: preferred layered import path for protocol objects. `quant/core_protocols/` remains compatibility-supported.
- `quant/cli.py`: command line entry point and dispatcher.
- `quant/cli_commands/`: command-specific parser registration and handlers.
- `quant/interfaces/cli_commands/`: layered CLI command namespace. `quant/cli_commands/` remains the compatibility import path in v0.34.
- `quant/interfaces/mcp_server/`: JSON-safe local MCP research tools. It is not a live trading or broker interface.
- `quant/strategy_dsl/`: YAML/JSON strategy definitions, validation, metadata persistence, and offline orchestration.
- `pyproject.toml`: packaging metadata, optional dependency groups, pytest defaults, and console script entry point.
- `.github/workflows/`: CI and project audit workflows.
- `docs/PACKAGING.md`: install, optional dependency, and CI guidance.
- `tests/`: pytest coverage for data, portfolio, alpha, factor pipeline, factor evaluation, factor backtest, strategy evaluation, backtest, rebalance, optimizer, risk, cost, market realism, and execution behavior.

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

## v0.19 Factor Development Notes

Use `quant/factors/factor_registry.py` as the central registry for deterministic factors. Each factor must declare category, type, description, required inputs, and lookback window. Factor calculations must use only signal-date-and-earlier data, and new factors should be tested through `factor-eval`, `factor-backtest`, `factor-pipeline`, and `alpha` compatibility paths.

## v0.20 Walk Forward Notes

Walk-forward code belongs under `quant/walk_forward` and should orchestrate existing engines rather than rewriting strategy logic. Keep reports deterministic, no-lookahead, and offline. New validation warnings should be stable codes with clear reasons and pytest coverage.

## v0.21 Trading Simulation Notes

Trading simulation code belongs under `quant/trading_simulation`. Keep it offline and deterministic. Use `PortfolioAccount` for in-memory cash and position state, preserve `signal_date < execution_date`, and do not write simulated historical loop state into persistent portfolio tables. New simulator changes should include CLI coverage, report schema tests, and Agent Export compatibility tests.

## v0.23 Visualization Notes

Visualization code belongs under `quant/visualization`. It should read existing JSON reports and write generated artifacts under `reports/charts/`. Do not change source report schemas, quant calculations, factor logic, portfolio state, or execution behavior.

## v0.24 Data Provider Notes

Provider code belongs under `quant/data_providers`. `PriceService` and data refresh should call the `DataProvider` interface rather than importing provider implementations directly. Keep `yfinance` as the default until a later release explicitly changes configuration. New providers must include health checks, deterministic tests, documentation, and must preserve no-lookahead semantics by only loading historical data requested by callers.

## v0.25 Fundamental Data Notes

Fundamental data code belongs under `quant/fundamental_data`. Store `report_date` separately from `fiscal_period_end`; factor code must use `report_date` for no-lookahead alignment. CSV import is the main supported path in v0.25.

## v0.26 Fundamental Factor Notes

Fundamental factor code belongs under `quant/fundamental_factors` and must be registered through `quant/factors/factor_registry.py`. Every fundamental factor must enforce `report_date <= signal_date`; `fiscal_period_end` alone is not enough. Missing metrics must be skipped or excluded, never filled with fake zero values.

## v0.27 Multi-Factor Notes

Multi-factor code belongs under `quant/multi_factor`. It may combine registered price and fundamental factors, but it must not introduce new factors, ML models, broker integration, or live trading. Preserve the existing Alpha, FactorEval, FactorBacktest, WalkForward, and TradingSimulation no-lookahead contracts.

## v0.28 Packaging And CI Notes

Packaging work belongs in `pyproject.toml`, `requirements.txt`, `.github/`, repository templates, and documentation. It must not change quant calculations, report schemas, or no-lookahead behavior. Keep `requirements.txt` usable, add optional dependencies through packaging metadata, and run both `pytest` and `python tools/project_audit.py` before release.

## v0.29 Protocol Notes

Protocol work belongs under `quant/core_protocols`. It may add JSON-safe objects and internal validation, but it must not add live broker behavior, automatic trading, new alpha factors, new data providers, or report schema changes. Future MCP/OpenClaw work should consume these objects rather than scraping engine internals.

## v0.31 Factor Store Notes

Factor Store work belongs under `quant/factor_store`. It may persist factor definitions, values, evaluation history, backtest history, walk-forward folds, stability scores, coverage, confidence, and versions. It must not add new factors, change factor evaluation semantics, change factor backtest semantics, alter walk-forward no-lookahead behavior, or generate trades. Persistence through `--save-factor-history` is opt-in.

## v0.32 Regime Detection Notes

Regime Detection work belongs under `quant/regime_detection`. It may classify stored benchmark price history into deterministic market regimes and persist factor-by-regime diagnostics. It must not add ML, news sentiment, broker integration, live trading, automatic factor disabling, or automatic portfolio changes. Regime diagnostics must preserve signal-date no-lookahead alignment.

## v0.33 Scheduler Notes

Scheduler work belongs under `quant/scheduler`. It may orchestrate existing offline research steps and persist `research_run_history`, but it must not add broker integration, live trading, AI-directed order execution, or new strategy logic. Scheduler steps should be failure-isolated and emit stable warning codes rather than hiding partial failures.

Short smoke:

```bash
python -m quant.cli research-run --skip-data-refresh --skip-trade-sim
```

## v0.34 Architecture Layout Notes

New code should prefer layered imports:

- `quant.core.protocols` for protocol objects.
- `quant.data.providers`, `quant.data.layer`, and `quant.data.fundamental` for data boundaries.
- `quant.factors.price`, `quant.factors.fundamental`, and `quant.factors.store` for factor boundaries.
- `quant.engines.*` for pure quant engines.
- `quant.reports.agent_export` and `quant.reports.visualization` for report consumers.
- `quant.interfaces.*` for CLI/API/MCP boundaries.
- `quant.adapters.*` for optional external framework adapters.

v0.34 is phase 1 of the namespace refactor. Do not remove legacy imports during v0.34 work. Compatibility shims are intentional and should remain until a later release explicitly schedules their removal. Future physical module migration may happen gradually after new callers adopt the layered namespaces. The reserved API/OpenClaw/LangChain/QuantStats/PyFolio packages are placeholders only; do not add those integrations under the architecture-refactor label.

## v0.35 MCP Notes

MCP code belongs under `quant/interfaces/mcp_server`. It may expose existing research capabilities through JSON-safe tool objects, but it must stay read-only or local offline simulation only. Do not add broker connectivity, live order submission, position mutation, automatic trading, ML, news sentiment, or new factors under the MCP label.

Every MCP tool must declare exactly one `capability_level`: `READ_ONLY`, `OFFLINE_SIMULATION`, `PAPER_TRADING_RESERVED`, or `LIVE_TRADING_FORBIDDEN`. v0.35 may only enable `READ_ONLY` and `OFFLINE_SIMULATION`. Disabled capability levels must be blocked before runner execution.

## v0.36 Strategy DSL Notes

Strategy DSL code belongs under `quant/strategy_dsl`. It may parse YAML/JSON definitions, validate deterministic gates, persist strategy metadata, and orchestrate existing offline engines. It must not add live trading, broker integration, automatic strategy mutation, new factors, ML, news sentiment, report schema changes, or no-lookahead semantic changes.

Strategy DSL validation must reject attempts to override no-lookahead behavior. Fundamental strategy definitions must still rely on existing factor engines using `report_date <= signal_date`.

Forbidden trading/broker tool names must return `NOT_SUPPORTED`, including `place_order`, `submit_order`, `cancel_order`, `modify_position`, `connect_broker`, `execute_trade`, `live_trade`, `rebalance_live`, and `paper_trade_live`.

## v0.37 Strategy Gate Notes

Strategy Evaluation Gate code belongs under `quant/strategy_gates`. It may read Strategy DSL validation, Factor Store history, walk-forward history, regime diagnostics, and offline strategy-run/trade-sim reports. It must not add factors, alter quant calculations, change report schemas for existing reports, connect brokers, submit orders, mutate real accounts, or weaken no-lookahead rules.

`strategy-gate` and `strategy-run --with-gates` are offline research quality-control commands. MCP `run_strategy_gates` must remain `OFFLINE_SIMULATION`; `latest_strategy_gate_report` must remain `READ_ONLY`.

## v0.39 Research Validation & Coverage Notes

Research validation code belongs under `quant/research_validation`. It may orchestrate existing factor evaluation, factor backtest, walk-forward, regime, Strategy DSL, and Strategy Gate engines. It must not add factors, change strategy logic, alter no-lookahead semantics, add broker/live trading behavior, or tune parameters.

Use `research-validation --mode quick` for bounded local smoke validation. Use `--mode full` only for deliberate long-running research sessions. The workflow must record partial results, skipped steps, timeouts, slow steps, and runtime seconds.

## v0.40 Performance Profiling Notes

Performance profiling code belongs under `quant/performance`. It may time existing engines, store/query calls, Factor Store lookups, fundamental lookups, and report generation. It must not optimize, parallelize, cache, vectorize, tune, suppress warnings, change report schemas, or alter quant semantics.

Use `performance-profile` to measure bottlenecks before proposing optimization work. Any future optimization must preserve no-lookahead behavior and existing factor evaluation, factor backtest, walk-forward, strategy, research validation, and trade simulation semantics.
