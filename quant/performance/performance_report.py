"""Build performance profile reports and recommendations."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any


class PerformanceReportBuilder:
    """Assemble deterministic profiling reports."""

    def __init__(self, report_dir: str | Path = "reports") -> None:
        self.report_dir = Path(report_dir)

    def build(
        self,
        parameters: dict[str, Any],
        tracker_summary: dict[str, Any],
        target_results: list[dict[str, Any]],
        database_profile: dict[str, Any],
        factor_store_profile: dict[str, Any],
        fundamental_profile: dict[str, Any],
    ) -> dict[str, Any]:
        slowest_modules = self._slowest_modules(target_results, tracker_summary)
        slowest_functions = tracker_summary.get("slowest_events") or []
        slowest_queries = database_profile.get("slowest_queries") or []
        recommendations = self._recommendations(slowest_modules, database_profile, factor_store_profile, fundamental_profile)
        report = {
            "metadata": {
                "report_type": "performance_profile",
                "generated_at": datetime.now().isoformat(timespec="seconds"),
                "release": "v0.40.0-performance-baseline-profiling",
                "measurement_only": True,
                "no_optimization": True,
                "no_semantic_changes": True,
            },
            "parameters": parameters,
            "summary": {
                "target_count": len(target_results),
                "total_runtime_seconds": tracker_summary.get("total_runtime_seconds", 0.0),
                "event_count": tracker_summary.get("event_count", 0),
            },
            "target_results": target_results,
            "runtime_breakdown": tracker_summary,
            "runtime_seconds": tracker_summary.get("total_runtime_seconds", 0.0),
            "call_counts": {
                category: values.get("count", 0)
                for category, values in (tracker_summary.get("by_category") or {}).items()
                if isinstance(values, dict)
            },
            "database_profile": database_profile,
            "factor_store_profile": factor_store_profile,
            "fundamental_lookup_profile": fundamental_profile,
            "slowest_modules": slowest_modules,
            "slowest_functions": slowest_functions,
            "slowest_queries": slowest_queries,
            "recommendations": recommendations,
            "interpretation_notes": [
                "This report measures runtime only; it does not optimize or change quant semantics.",
                "Recommendations are evidence-based candidates for future work, not implemented changes.",
                "SQLite, factor calculation, and report timings are best-effort instrumentation around existing engines.",
            ],
        }
        return self._write(report)

    def latest_profile(self) -> dict[str, Any] | None:
        reports = sorted(self.report_dir.glob("performance_profile_*.json"), key=lambda path: path.stat().st_mtime, reverse=True)
        if not reports:
            return None
        return json.loads(reports[0].read_text(encoding="utf-8"))

    def _write(self, report: dict[str, Any]) -> dict[str, Any]:
        self.report_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = self.report_dir / f"performance_profile_{stamp}.json"
        report = report | {"report_path": str(path)}
        path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
        summary_path = self.report_dir / "performance_profile_summary.md"
        summary_path.write_text(self._markdown(report), encoding="utf-8")
        report["summary_path"] = str(summary_path)
        path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
        return report

    @staticmethod
    def _slowest_modules(target_results: list[dict[str, Any]], tracker_summary: dict[str, Any]) -> list[dict[str, Any]]:
        rows = [
            {
                "module": result.get("target"),
                "runtime_seconds": result.get("runtime_seconds", 0.0),
                "status": result.get("status"),
                "details": result.get("details") or {},
            }
            for result in target_results
        ]
        for category, values in (tracker_summary.get("by_category") or {}).items():
            rows.append(
                {
                    "module": category,
                    "runtime_seconds": values.get("runtime_seconds", 0.0),
                    "status": "MEASURED",
                    "details": {"call_count": values.get("count", 0)},
                }
            )
        return sorted(rows, key=lambda item: float(item.get("runtime_seconds") or 0.0), reverse=True)[:20]

    @staticmethod
    def _recommendations(
        slowest_modules: list[dict[str, Any]],
        database_profile: dict[str, Any],
        factor_store_profile: dict[str, Any],
        fundamental_profile: dict[str, Any],
    ) -> list[str]:
        recommendations = []
        if slowest_modules:
            recommendations.append(f"Prioritize profiling follow-up for {slowest_modules[0]['module']}.")
        if (database_profile.get("runtime_seconds") or 0.0) > 0:
            recommendations.append("Measure whether database reads dominate factor evaluation before considering storage changes.")
        if (database_profile.get("query_count") or 0) > 100:
            recommendations.append("Consider a future cache or bulk-read design for repeated price history lookups.")
        if (factor_store_profile.get("save_runtime_seconds") or 0.0) > 1:
            recommendations.append("Review Factor Store save paths before larger all-factor validation runs.")
        if (fundamental_profile.get("lookup_count") or 0) > 0:
            recommendations.append("Consider semantic-preserving latest-as-of fundamental lookup caching in a future optimization release.")
        recommendations.extend(
            [
                "Do not add numba, multiprocessing, parquet, or vectorized rewrites until a dedicated optimization release.",
                "Use v0.40 results to scope v0.41 follow-up performance work.",
            ]
        )
        return recommendations

    @staticmethod
    def _markdown(report: dict[str, Any]) -> str:
        lines = [
            "# Performance Profile Summary",
            "",
            f"- Report: `{report['report_path']}`",
            f"- Total runtime seconds: {report['summary']['total_runtime_seconds']}",
            f"- Event count: {report['summary']['event_count']}",
            "",
            "## Slowest Modules",
        ]
        for row in report.get("slowest_modules", [])[:10]:
            lines.append(f"- {row.get('module')}: {row.get('runtime_seconds')}s status={row.get('status')}")
        lines.extend(["", "## Slowest Queries"])
        for row in report.get("slowest_queries", [])[:10]:
            lines.append(f"- {row.get('name')}: {row.get('runtime_seconds')}s calls={row.get('count')}")
        lines.extend(["", "## Recommendations"])
        for item in report.get("recommendations", []):
            lines.append(f"- {item}")
        return "\n".join(lines) + "\n"
