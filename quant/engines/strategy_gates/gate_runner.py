"""Strategy Evaluation Gate orchestration."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from quant.config import DEFAULT_SYMBOLS
from quant.data.fundamental.fundamental_service import FundamentalService
from quant.data.layer.data_quality import DataQualityAnalyzer
from quant.strategy_dsl.strategy_definition import StrategyDefinition
from quant.strategy_dsl.strategy_registry import StrategyRegistry
from quant.engines.strategy_gates.gate_models import FAIL, PASS, WARNING, GateConfig, GateResult, final_status
from quant.engines.strategy_gates.gate_registry import GateRegistry
from quant.engines.strategy_gates.gate_report import StrategyGateReportStore
from quant.engines.strategy_gates.gate_rules import fail_gate, num, pass_gate, ratio, reject_gate, warn_gate
from quant.engines.strategy_gates.gate_specs import GateRunInput, GateSpec


DEFAULT_GATE_CONFIG_PATH = Path("examples/strategy_gate_config.json")


class StrategyGateRunner:
    """Run deterministic offline gates against a Strategy DSL definition."""

    def __init__(self, context, strategy_dir: str | Path = "strategies", report_dir: str | Path = "reports") -> None:
        self.context = context
        self.strategy_dir = Path(strategy_dir)
        self.report_dir = Path(report_dir)
        self.report_store = StrategyGateReportStore(report_dir)
        self.registry = GateRegistry()

    def run(
        self,
        strategy: str | None = None,
        file: str | Path | None = None,
        config_path: str | Path | None = DEFAULT_GATE_CONFIG_PATH,
        strategy_run_report: dict[str, Any] | None = None,
        write_report: bool = True,
    ) -> dict[str, Any]:
        config = self._load_config(config_path)
        definition, source_path = StrategyRegistry(self.context, strategy_dir=self.strategy_dir).load_strategy(strategy, file)
        validation = StrategyRegistry(self.context, strategy_dir=self.strategy_dir).validate(strategy=strategy, file=file)
        symbols = self._symbols(definition)
        gate_input = GateRunInput(
            validation=validation,
            symbols=symbols,
            definition=definition,
            config=config,
            strategy_run_report=strategy_run_report,
            write_report=write_report,
        )
        gate_results = [self._execute_gate(spec, gate_input) for spec in self.registry.specs()]
        statuses = [gate.status for gate in gate_results]
        overall = final_status(statuses)
        warnings = self._dedupe([warning for gate in gate_results for warning in gate.warnings])
        rejection_reasons = self._dedupe([reason for gate in gate_results for reason in gate.rejection_reasons])
        report = {
            "metadata": {
                "report_type": "strategy_gate",
                "generated_at": datetime.now().isoformat(timespec="seconds"),
                "offline_research_only": True,
                "live_trading": False,
                "broker_integration": False,
                "no_lookahead_preserved": True,
            },
            "strategy_name": definition.name,
            "strategy_version": definition.version,
            "strategy_file": str(source_path),
            "source_path": str(source_path),
            "gate_config_path": str(config_path) if config_path else "<defaults>",
            "gate_config": config.to_dict(),
            "available_gates": self.registry.list_gates(),
            "overall_status": overall,
            "status": overall,
            "rejection_reasons": rejection_reasons,
            "gate_results": [gate.to_dict() for gate in gate_results],
            "evidence_summary": self._evidence_summary(gate_results),
            "input_reports": self._input_reports(strategy_run_report),
            "generated_reports": [],
            "warnings": warnings,
            "no_lookahead": True,
            "no_lookahead_notes": [
                "Strategy Gates read persisted reports, Factor Store history, and offline simulation outputs only.",
                "Fundamental factor evidence remains governed by report_date <= signal_date in the underlying engines.",
                "Gate evaluation cannot override Strategy DSL no-lookahead validation or enable live execution.",
            ],
            "interpretation_notes": [
                "Gate status is quality control for offline research readiness, not a return guarantee.",
                "REJECTED means the strategy failed deterministic validation or hard risk controls.",
                "WARNING means additional evidence is needed before relying on the research result.",
            ],
            "recommended_next_checks": self._recommended_next_checks(gate_results),
        }
        if write_report:
            report = self.report_store.write(report)
        return report

    def latest_report(self) -> dict[str, Any]:
        return self.report_store.latest()

    def _execute_gate(self, spec: GateSpec, gate_input: GateRunInput) -> GateResult:
        handler = getattr(self, spec.handler_name)
        return handler(gate_input)

    def _schema_gate(self, gate_input: GateRunInput) -> GateResult:
        validation = gate_input.validation
        config = gate_input.config
        evidence = {
            "valid": bool(validation.get("valid")),
            "errors": validation.get("errors") or [],
            "warnings": validation.get("warnings") or [],
            "normalized_factor_weights": (validation.get("gates") or {}).get("normalized_factor_weights", {}),
        }
        if not validation.get("valid"):
            status = reject_gate if config.reject_on_schema_error else fail_gate
            return status(
                "schema_validation",
                "DSL",
                "STRATEGY_SCHEMA_INVALID",
                "Strategy DSL validation failed.",
                evidence,
                evidence["errors"],
            )
        if evidence["warnings"]:
            return warn_gate(
                "schema_validation",
                "DSL",
                "WARN_STRATEGY_SCHEMA_WARNINGS",
                "Strategy DSL validation passed with warnings.",
                evidence,
                list(evidence["warnings"]),
            )
        return pass_gate("schema_validation", "DSL", "Strategy DSL validation passed.", evidence)

    def _data_quality_gate(self, gate_input: GateRunInput) -> GateResult:
        symbols = gate_input.symbols
        definition = gate_input.definition
        config = gate_input.config
        write_report = gate_input.write_report
        if write_report:
            data_quality = DataQualityAnalyzer(self.context.price_store, self.context.metadata_store, report_dir=self.report_dir)
            fundamentals = FundamentalService(self.context.fundamental_store, report_dir=self.report_dir)
        else:
            data_quality = self.context.data_quality_analyzer
            fundamentals = self.context.fundamental_service
        price_coverage = data_quality.coverage(symbols, write_report=write_report)
        fundamental_coverage = fundamentals.coverage(
            symbols,
            parameters={"source": "strategy_gate", "symbols": symbols},
            write_report=write_report,
        )
        price_ratio = ratio(price_coverage.get("symbols_with_price_data"), price_coverage.get("total_symbols"))
        f_summary = fundamental_coverage.get("summary") or {}
        fundamental_ratio = ratio(f_summary.get("symbols_with_any_fundamental_data"), f_summary.get("total_symbols"))
        required_fundamental = any(str(item.get("name", "")).startswith("fundamental_") for item in definition.factors)
        evidence = {
            "symbols": symbols,
            "price_coverage": round(price_ratio, 6),
            "fundamental_coverage": round(fundamental_ratio, 6),
            "price_report_path": price_coverage.get("report_path"),
            "fundamental_report_path": fundamental_coverage.get("report_path"),
            "fundamental_required": required_fundamental,
        }
        warnings = []
        if price_ratio < config.minimum_price_coverage:
            warnings.append("WARN_LOW_PRICE_COVERAGE")
        if required_fundamental and fundamental_ratio < config.minimum_fundamental_coverage:
            warnings.append("WARN_LOW_FUNDAMENTAL_COVERAGE")
        if warnings:
            return warn_gate("data_quality", "DATA", warnings[0], "Data coverage is below configured gate thresholds.", evidence, warnings)
        return pass_gate("data_quality", "DATA", "Data coverage passed configured thresholds.", evidence)

    def _factor_history_gate(self, gate_input: GateRunInput) -> GateResult:
        definition = gate_input.definition
        config = gate_input.config
        rows = []
        warnings = []
        for factor in self._factor_names(definition):
            history = self.context.factor_store.factor_history(factor=factor, limit=20, write_report=False)
            evaluations = history.get("evaluation_history") or []
            latest = evaluations[0] if evaluations else {}
            coverage = num(latest.get("coverage"))
            ic = num(latest.get("ic"))
            rank_ic = num(latest.get("rank_ic"))
            icir = num(latest.get("icir"))
            factor_warnings = []
            if len(evaluations) < config.minimum_factor_history_count:
                factor_warnings.append("WARN_LOW_FACTOR_HISTORY")
            if coverage is None or coverage < config.minimum_factor_coverage:
                factor_warnings.append("WARN_LOW_FACTOR_COVERAGE")
            if ic is not None and ic < config.minimum_ic:
                factor_warnings.append("WARN_WEAK_IC")
            if rank_ic is not None and rank_ic < config.minimum_rank_ic:
                factor_warnings.append("WARN_WEAK_RANK_IC")
            if icir is not None and icir < config.minimum_icir:
                factor_warnings.append("WARN_WEAK_ICIR")
            warnings.extend(f"{code}: {factor}" for code in factor_warnings)
            rows.append(
                {
                    "factor": factor,
                    "history_count": len(evaluations),
                    "ic": ic,
                    "rank_ic": rank_ic,
                    "icir": icir,
                    "coverage": coverage,
                    "warnings": factor_warnings,
                }
            )
        evidence = {"factors": rows}
        if warnings:
            return warn_gate("factor_history", "FACTORS", "WARN_FACTOR_EVIDENCE_WEAK", "Factor Store evidence is incomplete or weak.", evidence, warnings)
        return pass_gate("factor_history", "FACTORS", "Factor Store evidence passed configured thresholds.", evidence)

    def _walk_forward_gate(self, gate_input: GateRunInput) -> GateResult:
        definition = gate_input.definition
        config = gate_input.config
        rows = []
        warnings = []
        for factor in self._factor_names(definition):
            history = self.context.factor_store.factor_history(factor=factor, limit=50, write_report=False)
            folds = history.get("walk_forward_history") or []
            test_sharpes = [value for value in (num(row.get("test_sharpe")) for row in folds) if value is not None]
            train_sharpes = [value for value in (num(row.get("train_sharpe")) for row in folds) if value is not None]
            avg_test = sum(test_sharpes) / len(test_sharpes) if test_sharpes else None
            avg_train = sum(train_sharpes) / len(train_sharpes) if train_sharpes else None
            gap = None if avg_test is None or avg_train is None else avg_train - avg_test
            factor_warnings = []
            if len(folds) < config.minimum_walk_forward_folds:
                factor_warnings.append("WARN_LOW_WALK_FORWARD_FOLDS")
            if avg_test is not None and avg_test < config.minimum_test_sharpe:
                factor_warnings.append("WARN_LOW_TEST_SHARPE")
            if gap is not None and gap > config.maximum_train_test_gap:
                factor_warnings.append("WARN_TRAIN_TEST_GAP")
            warnings.extend(f"{code}: {factor}" for code in factor_warnings)
            rows.append(
                {
                    "factor": factor,
                    "fold_count": len(folds),
                    "average_train_sharpe": avg_train,
                    "average_test_sharpe": avg_test,
                    "train_test_gap": gap,
                    "warnings": factor_warnings,
                }
            )
        evidence = {"factors": rows}
        if warnings:
            return warn_gate("walk_forward", "VALIDATION", "WARN_WALK_FORWARD_EVIDENCE_WEAK", "Walk-forward evidence is incomplete or weak.", evidence, warnings)
        return pass_gate("walk_forward", "VALIDATION", "Walk-forward evidence passed configured thresholds.", evidence)

    def _regime_gate(self, gate_input: GateRunInput) -> GateResult:
        definition = gate_input.definition
        config = gate_input.config
        report = self.context.factor_store.factor_regime_rank(limit=20)
        regime_counts = {}
        try:
            regime_counts = self.context.regime_history_store.counts()
        except Exception:
            regime_counts = {}
        low_samples = {
            regime: count
            for regime, count in regime_counts.items()
            if int(count or 0) < config.minimum_regime_sample
        }
        missing = []
        by_regime = report.get("best_by_regime") or {}
        for factor in self._factor_names(definition):
            if not any(any(row.get("factor_name") == factor for row in rows) for rows in by_regime.values()):
                missing.append(factor)
        evidence = {
            "regime_counts": regime_counts,
            "low_sample_regimes": low_samples,
            "missing_factor_regime_history": missing,
            "regime_enabled": bool(definition.regime.get("enabled")),
        }
        warnings = []
        if low_samples:
            warnings.append("WARN_LOW_REGIME_SAMPLE")
        if definition.regime.get("enabled") and missing:
            warnings.append("WARN_MISSING_FACTOR_REGIME_HISTORY")
        if warnings:
            return warn_gate("regime_coverage", "REGIME", warnings[0], "Regime diagnostics have limited sample support.", evidence, warnings)
        return pass_gate("regime_coverage", "REGIME", "Regime diagnostics passed configured thresholds.", evidence)

    def _trading_simulation_gate(self, gate_input: GateRunInput) -> GateResult:
        config = gate_input.config
        summary = (gate_input.strategy_run_report or {}).get("trade_sim_summary") or {}
        if not summary:
            evidence = {"available": False}
            return warn_gate(
                "trading_simulation",
                "SIMULATION",
                "WARN_NO_TRADING_SIMULATION_EVIDENCE",
                "No strategy-run/trade-sim report was provided to the gate runner.",
                evidence,
                ["WARN_NO_TRADING_SIMULATION_EVIDENCE"],
            )
        drawdown = abs(num(summary.get("max_drawdown")) or 0.0)
        turnover = num(summary.get("turnover"))
        total_cost = num(summary.get("total_cost")) or 0.0
        final_equity = num(summary.get("final_equity")) or 0.0
        cost_drag = total_cost / final_equity if final_equity > 0 else None
        evidence = {
            "final_equity": final_equity,
            "total_return": summary.get("total_return"),
            "max_drawdown_abs": drawdown,
            "turnover": turnover,
            "total_cost": total_cost,
            "cost_drag": cost_drag,
        }
        failures = []
        warnings = []
        if drawdown > config.maximum_drawdown:
            failures.append("REJECT_MAX_DRAWDOWN")
        if turnover is not None and turnover > config.maximum_turnover:
            warnings.append("WARN_HIGH_TURNOVER")
        if cost_drag is not None and cost_drag > config.maximum_cost_drag:
            warnings.append("WARN_HIGH_COST_DRAG")
        if failures:
            return reject_gate("trading_simulation", "SIMULATION", failures[0], "Trading simulation breached hard risk controls.", evidence, failures)
        if warnings:
            return warn_gate("trading_simulation", "SIMULATION", warnings[0], "Trading simulation raised robustness warnings.", evidence, warnings)
        return pass_gate("trading_simulation", "SIMULATION", "Trading simulation passed configured thresholds.", evidence)

    def _complexity_gate(self, gate_input: GateRunInput) -> GateResult:
        definition = gate_input.definition
        config = gate_input.config
        parameter_count = self._parameter_count(definition)
        factor_count = len(definition.factors)
        evidence = {"factor_count": factor_count, "parameter_count": parameter_count}
        warnings = []
        if factor_count > config.maximum_factor_count:
            warnings.append("WARN_HIGH_FACTOR_COUNT")
        if parameter_count > config.maximum_parameter_count:
            warnings.append("WARN_HIGH_PARAMETER_COUNT")
        if warnings:
            return warn_gate("complexity", "ROBUSTNESS", warnings[0], "Strategy complexity exceeds configured thresholds.", evidence, warnings)
        return pass_gate("complexity", "ROBUSTNESS", "Strategy complexity passed configured thresholds.", evidence)

    def _load_config(self, config_path: str | Path | None) -> GateConfig:
        if not config_path:
            return GateConfig()
        path = Path(config_path)
        if not path.exists():
            return GateConfig()
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"strategy gate config is not valid JSON: {path}") from exc
        if not isinstance(payload, dict):
            raise ValueError("strategy gate config must contain a JSON object")
        return GateConfig.from_mapping(payload)

    @staticmethod
    def _symbols(definition: StrategyDefinition) -> list[str]:
        return definition.symbols or list(DEFAULT_SYMBOLS)

    @staticmethod
    def _factor_names(definition: StrategyDefinition) -> list[str]:
        return [str(item.get("name") or "").strip().lower() for item in definition.factors if str(item.get("name") or "").strip()]

    @staticmethod
    def _parameter_count(definition: StrategyDefinition) -> int:
        sections = [definition.universe, definition.regime, definition.portfolio, definition.risk, definition.execution, definition.validation, definition.metadata]
        return sum(len(section) for section in sections if isinstance(section, dict)) + len(definition.factors)

    @staticmethod
    def _input_reports(strategy_run_report: dict[str, Any] | None) -> dict[str, Any]:
        if not strategy_run_report:
            return {}
        artifacts = strategy_run_report.get("artifacts") or {}
        return {
            "strategy_run_report": strategy_run_report.get("report_path"),
            "trade_sim_report": artifacts.get("trade_sim_report_path"),
        }

    @staticmethod
    def _evidence_summary(gates: list[GateResult]) -> dict[str, Any]:
        by_status: dict[str, int] = {}
        for gate in gates:
            by_status[gate.status] = by_status.get(gate.status, 0) + 1
        return {
            "gate_count": len(gates),
            "by_status": dict(sorted(by_status.items())),
            "failed_or_rejected": [gate.gate_name for gate in gates if gate.status in {FAIL, "REJECTED"}],
            "warning_gates": [gate.gate_name for gate in gates if gate.status == WARNING],
        }

    @staticmethod
    def _recommended_next_checks(gates: list[GateResult]) -> list[str]:
        mapping = {
            "WARN_LOW_PRICE_COVERAGE": "refresh price data or reduce the strategy universe",
            "WARN_LOW_FUNDAMENTAL_COVERAGE": "import more fundamental statements before relying on fundamental factors",
            "WARN_FACTOR_EVIDENCE_WEAK": "run factor-eval with --save-factor-history for strategy factors",
            "WARN_WALK_FORWARD_EVIDENCE_WEAK": "run walk-forward validation and save factor history",
            "WARN_LOW_REGIME_SAMPLE": "extend regime history before using regime-aware confidence",
            "REJECT_MAX_DRAWDOWN": "review risk limits and historical drawdown before further simulation",
        }
        checks = []
        for gate in gates:
            for warning in gate.warnings + gate.rejection_reasons:
                code = str(warning).split(":", 1)[0]
                if code in mapping:
                    checks.append(mapping[code])
        if not checks:
            checks.append("review generated strategy-run and trade-sim reports")
        return StrategyGateRunner._dedupe(checks)

    @staticmethod
    def _dedupe(values: list[Any]) -> list[str]:
        output = []
        seen = set()
        for value in values:
            text = str(value)
            if text and text not in seen:
                output.append(text)
                seen.add(text)
        return output
