# Factor Library

v0.19.0 expands the deterministic factor library while preserving the existing no-lookahead contract. Every factor is computed from stored price history at or before the signal date. No machine learning, news sentiment, paid fundamentals, broker data, or live market data is used.

## CLI

```bash
python -m quant.cli factor-list
python -m quant.cli factor-eval --factor quality_score
python -m quant.cli factor-backtest --factor reversal_20d
python -m quant.cli alpha
```

## Factors

| Factor | Category | Higher Is Better | Inputs | Description |
| --- | --- | --- | --- | --- |
| `momentum_20d` | momentum | yes | close | 20-day close-to-close momentum. |
| `momentum_60d` | momentum | yes | close | 60-day close-to-close momentum. |
| `volatility_20d` | risk | no | close | 20-day realized volatility. This raw risk measure is useful for diagnostics, not as a long-only preference score. |
| `risk_adjusted_momentum` | momentum | yes | close | 60-day momentum divided by 20-day volatility. |
| `value_score` | value | yes | close | Price-only valuation proxy that favors long-term relative underperformance. |
| `quality_score` | quality | yes | close | Price-only stability proxy using consistency, volatility, and drawdown resistance. |
| `growth_score` | growth | yes | close | Multi-horizon trend persistence proxy. |
| `reversal_5d` | reversal | yes | close | 5-day mean-reversion score. Higher score means worse recent performance and stronger expected reversal. |
| `reversal_20d` | reversal | yes | close | 20-day mean-reversion score. Higher score means worse recent performance and stronger expected reversal. |
| `low_volatility_score` | low volatility | yes | close | Higher scores for lower 20-day realized volatility. |

## Composite Alpha

`examples/alpha_config.json` can define `factor_weights`. The Alpha Engine normalizes positive weights, rank-normalizes each factor cross-section using signal-date data only, and combines weighted rank scores into `composite_alpha_score`.

```json
{
  "factor_weights": {
    "momentum_60d": 0.30,
    "quality_score": 0.25,
    "growth_score": 0.20,
    "low_volatility_score": 0.15,
    "reversal_20d": 0.10
  }
}
```

Alpha reports include per-symbol `factor_values`, `factor_contributions`, and `composite_alpha_score`. Target weights remain constrained by cash and max-position settings and are compatible with `rebalance --targets`.

## No-Lookahead

Factor scores are calculated from price rows up to the signal date. Future returns are used only by evaluation and backtest modules after rankings are fixed. Pipeline preprocessing operates on the same signal-date cross-section and does not access future rows.

## Limitations

These are research proxies, not full fundamental factors. `value_score`, `quality_score`, and `growth_score` use price-derived approximations until future data-provider work adds audited fundamentals. In particular, `value_score` is not a true valuation factor such as book-to-market, earnings yield, sales yield, or cash-flow yield.

Long-short factor backtests compound overlapping forward-return spread observations. A leveraged spread period can be less than `-100%`; if that happens, the report emits a warning and the compounded spread can reach `-100%`. Treat this as a research diagnostic, not as a broker-executable portfolio equity curve.
