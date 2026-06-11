# Data Schema

The default SQLite database is `data/quant.db`.

## prices

Daily OHLCV price data.

Primary key:

- `(symbol, date)`

Columns:

- `symbol`: ticker symbol.
- `date`: trading date in `YYYY-MM-DD`.
- `open`: daily open.
- `high`: daily high.
- `low`: daily low.
- `close`: daily close.
- `adj_close`: adjusted close.
- `volume`: daily volume.
- `created_at`: insertion timestamp.
- `updated_at`: update timestamp.

## symbol_metadata

Static symbol metadata for universe construction and sector diagnostics.

Primary key:

- `symbol`

Columns:

- `symbol`: ticker symbol.
- `name`: issuer or fund name.
- `asset_type`: `Equity` or `ETF`.
- `sector`: sector classification or `ETF`.
- `industry`: industry classification.
- `currency`: reporting/trading currency.
- `exchange`: primary exchange.
- `created_at`: insertion timestamp.
- `updated_at`: update timestamp.

## accounts

Simulated account state.

Columns:

- `id`: account id.
- `name`: unique account name.
- `cash`: current cash.
- `initial_cash`: initial cash.
- `created_at`: insertion timestamp.
- `updated_at`: update timestamp.

## positions

Current simulated holdings.

Primary key:

- `(account_id, symbol)`

Columns:

- `account_id`: account id.
- `symbol`: ticker symbol.
- `qty`: current quantity.
- `avg_cost`: average cost.
- `updated_at`: update timestamp.

## trades

Append-only simulated trade ledger.

Columns:

- `id`: trade id.
- `account_id`: account id.
- `symbol`: ticker symbol.
- `side`: `BUY` or `SELL`.
- `qty`: executed quantity.
- `price`: executed price.
- `amount`: `qty * price`.
- `created_at`: trade timestamp.

## reports/backtest_*.json

Backtest reports are generated files, not database tables. They are ignored by git.

Top-level keys:

- `start`, `end`: requested backtest period.
- `initial_cash`: initial simulated cash.
- `mode`: optimizer mode.
- `rebalance_frequency`: monthly, weekly, or daily.
- `strategy`: `portfolio` or `alpha`.
- `no_lookahead`: true for the alpha strategy path.
- `signal_execution_lag`: signal and execution timing description.
- `alpha_config`: alpha config used for alpha strategy runs.
- `excluded_symbols_per_rebalance`: per-signal-date excluded symbols and reasons.
- `metrics`: final value, returns, drawdown, volatility, Sharpe ratio, trade count, turnover, total cost, and cash ratio.
- `trades`: deterministic simulated backtest executions with costs. Alpha strategy trades include `signal_date`, `execution_date`, `signal_price`, and `execution_price`.
- `equity_curve`: daily cash, positions, equity values, `last_signal_date`, and `last_execution_date`.

## reports/rebalance_*.json

Rebalance reports are generated files, not database tables. They are ignored by git.

Top-level keys:

- `total_assets`: current cash plus current market value of positions.
- `cash_before`: current account cash.
- `cash_after_rebalance`: estimated cash after suggested trades and commissions.
- `commission_rate`: configured commission rate.
- `estimated_total_commission`: estimated commission across suggested trades.
- `items`: cash and per-symbol current/target values, differences, action, quantity, and estimated trade cost.
- `warnings`: non-blocking warnings such as cash below target allocation.

## reports/risk_*.json

Risk reports are generated files, not database tables. They are ignored by git.

Top-level keys:

- `total_assets`: current cash plus current market value of positions.
- `cash_value`: current account cash.
- `cash_weight_pct`: cash as a percent of total assets.
- `single_stock_concentration_pct`: largest single holding weight.
- `industry_concentration_pct`: largest industry group weight.
- `top_5_holdings_pct`: sum of the five largest holding weights.
- `risk_score`: 0-100 score, where higher means more risk.
- `holdings`: per-symbol value, weight, and industry.
- `industries`: per-industry value and weight.
- `warnings`: non-blocking warnings such as unknown industry mapping.

## reports/optimize_*.json

Optimizer reports are generated files, not database tables. They are ignored by git.

Top-level keys:

- `mode`: optimizer mode.
- `current_allocation`: current cash and holding weights.
- `optimized_allocation`: target weights compatible with `rebalance --targets`.
- `constraints`: constraints used by the optimizer.
- `warnings`: skipped symbols or constraint adjustments.
- `risk_score_before`: current Risk Engine score.
- `estimated_risk_score_after`: estimated score using optimized target weights.
- `rationale`: human-readable explanation of the optimizer path.
- `targets_path`: target allocation JSON path.

## reports/alpha_*.json

