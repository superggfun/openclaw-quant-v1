# Factor Library

v0.19.0 expanded deterministic price-history factors. v0.26.0 adds accounting-based fundamental factors while preserving the no-lookahead contract. Price factors use stored price history at or before the signal date. Fundamental factors use only rows whose `report_date <= signal_date`. No machine learning, news sentiment, broker data, or live market data is used.

## CLI

```bash
python -m quant.cli factor-list
python -m quant.cli factor-eval --factor quality_score
python -m quant.cli factor-backtest --factor reversal_20d
python -m quant.cli factor-eval --factor fundamental_quality_score
python -m quant.cli factor-backtest --factor fundamental_value_score
python -m quant.cli factor-store-summary --sync-definitions
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

## Composite And Multi-Factor Alpha

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

`v0.27.0` adds a formal Multi-Factor Model v2 in `quant/multi_factor`. It supports explicit families (`PRICE`, `VALUE`, `QUALITY`, `GROWTH`, `HEALTH`, `LOW_VOL`, `REVERSAL`), rank/z-score normalization, optional winsorization, equal/custom/IC/stability weighting, coverage-aware confidence, and factor/family contribution reporting.

Multi-factor confidence is a deterministic diagnostic about coverage and supplied stability inputs. It is not a return guarantee.

## Factor Store Integration

`v0.31.0` adds a persistent Factor Store. `factor-store-summary --sync-definitions` records registry metadata such as category, description, `higher_is_better`, and whether fundamental data is required. `factor-eval`, `factor-backtest`, and `walk-forward` can opt in to persistence with `--save-factor-history`.

This is lifecycle metadata and research history only; it does not create new factors and does not alter factor evaluation, factor backtest, alpha, or walk-forward semantics.

## No-Lookahead

Factor scores are calculated from price rows up to the signal date. Future returns are used only by evaluation and backtest modules after rankings are fixed. Pipeline preprocessing operates on the same signal-date cross-section and does not access future rows.

## Limitations

`value_score`, `quality_score`, and `growth_score` remain price-derived proxies for backward compatibility.

Accounting factors added in v0.26 include `fundamental_value_score`, `fundamental_quality_score`, `fundamental_growth_score`, `fundamental_health_score`, and `fundamental_composite_score`. These use imported `fundamental_metrics` rows and require `report_date <= signal_date`.

Long-short factor backtests compound overlapping forward-return spread observations. A leveraged spread period can be less than `-100%`; if that happens, the report emits a warning and the compounded spread can reach `-100%`. Treat this as a research diagnostic, not as a broker-executable portfolio equity curve.
