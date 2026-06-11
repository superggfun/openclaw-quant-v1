# openclaw-quant-v1

`openclaw-quant-v1` is an early OpenClaw-oriented quant system skeleton. It currently includes a market data layer, a simulated portfolio state module, and a minimal backtest engine. It does not make AI decisions, place live orders, connect to brokers, or perform automated trading.

This project is for research and simulation only. It is not investment advice.

## Current Version

`v0.2.0-backtest-engine`

This release includes:

- yfinance daily OHLCV ingestion.
- SQLite price storage with idempotent updates.
- Simulated account state.
- Simulated positions and trade history.
- SMA crossover backtest engine using stored prices.
- JSON backtest reports under `reports/`.
- CLI commands for data and portfolio workflows.
- pytest coverage for core state transitions.

## Scope

- Python 3.11+
- Daily US stock and ETF prices from Yahoo Finance through `yfinance`
- SQLite storage at `data/quant.db`
- Idempotent price updates using `(symbol, date)` as the primary key
- Simulated account, position, and trade tracking in SQLite
- Empty extension packages for future backtesting, risk, and OpenClaw integration work

Default symbols:

```text
SPY, QQQ, NVDA, AAPL, MSFT, TSLA, AMD, META, GOOGL, TLT, GLD
```

## Project Layout

```text
openclaw-quant-v1/
|- data/
|  `- quant.db
|- quant/
|  |- config.py
|  |- data_source/
|  |  `- yfinance_client.py
|  |- storage/
|  |  |- sqlite_store.py
|  |  `- portfolio_store.py
|  |- services/
|  |  |- price_service.py
|  |  `- portfolio_service.py
|  |- backtesting/
|  |- portfolio/
|  |- risk/
|  |- openclaw/
|  `- cli.py
|- tests/
|- requirements.txt
`- README.md
```

## Architecture

The project uses a small layered architecture:

```text
CLI -> Services -> Storage / Data Sources -> SQLite / yfinance
```

Key modules:

- `quant/cli.py`: command line entry point.
- `quant/services/price_service.py`: price update orchestration.
- `quant/services/portfolio_service.py`: simulated portfolio rules and valuation.
- `quant/services/backtest_service.py`: SMA crossover backtest engine.
- `quant/storage/sqlite_store.py`: price persistence.
- `quant/storage/portfolio_store.py`: account, position, and trade persistence.
- `quant/data_source/yfinance_client.py`: yfinance adapter.

More detail is available in `docs/ARCHITECTURE.md`.

## Install

From WSL2:

```bash
cd /mnt/c/Users/Alphay/Desktop/qua/openclaw-quant-v1
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

## Market Data Commands

Update the default symbol pool:

```bash
python -m quant.cli update-prices
```

Update selected symbols:

```bash
python -m quant.cli update-prices --symbols SPY QQQ AAPL
```

Show recent prices:

```bash
python -m quant.cli show-prices SPY --limit 5
```

List configured and stored symbols:

```bash
python -m quant.cli list-symbols
```

## Simulated Portfolio Commands

Initialize or reset the default simulated account:

```bash
python -m quant.cli init-account --cash 100000
```

Record a simulated buy. The command checks that cash is sufficient before writing the trade:

```bash
python -m quant.cli buy SPY --qty 10 --price 500
```

Record a simulated sell. The command checks that the position is sufficient before writing the trade:

```bash
python -m quant.cli sell SPY --qty 3 --price 510
```

Show the portfolio. Current prices are read from the latest `close` in the existing `prices` table:

```bash
python -m quant.cli portfolio
```

Show trade history:

```bash
python -m quant.cli trades
```

## Backtest Engine

The backtest engine reads historical prices from the existing `prices` table. It does not download data. Load price data first with `update-prices`.

Default strategy: SMA crossover.

- Short SMA default: 20 days
- Long SMA default: 50 days
- Buy when the short SMA crosses above the long SMA
- Sell when the short SMA crosses below the long SMA
- Position size is calculated by code using available cash and close price

Example:

```bash
python -m quant.cli update-prices --symbols SPY --start 2023-01-01 --end 2024-12-31
python -m quant.cli backtest --symbol SPY --start 2023-01-01 --end 2024-12-31
```

Custom parameters:

```bash
python -m quant.cli backtest \
  --symbol SPY \
  --start 2023-01-01 \
  --end 2024-12-31 \
  --cash 100000 \
  --short-window 20 \
  --long-window 50 \
  --commission 1
```

The CLI prints a concise summary and writes a JSON report like:

```text
reports/backtest_SPY_YYYYMMDD_HHMMSS.json
```

The database path defaults to `data/quant.db`. You can override it with either:

```bash
python -m quant.cli --db-path /tmp/openclaw-quant.db portfolio
```

or:

```bash
export OPENCLAW_QUANT_DB_PATH=/tmp/openclaw-quant.db
```

## SQLite Tables

- `prices`: daily OHLCV data from yfinance
- `accounts`: simulated account cash and initial cash
- `positions`: current simulated positions
- `trades`: simulated trade ledger
- `reports/backtest_*.json`: generated backtest reports, ignored by git

## Roadmap

Near-term work:

- Add richer portfolio reporting.
- Add realized PnL tracking.
- Add basic performance metrics.
- Add more backtest strategies and benchmark comparisons.
- Add risk checks for max position size, cash usage, and symbol allowlists.

Out of scope until explicitly designed:

- Broker integration.
- Live trading.
- Automated order execution.
- AI decision execution.

See `docs/ROADMAP.md` for the longer roadmap.

## For AI Developers

Start with `docs/AI_DEVELOPMENT.md` before changing code. It links the stable project context, architecture, schema, CLI behavior, and design decisions.

Important docs:

- `docs/AI_DEVELOPMENT.md`
- `docs/ARCHITECTURE.md`
- `docs/ROADMAP.md`
- `docs/DATA_SCHEMA.md`
- `docs/CLI_COMMANDS.md`
- `docs/DECISIONS.md`

AI assistants should keep tests updated, avoid broker/live-trading code unless explicitly requested, and preserve existing CLI behavior unless the README and tests are updated together.

New features must include CLI coverage and pytest coverage before they are considered complete.

## Test

```bash
pytest
```

The core tests use temporary SQLite databases and a fake market data source, so they do not need network access.