Alpha reports are generated files, not database tables. They are ignored by git.

Top-level keys:

- `config`: alpha config used for the run.
- `as_of_date`: resolved signal date used for the selected symbols.
- `data_start_date`: earliest selected data row used by the long lookback.
- `data_end_date`: latest selected data row used by the signal.
- `lookback_used`: factor lookback settings.
- `factors`: per-symbol factor values, rank, and selected flag.
- `selected_symbols`: selected ranked symbols.
- `target_weights`: target weights compatible with `rebalance --targets`.
- `excluded_symbols`: symbols excluded from ranking.
- `exclusion_reasons`: per-symbol exclusion reason.
- `suggested_execution_date`: next stored trading date after the signal date when available.
- `warnings`: missing data or weighting fallback warnings.
- `targets_path`: optional target allocation JSON path.

## reports/factor_eval_*.json

Factor evaluation reports are generated files, not database tables. They are ignored by git.

Top-level keys:

- `factor`: evaluated factor name.
- `start_date`, `end_date`: optional inclusive signal-date range.
- `forward_days`: future-return horizon used for the main evaluation.
- `universe`: requested symbol universe.
- `no_lookahead`: true for the framework design.
- `ic_mean`, `ic_std`, `ic_positive_rate`, `ic_count`: Pearson IC summary.
- `rank_ic_mean`, `rank_ic_std`, `rank_ic_positive_rate`, `rank_ic_count`: Spearman Rank IC summary.
- `icir`: `ic_mean / ic_std` when available.
- `quintiles`: average future returns for `q1` through `q5`.
- `spread_return`: `q5 - q1`.
- `decay`: IC and Rank IC for 1, 5, 10, 20, and 60 day forward windows.
- `observations`: per-symbol signal-date observations with factor value and future return.
- `excluded_symbols`: symbols without valid factor and future-return pairs.
- `exclusion_reasons`: per-symbol exclusion reason.
- `warnings`: non-blocking data quality warnings.
- `pipeline_config`: optional factor pipeline config used before evaluation metrics.

## reports/factor_pipeline_*.json

Factor pipeline reports are generated files, not database tables. They are ignored by git.

Top-level keys:

- `factor`: factor processed by the pipeline.
- `as_of_date`: signal date for the cross-section.
- `raw_factor_values`: raw per-symbol factor values.
- `cleaned_factor_values`: cleaned per-symbol factor values after preprocessing.
- `excluded_symbols`: symbols removed during missing-value handling.
- `exclusion_reasons`: per-symbol exclusion reason.
- `preprocessing_steps_applied`: ordered list of preprocessing steps applied.
- `before_summary_statistics`: count, missing count, mean, standard deviation, min, and max before preprocessing.
- `after_summary_statistics`: count, missing count, mean, standard deviation, min, and max after preprocessing.
- `sector_neutralization_result`: per-sector mean before, mean after, and count when enabled.
- `warnings`: non-blocking warnings such as unknown sector or placeholder beta neutralization.
- `no_lookahead`: true for the framework design.

## reports/factor_backtest_*.json

Long-short factor backtest reports are generated files, not database tables. They are ignored by git.

Top-level keys:

- `factor`: evaluated factor name.
- `start_date`, `end_date`: optional inclusive signal-date range.
- `holding_period`: forward-return horizon in stored price rows.
- `quantiles`: number of factor buckets.
- `long_quantile`: quantile used for the long leg.
- `short_quantile`: quantile used for the short leg.
- `observations`: processed symbol-date observations.
- `rebalance_dates`: signal dates where the long-short spread is formed.
- `quantile_returns`: average future return by quantile.
- `top_quantile_return`: average future return for the configured long quantile.
- `bottom_quantile_return`: average future return for the configured short quantile.
- `long_symbols_by_date`: long symbols for each signal date.
- `short_symbols_by_date`: short symbols for each signal date.
- `long_leg_return`: compounded long-leg return.
- `short_leg_return`: compounded short-leg return.
- `long_short_return`: compounded long-short return stream.
- `annual_return`, `long_short_annual_return`: annualized long-short return.
- `volatility`, `long_short_volatility`: annualized long-short volatility.
- `sharpe`, `long_short_sharpe`: annualized long-short Sharpe ratio.
- `max_drawdown`: drawdown of the compounded long-short return stream.
- `hit_rate`: share of positive long-short periods.
- `turnover`: average long-short weight turnover between signal dates.
- `gross_exposure`: average gross long-short exposure.
- `net_exposure`: average net long-short exposure.
- `ic_mean`, `rank_ic_mean`, `icir`: cross-sectional factor diagnostics.
- `excluded_symbols`, `exclusion_reasons`: skipped symbols and reasons.
- `no_lookahead`: true for the framework design.
- `signal_execution_lag`: signal/forward-return timing description.
- `pipeline_enabled`: whether Factor Pipeline preprocessing was applied.
- `pipeline_config_path`: config path supplied from the CLI when available.
- `pipeline_config`: optional Factor Pipeline config applied before quantile grouping.
- `periods`: per-signal-date long symbols, short symbols, weights, exposures, quantile returns, long-short return, and turnover.
- `warnings`: non-blocking data quality warnings.

