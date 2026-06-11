# Architecture

`openclaw-quant-v1` is organized as a small layered Python application.

## Layers

```text
CLI
 |
Services
 |
Storage / Data Sources
 |
SQLite / External APIs
```

## Components

- `quant.cli`: Parses user commands and prints human-readable output.
- `quant.services.price_service`: Coordinates daily price updates and reads.
- `quant.services.portfolio_service`: Applies simulated account, buy, sell, and valuation rules.
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

## Extension Points

- `quant/backtesting`: future historical simulation module.
- `quant/risk`: future portfolio and strategy risk checks.
- `quant/openclaw`: future OpenClaw integration boundary.
- `quant/portfolio`: reserved for domain objects if the portfolio module grows beyond services and storage.

