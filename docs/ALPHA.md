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

Alpha-generated targets are signals for the next tradable session. Rebalance planning may inspect the target file immediately, but execution and backtest fills should default to the next trading day after the signal date. The alpha report includes `suggested_execution_date` when a next stored price row is available.

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
