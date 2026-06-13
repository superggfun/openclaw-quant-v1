# Parallelization Analysis Report - openclaw-quant-v1

**Project Version:** v0.41.0-factor-eval-cache
**Analysis Date:** 2026-06-13
**Scope:** All `.py` files under `quant/` (skipping `__pycache__`)

---

## Executive Summary

The project already has a well-designed parallel infrastructure (`FactorBatchTask` + `ProcessPoolExecutor` in `quant/factor_acceleration/parallel_runner.py`) that accelerates *factor-level batch tasks* (factor eval, factor backtest) across symbols. However, significant parallelization opportunities remain at **higher orchestration levels** (walk-forward folds, factor stability analysis, strategy evaluation) and **lower computation levels** (per-symbol factor computation in non-bulk paths, data downloads).

### Estimated Cumulative Impact
If all high-priority recommendations are implemented, a **full `research-validation --mode full` run could see 3×–8× speedup** on a machine with 8+ CPU cores.

---

## Existing Parallel Infrastructure (Baseline)

| Component | Location | Mechanism |
|-----------|----------|-----------|
| `FactorBatchTask` | `quant/factor_acceleration/factor_matrix_builder.py:parallel_runner.py:20` | Dataclass task descriptor |
| `run_factor_batch_tasks()` | `quant/factor_acceleration/parallel_runner.py:50` | `ProcessPoolExecutor` with timeout, `FIRST_COMPLETED` wait strategy |
| `_observations_bulk()` | `quant/engines/factor_backtest/factor_backtest.py:207` | Uses `FactorMatrixBuilder` for bulk matrix → avoids per-symbol serial loop |
| `BulkPriceLoader` | `quant/factor_acceleration/bulk_price_loader.py:27` | Single SQL query for all symbols via `get_price_history_many()` |
| `get_price_history_many()` | `quant/storage/sqlite_store.py:137` | `WHERE symbol IN (...)` bulk query + `groupby("symbol")` |
| `--parallel --workers N` CLI | `quant/cli_commands/research_validation.py` | Passes to `ResearchValidationRunner.run(parallel=True, worker_count=N)` |
| `--bulk-matrix` CLI | `quant/engines/factor_eval/factor_evaluation.py:178` | Enables `FactorMatrixBuilder` code path |
| **SQLite Writes** | `factor_phase.py:60-73` | Batched in main process after parallel compute completes (correct design for SQLite) |

---

## High-Priority Opportunities (Estimated Speedup ≥ 3×)

### H1. Walk-Forward Fold Execution — Serial Across Folds

**File:** `quant/engines/walk_forward/walk_forward.py`
**Function:** `WalkForwardEngine.run()` — line 119–145
**Pattern:**

```python
# Line 119-145
folds = []
for index, window in enumerate(fold_windows, start=1):
    folds.append(self._run_fold(...))
```

**Problem:** Each fold runs a *train backtest* + *test backtest* independently with no data dependency between folds. With `max_folds=5`, this serializes 10 full backtest engine runs (each with its own daily loop over hundreds of trading days across hundreds of symbols). A single fold can take 5–30 seconds; 5 folds = 25–150 seconds serial.

**Recommendation:** Use `ProcessPoolExecutor` to parallelize fold execution.

```python
from concurrent.futures import ProcessPoolExecutor, as_completed

# Each worker constructs its own engine (SQLite supports read concurrency)
def _run_fold_worker(args) -> WalkForwardFold:
    index, window, strategy, factor, symbols, initial_cash, rebalance_freq, alpha_config, pipeline_config, db_path, report_dir = args
    engine = WalkForwardEngine(SQLitePriceStore(db_path), report_dir=report_dir)
    return engine._run_fold(index, strategy, factor, window, symbols, initial_cash, rebalance_freq, alpha_config, pipeline_config)

folds = []
with ProcessPoolExecutor(max_workers=min(5, len(fold_windows))) as executor:
    futures = {executor.submit(_run_fold_worker, args): i for i, args in enumerate(fold_tasks)}
    for future in as_completed(futures):
        folds.append(future.result())
```

**Estimated Speedup:** 3×–5× (with 5 folds on 4+ cores)
**Risk:** Low — each fold touches disjoint time periods, SQLite supports WAL-mode concurrent reads.

