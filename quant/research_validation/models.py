"""Data models for research validation orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ValidationStep:
    name: str
    category: str
    target: str
    status: str
    runtime_seconds: float
    report_path: str | None = None
    warnings: list[str] | None = None
    error: str | None = None
    details: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "category": self.category,
            "target": self.target,
            "status": self.status,
            "runtime_seconds": round(self.runtime_seconds, 6),
            "report_path": self.report_path,
            "warnings": list(self.warnings or []),
            "error": self.error,
            "details": self.details or {},
        }
