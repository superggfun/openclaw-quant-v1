# Historical Trading Simulation

`v0.21.0` adds an offline historical trading simulation loop that behaves like an account through time. It is research infrastructure only. It does not connect to brokers, place live orders, stream real-time data, or perform high-frequency trading. It is not investment advice.

## Purpose

The simulator unifies signal generation, portfolio construction, rebalance planning, cost estimation, execution accounting, and mark-to-market portfolio state inside one historical loop.

`v0.29.0` adds internal protocol conversion for account state, trade records, orders, fills, and portfolio snapshots. These protocol objects prepare the simulator for future MCP/OpenClaw integration while preserving the existing `trade_sim` report schema.

`v0.30.0` adds deterministic market realism checks for slippage, ADV liquidity caps, position-size limits, minimum trade diagnostics, and missing-price skips. These are still historical simulation assumptions, not broker fills.

The execution model is simulated. By default it fills on the next available historical close after a signal date. Results can differ from live trading, paper trading, broker fills, opening auction behavior, intraday execution, delayed data, liquidity limits, and real slippage.

It is different from the existing backtest engine:

- `backtest` remains the existing research backtest path and its semantics are preserved.
- `trade-sim` tracks an in-memory account with cash, positions, realized PnL, unrealized PnL, costs, trade history, and daily equity.
- The simulated account is not written into the live `accounts`, `positions`, or `trades` SQLite portfolio state.
- Cost warnings such as small trade notional are reported but do not automatically delete trades.

## CLI

```bash
python -m quant.cli trade-sim --strategy alpha --start 2024-01-01 --end 2025-01-01 --initial-cash 100000 --rebalance-frequency monthly --portfolio-method equal_weight
python -m quant.cli trade-sim --strategy alpha --start 2024-01-01 --end 2025-01-01 --initial-cash 100000 --rebalance-frequency monthly --portfolio-method risk_parity
python -m quant.cli trade-sim --strategy alpha --portfolio-method equal_weight --market-realism-config examples/market_realism_config.json
```

Supported strategy:

- `alpha`

Supported portfolio construction methods:

- `equal_weight`
- `inverse_volatility`
- `risk_parity`
- `min_variance`

Supported rebalance frequencies:

- `daily`
- `weekly`
- `monthly`

## No-Lookahead Loop

For every trading date:

1. Market prices are read from stored historical data.
2. On rebalance signal dates, Alpha Engine reads only data available on or before the signal date.
3. Portfolio Construction uses only prices up to the signal date.
4. Execution is scheduled for the next available trading date by default.
5. Execution uses the next available close price unless `--execution-price open` is specified.
6. Cost Engine estimates cost for each simulated fill.
7. PortfolioAccount updates cash, positions, costs, and realized PnL.
8. Non-rebalance dates mark positions to market.

Every trade records `signal_date` and `execution_date`.

## Report

Reports are written to:

```text
reports/trade_sim_YYYYMMDD_HHMMSS.json
```

Schema includes `metadata`, `parameters`, `strategy`, `portfolio_method`, `initial_cash`, `final_equity`, `total_return`, `annual_return`, `volatility`, `sharpe`, `max_drawdown`, `total_cost`, `turnover`, `trade_count`, `equity_curve`, `cash_curve`, `positions_by_date`, `trades`, `rebalance_events`, `warnings`, and `no_lookahead`.

`v0.30.0` adds additive fields: `market_realism`, `rejected_trades`, per-trade requested/executed/rejected quantities, execution reasons, slippage cost, market impact cost, liquidity cost, ADV, and ADV participation.

## Agent Export

Trade simulation reports are supported by:

```bash
python -m quant.cli export-for-agent --report reports/trade_sim_YYYYMMDD_HHMMSS.json
```

The export summarizes strategy, portfolio method, final equity, total return, max drawdown, total cost, trade count, warnings, and next recommended checks.
