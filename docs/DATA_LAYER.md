# Data Layer

`v0.17.0` expands the research data foundation for larger universes, symbol metadata, historical data refresh, coverage diagnostics, and research readiness scoring. `v0.24.0` adds a provider abstraction so these workflows no longer depend directly on `yfinance` internals.

This layer is offline research infrastructure. The default provider remains Yahoo Finance / `yfinance` daily OHLCV data, but access now goes through `quant/data_providers`. It does not connect to brokers, place orders, provide real-time market data, run high-frequency logic, trade options, or use machine learning.

AkShare, Tushare, A-share universes, and other regional/provider integrations are future provider additions. They are registered as placeholders only.

## Commands

```bash
python -m quant.cli universe-list
python -m quant.cli universe-build
python -m quant.cli universe-build --symbols SPY,QQQ,NVDA
python -m quant.cli universe-build --sector Technology --max-symbols 10
python -m quant.cli provider-list
python -m quant.cli provider-health
python -m quant.cli provider-info yfinance
python -m quant.cli data-refresh
python -m quant.cli data-refresh --universe etf_universe --start-date 2024-01-01 --end-date 2025-01-01
python -m quant.cli data-coverage
python -m quant.cli research-readiness
```

## Universe Management

Supported universe types:

- `default_universe`
- `custom_universe` through `--symbols`
- `sector_universe` through `--sector`
- `etf_universe`
- `large_cap_universe`

Universe output includes selected symbols, excluded symbols, and exclusion reasons such as missing metadata or `max_symbols` limits.

## Symbol Metadata

Metadata is stored in SQLite table `symbol_metadata` and bootstrapped from static project data. Fields:

- `symbol`
- `name`
- `asset_type`
- `sector`
- `industry`
- `currency`
- `exchange`

The bootstrap data covers the original project pool plus additional ETFs and large-cap equities. No paid external provider is required.

## Historical Data Refresh

`data-refresh` uses the default `DataProvider` and SQLite price store. Today the default provider is `yfinance`; future providers can be added behind the same interface without changing refresh or coverage callers.

The command reports inserted, updated, skipped, fetched, and error counts per symbol and writes refresh plus coverage reports. Existing `(symbol, date)` rows are upserted, so repeated runs do not create duplicate price rows. When no `--start-date` is supplied, refresh starts after the latest stored date for each symbol and counts earlier rows as skipped.

## Data Quality

Diagnostics include:

- `missing_ratio`
- `duplicate_rows`
- `price_outliers`
- `zero_volume_days`
- `short_history`
- `data_gaps`
- `zero_negative_prices`
- `stale_data`
- `adjusted_close_availability`

Each check returns `PASS`, `WARNING`, or `FAIL` with an explanation. Reports are written to:

```text
reports/data_quality_YYYYMMDD_HHMMSS.json
```

## Coverage

`data-coverage` reports:

- total symbols
- symbols with price data
- symbols without price data
- average history length
- oldest stored date
- newest stored date

Reports are written to:

```text
reports/data_coverage_YYYYMMDD_HHMMSS.json
```

## Research Readiness

`research-readiness` combines:

- universe size
- history depth
- sector diversity
- factor coverage
- data quality status

It outputs a `0-100` readiness score and recommendations such as:

- Need more symbols
- Need broader price coverage
- Need longer history
- Need sector diversity
- Need factor coverage
- Review data quality warnings

Reports are written to:

```text
reports/research_readiness_YYYYMMDD_HHMMSS.json
```

## No-Lookahead

The data layer does not change factor evaluation or backtest semantics. It manages stored historical data and metadata. Existing no-lookahead rules remain unchanged: factors and signals must use only data available at or before their signal date, and future returns are evaluation-only.