## reports/strategy_eval_*.json

Strategy evaluation reports are generated files, not database tables. They are ignored by git.

Top-level keys:

- `metadata`: creation time, engine name, offline/no-live-trading flags, and source no-lookahead flag.
- `input_report_paths`: source report paths used for evaluation.
- `strategy_type`: `factor_backtest` or `backtest`.
- `evaluation_window`: first and last return observation date.
- `summary_metrics`: total return, annual return, annual volatility, Sharpe, Sortino, max drawdown, Calmar, hit rate, win/loss ratio, best/worst period, turnover, total cost, cost-to-return ratio, exposure, cash drag, and benchmark metrics when available.
- `benchmark_metrics`: benchmark symbol, benchmark return, excess return, and information ratio when supplied.
- `attribution`: return attribution by symbol and side, cost attribution by symbol, turnover attribution by symbol, top positive and negative contributors, return concentration, methodology notes, risk attribution, and drawdown attribution.
- `robustness_diagnostics`: rolling metrics, monthly returns, yearly returns, and diagnostics keyed by warning code.
- `warnings`: warning objects with `code` and `reason`.
- `interpretation_notes`: scope notes for offline interpretation.

## reports/data_quality_*.json

Data quality reports are generated files, not database tables. They are ignored by git.

Top-level keys:

- `created_at`: report timestamp.
- `symbols`: analyzed symbols.
- `status`: overall `PASS`, `WARNING`, or `FAIL`.
- `summary`: count of pass, warning, and fail symbols.
- `diagnostics`: per-symbol checks for missing ratio, duplicate rows, price outliers, zero/negative prices, zero-volume days, short history, data gaps, stale data, and adjusted close availability.

## reports/data_refresh_*.json

Data refresh reports are generated files, not database tables. They are ignored by git.

Top-level keys:

- `created_at`: report timestamp.
- `symbols`: refreshed symbols.
- `summary`: total symbols, inserted rows, updated rows, skipped existing rows, and error count.
- `per_symbol`: per-symbol inserted, updated, skipped, fetched, fetch start, end date, status, and error message.

## reports/data_coverage_*.json

Data coverage reports are generated files, not database tables. They are ignored by git.

Top-level keys:

- `total_symbols`
- `symbols_with_price_data`
- `symbols_without_price_data`
- `average_history_length`
- `oldest_date`
- `newest_date`
- `symbols`: per-symbol coverage rows.

## reports/research_readiness_*.json

Research readiness reports are generated files, not database tables. They are ignored by git.

Top-level keys:

- `readiness_score`: 0-100 score.
- `universe_size`
- `history_depth_average`
- `sector_count`
- `factor_coverage_symbols`
- `data_quality_status`
- `recommendations`
- `coverage_report_path`
- `data_quality_report_path`

## Agent export summaries

Agent export summaries can be printed to stdout or written to an optional output path. They are generated artifacts, not database tables. They are ignored by git when written under `reports/`.

Supported formats:

- text
- markdown
- compact JSON

Common compact JSON keys:

- `report_type`
- `generated_from`
- `summary`
- `key_metrics`
- `key_findings`
- `warnings`
- `recommended_next_steps`
- `action_candidates`
- `data_quality_notes`

Agent exports are not raw source reports and do not modify source report schemas.

## reports/portfolio_construction_*.json

Portfolio construction reports are generated files, not database tables. They are ignored by git.

Top-level keys:

- `method`: `equal_weight`, `inverse_volatility`, `risk_parity`, or `min_variance`.
- `symbols_requested`: requested symbol list.
- `symbols_used`: symbols with valid aligned return history.
- `excluded_symbols`, `exclusion_reasons`: skipped symbols and reasons.
- `start_date`, `end_date`: aligned return window used for calculation.
- `lookback`: maximum number of stored price rows used before return calculation.
- `no_lookahead`: true for the framework design.
- `target_weights`: rebalance-compatible weights including `cash`.
- `cash_weight`: final cash target weight.
- `constraints`: min cash, max position, max sector, and long-only settings.
- `volatility`: per-symbol realized return volatility over the calculation window.
- `covariance_matrix`: return covariance matrix.
- `correlation_matrix`: return correlation matrix.
- `portfolio_volatility`: volatility implied by target asset weights.
- `marginal_risk_contributions`: marginal contribution of each asset to portfolio volatility.
- `risk_contributions`: total risk contribution by asset.
- `risk_contribution_pct`: percentage contribution to total portfolio risk by asset.
- `warnings`: constraint adjustments or fallback notes.
- `output_targets_path`: optional target JSON path written by `--output-targets`.

