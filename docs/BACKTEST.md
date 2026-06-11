# Backtest Engine

The V0.7 Backtest Engine runs deterministic daily portfolio backtests.

It uses:

- stored historical prices from the Data Layer
- in-memory Portfolio State simulation
- optimizer-style target generation
- rebalance simulation
- Cost Engine estimates

It does not:

- download data
- place orders
- update live simulated positions
- connect to brokers
- call OpenClaw, Claude, GPT, or any AI model

## Command

```bash
python -m quant.cli backtest \
  --start 2024-01-01 \
  --end 2025-01-01 \
  --initial-cash 100000 \
  --mode equal_weight \
  --rebalance-frequency monthly
```

Modes:

- `equal_weight`
- `risk_adjusted`
- `constrained`

Rebalance frequencies:

- `monthly`
- `weekly`
- `daily`

## Metrics

- final value
- total return
- annual return
- max drawdown
- volatility
- Sharpe ratio
- trade count
- turnover
- total cost
- cash ratio

## Reports

Reports are written to:

```text
reports/backtest_YYYYMMDD_HHMMSS.json
```

Reports are ignored by git.

## Reproducibility

The engine uses only stored prices and explicit parameters. It simulates positions in memory and includes deterministic cost estimates, so repeated runs with the same inputs produce the same trades and metrics.

