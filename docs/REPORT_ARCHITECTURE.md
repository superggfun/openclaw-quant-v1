# Report Architecture

OpenClaw Quant uses a three-layer report architecture so humans, LLMs, Agent Export, MCP tools, and audit workflows can read the right amount of detail.

## Layer 1: Compact Summary Reports

Compact reports are for humans, LLMs, Agent Export, MCP, dashboards, and release notes. They are JSON or Markdown and contain metrics, warnings, recommendations, row counts, and paths to detailed artifacts.

Examples:

- `reports/research_validation_YYYYMMDD_HHMMSS_<id>.json`
- `reports/research_validation_summary.md`
- `reports/agent_export_research_validation.md`
- factor, strategy, regime, and performance summary JSON reports

Compact reports must not embed huge arrays such as factor observations, factor backtest periods, symbol-by-date maps, daily holdings, daily regime observations, or raw factor matrices. When detail is moved out, the compact report records the artifact path and emits `REPORT_COMPACTED`.

## Layer 2: Structured Table Artifacts

Table artifacts are for analysis scripts, pandas, spreadsheet review, and ranking comparisons. CSV is the default format. Parquet may be added later for large historical matrices, but it remains optional.

Use table artifacts for factor rankings, warning frequencies, batch summaries, strategy rankings, coverage tables, regime sample tables, and factor evidence tables.

## Layer 3: Large Detailed Artifacts

Detailed artifacts are for audit, reproducibility, debugging, and future offline analysis. Prefer CSV for flat data. Use JSON only when the structure is deeply nested and still manageable.

Move these details out of compact reports: factor observations, factor backtest periods, `long_symbols_by_date`, `short_symbols_by_date`, daily regime observations, strategy holdings, trade lists, and batch-level detailed reports.

## Directory Layout

Top-level `reports/` is reserved for compact user-facing outputs and backward-compatible filenames. Complex runs write optional detail under a run directory:

```text
reports/
  research_validation_*.json
  research_validation_summary.md
  agent_export_research_validation.md
  runs/
    <run_id>/
      manifest.json
      summaries/
      substeps/
      artifacts/
      charts/
      exports/
      logs/
```

`reports/runs/<run_id>/manifest.json` is the canonical entry point for a complex run. It records run metadata, compact summary paths, sub-step report paths, artifact paths, chart paths, export paths, log paths, warning summary, compaction status, aggregate report path, and agent export path.

## Research Validation Quick Mode

`research-validation --mode quick` is compact by default. It writes a compact aggregate JSON, compact Markdown summary, agent export summary when enabled, and a run manifest.

These outputs are disabled by default and opt-in only: sub-step reports, batch artifacts, intermediate alpha/multi-factor/portfolio reports, charts, and debug logs. When enabled, detailed files are routed under `reports/runs/<run_id>/`, not top-level `reports/`.

## Report Type Rules

`factor_eval` compact JSON keeps factor name, date range, observation count, IC, Rank IC, ICIR, quintile returns, coverage, warnings, no-lookahead notes, and artifact paths. Observations belong in artifacts.

`factor_backtest` compact JSON keeps factor name, spread semantics (`return_type`, `investable_equity`, `cumulative_method`), additive forward-spread diagnostics, legacy alias metadata, turnover, exposure, IC, Rank IC, coverage, warnings, performance metadata, and artifact paths. Periods and symbol-by-date maps belong in artifacts. Legacy names such as `annual_return`, `sharpe`, and `long_short_return` are compatibility aliases for spread diagnostics, not account equity metrics.

`regime_detection` compact JSON keeps current regime, confidence, volatility, trend strength, drawdown, regime counts, warnings, and artifact paths. Daily observations belong in artifacts.

`research_validation` compact JSON keeps run metadata, bounded date range, universe size, factor and strategy counts, top rankings, warning statistics, slowest steps, coverage statistics, recommendations, and artifact paths. Batch detail and raw sub-step detail belong in run artifacts.

`alpha`, `multi_factor`, `portfolio_construction`, `strategy_run`, and `trade_sim` remain JSON reports, but research-validation quick mode suppresses their repeated intermediate writes unless explicitly enabled.

## Agent Export And MCP

Agent Export consumes compact summaries only. It should include key metrics, warnings, recommendations, observation counts, and artifact paths. It must not include daily observations, huge symbol-by-date maps, raw factor matrices, or binary chart payloads.

MCP report tools return compact summary objects and metadata only. Detailed files are exposed as paths, artifact types, and row counts where available. MCP responses must not return large file contents, binary image payloads, or huge JSON arrays.

## Visualization

Charts should read compact summaries or table artifacts. Research-validation charts are disabled in quick mode by default and, when enabled, are written under `reports/runs/<run_id>/charts/`.

The standalone `visualize-report` command remains backward-compatible and can still write to the output directory supplied by the caller.
