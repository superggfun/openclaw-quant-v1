# Risk Engine

The Risk Engine calculates portfolio risk metrics from the simulated portfolio.

It is a pure calculation module. It does not:

- Place orders.
- Update cash.
- Update positions.
- Write trades.
- Connect to brokers.
- Call OpenClaw, Claude, GPT, or any AI model.

## Metrics

The engine calculates:

- single-stock concentration
- industry concentration
- cash allocation
- Top 5 holdings concentration
- risk score from 0 to 100

Higher risk score means higher concentration or cash-allocation risk.

## Industry Mapping

The current implementation uses a static industry map for the default universe:

- Technology
- Communication Services
- Consumer Discretionary
- Equity ETF
- Bond ETF
- Commodity ETF

Unknown symbols are grouped as `Unknown` and produce a warning.

## Risk Score

Risk score is deterministic and based on:

- largest single holding weight
- largest industry group weight
- Top 5 holdings weight
- cash below 5% or above 50%

It is a research and simulation metric only. It is not investment advice.

## Command

```bash
python -m quant.cli risk
```

Reports are written to:

```text
reports/risk_YYYYMMDD_HHMMSS.json
```

