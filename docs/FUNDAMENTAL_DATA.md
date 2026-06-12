# Fundamental Data

`v0.25.0` adds the storage, CSV import, query, coverage, and quality foundation for future fundamental factors.

This release created the data foundation. `v0.26.0` builds true PE/PB/ROE/ROA/revenue growth/EPS growth style factors on this data. Neither layer connects brokers, provides paid API integration, uses machine learning, or provides investment advice.

## Commands

```bash
python -m quant.cli fundamental-import --file examples/fundamentals_sample.csv
python -m quant.cli fundamental-import --file examples/fundamentals_sample.csv --statement income
python -m quant.cli fundamental-import --file examples/fundamentals_sample.csv --force
python -m quant.cli fundamental-show --symbol AAPL --latest
python -m quant.cli fundamental-show --symbol AAPL --statement income
python -m quant.cli fundamental-coverage
python -m quant.cli fundamental-quality
python -m quant.cli fundamental-quality --symbol AAPL
```

## Supported Tables

- `income_statement`
- `balance_sheet`
- `cash_flow`
- `fundamental_metrics`
- `fundamental_import_log`

Rows preserve both `fiscal_period_end` and `report_date`. Research code must use `report_date` for no-lookahead alignment.

## No-Lookahead Rules

`fiscal_period_end` is the accounting period close, not the date when the data was tradable or known to the market. Future fundamental factors must filter on `report_date <= signal_date`; using `fiscal_period_end` alone is not enough and can introduce lookahead bias.

`fundamental-show --latest` is a database query helper. It shows the latest stored row by `report_date` and `fiscal_period_end`, but it does not by itself mean the row was available on an arbitrary historical signal date. Historical research must pass through a signal-date filter before using fundamentals.

## CSV Import

CSV is currently the primary supported import path. The importer accepts:

- wide CSV files with `statement_type`
- statement-specific CSV files when `--statement` is supplied

Required common columns:

- `symbol`
- `fiscal_period_end`
- `report_date`
- `fiscal_year`
- `fiscal_quarter`
- `currency`

Blank numeric values are stored as missing values. Symbols are uppercased. Dates are normalized to `YYYY-MM-DD`.

Repeated imports are idempotent. Existing rows are keyed by `symbol`, `fiscal_period_end`, and `fiscal_quarter` inside each statement table. Older `report_date` rows do not overwrite newer rows unless `--force` is used.

## Reports

Generated reports are ignored by git:

- `reports/fundamental_import_YYYYMMDD_HHMMSS.json`
- `reports/fundamental_coverage_YYYYMMDD_HHMMSS.json`
- `reports/fundamental_quality_YYYYMMDD_HHMMSS.json`

Report sections include:

- `metadata`
- `parameters`
- `summary`
- `coverage`
- `quality_checks`
- `warnings`
- `no_lookahead_notes`
- `interpretation_notes`

## Quality Checks

The quality layer checks:

- duplicate rows
- missing fiscal period end
- missing report date
- report date before fiscal period end
- negative revenue
- negative total assets
- zero or negative total equity
- missing shares outstanding
- currency mismatch
- missing sequential quarterly records
- stale reports
- extreme ratio values

Warnings are research diagnostics only. They do not generate trades or target allocations.

## Agent Export

Agent Export supports:

- `fundamental_import`
- `fundamental_coverage`
- `fundamental_quality`

Summaries include readiness score, symbols covered, missing symbols, latest report date, and key quality warnings.

## Visualization

`visualize-report` can create small bar charts for:

- statement coverage in `fundamental_coverage`
- warning reason counts in `fundamental_quality`

See `docs/FUNDAMENTAL_FACTORS.md` for the v0.26 factor layer built on this data.
