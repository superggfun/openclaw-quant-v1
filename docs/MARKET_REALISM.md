# Market Realism

`v0.30.0` adds a market realism layer for historical simulation. It improves execution assumptions inside offline `trade-sim` and `execute-sim` workflows.

This is not broker integration, live trading, high-frequency trading, tick data, intraday data, machine learning, or investment advice.

## Purpose

Earlier simulations assumed that if a price existed, a trade could fully execute at that price after cost estimation. `v0.30.0` adds explicit checks for:

- slippage
- average daily volume
- liquidity participation caps
- position size limits
- minimum trade size
- missing execution prices
- rejected or partially filled simulated trades

The layer is deterministic and uses only stored daily OHLCV history.

## Components

- `quant/engines/execution/liquidity_model.py`: estimates ADV, average daily notional, and rolling volatility from stored daily bars.
- `quant/engines/execution/slippage_model.py`: estimates fixed, bps, volume-scaled, or volatility-scaled slippage.
- `quant/engines/execution/execution_constraints.py`: applies marketability, liquidity, and position-size constraints.
- `quant/engines/execution/marketability.py`: stores marketability diagnostics.

## Slippage Models

Supported slippage models:

- `fixed`: fixed dollar slippage per trade.
- `bps`: basis-points slippage on notional.
- `volume_scaled`: slippage scales with trade size divided by ADV.
- `volatility_scaled`: slippage scales with recent daily volatility.

Existing `slippage_bps` settings still work and map to the `bps` model.

## Liquidity Constraints

ADV is estimated from stored volume history using a configurable lookback. When `max_adv_participation` is set, requested shares are capped to:

```text
floor(ADV * max_adv_participation)
```

If the trade is capped, the report emits `WARN_LIQUIDITY_CAP` and records requested, executed, and rejected quantities.

The code-level default leaves ADV caps disabled for backward-compatible library calls. The example config `examples/market_realism_config.json` enables a 5% ADV cap for CLI simulation.

## Missing Price Handling

If an execution price is missing or invalid, the trade is not executed. Reports record:

- `execution_status: SKIPPED_NO_PRICE`
- `execution_reason: SKIPPED_NO_PRICE`
- `WARN_NO_PRICE`

The account is not mutated for skipped trades.

## Reports

`trade_sim` reports now include additive market-realism fields:

- `market_realism`
- `rejected_trades`
- per-trade `requested_quantity`
- per-trade `executed_quantity`
- per-trade `rejected_quantity`
- per-trade `execution_reason`
- per-trade `slippage_cost`
- per-trade `market_impact_cost`
- per-trade `liquidity_cost`
- ADV participation fields

Existing account, equity, trade, rebalance, and no-lookahead fields remain available.

## CLI

```bash
python -m quant.cli trade-sim --strategy alpha --start 2024-01-01 --end 2025-01-01 --portfolio-method equal_weight
python -m quant.cli trade-sim --strategy alpha --portfolio-method risk_parity --market-realism-config examples/market_realism_config.json
```

`execute-sim` also includes market realism fields in its execution report when cost config supplies `market_realism` settings.

## Agent Export and Visualization

Agent Export summarizes cost drag, slippage, market impact, liquidity cost, rejected trade count, largest constrained trades, and warnings such as `WARN_LIQUIDITY_CAP`, `WARN_HIGH_SLIPPAGE`, and `WARN_NO_PRICE`.

Visualization can generate charts for slippage, cost breakdown, rejected trades, and liquidity usage when the source report contains the required fields.

## Boundary

Market realism improves historical simulation assumptions. It does not make the system a live execution platform, does not guarantee live fill quality, and does not replace broker-side market data or order management.
