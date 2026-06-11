# CLI Commands

Run commands from the project root:

```bash
python -m quant.cli <command>
```

`v0.15.0` is an internal CLI refactor. The public commands below are intentionally unchanged while implementation lives in smaller `quant/cli_commands/` modules.

Use a custom database path:

```bash
python -m quant.cli --db-path /tmp/openclaw-quant.db <command>
```

## Market Data

```bash
python -m quant.cli update-prices
python -m quant.cli update-prices --symbols SPY QQQ AAPL
python -m quant.cli show-prices SPY --limit 5
python -m quant.cli list-symbols
python -m quant.cli universe-list
python -m quant.cli universe-build --sector Technology --max-symbols 10
python -m quant.cli data-refresh
python -m quant.cli data-coverage
python -m quant.cli research-readiness
python -m quant.cli export-for-agent --report reports/strategy_eval_YYYYMMDD_HHMMSS.json
```

## Data Layer

```bash
python -m quant.cli universe-list
python -m quant.cli universe-build
python -m quant.cli universe-build --symbols SPY,QQQ,NVDA
python -m quant.cli universe-build --sector Technology --max-symbols 10
python -m quant.cli data-refresh --universe etf_universe --start-date 2024-01-01
python -m quant.cli data-coverage
python -m quant.cli research-readiness
```

The data layer commands manage research universes, static metadata, stored-price coverage, data quality, and readiness diagnostics. They use the existing Yahoo Finance / `yfinance` daily data path. They do not provide real-time market data, AkShare, Tushare, A-share data, factor evaluation semantic changes, backtest semantic changes, portfolio state changes, or execution behavior.

## Agent Export

```bash
python -m quant.cli export-for-agent --report reports/strategy_eval_YYYYMMDD_HHMMSS.json
python -m quant.cli export-for-agent --report reports/factor_backtest_YYYYMMDD_HHMMSS.json --format markdown
python -m quant.cli export-for-agent --report reports/portfolio_construction_YYYYMMDD_HHMMSS.json --format json
python -m quant.cli export-for-agent --report reports/strategy_eval_YYYYMMDD_HHMMSS.json --max-tokens 500 --output reports/agent_summary.md
```

The export-for-agent command reads an existing JSON report, auto-detects its report type from schema keys, and emits a compact text, Markdown, or JSON summary. It does not modify the source report, quant logic, factor evaluation logic, backtest logic, portfolio state, or execution behavior.

## Simulated Portfolio

```bash
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
python -m quant.cli factor-backtest --factor momentum_20d
python -m quant.cli strategy-eval --factor-backtest-report reports/factor_backtest_YYYYMMDD_HHMMSS.json
python -m quant.cli strategy-eval --strategy factor_long_short --factor momentum_20d
python -m quant.cli optimize
python -m quant.cli portfolio-construct --method risk_parity --symbols SPY QQQ NVDA
python -m quant.cli cost
python -m quant.cli execute-sim --targets examples/optimized_targets.json
```

## Rebalance

Target files are JSON objects whose values sum to `1.0`:

```json
{
  "SPY": 0.4,
  "QQQ": 0.3,
  "NVDA": 0.2,
  "cash": 0.1
}
```

Commands:

```bash
python -m quant.cli allocation
python -m quant.cli rebalance --targets examples/targets.json
python -m quant.cli rebalance --targets examples/targets.json --commission 0.001
```

The rebalance command calculates suggested trades and writes a JSON report. It does not modify the simulated account.

## Risk

```bash
python -m quant.cli risk
```

The risk command calculates concentration, cash exposure, Top 5 holdings concentration, industry concentration, and a 0-100 risk score. It writes a JSON report and does not modify the simulated account.

## Alpha

```bash
python -m quant.cli alpha
python -m quant.cli alpha --pipeline examples/factor_pipeline_config.json
python -m quant.cli alpha --output-targets examples/alpha_targets.json
python -m quant.cli rebalance --targets examples/alpha_targets.json --with-costs
```

The alpha command reads `examples/alpha_config.json` by default, calculates momentum, volatility, and risk-adjusted momentum factors, ranks symbols, selects Top N, and generates target weights. It writes a JSON report and does not modify the simulated account. Alpha uses only rows at or before `as_of_date`; generated targets should be executed or backtested on the next trading day.

When `--pipeline` is supplied, Alpha Engine uses cleaned pipeline scores for ranking and score-weighted target generation.

## Factor Pipeline

```bash
python -m quant.cli factor-pipeline --factor momentum_20d
python -m quant.cli factor-pipeline --factor risk_adjusted_momentum --config examples/factor_pipeline_config.json
```

