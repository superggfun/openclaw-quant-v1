# Architecture

`openclaw-quant-v1` is organized as a small layered Python application.

## Layers

```text
CLI
 |
Services / Engines
 |
Storage / Data Sources
 |
SQLite / External APIs
```

## Layered Package Layout

`v0.34.0` is phase 1 of the layered namespace refactor. It introduces a clearer package layout before any MCP, API, OpenClaw, LangChain, QuantStats, or PyFolio adapters are implemented.

The new paths are structural boundaries only. They do not change CLI behavior, report schemas, factor calculations, backtest behavior, trading simulation semantics, or no-lookahead guarantees. Existing public import paths remain supported through lightweight compatibility shims for at least one release.

Most implementation files remain in their legacy locations in this phase. Future physical migration can happen gradually once callers have moved to the layered namespaces.

```text
quant/
  core/          protocols, validation, warning helpers
  data/          providers, data layer, fundamental data
  factors/       price factors, fundamental factors, factor store
  engines/       alpha, backtest, factor research, portfolio, risk, execution
  services/      application orchestration services
  reports/       agent export and visualization
  interfaces/    CLI plus reserved MCP/API boundaries
  adapters/      reserved external framework boundaries
  scheduler/     daily offline research automation
  utils/         small shared implementation helpers
```

Compatibility examples:

```python
from quant.core.protocols.account import AccountState
from quant.core_protocols.account import AccountState as LegacyAccountState

assert AccountState is LegacyAccountState
```

The reserved `quant.interfaces.mcp_server`, `quant.interfaces.api`, `quant.adapters.openclaw`, `quant.adapters.langchain`, `quant.adapters.quantstats`, and `quant.adapters.pyfolio` packages are placeholders only. They intentionally do not implement external integrations in v0.34.

## Components

- `quant.cli`: Main CLI entry point. It builds the top-level parser, creates shared context, and dispatches to command modules.
- `quant.cli_commands`: Dedicated parser registration and command handlers for data, data layer, scheduler, agent export, visualization, portfolio, rebalance, risk, optimizer, portfolio construction, alpha, factor, strategy evaluation, trading simulation, cost, execution, and backtest commands.
- `quant.interfaces.cli_commands`: Layered alias for CLI command modules. `quant.cli_commands` remains the implementation path in v0.34.
- `pyproject.toml`: PEP 621 packaging metadata, optional dependency groups, pytest defaults, and the `openclaw-quant` console entry point.
- `quant.core.protocols`: Layered protocol namespace. `quant.core_protocols` remains supported.
- `quant.reports.agent_export`: Layered report export namespace. `quant.agent_export` remains supported.
- `quant.reports.visualization`: Layered visualization namespace. `quant.visualization` remains supported.
- `quant.data.providers`: Layered data provider namespace. `quant.data_providers` remains supported.
- `quant.data.layer`: Layered universe, metadata, coverage, and quality namespace. `quant.data_layer` remains supported.
- `quant.data.fundamental`: Layered fundamental data namespace. `quant.fundamental_data` remains supported.
- `quant.engines.*`: Layered aliases for pure engine modules such as alpha, backtest, factor evaluation, factor backtest, multi-factor, regime, portfolio construction, risk, execution, trading simulation, strategy evaluation, and walk-forward.
- `quant.fundamental_data`: Stores, imports, queries, validates, and reports offline fundamental data.
- `quant.fundamental_factors`: Computes report-date-aware accounting factors from `fundamental_metrics`.
- `quant.multi_factor`: Combines price and fundamental factors into normalized, coverage-aware alpha scores.
- `quant.data_layer.universe_manager`: Builds default, custom, sector, ETF, and large-cap universes.
- `quant.data_layer.symbol_metadata`: Stores static symbol metadata in SQLite.
- `quant.data_layer.data_quality`: Produces coverage, data quality, and research readiness reports.
- `quant.services.price_service`: Coordinates daily price updates and reads.
- `quant.services.portfolio_service`: Applies simulated account, buy, sell, and valuation rules.
- `quant.services.backtest_service`: Runs SMA crossover backtests from stored prices and writes JSON reports.
- `quant.alpha.alpha_engine`: Calculates alpha factors, ranks symbols, and generates target weights.
- `quant.factor_backtest.factor_backtest`: Runs no-lookahead equal-weight long-short factor return backtests.
- `quant.factor_store`: Persists factor definitions, values, evaluation history, backtest history, walk-forward fold history, stability, coverage, and versions.
- `quant.factor_pipeline.factor_pipeline`: Preprocesses same-date factor cross-sections before alpha generation or evaluation.
- `quant.factor_eval.factor_evaluation`: Evaluates factor predictive quality with no-lookahead IC, Rank IC, quintile, and decay metrics.
- `quant.regime_detection`: Classifies deterministic market regimes, persists regime history, and summarizes factor performance by regime.
- `quant.scheduler`: Orchestrates daily offline research pipeline runs and persists scheduler history.
- `quant.strategy_eval.strategy_evaluation`: Explains returns, risk, drawdowns, rolling metrics, and attribution from generated reports.
- `quant.trading_simulation`: Runs offline account-style historical simulations with in-memory cash, positions, trades, costs, and equity curves.
- `quant.market_realism`: Applies deterministic slippage, ADV liquidity, marketability, and position-size constraints to simulated execution.
- `quant.backtest.backtest_engine`: Runs daily portfolio backtests from stored prices, optimizer targets, rebalance logic, and costs.
- `quant.rebalance.rebalance_engine`: Calculates current allocation and rebalance suggestions from account, position, and price state.
- `quant.risk.risk_engine`: Calculates portfolio concentration, cash, Top 5, industry, and risk score metrics.
- `quant.optimizer.optimizer_engine`: Generates target allocations for the Rebalance Engine.
- `quant.portfolio_construction.portfolio_construction`: Builds target allocations from stored close prices, covariance, and risk contribution calculations.
- `quant.cost.cost_engine`: Estimates transaction costs for suggested trades.
- `quant.execution.execution_engine`: Simulates execution of rebalance suggestions and costs.
- `quant.storage.sqlite_store`: Owns the `prices` table.
- `quant.storage.portfolio_store`: Owns `accounts`, `positions`, and `trades`.
- `quant.data_source.yfinance_client`: Legacy yfinance normalization client used by `quant.data_providers.yfinance_provider`.