---

### H2. Factor Stability Analysis — Serial Factor Loop

**File:** `quant/engines/walk_forward/walk_forward.py`
**Function:** `WalkForwardEngine.factor_stability()` — line 193–228
**Pattern:**

```python
# Line 193-228
for factor in factors:           # 14 factors
    for window in windows:       # N windows
        ic, rank_ic = self._lightweight_factor_ic(
            factor=factor, symbols=symbols,
            start=window["test_start"], end=window["test_end"],
            forward_days=20,
        )
```

**Problem:** 14 stability factors × N windows = 14N independent IC computations. Each `_lightweight_factor_ic()` call loads ALL symbols' histories and computes factor values row-by-row. On 500 symbols with 3 windows, that's 14 × 3 = 42 serial calls, each processing 500 symbols × ~250 bars.

**Recommendation:** Two-tier parallelization:
1. **(Easy)** Parallelize the outer `for factor in factors:` loop via `ProcessPoolExecutor` (each worker gets one factor, processes all windows)
2. **(Better)** Make `_lightweight_factor_ic()` use `FactorMatrixBuilder.build_many_horizons()` — already exists and is much faster

**Estimated Speedup:** 5×–10× (14 factors on 8 cores)
**Risk:** Low — factor computation is read-only.

---

### H3. Walk-Forward `_lightweight_factor_ic()` — Row-by-Row Without Bulk Matrix

**File:** `quant/engines/walk_forward/walk_forward.py`
**Function:** `WalkForwardEngine._lightweight_factor_ic()` — line 230–272
**Pattern:**

```python
# Line 230-272
for symbol in symbols:                     # 500+ symbols
    history = self.price_store.get_price_history(symbol)  # Individual SQL query!
    for index in range(len(history)):      # ~250 bars per symbol
        factor_value = self.factor_registry.factor_value(...)
```

**Problem:** Triple-nested serial loop: symbols → bars → factor computation. Each call makes 500+ individual SQL queries. Also does NOT use `get_price_history_many()` (line 237: `self.price_store.get_price_history(symbol)` — singular!).

**Recommendation:** Rewrite to use `FactorMatrixBuilder`:

```python
matrix = FactorMatrixBuilder(self.price_store, self.factor_registry).build(
    factor=factor, symbols=symbols, start=start, end=end, forward_days=forward_days,
)
# matrix.valid_rows is already computed in bulk
observations = matrix.valid_rows  # or adapt as needed
```

This already exists and is battle-tested in the factor eval/backtest paths.

**Estimated Speedup:** 10×–50× (eliminates N individual SQL queries + row-by-row Python loops)
**Risk:** None — `FactorMatrixBuilder` is the project's own acceleration infrastructure.

---

### H4. Walk-Forward `_date_range()` — Serial Per-Symbol Queries

**File:** `quant/engines/walk_forward/walk_forward.py`
**Function:** `WalkForwardEngine._date_range()` — line 380–395
**Pattern:**

```python
# Line 380-395
for symbol in symbols:                                 # 500+ symbols
    history = self.price_store.get_price_history(symbol)  # Individual SQL query
    if not history.empty:
        dates.extend(str(value) for value in history["date"].tolist())
```

**Problem:** 500+ individual SQL queries just to find min/max dates. `SQLitePriceStore.latest_dates()` (line 198) already has a bulk version.

**Recommendation:** Use `self.price_store.latest_dates(symbols)` which does a single `SELECT symbol, MAX(date) ... GROUP BY symbol` query, and add a similar `earliest_dates()` method if needed, or use `get_price_history_many()` and compute min/max in pandas.

**Estimated Speedup:** 5×–10× (reduces N SQL round-trips to 1)
**Risk:** None — bulk queries already exist in codebase.

---

### H5. Strategy Phase — Serial Strategy Execution

**File:** `quant/research_validation/strategy_phase.py`
**Function:** `run_strategy_phase()` — line 22–51
**Pattern:**

```python
# Line 22-51
for strategy in strategies:       # Serial loop over strategies
    step, result = runner._timed_step("strategy_run_with_gates", "strategy", strategy, lambda s=strategy: runner._run_strategy(...))
```

**Problem:** Each strategy runs its own full backtest independently (portfolio level or factor-long-short). N strategies = N full backtest runs, each taking 10–60 seconds.

