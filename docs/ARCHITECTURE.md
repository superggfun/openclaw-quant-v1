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

## Components

- `quant.cli`: Main CLI entry point. It builds the top-level parser, creates shared context, and dispatches to command modules.
- `quant.cli_commands`: Dedicated parser registration and command handlers for data, data layer, agent export, portfolio, rebalance, risk, optimizer, portfolio construction, alpha, factor, strategy evaluation, cost, execution, and backtest commands.
- `quant.agent_export.agent_exporter`: Converts detailed JSON reports into compact agent-friendly text, Markdown, or JSON summaries.
- `quant.data_layer.universe_manager`: Builds default, custom, sector, ETF, and large-cap universes.
- `quant.data_layer.symbol_metadata`: Stores static symbol metadata in SQLite.
- `quant.data_layer.data_quality`: Produces coverage, data quality, and research readiness reports.
- `quant.services.price_service`: Coordinates daily price updates and reads.
- `quant.services.portfolio_service`: Applies simulated account, buy, sell, and valuation rules.
- `quant.services.backtest_service`: Runs SMA crossover backtests from stored prices and writes JSON reports.
- `quant.alpha.alpha_engine`: Calculates alpha factors, ranks symbols, and generates target weights.
- `quant.factor_backtest.factor_backtest`: Runs no-lookahead equal-weight long-short factor return backtests.
- `quant.factor_pipeline.factor_pipeline`: Preprocesses same-date factor cross-sections before alpha generation or evaluation.
- `quant.factor_eval.factor_evaluation`: Evaluates factor predictive quality with no-lookahead IC, Rank IC, quintile, and decay metrics.
- `quant.strategy_eval.strategy_evaluation`: Explains returns, risk, drawdowns, rolling metrics, and attribution from generated reports.
- `quant.backtest.backtest_engine`: Runs daily portfolio backtests from stored prices, optimizer targets, rebalance logic, and costs.
- `quant.rebalance.rebalance_engine`: Calculates current allocation and rebalance suggestions from account, position, and price state.
- `quant.risk.risk_engine`: Calculates portfolio concentration, cash, Top 5, industry, and risk score metrics.
- `quant.optimizer.optimizer_engine`: Generates target allocations for the Rebalance Engine.
- `quant.portfolio_construction.portfolio_construction`: Builds target allocations from stored close prices, covariance, and risk contribution calculations.
- `quant.cost.cost_engine`: Estimates transaction costs for suggested trades.
- `quant.execution.execution_engine`: Simulates execution of rebalance suggestions and costs.
- `quant.storage.sqlite_store`: Owns the `prices` table.
- `quant.storage.portfolio_store`: Owns `accounts`, `positions`, and `trades`.
- `quant.data_source.yfinance_client`: Wraps yfinance and normalizes downloaded prices.

## Data Flow

CLI dispatch flow:

```text
python -m quant.cli -> quant.cli build_parser/create_context -> quant.cli_commands.<area>.handle
```

`v0.15.0` only refactors CLI structure. It does not change command names, arguments, output text, report schemas, or engine behavior.

Price update flow:

```text
CLI update-prices -> PriceService -> YFinanceClient -> SQLitePriceStore -> prices
```

Data layer flow:

```text
CLI universe/data commands -> UniverseManager + SymbolMetadataStore + DataQualityAnalyzer -> prices/symbol_metadata -> reports/data_*.json
```

The data layer expands research coverage and diagnostics without changing factor evaluation, factor backtest, portfolio backtest, or no-lookahead semantics.

Agent export flow:

```text
CLI export-for-agent -> AgentExporter -> existing reports/*.json -> compact text/markdown/json summary
```

The agent export layer is read-only and export-only. It does not modify source reports, quant logic, factor evaluation, backtest behavior, portfolio state, or execution behavior.

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
CLI alpha -> AlphaEngine -> optional FactorPipeline -> SQLitePriceStore -> examples/alpha_targets.json -> reports/alpha_*.json
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

## Extension Points

- `quant/backtesting`: future historical simulation module.
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
