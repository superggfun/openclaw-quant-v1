# Multi-Factor Model

`v0.27.0` adds a formal multi-factor model on top of existing price factors and fundamental factors.

This is an offline factor-combination layer. It does not add machine learning, news sentiment, broker integration, live trading, or high-frequency trading.

## Inputs

The model uses registered factors from `FactorRegistry`:

- Price family: momentum and risk-adjusted momentum factors.
- Value family: price-proxy value and accounting-based fundamental value factors.
- Quality family: price-proxy quality and accounting-based profitability/margin factors.
- Growth family: price trend persistence and accounting-based growth factors.
- Health family: accounting-based leverage and liquidity factors.
- Low volatility family: low-volatility score.
- Reversal family: short and medium horizon reversal scores.

Fundamental factors keep the same no-lookahead rule as v0.26:

```text
report_date <= signal_date
```

`fiscal_period_end` alone is not a tradable availability date.

## Normalization

All factor values are normalized cross-sectionally before combination.

Supported preprocessing:

- rank normalization
- z-score normalization
- optional winsorization
- missing value handling by drop or neutral fill

## Weighting Modes

Supported weighting modes:

- `equal_weight`
- `custom_weight`
- `ic_weighted`
- `stability_weighted`

`ic_weighted` uses IC, RankIC, and ICIR style inputs when supplied. `stability_weighted` combines supplied stability scores with coverage. If quality inputs are unavailable, the model falls back deterministically rather than inventing data.

`stability_weighted` does not invent stability history. Missing stability inputs emit a warning; if no usable stability scores are supplied, the factor weights fall back to equal weight with an explicit warning.

`v0.32.0` regime diagnostics can report whether a factor has historically been stronger or weaker in the current market regime. This is diagnostic context only. The multi-factor model does not automatically disable factors or change weights from regime labels.

Regime labels are heuristic historical classifications. They are not forecasts or timing signals, and multi-factor confidence remains diagnostic rather than a return guarantee.

## Output

Reports are written as:

```text
reports/multi_factor_YYYYMMDD_HHMMSS.json
```

Reports include factor scores, family scores, factor weights, factor weights normalized inside each family, family weights, factor contributions, family contributions, coverage, factor confidence, overall confidence, stability classification, final alpha score, and warnings.

## Alpha Configuration

`examples/alpha_config.json` enables the formal model with:

```json
{
  "weighting_mode": "stability_weighted",
  "family_weights": {
    "PRICE": 0.25,
    "VALUE": 0.25,
    "QUALITY": 0.20,
    "GROWTH": 0.20,
    "HEALTH": 0.10
  },
  "multi_factor": {
    "weighting_mode": "stability_weighted",
    "normalization": "rank",
    "missing": "drop"
  }
}
```

When `weighting_mode` is `stability_weighted`, `ic_weighted`, or `custom_weight`, it controls factor blending. Target allocation remains constrained by `min_cash_weight`, `max_position_weight`, and the existing Alpha target logic.

## Coverage And Confidence

Coverage is the percentage of universe symbols with a finite value for a factor on the signal date. Fundamental factors often have lower coverage until the fundamental database is expanded.

Confidence is coverage-aware. Low coverage lowers factor confidence and overall confidence. The model emits `LOW_FACTOR_COVERAGE` warnings instead of silently treating missing fundamentals as real zeros.

Confidence is a diagnostic reliability score, not a return forecast and not a performance guarantee. Low fundamental coverage weakens the reliability of the blended score and should be reviewed before promoting any configuration.

## Agent Export And Visualization

Agent Export supports `multi_factor` reports and summarizes top symbols, family weights, coverage, confidence, warnings, and recommended next checks.

Visualization supports multi-factor charts for family contribution, factor contribution, confidence, and stability ranking.
