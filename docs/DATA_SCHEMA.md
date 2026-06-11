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

## reports/rebalance_*.json

Rebalance reports are generated files, not database tables. They are ignored by git.

Top-level keys:

- `total_assets`: current cash plus current market value of positions.
- `cash_before`: current account cash.
- `cash_after_rebalance`: estimated cash after suggested trades and commissions.
- `commission_rate`: configured commission rate.
- `estimated_total_commission`: estimated commission across suggested trades.
- `items`: cash and per-symbol current/target values, differences, action, quantity, and estimated trade cost.
- `warnings`: non-blocking warnings such as cash below target allocation.

## reports/risk_*.json

Risk reports are generated files, not database tables. They are ignored by git.

Top-level keys:

- `total_assets`: current cash plus current market value of positions.
- `cash_value`: current account cash.
- `cash_weight_pct`: cash as a percent of total assets.
- `single_stock_concentration_pct`: largest single holding weight.
- `industry_concentration_pct`: largest industry group weight.
- `top_5_holdings_pct`: sum of the five largest holding weights.
- `risk_score`: 0-100 score, where higher means more risk.
- `holdings`: per-symbol value, weight, and industry.
- `industries`: per-industry value and weight.
- `warnings`: non-blocking warnings such as unknown industry mapping.
