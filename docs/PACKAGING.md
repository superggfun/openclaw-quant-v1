# Packaging And CI

`v0.28.0` adds packaging and continuous integration infrastructure.

This is engineering infrastructure only. It does not add factors, trading logic, data providers, broker integration, news sentiment, or machine learning.

## Install

The project remains compatible with the existing requirements workflow:

```bash
python -m pip install -r requirements.txt
```

It can also be installed as an editable package:

```bash
python -m pip install -e ".[core,dev]"
```

CI installs the project with `.[dev]` so test runs also validate startup when optional provider packages such as `yfinance` are absent. Release QA can still run `python -m pip install -e ".[core,dev]"` to verify the full Yahoo Finance provider extra.

## pyproject.toml

`pyproject.toml` uses PEP 621 metadata:

- package name: `openclaw-quant`
- Python: `>=3.11`
- license: MIT
- console script: `openclaw-quant`

Optional dependency groups:

- `core`: pandas and yfinance for daily Yahoo Finance data
- `visualization`: reserved for optional visualization dependencies; current charts are dependency-free
- `dev`: pytest

## Lazy Optional Imports

Provider-specific dependencies stay inside provider modules. `yfinance` is imported only when the yfinance provider actually needs it.

If `yfinance` is missing:

- `provider-list` still works
- `provider-health` reports yfinance as `NOT_INSTALLED`
- project audit still works
- mock and CSV provider tests still work

Only yfinance downloads require the yfinance package.

## CI

GitHub Actions workflows:

- `.github/workflows/ci.yml`: runs pytest and project audit on Python 3.11 and 3.12
- `.github/workflows/project_audit.yml`: runs the lightweight project audit

CI does not require `data/quant.db`, generated reports, charts, broker credentials, or live market data.

## Repository Health

The release adds:

- MIT `LICENSE`
- bug report template
- feature request template
- pull request template

## Package Layout

`v0.34.0` is phase 1 of the layered namespace refactor. It adds layered package namespaces while keeping legacy import paths available. The editable install includes both old compatibility packages and new preferred packages because `pyproject.toml` discovers packages under `quant*`.

Preferred new paths:

- `quant.core.*`
- `quant.data.*`
- `quant.factors.*`
- `quant.engines.*`
- `quant.reports.*`
- `quant.interfaces.*`
- `quant.adapters.*`

The `quant.interfaces.mcp_server`, `quant.interfaces.api`, and `quant.adapters.*` namespaces are packaging placeholders only. They do not add MCP, API, OpenClaw, LangChain, QuantStats, or PyFolio integrations.

Most implementation modules remain in their original locations in this phase. Future physical moves should be gradual and must preserve compatibility shims until a planned removal release.

## Boundaries

Packaging and CI are not investment advice, not live trading, and not broker execution. Generated artifacts such as `data/quant.db`, `reports/*.json`, `reports/charts/`, and agent summaries remain ignored.
