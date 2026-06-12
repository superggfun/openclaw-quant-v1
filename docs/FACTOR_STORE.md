# Factor Store

`v0.31.0` adds a persistent factor research database. It stores factor definitions, factor values, evaluation history, backtest history, walk-forward history, stability diagnostics, coverage diagnostics, and factor versions.

This is storage and analytics infrastructure only. It does not add new alpha factors, machine learning, broker integration, news sentiment, live trading, or changes to no-lookahead semantics.

## Purpose

Before v0.31, factor research results were mostly report artifacts. The Factor Store makes research reproducible by storing structured factor outputs in SQLite:

- factor values by symbol and signal date
- factor metadata
- IC and RankIC history
- ICIR history
- factor coverage
- factor stability
- factor versions

## Tables

The store creates:

- `factor_definitions`
- `factor_values`
- `factor_evaluation_history`
- `factor_backtest_history`
- `factor_walk_forward_history`
- `factor_stability_history`
- `factor_versions`
- `factor_regime_history`

`factor_values` uses:

```text
PRIMARY KEY (factor_name, symbol, signal_date, version)
```

Repeated saves for the same factor, symbol, signal date, and version update the value instead of duplicating rows.

Evaluation, backtest, walk-forward, and stability history tables are append-only by run timestamp. This preserves a research audit trail: repeating a save records another evaluation event, while the underlying `factor_values` table remains idempotent by `(factor_name, symbol, signal_date, version)`.

## No-Lookahead

The Factor Store does not compute new factor values by itself. It persists values produced by existing no-lookahead engines:

- `factor-eval`
- `factor-backtest`
- `walk-forward`

Fundamental factors continue to use:

```text
report_date <= signal_date
```

`fiscal_period_end` alone is not a valid tradable availability date.

## CLI

Persist factor evaluation history:

```bash
python -m quant.cli factor-eval --factor momentum_20d --save-factor-history
```

Persist factor backtest history:

```bash
python -m quant.cli factor-backtest --factor momentum_20d --save-factor-history
```

Persist walk-forward fold history:

```bash
python -m quant.cli walk-forward --strategy factor_long_short --factor momentum_20d --save-factor-history
```

Query the store:

```bash
python -m quant.cli factor-store-summary
python -m quant.cli factor-store-summary --sync-definitions
python -m quant.cli factor-history --factor momentum_20d
python -m quant.cli factor-rank
```

## Factor Rank

`factor-rank` produces:

- top factors
- worst factors
- most stable factors
- most unstable factors

The health score blends:

- ICIR
- coverage
- stability
- drawdown diagnostics

The score is a research diagnostic, not a return guarantee or trading instruction.

## Regime Integration

`v0.32.0` adds optional factor-by-regime diagnostics. `factor-eval` and `factor-backtest` can persist regime statistics with:

```bash
python -m quant.cli factor-eval --factor momentum_20d --save-regime-history
python -m quant.cli factor-backtest --factor momentum_20d --save-regime-history
```

These rows are stored in `factor_regime_history`. They are grouped by the regime active on each factor `signal_date`, preserving no-lookahead alignment. Regime rankings are diagnostics only and do not change factor weights or trading behavior.

`factor_regime_history` appends one set of rows per research run. Low-sample regime groups emit warnings and reduce ranking support; a high IC in a thin regime should be treated as fragile evidence.

## Reports

Generated reports:

- `reports/factor_store_summary_YYYYMMDD_HHMMSS.json`
- `reports/factor_history_YYYYMMDD_HHMMSS.json`
- `reports/factor_rank_YYYYMMDD_HHMMSS.json`

Reports are generated artifacts under `reports/*.json` and are ignored by git.

## Agent Export and Visualization

Agent Export supports factor store reports and summarizes:

- top factor
- IC / RankIC / ICIR
- coverage
- stability
- confidence
- recommended follow-up checks

Visualization supports:

- IC history
- RankIC history
- factor ranking
- stability history
- coverage history

## Boundary

Factor Store is for reproducibility and lifecycle management. It does not change factor evaluation, factor backtest, walk-forward, alpha generation, or trading simulation behavior unless a CLI command explicitly uses `--save-factor-history`.
## Scheduler Integration

The Daily Research Scheduler can run factor evaluation and persist results through Factor Store during `research-run`. The scheduler does not change Factor Store semantics: factor values remain keyed by factor, symbol, signal date, and version, and no-lookahead rules remain owned by the factor engines.

## Strategy Metadata

Strategy DSL metadata is persisted separately in `strategy_registry`, `strategy_versions`, and `strategy_runs`. Factor Store semantics and factor history tables are unchanged.