The factor pipeline command reads stored prices up to `--as-of-date` when provided, calculates raw factor values, applies preprocessing, and writes `reports/factor_pipeline_*.json`.

## Factor Evaluation

```bash
python -m quant.cli factor-eval --factor momentum_20d
python -m quant.cli factor-eval --factor momentum_20d --pipeline examples/factor_pipeline_config.json
python -m quant.cli factor-eval --factor risk_adjusted_momentum
python -m quant.cli factor-eval --factor volatility_20d --start 2024-01-01 --end 2024-12-31 --forward-days 20
```

The factor evaluation command reads stored prices, calculates factor values using signal-date-and-earlier data, then compares them with future returns. It prints IC, Rank IC, ICIR, quintile returns, spread, and decay metrics, and writes `reports/factor_eval_*.json`.

## Long-Short Factor Backtest

```bash
python -m quant.cli factor-backtest --factor momentum_20d
python -m quant.cli factor-backtest --factor momentum_20d --pipeline examples/factor_pipeline_config.json
python -m quant.cli factor-backtest --factor risk_adjusted_momentum --start 2024-01-01 --end 2024-12-31 --holding-period 20 --quantiles 5
```

The factor-backtest command ranks each no-lookahead signal-date cross-section, longs the configured top quantile, shorts the configured bottom quantile, and prints long-short return metrics. It writes `reports/factor_backtest_*.json` and does not modify portfolio state.

This is not Strategy Evaluation or Performance Attribution. V1.4 adds those as a separate report-reading layer.

## Strategy Evaluation

```bash
python -m quant.cli strategy-eval --factor-backtest-report reports/factor_backtest_YYYYMMDD_HHMMSS.json
python -m quant.cli strategy-eval --backtest-report reports/backtest_YYYYMMDD_HHMMSS.json
python -m quant.cli strategy-eval --strategy factor_long_short --factor momentum_20d
python -m quant.cli strategy-eval --strategy factor_long_short --factor momentum_20d --pipeline examples/factor_pipeline_config.json
python -m quant.cli strategy-eval --strategy alpha --pipeline examples/factor_pipeline_config.json
python -m quant.cli strategy-eval --factor-backtest-report reports/factor_backtest_YYYYMMDD_HHMMSS.json --benchmark SPY
```

The strategy-eval command reads or generates a supported source report, then explains return, risk, attribution, robustness diagnostics, drawdown, rolling metrics, monthly performance, and yearly performance. It writes `reports/strategy_eval_*.json` and does not introduce new signals, modify portfolio state, or execute trades.

## Optimize

```bash
python -m quant.cli optimize
python -m quant.cli optimize --mode risk_adjusted
python -m quant.cli optimize --mode constrained --max-position-weight 0.15
python -m quant.cli rebalance --targets examples/optimized_targets.json
```

The optimize command reads `examples/optimizer_config.json` by default, writes `examples/optimized_targets.json`, and writes a JSON report. It does not modify the simulated account.

## Portfolio Construction

```bash
python -m quant.cli portfolio-construct --method equal_weight --symbols SPY QQQ NVDA
python -m quant.cli portfolio-construct --method inverse_volatility --symbols SPY QQQ NVDA --lookback 60
python -m quant.cli portfolio-construct --method risk_parity --symbols SPY QQQ NVDA --output-targets examples/portfolio_constructed_targets.json
python -m quant.cli portfolio-construct --method min_variance --symbols SPY QQQ NVDA --end 2025-01-01
python -m quant.cli rebalance --targets examples/portfolio_constructed_targets.json --with-costs
```

The portfolio-construct command reads stored close prices, constructs long-only target weights, prints volatility and risk contribution diagnostics, and writes `reports/portfolio_construction_*.json`. It does not modify the simulated account. `examples/portfolio_constructed_targets.json` is treated as a generated local artifact and is ignored by git.

## Cost

```bash
python -m quant.cli cost
python -m quant.cli cost --model fixed
python -m quant.cli cost --targets examples/optimized_targets.json --config examples/cost_config.json
python -m quant.cli rebalance --targets examples/optimized_targets.json --with-costs
```

The cost command estimates costs for current rebalance suggestions. It writes a JSON report and does not modify the simulated account.

## Execution Simulation

```bash
python -m quant.cli execute-sim --targets examples/optimized_targets.json
python -m quant.cli execute-sim --targets examples/optimized_targets.json --mode next_day_open --date 2024-01-02
python -m quant.cli execute-sim --targets examples/optimized_targets.json --mode twap --twap-slices 4
python -m quant.cli execute-sim --targets examples/optimized_targets.json --mode partial_fill --fill-ratio 0.5
```

