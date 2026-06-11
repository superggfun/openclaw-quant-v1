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
```

## Failure Behavior

- Buying without enough cash returns a non-zero exit code and prints `Error: insufficient cash`.
- Selling without enough position returns a non-zero exit code and prints `Error: insufficient position`.
- Portfolio commands require an initialized account.

