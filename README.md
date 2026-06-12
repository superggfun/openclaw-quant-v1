# openclaw-quant-v1

OpenClaw Quant is an offline quantitative research and simulation framework. It is designed for reproducible data workflows, factor research, portfolio construction, historical simulation, validation, report export, and future OpenClaw-style agent integration.

This project is research infrastructure only. It is not investment advice, does not connect to brokers, does not place live orders, does not run high-frequency trading, and does not use machine learning or news sentiment.

## Current Version

`v0.36.0-strategy-dsl`

This release adds Strategy DSL definitions as structured, versioned offline research objects.

No alpha factors, data providers, broker integrations, live trading, order submission, machine learning, report schemas, quant calculation behavior, or no-lookahead rules are intentionally changed in v0.36.

Strategy DSL commands and MCP tools orchestrate existing offline engines only. MCP capability gates still enable only `READ_ONLY` and `OFFLINE_SIMULATION`; paper/live trading capabilities are reserved or forbidden and blocked before execution.

## Quick Start

From WSL2:

```bash
cd /mnt/c/Users/Alphay/Desktop/qua/openclaw-quant-v1
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
pytest
python tools/project_audit.py
```

Editable install:

```bash
python -m pip install -e ".[core,dev]"
openclaw-quant factor-list
```

The existing requirements workflow remains supported.

## CLI Examples

Provider and data checks:

```bash
python -m quant.cli provider-list
python -m quant.cli provider-health
python -m quant.cli data-coverage
python -m quant.cli research-readiness
```

Factor and alpha research:

```bash
python -m quant.cli factor-list
python -m quant.cli factor-eval --factor fundamental_quality_score
python -m quant.cli factor-backtest --factor fundamental_value_score
python -m quant.cli factor-eval --factor momentum_20d --save-factor-history
python -m quant.cli factor-history --factor momentum_20d
python -m quant.cli factor-rank
python -m quant.cli detect-regime
python -m quant.cli regime-rank
python -m quant.cli alpha
python -m quant.cli walk-forward --strategy alpha --max-folds 1
```

Portfolio and simulation:

```bash
python -m quant.cli init-account --cash 100000
python -m quant.cli portfolio
python -m quant.cli portfolio-construct --method risk_parity
python -m quant.cli trade-sim --strategy alpha --start 2024-01-01 --end 2025-01-01 --initial-cash 100000 --rebalance-frequency monthly --portfolio-method equal_weight
python -m quant.cli trade-sim --strategy alpha --portfolio-method risk_parity --market-realism-config examples/market_realism_config.json
```

Reports:

```bash
python -m quant.cli export-for-agent --report reports/example.json
python -m quant.cli visualize-report --report reports/example.json
python -m quant.cli mcp-list-tools
python -m quant.cli mcp-smoke
python -m quant.cli strategy-list
python -m quant.cli strategy-validate
```

See `docs/CLI.md` and `docs/CLI_COMMANDS.md` for the full command reference.

## Core Features

- SQLite daily OHLCV storage with idempotent updates.
- Data provider abstraction with yfinance as the default public daily-data provider.
- CSV and mock providers for offline imports and tests.
- Static symbol metadata, universe construction, coverage reports, data quality checks, and research readiness scoring.
- Fundamental statement and metrics storage with CSV import, coverage, and quality diagnostics.
- Price factors and report-date-aware fundamental factors.
- Formal multi-factor model with factor families, normalization, coverage-aware confidence, and contribution reporting.
- Alpha target generation with no-lookahead signal dates.
- Factor pipeline, factor evaluation, long-short factor backtest, and walk-forward validation.
- Persistent factor store for definitions, values, IC history, backtest history, walk-forward folds, stability, coverage, and versions.
- Deterministic regime detection and factor-by-regime diagnostics.
- Daily Research Scheduler for offline pipeline automation.
- Local MCP-compatible research interface for OpenClaw-style tool access.
- Strategy DSL definitions for reproducible research strategy configuration.
- Portfolio construction methods including equal weight, inverse volatility, risk parity, and minimum variance.
- Simulated portfolio state, rebalance planning, cost estimation, execution simulation, historical trading simulation, and market realism constraints.
- Unified account/order/fill/position protocol objects for future MCP/OpenClaw integration.
- Strategy evaluation, agent export, and visualization dashboards.

