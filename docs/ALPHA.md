# Alpha Engine

The Alpha Engine is the signal layer. It reads stored historical prices, calculates simple factors, ranks symbols, and generates target portfolio weights.

It does not download data, place trades, call AI models, or update portfolio state.

## Factors

The current factor set is:

- `momentum_20d`: latest close divided by close 20 trading rows ago minus 1.
- `momentum_60d`: latest close divided by close 60 trading rows ago minus 1.
- `volatility_20d`: standard deviation of the latest 20 daily returns.
- `risk_adjusted_momentum`: `momentum_60d / volatility_20d`.

Symbols are ranked by `risk_adjusted_momentum`, highest first.

## Signal Date And Execution Date

Alpha is calculated with an inclusive `as_of_date` cutoff. The engine only reads price rows where `date <= as_of_date`. When `as_of_date` is `null`, the latest stored date available for each symbol is used.

Alpha-generated targets are signals for the next tradable session. Rebalance planning may inspect the target file immediately, but execution and backtest fills should default to the next trading day after the signal date. The alpha report includes `suggested_execution_date` when a next stored price row is available. The v0.10 alpha backtest path follows this rule and records both `signal_date` and `execution_date` for every trade.

This avoids lookahead bias: prices after the signal date are not used to rank symbols or size target weights.

## Config

Default config:

```text
examples/alpha_config.json
```

Fields:

- `universe`: symbols to evaluate.
- `as_of_date`: optional inclusive date cutoff, or `null` for latest stored data.
- `lookback_short`: default `20`.
- `lookback_long`: default `60`.
- `top_n`: number of ranked symbols to select.
- `weighting_mode`: `equal_weight` or `score_weighted`.
- `min_cash_weight`: cash reserve in the generated target weights.
- `max_position_weight`: maximum target weight for one non-cash symbol.

## Exclusions

Symbols are excluded when:

- no stored price data exists at or before `as_of_date`
- there are not enough closes for `lookback_long`
- `volatility_20d` is unavailable
- `volatility_20d` is zero

Zero-volatility symbols are excluded instead of receiving an infinite or unstable `risk_adjusted_momentum` score. The report includes `excluded_symbols` and `exclusion_reasons`.

## Target Constraints

Generated target weights are validated before they are written:

- total weight sums to `1.0`
- `cash >= min_cash_weight`
- every non-cash symbol is `<= max_position_weight`
- the file shape is compatible with `rebalance --targets`

## Commands

```bash
python -m quant.cli alpha
python -m quant.cli alpha --pipeline examples/factor_pipeline_config.json
python -m quant.cli alpha --output-targets examples/alpha_targets.json
python -m quant.cli rebalance --targets examples/alpha_targets.json --with-costs
```

## Output

The CLI prints:

- per-symbol factor values
- `as_of_date`
- `data_start_date`
- `data_end_date`
- `lookback_used`
- rank
- excluded symbols and reasons
- selected symbols
- target weights
- optional factor pipeline report path

Reports are written as:

```text
reports/alpha_YYYYMMDD_HHMMSS.json
```

Generated target files are compatible with:

```bash
python -m quant.cli rebalance --targets <file>
```

## Boundary

The Alpha Engine creates research signals and target weights only. The Rebalance Engine turns target weights into suggested trades. Cost Engine, Execution Simulator, and Backtest Engine consume downstream trade or simulation outputs.

Use `docs/FACTOR_PIPELINE.md` and `python -m quant.cli alpha --pipeline examples/factor_pipeline_config.json` to clean or neutralize same-date factor scores before ranking.

Use `docs/FACTOR_EVALUATION.md` and `python -m quant.cli factor-eval` to evaluate factor predictive quality before promoting a factor into target generation rules.

## Composite Alpha Factors

v0.19 adds optional `factor_weights` support. When configured, Alpha normalizes positive weights, rank-normalizes each same-date factor cross-section, computes per-factor `factor_contributions`, and ranks symbols by `composite_alpha_score`.

Missing values receive zero contribution for that factor. Symbols with no valid composite inputs are excluded with a clear reason. The no-lookahead rule is unchanged: all factor values are computed from `as_of_date` and earlier rows, and generated targets should be executed or backtested on the next available trading day.

Factor direction comes from the central registry. Most score factors are `higher_is_better=true`; raw `volatility_20d` is `higher_is_better=false` because it is a risk measure, while `low_volatility_score` flips that into a preference score. Reversal factors use negative recent momentum, so a higher `reversal_20d` means the symbol recently underperformed more and has a stronger mean-reversion score.

The current `value_score`, `quality_score`, and `growth_score` are price-only proxies. They are placeholders for future fundamental-data-aware factors and should not be interpreted as true valuation, accounting quality, or fundamental growth measures.
