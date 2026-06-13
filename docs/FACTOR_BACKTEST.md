# Long-Short Factor Backtest

The Long-Short Factor Backtest checks whether one factor can produce an equal-weight long-short factor spread return stream.

It is not Strategy Evaluation and it is not Performance Attribution. v0.14 implements those as a separate report-reading module.

It does not explain why returns happened inside the factor backtest itself. Use Strategy Evaluation to explain a generated factor backtest report.

The module does not modify simulated portfolio state, write trades, connect to brokers, call AI models, or execute orders.

## No-Lookahead Rule

For each `signal_date`:

- factor values use only prices at or before `signal_date`
- optional Factor Pipeline preprocessing is applied only to that same-date cross-section
- future return uses a later stored close: `signal_date + holding_period`

The report includes:

```text
no_lookahead: true
signal_execution_lag: factor uses signal_date and earlier; future_return uses T+N close
```

## Method

1. Calculate one factor for each symbol on each signal date.
2. Optionally clean the cross-section with Factor Pipeline.
3. Sort symbols by factor score.
4. Split symbols into `N` quantiles.
5. Long the configured top quantile.
6. Short the configured bottom quantile.
7. Calculate equal-weight long-short return from forward returns.

Construction checks:

- long leg weights sum to approximately `+1`
- short leg weights sum to approximately `-1`
- net exposure is approximately `0`
- gross exposure is approximately `2`

If a signal date cannot form both a long leg and a short leg, that period is reported but excluded from long-short return, turnover, and exposure summary metrics.

Default settings:

- `holding_period`: `20`
- `quantiles`: `5`
- `long_quantile`: top quantile
- `short_quantile`: `1`

## CLI

```bash
python -m quant.cli factor-backtest --factor momentum_20d
python -m quant.cli factor-backtest --factor momentum_20d --pipeline examples/factor_pipeline_config.json
python -m quant.cli factor-backtest --factor momentum_20d --save-regime-history
python -m quant.cli factor-backtest --factor risk_adjusted_momentum --start 2024-01-01 --end 2024-12-31 --holding-period 20 --quantiles 5
```

Supported arguments:

- `--factor`
- `--start`
- `--end`
- `--holding-period`
- `--quantiles`
- `--long-quantile`
- `--short-quantile`
- `--pipeline`
- `--report`
- `--save-regime-history`

Reports are written by default.

`--save-regime-history` stores factor spread diagnostics by the persisted market regime active on each signal date. It is diagnostic only and does not change long/short construction.

## Metrics

- `observations`
- `quantile_returns`
- `top_quantile_return`
- `bottom_quantile_return`
- `long_short_return`
- `long_short_annual_return`
- `long_short_volatility`
- `long_short_sharpe`
- `max_drawdown`
- `hit_rate`
- `turnover`
- `ic_mean`
- `rank_ic_mean`
- `icir`
- `excluded_symbols`
- `exclusion_reasons`
- `no_lookahead`
- `signal_execution_lag`
- `gross_exposure`
- `net_exposure`
- `long_symbols_by_date`
- `short_symbols_by_date`

`long_short_return` is a compounded return over the period return stream.

`long_short_sharpe` uses the arithmetic mean and standard deviation of period long-short returns, annualized with `sqrt(252)`. Because compounded return and arithmetic mean are different statistics, they can differ in sign in high-volatility samples. This is possible without a sign bug.

Long-short factor returns may also disagree with IC direction because of sample filtering, quantile boundaries, equal-weight portfolio construction, overlapping holding windows, pipeline transformations, missing symbols, and costs not being modeled in v0.13.

## Reports

Reports are written as:

```text
reports/factor_backtest_<factor>_YYYYMMDD_HHMMSS_<id>.json
```

Top-level keys match the printed metrics and include per-period long symbols, short symbols, long and short weights, net exposure, gross exposure, quantile returns, long-short returns, and turnover.

## Boundary

Use Factor Evaluation for IC, Rank IC, quintile, and decay diagnostics.

Use Long-Short Factor Backtest to check whether a single factor creates a plausible return stream.

Do not treat this module as full strategy evaluation. Portfolio-level explanation, benchmark comparison, exposure attribution, risk contribution, exposure decomposition, and performance attribution are handled by the separate Strategy Evaluation layer.

Use `docs/STRATEGY_EVALUATION.md` and `python -m quant.cli strategy-eval --factor-backtest-report <factor_backtest_report>` to explain a generated factor backtest report.

## v0.41 Bulk Matrix Reuse

`FactorBacktest.run(..., bulk_matrix=True)` can reuse the semantic-preserving observation matrix builder introduced for factor evaluation. The long-short, quantile, turnover, exposure, IC, Rank IC, and drawdown formulas are unchanged. This path is intended for explicit acceleration callers such as research-validation.
