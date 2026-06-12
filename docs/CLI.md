# CLI

This file is the concise CLI index. See `docs/CLI_COMMANDS.md` for fuller examples.

The public entry point remains `python -m quant.cli`. In `v0.15.0`, command parser registration and command execution were split into `quant/cli_commands/` modules without changing command names, arguments, output text, or report schemas.

`v0.28.0` also exposes the installed console script `openclaw-quant` when the project is installed from `pyproject.toml`. Existing `python -m quant.cli` usage remains the canonical documented path.

```bash
python -m quant.cli update-prices
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
python -m quant.cli export-for-agent --report reports/factor_backtest_YYYYMMDD_HHMMSS.json --format markdown
python -m quant.cli export-for-agent --report reports/portfolio_construction_YYYYMMDD_HHMMSS.json --format json
python -m quant.cli mcp-list-tools
python -m quant.cli mcp-tool-info detect_regime
python -m quant.cli mcp-smoke
python -m quant.cli init-account --cash 100000
python -m quant.cli buy SPY --qty 10 --price 500
python -m quant.cli sell SPY --qty 3 --price 510
python -m quant.cli portfolio
python -m quant.cli trades
python -m quant.cli allocation
python -m quant.cli rebalance --targets examples/targets.json
python -m quant.cli risk
python -m quant.cli alpha
python -m quant.cli alpha --pipeline examples/factor_pipeline_config.json
python -m quant.cli factor-pipeline --factor momentum_20d
python -m quant.cli factor-eval --factor momentum_20d
python -m quant.cli factor-eval --factor momentum_20d --save-factor-history
python -m quant.cli factor-eval --factor momentum_20d --pipeline examples/factor_pipeline_config.json
python -m quant.cli factor-backtest --factor momentum_20d
python -m quant.cli factor-backtest --factor momentum_20d --save-factor-history
python -m quant.cli factor-backtest --factor momentum_20d --pipeline examples/factor_pipeline_config.json
python -m quant.cli factor-store-summary
python -m quant.cli factor-history --factor momentum_20d
python -m quant.cli factor-rank
python -m quant.cli detect-regime
python -m quant.cli regime-history
python -m quant.cli regime-report
python -m quant.cli regime-rank
python -m quant.cli strategy-eval --factor-backtest-report reports/factor_backtest_YYYYMMDD_HHMMSS.json
python -m quant.cli strategy-eval --strategy factor_long_short --factor momentum_20d
python -m quant.cli strategy-eval --strategy alpha --pipeline examples/factor_pipeline_config.json
python -m quant.cli optimize
python -m quant.cli portfolio-construct --method risk_parity --symbols SPY QQQ NVDA --output-targets examples/portfolio_constructed_targets.json
python -m quant.cli cost
python -m quant.cli rebalance --targets examples/optimized_targets.json --with-costs
python -m quant.cli execute-sim --targets examples/optimized_targets.json
python -m quant.cli trade-sim --strategy alpha --portfolio-method equal_weight --market-realism-config examples/market_realism_config.json
python -m quant.cli backtest --strategy alpha --start 2024-01-01 --end 2025-01-01 --initial-cash 100000 --rebalance-frequency monthly --alpha-config examples/alpha_config.json --execution-price close
python -m quant.cli backtest --start 2023-01-01 --end 2024-12-31 --initial-cash 100000 --mode equal_weight --rebalance-frequency monthly
```

## Factor Library

```bash
python -m quant.cli factor-list
python -m quant.cli factor-eval --factor quality_score
python -m quant.cli factor-backtest --factor reversal_20d
python -m quant.cli factor-eval --factor fundamental_quality_score
python -m quant.cli factor-backtest --factor fundamental_value_score
python -m quant.cli factor-store-summary
python -m quant.cli factor-history --factor momentum_20d
python -m quant.cli factor-rank
python -m quant.cli alpha
```

`factor-list` prints registered factor names, categories, descriptions, required inputs, no-lookahead metadata, `fundamental_data_required`, and lookback windows. Registered factors work with factor evaluation, factor pipeline, factor backtest, and composite alpha generation. Fundamental factors use `report_date <= signal_date` and include coverage fields in factor reports.

