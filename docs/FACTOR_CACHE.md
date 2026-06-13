# Factor Eval Cache / Bulk Factor Matrix

`v0.41.0` adds an opt-in in-memory factor matrix cache for Factor Evaluation and bounded Research Validation.

This is a semantic-preserving performance release. It does not add factors, change IC or Rank IC calculations, change future-return labels, change factor backtest semantics, change walk-forward semantics, change research-validation semantics, add multiprocessing, add numba, add parquet, or weaken no-lookahead rules.

## What Is Cached

The cache stores a bulk factor matrix for one evaluation key:

- `signal_date`
- `symbol`
- `factor_name`
- `factor_value`
- `future_return`
- `forward_days`
- `valid`

The matrix is built with the same no-lookahead observation path used by uncached Factor Evaluation. Cached and uncached metrics must match within strict test tolerance.

## Cache Keys

Cache keys include:

- factor name
- normalized universe hash
- start date
- end date
- forward days
- factor version
- newest stored price date in the universe
- `no_lookahead = true`

Changing data, universe, factor version, date range, or forward return horizon produces a different key.

## No-Lookahead

Price factors still receive only close history through `signal_date`.

Fundamental factors still use the report-date-aware lookup:

```text
report_date <= signal_date
```

`fiscal_period_end` alone is never treated as tradable availability. Cached fundamental factor values are built after the same report-date filter as uncached values.

## CLI

```bash
python -m quant.cli factor-eval --factor momentum_20d
python -m quant.cli factor-eval --factor momentum_20d --use-cache --cache-stats
python -m quant.cli factor-eval --factor fundamental_quality_score --use-cache --cache-stats
python -m quant.cli research-validation --mode quick --max-symbols 20 --max-factors 3 --use-cache --cache-stats
```

`--use-cache` enables the process-local matrix cache.

`--cache-stats` prints cache diagnostics.

`--bulk-matrix` builds and consumes a matrix without cache reuse. This is useful for testing the matrix path without retaining state.

## Report Metadata

When cache or bulk matrix mode is used, `factor_eval` reports may include optional `performance_metadata` fields:

- `cache_enabled`
- `cache_hits`
- `cache_misses`
- `matrix_rows`
- `matrix_build_seconds`
- `eval_seconds`
- `speedup_estimate`
- `cache_stats`

Old metric fields remain unchanged.

`research-validation` reports include `cache_summary` when cache stats are requested or cache is enabled.

## Boundaries

The cache is in-memory only for v0.41. It is not Parquet, not a persistent factor store, and not a distributed cache. SQLite persistence can be considered later only if invalidation and no-lookahead rules remain explicit.

The cache is disabled by default. Existing CLI workflows behave as before unless the user passes cache flags.
