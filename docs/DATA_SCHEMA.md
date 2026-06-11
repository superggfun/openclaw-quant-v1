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

- `start`, `end`: requested backtest period.
- `initial_cash`: initial simulated cash.
- `mode`: optimizer mode.
- `rebalance_frequency`: monthly, weekly, or daily.
- `metrics`: final value, returns, drawdown, volatility, Sharpe ratio, trade count, turnover, total cost, and cash ratio.
- `trades`: deterministic simulated backtest executions with costs.
- `equity_curve`: daily cash, positions, and equity values.

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

## reports/optimize_*.json

Optimizer reports are generated files, not database tables. They are ignored by git.

Top-level keys:

- `mode`: optimizer mode.
- `current_allocation`: current cash and holding weights.
- `optimized_allocation`: target weights compatible with `rebalance --targets`.
- `constraints`: constraints used by the optimizer.
- `warnings`: skipped symbols or constraint adjustments.
- `risk_score_before`: current Risk Engine score.
- `estimated_risk_score_after`: estimated score using optimized target weights.
- `rationale`: human-readable explanation of the optimizer path.
- `targets_path`: target allocation JSON path.

## reports/alpha_*.json

Alpha reports are generated files, not database tables. They are ignored by git.

Top-level keys:

- `config`: alpha config used for the run.
- `as_of_date`: resolved signal date used for the selected symbols.
- `data_start_date`: earliest selected data row used by the long lookback.
- `data_end_date`: latest selected data row used by the signal.
- `lookback_used`: factor lookback settings.
- `factors`: per-symbol factor values, rank, and selected flag.
- `selected_symbols`: selected ranked symbols.
- `target_weights`: target weights compatible with `rebalance --targets`.
- `excluded_symbols`: symbols excluded from ranking.
- `exclusion_reasons`: per-symbol exclusion reason.
- `suggested_execution_date`: next stored trading date after the signal date when available.
- `warnings`: missing data or weighting fallback warnings.
- `targets_path`: optional target allocation JSON path.

## reports/cost_*.json

Cost reports are generated files, not database tables. They are ignored by git.

Top-level keys:

- `model`: `fixed`, `linear`, or `combined`.
- `currency`: reporting currency.
- `config`: cost model parameters.
- `trades`: per-trade symbol, side, shares, price, notional, fees, slippage, total cost, and cost ratio.
- `gross_trade_value`: sum of trade notionals.
- `total_commission`: fixed plus linear commissions.
- `total_slippage`: slippage cost.
- `total_cost`: all estimated costs.
- `total_cost_ratio`: total cost divided by gross trade value.
- `warnings`: small trades or poor cost efficiency warnings.

## reports/execution_*.json

Execution simulation reports are generated files, not database tables. They are ignored by git.

Top-level keys:

- `mode`: `immediate`, `next_day_open`, `twap`, or `partial_fill`.
- `target_allocation`: target weights used for rebalance suggestions.
- `intended_trades`: Rebalance Engine suggestions before execution simulation.
- `executed_trades`: simulated fills with per-fill costs.
- `unfilled_trades`: quantities that were not filled and reasons.
- `execution_costs`: gross value, commission, slippage, total cost, and cost ratio.
- `slippage_estimate`: total simulated slippage cost.
- `final_cash`: cash after simulated fills and costs.
- `final_positions`: simulated ending quantities.
- `warnings`: non-blocking warnings.
