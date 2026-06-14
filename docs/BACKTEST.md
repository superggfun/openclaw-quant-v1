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
  --rebalance-frequency monthly \
  --allow-same-day-close-simple-mode
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

Backtest valuation and execution prices are separated. Valuation can use forward-filled mark prices for daily equity continuity, but simulated trades require a real stored execution price on the execution date. If a symbol has no real execution price for that date, the engine skips that trade and records a `NOT_TRADABLE_ON_EXECUTION_DATE` warning.

## Research-Only Simple Mode

The original `equal_weight`, `risk_adjusted`, and `constrained` portfolio modes rebalance on the same date using that date's close. They are useful for smoke tests and rough plumbing checks, but they should not be treated as trustworthy strategy evaluation because they have a same-day close assumption.

This mode is disabled by default. To run it, pass `--allow-same-day-close-simple-mode` or call `PortfolioBacktestEngine.run(..., allow_same_day_close_simple_mode=True)`.

Reports from this mode include:

- `no_lookahead: false`
- `signal_execution_lag: same_day_close_simple_mode`
- `tradability_label: Research-only, same-day-close, not tradable.`
- a `RESEARCH_ONLY_SAME_DAY_CLOSE` warning

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

## Trading Simulation Relationship

`python -m quant.cli trade-sim` is a separate v0.21 account-style simulator. It preserves existing `backtest` semantics and focuses on unified historical account state: cash, positions, costs, trades, realized/unrealized PnL, and daily mark-to-market snapshots. Use `backtest` for the existing research backtest path and `trade-sim` when account state evolution is the primary object of study.
