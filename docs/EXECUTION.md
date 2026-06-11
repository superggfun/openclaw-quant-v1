# Execution Simulator

The Execution Simulator models how rebalance suggestions could be filled. It is a simulation layer only. It does not connect to brokers, place live orders, or update the persistent simulated account.

## Flow

```text
target allocation -> RebalanceEngine -> intended trades -> ExecutionEngine -> CostEngine -> execution report
```

## Command

```bash
python -m quant.cli execute-sim --targets examples/optimized_targets.json
```

Optional modes:

```bash
python -m quant.cli execute-sim --targets examples/optimized_targets.json --mode immediate
python -m quant.cli execute-sim --targets examples/optimized_targets.json --mode next_day_open --date 2024-01-02
python -m quant.cli execute-sim --targets examples/optimized_targets.json --mode twap --twap-slices 4
python -m quant.cli execute-sim --targets examples/optimized_targets.json --mode partial_fill --fill-ratio 0.5
```

## Modes

- `immediate`: executes each suggested trade once at the latest rebalance price, or the specified date close.
- `next_day_open`: executes each suggested trade once at the first stored open after `--date`.
- `twap`: splits each suggested trade into equal integer-share batches.
- `partial_fill`: fills a configured ratio and reports the remaining quantity as unfilled.

## Inputs

- current simulated account cash
- current simulated positions
- target allocation JSON
- stored prices from `prices`
- optional cost config JSON

## Outputs

The report includes:

- `intended_trades`
- `executed_trades`
- `unfilled_trades`
- `execution_costs`
- `slippage_estimate`
- `final_cash`
- `final_positions`
- `warnings`

Reports are written as:

```text
reports/execution_YYYYMMDD_HHMMSS.json
```

## Design Boundary

The simulator is side-effect free for portfolio state. It reads account and price data, but it does not write `accounts`, `positions`, or `trades`.

Future OpenClaw Execution Agent work should consume this report shape before any real execution API is designed.
