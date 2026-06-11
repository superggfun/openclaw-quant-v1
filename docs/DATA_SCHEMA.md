# Data Schema

The default SQLite database is `data/quant.db`.

## prices

Daily OHLCV price data.

Primary key:

- `(symbol, date)`

Columns:

- `symbol`: ticker symbol.
- `date`: trading date in `YYYY-MM-DD`.
- `open`: daily open.
- `high`: daily high.
- `low`: daily low.
- `close`: daily close.
- `adj_close`: adjusted close.
- `volume`: daily volume.
- `created_at`: insertion timestamp.
- `updated_at`: update timestamp.

## accounts

Simulated account state.

Columns:

- `id`: account id.
- `name`: unique account name.
- `cash`: current cash.
- `initial_cash`: initial cash.
- `created_at`: insertion timestamp.
- `updated_at`: update timestamp.

## positions

Current simulated holdings.

Primary key:

- `(account_id, symbol)`

Columns:

- `account_id`: account id.
- `symbol`: ticker symbol.
- `qty`: current quantity.
- `avg_cost`: average cost.
- `updated_at`: update timestamp.

## trades

Append-only simulated trade ledger.

Columns:

- `id`: trade id.
- `account_id`: account id.
- `symbol`: ticker symbol.
- `side`: `BUY` or `SELL`.
- `qty`: executed quantity.
- `price`: executed price.
- `amount`: `qty * price`.
- `created_at`: trade timestamp.

## reports/backtest_*.json

Backtest reports are generated files, not database tables. They are ignored by git.

Top-level keys:

- `metrics`: symbol, period, initial cash, final value, return, drawdown, Sharpe ratio, trade count, and win rate.
- `trades`: deterministic simulated backtest executions.
- `equity_curve`: daily cash, position, close, and equity values.
