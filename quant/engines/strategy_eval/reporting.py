"""Strategy evaluation report I/O."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from quant.engines.strategy_eval.models import StrategyEvaluationResult
from quant.reports.report_io import generate_report_path, write_json_report


def load_report(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"strategy evaluation report file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"strategy evaluation report is not valid JSON: {path}") from exc
    if not isinstance(data, dict):
        raise ValueError("strategy evaluation source report must contain a JSON object")
    return data


def report_type(data: dict[str, Any]) -> str:
    if "periods" in data and "long_short_return" in data:
        return "factor_backtest"
    if "metrics" in data and "equity_curve" in data:
        return "backtest"
    return "unknown"


def write_report(
    result: StrategyEvaluationResult,
    report_dir: Path,
    output_path: str | Path | None = None,
) -> Path:
    if output_path:
        path = Path(output_path)
    else:
        path = generate_report_path(report_dir, "strategy_eval")
    return write_json_report(path, result.to_report())
