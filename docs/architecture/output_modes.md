# Output Modes

OpenClaw Quant uses a tiered output system optimized for different consumption surfaces — CLI, MCP, archival reports, and correctness debugging.

## Design Philosophy

- **Compact by default.** Most factor research runs produce large result objects (FactorEvaluationResult, FactorBacktestResult). Shipping full observations over MCP or printing verbose JSON wastes tokens, bandwidth, and human attention.
- **Reports are archival.** Full Markdown/JSON reports are preserved for compliance, audit trails, and deep-dive analysis — never the default.
- **Production paths are optimized.** Bulk-matrix acceleration and in-memory providers are on by default in production. Serial reference is a debug lane.

---

## Output Modes

Three conceptual tiers, mapped from `quant/engines/output_modes.py`:

| Mode | Enum | Purpose |
|------|------|---------|
| **Compact JSON** | `COMPACT` | Default for CLI and MCP. Lightweight summary with key metrics — no raw observations or full period lists. |
| **Full JSON** | `FULL` | Full result objects when explicitly requested via `--output` or `--write-report`. |
| **Archive (Markdown)** | `ARCHIVE` | Reports written to `reports/` for audit, compliance, and offline review. Triggered explicitly with `--write-report` / `--archive`. |

### Compact JSON (Default)

Compact JSON is the default output mode for:
- The `factor-test` CLI command (recommended daily tool)
- MCP tools (`evaluate_factor`, `test_factor`)
- Programmatic use via `to_summary()` / `to_mcp_response()`

Compact output includes **key metrics only**: IC mean, rank IC, Sharpe, drawdown, turnover, hit rate, quantile returns, warnings, and performance metadata. Raw observations and full period lists are **excluded by default** (`include_observations=False`).

### Reports / Markdown (Archive Mode)

Full reports are **opt-in only**. They require explicit flags:
- `--write-report` writes a JSON report to the `reports/` directory
- `--archive` generates a Markdown report file

Reports are intended for:
- Compliance and audit trails
- Detailed offline review
- Historical record-keeping

### Serial Reference (Debug Mode)

The serial reference path (`--no-bulk-matrix`) bypasses all acceleration:
- Disables `bulk_matrix` (FactorMatrixBuilder)
- Uses one-by-one factor computation per symbol/horizon
- Produces identical results to the accelerated path — purely for **correctness verification and debugging**
- Not recommended for daily use; roughly 10-50× slower

---

## Production Compute Defaults

In production, factor evaluation and backtesting default to:

| Setting | Default | Meaning |
|---------|---------|---------|
| `bulk_matrix` | `True` | Uses FactorMatrixBuilder for vectorized multi-horizon computation |
| `prefer_in_memory` | `True` | Keeps matrix in memory (InMemory provider) rather than spilling to disk |

These are set in `FactorEvaluation.evaluate()` and the corresponding backtest engine. The serial reference path (`--no-bulk-matrix`) is strictly for debugging.

### Performance Metadata

Compact summaries include `performance_metadata` with the actual runtime configuration:

```json
{
  "performance_metadata": {
    "bulk_matrix_enabled": true,
    "serial_reference": false,
    "provider_type": "InMemory",
    "cache_strategy": "...",
    "fallback_used": false,
    "matrix_workers": 4,
    "eval_seconds": 2.3
  }
}
```

---

## `include_observations` — Controlling Payload Size

Both `to_summary()` and `to_mcp_response()` accept `include_observations: bool = False`:

- **`False` (default):** Returns only aggregate metrics. Payload is typically < 2 KB. Safe for MCP, CLI, and agent consumption.
- **`True`:** Appends the full `observations` list (FactorEvaluationResult) or `periods` list (FactorBacktestResult). Payload can reach 100+ KB for large universes.

**Default is `False`** to avoid accidentally shipping large payloads over MCP or into agent context windows.

---

## Result Objects & Serialization Methods

### FactorEvaluationResult

Located in `quant/engines/factor_eval/factor_evaluation.py`.

| Method | Returns | Includes Observations? |
|--------|---------|----------------------|
| `to_summary(include_observations=False)` | `dict` — compact key metrics | By flag |
| `to_mcp_response(include_observations=False)` | `dict` — alias for `to_summary()` | By flag |
| `to_json(...)` | `str` — JSON string | By flag |
| `to_report()` | `dict` — full report with all fields | Always |

### FactorBacktestResult

Located in `quant/engines/factor_backtest/factor_backtest.py`.

| Method | Returns | Includes Periods? |
|--------|---------|-------------------|
| `to_summary(include_observations=False)` | `dict` — compact key metrics | By flag |
| `to_mcp_response(include_observations=False)` | `dict` — alias for `to_summary()` | By flag |
| `to_json(...)` | `str` — JSON string | By flag |
| `to_report()` | `dict` — full report with all fields | Always |

---

## Scoring: 0–100 System with PASS / WATCH / REJECT / ERROR

The scoring engine in `quant/engines/output_modes.py` computes a **0–100 composite score** from evaluation and backtest results, then classifies the factor into one of four statuses.

### Score Components

