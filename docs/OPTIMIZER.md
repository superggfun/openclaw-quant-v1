# Portfolio Optimizer

The Portfolio Optimizer generates target allocations that can be passed directly to the Rebalance Engine.

It is a pure calculation module. It does not:

- Place orders.
- Update cash.
- Update positions.
- Write trades.
- Connect to brokers.
- Call OpenClaw, Claude, GPT, or any AI model.

## Modes

### equal_weight

Distributes investable weight evenly across symbols with stored price data.

### risk_adjusted

Uses stored price history to estimate recent volatility. Higher-volatility symbols receive lower weights.

### constrained

Starts from equal weights and applies portfolio constraints.

## Default Universe

```text
SPY, QQQ, NVDA, AAPL, MSFT, TSLA, AMD, META, GOOGL, TLT, GLD
```

Symbols without stored price data are skipped with warnings. If no symbol has price data, the optimizer raises a clear error.

## Constraints

Defaults:

```json
{
  "max_position_weight": 0.20,
  "min_cash_weight": 0.10,
  "max_sector_weight": 0.50,
  "only_long": true
}
```

Rules:

- single position weight cannot exceed `max_position_weight`
- cash weight is at least `min_cash_weight`
- sector weight cannot exceed `max_sector_weight`
- weights are long-only when `only_long` is true
- total target allocation is kept at `1.0`

## Command

```bash
python -m quant.cli optimize
```

Optional:

```bash
python -m quant.cli optimize --mode risk_adjusted
python -m quant.cli optimize --mode constrained --max-position-weight 0.15
```

The default config is:

```text
examples/optimizer_config.json
```

The default targets output is:

```text
examples/optimized_targets.json
```

The generated target file can be passed to rebalance:

```bash
python -m quant.cli rebalance --targets examples/optimized_targets.json
```

Reports are written to:

```text
reports/optimize_YYYYMMDD_HHMMSS.json
```

