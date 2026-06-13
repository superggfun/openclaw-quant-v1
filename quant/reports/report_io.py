"""Shared report path and JSON writing helpers."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4


def report_timestamp(fmt: str = "%Y%m%d_%H%M%S") -> str:
    return datetime.now().strftime(fmt)


def generate_report_path(
    report_dir: str | Path,
    prefix: str,
    *,
    suffix: str = ".json",
    unique: bool = False,
    timestamp_format: str = "%Y%m%d_%H%M%S",
) -> Path:
    output_dir = Path(report_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = f"{prefix}_{report_timestamp(timestamp_format)}"
    if unique:
        stem = f"{stem}_{uuid4().hex[:8]}"
    return output_dir / f"{stem}{suffix}"


def write_json_report(
    path: str | Path,
    payload: Any,
    *,
    sort_keys: bool = False,
    trailing_newline: bool = False,
) -> Path:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2, sort_keys=sort_keys)
    if trailing_newline:
        text += "\n"
    output_path.write_bytes(text.encode("utf-8"))
    return output_path


def write_report_payload(
    report_dir: str | Path,
    prefix: str,
    payload: Any,
    *,
    sort_keys: bool = False,
    unique: bool = False,
) -> Path:
    return write_json_report(
        generate_report_path(report_dir, prefix, unique=unique),
        payload,
        sort_keys=sort_keys,
    )
