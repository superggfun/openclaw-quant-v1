# Daily Research Scheduler

v0.33.0 adds an offline Daily Research Scheduler for repeatable research automation.

It is not live trading, not broker execution, not real-time market data, and not investment advice. It runs existing OpenClaw Quant research modules in sequence and records artifacts for human and agent review.

## Commands

```bash
python -m quant.cli research-run
python -m quant.cli research-status
python -m quant.cli research-history
python -m quant.cli research-report
```

`research-run` reads `examples/research_scheduler_config.json` by default. This default is the lightweight daily/smoke research pipeline. It is intentionally local-friendly: it skips network data refresh, uses a compact four-symbol universe, and runs one factor. It should not be interpreted as full-universe, full-research validation.

Full research remains available through config:

- set `run_data_refresh` to `true`
- expand `symbols`
- add multiple `factors`
- keep `run_visualization` and `run_agent_export` enabled
- extend `trade_sim_start` and `trade_sim_end`
- use a richer alpha config path

Runtime overrides include:

```bash
python -m quant.cli research-run --skip-data-refresh --factor momentum_20d
python -m quant.cli research-run --symbols SPY,QQQ,NVDA --skip-trade-sim
```

## Pipeline

The daily pipeline can run data refresh, data coverage, fundamental coverage, factor evaluation, Factor Store update, regime detection, historical trade simulation, visualization, Agent Export, and daily research summary generation.

Each step records `PASS`, `WARNING`, `FAIL`, or `SKIPPED`. Failures are isolated where possible, so later steps can still run and the final summary includes failure warnings.

## History

Scheduler history is stored in SQLite table `research_run_history` with `run_id`, timestamp, status, duration, warnings, factor count, regime, trade simulation return, and generated report paths.

## Report

`research-run` writes `reports/research_run_YYYYMMDD_HHMMSS.json` with metadata, run ID, pipeline steps, warnings, artifacts, daily summary, and recommended next checks.

Reports also include `config_source`, `config_path`, `pipeline_mode`, `lightweight_default`, enabled and disabled pipeline steps, skipped step reasons, `generated_reports`, `generated_visualizations`, `generated_agent_exports`, `report_path`, and a warning summary by stable warning code.

Final status is `PASS` only when all enabled steps pass with no warnings and no configured steps are skipped. It is `WARNING` when any step warns or any step is intentionally skipped. It is `FAIL` when any enabled step fails; later independent steps still run when possible.

## Agent Export And Visualization

Agent Export supports `research_run`, `research_status`, and `research_history` reports. Visualization supports scheduler dashboards for pipeline status, trade simulation metrics, factor ICIR summaries, and artifact counts.

`v0.35.0` exposes scheduler status/history/report and local `run_research_pipeline` through MCP tools. These MCP tools remain offline research orchestration only. They do not run a daemon, schedule cron jobs, connect to brokers, or place orders.

## Boundaries

The scheduler automates offline research commands only. It does not place orders, connect to brokers, alter persistent portfolio state, or make autonomous trading decisions.
