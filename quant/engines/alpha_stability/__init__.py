"""Alpha Stability Audit framework.

Provides robustness diagnostics for factor-based alpha signals:
universe sensitivity, transaction cost sensitivity, turnover audit,
decile analysis, IC decay analysis, and a composite stability score.
"""

from __future__ import annotations

from quant.engines.alpha_stability.models import AuditModuleResult
from quant.engines.alpha_stability.orchestrator import (
    AlphaStabilityAudit,
    AlphaStabilityAuditResult,
)
from quant.engines.alpha_stability.universe_sensitivity import run_universe_sensitivity
from quant.engines.alpha_stability.cost_sensitivity import run_cost_sensitivity
from quant.engines.alpha_stability.turnover_audit import run_turnover_audit
from quant.engines.alpha_stability.decile_analysis import run_decile_analysis
from quant.engines.alpha_stability.ic_decay import run_ic_decay
from quant.engines.alpha_stability.stability_score import compute_stability_score

__all__ = [
    "AlphaStabilityAudit",
    "AlphaStabilityAuditResult",
    "AuditModuleResult",
    "compute_stability_score",
    "run_cost_sensitivity",
    "run_decile_analysis",
    "run_ic_decay",
    "run_turnover_audit",
    "run_universe_sensitivity",
]
