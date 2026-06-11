# Factor Evaluation Framework

The Factor Evaluation Framework measures whether an alpha factor has useful cross-sectional predictive power.

It reads stored prices only. It does not download data, generate trades, update portfolio state, call AI models, or execute orders.

## No-Lookahead Rule

Factor evaluation uses two separate dates:

- `signal_date`: the date when factor values are calculated.
- `future_date`: the date used to calculate forward returns.

For every `signal_date`, the factor calculation receives only rows where `date <= signal_date`. Forward returns are calculated from `signal_date` to `future_date`, where `future_date` is `forward_days` stored price rows later.

This means a factor can use past and current information only, while the evaluation target always comes from the future window.

## Supported Factors

- `momentum_20d`
- `momentum_60d`
- `volatility_20d`
- `risk_adjusted_momentum`

The factor definitions match the Alpha Engine so research evaluation and target generation use the same data constraints.

## Metrics

IC:

```text
corr(factor_t, future_return_t)
```

Rank IC:

```text
spearman_rank_correlation(factor_t, future_return_t)
```

ICIR:

```text
ic_mean / ic_std
```

Quintile analysis sorts the cross-section by factor value and calculates average future return for `q1` through `q5`. `spread_return` is:

```text
q5_return - q1_return
```

Factor decay evaluates IC and Rank IC for:

- `1d`
- `5d`
- `10d`
- `20d`
- `60d`

## CLI

```bash
python -m quant.cli factor-eval --factor momentum_20d
python -m quant.cli factor-eval --factor momentum_20d --pipeline examples/factor_pipeline_config.json
python -m quant.cli factor-eval --factor risk_adjusted_momentum
python -m quant.cli factor-eval --factor momentum_60d --start 2024-01-01 --end 2024-12-31 --forward-days 20
```

The CLI prints:

- IC mean, standard deviation, positive rate, and count
- Rank IC mean, standard deviation, positive rate, and count
- ICIR
- Quintile returns
- Spread return
- Decay curve
- Excluded symbols and reasons

## Reports

Reports are written as:

```text
reports/factor_eval_YYYYMMDD_HHMMSS.json
```

Top-level keys include:

- `factor`
- `start_date`
- `end_date`
- `forward_days`
- `universe`
- `no_lookahead`
- `ic_mean`
- `ic_std`
- `ic_positive_rate`
- `ic_count`
- `rank_ic_mean`
- `rank_ic_std`
- `rank_ic_positive_rate`
- `rank_ic_count`
- `icir`
- `quintiles`
- `spread_return`
- `decay`
- `observations`
- `excluded_symbols`
- `exclusion_reasons`
- `warnings`

Each observation records `signal_date`, `future_date`, `symbol`, `factor_value`, `future_return`, and `forward_days`.

When `--pipeline` is supplied, `factor_value` contains the cleaned same-date cross-sectional value used for IC, Rank IC, quintiles, and decay. Raw factor preprocessing details are documented in `docs/FACTOR_PIPELINE.md`.

## Edge Cases

Symbols with no prices, missing closes, insufficient lookback history, zero volatility, or no valid future-return window are excluded from the evaluation sample and reported with a reason.

Single-symbol evaluations can produce factor observations and quintile data, but IC and Rank IC require at least two symbols on a signal date.

## Relationship To Strategy Evaluation

Factor Evaluation measures predictive quality with IC, Rank IC, quintiles, and decay. It does not explain portfolio returns or risk.

Use `python -m quant.cli factor-backtest --factor <factor>` to create a factor spread return stream, then use `python -m quant.cli strategy-eval --factor-backtest-report <report>` for v0.14 performance attribution and robustness diagnostics.

## v0.19 Factor Registry

Factor Evaluation resolves supported factors through `FactorRegistry`. In addition to the original momentum and volatility factors, registered factors include `value_score`, `quality_score`, `growth_score`, `reversal_5d`, `reversal_20d`, and `low_volatility_score`.

Reports include `factor_family`, `factor_type`, `factor_category`, `factor_description`, and `factor_inputs` so downstream tools can interpret factor results without filename assumptions.
