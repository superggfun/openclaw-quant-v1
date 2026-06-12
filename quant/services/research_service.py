"""Research orchestration service boundary.

The scheduler remains the implementation owner in v0.34.0; this service module
provides a stable layered import path for future orchestration code.
"""

from quant.scheduler.research_scheduler import ResearchScheduler

__all__ = ["ResearchScheduler"]

