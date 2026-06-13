# Factor Acceleration

`v0.41.0` adds optional, semantic-preserving acceleration for factor research.

## Scope

- Bulk price reads through `SQLitePriceStore.get_price_history_many`.
- Bulk factor observation matrices under `quant/factor_acceleration`.
- Optional factor-eval bulk matrix mode through `--bulk-matrix`.
- Optional research-validation factor batch parallelism through `--parallel`.
- Reused factor value series for bulk decay calculations.
- Optional factor-backtest reuse of the same observation matrix builder.

## Semantics

The acceleration layer does not add factors, change IC or Rank IC formulas, alter future-return formulas, weaken no-lookahead checks, or change strategy behavior. Price factor values use signal-date-and-earlier prices only. Fundamental factors continue to use `report_date <= signal_date`.

Bulk matrix mode is explicit. Default serial behavior remains available.

## Parallel Safety

Research-validation workers compute independent factor batches only. Workers do not write Factor Store, regime history, or final research reports. The main process performs SQLite writes and final report generation after worker results are collected in deterministic order.

Stateful portfolio/account simulation remains serial because daily cash and position progression depends on previous dates.

## Deferred Work

Parquet, Numba, swifter, pandarallel, broker integration, and live trading are intentionally out of scope.

## CLI

```bash
python -m quant.cli factor-eval --factor momentum_20d --bulk-matrix --cache-stats
python -m quant.cli research-validation --mode quick --max-symbols 20 --max-factors 3 --bulk-matrix --parallel --workers 4 --cache-stats
```
