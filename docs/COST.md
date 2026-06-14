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
  "market_impact_model": "sqrt_participation",
  "market_impact_participation_factor": 1.0,
  "market_impact_volatility_factor": 0.0,
  "liquidity_impact_rate": 0.0,
  "currency": "USD",
  "min_trade_notional": 50,
  "min_cost_efficiency_ratio": null
}
```

## Market Impact

`market_impact_bps` is the base impact in basis points. The default `market_impact_model` is `sqrt_participation`, which scales impact with the square root of ADV participation:

```text
effective_impact_bps =
  market_impact_bps * (1 + market_impact_participation_factor * sqrt(shares / ADV))
  + volatility * 10000 * market_impact_volatility_factor * sqrt(shares / ADV)
```

The volatility term is disabled by default because it requires recent volatility context on the trade. Set `market_impact_volatility_factor` when `TradeInput.volatility` is available from the liquidity model.

The code-level default profile is intentionally conservative and keeps `market_impact_bps: 0.0` and `market_impact_volatility_factor: 0.0` for backward compatibility. This means market impact is supported but not active unless configured.

For research simulations that should include a non-zero deterministic impact assumption, use the `realistic` profile:

```json
{
  "model": "combined",
  "fixed_fee": 1.0,
  "commission_rate": 0.0005,
  "min_commission": 1.0,
  "slippage_bps": 5.0,
  "market_impact_bps": 2.0,
  "market_impact_model": "sqrt_participation",
  "market_impact_participation_factor": 1.0,
  "market_impact_volatility_factor": 0.05
}
```

For backward-compatible diagnostics, `market_impact_model: "flat"` preserves the older formula:

```text
cost = notional * market_impact_bps / 10000 * max(1, shares / ADV)
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
- market impact model
- effective market impact bps
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
python -m quant.cli cost --cost-profile realistic
python -m quant.cli cost --model fixed
python -m quant.cli rebalance --targets examples/optimized_targets.json --with-costs
```

Reports are written to:

```text
reports/cost_YYYYMMDD_HHMMSS.json
```

`v0.30.0` keeps `slippage_bps` backward compatible and adds optional `slippage_model`, `market_impact_bps`, square-root ADV participation impact, and `liquidity_impact_rate` fields. These are still offline estimates and do not represent broker quotes or live market impact.
