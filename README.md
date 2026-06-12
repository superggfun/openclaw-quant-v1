# openclaw-quant-v1

`openclaw-quant-v1` is an early OpenClaw-oriented quant system skeleton. It currently includes a market data layer, a simulated portfolio state module, an alpha engine, a factor pipeline, a factor evaluation framework, a long-short factor backtest, a strategy evaluation layer, a portfolio backtest engine, a historical trading simulator, a portfolio rebalance engine, a risk engine, a portfolio optimizer, a portfolio construction/risk parity layer, a cost engine, and an execution simulator. It does not make AI decisions, place live orders, connect to brokers, or perform automated trading.

This project is for research and simulation only. It is not investment advice.

## Current Version

`v0.25.0-fundamental-data-layer`

This release includes:

- CLI parser and command handlers split under `quant/cli_commands/`.
- Data provider abstraction with yfinance as the default provider.
- yfinance daily OHLCV ingestion through the provider interface.
- Fundamental data storage, CSV import, query, coverage, and quality diagnostics.
- SQLite price storage with idempotent updates.
- Expanded research universe management.
- Static symbol metadata storage.
- Data coverage, data quality, and research readiness diagnostics.
- Agent export summaries for OpenClaw, Claude, GPT, Qwen, and other LLM agents.
- Visualization reports with PNG, SVG, and HTML dashboards for existing JSON reports.
- Historical account-style trading simulation with in-memory cash, positions, costs, trade history, and daily equity.
- Simulated account state.
- Simulated positions and trade history.
- Alpha factor generation from stored historical prices.
- Reusable factor preprocessing pipeline for cleaning and neutralization.
- No-lookahead factor evaluation with IC, Rank IC, ICIR, quintile, and decay metrics.
- No-lookahead long-short factor backtest for single-factor profitability checks.
- Strategy evaluation and performance attribution from generated reports.
- Daily portfolio backtest engine using stored prices, optimizer targets, rebalance logic, and costs.
- Portfolio allocation and rebalance calculation engine.
- Portfolio risk metrics and risk score.
- Portfolio optimizer that generates target allocations.
- Portfolio construction methods for equal weight, inverse volatility, risk parity, and minimum variance target weights.
- Transaction cost estimation for rebalance suggestions.
- Simulated execution of rebalance suggestions with immediate, next-day open, TWAP, and partial-fill modes.
- JSON research, factor pipeline, factor evaluation, factor backtest, strategy evaluation, portfolio construction, trade simulation, rebalance, cost, backtest, and execution reports under `reports/`.
- Generated charts and dashboards under `reports/charts/`.
- CLI commands for data, portfolio, alpha, factor pipeline, factor evaluation, factor backtest, strategy evaluation, backtest, allocation, rebalance, risk, optimizer, portfolio construction, cost, and execution workflows.
- pytest coverage for core state transitions.

`v0.25.0` adds a fundamental-data foundation for future true value, quality, and growth factors. It does not create fundamental factor scores yet, change price-only factor semantics, connect brokers, or add machine learning.

## Scope

- Python 3.11+
- Daily US stock and ETF prices from Yahoo Finance through the default `yfinance` provider
- SQLite storage at `data/quant.db`
- Idempotent price updates using `(symbol, date)` as the primary key
- Simulated account, position, and trade tracking in SQLite
- Pure calculation alpha, factor pipeline, factor evaluation, factor backtest, backtest, rebalance, risk, optimizer, portfolio construction, cost, and execution modules
- Fundamental CSV import and diagnostics for offline research
- Reserved OpenClaw integration boundary with no live execution code

Default symbols:

```text
SPY, QQQ, NVDA, AAPL, MSFT, TSLA, AMD, META, GOOGL, TLT, GLD
```

## Project Layout

