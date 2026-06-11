# CLI Commands

Run commands from the project root:

```bash
python -m quant.cli <command>
```

Use a custom database path:

```bash
python -m quant.cli --db-path /tmp/openclaw-quant.db <command>
```

## Market Data

```bash
python -m quant.cli update-prices
python -m quant.cli update-prices --symbols SPY QQQ AAPL
python -m quant.cli show-prices SPY --limit 5
python -m quant.cli list-symbols
```

## Simulated Portfolio

```bash
python -m quant.cli init-account --cash 100000
python -m quant.cli buy SPY --qty 10 --price 500
python -m quant.cli sell SPY --qty 3 --price 510
python -m quant.cli portfolio
python -m quant.cli trades
python -m quant.cli allocation
python -m quant.cli rebalance --targets examples/targets.json
```

## Rebalance

Target files are JSON objects whose values sum to `1.0`:

```json
{
  "SPY": 0.4,
  "QQQ": 0.3,
  "NVDA": 0.2,
  "cash": 0.1
}
```

Commands:

```bash
python -m quant.cli allocation
python -m quant.cli rebalance --targets examples/targets.json
python -m quant.cli rebalance --targets examples/targets.json --commission 0.001
```

The rebalance command calculates suggested trades and writes a JSON report. It does not modify the simulated account.

## Backtest

Backtests use existing rows in the `prices` table. Load prices first:

```bash
python -m quant.cli update-prices --symbols SPY --start 2023-01-01 --end 2024-12-31
python -m quant.cli backtest --symbol SPY --start 2023-01-01 --end 2024-12-31
```

Optional parameters:

```bash
python -m quant.cli backtest \
  --symbol SPY \
  --start 2023-01-01 \
  --end 2024-12-31 \
  --cash 100000 \
  --short-window 20 \
  --long-window 50 \
  --commission 0
```

## Failure Behavior

- Buying without enough cash returns a non-zero exit code and prints `Error: insufficient cash`.
- Selling without enough position returns a non-zero exit code and prints `Error: insufficient position`.
- Portfolio commands require an initialized account.
- Backtest with no stored prices returns a non-zero exit code and a clear missing-data error.
- Backtest rejects `short_window >= long_window`.
- Rebalance rejects target weights that do not sum to `1.0`.
- Rebalance requires latest prices for target symbols and held symbols.