`factor-eval`, `factor-backtest`, and `walk-forward` can persist reusable research history with `--save-factor-history`. The Factor Store commands read that SQLite history and write generated summary reports under `reports/`.

## Regime Detection

```bash
python -m quant.cli detect-regime
python -m quant.cli regime-history
python -m quant.cli regime-report
python -m quant.cli regime-rank
python -m quant.cli factor-eval --factor momentum_20d --save-regime-history
```

Regime commands classify market states from stored daily benchmark prices, defaulting to SPY. The output is diagnostic only; it does not change factor weights, portfolio targets, or trading simulation behavior.

`alpha` supports the v0.27 formal multi-factor model through `examples/alpha_config.json`. Multi-factor reports are written to `reports/multi_factor_*.json` and include coverage, confidence, stability, factor contributions, and family contributions.

## Walk Forward

```bash
python -m quant.cli walk-forward --strategy alpha
python -m quant.cli walk-forward --strategy alpha --save-factor-history
python -m quant.cli walk-forward --strategy factor_long_short --factor momentum_20d
python -m quant.cli trade-sim --strategy alpha --start 2024-01-01 --end 2025-01-01 --initial-cash 100000 --rebalance-frequency monthly --portfolio-method equal_weight
python -m quant.cli trade-sim --strategy alpha --start 2024-01-01 --end 2025-01-01 --initial-cash 100000 --rebalance-frequency monthly --portfolio-method risk_parity
```

Use `--train-years`, `--test-years`, `--start`, `--end`, `--symbols`, and `--max-folds` to control fold generation. `--max-folds 0` runs all generated folds.

## Trading Simulation

```bash
python -m quant.cli trade-sim --strategy alpha --start 2024-01-01 --end 2025-01-01 --initial-cash 100000 --rebalance-frequency monthly --portfolio-method equal_weight
python -m quant.cli trade-sim --strategy alpha --portfolio-method risk_parity --market-realism-config examples/market_realism_config.json
```

`trade-sim` is an offline historical account simulation. It records signal dates and next execution dates, updates in-memory cash and positions, applies deterministic market realism constraints when configured, and writes `reports/trade_sim_*.json`.

If `--start` and `--end` are omitted, `trade-sim` uses the default smoke window `2024-01-01` to `2025-01-01`.

## Visualization

```bash
python -m quant.cli visualize-report --report reports/trade_sim_YYYYMMDD_HHMMSS.json
python -m quant.cli visualize-report --report reports/walk_forward_YYYYMMDD_HHMMSS.json
```

`visualize-report` reads existing JSON reports and writes PNG, SVG, and HTML dashboard files under `reports/charts/`.

## Daily Research Scheduler

```bash
python -m quant.cli research-run
python -m quant.cli research-status
python -m quant.cli research-history
python -m quant.cli research-report
```

`research-run` executes the offline daily research pipeline from `examples/research_scheduler_config.json`: coverage checks, factor evaluation, Factor Store update, regime detection, historical trade simulation, visualization, Agent Export, and a compact summary. The default config is lightweight daily/smoke mode, not full-universe validation. Full research remains available by enabling data refresh, expanding symbols, adding factors, and extending the trade simulation window in config. Steps are failure-isolated where possible. This is research automation only; it does not connect to brokers, place orders, or perform live trading.

## Strategy DSL

```bash
python -m quant.cli strategy-list
python -m quant.cli strategy-show --strategy momentum_fundamental
python -m quant.cli strategy-validate --file strategies/momentum_fundamental.yaml
python -m quant.cli strategy-run --strategy momentum_fundamental
```

Strategy DSL commands load YAML/JSON definitions, validate gates, and optionally run existing offline trade simulation. They do not change quant calculations, report schemas, no-lookahead rules, or broker/live trading boundaries.

## Optional Dependencies

Provider commands are safe to run when optional provider packages are missing. If `yfinance` is not installed, `provider-list`, `provider-health`, `provider-info yfinance`, `factor-list`, and `--help` commands still start; the yfinance provider reports `NOT_INSTALLED` until the core extra or `requirements.txt` dependencies are installed.
