# Performance Baseline & Profiling

`v0.40.0` introduces performance measurement for OpenClaw Quant. It is a profiling release only.

It does not add numba, multiprocessing, pandarallel, swifter, parquet, vectorized backtest rewrites, parameter tuning, report schema changes, validation logic changes, or quant semantic changes.

## CLI

```bash
python -m quant.cli performance-profile
python -m quant.cli performance-profile --target factor_eval --factor momentum_20d --max-symbols 5
python -m quant.cli performance-summary
python -m quant.cli performance-report
```

`performance-profile` runs bounded profiling around existing engines. The default run is intentionally small enough for local smoke validation. Use repeated `--target` and `--factor` options to expand the measurement scope.

Supported targets:

- `factor_eval`
- `factor_backtest`
- `walk_forward`
- `strategy_run`
- `research_validation`
- `all`

## Measured Areas

The profiler records:

- total runtime by target
- runtime events by category
- database read call counts and runtime
- slowest query-like store calls
- factor target runtime
- walk-forward runtime
- strategy-run runtime
- research-validation runtime
- Factor Store ranking lookup runtime
- fundamental lookup runtime

Generated reports:

- `reports/performance_profile_YYYYMMDD_HHMMSS.json`
- `reports/performance_profile_summary.md`

## Interpretation

Recommendations are evidence-based candidates for future work. They are not implemented optimizations.

Current local v0.40 profiling found `factor_eval` as the dominant measured bottleneck. `get_price_history` and SQLite read timing are measured and visible in the report, but they are not currently the dominant share of runtime in the default profile. Optimization decisions should therefore prioritize semantic-preserving factor evaluation caching or bulk factor-row computation before larger storage migrations such as Parquet, JIT compilation, or multiprocessing.

`v0.41.0` implements the first semantic-preserving response to that evidence: an opt-in in-memory Factor Eval Cache / Bulk Factor Matrix. It is disabled by default, tested against the uncached path for metric parity, and does not add multiprocessing, numba, parquet, or any factor/backtest semantic change. See `docs/FACTOR_CACHE.md`.

`v0.41.0` also adds explicit safe parallel research-validation for independent factor batches. Worker processes compute factor-eval and factor-backtest results only; SQLite Factor Store writes remain single-process in the main runner. The portfolio/account date progression path remains serial. See `docs/FACTOR_ACCELERATION.md`.

Report write time is measured separately from compute time. Research-validation compact reports avoid embedding huge detail arrays and route optional detailed artifacts under `reports/runs/<run_id>/`, which keeps aggregate report size and Agent Export/MCP payloads manageable.

Examples:

- repeated price history reads may justify a future cache or bulk-read design
- slow fundamental lookups may justify latest-as-of caching
- slow factor evaluation may justify a later profiling-guided optimization release

`v0.40.0` deliberately stops at measurement. `v0.41.0` keeps the same evidence-based boundary by adding only semantic-preserving cache instrumentation. Future performance work must preserve no-lookahead behavior, report schemas, factor semantics, backtest semantics, and validation behavior.
