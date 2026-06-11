# Backtest Engine

The Backtest Engine runs deterministic daily portfolio backtests.

It uses:

- stored historical prices from the Data Layer
- in-memory Portfolio State simulation
- optimizer-style target generation
- alpha signal generation
- rebalance simulation
- Cost Engine estimates

It does not:

- download data
- place orders
- update live simulated positions
- connect to brokers
- call OpenClaw, Claude, GPT, or any AI model

## Command

No-lookahead alpha strategy:

```bash
python -m quant.cli backtest \
  --strategy alpha \
  --start 2024-01-01 \
  --end 2025-01-01 \
  --initial-cash 100000 \
  --rebalance-frequency monthly \
  --alpha-config examples/alpha_config.json \
  --execution-price close
```

Simple portfolio strategy:

```bash
python -m quant.cli backtest \
  --start 2024-01-01 \
  --end 2025-01-01 \
  --initial-cash 100000 \
  --mode equal_weight \
  --rebalance-frequency monthly
```

## No-Lookahead Alpha Flow

The `--strategy alpha` path is the trustworthy strategy research path.

Flow:

- On signal date T, Alpha Engine reads only price rows where `date <= T`.
- Alpha Engine generates target weights from T and earlier data.
- The target is scheduled for the next available trading date.
- Trades execute on T+1 using `--execution-price close` or `--execution-price open`.
- Cost Engine estimates are deducted from cash.
- Trades record both `signal_date` and `execution_date`.

This prevents using the same close both to generate a signal and execute the trade.

## Legacy Simple Mode

The original `equal_weight`, `risk_adjusted`, and `constrained` portfolio modes rebalance on the same date using that date's close. They are useful for smoke tests and rough plumbing checks, but they should not be treated as trustworthy strategy evaluation because they have a same-day close assumption.

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

Alpha strategy reports include:

- `strategy`
- `no_lookahead`
- `signal_execution_lag`
- `alpha_config`
- `excluded_symbols_per_rebalance`
- trade-level `signal_date` and `execution_date`
- equity-curve `last_signal_date` and `last_execution_date`

## Reproducibility

The engine uses only stored prices and explicit parameters. It simulates positions in memory and includes deterministic cost estimates, so repeated runs with the same inputs produce the same trades and metrics.