## Data Flow

CLI dispatch flow:

```text
python -m quant.cli -> quant.cli build_parser/create_context -> quant.cli_commands.<area>.handle
```

`v0.15.0` only refactors CLI structure. It does not change command names, arguments, output text, report schemas, or engine behavior.

Price update flow:

```text
CLI update-prices -> PriceService -> ProviderRegistry/default DataProvider -> SQLitePriceStore -> prices
                                    |
                                    `-> YFinanceProvider -> YFinanceClient -> yfinance
```

Data layer flow:

```text
CLI provider/data commands -> ProviderRegistry + UniverseManager + SymbolMetadataStore + DataQualityAnalyzer -> prices/symbol_metadata -> reports/data_*.json
```

The data layer expands research coverage and diagnostics without changing factor evaluation, factor backtest, portfolio backtest, or no-lookahead semantics. `v0.24.0` changes the data access boundary only: yfinance remains the default provider, CSV and mock providers support offline workflows, and AkShare/Tushare/Alpha Vantage/Polygon are placeholders.

`v0.28.0` adds dependency isolation around provider imports. CLI startup, project audit, provider listing, and mock/CSV workflows must not import or require `yfinance`; only the yfinance provider health check or data download path reports `NOT_INSTALLED` when the package is absent.

Packaging and CI flow:

```text
pyproject.toml + requirements.txt -> editable/dev installs -> pytest + tools/project_audit.py -> GitHub Actions
```

Fundamental data flow:

```text
CLI fundamental-* commands -> FundamentalService -> FundamentalStore -> SQLite fundamental tables -> reports/fundamental_*.json

CLI factor-eval/factor-backtest/alpha -> FactorRegistry -> FundamentalStore.latest_as_of(report_date <= signal_date) -> fundamental factor values
CLI alpha -> MultiFactorModel -> normalized factor/family contributions -> coverage-aware alpha scores -> targets
```

The fundamental data layer handles storage/import/query/quality. `v0.26.0` adds accounting-based factor calculations while preserving price-only factor behavior. `v0.27.0` adds the formal multi-factor combination layer. Fundamental factors always use `report_date <= signal_date`; `fiscal_period_end` alone is not a valid no-lookahead filter.

Factor store flow:

```text
factor-eval / factor-backtest / walk-forward --save-factor-history -> FactorStore -> factor_* SQLite tables -> factor-history / factor-rank reports
```

The Factor Store persists outputs from existing no-lookahead engines. It does not recompute factors independently and does not change factor evaluation, factor backtest, walk-forward, alpha, or trading simulation semantics.

Regime detection flow:

```text
detect-regime -> RegimeDetector -> prices(SPY by default, date-and-earlier rolling metrics) -> regime_history -> regime reports

