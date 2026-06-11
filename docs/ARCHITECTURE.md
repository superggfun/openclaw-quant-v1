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

- `quant.cli`: Parses user commands and prints human-readable output.
- `quant.services.price_service`: Coordinates daily price updates and reads.
- `quant.services.portfolio_service`: Applies simulated account, buy, sell, and valuation rules.
- `quant.services.backtest_service`: Runs SMA crossover backtests from stored prices and writes JSON reports.
- `quant.alpha.alpha_engine`: Calculates alpha factors, ranks symbols, and generates target weights.
- `quant.backtest.backtest_engine`: Runs daily portfolio backtests from stored prices, optimizer targets, rebalance logic, and costs.
- `quant.rebalance.rebalance_engine`: Calculates current allocation and rebalance suggestions from account, position, and price state.
- `quant.risk.risk_engine`: Calculates portfolio concentration, cash, Top 5, industry, and risk score metrics.
- `quant.optimizer.optimizer_engine`: Generates target allocations for the Rebalance Engine.
- `quant.cost.cost_engine`: Estimates transaction costs for suggested trades.
- `quant.execution.execution_engine`: Simulates execution of rebalance suggestions and costs.
- `quant.storage.sqlite_store`: Owns the `prices` table.
- `quant.storage.portfolio_store`: Owns `accounts`, `positions`, and `trades`.
- `quant.data_source.yfinance_client`: Wraps yfinance and normalizes downloaded prices.

## Data Flow

Price update flow:

```text
CLI update-prices -> PriceService -> YFinanceClient -> SQLitePriceStore -> prices
```

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

Alpha flow:

```text
CLI alpha -> AlphaEngine -> SQLitePriceStore -> examples/alpha_targets.json -> reports/alpha_*.json
```

The alpha engine is side-effect free for portfolio state. It reads stored prices, calculates factors and ranks, and generates target weights for downstream rebalance workflows.

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

Execution simulation flow:

```text
CLI execute-sim -> RebalanceEngine -> ExecutionEngine -> CostEngine -> reports/execution_*.json
```

The execution simulator is side-effect free for portfolio state. It models fills, unfilled quantities, costs, slippage, final cash, and final positions without writing `accounts`, `positions`, or `trades`.

## Extension Points

- `quant/backtesting`: future historical simulation module.
- `quant/risk`: future portfolio and strategy risk checks.
- `quant/openclaw`: future OpenClaw integration boundary.
- `quant/portfolio`: reserved for domain objects if the portfolio module grows beyond services and storage.
- `quant/alpha`: stable signal and target-weight boundary for future research callers.
- `quant/rebalance`: stable calculation boundary for future Risk Engine, OpenClaw, and AI research callers.
- `quant/risk`: stable calculation boundary for future OpenClaw Risk Agent callers.
- `quant/optimizer`: stable target-allocation boundary for future research and OpenClaw callers.
- `quant/cost`: stable cost-estimation boundary for future Backtest and Execution Engines.
- `quant/backtest`: stable daily portfolio backtest boundary for future research callers.
- `quant/execution`: stable simulated execution boundary for future OpenClaw Execution Agent callers.
