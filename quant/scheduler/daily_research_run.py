"""Daily research run orchestration."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from time import perf_counter
from typing import Any
from uuid import uuid4

from quant.scheduler.research_pipeline import ResearchPipeline
from quant.scheduler.scheduler_config import SchedulerConfig
from quant.strategy_dsl.strategy_registry import StrategyRegistry


class DailyResearchRun:
    """Execute the daily offline research pipeline."""

    def __init__(self, context, report_dir: str | Path = "reports") -> None:
        self.context = context
        self.report_dir = Path(report_dir)

    def run(
        self,
        config: SchedulerConfig | None = None,
        config_source: str = "defaults",
        config_path: str | None = None,
    ) -> dict[str, Any]:
        config = config or SchedulerConfig()
        pipeline = ResearchPipeline()
        started = datetime.now()
        timer = perf_counter()
        run_id = f"research-{started.strftime('%Y%m%d-%H%M%S')}-{uuid4().hex[:8]}"
        state: dict[str, Any] = {
            "generated_reports": [],
            "generated_visualizations": [],
            "agent_exports": [],
            "factor_results": [],
            "current_regime": None,
            "trade_sim": None,
        }

        pipeline.run_step("data_refresh", config.run_data_refresh, lambda: self._data_refresh(config, state))
        pipeline.run_step("data_coverage", config.run_data_coverage, lambda: self._data_coverage(config, state))
        pipeline.run_step("fundamental_coverage", config.run_fundamental_coverage, lambda: self._fundamental_coverage(config, state))
        pipeline.run_step("factor_evaluation", config.run_factor_eval, lambda: self._factor_evaluation(config, state))
        pipeline.run_step("factor_store_update", config.run_factor_store_update, lambda: self._factor_store_update(state))
        pipeline.run_step("regime_detection", config.run_regime_detection, lambda: self._regime_detection(state))
        pipeline.run_step("trade_simulation", config.run_trade_sim, lambda: self._trade_simulation(config, state))
        pipeline.run_step("strategy_run", config.run_strategy, lambda: self._strategy_run(config, state))
        pipeline.run_step("visualization", config.run_visualization, lambda: self._visualization(state))
        pipeline.run_step("agent_export", config.run_agent_export, lambda: self._agent_export(state))

        ended = datetime.now()
        status = self._overall_status(pipeline)
        warnings = self._warnings(pipeline)
        summary = self._summary(state, warnings)
        report = {
            "metadata": {
                "report_type": "research_run",
                "generated_at": ended.isoformat(timespec="seconds"),
                "offline_research_only": True,
                "live_trading": False,
                "broker_integration": False,
                "no_lookahead_preserved": True,
            },
            "run_id": run_id,
            "start_time": started.isoformat(timespec="seconds"),
            "end_time": ended.isoformat(timespec="seconds"),
            "duration_seconds": round(perf_counter() - timer, 6),
            "status": status,
            "config_source": config_source,
            "config_path": config_path,
            "pipeline_mode": config.pipeline_mode,
            "lightweight_default": bool(config.lightweight_default),
            "config": config.to_dict(),
            "pipeline_steps": pipeline.to_list(),
            "pipeline_step_summary": self._step_summary(pipeline),
            "enabled_pipeline_steps": self._enabled_steps(pipeline),
            "disabled_pipeline_steps": self._disabled_steps(pipeline),
            "skipped_steps": self._skipped_steps(pipeline),
            "warning_summary": self._warning_summary(warnings),
            "warnings": warnings,
            "generated_reports": state["generated_reports"],
            "generated_visualizations": state["generated_visualizations"],
            "agent_exports": state["agent_exports"],
            "generated_agent_exports": state["agent_exports"],
            "daily_research_summary": summary,
            "recommended_next_checks": self._recommended_next_checks(summary, warnings),
        }
        report_path = self._report_path()
        report["report_path"] = str(report_path)
        report["generated_reports"].append(str(report_path))
        self._write_report(report, report_path)
        return report

    def _data_refresh(self, config: SchedulerConfig, state: dict[str, Any]) -> dict[str, Any]:
        result = self.context.data_refresh_manager.refresh(
            config.symbols,
            start_date=config.data_start_date,
            end_date=config.data_end_date,
        )
        state["generated_reports"].append(result.report_path)
        warnings = []
        if result.summary.get("errors"):
            warnings.append(f"WARN_DATA_REFRESH_ERRORS: {result.summary['errors']}")
        return {
            "status": "WARNING" if warnings else "PASS",
            "warnings": warnings,
            "artifacts": [result.report_path],
            "summary": result.summary,
        }

    def _data_coverage(self, config: SchedulerConfig, state: dict[str, Any]) -> dict[str, Any]:
        result = self.context.data_quality_analyzer.coverage(config.symbols)
        state["generated_reports"].append(result["report_path"])
        missing = result.get("symbols_without_price_data", 0)
        warnings = [f"WARN_PRICE_COVERAGE_GAPS: {missing} symbols missing price data"] if missing else []
        return {
            "status": "WARNING" if warnings else "PASS",
            "warnings": warnings,
            "artifacts": [result["report_path"]],
            "summary": {
                "total_symbols": result.get("total_symbols"),
                "symbols_with_price_data": result.get("symbols_with_price_data"),
                "average_history_length": result.get("average_history_length"),
            },
        }

    def _fundamental_coverage(self, config: SchedulerConfig, state: dict[str, Any]) -> dict[str, Any]:
        result = self.context.fundamental_service.coverage(config.symbols, parameters={"symbols": config.symbols})
        state["generated_reports"].append(result["report_path"])
        coverage = result.get("coverage") or {}
        missing = coverage.get("symbols_missing_fundamental_data", 0)
        warnings = [f"WARN_FUNDAMENTAL_COVERAGE_GAPS: {missing} symbols missing fundamental data"] if missing else []
        return {
            "status": "WARNING" if warnings else "PASS",
            "warnings": warnings,
            "artifacts": [result["report_path"]],
            "summary": {
                "symbols_with_any_fundamental_data": coverage.get("symbols_with_any_fundamental_data"),
                "symbols_missing_fundamental_data": missing,
                "readiness_score": coverage.get("readiness_score"),
            },
        }

    def _factor_evaluation(self, config: SchedulerConfig, state: dict[str, Any]) -> dict[str, Any]:
        warnings: list[str] = []
        artifacts: list[str] = []
        factors = []
        for factor in config.factors:
            result = self.context.factor_evaluation.evaluate(
                factor=factor,
                forward_days=config.forward_days,
                universe=config.symbols,
            )
            saved = self.context.factor_store.save_factor_evaluation(result)
            if self.context.regime_history_store.latest() is None:
                self.context.regime_analytics.detect_and_save()
            self.context.regime_analytics.save_factor_evaluation_by_regime(result)
            artifacts.append(result.report_path)
            state["generated_reports"].append(result.report_path)
            warnings.extend(result.warnings)
            factors.append(
                {
                    "factor": factor,
                    "ic": result.ic_mean,
                    "rank_ic": result.rank_ic_mean,
                    "icir": result.icir,
                    "coverage": saved.get("coverage"),
                    "confidence": saved.get("confidence"),
                    "report_path": result.report_path,
                }
            )
        state["factor_results"] = factors
        return {
            "status": "WARNING" if warnings else "PASS",
            "warnings": warnings,
            "artifacts": artifacts,
            "summary": {"factor_count": len(factors), "factors": factors},
        }

    def _factor_store_update(self, state: dict[str, Any]) -> dict[str, Any]:
        synced = self.context.factor_registry_store.sync()
        rank = self.context.factor_store.rank_factors()
        state["generated_reports"].append(rank["report_path"])
        return {
            "status": "PASS",
            "artifacts": [rank["report_path"]],
            "summary": {
                "synced_factor_definitions": synced,
                "top_factors": [row.get("factor_name") for row in rank.get("top_factors", [])[:5]],
            },
        }

    def _regime_detection(self, state: dict[str, Any]) -> dict[str, Any]:
        report = self.context.regime_analytics.detect_and_save()
        state["generated_reports"].append(report["report_path"])
        current = report.get("current_regime") or {}
        state["current_regime"] = current.get("regime")
        return {
            "status": "WARNING" if report.get("warnings") else "PASS",
            "warnings": report.get("warnings") or [],
            "artifacts": [report["report_path"]],
            "summary": {
                "current_regime": current.get("regime"),
                "confidence": current.get("confidence"),
                "saved_rows": report.get("saved_rows"),
            },
        }

    def _trade_simulation(self, config: SchedulerConfig, state: dict[str, Any]) -> dict[str, Any]:
        result = self.context.trading_simulator.run(
            strategy="alpha",
            start=config.trade_sim_start,
            end=config.trade_sim_end,
            initial_cash=config.trade_sim_initial_cash,
            rebalance_frequency=config.trade_sim_rebalance_frequency,
            portfolio_method=config.trade_sim_portfolio_method,
            alpha_config=self._load_json_if_exists(config.alpha_config_path),
            cost_config=self._load_json_if_exists(config.cost_config_path),
            market_realism_config=self._load_json_if_exists(config.market_realism_config_path),
            symbols=config.symbols,
        )
        state["generated_reports"].append(result.report_path)
        state["trade_sim"] = result.to_report()
        return {
            "status": "WARNING" if result.warnings else "PASS",
            "warnings": result.warnings,
            "artifacts": [result.report_path],
            "summary": {
                "final_equity": result.final_equity,
                "total_return": result.total_return,
                "max_drawdown": result.max_drawdown,
                "total_cost": result.total_cost,
                "trade_count": result.trade_count,
            },
        }

    def _strategy_run(self, config: SchedulerConfig, state: dict[str, Any]) -> dict[str, Any]:
        report = StrategyRegistry(self.context).run(
            strategy=config.strategy_name,
            start=config.strategy_start,
            end=config.strategy_end,
            initial_cash=config.strategy_initial_cash,
            rebalance_frequency=config.strategy_rebalance_frequency,
        )
        state["generated_reports"].append(report["report_path"])
        trade_path = (report.get("artifacts") or {}).get("trade_sim_report_path")
        if trade_path:
            state["generated_reports"].append(trade_path)
        state["strategy_run"] = report
        return {
            "status": report.get("status", "PASS"),
            "warnings": report.get("warnings") or [],
            "artifacts": [path for path in [report.get("report_path"), trade_path] if path],
            "summary": {
                "strategy_name": report.get("strategy_name"),
                "strategy_version": report.get("strategy_version"),
                "trade_sim_summary": report.get("trade_sim_summary"),
            },
        }

    def _visualization(self, state: dict[str, Any]) -> dict[str, Any]:
        artifacts = []
        warnings = []
        for report_path in list(state["generated_reports"]):
            try:
                visual = self.context.report_visualizer.visualize_file(Path(report_path))
            except ValueError as exc:
                warnings.append(f"WARN_VISUALIZATION_SKIPPED: {Path(report_path).name}: {exc}")
                continue
            artifacts.append(visual.dashboard_path)
            artifacts.extend(chart.get("png_path") for chart in visual.charts if chart.get("png_path"))
            state["generated_visualizations"].append(visual.dashboard_path)
            state["generated_visualizations"].extend(chart.get("png_path") for chart in visual.charts if chart.get("png_path"))
            warnings.extend(visual.warnings)
        return {
            "status": "WARNING" if warnings else "PASS",
            "warnings": warnings,
            "artifacts": artifacts,
            "summary": {"visualization_count": len(artifacts)},
        }

    def _agent_export(self, state: dict[str, Any]) -> dict[str, Any]:
        artifacts = []
        warnings = []
        for report_path in list(state["generated_reports"]):
            try:
                output = self._agent_export_path(report_path)
                self.context.agent_exporter.export_file(
                    report_path=Path(report_path),
                    output_format="text",
                    output_path=output,
                )
            except Exception as exc:
                warnings.append(f"WARN_AGENT_EXPORT_SKIPPED: {Path(report_path).name}: {exc}")
                continue
            artifacts.append(str(output))
            state["agent_exports"].append(str(output))
        return {
            "status": "WARNING" if warnings else "PASS",
            "warnings": warnings,
            "artifacts": artifacts,
            "summary": {"agent_export_count": len(artifacts)},
        }

    def _summary(self, state: dict[str, Any], warnings: list[str]) -> dict[str, Any]:
        factor_results = state.get("factor_results") or []
        sorted_factors = sorted(
            factor_results,
            key=lambda row: ((row.get("icir") is not None), row.get("icir") or -999.0, row.get("factor") or ""),
            reverse=True,
        )
        weak_factors = [
            row.get("factor")
            for row in factor_results
            if row.get("ic") is not None and row.get("ic") < 0
        ]
        trade_sim = state.get("trade_sim") or {}
        return {
            "current_regime": state.get("current_regime"),
            "best_factors": [row.get("factor") for row in sorted_factors[:5]],
            "weak_factors": sorted(weak_factors),
            "coverage_warnings": [warning for warning in warnings if "COVERAGE" in warning or "DATA" in warning],
            "trade_sim_summary": {
                "final_equity": trade_sim.get("final_equity"),
                "total_return": trade_sim.get("total_return"),
                "max_drawdown": trade_sim.get("max_drawdown"),
                "total_cost": trade_sim.get("total_cost"),
            },
            "trade_sim_return": trade_sim.get("total_return"),
            "factor_stability_summary": {
                row.get("factor"): {
                    "ic": row.get("ic"),
                    "rank_ic": row.get("rank_ic"),
                    "icir": row.get("icir"),
                    "coverage": row.get("coverage"),
                    "confidence": row.get("confidence"),
                }
                for row in factor_results
            },
        }

    @staticmethod
    def _recommended_next_checks(summary: dict[str, Any], warnings: list[str]) -> list[str]:
        checks = ["review generated factor and regime reports"]
        if summary.get("coverage_warnings"):
            checks.append("improve data or fundamental coverage")
        if summary.get("weak_factors"):
            checks.append("inspect weak factor history before using in alpha")
        trade = summary.get("trade_sim_summary") or {}
        if trade.get("max_drawdown") is not None and trade["max_drawdown"] < -0.2:
            checks.append("review trade simulation drawdown and risk settings")
        if any("REGIME" in warning for warning in warnings):
            checks.append("review low-sample regime diagnostics")
        return sorted(set(checks))

    @staticmethod
    def _overall_status(pipeline: ResearchPipeline) -> str:
        statuses = {step.status for step in pipeline.steps if step.status != "SKIPPED"}
        if "FAIL" in statuses:
            return "FAIL"
        if "WARNING" in statuses:
            return "WARNING"
        if any(step.status == "SKIPPED" for step in pipeline.steps):
            return "WARNING"
        return "PASS"

    @staticmethod
    def _step_summary(pipeline: ResearchPipeline) -> dict[str, int]:
        summary = {"PASS": 0, "WARNING": 0, "FAIL": 0, "SKIPPED": 0}
        for step in pipeline.steps:
            summary[step.status] = summary.get(step.status, 0) + 1
        return summary

    @staticmethod
    def _enabled_steps(pipeline: ResearchPipeline) -> list[str]:
        return [step.name for step in pipeline.steps if step.status != "SKIPPED"]

    @staticmethod
    def _disabled_steps(pipeline: ResearchPipeline) -> list[str]:
        return [step.name for step in pipeline.steps if step.status == "SKIPPED"]

    @staticmethod
    def _skipped_steps(pipeline: ResearchPipeline) -> list[dict[str, Any]]:
        return [
            {
                "name": step.name,
                "status": step.status,
                "reason": step.summary.get("skip_reason", "disabled_by_config"),
            }
            for step in pipeline.steps
            if step.status == "SKIPPED"
        ]

    @staticmethod
    def _warning_summary(warnings: list[str]) -> dict[str, Any]:
        by_code: dict[str, int] = {}
        for warning in warnings:
            code = str(warning).split(":", 1)[0].strip()
            by_code[code] = by_code.get(code, 0) + 1
        return {
            "count": len(warnings),
            "by_code": dict(sorted(by_code.items())),
        }

    @staticmethod
    def _warnings(pipeline: ResearchPipeline) -> list[str]:
        output = []
        seen = set()
        for step in pipeline.steps:
            for warning in step.warnings:
                if warning not in seen:
                    output.append(warning)
                    seen.add(warning)
        return output

    @staticmethod
    def _load_json_if_exists(path: str) -> dict:
        file_path = Path(path)
        if not file_path.exists():
            return {}
        payload = json.loads(file_path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}

    def _agent_export_path(self, report_path: str) -> Path:
        source = Path(report_path)
        self.report_dir.mkdir(parents=True, exist_ok=True)
        return self.report_dir / f"agent_export_{source.stem}.txt"

    def _report_path(self) -> Path:
        self.report_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return self.report_dir / f"research_run_{timestamp}.json"

    @staticmethod
    def _write_report(report: dict[str, Any], path: Path) -> None:
        path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
