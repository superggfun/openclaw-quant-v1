"""Shared helpers for agent export builders."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from quant.reports.agent_export.models import AgentExport


class AgentExportContext:
    """Create normalized AgentExport objects and shared diagnostics."""

    def base_export(
        self,
        report_type: str,
        generated_from: str,
        summary: str,
        key_metrics: dict[str, Any] | None = None,
        key_findings: list[str] | None = None,
        warnings: list[str] | None = None,
        recommended_next_steps: list[str] | None = None,
        action_candidates: list[str] | None = None,
        data_quality_notes: list[str] | None = None,
    ) -> AgentExport:
        return AgentExport(
            report_type=report_type,
            generated_from=generated_from,
            summary=summary,
            key_metrics=key_metrics or {},
            key_findings=dedupe(key_findings or []),
            warnings=dedupe(warnings or []),
            recommended_next_steps=dedupe(recommended_next_steps or []),
            action_candidates=dedupe(action_candidates or []),
            data_quality_notes=dedupe(data_quality_notes or []),
            visual_summary_paths=visual_summary_paths(generated_from),
            visualization_paths=visualization_paths(generated_from),
        )

    def performance_warnings(self, total_return: Any, sharpe: Any, drawdown: Any) -> list[str]:
        warnings = []
        total = num(total_return)
        sharpe_value = num(sharpe)
        drawdown_value = num(drawdown)
        if drawdown_value is not None and drawdown_value <= -0.30:
            warnings.append("WARN_EXTREME_DRAWDOWN")
        if total is not None and sharpe_value is not None and total < 0 and sharpe_value > 0:
            warnings.append("WARN_SHARPE_RETURN_MISMATCH")
        return warnings

    def exclusion_notes(self, report: dict[str, Any]) -> list[str]:
        excluded = report.get("excluded_symbols") or []
        reasons = report.get("exclusion_reasons") or {}
        if not excluded:
            return []
        notes = [f"excluded_symbols: {len(excluded)}"]
        for symbol in list(excluded)[:5]:
            reason = reasons.get(symbol) if isinstance(reasons, dict) else None
            notes.append(f"{symbol}: {reason or 'excluded'}")
        return notes


def best_decay_horizon(decay: dict[str, Any]) -> str | None:
    best = None
    best_value = None
    for horizon, values in decay.items():
        value = values.get("ic") if isinstance(values, dict) else None
        number = num(value)
        if number is None:
            continue
        if best_value is None or number > best_value:
            best = horizon
            best_value = number
    return best


def stringify(value: Any) -> str:
    if isinstance(value, float):
        return f"{value:.6g}"
    if isinstance(value, (dict, list)):
        return json.dumps(value, sort_keys=True)
    return str(value)


def estimate_tokens(value: Any) -> int:
    text = json.dumps(value, default=str, sort_keys=True)
    return max(1, int(len(text.split()) * 1.3))


def format_pct(value: Any) -> str:
    number = num(value)
    return "N/A" if number is None else f"{number * 100:.2f}%"


def round_mapping(values: dict[str, Any]) -> dict[str, Any]:
    output = {}
    for key in sorted(values):
        number = num(values[key])
        output[key] = round(number, 6) if number is not None else values[key]
    return output


def clean_warnings(warnings: Any) -> list[str]:
    if not warnings:
        return []
    cleaned = []
    if isinstance(warnings, list):
        for warning in warnings:
            if isinstance(warning, dict):
                cleaned.append(str(warning.get("code") or warning.get("reason") or warning))
            else:
                text = str(warning)
                cleaned.append(text if text.startswith("WARN_") else f"SOURCE_WARNING: {text}")
    else:
        text = str(warnings)
        cleaned.append(text if text.startswith("WARN_") else f"SOURCE_WARNING: {text}")
    return cleaned


def visualization_paths(generated_from: str) -> list[str]:
    if generated_from == "<memory>":
        return []
    report_path = Path(generated_from)
    charts_dir = report_path.parent / "charts"
    if not charts_dir.exists():
        return []
    paths = []
    for extension in ("png", "svg", "html"):
        paths.extend(charts_dir.glob(f"{report_path.stem}_*.{extension}"))
    return sorted(str(path) for path in paths if not path.name.endswith("_dashboard.png"))


def visual_summary_paths(generated_from: str) -> list[str]:
    if generated_from == "<memory>":
        return []
    report_path = Path(generated_from)
    charts_dir = report_path.parent / "charts"
    if not charts_dir.exists():
        return []
    return sorted(str(path) for path in charts_dir.glob(f"{report_path.stem}_visual_summary.json"))


def dedupe(values: list[str]) -> list[str]:
    output = []
    seen = set()
    for value in values:
        text = str(value)
        if text and text not in seen:
            output.append(text)
            seen.add(text)
    return output


def num(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None
