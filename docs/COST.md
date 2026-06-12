# Cost Engine

The Cost Engine estimates transaction costs for suggested trades.

It is a pure calculation module. It does not:

- Place orders.
- Update cash.
- Update positions.
- Write trades.
- Connect to brokers.
- Call OpenClaw, Claude, GPT, or any AI model.

## Models

### fixed

Applies a fixed fee per trade.

### linear

Applies commission as a percentage of notional, with a minimum commission.

### combined

Applies both fixed fee and linear commission.

## Defaults

```json
{
  "model": "combined",
  "fixed_fee": 1.0,
  "commission_rate": 0.001,
  "min_commission": 1.0,
  "slippage_bps": 5,
  "slippage_model": null,
  "market_impact_bps": 0.0,
  "liquidity_impact_rate": 0.0,
  "currency": "USD",
  "min_trade_notional": 50,
  "min_cost_efficiency_ratio": null
}
```

## Per-Trade Output

- symbol
- side
- shares
- price
- notional
- fixed fee
- commission
- slippage cost
- market impact cost
- liquidity cost
- total cost
- cost ratio

## Summary Output

- gross trade value
- total commission
- total slippage
- total market impact
- total liquidity cost
- total cost
- total cost ratio
- warnings

## Commands

```bash
python -m quant.cli cost
python -m quant.cli cost --model fixed
python -m quant.cli rebalance --targets examples/optimized_targets.json --with-costs
```

Reports are written to:

```text
reports/cost_YYYYMMDD_HHMMSS.json
```

`v0.30.0` keeps `slippage_bps` backward compatible and adds optional `slippage_model`, `market_impact_bps`, and `liquidity_impact_rate` fields. These are still offline estimates and do not represent broker quotes or live market impact.