## Architecture Overview

```text
CLI -> Services / Engines -> Data Providers / Storage -> SQLite / yfinance / CSV / mock
```

Layered package areas:

- `quant/core/`: protocols, validation, and shared warning helpers.
- `quant/data/`: data providers, data quality/universe layer, and fundamental data.
- `quant/factors/`: price factors, fundamental factors, and factor store access.
- `quant/engines/`: pure quant/research/simulation engines.
- `quant/services/`: application orchestration services.
- `quant/reports/`: agent export and visualization.
- `quant/interfaces/`: CLI boundary, local MCP research interface, and reserved API namespace.
- `quant/strategy_dsl/`: versioned research strategy definitions and validation.
- `quant/adapters/`: reserved external framework adapter namespaces.
- `quant/scheduler/`: failure-isolated daily research pipeline automation.

Legacy paths such as `quant/core_protocols`, `quant/data_providers`, `quant/alpha`, and `quant/agent_export` remain import-compatible for at least this release. API/adapters are placeholders only; the MCP interface in v0.35 is local research infrastructure, not a broker or execution API.

## No-Lookahead Contract

Price factors use price rows at or before the signal date.

Fundamental factors use:

```text
report_date <= signal_date
```

`fiscal_period_end` alone is not a tradable availability date. Future returns are labels for evaluation only and must not affect signal generation, ranking, target weights, or portfolio construction.

## Packaging And Dependencies

`pyproject.toml` defines package metadata and optional dependency groups:

- `core`: pandas and yfinance
- `visualization`: reserved for optional visualization dependencies; current charts are dependency-free
- `dev`: pytest

Provider-specific imports are lazy. If `yfinance` is not installed, provider discovery, project audit, mock/CSV workflows, and most CLI startup paths still work. The yfinance provider reports `NOT_INSTALLED` until the optional package is installed.

## Generated Files

Generated local artifacts are intentionally ignored:

- `data/quant.db`
- `reports/*.json`
- `reports/agent_summary.*`
- `reports/charts/`
- `examples/portfolio_constructed_targets.json`

## Documentation Index

- `docs/ARCHITECTURE.md`
- `docs/AI_DEVELOPMENT.md`
- `docs/CLI.md`
- `docs/CLI_COMMANDS.md`
- `docs/DATA_SCHEMA.md`
- `docs/DATA_LAYER.md`
- `docs/DATA_PROVIDERS.md`
- `docs/FUNDAMENTAL_DATA.md`
- `docs/FUNDAMENTAL_FACTORS.md`
- `docs/MULTI_FACTOR.md`
- `docs/MARKET_REALISM.md`
- `docs/FACTOR_LIBRARY.md`
- `docs/FACTOR_STORE.md`
- `docs/REGIME_DETECTION.md`
- `docs/SCHEDULER.md`
- `docs/FACTOR_PIPELINE.md`
- `docs/FACTOR_EVALUATION.md`
- `docs/FACTOR_BACKTEST.md`
- `docs/PORTFOLIO_CONSTRUCTION.md`
- `docs/PROTOCOLS.md`
- `docs/TRADING_SIMULATION.md`
- `docs/WALK_FORWARD.md`
- `docs/STRATEGY_EVALUATION.md`
- `docs/AGENT_EXPORT.md`
- `docs/VISUALIZATION.md`
- `docs/PACKAGING.md`
- `docs/MCP_SERVER.md`
- `docs/STRATEGY_DSL.md`
- `docs/ROADMAP.md`
- `docs/DECISIONS.md`

## Development Status

The framework is early and research-focused. Stable boundaries are CLI commands, report readers, storage layers, and deterministic engine APIs. New features should include tests, documentation, and CLI coverage.

Recommended validation before release:

```bash
pytest
python tools/project_audit.py
python -m quant.cli provider-list
python -m quant.cli factor-list
python -m quant.cli trade-sim --help
python -m quant.cli research-run --skip-data-refresh --skip-trade-sim
```

## Contributing

Use the GitHub issue templates for bugs and feature requests. Pull requests should include validation notes and confirm that no generated local reports, charts, or databases are committed.

Do not add live broker execution, credentials, automatic trading, machine learning, or news sentiment unless a future release explicitly scopes and designs that work.

## License

MIT License. See `LICENSE`.
