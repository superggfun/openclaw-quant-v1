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
- `quant.rebalance.rebalance_engine`: Calculates current allocation and rebalance suggestions from account, position, and price state.
- `quant.risk.risk_engine`: Calculates portfolio concentration, cash, Top 5, industry, and risk score metrics.
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

## Extension Points

- `quant/backtesting`: future historical simulation module.
- `quant/risk`: future portfolio and strategy risk checks.
- `quant/openclaw`: future OpenClaw integration boundary.
- `quant/portfolio`: reserved for domain objects if the portfolio module grows beyond services and storage.
- `quant/rebalance`: stable calculation boundary for future Risk Engine, OpenClaw, and AI research callers.
- `quant/risk`: stable calculation boundary for future OpenClaw Risk Agent callers.
