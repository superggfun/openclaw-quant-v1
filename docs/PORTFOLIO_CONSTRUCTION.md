# Portfolio Construction

`v0.16.0` adds a portfolio construction layer for turning a symbol universe and historical price window into target allocation weights.

This module is offline research infrastructure. It does not place trades, update portfolio state, connect to brokers, run high-frequency execution logic, or call AI systems.

## CLI

```bash
python -m quant.cli portfolio-construct --method equal_weight --symbols SPY QQQ NVDA
python -m quant.cli portfolio-construct --method inverse_volatility --symbols SPY QQQ NVDA --output-targets examples/portfolio_constructed_targets.json
python -m quant.cli portfolio-construct --method risk_parity --symbols SPY QQQ NVDA --lookback 60
python -m quant.cli portfolio-construct --method min_variance --symbols SPY QQQ NVDA --end 2025-01-01
```

The output target JSON is compatible with:

```bash
python -m quant.cli rebalance --targets examples/portfolio_constructed_targets.json --with-costs
```

## Methods

- `equal_weight`: assigns equal asset weights after reserving the minimum cash weight.
- `inverse_volatility`: gives lower-volatility assets larger weights.
- `risk_parity`: iteratively targets similar percentage risk contributions across assets.
- `min_variance`: uses a lightweight covariance-matrix minimum-variance solve and falls back safely when covariance is unusable.

The current implementation intentionally avoids heavyweight optimization libraries. It is deterministic, long-only, and designed to be easy to test.

## Constraints

Default constraints:

- `min_cash_weight`: `0.10`
- `max_position_weight`: `0.20`
- `max_sector_weight`: `0.50`
- `only_long`: `true`

Weights always sum to `1.0` including `cash`. Cash is residual unallocated capital after position, sector, and investable-weight constraints are applied; it is not treated as a risky asset in covariance or risk contribution calculations. Unknown sectors are not capped by sector weight because no sector grouping is available for those symbols. Known sectors use the built-in sector map from the Risk Engine.

`min_variance` can leave a high cash allocation when max-position constraints bind or when the risky assets are volatile. This is expected behavior for the current long-only constrained implementation.

`examples/portfolio_constructed_targets.json` is treated as a generated smoke-test artifact and is ignored by git. Regenerate it with `--output-targets` when needed.

## No-Lookahead

Portfolio construction reads only stored close prices at or before the requested `--end` date. If `--end` is omitted, it uses the latest stored price rows available in SQLite. The generated report sets:

```json
{
  "no_lookahead": true
}
```

The module computes target weights only. Rebalance or execution simulation remains responsible for next-step trade suggestions and fills.

## Report

Reports are written to:

```text
reports/portfolio_construction_YYYYMMDD_HHMMSS.json
```

Important fields:

- `method`
- `symbols_requested`
- `symbols_used`
- `excluded_symbols`
- `exclusion_reasons`
- `start_date`
- `end_date`
- `lookback`
- `no_lookahead`
- `target_weights`
- `cash_weight`
- `constraints`
- `volatility`
- `covariance_matrix`
- `correlation_matrix`
- `portfolio_volatility`
- `marginal_risk_contributions`
- `risk_contributions`
- `risk_contribution_pct`
- `warnings`
- `output_targets_path`

## Data Quality

Symbols are excluded when they have no stored prices, insufficient close history, insufficient return history, or zero volatility. Exclusion reasons are included in the report and CLI output.
