# Data Providers

`v0.24.0` introduces a data provider abstraction layer. The default provider remains Yahoo Finance through `yfinance`, but services now depend on a `DataProvider` interface instead of direct `yfinance` calls.

Only `yfinance` is implemented as a live public daily data provider in this release. CSV is local-file only, mock is tests-only, and AkShare/Tushare/A-share providers are not implemented yet.

This is an architecture release only. It does not add factors, change backtests, change factor evaluation semantics, connect brokers, provide real-time data, or implement high-frequency trading.

## Commands

```bash
python -m quant.cli provider-list
python -m quant.cli provider-health
python -m quant.cli provider-info yfinance
```

## Interface

Providers implement:

- `get_price_history`
- `get_symbol_metadata`
- `get_latest_price`
- `refresh_symbol`
- `refresh_universe`
- `health_check`

Price refresh, `update-prices`, coverage, and readiness workflows resolve provider behavior through this interface.

## Registered Providers

- `yfinance`: default Yahoo Finance daily OHLCV provider.
- `csv`: local CSV provider for offline imports and tests.
- `mock`: deterministic in-memory provider for tests.
- `akshare`: placeholder, not installed.
- `tushare`: placeholder, not installed.
- `alpha_vantage`: placeholder, not installed.
- `polygon`: placeholder, not installed.

Provider specs are auto-discovered from `quant/data/providers/`.

To add a provider:

1. Implement a `DataProvider` subclass in `quant/data/providers/`.
2. Expose `PROVIDER_SPECS = (ProviderSpec("provider_name", ProviderClass),)` from that module.
3. Add health-check, normalization, CLI/provider-registry, and optional-dependency tests.

Do not edit `ProviderRegistry` for ordinary provider additions. The registry discovers provider specs, instantiates providers, and preserves `yfinance` as the default unless configuration changes it.

## CSV Provider

The CSV provider supports either one combined file or symbol files:

```text
data/csv/prices.csv
data/csv/SPY.csv
```

Required columns:

- `date`
- `symbol`
- `open`
- `high`
- `low`
- `close`
- `adj_close`
- `volume`

Column names like `Date`, `Open`, `Adj Close`, and `Volume` are normalized.

## Health Checks

Health checks return:

- `healthy`
- `status`
- `warning`
- `error`
- `messages`

`provider-health` does not download market data. The default `yfinance` health check verifies package availability and avoids network calls.

As of `v0.28.0`, provider-specific dependencies are isolated behind lazy imports. Missing `yfinance` marks the yfinance provider as `NOT_INSTALLED`, but the rest of the CLI, project audit, CSV provider, mock provider, and placeholder provider metadata remain available. Install the core dependency set with `pip install -e ".[core]"` or continue using `pip install -r requirements.txt`.

## Boundaries

The provider layer is offline research infrastructure. It does not provide live broker execution, real-time market data guarantees, investment advice, machine learning, options data, or high-frequency workflows.