```text
openclaw-quant-v1/
|- data/
|  `- quant.db
|- docs/
|- examples/
|  `- targets.json
|- quant/
|  |- config.py
|  |- alpha/
|  |- agent_export/
|  |- data_source/
|  |- data_providers/
|  |- backtest/
|  |- cost/
|  |- data_layer/
|  |- cli_commands/
|  |- execution/
|  |- factor_backtest/
|  |- factor_eval/
|  |- factor_pipeline/
|  |- factors/
|  |- fundamental_data/
|  |- optimizer/
|  |- portfolio_construction/
|  |- rebalance/
|  |  `- rebalance_engine.py
|  |- services/
|  |- storage/
|  |- portfolio/
|  |- risk/
|  |- openclaw/
|  |- trading_simulation/
|  |- walk_forward/
|  `- cli.py
|- reports/
|- tests/
|- requirements.txt
`- README.md
```

## Architecture

The project uses a small layered architecture:

```text
CLI -> Services / Engines -> Data Providers / Storage -> SQLite / yfinance / CSV / mock
```

Key modules:

- `quant/cli.py`: command line entry point and command dispatcher.
- `quant/cli_commands/`: parser registration and command handlers for each CLI area.
- `quant/data_layer/`: universe management, symbol metadata, coverage, quality, and readiness diagnostics.
- `quant/data_providers/`: provider abstraction, registry, yfinance provider, CSV provider, mock provider, and future-provider placeholders.
- `quant/fundamental_data/`: fundamental statement storage, CSV import, query, coverage, and quality diagnostics.
- `quant/agent_export/agent_exporter.py`: compact report summaries for LLM/agent contexts.
- `quant/visualization/`: PNG, SVG, and HTML visual reports from existing JSON reports.
- `quant/alpha/alpha_engine.py`: factor calculation and target weight generation.
- `quant/factor_backtest/factor_backtest.py`: long-short factor return backtest.
- `quant/factor_pipeline/factor_pipeline.py`: factor preprocessing, standardization, and neutralization.
- `quant/factor_eval/factor_evaluation.py`: no-lookahead factor evaluation metrics.
- `quant/factors/`: deterministic factor registry and price-history factor implementations.
- `quant/strategy_eval/strategy_evaluation.py`: strategy evaluation and attribution from generated reports.
- `quant/trading_simulation/`: historical account-style simulation with cash, positions, trades, costs, and equity curves.
- `quant/walk_forward/`: walk-forward and rolling validation.
- `quant/services/price_service.py`: price update orchestration.
- `quant/services/portfolio_service.py`: simulated portfolio rules and valuation.
- `quant/services/backtest_service.py`: SMA crossover backtest engine.
- `quant/backtest/backtest_engine.py`: daily portfolio backtest engine.
- `quant/rebalance/rebalance_engine.py`: allocation and rebalance calculations.
- `quant/risk/risk_engine.py`: concentration, cash, Top 5, and risk score calculations.
- `quant/optimizer/optimizer_engine.py`: target allocation generation for rebalance.
- `quant/portfolio_construction/portfolio_construction.py`: portfolio construction, covariance, and risk contribution calculations.
- `quant/cost/cost_engine.py`: fixed, linear, and combined transaction cost estimates.
- `quant/execution/execution_engine.py`: simulated execution of rebalance suggestions.
- `quant/storage/sqlite_store.py`: price persistence.
- `quant/storage/portfolio_store.py`: account, position, and trade persistence.
- `quant/data_source/yfinance_client.py`: legacy yfinance normalization client used by the yfinance provider.

More detail is available in `docs/ARCHITECTURE.md`.

## Install

From WSL2:

```bash
cd /mnt/c/Users/Alphay/Desktop/qua/openclaw-quant-v1
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

## Market Data Commands

```bash
python -m quant.cli update-prices
python -m quant.cli update-prices --symbols SPY QQQ AAPL
python -m quant.cli show-prices SPY --limit 5
python -m quant.cli list-symbols
python -m quant.cli universe-list
python -m quant.cli universe-build --sector Technology --max-symbols 10
python -m quant.cli provider-list
python -m quant.cli provider-health
python -m quant.cli provider-info yfinance
python -m quant.cli fundamental-import --file examples/fundamentals_sample.csv
python -m quant.cli fundamental-show --symbol AAPL --latest
python -m quant.cli fundamental-coverage
python -m quant.cli fundamental-quality
python -m quant.cli data-refresh
python -m quant.cli data-coverage
python -m quant.cli research-readiness
python -m quant.cli export-for-agent --report reports/strategy_eval_YYYYMMDD_HHMMSS.json
python -m quant.cli visualize-report --report reports/trade_sim_YYYYMMDD_HHMMSS.json
```

