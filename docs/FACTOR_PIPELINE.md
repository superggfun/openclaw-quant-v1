# Factor Pipeline

The Factor Pipeline is a reusable preprocessing layer for cross-sectional factor values.

It sits between raw factor calculation and downstream consumers such as Alpha Engine and Factor Evaluation.

It does not download prices, generate trades, update portfolio state, call AI models, or execute orders.

## No-Lookahead Rule

The pipeline receives factor values that were already calculated for one `as_of_date` or `signal_date`.

It only transforms that same-date cross-section:

- no future prices are read
- no future returns are read
- no future metadata is required
- sector neutralization uses the static sector map supplied in config

Alpha and Factor Evaluation remain responsible for calculating raw factors using only data at or before the signal date.

## Preprocessing Steps

Supported steps:

- missing value handling
- winsorization
- z-score standardization
- sector neutralization
- rank normalization
- market/beta neutralization placeholder

Default order:

```text
missing -> winsorization -> zscore -> sector_neutralization -> rank_normalization -> market_beta_placeholder
```

Missing values can be dropped or filled. The default is `drop`.

Winsorization clips cross-sectional values between configured quantiles.

Z-score standardization subtracts the cross-sectional mean and divides by cross-sectional standard deviation. If standard deviation is zero, values become `0.0`.

Sector neutralization subtracts the sector mean from each symbol using a static sector map.

Rank normalization converts cross-sectional ranks to approximately `[-1, 1]`.

Market/beta neutralization is intentionally a placeholder in V1.2. Enabling it records a warning and does not alter values.

## Config

Default config:

```text
examples/factor_pipeline_config.json
```

Example:

```json
{
  "missing": "drop",
  "winsorization": {
    "enabled": true,
    "lower_quantile": 0.05,
    "upper_quantile": 0.95
  },
  "zscore": true,
  "rank_normalization": false,
  "sector_neutralization": {
    "enabled": true,
    "sector_map": {
      "SPY": "Equity ETF",
      "QQQ": "Equity ETF",
      "NVDA": "Technology"
    }
  },
  "market_beta_neutralization": {
    "enabled": false
  }
}
```

## CLI

Run the pipeline directly:

```bash
python -m quant.cli factor-pipeline --factor momentum_20d
```

Use it in factor evaluation:

```bash
python -m quant.cli factor-eval --factor momentum_20d --pipeline examples/factor_pipeline_config.json
```

Use it in alpha target generation:

```bash
python -m quant.cli alpha --pipeline examples/factor_pipeline_config.json
```

## Reports

Reports are written as:

```text
reports/factor_pipeline_YYYYMMDD_HHMMSS.json
```

Top-level keys:

- `factor`
- `as_of_date`
- `raw_factor_values`
- `cleaned_factor_values`
- `excluded_symbols`
- `exclusion_reasons`
- `preprocessing_steps_applied`
- `before_summary_statistics`
- `after_summary_statistics`
- `sector_neutralization_result`
- `warnings`
- `no_lookahead`

## Integration

Alpha Engine uses cleaned pipeline scores for ranking and score-weighted target generation when `--pipeline` is supplied.

Factor Evaluation runs the pipeline independently for each signal-date cross-section before calculating IC, Rank IC, quintiles, and decay.
