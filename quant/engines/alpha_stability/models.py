"""Shared data models for the Alpha Stability Audit framework."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class AuditModuleResult:
    """Standardised result envelope for every audit module."""

    module: str  # e.g. "universe_sensitivity"
    status: str  # "pass" | "warn" | "fail"
    score: float  # 0-100 normalised score
    details: dict  # module-specific data
    warnings: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "module": self.module,
            "status": self.status,
            "score": round(self.score, 2),
            "details": self.details,
            "warnings": list(self.warnings),
            "recommendations": list(self.recommendations),
        }
