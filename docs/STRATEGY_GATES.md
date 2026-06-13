# Strategy Evaluation Gates

`v0.37.0` adds deterministic Strategy Evaluation Gates for offline research quality control.

Strategy Gates do not add factors, trading logic, broker access, live execution, machine learning, or news sentiment. They read Strategy DSL definitions, persisted research evidence, and offline simulation reports, then produce a `strategy_gate` report with `PASS`, `WARNING`, `FAIL`, or `REJECTED` statuses.

## Commands

```bash
python -m quant.cli strategy-gate --strategy momentum_fundamental
python -m quant.cli strategy-gate-report --latest
python -m quant.cli strategy-run --strategy momentum_fundamental --with-gates
```

`strategy-run --with-gates` first runs the existing offline Strategy DSL path, then passes the resulting strategy-run evidence to the Gate Runner. It does not change factor, alpha, trade simulation, report schema, or no-lookahead semantics.

## Gates

- `schema_validation`: rejects invalid DSL, unknown factors, live-trading fields, and no-lookahead override attempts.
- `data_quality`: checks price coverage and fundamental coverage when fundamental factors are present.
- `factor_history`: checks persisted Factor Store IC, RankIC, ICIR, coverage, and history depth.
- `walk_forward`: checks fold count, test Sharpe, and train/test gap diagnostics when walk-forward history exists.
- `regime_coverage`: checks regime sample support and factor-by-regime evidence.
- `trading_simulation`: checks drawdown, turnover, cost drag, and offline trade simulation evidence.
- `complexity`: checks factor count and parameter count.

Gate specs are auto-discovered from `quant/engines/strategy_gates/gates/`.

To add a gate:

1. Add a `GateSpec` to a module under `quant/engines/strategy_gates/gates/`.
2. Implement the matching handler on `StrategyGateRunner`; handlers receive a `GateRunInput`.
3. Add tests for ordering, status behavior, evidence fields, and report output.

Do not edit `GateRegistry` or the `StrategyGateRunner.run()` gate list for ordinary gate additions. The runner executes discovered specs by `order`.

## Status Semantics

- `PASS`: evidence meets configured thresholds.
- `WARNING`: evidence is missing, sparse, weak, or below a soft threshold.
- `FAIL`: a non-schema gate failed a configured hard check.
- `REJECTED`: the strategy failed deterministic validation or breached hard risk controls.

Missing Factor Store, walk-forward, or regime evidence is a `WARNING`, not a fabricated pass. Gate results are diagnostics, not return guarantees.

A `PASS` result does not authorize trading, paper trading, broker connectivity, order placement, or account mutation. Future Paper Trading Gates and Live Trading Gates are separate approval layers that would require explicit new permission gates, tests, documentation, and safety review. v0.37 implements research-quality gates only.

## Configuration

Default thresholds live in:

```text
examples/strategy_gate_config.json
```

The config controls coverage thresholds, IC/RankIC/ICIR thresholds, walk-forward fold count, drawdown, turnover, cost drag, regime sample support, and complexity thresholds.

## Report Schema

Reports are written to:

```text
reports/strategy_gate_YYYYMMDD_HHMMSS.json
```

Important fields:

- `strategy_name`
- `strategy_version`
- `strategy_file`
- `gate_config_path`
- `gate_config`
- `gate_results`
- `overall_status`
- `rejection_reasons`
- `evidence_summary`
- `input_reports`
- `warnings`
- `no_lookahead_notes`
- `recommended_next_checks`

## No-Lookahead

Strategy Gates preserve existing no-lookahead boundaries:

- Fundamental factor evidence remains governed by `report_date <= signal_date`.
- Strategy DSL cannot override no-lookahead settings.
- Gate reports may read future evaluation reports as research evidence, but they do not feed those values back into historical signal generation or trade selection.
- Gate evaluation is quality control after or around a research run, not a trading signal.

## MCP

v0.37 exposes:

- `run_strategy_gates`: `OFFLINE_SIMULATION`
- `latest_strategy_gate_report`: `READ_ONLY`

These tools can generate or read local research reports. They cannot connect brokers, submit orders, mutate real accounts, or enable live trading.
