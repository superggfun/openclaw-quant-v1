# Strategy Evaluation

Strategy Evaluation explains return, risk, attribution, and robustness from generated strategy reports.

It answers:

- why a strategy made or lost money
- where return came from
- where costs and turnover mattered
- whether results are concentrated or fragile

It does not create new alpha factors, introduce new strategies, connect to brokers, modify portfolio state, or execute live trades.

## Inputs

Supported inputs:

- `reports/factor_backtest_*.json`
- `reports/backtest_*.json`

The CLI can also generate a fresh source report first, then evaluate that report:

```bash
python -m quant.cli strategy-eval --strategy factor_long_short --factor momentum_20d
python -m quant.cli strategy-eval --strategy factor_long_short --factor momentum_20d --pipeline examples/factor_pipeline_config.json
python -m quant.cli strategy-eval --strategy alpha --pipeline examples/factor_pipeline_config.json
```

Existing report inputs:

```bash
python -m quant.cli strategy-eval --factor-backtest-report reports/factor_backtest_YYYYMMDD_HHMMSS.json
python -m quant.cli strategy-eval --backtest-report reports/backtest_YYYYMMDD_HHMMSS.json
python -m quant.cli strategy-eval --report reports/factor_backtest_YYYYMMDD_HHMMSS.json
```

Optional benchmark and output path:

```bash
python -m quant.cli strategy-eval --factor-backtest-report reports/factor_backtest_YYYYMMDD_HHMMSS.json --benchmark SPY
python -m quant.cli strategy-eval --strategy factor_long_short --factor momentum_20d --output reports/strategy_eval_custom.json
```

## Report

Reports are written as:

```text
reports/strategy_eval_YYYYMMDD_HHMMSS.json
```

Top-level sections:

- `metadata`
- `input_report_paths`
- `strategy_type`
- `evaluation_window`
- `summary_metrics`
- `benchmark_metrics`
- `attribution`
- `robustness_diagnostics`
- `warnings`
- `interpretation_notes`

## Summary Metrics

Summary metrics include:

- `total_return`
- `annual_return`
- `annual_volatility`
- `sharpe_ratio`
- `sortino_ratio`
- `max_drawdown`
- `calmar_ratio`
- `hit_rate`
- `win_loss_ratio`
- `average_win`
- `average_loss`
- `best_period`
- `worst_period`
- `turnover`
- `total_cost`
- `cost_to_return_ratio`
- `gross_exposure`
- `net_exposure`
- `cash_drag`
- `benchmark_return`, `excess_return`, and `information_ratio` when a benchmark is supplied

## Attribution

Return attribution includes:

- return contribution by symbol
- long side, short side, and long-short contribution for factor reports
- cash drag
- cost drag
- monthly or period return attribution

Cost and turnover attribution are reported by symbol when the source report contains trades.

Top positive contributors, top negative contributors, and return concentration are included to show whether performance depends on a small number of names.

For factor long-short reports:

- `long_side` and `short_side` preserve the raw V1.3 leg return fields from the source report.
- `raw_short_leg_underlying_return` is the compounded return of the underlying short basket.
- `short_side_contribution` is sign-adjusted for the long-short spread, so a falling short basket contributes positively.
- `by_symbol` contributions are arithmetic period contributions using long weights and negative short weights. They are attribution diagnostics and are not compounded portfolio returns.

## Robustness Diagnostics

Diagnostics emit warning objects with clear reason codes, including:

- `LOW_OBSERVATION_COUNT`
- `HIGH_TURNOVER`
- `HIGH_COST_DRAG`
- `NEGATIVE_COMPOUND_POSITIVE_SHARPE`
- `LARGE_DRAWDOWN`
- `BENCHMARK_UNDERPERFORMANCE`
- `SYMBOL_CONCENTRATION`
- `LONG_SHORT_IMBALANCE`
- `NO_LOOKAHEAD_NOT_MARKED`
- `CAPITAL_WIPEOUT_OR_MARGIN_LOSS`

These warnings are not trade signals. They are research quality checks for offline review.

## No-Lookahead Compatibility

Strategy Evaluation preserves no-lookahead metadata from source reports. It does not recompute signals or use future prices to form groups or targets.

When the source report is not marked `no_lookahead: true`, the evaluator adds a compatibility warning.

## Drawdown

Strategy Evaluation computes drawdown from the evaluated return stream with initial capital treated as the starting high-water mark. This avoids hiding a loss that occurs in the first evaluated period.

For long-short spread returns, drawdown may reach or exceed `-100%` because spread returns can represent margin-style losses rather than a long-only cash account. In that case the report emits `CAPITAL_WIPEOUT_OR_MARGIN_LOSS`.

## Boundary

Strategy Evaluation is an explanation layer over existing reports.

It does not recalculate signals, change target allocations, alter portfolio state, execute trades, or provide investment advice.