**Recommendation:** Use the same `FactorBatchTask` / `ProcessPoolExecutor` pattern already proven in `factor_phase.py`. Create a `StrategyBatchTask` or extend `FactorBatchTask` with a `kind="strategy"` variant.

**Estimated Speedup:** 3×–6× (N strategies on N/2 cores)
**Risk:** Medium — strategy backtest writes reports; need to isolate report paths per worker. SQLite reads are safe.

---

## Medium-Priority Opportunities (Estimated Speedup 1.5×–3×)

### M1. FactorMatrixBuilder Symbol Loop — Serial Within "Accelerated" Path

**File:** `quant/factor_acceleration/factor_matrix_builder.py`
**Function:** `FactorMatrixBuilder.build_many_horizons()` — line 53–84
**Pattern:**

```python
# Line 53-84
for symbol in symbols:              # Serial symbol loop
    history = histories.histories.get(symbol)  # Pre-loaded in bulk
    factor_values = self._factor_values(factor, symbol, history, start, end)
    for horizon in normalized_horizons:
        symbol_rows = self._rows_for_horizon(...)
```

**Problem:** Even though prices are bulk-loaded via `BulkPriceLoader`, factor computation for each symbol runs serially. For non-price-series factors (fundamental, quality_score, etc.), `_factor_values()` calls `registry.factor_value()` for every historical bar — an independent computation per symbol.

**Recommendation:** Split symbols into chunks and use `ProcessPoolExecutor`:

```python
from concurrent.futures import ProcessPoolExecutor

# Each worker computes factor values for a chunk of symbols
def _compute_symbol_chunk(args):
    symbol_chunk, factor, histories, horizons, start, end, registry, store = args
    # Reconstruct builder state (or pass serialized history data)
    ...

chunk_size = max(1, len(symbols) // workers)
with ProcessPoolExecutor(max_workers=workers) as executor:
    futures = [executor.submit(_compute_symbol_chunk, chunk_args) for chunk_args in chunks]
    for future in as_completed(futures):
        merge_results(future.result())
```

**Estimated Speedup:** 2×–4× (on 500 symbols with 4–8 workers)
**Risk:** Medium — need to ensure `FactorRegistry` is pickle-safe (it should be — just holds a dict of definitions).

---

### M2. YFinanceProvider Data Downloads — Serial HTTP Calls

**File:** `quant/data/providers/yfinance_provider.py`
**Function:** `YFinanceProvider.fetch_many_daily_prices()` — line 126–133
**Pattern:**

```python
# Line 126-133
frames = [self.get_price_history(symbol, start=start, end=end) for symbol in symbols]
```

**Problem:** List comprehension downloads one symbol at a time, each making an HTTP request to Yahoo Finance. For 500 symbols, that's 500 serial network round-trips. Also, `get_price_history()` passes `threads=False` to yfinance (line 39).

**Recommendation:** Use `ThreadPoolExecutor` for IO-bound parallel downloads:

```python
from concurrent.futures import ThreadPoolExecutor, as_completed

with ThreadPoolExecutor(max_workers=8) as executor:
    futures = {executor.submit(self.get_price_history, s, start, end): s for s in symbols}
    frames = []
    for future in as_completed(futures):
        frame = future.result()
        if not frame.empty:
            frames.append(frame)
```

Also consider using `yfinance.download(tickers, group_by='ticker', threads=True)` for multi-ticker download in a single call.

**Estimated Speedup:** 5×–20× (IO-bound; thread pool eliminates serial wait time)
**Risk:** Low — yfinance rate limits may apply; add sensible `max_workers` (4–8) and retry logic.

---

### M3. BacktestEngine `_load_price_frame()` — Serial Per-Symbol Loading

**File:** `quant/engines/backtest/backtest_engine.py`
**Function:** `PortfolioBacktestEngine._load_price_frame()` — line 332–353
**Pattern:**

```python
# Line 332-353
for symbol in symbols:                           # Individual SQL queries
    history = self.price_store.get_price_history(symbol, start=start, end=end)
    ...
    columns[symbol] = history.set_index("date")["close"]
```

**Problem:** 500+ individual SQL queries to build a price DataFrame. `get_price_history_many()` already exists in `SQLitePriceStore` (line 137) but is not used here.

