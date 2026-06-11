# CLI

This file is the concise CLI index. See `docs/CLI_COMMANDS.md` for fuller examples.

```bash
python -m quant.cli update-prices
python -m quant.cli show-prices SPY --limit 5
python -m quant.cli list-symbols
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
python -m quant.cli optimize
python -m quant.cli cost
python -m quant.cli rebalance --targets examples/optimized_targets.json --with-costs
python -m quant.cli execute-sim --targets examples/optimized_targets.json
python -m quant.cli backtest --strategy alpha --start 2024-01-01 --end 2025-01-01 --initial-cash 100000 --rebalance-frequency monthly --alpha-config examples/alpha_config.json --execution-price close
python -m quant.cli backtest --start 2023-01-01 --end 2024-12-31 --initial-cash 100000 --mode equal_weight --rebalance-frequency monthly
```
