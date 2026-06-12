# Strategy DSL

v0.36.0 introduces Strategy DSL definitions as structured, versioned offline research objects.

The DSL does not add live trading, broker access, machine learning, news sentiment, or automatic strategy mutation. It only records how existing engines should be orchestrated.

## Format

YAML is the primary format. JSON is also supported for automation.

Strategy files live under `strategies/`:

- `momentum_fundamental.yaml`
- `quality_growth.yaml`
- `regime_aware_momentum.yaml`

## Sections

- `name`, `description`, `version`, `author`, `created_at`, `tags`
- `universe`: default/custom/sector/ETF/large-cap universe definition.
- `factors`: factor names and deterministic weights.
- `regime`: optional diagnostic regime preferences.
- `portfolio`: construction method, max position weight, and cash buffer.
- `risk`: offline research gates such as drawdown and turnover limits.
- `execution`: simulated cost and market-realism assumptions.
- `validation`: gates such as walk-forward requirement, minimum IC, coverage, and regime sample size.

## Commands

```bash
python -m quant.cli strategy-list
python -m quant.cli strategy-show --strategy momentum_fundamental
python -m quant.cli strategy-validate --file strategies/momentum_fundamental.yaml
python -m quant.cli strategy-run --strategy momentum_fundamental
```

`strategy-run` loads the DSL, validates it, builds alpha configuration, calls existing portfolio construction and trade simulation, and writes a `strategy_run` report. It does not change factor, alpha, trade-sim, scheduler, MCP, or no-lookahead semantics.

Factor weights are checked as supplied. When their sum is positive but not exactly `1.0`, validation emits `WARN_FACTOR_WEIGHTS_NORMALIZED` and reports the normalized weights used by downstream alpha configuration. Negative weights are invalid.

The sample strategies are small deterministic examples for testing and documentation. They are not recommendations.

## Report Fields

`strategy_run` reports include:

- `strategy_name`
- `strategy_version`
- `strategy_file`
- `factors`
- `factor_weights`
- `normalized_factor_weights`
- `portfolio_settings`
- `risk_settings`
- `execution_settings`
- `validation_results`
- `generated_reports`
- `warnings`
- `no_lookahead_notes`

## Persistence

The metadata layer creates:

- `strategy_registry`
- `strategy_versions`
- `strategy_runs`

Definitions are upserted by strategy name and version. Runs are appended with a run id.

## MCP

v0.36 exposes these MCP tools:

- `list_strategies`: `READ_ONLY`
- `show_strategy`: `READ_ONLY`
- `validate_strategy`: `READ_ONLY`
- `run_strategy`: `OFFLINE_SIMULATION`

All broker, order, and live trading tools remain disabled by the capability model.

## Scheduler

The daily research scheduler can optionally run a strategy DSL step through `run_strategy`. The default lightweight daily configuration keeps this disabled so existing scheduler behavior remains unchanged.

## Boundaries

Strategy DSL is for reproducible offline research configuration only. It is not investment advice, not paper/live trading, and not autonomous execution.

Strategy DSL cannot override no-lookahead behavior. Fundamental factors remain gated by `report_date <= signal_date`; `fiscal_period_end` alone is never enough for tradable availability.