**Recommendation:** Use `get_price_history_many()`:

```python
histories = self.price_store.get_price_history_many(symbols, start=start, end=end)
for symbol, history in histories.items():
    if not history.empty:
        columns[symbol] = history.set_index("date")["close"]
```

**Estimated Speedup:** 5×–10× (reduces N SQL round-trips to 1)
**Risk:** None — `get_price_history_many()` is already tested and uses the same WHERE clause patterns.

---

### M4. Serial Factor Eval/Backtest — Non-Parallel Code Path

**File:** `quant/research_validation/factor_phase.py`
**Functions:** `_run_serial_factor_eval_phase()` — line 318–371, `_run_serial_factor_backtest_phase()` — line 374–434
**Pattern:**

```python
# Line 318-371
for factor in factors:                          # N factors
    for batch_index, batch in enumerate(batches, start=1):  # M symbol batches
        step, result = runner._timed_step(...)  # Serial execution
```

**Problem:** When `--parallel` is NOT passed (or if parallel fails and falls back to serial), ALL factor×batch combinations run sequentially. With 15 factors × 5 batches = 75 independent tasks, total runtime = sum of all individual task times.

**Recommendation:** The parallel path already exists and works well. Consider:
1. Making `--parallel` the default (opt-out instead of opt-in)
2. Adding a warning when running without `--parallel` on multi-core machines
3. Using `ThreadPoolExecutor` for the serial fallback (instead of true serial) since SQLite can handle multiple readers

**Estimated Speedup:** 4×–8× (75 tasks on 8 cores vs. serial)
**Risk:** Low — the parallel path is already well-tested; just needs to be made default.

---

## Low-Priority Opportunities (Estimated Speedup < 2× or High Risk)

### L1. FactorMatrixBuilder `_factor_values()` — Row-by-Row Factor Computation

**File:** `quant/factor_acceleration/factor_matrix_builder.py`
**Function:** `FactorMatrixBuilder._factor_values()` — line 102–120
**Pattern:**

```python
# Line 102-120
for index in range(len(history)):           # ~250 iterations per symbol
    value = self.factor_registry.factor_value(
        history.iloc[: index + 1]["close"],  # Expanding window — O(n²) memory
        factor, symbol=symbol, as_of_date=signal_date,
    )
```

**Problem:** For price-series factors (momentum, volatility, etc.), `_price_factor_series()` already handles this vectorized (line 142-175). But for non-vectorized factors and fundamental factors, this row-by-row loop runs Python-level expanding windows with O(n²) complexity.

**Recommendation:**
- **Short-term:** Use `FactorMatrixBuilder._price_factor_series()` path for common price factors (already done for 9 factors)
- **Medium-term:** For `quality_score` (line ~182): reimplement the `rolling(61).apply()` lambda with numba:

```python
from numba import njit

@njit
def _quality_window_numba(values):
    # Avoid pd.Series construction in rolling apply
    returns = values[1:] / values[:-1] - 1.0
    ...
```

- **Long-term:** Precompute all factor values in a single pass using expanding/rolling pandas operations

**Estimated Speedup:** 1.5×–3× (numba for quality_score; limited to non-vectorized factors)
**Risk:** Medium — numba adds a dependency; benefits only apply to `quality_score` and custom fundamental factors.

---

### L2. RegimeDetector — `.iterrows()` Loop

**File:** `quant/engines/regime/regime_detector.py`
**Function:** `RegimeDetector.detect()` — line 38–72
**Pattern:**

```python
# Line 38-72
for index, row in history.iterrows():       # Slow pandas iteration
    close = self._num(closes.iloc[index])
    ...
    regime, confidence = classify_regime(...)
    observations.append(RegimeObservation(...))
```

**Problem:** `.iterrows()` is the slowest way to iterate in pandas. The upstream computations are already vectorized (rolling std, pct_change, cummax). The bottleneck is the per-row `classify_regime()` call.

**Recommendation:** Replace `.iterrows()` with vectorized assignment:

