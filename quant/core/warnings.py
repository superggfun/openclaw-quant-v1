"""Stable warning-code helpers shared by layered modules."""

from __future__ import annotations


def warning_code(message: str) -> str:
    """Return the stable warning code prefix from a warning message."""
    return str(message).split(":", 1)[0].strip()


def summarize_warnings(warnings: list[str]) -> dict[str, int]:
    """Count warnings by stable code prefix."""
    counts: dict[str, int] = {}
    for warning in warnings:
        code = warning_code(warning)
        counts[code] = counts.get(code, 0) + 1
    return dict(sorted(counts.items()))

