# Regime Detection

`v0.32.0` adds deterministic market regime detection and regime-aware factor diagnostics.

This is market-state awareness for offline research. It does not add machine learning, news sentiment, broker integration, live trading, or automatic factor disabling.

## Regimes

Supported regime labels:

- `BULL`
- `BEAR`
- `HIGH_VOL`
- `LOW_VOL`
- `TRENDING`
- `RANGE_BOUND`
- `CRISIS`
- `RECOVERY`
- `UNKNOWN`

The initial implementation assigns one primary regime per date. Crisis and high-volatility states take precedence over simple bull/bear labels when thresholds are triggered.

These regimes are heuristic classifications of historical market state. They are not market forecasts, not timing signals, and not investment advice.

## Detection Rules

The detector uses stored daily benchmark prices, defaulting to `SPY`.

Inputs are calculated with data available on or before each date:

- long moving average
- realized volatility
- trend strength
- drawdown from prior peak
- daily market return

There is no ML model, no external sentiment input, and no forward-looking label leakage.

The detector calculates every row from benchmark prices available at or before that row's date. Future returns, future drawdowns, future volatility, and future market states are not used to label earlier dates.

## CLI

```bash
python -m quant.cli detect-regime
python -m quant.cli regime-history
python -m quant.cli regime-report
python -m quant.cli regime-rank
```

Factor commands can optionally persist regime diagnostics:

```bash
python -m quant.cli factor-eval --factor momentum_20d --save-regime-history
python -m quant.cli factor-backtest --factor momentum_20d --save-regime-history
```

If regime history is empty, the save path detects and persists benchmark regimes first.

## Storage

`regime_history` stores:

- `date`
- `regime`
- `volatility`
- `trend_strength`
- `drawdown`
- `market_return`
- `confidence`

`factor_regime_history` stores factor diagnostics by regime:

- `factor_name`
- `regime`
- `ic`
- `rank_ic`
- `icir`
- `coverage`
- `stability`
- `evaluation_date`

`regime_history` is idempotent by `date`. `factor_regime_history` is append-only by evaluation run, preserving an audit trail of repeated research evaluations.

Low sample counts emit `WARN_LOW_REGIME_SAMPLE`. Low-sample regimes reduce ranking support and confidence because a factor can appear strong in a regime with too few observations.

## Reports

Generated reports:

- `reports/regime_detection_YYYYMMDD_HHMMSS.json`
- `reports/regime_history_YYYYMMDD_HHMMSS.json`
- `reports/regime_report_YYYYMMDD_HHMMSS.json`
- `reports/regime_rank_YYYYMMDD_HHMMSS.json`

Reports are generated artifacts and are ignored by git.

## Factor Analytics

Regime analytics groups saved factor observations by the regime active on each `signal_date`.

For factor evaluation, it calculates IC, RankIC, ICIR, coverage, and stability by regime.

For factor backtests, it stores long-short spread-return diagnostics by regime as research analytics. This is not a cash-account tradable equity curve and does not change factor backtest semantics.

## Agent Export And Visualization

Agent Export supports regime reports and summarizes:

- current regime
- regime counts
- strongest and weakest factors by regime
- stability across regimes
- diagnostics and recommended follow-up checks

Visualization supports:

- regime timeline
- regime transition/frequency charts
- factor performance by regime
- regime confidence chart
- regime ranking charts

## Boundary

Regime Detection is diagnostic only. It does not disable factors, change alpha weights automatically, modify portfolio targets, place trades, or provide investment advice.
## Scheduler Integration

`research-run` can call regime detection as one step in the daily offline research pipeline. The generated scheduler summary includes the current regime and any low-sample regime warnings. This remains diagnostic only and does not automatically disable factors, alter target weights, or time the market.