```python
# Create a DataFrame with all the computed columns, then
# vectorize classify_regime or use df.apply(axis=1) with raw=True
frame = pd.DataFrame({
    'date': history['date'].astype(str),
    'close': closes,
    'ma': moving_average,
    'vol': rolling_vol * math.sqrt(252),
    'trend_strength': trend,
    'drawdown': drawdown,
    'market_return': market_return,
}).dropna()

# Use df.itertuples() instead of iterrows() for 3x speedup
for row in frame.itertuples(index=False):
    regime, confidence = classify_regime(...)
```

Or, if `classify_regime` can be refactored, use `pd.DataFrame.apply()` with `result_type='expand'`.

**Estimated Speedup:** 1.5×–3× (from iterrows→itertuples or vectorization)
**Risk:** Low — pure refactoring, no parallelism needed.

---

### L3. Research Validation Phase Orchestration — Sequential Phases

**File:** `quant/research_validation/research_validation.py`
**Function:** `ResearchValidationRunner.run()` — line 171+
**Pattern:** The main runner calls phases sequentially: factor_phase → regime_phase → strategy_phase → walk_forward_phase.

**Problem:** Strategy and walk-forward phases must wait for the factor phase to complete (they depend on factor store results). But within the factor phase, regime detection could run concurrently with factor evals (regime only needs price data).

**Recommendation:**
- Phase-level: Run regime detection in parallel with factor eval/backtest (regime uses benchmark price data only)
- Walk-forward could start as soon as its target factor's eval is complete (streaming dependency)

**Estimated Speedup:** 1.2×–1.5× (limited overlap opportunity)
**Risk:** Medium — adds orchestration complexity.

---

### L4. Fundamental Coverage Service — Serial Per-Symbol Queries

**File:** `quant/data/fundamental/fundamental_service.py`
**Function:** `FundamentalService.coverage()` — line 36+
**Pattern:** Multiple per-symbol SQLite queries to compute coverage statistics.

**Recommendation:** Use bulk SQL queries with GROUP BY where possible, similar to `latest_dates()`.

**Estimated Speedup:** 1.2×–1.5× (only called occasionally)
**Risk:** Low.

---

## Summary Table

| # | Priority | File | Function | Pattern | Solution | Speedup |
|---|----------|------|----------|---------|----------|---------|
| H1 | ★★★ | `walk_forward.py:119` | `WalkForwardEngine.run()` | Serial fold loop | ProcessPoolExecutor per fold | 3×–5× |
| H2 | ★★★ | `walk_forward.py:193` | `factor_stability()` | 14 factors serial | ProcessPoolExecutor per factor | 5×–10× |
| H3 | ★★★ | `walk_forward.py:230` | `_lightweight_factor_ic()` | N SQL queries + row loops | Use `FactorMatrixBuilder` (already exists!) | 10×–50× |
| H4 | ★★★ | `walk_forward.py:380` | `_date_range()` | N individual SQL queries | Use bulk `latest_dates()` or `get_price_history_many()` | 5×–10× |
| H5 | ★★★ | `strategy_phase.py:22` | `run_strategy_phase()` | Serial strategy loop | ProcessPoolExecutor per strategy | 3×–6× |
| M1 | ★★ | `factor_matrix_builder.py:53` | `build_many_horizons()` | Serial symbol loop in "accelerated" path | ProcessPoolExecutor symbol chunks | 2×–4× |
| M2 | ★★ | `yfinance_provider.py:126` | `fetch_many_daily_prices()` | Serial HTTP downloads | ThreadPoolExecutor | 5×–20× |
| M3 | ★★ | `backtest_engine.py:332` | `_load_price_frame()` | N individual SQL queries | Use `get_price_history_many()` | 5×–10× |
| M4 | ★★ | `factor_phase.py:318` | `_run_serial_factor_*_phase()` | Serial when no `--parallel` | Make parallel default or add ThreadPool fallback | 4×–8× |
| L1 | ★ | `factor_matrix_builder.py:102` | `_factor_values()` | Row-by-row expanding window | numba for quality_score; vectorize | 1.5×–3× |
| L2 | ★ | `regime_detector.py:38` | `detect()` | `.iterrows()` loop | `itertuples()` or vectorize | 1.5×–3× |
| L3 | ★ | `research_validation.py:171` | `run()` | Sequential phases | Concurrent non-dependent phases | 1.2×–1.5× |
| L4 | ★ | `fundamental_service.py:36` | `coverage()` | Per-symbol queries | Bulk SQL with GROUP BY | 1.2×–1.5× |

