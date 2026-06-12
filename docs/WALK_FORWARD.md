# Walk Forward Validation

v0.20.0 adds an offline walk-forward and rolling validation layer. It validates whether factors, composite alpha, and portfolio construction behavior remain useful out-of-sample. It does not add factors, train machine-learning models, connect to brokers, or execute live trades.

## CLI

```bash
python -m quant.cli walk-forward --strategy alpha
python -m quant.cli walk-forward --strategy alpha --save-factor-history
python -m quant.cli walk-forward --strategy alpha --train-years 3 --test-years 1
python -m quant.cli walk-forward --strategy factor_long_short --factor momentum_20d
```

The CLI defaults to the latest 5 folds to keep interactive runs fast on large local histories. Use `--max-folds 0` to run every generated fold.

Fundamental-factor composite alpha can increase walk-forward runtime because each signal date may need report-date-aware fundamental lookups in addition to price history. Validation smoke checks can use `--max-folds 1` or `--max-folds 2`; full validation can still use the default or `--max-folds 0`.

`v0.37.0` Strategy Evaluation Gates may inspect saved walk-forward history to warn about low fold count, weak test Sharpe, or train/test gaps. The gates do not rerun or alter walk-forward semantics.

Optional parameters:

- `--train-years`
- `--test-years`
- `--start`
- `--end`
- `--symbols`
- `--initial-cash`
- `--rebalance-frequency`
- `--alpha-config`
- `--pipeline`
- `--max-folds`
- `--save-factor-history`

## Window Logic

The engine generates rolling train/test windows:

```text
Train: 2018-2020
Test:  2021

Train: 2019-2021
Test:  2022
```

Each fold records train and test returns, Sharpe, max drawdown, turnover, cost, IC, Rank IC, and ICIR where available.

## Supported Strategies

`alpha` uses the existing no-lookahead Alpha Strategy path in `PortfolioBacktestEngine`.

`factor_long_short` uses existing `FactorBacktest` and `FactorEvaluation` logic. It does not change factor semantics or factor backtest portfolio construction.

## Diagnostics

Warnings include:

- `WARN_OVERFIT`: strong train Sharpe but weak test Sharpe.
- `WARN_FACTOR_DECAY`: test IC collapses near zero.
- `WARN_REGIME_DEPENDENT`: train return is positive but test return is negative.
- `WARN_NO_LOOKAHEAD_NOT_CONFIRMED`: a fold report was not marked no-lookahead.
- `WARN_COMPOUNDED_RETURN_WEAK_SHARPE`: compounded return is high but arithmetic-period Sharpe is weak, usually because the return path is unstable.
- `WARN_SPREAD_RETURN_WIPEOUT`: a factor long-short research spread compounds to about `-100%`.

High compounded return and weak Sharpe can occur together. The return field compounds the fold return stream, while Sharpe uses arithmetic average period returns divided by period volatility. A few large positive periods can lift compounded return even when most periods are noisy, volatile, or path dependent.

For `factor_long_short`, returns are research spread returns. They may use overlapping forward-return windows and equal-weight long/short legs. They are useful for factor research, but they are not a cash-account tradable equity curve and can imply leveraged spread losses below `-100%` for a period. Treat such reports as diagnostics, not execution instructions.

`alpha` walk-forward uses the existing no-lookahead portfolio backtest path: signals are generated on `signal_date` with signal-date-and-earlier data, then executed on the next available trading day.

The v0.27 multi-factor model can be used by `alpha` inside walk-forward runs. Stability-weighted alpha may use configured stability priors and coverage-aware confidence, but walk-forward validation itself still uses the existing no-lookahead signal/execution path.

Full alpha walk-forward validation keeps the existing default fold behavior. Multi-factor alpha with fundamental factors can be more expensive than price-only alpha, so smoke checks may pass `--max-folds 1` or `--max-folds 2` explicitly without changing defaults.

`--save-factor-history` stores fold-level train/test metrics and warnings in the Factor Store. It does not change fold generation, signal dates, execution dates, or return calculations.

Regime Detection in `v0.32.0` can be used after walk-forward runs to inspect whether factor behavior differs by persisted market regime. It does not change walk-forward fold boundaries, train/test separation, or no-lookahead guarantees.

Regime labels are heuristic diagnostics, not forecasts. They should be used to review robustness, not to time markets automatically.

## Factor Stability

The report evaluates registered factors across folds and classifies them as `stable`, `moderate`, `unstable`, or `insufficient_data`.

## Report

Reports are written to:

```text
reports/walk_forward_YYYYMMDD_HHMMSS.json
```

Top-level schema:

- `metadata`
- `strategy`
- `parameters`
- `folds`
- `summary`
- `rolling_validation`
- `stability_analysis`
- `warnings`
- `recommendations`

## No-Lookahead

Walk-forward validation preserves existing no-lookahead guarantees. Signal generation uses only train or signal-date-and-earlier data. Future returns are labels for out-of-sample validation only.
