"""Configuration values for research validation."""

from __future__ import annotations

from dataclasses import dataclass


QUICK_FACTOR_PRIORITY = [
    "momentum_20d",
    "momentum_60d",
    "quality_price_proxy",
    "low_volatility_score",
    "fundamental_quality_score",
]
QUICK_UNIVERSE = ["SPY", "QQQ", "NVDA", "AAPL", "MSFT"]
QUICK_DEFAULT_START = "2024-01-01"
DEFAULT_FORWARD_DAYS = 20
DEFAULT_HOLDING_PERIOD = 20
REPORT_SCHEMA_VERSION = "research_validation.v1"
RESEARCH_VALIDATION_RELEASE = "research-validation"
REPORT_TITLE = "Research Validation Sprint"

REPORT_INTERPRETATION_NOTES = [
    "Quick mode is bounded smoke/research validation, not full-universe validation.",
    "Full mode uses all selected factors and default fold settings and can run much longer.",
    "Expanded universe evidence is passed internally by research-validation; default factor-eval CLI behavior is unchanged unless a caller supplies a custom universe through the engine API.",
    "Factor matrix cache is opt-in through --use-cache and does not change factor_eval metrics.",
    "Bulk matrix and parallel research validation are optional explicit acceleration paths.",
    "Parallel workers compute only; Factor Store writes stay in the main process.",
    "Gate PASS/WARNING/FAIL/REJECTED statuses are research quality controls, not trading authorization.",
    "Runtime bottlenecks are recorded only; this refactor does not add multiprocessing, numba, parquet, vectorized backtests, parameter tuning, or warning suppression.",
]

RECOMMENDED_PERFORMANCE_WORK = [
    "Add semantic-preserving caching around factor rows per signal_date.",
    "Cache latest fundamental-as-of lookups by symbol/date.",
    "Avoid writing intermediate reports when a caller requests in-memory validation only.",
    "Keep core engine semantics unchanged before considering parallelism or storage migrations.",
]


@dataclass(frozen=True)
class ResearchValidationConfig:
    quick_default_timeout_seconds: float = 120.0
    full_default_timeout_seconds: float = 3600.0
    quick_reserve_seconds: float = 15.0
    quick_default_start: str = QUICK_DEFAULT_START
    default_forward_days: int = DEFAULT_FORWARD_DAYS
    default_holding_period: int = DEFAULT_HOLDING_PERIOD
    schema_version: str = REPORT_SCHEMA_VERSION
    release: str = RESEARCH_VALIDATION_RELEASE