---

## Recommended Implementation Order

### Phase 1: "Quick Wins" (1–2 days)
1. **H4** — Replace `_date_range()` individual queries with bulk query (one-line change)
2. **H3** — Replace `_lightweight_factor_ic()` with `FactorMatrixBuilder` call (already tested code path)
3. **M3** — Replace `_load_price_frame()` individual queries with `get_price_history_many()` (one-line change)
4. **M4** — Make `--parallel` the default with `workers=min(4, os.cpu_count())`

**Impact:** 5×–20× speedup for walk-forward and backtest paths with minimal code changes.

### Phase 2: "Parallel Folds & Factors" (2–3 days)
5. **H1** — Parallelize walk-forward fold execution
6. **H2** — Parallelize factor stability analysis
7. **H5** — Parallelize strategy execution
8. **M2** — Parallelize data downloads

**Impact:** 3×–10× additional speedup for full research-validation runs.

### Phase 3: "Deep Optimization" (3–5 days)
9. **M1** — Parallelize symbol computation in FactorMatrixBuilder
10. **L1** — Numba-accelerate quality_score and other rolling computations
11. **L2** — Vectorize regime detection
12. **L3** — Optimize phase orchestration

**Impact:** 1.5×–3× additional speedup. Diminishing returns but better for very large universes.

---

## Risks & Cautions

| Risk | Mitigation |
|------|------------|
| **SQLite write contention** | All writes remain in main process (current design is correct). Do NOT parallelize SQLite writes. |
| **SQLite read concurrency** | WAL mode supports concurrent reads. Test with `PRAGMA journal_mode=WAL`. |
| **ProcessPool overhead** | Serialization of large DataFrames can be slow. For H1-H2, only pass config (strings/ints), not DataFrames — each worker loads its own data from SQLite. |
| **Memory** | 8× `ProcessPoolExecutor` × 500 symbols × ~250 bars = ~400 MB. Limit workers based on available RAM. |
| **yfinance rate limits** | Yahoo Finance may throttle. Use `max_workers=4` with exponential backoff retry. |
| **Determinism** | Parallel execution order is non-deterministic. Results must be sorted by fold/factor/batch index after collection (already done in `_sort_results()`). |

---

## Appendix: Files Analyzed

All source files under:
- `quant/engines/backtest/` — `backtest_engine.py`
- `quant/engines/factor_backtest/` — `factor_backtest.py`
- `quant/engines/factor_eval/` — `factor_evaluation.py`, `factor_scoring.py`, `multi_factor_model.py`
- `quant/engines/walk_forward/` — `walk_forward.py`, `rolling_validation.py`
- `quant/engines/regime/` — `regime_detector.py`, `regime_analytics.py`, `regime_classification.py`, `regime_history.py`, `market_regime.py`
- `quant/engines/alpha/` — `alpha_engine.py`
- `quant/engines/risk/` — `risk_engine.py`
- `quant/engines/portfolio/` — `optimizer_engine.py`, `portfolio_construction.py`
- `quant/engines/execution/` — `cost_engine.py`
- `quant/engines/factor_pipeline/` — `factor_pipeline.py`
- `quant/engines/strategy_eval/` — evaluation and adapter modules
- `quant/factor_acceleration/` — `factor_matrix_builder.py`, `parallel_runner.py`, `bulk_price_loader.py`, `observation_matrix.py`
- `quant/research_validation/` — `research_validation.py`, `factor_phase.py`, `strategy_phase.py`, `walk_forward_phase.py`, `config.py`, `models.py`, `phase_common.py`
- `quant/data/` — `providers/yfinance_provider.py`, `fundamental/fundamental_service.py`, `fundamental/fundamental_store.py`
- `quant/storage/` — `sqlite_store.py`, `sqlite_connection.py`, `portfolio_store.py`
- `quant/factors/` — `price/factor_registry.py`, `price/factor_common.py`, `registry.py`, `specs.py`
- `quant/cli_commands/` — `research_validation.py`, `factor_pipeline.py`, `regime.py`, `strategy_dsl.py`
- `quant/strategy_dsl/` — `strategy_registry.py`, `strategy_loader.py`, `strategy_definition.py`