See `docs/DATA_LAYER.md` and `docs/DATA_PROVIDERS.md` for universe, provider, metadata, coverage, quality, and readiness details.
See `docs/FUNDAMENTAL_DATA.md` for fundamental CSV import, query, coverage, and quality details.

## Agent Export

The agent export layer converts existing detailed JSON reports into compact text, Markdown, or JSON summaries for LLM and agent context windows.

Run:

```bash
python -m quant.cli export-for-agent --report reports/strategy_eval_YYYYMMDD_HHMMSS.json
python -m quant.cli export-for-agent --report reports/factor_backtest_YYYYMMDD_HHMMSS.json --format markdown
python -m quant.cli export-for-agent --report reports/portfolio_construction_YYYYMMDD_HHMMSS.json --format json
```

See `docs/AGENT_EXPORT.md` for details.

## Visualization Reports

Generate charts and a dashboard from existing JSON reports:

```bash
python -m quant.cli visualize-report --report reports/trade_sim_YYYYMMDD_HHMMSS.json
python -m quant.cli visualize-report --report reports/walk_forward_YYYYMMDD_HHMMSS.json
```

Charts are written to `reports/charts/` and are ignored by git. See `docs/VISUALIZATION.md`.

## Historical Trading Simulation

`trade-sim` runs an offline account-style historical simulation. It generates alpha targets on signal dates, constructs a portfolio, simulates next-day execution with costs, updates in-memory cash and positions, and marks the account to market through time.

```bash
python -m quant.cli trade-sim --strategy alpha --start 2024-01-01 --end 2025-01-01 --initial-cash 100000 --rebalance-frequency monthly --portfolio-method equal_weight
python -m quant.cli trade-sim --strategy alpha --start 2024-01-01 --end 2025-01-01 --initial-cash 100000 --rebalance-frequency monthly --portfolio-method risk_parity
```

Reports are written to `reports/trade_sim_YYYYMMDD_HHMMSS.json`. See `docs/TRADING_SIMULATION.md`.

## Simulated Portfolio Commands

```bash
python -m quant.cli init-account --cash 100000
python -m quant.cli buy SPY --qty 10 --price 500
python -m quant.cli sell SPY --qty 3 --price 510
python -m quant.cli portfolio
python -m quant.cli trades
```

## Portfolio Rebalance Engine

The rebalance engine reads the current simulated account, positions, and latest prices from SQLite. It calculates suggested trades only. It does not update positions, write trades, connect to brokers, or place orders.

Create a target file:

```json
{
  "SPY": 0.40,
  "QQQ": 0.30,
  "NVDA": 0.20,
  "cash": 0.10
}
```

Show current allocation:

```bash
python -m quant.cli allocation
```

Calculate a rebalance plan:

```bash
python -m quant.cli rebalance --targets examples/targets.json
```

Configure commission. The default is `0.001`, or 0.1%:

```bash
python -m quant.cli rebalance --targets examples/targets.json --commission 0.001
```

The rebalance report is written as:

```text
reports/rebalance_YYYYMMDD_HHMMSS.json
```

See `docs/REBALANCE.md` for details.

## Risk Engine

The risk engine reads the simulated portfolio and latest prices, then calculates:

- single-stock concentration
- industry concentration
- cash allocation
- Top 5 holdings concentration
- risk score from 0 to 100

Run:

```bash
python -m quant.cli risk
```

The risk report is written as:

```text
reports/risk_YYYYMMDD_HHMMSS.json
```

The Risk Engine is a pure calculation source for future OpenClaw Risk Agent work. It does not call OpenClaw or any AI model.

## Portfolio Optimizer

The optimizer generates target allocations that can be passed directly to the Rebalance Engine.

Supported modes:

- `equal_weight`
- `risk_adjusted`
- `constrained`

Default constraints:

- `max_position_weight`: `0.20`
- `min_cash_weight`: `0.10`
- `max_sector_weight`: `0.50`
- `only_long`: `true`

Run:

```bash
python -m quant.cli optimize
python -m quant.cli rebalance --targets examples/optimized_targets.json
python -m quant.cli rebalance --targets examples/optimized_targets.json --with-costs
```

The optimize command reads `examples/optimizer_config.json` by default and writes:

```text
examples/optimized_targets.json
reports/optimize_YYYYMMDD_HHMMSS.json
```

See `docs/OPTIMIZER.md` for details.

## Portfolio Construction

The portfolio construction engine generates target allocations from stored historical close prices.

Supported methods:

- `equal_weight`
- `inverse_volatility`
- `risk_parity`
- `min_variance`

Run:

```bash
python -m quant.cli portfolio-construct --method equal_weight --symbols SPY QQQ NVDA
python -m quant.cli portfolio-construct --method risk_parity --symbols SPY QQQ NVDA --output-targets examples/portfolio_constructed_targets.json
python -m quant.cli rebalance --targets examples/portfolio_constructed_targets.json --with-costs
```

Reports:

```text
reports/portfolio_construction_YYYYMMDD_HHMMSS.json
```

`examples/portfolio_constructed_targets.json` is a generated local smoke-test artifact and is ignored by git. Regenerate it with `--output-targets` when needed.

See `docs/PORTFOLIO_CONSTRUCTION.md` for details.

## Alpha Engine

The alpha engine reads stored historical prices, calculates simple factors, ranks symbols, and generates target weights compatible with the Rebalance Engine.

Alpha uses only rows at or before `as_of_date`. Generated targets are signal-date outputs and should be executed or backtested on the next trading day.

Supported factors:

- `momentum_20d`
- `momentum_60d`
- `volatility_20d`
- `risk_adjusted_momentum`

Run:

```bash
python -m quant.cli alpha
python -m quant.cli alpha --pipeline examples/factor_pipeline_config.json
python -m quant.cli alpha --output-targets examples/alpha_targets.json
python -m quant.cli rebalance --targets examples/alpha_targets.json --with-costs
```

Default config:

```text
examples/alpha_config.json
```

Reports:

```text
reports/alpha_YYYYMMDD_HHMMSS.json
```

See `docs/ALPHA.md` for details.

## Factor Pipeline

The factor pipeline preprocesses same-date cross-sectional factor values before Alpha Engine ranking or Factor Evaluation metrics.

Supported preprocessing:

- missing value handling
- winsorization
- z-score standardization
- rank normalization
- sector neutralization
- market/beta neutralization placeholder

Run:

```bash
python -m quant.cli factor-pipeline --factor momentum_20d
python -m quant.cli factor-eval --factor momentum_20d --pipeline examples/factor_pipeline_config.json
python -m quant.cli alpha --pipeline examples/factor_pipeline_config.json
```

Reports:

```text
reports/factor_pipeline_YYYYMMDD_HHMMSS.json
```

See `docs/FACTOR_PIPELINE.md` for details.

## Factor Evaluation Framework

The factor evaluation framework measures whether an alpha factor has useful cross-sectional predictive power.

It follows the same no-lookahead constraint as the Alpha Engine:

- factor values use only `signal_date` and earlier prices
- future returns use a later stored price row
- IC and Rank IC are calculated across symbols on each signal date

Supported factors:

- `momentum_20d`
- `momentum_60d`
- `volatility_20d`
- `risk_adjusted_momentum`

Run:

```bash
python -m quant.cli factor-eval --factor momentum_20d
python -m quant.cli factor-eval --factor momentum_20d --pipeline examples/factor_pipeline_config.json
python -m quant.cli factor-eval --factor risk_adjusted_momentum
python -m quant.cli factor-eval --factor momentum_60d --start 2024-01-01 --end 2024-12-31 --forward-days 20
```

Reports:

```text
reports/factor_eval_YYYYMMDD_HHMMSS.json
```

See `docs/FACTOR_EVALUATION.md` for details.

## Long-Short Factor Backtest

The long-short factor backtest checks whether one factor can produce a plausible equal-weight long-short return stream.

It is not Strategy Evaluation and not Performance Attribution. v0.14 adds that as a separate report-reading layer.

Run:

```bash
python -m quant.cli factor-backtest --factor momentum_20d
python -m quant.cli factor-backtest --factor momentum_20d --pipeline examples/factor_pipeline_config.json
```

Reports:

```text
reports/factor_backtest_YYYYMMDD_HHMMSS.json
```

See `docs/FACTOR_BACKTEST.md` for details.

## Strategy Evaluation

Strategy Evaluation explains return and risk from existing generated reports.

