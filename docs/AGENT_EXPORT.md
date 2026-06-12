# Agent Export

`v0.18.0` adds an Agent Export Layer for compact report summaries optimized for OpenClaw, Claude, GPT, Qwen, and other LLM agents.

This is an export-only layer. It does not modify existing report schemas, quant logic, factor evaluation, backtests, portfolio state, broker connectivity, or live execution. Agent exports are research summaries, not investment advice.

## CLI

```bash
python -m quant.cli export-for-agent --report reports/strategy_eval_YYYYMMDD_HHMMSS.json
python -m quant.cli export-for-agent --report reports/factor_backtest_YYYYMMDD_HHMMSS.json --format markdown
python -m quant.cli export-for-agent --report reports/portfolio_construction_YYYYMMDD_HHMMSS.json --format json
python -m quant.cli export-for-agent --report reports/strategy_eval_YYYYMMDD_HHMMSS.json --output reports/agent_summary.md
```

Supported formats:

- `text`
- `markdown`
- `json`

`json` is compact machine-friendly JSON, not the raw source report.

## Supported Reports

Report type is detected from schema keys, not file names.

Supported report types:

- `alpha`
- `factor_eval`
- `factor_backtest`
- `strategy_eval`
- `portfolio_construction`
- `risk`
- `rebalance`
- `execution`
- `backtest`
- `trade_sim`
- `multi_factor`
- `fundamental_import`
- `fundamental_coverage`
- `fundamental_quality`
- `factor_store_summary`
- `factor_history`
- `factor_rank`
- `regime_detection`
- `regime_history`
- `regime_report`
- `regime_rank`
- `strategy_list`
- `strategy_definition`
- `strategy_validation`
- `strategy_run`
- `strategy_gate`

Factor evaluation and factor backtest exports include `factor_coverage` when source reports evaluate fundamental factors. Agent summaries do not recompute the factors; they only compact existing report fields such as coverage percentage, missing percentage, metrics used, and warnings.

Multi-factor exports summarize top symbols, factor/family weights, coverage, confidence, warnings, and recommended validation checks. They do not embed chart bytes and do not make allocation decisions.

Factor Store exports summarize persisted factor definitions, IC/Rank IC/ICIR history, coverage, stability, confidence, and rankings. They read stored research history only; they do not recompute factors and do not generate trade decisions.

Regime exports summarize current regime, regime counts, factor performance by regime, regime-aware rankings, and deterministic follow-up checks. They are diagnostics only and do not provide investment advice.

## Common Output Schema

All exports include:

- `report_type`
- `generated_from`
- `summary`
- `key_metrics`
- `key_findings`
- `warnings`
- `recommended_next_steps`
- `action_candidates`
- `data_quality_notes`

## Token Budget

Use:

```bash
python -m quant.cli export-for-agent --report reports/strategy_eval_YYYYMMDD_HHMMSS.json --max-tokens 800
```

The exporter prioritizes:

1. `summary`
2. `key_metrics`
3. `warnings`
4. `recommended_next_steps`

Lower-priority sections are trimmed first. The token budget is approximate and deterministic.

## Warnings

The exporter deterministically emits warnings for conditions such as:

- `WARN_UNIVERSE_SMALL`
- `WARN_LOW_OBSERVATION_COUNT`
- `WARN_EXTREME_DRAWDOWN`
- `WARN_CASH_ALLOCATION_HIGH`
- `WARN_SHARPE_RETURN_MISMATCH`
- `WARN_FACTOR_IC_NEGATIVE`
- `WARN_UNFILLED_TRADES_PRESENT`
- `WARN_LIQUIDITY_CAP`
- `WARN_HIGH_SLIPPAGE`
- `WARN_NO_PRICE`
- `WARN_POSITION_CONCENTRATION_HIGH`

Warnings are research prompts for review. They are not trade instructions.

## Recommended Next Steps

Recommendations are deterministic and report-type specific, for example:

- expand universe
- run walk-forward validation
- compare factors
- review drawdown
- inspect cost drag
- evaluate risk parity allocation

The exporter does not invent external facts. It only uses fields in the input report.

## MCP Integration

The v0.35 MCP foundation can call Agent Export through the `export_for_agent` and `get_report_summary` tools. MCP returns compact summaries, warnings, recommendations, and report paths only. It does not embed image bytes, mutate source reports, execute trades, or create investment advice.

## Protocol Objects

`v0.29.0` adds direct protocol-object export through `AgentExporter.export_protocol()`. This supports JSON-safe objects such as `AccountState`, `Position`, `Order`, `Fill`, `Signal`, and `Recommendation` for future MCP/OpenClaw context passing.

This direct protocol export is an in-process API, not a CLI report schema change. Existing `export-for-agent --report ...` behavior remains unchanged.

## Visualization Paths

When `visualize-report` has generated charts for the same source report, Agent Export includes those files in `visualization_paths`. The source JSON report is not modified.

## Walk Forward Reports

Agent Export supports `reports/walk_forward_*.json`. Summaries include fold count, average train/test return and Sharpe, factor stability ranking, warnings such as `WARN_OVERFIT` and `WARN_FACTOR_DECAY`, and deterministic next steps like reviewing out-of-sample folds or comparing factor stability.

## Market Realism

For `trade_sim` and `execution` reports, Agent Export includes slippage, market impact, liquidity cost, rejected trade counts, and largest constrained trades when those fields exist. It does not embed chart bytes or change source reports.

## Trade Simulation Reports

Agent Export supports `reports/trade_sim_*.json`. Summaries include strategy, portfolio method, initial cash, final equity, total return, annual return, Sharpe, max drawdown, total cost, turnover, trade count, rebalance count, no-lookahead marker, warnings, and deterministic next steps such as comparing portfolio methods or inspecting cost drag.

## Fundamental Reports

Agent Export supports `reports/fundamental_import_*.json`, `reports/fundamental_coverage_*.json`, and `reports/fundamental_quality_*.json`. Summaries include import counts, readiness score, symbols covered, missing symbols, latest report date, and key quality warnings. These summaries are diagnostics only and do not create trading signals.

## Factor Store Reports

Agent Export supports `reports/factor_store_summary_*.json`, `reports/factor_history_*.json`, and `reports/factor_rank_*.json`. Summaries include stored row counts, latest factor metrics, top and weak factors, stability and coverage notes, and deterministic next steps such as expanding coverage or rerunning walk-forward validation.

## Regime Reports

Agent Export supports `reports/regime_detection_*.json`, `reports/regime_history_*.json`, `reports/regime_report_*.json`, and `reports/regime_rank_*.json`. Summaries include current regime, regime confidence, factor-by-regime diagnostics, and next steps such as reviewing momentum exposure or comparing factor stability. These are not trading instructions.
## Scheduler Reports

Agent Export supports `research_run`, `research_status`, and `research_history` reports. Exports summarize run status, current regime, best and weak factors, trade simulation return, generated artifacts, warnings, and recommended next checks. These summaries are context compaction for LLM agents, not investment advice or autonomous trading instructions.

## Strategy DSL Reports

Agent Export supports `strategy_list`, `strategy_definition`, `strategy_validation`, `strategy_run`, and `strategy_gate` reports. These summaries describe reproducible research configuration, validation gates, offline simulation results, and v0.37 Strategy Evaluation Gate outcomes; they are not trading advice.

Strategy Gate exports include overall status, warning gates, failed or rejected gates, rejection reasons, and deterministic next checks. They do not authorize order placement or live trading.
