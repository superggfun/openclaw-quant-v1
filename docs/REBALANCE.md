# Portfolio Rebalance Engine

The Rebalance Engine calculates allocation drift and suggested trades for the simulated portfolio.

It is a pure calculation module. It does not:

- Place orders.
- Update cash.
- Update positions.
- Write trades.
- Connect to brokers.
- Call OpenClaw, Claude, GPT, or any AI model.

## Inputs

The engine reads:

- `accounts`: current simulated cash.
- `positions`: current simulated holdings.
- `prices`: latest close for each held or targeted symbol.
- target allocation JSON.

Example target file:

```json
{
  "SPY": 0.40,
  "QQQ": 0.30,
  "NVDA": 0.20,
  "cash": 0.10
}
```

Target weights must sum to `1.0`.

## Calculation

The engine computes:

- current total assets
- current value per symbol
- current allocation per symbol
- target value per symbol
- difference between target and current value
- suggested integer-share buy or sell quantity
- estimated commission
- estimated cash after rebalance

Buy quantity is calculated from available target difference, latest price, and commission. Sell quantity is calculated from target difference, latest price, and current shares.

## Commission Model

The default commission rate is:

```text
0.001 = 0.1%
```

Estimated commission is:

```text
trade_notional * commission_rate
```

CLI example:

```bash
python -m quant.cli rebalance --targets examples/targets.json --commission 0.001
```

## Commands

Show current allocation:

```bash
python -m quant.cli allocation
```

Calculate rebalance suggestions:

```bash
python -m quant.cli rebalance --targets examples/targets.json
```

Reports are written to:

```text
reports/rebalance_YYYYMMDD_HHMMSS.json
```

Generated reports are ignored by git.

