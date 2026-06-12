"""Strategy registry and execution orchestration."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from quant.config import DEFAULT_SYMBOLS
from quant.strategy_dsl.strategy_definition import StrategyDefinition
from quant.strategy_dsl.strategy_loader import StrategyLoader
from quant.strategy_dsl.strategy_metadata import StrategyMetadataStore
from quant.strategy_dsl.strategy_validator import StrategyValidator


class StrategyRegistry:
    """Load, validate, register, and run strategy DSL definitions."""

    def __init__(self, context, strategy_dir: str | Path = "strategies", report_dir: str | Path = "reports") -> None:
        self.context = context
        self.loader = StrategyLoader(strategy_dir)
        self.validator = StrategyValidator(context.factor_evaluation.factor_registry)
        self.metadata_store = StrategyMetadataStore(context.db_path)
        self.report_dir = Path(report_dir)

    def list_strategies(self) -> dict[str, Any]:
        rows = []
        for path in self.loader.list_files():
            try:
                definition = self.loader.load_file(path)
                validation = self.validator.validate(definition)
                self.metadata_store.upsert_strategy(definition, validation.to_report(), str(path))
                rows.append(
                    {
                        "name": definition.name,
                        "version": definition.version,
                        "description": definition.description,
                        "tags": definition.tags,
                        "file": str(path),
                        "valid": validation.valid,
                        "warnings": validation.warnings,
                    }
                )
            except ValueError as exc:
                rows.append({"name": path.stem, "file": str(path), "valid": False, "errors": [str(exc)]})
        return {
            "metadata": {"report_type": "strategy_list"},
            "strategy_count": len(rows),
            "strategies": rows,
        }

    def load_strategy(self, strategy: str | None = None, file: str | Path | None = None) -> tuple[StrategyDefinition, Path]:
        if file:
            path = Path(file)
            return self.loader.load_file(path), path
        return self.loader.load_name(strategy or "momentum_fundamental")

    def show(self, strategy: str | None = None, file: str | Path | None = None) -> dict[str, Any]:
        definition, path = self.load_strategy(strategy, file)
        validation = self.validator.validate(definition)
        self.metadata_store.upsert_strategy(definition, validation.to_report(), str(path))
        return {
            "metadata": {"report_type": "strategy_definition"},
            "strategy": definition.to_dict(),
            "source_path": str(path),
            "validation": validation.to_report(),
        }

    def validate(self, strategy: str | None = None, file: str | Path | None = None, write_report: bool = False) -> dict[str, Any]:
        definition, path = self.load_strategy(strategy, file)
        validation = self.validator.validate(definition)
        report = validation.to_report() | {
            "source_path": str(path),
            "strategy": definition.to_dict(),
        }
        self.metadata_store.upsert_strategy(definition, validation.to_report(), str(path))
        if write_report:
            report = self._with_report_path(report, "strategy_validation")
        return report

    def run(
        self,
        strategy: str | None = None,
        file: str | Path | None = None,
        start: str = "2024-01-01",
        end: str = "2025-01-01",
        initial_cash: float = 100000.0,
        rebalance_frequency: str = "monthly",
    ) -> dict[str, Any]:
        definition, path = self.load_strategy(strategy, file)
        validation = self.validator.validate(definition)
        self.metadata_store.upsert_strategy(definition, validation.to_report(), str(path))
        if not validation.valid:
            raise ValueError("strategy validation failed: " + ", ".join(validation.errors))
        cost_config, market_realism_config = self._execution_configs(definition)
        alpha_config = self._alpha_config(definition)
        result = self.context.trading_simulator.run(
            strategy="alpha",
            start=start,
            end=end,
            initial_cash=initial_cash,
            rebalance_frequency=rebalance_frequency,
            portfolio_method=definition.portfolio_method,
            alpha_config=alpha_config,
            cost_config=cost_config,
            market_realism_config=market_realism_config,
            symbols=alpha_config["universe"],
        )
        report = self._strategy_run_report(
            definition=definition,
            source_path=path,
            validation=validation.to_report(),
            trading_report=result.to_report(),
        )
        self.metadata_store.save_run(report)
        return report

    def _strategy_run_report(
        self,
        definition: StrategyDefinition,
        source_path: Path,
        validation: dict[str, Any],
        trading_report: dict[str, Any],
    ) -> dict[str, Any]:
        generated_at = datetime.now().isoformat(timespec="seconds")
        warnings = list(validation.get("warnings") or []) + list(trading_report.get("warnings") or [])
        report = {
            "metadata": {
                "report_type": "strategy_run",
                "generated_at": generated_at,
                "offline_research_only": True,
                "live_trading": False,
                "broker_integration": False,
                "no_lookahead_preserved": True,
            },
            "run_id": f"strategy-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid4().hex[:8]}",
            "generated_at": generated_at,
            "strategy_name": definition.name,
            "strategy_version": definition.version,
            "strategy_file": str(source_path),
            "source_path": str(source_path),
            "status": "WARNING" if warnings else "PASS",
            "strategy": definition.to_dict(),
            "factors": [dict(item) for item in definition.factors],
            "factor_weights": definition.factor_weights,
            "normalized_factor_weights": (validation.get("gates") or {}).get("normalized_factor_weights", {}),
            "portfolio_settings": dict(definition.portfolio),
            "risk_settings": dict(definition.risk),
            "execution_settings": dict(definition.execution),
            "validation": validation,
            "validation_results": validation,
            "trade_sim_summary": {
                "final_equity": trading_report.get("final_equity"),
                "total_return": trading_report.get("total_return"),
                "max_drawdown": trading_report.get("max_drawdown"),
                "total_cost": trading_report.get("total_cost"),
                "trade_count": trading_report.get("trade_count"),
            },
            "artifacts": {"trade_sim_report_path": trading_report.get("report_path")},
            "generated_reports": [path for path in [trading_report.get("report_path")] if path],
            "warnings": _dedupe(warnings),
            "no_lookahead": True,
            "no_lookahead_notes": [
                "Strategy DSL cannot override no-lookahead behavior.",
                "Fundamental factors remain report-date gated with report_date <= signal_date.",
                "Execution remains delegated to the existing offline trade simulator.",
            ],
            "interpretation_notes": [
                "Strategy DSL runs orchestrate existing offline engines without changing their semantics.",
                "This is not live trading, broker execution, or investment advice.",
            ],
        }
        return self._with_report_path(report, "strategy_run")

    def _alpha_config(self, definition: StrategyDefinition) -> dict[str, Any]:
        cash = float(definition.portfolio.get("cash_buffer", 0.10))
        max_position = float(definition.portfolio.get("max_position_weight", 0.20))
        symbols = definition.symbols or list(DEFAULT_SYMBOLS)
        return {
            "universe": symbols,
            "factor_weights": definition.factor_weights,
            "weighting_mode": "custom_weight",
            "top_n": int(definition.metadata.get("top_n", min(5, len(symbols)) or 1)),
            "min_cash_weight": cash,
            "max_position_weight": max_position,
            "regime": definition.regime,
            "strategy_name": definition.name,
            "strategy_version": definition.version,
        }

    @staticmethod
    def _execution_configs(definition: StrategyDefinition) -> tuple[dict[str, Any], dict[str, Any]]:
        execution = dict(definition.execution)
        cost = {
            "model": execution.get("cost_model", "combined"),
            "slippage_bps": float(execution.get("slippage_bps", 5)),
        }
        market = {
            "slippage_model": execution.get("slippage_model", "bps"),
            "slippage_bps": float(execution.get("slippage_bps", 5)),
            "max_adv_participation": float(execution.get("max_adv_participation", 0.05)),
        }
        return cost, market

    def _with_report_path(self, report: dict[str, Any], prefix: str) -> dict[str, Any]:
        self.report_dir.mkdir(parents=True, exist_ok=True)
        path = self.report_dir / f"{prefix}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        output = report | {"report_path": str(path)}
        if prefix == "strategy_run":
            generated = list(output.get("generated_reports") or [])
            generated.append(str(path))
            output["generated_reports"] = _dedupe(generated)
        path.write_text(json.dumps(output, indent=2, sort_keys=True), encoding="utf-8")
        return output


def _dedupe(values: list[str]) -> list[str]:
    output = []
    seen = set()
    for value in values:
        text = str(value)
        if text and text not in seen:
            output.append(text)
            seen.add(text)
    return output
