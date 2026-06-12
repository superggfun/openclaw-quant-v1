# Fundamental Factors

`v0.26.0` adds true accounting-based factors on top of the `v0.25.0` fundamental data layer.

This is still offline research infrastructure. It is not investment advice, does not connect to brokers, does not perform live trading, and does not use machine learning or news sentiment.

## No-Lookahead Rule

Fundamental factors must use only rows whose `report_date <= signal_date`.

`fiscal_period_end` is never sufficient by itself because it is the accounting period close, not the market availability date. Every v0.26 factor reads fundamentals through a report-date-aware lookup and ignores rows reported after the signal date.

## Factor Families

Value:

- `pe_value_factor`: lower positive PE scores higher.
- `pb_value_factor`: lower positive PB scores higher.
- `ev_ebitda_factor`: lower positive EV/EBITDA scores higher.
- `value_composite`
- `fundamental_value_score`

Quality:

- `roe_quality_factor`
- `roa_quality_factor`
- `gross_margin_factor`
- `net_margin_factor`
- `quality_composite`
- `fundamental_quality_score`

Growth:

- `revenue_growth_factor`
- `eps_growth_factor`
- `growth_composite`
- `fundamental_growth_score`

Financial health:

- `debt_to_equity_factor`: lower debt-to-equity scores higher.
- `current_ratio_factor`: current ratio closest to 2.0 scores higher.
- `quick_ratio_factor`: quick ratio closest to 1.0 scores higher.
- `financial_health_composite`
- `fundamental_health_score`

Composite:

- `fundamental_composite_score`: combines value, quality, growth, and financial health components.

## Missing Data

Missing metrics are skipped inside composites. Remaining valid components are normalized by the number of available components.

The system does not fill missing fundamentals with zero and does not invent values. If a symbol has no usable report-date-filtered row, the factor value is missing and reports may emit:

- `MISSING_FUNDAMENTAL_DATA`
- `PARTIAL_FUNDAMENTAL_DATA`

## CLI

```bash
python -m quant.cli factor-list
python -m quant.cli factor-eval --factor fundamental_quality_score
python -m quant.cli factor-backtest --factor fundamental_value_score
python -m quant.cli alpha
python -m quant.cli walk-forward --strategy alpha --max-folds 1
```

`factor-eval` and `factor-backtest` reports include `factor_coverage`, including coverage percentage, missing percentage, metrics used, report-date coverage, and the no-lookahead filter.

Full alpha walk-forward validation keeps the existing default fold behavior. Fundamental composite alpha can be more expensive than price-only alpha, so smoke checks should pass `--max-folds 1` or `--max-folds 2` explicitly.

`factor-list` marks these factors with `fundamental_data_required=true`.