## reports/cost_*.json

Cost reports are generated files, not database tables. They are ignored by git.

Top-level keys:

- `model`: `fixed`, `linear`, or `combined`.
- `currency`: reporting currency.
- `config`: cost model parameters.
- `trades`: per-trade symbol, side, shares, price, notional, fees, slippage, total cost, and cost ratio.
- `gross_trade_value`: sum of trade notionals.
- `total_commission`: fixed plus linear commissions.
- `total_slippage`: slippage cost.
- `total_cost`: all estimated costs.
- `total_cost_ratio`: total cost divided by gross trade value.
- `warnings`: small trades or poor cost efficiency warnings.

## reports/execution_*.json

Execution simulation reports are generated files, not database tables. They are ignored by git.

Top-level keys:

- `mode`: `immediate`, `next_day_open`, `twap`, or `partial_fill`.
- `target_allocation`: target weights used for rebalance suggestions.
- `intended_trades`: Rebalance Engine suggestions before execution simulation.
- `executed_trades`: simulated fills with per-fill costs.
- `unfilled_trades`: quantities that were not filled and reasons.
- `execution_costs`: gross value, commission, slippage, total cost, and cost ratio.
- `slippage_estimate`: total simulated slippage cost.
- `final_cash`: cash after simulated fills and costs.
- `final_positions`: simulated ending quantities.
- `warnings`: non-blocking warnings.

## v0.19 Factor Metadata

Factor evaluation and factor backtest reports include registry metadata:

- `factor_family`
- `factor_type`
- `factor_category`
- `factor_description`
- `factor_inputs`
- `factor_higher_is_better`
- `factor_no_lookahead`

Alpha factor rows may include:

- `factor_values`: raw registered factor values by symbol.
- `factor_contributions`: weighted normalized factor contributions when composite alpha is enabled.
- `composite_alpha_score`: final blended score used for ranking when `factor_weights` are configured.

## reports/walk_forward_*.json

Walk-forward reports are generated files, not database tables. Top-level keys:

- `metadata`: engine, creation time, validation-only flags, and no-lookahead marker.
- `strategy`: `alpha` or `factor_long_short`.
- `parameters`: universe, windows, factor, cash, rebalance frequency, and fold limits.
- `folds`: train/test windows and fold metrics.
- `summary`: average train/test metrics plus best and worst folds.
- `rolling_validation`: rolling return, Sharpe, IC, Rank IC, and drawdown.
- `stability_analysis`: factor stability ranking.
- `warnings`: deterministic diagnostics.
- `recommendations`: deterministic follow-up suggestions.

## reports/trade_sim_*.json

Trading simulation reports are generated files, not database tables. They are ignored by git.

Top-level keys:

- `metadata`: report type, generation time, offline simulation flags, and no-broker markers.
- `parameters`: start/end, rebalance frequency, execution price, symbols, alpha config, and cost config.
- `strategy`: currently `alpha`.
- `portfolio_method`: `equal_weight`, `inverse_volatility`, `risk_parity`, or `min_variance`.
- `initial_cash`: starting simulated account cash.
- `final_equity`: final marked-to-market account equity.
- `total_return`, `annual_return`, `volatility`, `sharpe`, `max_drawdown`: account-level metrics.
- `total_cost`: cumulative simulated transaction costs paid.
- `turnover`: gross trade value divided by initial cash.
- `trade_count`: number of simulated fills.
- `equity_curve`: daily equity observations.
- `cash_curve`: daily cash observations.
- `positions_by_date`: daily positions and marked market value.
- `trades`: simulated fills with signal and execution dates.
- `rebalance_events`: signal date, execution date, targets, fills, costs, and warnings by rebalance.
- `warnings`: deterministic simulation warnings.
- `no_lookahead`: true for the signal/execution design.

## reports/charts/*

Visualization outputs are generated artifacts, not database tables. They are ignored by git.

Generated files include:

- `*_equity_curve.png` / `.svg`
- `*_drawdown_curve.png` / `.svg`
- `*_factor_decay.png` / `.svg`
- `*_target_weights.png` / `.svg`
- `*_summary.html`

The source JSON report is not modified. Agent Export may include chart paths in `visualization_paths` when matching chart files exist.