factor-eval/factor-backtest --save-regime-history -> RegimeAnalytics -> factor_regime_history -> regime-rank
```

The regime layer is diagnostic only. It does not disable factors, adjust target weights automatically, or execute trades.

Scheduler flow:

```text
research-run -> Data Refresh / Coverage -> Factor Evaluation -> Factor Store -> Regime Detection -> Trade Simulation -> Visualization -> Agent Export -> research_run report
```

The scheduler is an orchestration layer over existing engines. It does not introduce new quant calculations, modify existing report schemas, connect to brokers, or place orders.

Agent export flow:

```text
CLI export-for-agent -> AgentExporter -> existing reports/*.json -> compact text/markdown/json summary
```

The agent export layer is read-only and export-only. It does not modify source reports, quant logic, factor evaluation, backtest behavior, portfolio state, or execution behavior.

Protocol export flow:

```text
Protocol object -> AgentExporter.export_protocol -> compact AgentExport object
```

Protocol export does not replace existing report export. It gives future MCP/OpenClaw callers a stable JSON-safe object boundary without changing report schemas.

Visualization flow:

```text
CLI visualize-report -> ReportVisualizer -> existing reports/*.json -> reports/charts/*.png/*.svg/*_summary.html
```

The visualization layer is read-only with respect to source reports. It does not modify quant calculations, report schemas, portfolio state, or execution behavior.

Market realism flow:

```text
target trade -> LiquidityModel -> ExecutionConstraints -> CostEngine -> simulated fill / rejected trade
```

`v0.30.0` adds this flow to historical simulation and execution simulation. It uses stored daily OHLCV rows only. It does not add intraday data, tick data, live broker connectivity, or high-frequency execution.

Portfolio flow:

```text
CLI buy/sell -> PortfolioService -> SQLitePortfolioStore -> accounts/positions/trades
```

Portfolio valuation flow:

```text
CLI portfolio -> PortfolioService -> SQLitePortfolioStore -> positions + latest prices.close
```

Backtest flow:

```text
CLI backtest -> BacktestService -> SQLitePriceStore -> prices -> reports/backtest_*.json
```

The backtest engine never downloads data. It only uses rows already present in `prices`.

Rebalance flow:

```text
CLI allocation/rebalance -> RebalanceEngine -> SQLitePortfolioStore -> accounts/positions/prices -> reports/rebalance_*.json
```

The rebalance engine is side-effect free for portfolio state. It does not update cash, positions, or trades.

Risk flow:

```text
CLI risk -> RiskEngine -> RebalanceEngine allocation -> SQLitePortfolioStore -> accounts/positions/prices -> reports/risk_*.json
```

The risk engine is side-effect free for portfolio state. It is designed as a stable data source for future OpenClaw Risk Agent work.

Optimizer flow:

```text
CLI optimize -> OptimizerEngine -> prices + allocation + risk -> examples/optimized_targets.json -> reports/optimize_*.json
```

The optimizer is side-effect free for portfolio state. It generates target allocations, not trades.

Portfolio construction flow:

```text
CLI portfolio-construct -> PortfolioConstructionEngine -> SQLitePriceStore -> reports/portfolio_construction_*.json + optional target JSON
```

The portfolio construction engine is side-effect free for portfolio state. It uses stored close prices at or before the requested end/as-of date, computes return covariance/correlation and risk contributions, applies long-only constraints, and generates rebalance-compatible target allocations.

Alpha flow:

```text
CLI alpha -> AlphaEngine -> optional MultiFactorModel -> optional FactorPipeline -> SQLitePriceStore/FundamentalStore -> examples/alpha_targets.json -> reports/alpha_*.json
```

The alpha engine is side-effect free for portfolio state. It reads stored prices, calculates factors and ranks, and generates target weights for downstream rebalance workflows.

Factor pipeline flow:

```text
CLI factor-pipeline -> FactorPipeline -> reports/factor_pipeline_*.json
CLI alpha --pipeline -> AlphaEngine -> FactorPipeline -> reports/factor_pipeline_*.json
CLI factor-eval --pipeline -> FactorEvaluation -> FactorPipeline -> reports/factor_eval_*.json
```

The factor pipeline is side-effect free for portfolio state. It transforms factor values that were already calculated for one signal date and does not read future prices or returns.

Factor evaluation flow:

```text
CLI factor-eval -> FactorEvaluation -> optional FactorPipeline -> SQLitePriceStore -> reports/factor_eval_*.json
```

The factor evaluation framework is side-effect free for portfolio state. It calculates factor values with signal-date-and-earlier data, then compares them to future returns.

Long-short factor backtest flow:

```text
CLI factor-backtest -> FactorBacktest -> optional FactorPipeline -> SQLitePriceStore -> reports/factor_backtest_*.json
```

The long-short factor backtest is side-effect free for portfolio state. It ranks each signal-date cross-section, longs the configured top quantile, shorts the configured bottom quantile, and measures factor returns only.

Strategy evaluation flow:

```text
CLI strategy-eval -> StrategyEvaluation -> reports/factor_backtest_*.json or reports/backtest_*.json -> reports/strategy_eval_*.json
```

The CLI may optionally generate a fresh alpha backtest or factor long-short source report first. StrategyEvaluation itself remains side-effect free for portfolio state: it reads supported reports and explains return contribution, cost attribution, turnover attribution, risk attribution, benchmark-relative results, robustness warnings, drawdowns, rolling metrics, and monthly/yearly performance.

Cost flow:

```text
CLI cost -> RebalanceEngine suggestions -> CostEngine -> reports/cost_*.json
CLI rebalance --with-costs -> RebalanceEngine -> CostEngine -> reports/cost_*.json
```

The cost engine is side-effect free for portfolio state. It estimates costs only.

Portfolio backtest flow:

```text
CLI backtest -> PortfolioBacktestEngine -> prices -> optimizer-style targets -> rebalance simulation -> CostEngine -> reports/backtest_*.json
```

The portfolio backtest engine is deterministic and runs in memory. It does not modify live simulated portfolio state.

No-lookahead alpha backtest flow:

```text
CLI backtest --strategy alpha -> PortfolioBacktestEngine -> AlphaEngine on signal date T -> next trading day execution -> CostEngine -> reports/backtest_*.json
```

The alpha backtest path uses only T and earlier rows for signal generation, then executes on the next available trading day. It records signal and execution dates in trades and equity snapshots.

Execution simulation flow:

```text
CLI execute-sim -> RebalanceEngine -> ExecutionEngine -> CostEngine -> reports/execution_*.json
```

The execution simulator is side-effect free for portfolio state. It models fills, unfilled quantities, costs, slippage, final cash, and final positions without writing `accounts`, `positions`, or `trades`.

Historical trading simulation flow:

```text
CLI trade-sim -> TradingSimulator -> AlphaEngine signal date T -> PortfolioConstructionEngine -> next trading day execution -> CostEngine -> PortfolioAccount -> reports/trade_sim_*.json
```

The trading simulator is offline and deterministic. It does not write to SQLite portfolio state, does not connect to brokers, and does not alter existing backtest semantics.

`v0.29.0` adds internal Order/Fill/AccountState protocol creation and validation inside execution and trade simulation paths. Existing reports are intentionally unchanged.

## Extension Points

- `quant/core_protocols`: stable JSON-safe protocol boundary for future MCP/OpenClaw, broker adapter, and agent integrations.
- `quant/data_layer`: stable universe, metadata, coverage, and data quality boundary for future factor research.
- `quant/agent_export`: stable report-to-agent context boundary for future OpenClaw and LLM agent integrations.
- `quant/risk`: future portfolio and strategy risk checks.
- `quant/openclaw`: future OpenClaw integration boundary.
- `quant/portfolio`: reserved for domain objects if the portfolio module grows beyond services and storage.
- `quant/alpha`: stable signal and target-weight boundary for future research callers.
- `quant/factor_backtest`: stable single-factor long-short return research boundary.
- `quant/factor_pipeline`: stable factor preprocessing boundary for future alpha and evaluation callers.
- `quant/factor_eval`: stable research diagnostics boundary for future factor and alpha research callers.
- `quant/strategy_eval`: stable report explanation and attribution boundary.
- `quant/trading_simulation`: stable offline historical account simulation boundary for future research and agent review.
- `quant/rebalance`: stable calculation boundary for future Risk Engine, OpenClaw, and AI research callers.
- `quant/risk`: stable calculation boundary for future OpenClaw Risk Agent callers.
- `quant/optimizer`: stable target-allocation boundary for future research and OpenClaw callers.
- `quant/portfolio_construction`: stable risk-aware target-construction boundary for future optimizer, backtest, and research callers.
- `quant/cost`: stable cost-estimation boundary for future Backtest and Execution Engines.
- `quant/backtest`: stable daily portfolio backtest boundary for future research callers.
- `quant/execution`: stable simulated execution boundary for future OpenClaw Execution Agent callers.

## v0.19 Factor Library

- `quant/factors`: central deterministic factor registry plus price-history factor implementations.
- `factor-list`: CLI command for factor discovery.
- Alpha can blend configured `factor_weights` into `composite_alpha_score`.
- Factor Evaluation, Factor Pipeline, and Factor Backtest resolve supported factors through the same registry.

All v0.19 factors are computed from stored rows at or before the signal date. Future returns remain labels for evaluation/backtest only.

## v0.20 Walk Forward Validation

`quant/walk_forward` is the out-of-sample validation boundary. It orchestrates existing Alpha, PortfolioBacktest, FactorEvaluation, FactorBacktest, and rolling-validation helpers. It does not change strategy, factor, or no-lookahead semantics. It produces `reports/walk_forward_*.json` for downstream Strategy Evaluation and Agent Export consumption.
