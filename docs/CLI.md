# CLI

This file is the concise CLI index. See `docs/CLI_COMMANDS.md` for fuller examples.

The public entry point remains `python -m quant.cli`. In `v0.15.0`, command parser registration and command execution were split into `quant/cli_commands/` modules without changing command names, arguments, output text, or report schemas.

```bash
python -m quant.cli update-prices
python -m quant.cli show-prices SPY --limit 5
python -m quant.cli list-symbols
python -m quant.cli universe-list
python -m quant.cli universe-build --sector Technology --max-symbols 10
python -m quant.cli data-refresh
python -m quant.cli data-coverage
python -m quant.cli research-readiness
python -m quant.cli export-for-agent --report reports/strategy_eval_YYYYMMDD_HHMMSS.json
python -m quant.cli export-for-agent --report reports/factor_backtest_YYYYMMDD_HHMMSS.json --format markdown
python -m quant.cli export-for-agent --report reports/portfolio_construction_YYYYMMDD_HHMMSS.json --format json
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
python -m quant.cli factor-eval --factor momentum_20d --pipeline examples/factor_pipeline_config.json
python -m quant.cli factor-backtest --factor momentum_20d
python -m quant.cli factor-backtest --factor momentum_20d --pipeline examples/factor_pipeline_config.json
python -m quant.cli strategy-eval --factor-backtest-report reports/factor_backtest_YYYYMMDD_HHMMSS.json
python -m quant.cli strategy-eval --strategy factor_long_short --factor momentum_20d
python -m quant.cli strategy-eval --strategy alpha --pipeline examples/factor_pipeline_config.json
python -m quant.cli optimize
python -m quant.cli portfolio-construct --method risk_parity --symbols SPY QQQ NVDA --output-targets examples/portfolio_constructed_targets.json
python -m quant.cli cost
python -m quant.cli rebalance --targets examples/optimized_targets.json --with-costs
python -m quant.cli execute-sim --targets examples/optimized_targets.json
python -m quant.cli backtest --strategy alpha --start 2024-01-01 --end 2025-01-01 --initial-cash 100000 --rebalance-frequency monthly --alpha-config examples/alpha_config.json --execution-price close
python -m quant.cli backtest --start 2023-01-01 --end 2024-12-31 --initial-cash 100000 --mode equal_weight --rebalance-frequency monthly
```

## Factor Library

```bash
python -m quant.cli factor-list
python -m quant.cli factor-eval --factor quality_score
python -m quant.cli factor-backtest --factor reversal_20d
python -m quant.cli alpha
```

`factor-list` prints registered factor names, categories, descriptions, required inputs, and lookback windows. Registered factors work with factor evaluation, factor pipeline, factor backtest, and composite alpha generation.
