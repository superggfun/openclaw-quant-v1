"""Regime analytics and factor-by-regime diagnostics."""

from __future__ import annotations

import math
from typing import Any

import pandas as pd

from quant.factors.store.factor_analytics import FactorAnalytics
from quant.factors.store.factor_store import FactorStore
from quant.engines.regime.regime_detector import RegimeDetector
from quant.engines.regime.regime_history import RegimeHistoryStore


class RegimeAnalytics:
    """Build regime reports and save factor-by-regime diagnostics."""

    low_sample_threshold = 30

    def __init__(self, detector: RegimeDetector, history_store: RegimeHistoryStore, factor_store: FactorStore) -> None:
        self.detector = detector
        self.history_store = history_store
        self.factor_store = factor_store

    def detect_and_save(self, start: str | None = None, end: str | None = None, write_report: bool = True) -> dict:
        observations = self.detector.detect(start=start, end=end)
        saved = self.history_store.save(observations)
        latest = observations[-1].to_dict() if observations else None
        counts = self._counts([obs.to_dict() for obs in observations])
        warnings = self._low_sample_warnings(counts)
        if not observations:
            warnings.append("WARN_NO_REGIME_OBSERVATIONS")
        report = {
            "metadata": {"report_type": "regime_detection", "generated_at": self.history_store.now()},
            "benchmark": self.detector.benchmark,
            "parameters": {
                "start": start,
                "end": end,
                "long_window": self.detector.long_window,
                "volatility_window": self.detector.volatility_window,
                "trend_window": self.detector.trend_window,
            },
            "current_regime": latest,
            "observations": [obs.to_dict() for obs in observations],
            "regime_counts": counts,
            "saved_rows": saved,
            "no_lookahead": True,
            "warnings": warnings,
            "interpretation_notes": [
                "Regime detection uses deterministic rules and stored daily prices only.",
                "Regime diagnostics are not trading instructions or investment advice.",
            ],
        }
        if not write_report:
            report["report_path"] = ""
            return report
        return self.history_store.write_report(report, "regime_detection")

    def history_report(self, limit: int = 30, regime: str | None = None) -> dict:
        rows = self.history_store.history(limit=limit, regime=regime)
        counts = self.history_store.counts()
        report = {
            "metadata": {"report_type": "regime_history", "generated_at": self.history_store.now()},
            "limit": limit,
            "regime_filter": regime,
            "current_regime": self.history_store.latest(),
            "history": rows,
            "regime_counts": counts,
            "warnings": ([] if rows else ["WARN_REGIME_HISTORY_EMPTY"]) + self._low_sample_warnings(counts),
            "interpretation_notes": ["Regime history is persisted diagnostic state and does not alter strategies."],
        }
        return self.history_store.write_report(report, "regime_history")

    def regime_report(self) -> dict:
        current = self.history_store.latest()
        with self.factor_store.connect() as connection:
            factor_rows = self.factor_store._fetch_all(
                connection,
                """
                SELECT factor_name, regime, AVG(ic) AS ic, AVG(rank_ic) AS rank_ic,
                       AVG(icir) AS icir, AVG(coverage) AS coverage, AVG(stability) AS stability,
                       COUNT(*) AS samples
                FROM factor_regime_history
                GROUP BY factor_name, regime
                ORDER BY regime, factor_name
                """,
                [],
            )
        by_regime: dict[str, list[dict]] = {}
        for row in factor_rows:
            by_regime.setdefault(row["regime"], []).append(row)
        counts = self.history_store.counts()
        report = {
            "metadata": {"report_type": "regime_report", "generated_at": self.history_store.now()},
            "current_regime": current,
            "regime_counts": counts,
            "factor_performance_by_regime": by_regime,
            "warnings": ([] if current else ["WARN_REGIME_HISTORY_EMPTY"]) + self._low_sample_warnings(counts),
            "interpretation_notes": [
                "Factor-by-regime metrics are diagnostics from saved factor evaluations.",
                "They do not disable factors or generate orders.",
            ],
        }
        return self.history_store.write_report(report, "regime_report")

    def regime_rank(self, limit: int = 10, write_report: bool = True) -> dict:
        report = self.factor_store.factor_regime_rank(limit=limit)
        current = self.history_store.latest()
        report["current_regime"] = current
        counts = self.history_store.counts()
        report["regime_counts"] = counts
        self._apply_regime_sample_support(report, counts)
        report["warnings"] = list(report.get("warnings") or []) + self._low_sample_warnings(counts)
        if not write_report:
            return report | {"report_path": ""}
        return self.history_store.write_report(report, "regime_rank")

    def save_factor_evaluation_by_regime(self, result) -> dict:
        rows = self.factor_regime_rows_from_evaluation(result)
        saved = self.factor_store.save_factor_regime_history(result.factor, rows, report_path=result.report_path)
        return saved | {"regime_rows": rows}

    def save_factor_backtest_by_regime(self, result) -> dict:
        rows = self.factor_regime_rows_from_backtest(result)
        saved = self.factor_store.save_factor_regime_history(result.factor, rows, report_path=result.report_path)
        return saved | {"regime_rows": rows}

    def factor_regime_rows_from_evaluation(self, result) -> list[dict]:
        observations = []
        for obs in result.observations:
            regime = self.history_store.regime_for_date(obs.signal_date)
            if not regime:
                continue
            observations.append(
                {
                    "regime": regime,
                    "factor_value": obs.factor_value,
                    "future_return": obs.future_return,
                }
            )
        return self._factor_rows(result.factor, observations, value_key="factor_value", return_key="future_return")

    def factor_regime_rows_from_backtest(self, result) -> list[dict]:
        observations = []
        for period in result.periods:
            regime = self.history_store.regime_for_date(period.signal_date)
            if not regime:
                continue
            observations.append({"regime": regime, "spread_return": period.long_short_return})
        rows = []
        for regime, items in self._group(observations).items():
            returns = [self._num(item.get("spread_return")) for item in items]
            clean = [value for value in returns if value is not None]
            if not clean:
                continue
            mean = sum(clean) / len(clean)
            std = self._std(clean)
            rows.append(
                {
                    "factor_name": result.factor,
                    "regime": regime,
                    "ic": mean,
                    "rank_ic": None,
                    "icir": mean / std if std and std > 0 else None,
                    "coverage": len(clean) / max(len(result.periods), 1),
                    "stability": FactorAnalytics.consistency_score(clean),
                    "samples": len(clean),
                    "metric_note": "factor_backtest spread-return proxy stored in ic field for regime diagnostics",
                }
            )
        return rows

    def _factor_rows(self, factor: str, observations: list[dict], value_key: str, return_key: str) -> list[dict]:
        rows = []
        total = len(observations)
        for regime, items in self._group(observations).items():
            values = [self._num(item.get(value_key)) for item in items]
            returns = [self._num(item.get(return_key)) for item in items]
            pairs = [(v, r) for v, r in zip(values, returns) if v is not None and r is not None]
            if len(pairs) < 2:
                continue
            frame = pd.DataFrame(pairs, columns=["factor", "future_return"])
            ic = self._corr(frame["factor"], frame["future_return"], method="pearson")
            rank_ic = self._corr(frame["factor"], frame["future_return"], method="spearman")
            icir = None
            if ic is not None:
                icir = ic / max(float(frame["future_return"].std(ddof=1) or 0.0), 1e-12)
            rows.append(
                {
                    "factor_name": factor,
                    "regime": regime,
                    "ic": ic,
                    "rank_ic": rank_ic,
                    "icir": icir,
                    "coverage": len(pairs) / max(total, 1),
                    "stability": self._supported_stability(FactorAnalytics.consistency_score([ic, rank_ic]), len(pairs)),
                    "samples": len(pairs),
                    "warnings": self._low_factor_sample_warnings(regime, len(pairs)),
                }
            )
        return rows

    def _supported_stability(self, stability: float | None, samples: int) -> float | None:
        if stability is None:
            return None
        support = min(max(samples / self.low_sample_threshold, 0.0), 1.0)
        return round(stability * support, 6)

    def _apply_regime_sample_support(self, report: dict, counts: dict[str, int]) -> None:
        for section in ("best_by_regime", "worst_by_regime"):
            by_regime = report.get(section) or {}
            for regime, rows in by_regime.items():
                support = min(max(float(counts.get(regime, 0)) / self.low_sample_threshold, 0.0), 1.0)
                for row in rows:
                    raw = row.get("health_score")
                    row["raw_health_score"] = raw
                    row["regime_sample_support"] = round(support, 6)
                    if raw is not None:
                        row["health_score"] = round(float(raw) * support, 6)

    @staticmethod
    def _group(items: list[dict]) -> dict[str, list[dict]]:
        grouped: dict[str, list[dict]] = {}
        for item in items:
            grouped.setdefault(str(item.get("regime") or "UNKNOWN"), []).append(item)
        return grouped

    @staticmethod
    def _counts(items: list[dict]) -> dict[str, int]:
        counts: dict[str, int] = {}
        for item in items:
            regime = str(item.get("regime") or "UNKNOWN")
            counts[regime] = counts.get(regime, 0) + 1
        return counts

    @classmethod
    def _low_sample_warnings(cls, counts: dict[str, int]) -> list[str]:
        return [
            f"WARN_LOW_REGIME_SAMPLE: {regime} has {count} samples below threshold {cls.low_sample_threshold}"
            for regime, count in sorted(counts.items())
            if regime != "UNKNOWN" and 0 < count < cls.low_sample_threshold
        ]

    @classmethod
    def _low_factor_sample_warnings(cls, regime: str, samples: int) -> list[str]:
        if samples < cls.low_sample_threshold:
            return [f"WARN_LOW_REGIME_SAMPLE: {regime} factor sample count {samples} below threshold {cls.low_sample_threshold}"]
        return []

    @staticmethod
    def _corr(left: pd.Series, right: pd.Series, method: str) -> float | None:
        left_values = pd.to_numeric(left, errors="coerce")
        right_values = pd.to_numeric(right, errors="coerce")
        if method == "spearman":
            left_values = left_values.rank(method="average")
            right_values = right_values.rank(method="average")
            method = "pearson"
        value = left_values.corr(right_values, method=method)
        try:
            number = float(value)
            return number if math.isfinite(number) else None
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _std(values: list[float]) -> float | None:
        if len(values) < 2:
            return None
        mean = sum(values) / len(values)
        variance = sum((value - mean) ** 2 for value in values) / (len(values) - 1)
        return math.sqrt(variance)

    @staticmethod
    def _num(value: Any) -> float | None:
        try:
            number = float(value)
            return number if math.isfinite(number) else None
        except (TypeError, ValueError):
            return None
