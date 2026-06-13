# Research Validation & Coverage Expansion

`v0.39.0` freezes feature development and uses the existing platform to collect evidence about factors, strategies, warnings, validation risk, coverage, and regime samples.

`v0.38.0` was folded into `v0.39.0` before release. The original unbounded validation sprint was too slow for local release QA, so `v0.39.0` ships the bounded validation workflow plus coverage expansion diagnostics together.

This is a research validation and evidence-quality workflow, not a quant feature release. It does not add factors, data providers, MCP features, broker integrations, live trading, machine learning, news sentiment, new strategy logic, parameter tuning, or warning suppression.

Warning-heavy output is expected and meaningful in this release. The point of v0.39 is to expose weak evidence, sparse coverage, low-sample regimes, partial runs, and runtime bottlenecks instead of hiding them.

## CLI

```bash
python -m quant.cli research-validation --mode quick
python -m quant.cli research-validation --mode quick --start 2024-01-01 --end 2026-06-11
python -m quant.cli research-validation --mode quick --max-factors 5 --max-strategies 2 --max-folds 1 --timeout-seconds 180
python -m quant.cli research-validation --mode quick --max-symbols 50 --factor-family price --batch-size 10
python -m quant.cli research-validation --mode quick --max-symbols 50 --factor-family fundamental --batch-size 10
python -m quant.cli research-validation --mode quick --max-symbols 20 --max-factors 3 --use-cache --cache-stats
python -m quant.cli research-validation --mode full --max-folds 5 --timeout-seconds 3600
```

## Modes

`quick` is the bounded local smoke/research mode. By default it uses one representative factor, one Strategy DSL strategy, a small validation universe (`SPY`, `QQQ`, `NVDA`, `AAPL`, `MSFT`), `max_folds=1`, a shorter runtime budget, and a bounded daily signal-date window from `2024-01-01` through the latest available price date in the selected universe. Use `--start` and `--end` to override the signal-date window explicitly. Quick mode must not run unbounded full-history validation.

`full` is the long-running validation mode. It can run all registered factors, all Strategy DSL strategies, the full configured universe, and default walk-forward folds. It is intended for deliberate research sessions, not routine smoke validation.

Every research-validation report records `start_date`, `end_date`, `effective_start_date`, `effective_end_date`, `trading_day_count`, `frequency`, `forward_days`, `holding_period`, `symbol_count`, `factor_count`, and `estimated_observation_count`. CLI runs print the plan before execution: symbols, factors, date range, batch size, workers, and expected factor task count.

Quick research-validation runs are compact by default. They write the aggregate JSON, `reports/research_validation_summary.md`, and `reports/agent_export_research_validation.md` when agent export is enabled. Sub-step reports, detailed batch artifacts, charts, and debug logs are disabled unless requested.

Every run also has a run-specific artifact directory at `reports/runs/<run_id>/` with `manifest.json`, `substeps/`, `artifacts/`, `charts/`, and `logs/`. The manifest records generated artifact paths, warnings, and compaction status. Top-level `reports/` is reserved for compact user-facing outputs; optional detailed artifacts live under the run directory.

The report layout follows `docs/REPORT_ARCHITECTURE.md`: JSON is for compact reports and metadata, CSV is for structured table artifacts, and future Parquet support is reserved for optional large historical matrices.

Research-validation charts are opt-in. Quick and full runs do not write charts unless `--write-charts` or `--charts` is supplied. When enabled, research-validation charts are written under `reports/runs/<run_id>/charts/`, and the report records `charts_enabled`, `chart_count`, and chart write timing.

Detailed output flags:

- `--write-substep-reports`: write engine sub-step reports under `reports/runs/<run_id>/substeps/`.
- `--write-batch-artifacts`: write full factor-backtest batch artifacts under `reports/runs/<run_id>/artifacts/`.
- `--write-intermediate-reports`: allow intermediate alpha, multi-factor, portfolio, strategy, and trade-simulation reports where those engines would normally write them.
- `--write-charts` / `--charts`: generate charts under `reports/runs/<run_id>/charts/`.
- `--write-debug-logs`: reserve the run log directory for detailed diagnostic logs.
- `--artifact-dir`: override the run artifact directory; `<run_id>` in the path is replaced with the generated run id.

## Bounded Expansion

`v0.39.0` uses the same command for bounded coverage expansion. The runner supports:

- `--batch-size`: evaluate symbols in small batches so partial results are saved after each batch.
- `--max-symbols`: cap the number of pre-filtered symbols for a local run.
- `--max-factors`: cap the number of factors.
- `--factor-family price|fundamental|all`: separate price factors from accounting-based fundamental factors.
- `--resume`: resume-style mode that skips batches with existing factor values.
- `--skip-existing`: skip a batch when all symbols in that batch already have stored factor values for that factor.
- `--use-cache`: enable the v0.41 in-memory factor matrix cache for factor evaluation steps.
- `--cache-stats`: include cache hit/miss and matrix diagnostics in the report and CLI output.

Before running factor evidence, symbols are pre-filtered. Symbols with no price data or insufficient close history are skipped and listed in the report. Fundamental coverage is measured before fundamental factor runs, so low accounting-data coverage remains visible instead of being hidden.

## Runtime Budget

The workflow is budget-aware and records:

- `TIMEOUT`
- `SLOW_STEP`
- `PARTIAL_RESULTS`
- `runtime_seconds` per step
- skipped steps and reasons
- slowest steps
- runtime per factor batch
- symbols evaluated and skipped
- observations produced
- recommended performance work

The runner does not force-kill an active engine step mid-write. It records elapsed time after each step and skips later steps once the budget is exhausted. This avoids corrupting local SQLite writes or generated reports.

## Reports

Generated files:

- `reports/research_validation_YYYYMMDD_HHMMSS.json`
- `reports/research_validation_summary.md`
- `reports/agent_export_research_validation.md`
- optional detailed files under `reports/runs/<run_id>/`

Reports include completed steps, skipped steps, timed-out steps, slow steps, factor rankings, strategy rankings, warning statistics, recommendations, and interpretation notes.

Coverage expansion reports also include:

- explicit universe size
- evaluated symbols
- skipped symbols and reasons
- missing price symbols
- price coverage
- fundamental coverage
- Factor Store before/after counts and growth
- regime sample counts
- runtime per factor and per batch
- slowest factors and steps

## Current QA Findings

The current v0.39 local expansion run used an explicit 147-symbol research universe. Price coverage improved substantially: 146 of 147 symbols had stored daily price data. `CVS` was the only missing-price symbol in that run due to provider/network failure.

Regime sample counts improved materially after extending SPY history. The latest local sample included BULL 2039, BEAR 313, HIGH_VOL 322, LOW_VOL 905, RANGE_BOUND 316, CRISIS 55, RECOVERY 38, TRENDING 48, and UNKNOWN 99.

Fundamental coverage remains the largest bottleneck. In the bounded 50-symbol fundamental smoke run, only about 2% of selected symbols had usable fundamental metrics. Accounting-based factor evidence remains coverage-limited until more fundamental data is imported.

`factor_eval` remains the dominant runtime bottleneck. v0.39 records this bottleneck through `SLOW_STEP`, runtime-per-batch, and slowest-step diagnostics. It intentionally does not add multiprocessing, numba, parquet, vectorized backtest rewrites, or other performance optimizations. `v0.40` should focus on Performance Baseline & Profiling.

## v0.41 Optional Parallel Factor Batches

`research-validation` supports explicit semantic-preserving acceleration:

```bash
python -m quant.cli research-validation --mode quick --max-symbols 20 --max-factors 3 --bulk-matrix --parallel --workers 4 --cache-stats
```

`--bulk-matrix` enables bulk factor observation construction for factor-eval and factor-backtest batches. `--parallel --parallel-target factor_batch` runs independent factor batches in worker processes. Workers compute only; Factor Store, regime history, and final research-validation report writes remain in the main process. If the parallel worker path fails, research-validation falls back to the serial path and records `PARALLEL_FALLBACK_SERIAL`.

Stateful portfolio/account date progression is not parallelized.

`v0.40` adds the measurement-only performance layer described in `docs/PERFORMANCE.md`. It profiles bottlenecks observed here without changing research-validation semantics.

`v0.41` adds opt-in factor matrix caching for research-validation factor-eval steps. The cache is process-local and semantic-preserving: it reuses the same no-lookahead factor observation path and records `cache_summary` instead of changing evidence metrics.

Expanded universe evidence is now passed internally by `research-validation`. The default `factor-eval` CLI workflow is unchanged and does not automatically use the expanded research universe unless a caller uses an engine/API path that supplies `universe`.

## Boundaries

Research validation uses existing engines exactly as implemented. It does not optimize results, tune parameters, remove warnings, change no-lookahead behavior, change factor evaluation semantics, change factor backtest semantics, change walk-forward semantics, change strategy gate semantics, or authorize trading.
