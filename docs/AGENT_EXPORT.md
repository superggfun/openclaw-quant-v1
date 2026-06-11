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

## Visualization Paths

When `visualize-report` has generated charts for the same source report, Agent Export includes those files in `visualization_paths`. The source JSON report is not modified.

## Walk Forward Reports

Agent Export supports `reports/walk_forward_*.json`. Summaries include fold count, average train/test return and Sharpe, factor stability ranking, warnings such as `WARN_OVERFIT` and `WARN_FACTOR_DECAY`, and deterministic next steps like reviewing out-of-sample folds or comparing factor stability.

## Trade Simulation Reports

Agent Export supports `reports/trade_sim_*.json`. Summaries include strategy, portfolio method, initial cash, final equity, total return, annual return, Sharpe, max drawdown, total cost, turnover, trade count, rebalance count, no-lookahead marker, warnings, and deterministic next steps such as comparing portfolio methods or inspecting cost drag.
