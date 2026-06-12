# Visualization Reports

`v0.23.0` adds a visualization layer for existing JSON reports. It is for human review, OpenClaw context, research debugging, and report inspection.

It does not change quant calculations, factor logic, backtests, portfolio state, execution behavior, broker connectivity, or report source schemas.

## CLI

```bash
python -m quant.cli visualize-report --report reports/trade_sim_YYYYMMDD_HHMMSS.json
python -m quant.cli visualize-report --report reports/strategy_eval_YYYYMMDD_HHMMSS.json
python -m quant.cli visualize-report --report reports/walk_forward_YYYYMMDD_HHMMSS.json
```

Optional output directory:

```bash
python -m quant.cli visualize-report --report reports/trade_sim_YYYYMMDD_HHMMSS.json --output-dir reports/charts
```

## Supported Reports

Report type is auto-detected from schema keys:

- `trade_sim`
- `backtest`
- `strategy_eval`
- `factor_eval`
- `factor_backtest`
- `portfolio_construction`
- `walk_forward`
- `risk`
- `multi_factor`
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

## Outputs

Generated files are written under:

```text
reports/charts/
```

Each chart is written as:

- `.png`
- `.svg`

Each report also gets:

- `*_summary.html`

`reports/charts/` is ignored by git because charts are generated artifacts.

## Dashboard

The summary dashboard includes:

- report type
- key metrics
- warnings
- interpretation notes
- chart images

Multi-factor reports generate charts for family contribution, factor contribution, confidence, and stability ranking.

Factor Store reports generate charts for stored table counts, IC history, Rank IC history, factor rankings, stability history, coverage history, and coverage rankings when those fields exist.

Regime reports generate charts for regime timeline, regime frequency, regime confidence, factor performance by regime, and regime-aware ranking diagnostics when those fields exist.

Trade simulation reports with v0.30 market realism fields can also generate charts for slippage, cost breakdown, rejected trades, and liquidity usage. Missing fields skip those charts with warnings rather than crashing.

## Agent Export

Agent Export detects generated chart files next to the source report and includes them in `visualization_paths`. The source JSON report is not modified.

```bash
python -m quant.cli export-for-agent --report reports/trade_sim_YYYYMMDD_HHMMSS.json
```

## Boundary

Visualization is offline review infrastructure only. It is not investment advice, not a strategy, not a factor, not live trading, and not broker execution.
## Scheduler Dashboards

`visualize-report` supports `research_run`, `research_status`, and `research_history` reports. Scheduler dashboards can include pipeline status counts, trade simulation metrics, factor ICIR summaries, artifact counts, and run status history. The dashboard is static local HTML with generated chart assets under `reports/charts/`.

## Strategy DSL Dashboards

`visualize-report` supports Strategy DSL and Strategy Gate reports. Dashboards may include factor allocation, portfolio constraints, validation status, strategy run summaries, gate status, warning counts, and numeric gate evidence. Missing fields are skipped with warnings.