The execution simulator turns rebalance suggestions into simulated fills, unfilled quantities, costs, final cash, and final positions. It writes a JSON report and does not modify the simulated account.

## Backtest

Backtests use existing rows in the `prices` table. Load prices first:

No-lookahead alpha strategy:

```bash
python -m quant.cli backtest \
  --strategy alpha \
  --start 2024-01-01 \
  --end 2025-01-01 \
  --initial-cash 100000 \
  --rebalance-frequency monthly \
  --alpha-config examples/alpha_config.json \
  --execution-price close
```

Simple portfolio smoke mode:

```bash
python -m quant.cli update-prices --symbols SPY --start 2023-01-01 --end 2024-12-31
python -m quant.cli backtest --start 2023-01-01 --end 2024-12-31 --initial-cash 100000 --mode equal_weight --rebalance-frequency monthly
```

Optional parameters:

```bash
python -m quant.cli backtest \
  --start 2023-01-01 \
  --end 2024-12-31 \
  --initial-cash 100000 \
  --mode risk_adjusted \
  --rebalance-frequency weekly
```

Legacy SMA single-symbol backtests remain available with `--symbol`.

The alpha strategy path records `signal_date` and `execution_date` and executes on the next available trading day. Simple portfolio modes use a same-day close assumption and are intended for smoke checks.

## Failure Behavior

- Buying without enough cash returns a non-zero exit code and prints `Error: insufficient cash`.
- Selling without enough position returns a non-zero exit code and prints `Error: insufficient position`.
- Portfolio commands require an initialized account.
- Backtest with no stored prices returns a non-zero exit code and a clear missing-data error.
- Universe build excludes symbols that do not have metadata.
- Data coverage and readiness commands can run with partial or missing price coverage and report recommendations.
- Backtest rejects `short_window >= long_window`.
- Rebalance rejects target weights that do not sum to `1.0`.
- Rebalance requires latest prices for target symbols and held symbols.
- Risk requires latest prices for held symbols.
- Alpha requires enough stored price history for at least one symbol in the universe.
- Factor pipeline requires stored price history for symbols whose raw factor values should be calculated.
- Factor evaluation requires enough stored price history and future-return windows for at least one symbol.
- Factor backtest requires enough stored price history and future-return windows for at least one long-short cross-section.
- Strategy evaluation requires a supported JSON report path or `--strategy alpha/factor_long_short`.
- Trading simulation requires enough stored price history before the first signal date and at least one next execution date.
- Optimize requires at least one symbol in the optimizer universe with stored price data.
- Portfolio construction requires at least one requested symbol with sufficient stored return history.
- Cost requires a target allocation that can produce rebalance suggestions.
- Execution simulation requires an initialized account, target allocation, and latest prices for target and held symbols.

## Factor Library

```bash
python -m quant.cli factor-list
python -m quant.cli factor-eval --factor quality_score
python -m quant.cli factor-backtest --factor reversal_20d
python -m quant.cli alpha
```

The factor library is registry-driven. `factor-list` shows each factor's category, type, required inputs, lookback window, and description. The Alpha Engine can combine registered factors using `factor_weights` in `examples/alpha_config.json`, producing `composite_alpha_score` and per-factor contributions in alpha reports.

## Walk Forward Validation

```bash
python -m quant.cli walk-forward --strategy alpha
python -m quant.cli walk-forward --strategy factor_long_short --factor momentum_20d
python -m quant.cli walk-forward --strategy factor_long_short --factor momentum_20d --train-years 3 --test-years 1 --max-folds 0
```

The command generates rolling train/test folds, computes out-of-sample metrics, factor stability rankings, and warnings such as `WARN_OVERFIT`, `WARN_FACTOR_DECAY`, and `WARN_REGIME_DEPENDENT`. It writes `reports/walk_forward_*.json` and does not modify portfolio state.

## Historical Trading Simulation

```bash
python -m quant.cli trade-sim --strategy alpha --start 2024-01-01 --end 2025-01-01 --initial-cash 100000 --rebalance-frequency monthly --portfolio-method equal_weight
python -m quant.cli trade-sim --strategy alpha --start 2024-01-01 --end 2025-01-01 --initial-cash 100000 --rebalance-frequency monthly --portfolio-method risk_parity
```

The command generates alpha signals on rebalance dates, constructs target weights, simulates next-trading-day execution with costs, updates an in-memory `PortfolioAccount`, and writes `reports/trade_sim_*.json`. It is offline research only and does not update persistent portfolio state or connect to brokers.
