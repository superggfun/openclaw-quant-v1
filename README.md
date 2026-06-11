# openclaw-quant-v1

`openclaw-quant-v1` is an early OpenClaw-oriented quant system skeleton. It currently includes a market data layer, a simulated portfolio state module, a minimal backtest engine, a portfolio rebalance engine, a risk engine, a portfolio optimizer, and a cost engine. It does not make AI decisions, place live orders, connect to brokers, or perform automated trading.

This project is for research and simulation only. It is not investment advice.

## Current Version

`v0.6.0-cost-engine`

This release includes:

- yfinance daily OHLCV ingestion.
- SQLite price storage with idempotent updates.
- Simulated account state.
- Simulated positions and trade history.
- SMA crossover backtest engine using stored prices.
- Portfolio allocation and rebalance calculation engine.
- Portfolio risk metrics and risk score.
- Portfolio optimizer that generates target allocations.
- Transaction cost estimation for rebalance suggestions.
- JSON backtest and rebalance reports under `reports/`.
- CLI commands for data, portfolio, backtest, allocation, and rebalance workflows.
- pytest coverage for core state transitions.

## Scope

- Python 3.11+
- Daily US stock and ETF prices from Yahoo Finance through `yfinance`
- SQLite storage at `data/quant.db`
- Idempotent price updates using `(symbol, date)` as the primary key
- Simulated account, position, and trade tracking in SQLite
- Pure calculation backtest and rebalance modules
- Empty extension packages for future risk and OpenClaw integration work

Default symbols:

```text
SPY, QQQ, NVDA, AAPL, MSFT, TSLA, AMD, META, GOOGL, TLT, GLD
```

## Project Layout

```text
openclaw-quant-v1/
|- data/
|  `- quant.db
|- docs/
|- examples/
|  `- targets.json
|- quant/
|  |- config.py
|  |- data_source/
|  |- rebalance/
|  |  `- rebalance_engine.py
|  |- services/
|  |- storage/
|  |- backtesting/
|  |- portfolio/
|  |- risk/
|  |- openclaw/
|  `- cli.py
|- reports/
|- tests/
|- requirements.txt
`- README.md
```

## Architecture

The project uses a small layered architecture:

```text
CLI -> Services / Engines -> Storage / Data Sources -> SQLite / yfinance
```

Key modules:

- `quant/cli.py`: command line entry point.
- `quant/services/price_service.py`: price update orchestration.
- `quant/services/portfolio_service.py`: simulated portfolio rules and valuation.
- `quant/services/backtest_service.py`: SMA crossover backtest engine.
- `quant/rebalance/rebalance_engine.py`: allocation and rebalance calculations.
- `quant/risk/risk_engine.py`: concentration, cash, Top 5, and risk score calculations.
- `quant/optimizer/optimizer_engine.py`: target allocation generation for rebalance.
- `quant/cost/cost_engine.py`: fixed, linear, and combined transaction cost estimates.
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

```bash
python -m quant.cli update-prices
python -m quant.cli update-prices --symbols SPY QQQ AAPL
python -m quant.cli show-prices SPY --limit 5
python -m quant.cli list-symbols
```

## Simulated Portfolio Commands

```bash
python -m quant.cli init-account --cash 100000
python -m quant.cli buy SPY --qty 10 --price 500
python -m quant.cli sell SPY --qty 3 --price 510
python -m quant.cli portfolio
python -m quant.cli trades
```

## Portfolio Rebalance Engine

The rebalance engine reads the current simulated account, positions, and latest prices from SQLite. It calculates suggested trades only. It does not update positions, write trades, connect to brokers, or place orders.

Create a target file:

```json
{
  "SPY": 0.40,
  "QQQ": 0.30,
  "NVDA": 0.20,
  "cash": 0.10
}
```

Show current allocation:

```bash
python -m quant.cli allocation
```

Calculate a rebalance plan:

```bash
python -m quant.cli rebalance --targets examples/targets.json
```

Configure commission. The default is `0.001`, or 0.1%:

```bash
python -m quant.cli rebalance --targets examples/targets.json --commission 0.001
```

The rebalance report is written as:

```text
reports/rebalance_YYYYMMDD_HHMMSS.json
```

See `docs/REBALANCE.md` for details.

## Risk Engine

The risk engine reads the simulated portfolio and latest prices, then calculates:

- single-stock concentration
- industry concentration
- cash allocation
- Top 5 holdings concentration
- risk score from 0 to 100

Run:

```bash
python -m quant.cli risk
```

The risk report is written as:

```text
reports/risk_YYYYMMDD_HHMMSS.json
```

The Risk Engine is a pure calculation source for future OpenClaw Risk Agent work. It does not call OpenClaw or any AI model.

## Portfolio Optimizer

The optimizer generates target allocations that can be passed directly to the Rebalance Engine.

Supported modes:

- `equal_weight`
- `risk_adjusted`
- `constrained`

Default constraints:

- `max_position_weight`: `0.20`
- `min_cash_weight`: `0.10`
- `max_sector_weight`: `0.50`
- `only_long`: `true`

Run:

```bash
python -m quant.cli optimize
python -m quant.cli rebalance --targets examples/optimized_targets.json
python -m quant.cli rebalance --targets examples/optimized_targets.json --with-costs
```

The optimize command reads `examples/optimizer_config.json` by default and writes:

```text
examples/optimized_targets.json
reports/optimize_YYYYMMDD_HHMMSS.json
```

See `docs/OPTIMIZER.md` for details.

## Cost Engine

The cost engine estimates whether a rebalance is worth doing by calculating per-trade and total costs.

Supported models:

- `fixed`
- `linear`
- `combined`

Run:

```bash
python -m quant.cli cost
python -m quant.cli rebalance --targets examples/optimized_targets.json --with-costs
```

Default config:

```text
examples/cost_config.json
```

Reports:

```text
reports/cost_YYYYMMDD_HHMMSS.json
```

See `docs/COST.md` for details.

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
- `reports/rebalance_*.json`: generated rebalance reports, ignored by git
- `reports/risk_*.json`: generated risk reports, ignored by git
- `reports/optimize_*.json`: generated optimizer reports, ignored by git
- `reports/cost_*.json`: generated cost reports, ignored by git

## Roadmap

Near-term work:

- Add richer portfolio reporting.
- Add realized PnL tracking.
- Add basic performance metrics.
- Add more backtest strategies and benchmark comparisons.
- Add risk checks for max position size, cash usage, symbol allowlists, and rebalance suggestions.
- Add configurable sector maps and risk thresholds.
- Add optimizer modes that use return estimates and risk budgets.
- Feed Cost Engine estimates into future Backtest and Execution Engines.

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
- `docs/REBALANCE.md`
- `docs/RISK.md`
- `docs/OPTIMIZER.md`
- `docs/COST.md`
- `docs/CLI.md`
- `docs/CLI_COMMANDS.md`
- `docs/DECISIONS.md`

AI assistants should keep tests updated, avoid broker/live-trading code unless explicitly requested, and preserve existing CLI behavior unless the README and tests are updated together.

New features must include CLI coverage and pytest coverage before they are considered complete.

## Test

```bash
pytest
```

The core tests use temporary SQLite databases and a fake market data source, so they do not need network access.
