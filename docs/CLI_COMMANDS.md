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
python -m quant.cli risk
python -m quant.cli alpha
python -m quant.cli optimize
python -m quant.cli cost
python -m quant.cli execute-sim --targets examples/optimized_targets.json
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

## Risk

```bash
python -m quant.cli risk
```

The risk command calculates concentration, cash exposure, Top 5 holdings concentration, industry concentration, and a 0-100 risk score. It writes a JSON report and does not modify the simulated account.

## Alpha

```bash
python -m quant.cli alpha
python -m quant.cli alpha --output-targets examples/alpha_targets.json
python -m quant.cli rebalance --targets examples/alpha_targets.json --with-costs
```

The alpha command reads `examples/alpha_config.json` by default, calculates momentum, volatility, and risk-adjusted momentum factors, ranks symbols, selects Top N, and generates target weights. It writes a JSON report and does not modify the simulated account. Alpha uses only rows at or before `as_of_date`; generated targets should be executed or backtested on the next trading day.

## Optimize

```bash
python -m quant.cli optimize
python -m quant.cli optimize --mode risk_adjusted
python -m quant.cli optimize --mode constrained --max-position-weight 0.15
python -m quant.cli rebalance --targets examples/optimized_targets.json
```

The optimize command reads `examples/optimizer_config.json` by default, writes `examples/optimized_targets.json`, and writes a JSON report. It does not modify the simulated account.

## Cost

```bash
python -m quant.cli cost
python -m quant.cli cost --model fixed
python -m quant.cli cost --targets examples/optimized_targets.json --config examples/cost_config.json
python -m quant.cli rebalance --targets examples/optimized_targets.json --with-costs
```

The cost command estimates costs for current rebalance suggestions. It writes a JSON report and does not modify the simulated account.

## Execution Simulation

```bash
python -m quant.cli execute-sim --targets examples/optimized_targets.json
python -m quant.cli execute-sim --targets examples/optimized_targets.json --mode next_day_open --date 2024-01-02
python -m quant.cli execute-sim --targets examples/optimized_targets.json --mode twap --twap-slices 4
python -m quant.cli execute-sim --targets examples/optimized_targets.json --mode partial_fill --fill-ratio 0.5
```

The execution simulator turns rebalance suggestions into simulated fills, unfilled quantities, costs, final cash, and final positions. It writes a JSON report and does not modify the simulated account.

## Backtest

Backtests use existing rows in the `prices` table. Load prices first:

```bash
python -m quant.cli update-prices --symbols SPY --start 2023-01-01 --end 2024-12-31
python -m quant.cli backtest --start 2023-01-01 --end 2024-12-31 --initial-cash 100000 --mode equal_weight --rebalance-frequency monthly
```

Optional parameters:

```bash
python -m quant.cli backtest \
  --start 2023-01-01 \
  --end 2024-12-31 \
  --initial-cash 100000 \
  --mode risk_adjusted \
  --rebalance-frequency weekly
```

Legacy SMA single-symbol backtests remain available with `--symbol`.

## Failure Behavior

- Buying without enough cash returns a non-zero exit code and prints `Error: insufficient cash`.
- Selling without enough position returns a non-zero exit code and prints `Error: insufficient position`.
- Portfolio commands require an initialized account.
- Backtest with no stored prices returns a non-zero exit code and a clear missing-data error.
- Backtest rejects `short_window >= long_window`.
- Rebalance rejects target weights that do not sum to `1.0`.
- Rebalance requires latest prices for target symbols and held symbols.
- Risk requires latest prices for held symbols.
- Alpha requires enough stored price history for at least one symbol in the universe.
- Optimize requires at least one symbol in the optimizer universe with stored price data.
- Cost requires a target allocation that can produce rebalance suggestions.
- Execution simulation requires an initialized account, target allocation, and latest prices for target and held symbols.