Run:

```bash
python -m quant.cli strategy-eval --factor-backtest-report reports/factor_backtest_YYYYMMDD_HHMMSS.json
python -m quant.cli strategy-eval --backtest-report reports/backtest_YYYYMMDD_HHMMSS.json
python -m quant.cli strategy-eval --strategy factor_long_short --factor momentum_20d
python -m quant.cli strategy-eval --strategy alpha --pipeline examples/factor_pipeline_config.json
```

Reports:

```text
reports/strategy_eval_YYYYMMDD_HHMMSS.json
```

See `docs/STRATEGY_EVALUATION.md` for details.

## Cost Engine

The cost engine estimates whether a rebalance is worth doing by calculating per-trade and total costs.

Supported models:

- `fixed`
- `linear`
- `combined`

Run:

```bash
python -m quant.cli cost
python -m quant.cli rebalance --targets examples/optimized_targets.json --with-costs
```

Default config:

```text
examples/cost_config.json
```

Reports:

```text
reports/cost_YYYYMMDD_HHMMSS.json
```

See `docs/COST.md` for details.

## Backtest Engine

The portfolio backtest engine reads historical prices from the existing `prices` table. It does not download data. Load price data first with `update-prices`.

It combines:

- Data Layer
- Portfolio State concepts
- Optimizer target generation
- Rebalance logic
- Cost Engine cost estimates

Example:

```bash
python -m quant.cli update-prices --symbols SPY --start 2023-01-01 --end 2024-12-31
python -m quant.cli backtest --start 2023-01-01 --end 2024-12-31 --initial-cash 100000 --mode equal_weight --rebalance-frequency monthly
```

Custom parameters:

```bash
python -m quant.cli backtest \
  --start 2023-01-01 \
  --end 2024-12-31 \
  --initial-cash 100000 \
  --mode risk_adjusted \
  --rebalance-frequency weekly
```

The CLI prints a concise summary and writes a JSON report like:

```text
reports/backtest_YYYYMMDD_HHMMSS.json
```

Legacy SMA single-symbol backtests are still available with `--symbol`.

See `docs/BACKTEST.md` for details.

## Execution Simulator

The execution simulator takes target allocation JSON, asks the Rebalance Engine for intended trades, then simulates fills and costs. It does not update the persistent simulated account or connect to a broker.

Run:

```bash
python -m quant.cli execute-sim --targets examples/optimized_targets.json
python -m quant.cli execute-sim --targets examples/optimized_targets.json --mode next_day_open --date 2024-01-02
python -m quant.cli execute-sim --targets examples/optimized_targets.json --mode twap --twap-slices 4
python -m quant.cli execute-sim --targets examples/optimized_targets.json --mode partial_fill --fill-ratio 0.5
```

Reports:

```text
reports/execution_YYYYMMDD_HHMMSS.json
```

See `docs/EXECUTION.md` for details.

The database path defaults to `data/quant.db`. You can override it with either:

```bash
python -m quant.cli --db-path /tmp/openclaw-quant.db portfolio
```

or:

```bash
export OPENCLAW_QUANT_DB_PATH=/tmp/openclaw-quant.db
```

## SQLite Tables

- `prices`: daily OHLCV data from the configured provider, defaulting to yfinance
- `symbol_metadata`: static symbol metadata for universe and sector workflows
- `income_statement`, `balance_sheet`, `cash_flow`, `fundamental_metrics`: imported fundamental data
- `fundamental_import_log`: import summaries
- `accounts`: simulated account cash and initial cash
- `positions`: current simulated positions
- `trades`: simulated trade ledger
- `reports/backtest_*.json`: generated backtest reports, ignored by git
- `reports/rebalance_*.json`: generated rebalance reports, ignored by git
- `reports/risk_*.json`: generated risk reports, ignored by git
- `reports/alpha_*.json`: generated alpha reports, ignored by git
- `reports/factor_pipeline_*.json`: generated factor pipeline reports, ignored by git
- `reports/factor_eval_*.json`: generated factor evaluation reports, ignored by git
- `reports/factor_backtest_*.json`: generated long-short factor backtest reports, ignored by git
- `reports/strategy_eval_*.json`: generated strategy evaluation reports, ignored by git
- `reports/optimize_*.json`: generated optimizer reports, ignored by git
- `reports/portfolio_construction_*.json`: generated portfolio construction reports, ignored by git
- `reports/data_quality_*.json`: generated data quality reports, ignored by git
- `reports/data_coverage_*.json`: generated data coverage reports, ignored by git
- `reports/research_readiness_*.json`: generated research readiness reports, ignored by git
- `reports/agent_summary.*`: optional local agent export output, ignored by git when generated under `reports/`
- `reports/cost_*.json`: generated cost reports, ignored by git
- `reports/execution_*.json`: generated execution simulation reports, ignored by git

