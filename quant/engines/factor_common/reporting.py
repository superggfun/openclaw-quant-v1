"""Shared factor report writing helpers."""

from __future__ import annotations

from pathlib import Path

from quant.reports.report_io import generate_report_path, write_json_report


def write_factor_report(report_dir: str | Path, prefix: str, factor: str, payload: dict) -> Path:
    return write_json_report(
        generate_report_path(report_dir, f"{prefix}_{factor}", unique=True),
        payload,
    )