| Component | Weight | Key Inputs |
|-----------|--------|-----------|
| **IC** | 30% | `ic_mean`, `rank_ic_mean`, `icir`, `ic_positive_rate` |
| **Return** | 30% | `long_short_return`, `annual_return`, `sharpe` / `long_short_sharpe` |
| **Risk** | 20% | `max_drawdown`, `hit_rate` |
| **Turnover / Cost** | 10% | `turnover` |
| **Data Quality** | 10% | `observation_count`, `warnings`, `fallback_used` |

### Classification Thresholds

| Status | Score Range | Meaning |
|--------|-------------|---------|
| **PASS** 🟢 | ≥ 70 + no fallback | Strong signal. Ready for further research or portfolio consideration. |
| **WATCH** 🟡 | 50 – 69 (or ≥ 70 with fallback) | Moderate signal. Monitor, refine, or investigate. |
| **REJECT** 🔴 | < 50 | Weak signal. Not usable in current form. |
| **ERROR** ⚪ | — | Computation failed (exception, no observations, etc.) |

### Hard Reject Criteria

Even if the score is above 50, these conditions trigger automatic rejection:

- `observation_count == 0` → `ERROR`
- `max_drawdown < -80%` → `REJECT`
- `abs(ic_mean) < 0.005` → `REJECT`
- `turnover > 200%` → `REJECT`

### Usage

Scoring is integrated into both CLI and MCP paths:

```python
from quant.engines.output_modes import score_factor

scoring = score_factor(eval_summary, bt_summary)
# scoring = {"score": 72.5, "status": "PASS", "reason": "strong signal (score=72)", ...}
```

---

## Recommended Daily Tool: `factor-test` CLI

`factor-test` is the recommended daily interface for quick factor validation. It runs evaluation + backtest, scores the result, and outputs **compact JSON to stdout**.

```bash
# Single factor
python -m quant.cli factor-test --factor momentum_20d --pretty

# Multiple factors
python -m quant.cli factor-test --factors momentum_20d,momentum_60d --pretty

# With report generation
python -m quant.cli factor-test --factor momentum_20d --write-report

# Debug: serial reference path
python -m quant.cli factor-test --factor momentum_20d --no-bulk-matrix
```

### Key Flags

| Flag | Default | Purpose |
|------|---------|---------|
| `--write-report` | `False` | Generate full JSON report in `reports/` |
| `--include-observations` | `False` | Include raw observations in output |
| `--no-bulk-matrix` | `False` | Use serial reference path (debug only) |
| `--mode quick` | `quick` | Single horizon (20d). `standard` = multi-horizon |
| `--max-symbols` | `200` | Universe size cap |
| `--pretty` | `False` | Pretty-print JSON |
| `--output <path>` | — | Write result JSON to file |

### Output Format

```json
{
  "run_type": "factor_test",
  "mode": "quick",
  "results": [
    {
      "factor": "momentum_20d",
      "status": "PASS",
      "score": 78.4,
      "metrics": {
        "ic_mean": 0.038,
        "rank_ic_mean": 0.042,
        "icir": 0.65,
        "sharpe": 1.23,
        "max_drawdown": -0.18,
        "turnover": 0.35,
        ...
      },
      "decision": {"useful": true, "reason": "strong signal (score=78)"},
      "scoring": {...},
      "warnings": [],
      "metadata": {
        "bulk_matrix_enabled": true,
        "serial_reference": false,
        "provider_type": "InMemory",
        "runtime_seconds": 2.3
      }
    }
  ],
  "summary": {
    "pass": 1,
    "watch": 0,
    "reject": 0,
    "error": 0,
    "top_factors": [{"factor": "momentum_20d", "score": 78.4, "status": "PASS", ...}]
  }
}
```

---

## MCP Integration

### MCP Defaults

MCP tools default to compact JSON output:

- `evaluate_factor` → calls `FactorEvaluationResult.to_mcp_response(include_observations=False)`
- `test_factor` → runs eval + backtest, calls `to_summary()` on both, pipes through `score_factor()`, returns compact result with score/status/decision

Both accept `include_observations` and `write_report` as optional boolean arguments.

### `test_factor` MCP Tool

The `test_factor` MCP tool is the primary MCP entry point for factor research. It:
1. Runs `FactorEvaluation.evaluate()` with `write_report` from arguments
2. Runs the factor backtest engine with `write_report` from arguments
3. Calls `eval_result.to_summary()` and `bt_result.to_summary()`
4. Scores via `score_factor()`
5. Returns a compact response: `{factor, status, score, metrics, decision, scoring, warnings, metadata}`

### MCP Response Shape

```json
{
  "factor": "momentum_20d",
  "status": "PASS",
  "score": 78.4,
  "metrics": {...},
  "decision": {"useful": true, "reason": "strong signal (score=78)"},
  "scoring": {...},
  "warnings": [],
  "metadata": {...}
}
```

---

## Summary of Defaults

| Surface | Output Mode | `include_observations` | `write_report` | `bulk_matrix` |
|---------|------------|----------------------|----------------|---------------|
| `factor-test` CLI | Compact JSON | `False` | `False` | `True` |
| MCP `evaluate_factor` | Compact JSON | `False` | `False` | `True` |
| MCP `test_factor` | Compact JSON + Score | `False` | `False` | `True` |
| `--write-report` | Full JSON report | N/A | `True` | Per flag |
| `--no-bulk-matrix` | Serial reference | Per flag | Per flag | **`False`** |

The system is designed so that **the fast, compact path is the default**, and heavier outputs (reports, raw observations) require explicit opt-in.