## Roadmap

Near-term work:

- Add richer portfolio reporting.
- Add richer universe curation and metadata maintenance workflows.
- Add realized PnL tracking.
- Add basic performance metrics.
- Add more backtest strategies and benchmark comparisons.
- Add risk checks for max position size, cash usage, symbol allowlists, and rebalance suggestions.
- Add configurable sector maps and risk thresholds.
- Add optimizer modes that use return estimates and risk budgets.
- Add richer portfolio construction methods and configurable risk budgets.
- Add more alpha factors and signal combination rules.
- Add richer factor evaluation diagnostics and benchmark comparisons.
- Add richer neutralization methods and factor pipeline audit views.
- Add execution report and portfolio report adapters for Strategy Evaluation.
- Add richer execution assumptions and market calendar support.

Out of scope until explicitly designed:

- Broker integration.
- Live trading.
- Automated order execution.
- AI decision execution.

See `docs/ROADMAP.md` for the longer roadmap.

## For AI Developers

Start with `docs/AI_DEVELOPMENT.md` before changing code. It links the stable project context, architecture, schema, CLI behavior, and design decisions.

Important docs:

- `docs/AI_DEVELOPMENT.md`
- `docs/ARCHITECTURE.md`
- `docs/ROADMAP.md`
- `docs/DATA_SCHEMA.md`
- `docs/DATA_LAYER.md`
- `docs/AGENT_EXPORT.md`
- `docs/REBALANCE.md`
- `docs/RISK.md`
- `docs/ALPHA.md`
- `docs/FACTOR_PIPELINE.md`
- `docs/FACTOR_EVALUATION.md`
- `docs/FACTOR_BACKTEST.md`
- `docs/STRATEGY_EVALUATION.md`
- `docs/OPTIMIZER.md`
- `docs/PORTFOLIO_CONSTRUCTION.md`
- `docs/COST.md`
- `docs/EXECUTION.md`
- `docs/CLI.md`
- `docs/CLI_COMMANDS.md`
- `docs/DECISIONS.md`

AI assistants should keep tests updated, avoid broker/live-trading code unless explicitly requested, and preserve existing CLI behavior unless the README and tests are updated together.

New features must include CLI coverage and pytest coverage before they are considered complete.

## Test

```bash
pytest
```

The core tests use temporary SQLite databases and a fake market data source, so they do not need network access.

## v0.20.0 Walk Forward Validation

v0.20.0 adds walk-forward and rolling validation for `alpha` and `factor_long_short` strategies. It is a validation layer only: no new factors, no ML, no broker integration, and no live trading.

```bash
python -m quant.cli walk-forward --strategy alpha
python -m quant.cli walk-forward --strategy factor_long_short --factor momentum_20d
```

Reports are written to `reports/walk_forward_YYYYMMDD_HHMMSS.json` and include folds, train/test metrics, rolling validation, factor stability ranking, warnings, and recommendations.

## v0.19.0 Factor Expansion

v0.19.0 adds a deterministic price-history factor library under `quant/factors/` plus the `factor-list` CLI command. New supported factors include `value_score`, `quality_score`, `growth_score`, `reversal_5d`, `reversal_20d`, and `low_volatility_score` alongside the original momentum and volatility factors.

```bash
python -m quant.cli factor-list
python -m quant.cli factor-eval --factor quality_score
python -m quant.cli factor-backtest --factor reversal_20d
python -m quant.cli alpha
```

`examples/alpha_config.json` supports `factor_weights` for composite alpha scoring. Alpha reports include `factor_values`, `factor_contributions`, and `composite_alpha_score`. This remains offline research infrastructure: no machine learning, no news sentiment, no broker integration, and no live execution.
