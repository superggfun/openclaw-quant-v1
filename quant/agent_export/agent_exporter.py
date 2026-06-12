"""Compact report exports for LLM and agent consumers."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


SUPPORTED_FORMATS = {"text", "markdown", "json"}


@dataclass(frozen=True)
class AgentExport:
    report_type: str
    generated_from: str
    summary: str
    key_metrics: dict[str, Any]
    key_findings: list[str]
    warnings: list[str]
    recommended_next_steps: list[str]
    action_candidates: list[str]
    data_quality_notes: list[str]
    visualization_paths: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "report_type": self.report_type,
            "generated_from": self.generated_from,
            "summary": self.summary,
            "key_metrics": self.key_metrics,
            "key_findings": self.key_findings,
            "warnings": self.warnings,
            "recommended_next_steps": self.recommended_next_steps,
            "action_candidates": self.action_candidates,
            "data_quality_notes": self.data_quality_notes,
            "visualization_paths": self.visualization_paths,
        }


class AgentExporter:
    """Convert rich reports into deterministic compact agent summaries."""

    def export_file(
        self,
        report_path: str | Path,
        output_format: str = "text",
        max_tokens: int = 800,
        output_path: str | Path | None = None,
    ) -> str:
        path = Path(report_path)
        try:
            report = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise ValueError(f"report file not found: {path}") from exc
        except json.JSONDecodeError as exc:
            raise ValueError(f"report file is not valid JSON: {path}") from exc
        if not isinstance(report, dict):
            raise ValueError("report must contain a JSON object")

        export = self.export_report(report, generated_from=str(path))
        rendered = self.render(export, output_format=output_format, max_tokens=max_tokens)
        if output_path:
            target = Path(output_path)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(rendered, encoding="utf-8")
        return rendered

    def export_report(self, report: dict[str, Any], generated_from: str = "<memory>") -> AgentExport:
        report_type = self.detect_report_type(report)
        builder = getattr(self, f"_export_{report_type}", None)
        if builder is None:
            return self._base_export(
                report_type=report_type,
                generated_from=generated_from,
                summary=f"Detected {report_type} report.",
            )
        return builder(report, generated_from)

    def export_protocol(self, protocol_object: Any, generated_from: str = "<protocol>") -> AgentExport:
        to_dict = getattr(protocol_object, "to_dict", None)
        if not callable(to_dict):
            raise ValueError("protocol object must expose to_dict()")
        payload = to_dict()
        protocol_type = protocol_object.__class__.__name__
        warnings = []
        validate = getattr(protocol_object, "validate", None)
        if callable(validate):
            warnings = [f"PROTOCOL_VALIDATION: {error}" for error in validate()]
        metrics = {
            key: payload.get(key)
            for key in ("account_id", "cash", "equity", "market_value", "symbol", "side", "quantity", "status", "target_weight")
            if key in payload
        }
        return self._base_export(
            report_type=f"protocol_{protocol_type}",
            generated_from=generated_from,
            summary=f"{protocol_type} protocol object exported for agent context.",
            key_metrics=metrics,
            key_findings=["protocol object is JSON serializable"],
            warnings=warnings,
            recommended_next_steps=["use stable protocol fields for MCP/OpenClaw integration"],
            action_candidates=[],
            data_quality_notes=[],
        )

    def detect_report_type(self, report: dict[str, Any]) -> str:
        if (
            report.get("metadata", {}).get("report_type") == "trade_sim"
            or {"strategy", "portfolio_method", "equity_curve", "rebalance_events", "final_equity"}.issubset(report)
        ):
            return "trade_sim"
        report_type = (report.get("metadata") or {}).get("report_type")
        if report_type in {
            "factor_store_summary",
            "factor_history",
            "factor_rank",
            "regime_detection",
            "regime_history",
            "regime_report",
            "regime_rank",
            "research_run",
            "research_status",
            "research_history",
            "strategy_list",
            "strategy_definition",
            "strategy_validation",
            "strategy_run",
            "strategy_gate",
        }:
            return report_type
        if {"strategy", "folds", "stability_analysis", "summary"}.issubset(report):
            return "walk_forward"
        if {"summary_metrics", "attribution", "robustness_diagnostics"}.issubset(report):
            return "strategy_eval"
        if "factor" in report and "holding_period" in report and "long_short_return" in report:
            return "factor_backtest"
        if "factor" in report and ("forward_days" in report or "ic_mean" in report) and "decay" in report:
            return "factor_eval"
        if (report.get("metadata") or {}).get("report_type") == "multi_factor" or {"factor_families", "family_weights", "confidence", "scores"}.issubset(report):
            return "multi_factor"
        if "method" in report and "risk_contribution_pct" in report and "covariance_matrix" in report:
            return "portfolio_construction"
        if "selected_symbols" in report and "target_weights" in report:
            return "alpha"
        if "risk_score" in report and ("single_stock_concentration_pct" in report or "holdings" in report):
            return "risk"
        if "items" in report and "cash_after_rebalance" in report:
            return "rebalance"
        if "executed_trades" in report and "unfilled_trades" in report and "execution_costs" in report:
            return "execution"
        if "metrics" in report and ("equity_curve" in report or "trades" in report):
            return "backtest"
        if report_type in {"fundamental_import", "fundamental_coverage", "fundamental_quality"}:
            return report_type
        return "unknown"

    def render(self, export: AgentExport, output_format: str = "text", max_tokens: int = 800) -> str:
        normalized_format = output_format.lower().strip()
        if normalized_format not in SUPPORTED_FORMATS:
            raise ValueError("format must be one of: text, markdown, json")
        compact = self._trim_export(export.to_dict(), max_tokens=max_tokens)
        if normalized_format == "json":
            return json.dumps(compact, indent=2, sort_keys=True)
        if normalized_format == "markdown":
            return self._render_markdown(compact)
        return self._render_text(compact)

    def _export_alpha(self, report: dict[str, Any], generated_from: str) -> AgentExport:
        selected = report.get("selected_symbols") or []
        weights = report.get("target_weights") or {}
        universe_size = len((report.get("config") or {}).get("universe") or selected)
        warnings = self._clean_warnings(report.get("warnings"))
        if universe_size < 10:
            warnings.append("WARN_UNIVERSE_SMALL")
        summary = f"Alpha selected {len(selected)} symbols from a {universe_size} symbol universe."
        metrics = {
            "as_of_date": report.get("as_of_date"),
            "selected_symbols": selected,
            "target_weights": self._round_mapping(weights),
            "cash_weight": weights.get("cash"),
            "weighting_mode": (report.get("config") or {}).get("weighting_mode"),
            "multi_factor_confidence": ((report.get("multi_factor_summary") or {}).get("confidence") or {}).get("overall_confidence"),
            "multi_factor_report_path": report.get("multi_factor_report_path"),
        }
        return self._base_export(
            "alpha",
            generated_from,
            summary,
            metrics,
            [f"selected_symbols: {', '.join(selected)}", "momentum-based portfolio selected"],
            warnings,
            ["run factor evaluation", "run rebalance with costs", "expand universe"],
            [f"target {symbol} {self._format_pct(weight)}" for symbol, weight in weights.items()],
            self._exclusion_notes(report),
        )

    def _export_multi_factor(self, report: dict[str, Any], generated_from: str) -> AgentExport:
        scores = report.get("scores") or []
        top_scores = sorted(
            [score for score in scores if isinstance(score, dict) and self._num(score.get("final_alpha_score")) is not None],
            key=lambda item: (float(item.get("final_alpha_score") or 0.0), str(item.get("symbol"))),
            reverse=True,
        )[:5]
        confidence = report.get("confidence") or {}
        coverage = report.get("coverage") or {}
        warnings = self._clean_warnings(report.get("warnings"))
        low_coverage = {
            factor: value
            for factor, value in coverage.items()
            if self._num(value) is not None and float(value) < 0.8
        }
        if low_coverage:
            warnings.append("WARN_LOW_FACTOR_COVERAGE")
        metrics = {
            "as_of_date": report.get("as_of_date"),
            "weighting_mode": report.get("weighting_mode"),
            "overall_confidence": confidence.get("overall_confidence"),
            "factor_weights": report.get("factor_weights"),
            "factor_weights_by_family": report.get("factor_weights_by_family"),
            "family_weights": report.get("family_weights"),
            "coverage": coverage,
            "top_symbols": [
                {"symbol": item.get("symbol"), "score": item.get("final_alpha_score"), "confidence": item.get("overall_confidence")}
                for item in top_scores
            ],
        }
        return self._base_export(
            "multi_factor",
            generated_from,
            "Multi-factor model produced a unified coverage-aware alpha score.",
            metrics,
            ["unified alpha score generated", "coverage-aware confidence generated"],
            warnings,
            ["review low-coverage factors", "run walk-forward validation", "compare family contributions"],
            [f"inspect {item.get('symbol')} factor contributions" for item in top_scores],
            [f"{factor}: coverage {float(value):.2%}" for factor, value in low_coverage.items()],
        )

    def _export_factor_eval(self, report: dict[str, Any], generated_from: str) -> AgentExport:
        ic = report.get("ic_mean")
        rank_ic = report.get("rank_ic_mean")
        icir = report.get("icir")
        decay = report.get("decay") or {}
        best_horizon = self._best_decay_horizon(decay)
        assessment = "positive predictive quality" if self._num(ic) and self._num(ic) > 0 else "negative predictive quality"
        warnings = self._clean_warnings(report.get("warnings"))
        if self._num(ic) is not None and self._num(ic) < 0:
            warnings.append("WARN_FACTOR_IC_NEGATIVE")
        coverage = report.get("factor_coverage") or {}
        if coverage and self._num(coverage.get("missing_percentage")) and self._num(coverage.get("missing_percentage")) > 0:
            warnings.append("WARN_PARTIAL_FUNDAMENTAL_DATA")
        metrics = {
            "factor": report.get("factor"),
            "ic_mean": ic,
            "rank_ic_mean": rank_ic,
            "icir": icir,
            "ic_count": report.get("ic_count"),
            "best_horizon": best_horizon,
            "spread_return": report.get("spread_return"),
            "factor_coverage": coverage or None,
        }
        return self._base_export(
            "factor_eval",
            generated_from,
            f"Factor {report.get('factor')} shows {assessment}.",
            metrics,
            [assessment],
            warnings,
            ["compare factors", "run factor backtest", "expand universe"],
            [f"evaluate {report.get('factor')} over larger universe"],
            self._exclusion_notes(report),
        )

    def _export_factor_backtest(self, report: dict[str, Any], generated_from: str) -> AgentExport:
        ret = report.get("long_short_return")
        sharpe = report.get("long_short_sharpe", report.get("sharpe"))
        drawdown = report.get("max_drawdown")
        assessment = "factor currently positive" if self._num(ret) and self._num(ret) > 0 else "factor currently weak"
        warnings = self._clean_warnings(report.get("warnings"))
        warnings.extend(self._performance_warnings(total_return=ret, sharpe=sharpe, drawdown=drawdown))
        if len(report.get("rebalance_dates") or []) < 20:
            warnings.append("WARN_LOW_OBSERVATION_COUNT")
        coverage = report.get("factor_coverage") or {}
        if coverage and self._num(coverage.get("missing_percentage")) and self._num(coverage.get("missing_percentage")) > 0:
            warnings.append("WARN_PARTIAL_FUNDAMENTAL_DATA")
        metrics = {
            "factor": report.get("factor"),
            "long_short_return": ret,
            "sharpe": sharpe,
            "max_drawdown": drawdown,
            "turnover": report.get("turnover"),
            "gross_exposure": report.get("gross_exposure"),
            "net_exposure": report.get("net_exposure"),
            "ic_mean": report.get("ic_mean"),
            "rank_ic_mean": report.get("rank_ic_mean"),
            "icir": report.get("icir"),
            "factor_coverage": coverage or None,
        }
        return self._base_export(
            "factor_backtest",
            generated_from,
            f"Long-short factor backtest assessment: {assessment}.",
            metrics,
            [assessment],
            warnings,
            ["test with larger universe", "review drawdown", "compare factors"],
            ["run strategy evaluation", "run factor evaluation"],
            self._exclusion_notes(report),
        )

    def _export_strategy_eval(self, report: dict[str, Any], generated_from: str) -> AgentExport:
        summary_metrics = report.get("summary_metrics") or {}
        attribution = report.get("attribution") or {}
        assessment = "positive historical performance" if self._num(summary_metrics.get("total_return")) and self._num(summary_metrics.get("total_return")) > 0 else "weak or negative historical performance"
        warnings = self._clean_warnings(report.get("warnings"))
        warnings.extend(
            self._performance_warnings(
                total_return=summary_metrics.get("total_return"),
                sharpe=summary_metrics.get("sharpe_ratio"),
                drawdown=summary_metrics.get("max_drawdown"),
            )
        )
        metrics = {
            "total_return": summary_metrics.get("total_return"),
            "annual_return": summary_metrics.get("annual_return"),
            "sharpe": summary_metrics.get("sharpe_ratio"),
            "max_drawdown": summary_metrics.get("max_drawdown"),
            "total_cost": summary_metrics.get("total_cost"),
            "turnover": summary_metrics.get("turnover"),
            "cost_to_return_ratio": summary_metrics.get("cost_to_return_ratio"),
            "top_contributors": attribution.get("top_positive_contributors", [])[:3],
            "top_detractors": attribution.get("top_negative_contributors", [])[:3],
        }
        return self._base_export(
            "strategy_eval",
            generated_from,
            f"Strategy evaluation indicates {assessment}.",
            metrics,
            [assessment],
            warnings,
            ["run walk-forward validation", "inspect cost drag", "review drawdown"],
            ["compare against benchmark", "export backtest summary"],
            [],
        )

    def _export_portfolio_construction(self, report: dict[str, Any], generated_from: str) -> AgentExport:
        weights = report.get("target_weights") or {}
        cash = report.get("cash_weight", weights.get("cash"))
        warnings = self._clean_warnings(report.get("warnings"))
        if self._num(cash) is not None and self._num(cash) >= 0.30:
            warnings.append("WARN_CASH_ALLOCATION_HIGH")
        if any("capped" in warning for warning in warnings):
            warnings.append("WARN_MAX_WEIGHT_CONSTRAINT_BINDING")
        metrics = {
            "method": report.get("method"),
            "target_weights": self._round_mapping(weights),
            "cash_weight": cash,
            "portfolio_volatility": report.get("portfolio_volatility", report.get("expected_portfolio_volatility")),
            "risk_contribution_pct": self._round_mapping(report.get("risk_contribution_pct") or report.get("risk_contribution_pct_by_symbol") or {}),
            "selected_symbols": report.get("selected_symbols") or report.get("symbols_used"),
        }
        assessment = "constraints produced large cash allocation" if self._num(cash) and self._num(cash) >= 0.30 else "portfolio construction produced constrained target weights"
        return self._base_export(
            "portfolio_construction",
            generated_from,
            f"Portfolio construction method {report.get('method')} generated target weights.",
            metrics,
            [assessment],
            warnings,
            ["evaluate risk parity allocation", "run rebalance with costs", "expand universe"],
            [f"target {symbol} {self._format_pct(weight)}" for symbol, weight in weights.items()],
            self._exclusion_notes(report),
        )

    def _export_risk(self, report: dict[str, Any], generated_from: str) -> AgentExport:
        score = report.get("risk_score")
        warnings = self._clean_warnings(report.get("warnings"))
        concentration = report.get("single_stock_concentration_pct")
        if self._num(concentration) is not None and self._num(concentration) > 50:
            warnings.append("WARN_POSITION_CONCENTRATION_HIGH")
        metrics = {
            "risk_score": score,
            "single_stock_concentration_pct": concentration,
            "industry_concentration_pct": report.get("industry_concentration_pct"),
            "top_5_holdings_pct": report.get("top_5_holdings_pct"),
            "cash_weight_pct": report.get("cash_weight_pct"),
            "top_holdings": (report.get("holdings") or [])[:5] if isinstance(report.get("holdings"), list) else report.get("holdings"),
        }
        assessment = "high risk" if self._num(score) is not None and self._num(score) >= 70 else "moderate or low risk"
        return self._base_export(
            "risk",
            generated_from,
            f"Risk report assessment: {assessment}.",
            metrics,
            [assessment],
            warnings,
            ["review concentration", "run rebalance", "evaluate risk parity allocation"],
            [],
            [],
        )

    def _export_rebalance(self, report: dict[str, Any], generated_from: str) -> AgentExport:
        items = report.get("items") or []
        trades = [item for item in items if item.get("action") in {"BUY", "SELL"}]
        warnings = self._clean_warnings(report.get("warnings"))
        metrics = {
            "total_assets": report.get("total_assets"),
            "cash_before": report.get("cash_before"),
            "cash_after_rebalance": report.get("cash_after_rebalance"),
            "estimated_total_commission": report.get("estimated_total_commission"),
            "trade_count": len(trades),
            "largest_changes": sorted(trades, key=lambda item: abs(item.get("difference", 0) or 0), reverse=True)[:5],
        }
        actions = [f"{item.get('action')} {item.get('symbol')} {item.get('qty')} shares" for item in trades]
        return self._base_export(
            "rebalance",
            generated_from,
            f"Rebalance plan has {len(trades)} trade candidates.",
            metrics,
            [f"{len(trades)} buy/sell suggestions"],
            warnings,
            ["inspect cost drag", "simulate execution", "review cash target"],
            actions,
            [],
        )

    def _export_execution(self, report: dict[str, Any], generated_from: str) -> AgentExport:
        executed = report.get("executed_trades") or []
        unfilled = report.get("unfilled_trades") or []
        costs = report.get("execution_costs") or {}
        warnings = self._clean_warnings(report.get("warnings"))
        if unfilled:
            warnings.append("WARN_UNFILLED_TRADES_PRESENT")
        metrics = {
            "mode": report.get("mode"),
            "executed_count": len(executed),
            "unfilled_count": len(unfilled),
            "total_cost": costs.get("total_cost"),
            "slippage_estimate": report.get("slippage_estimate", costs.get("total_slippage")),
            "market_impact": costs.get("total_market_impact"),
            "liquidity_cost": costs.get("total_liquidity_cost"),
            "market_realism": report.get("market_realism"),
            "final_cash": report.get("final_cash"),
        }
        realism = report.get("market_realism") or {}
        if realism.get("total_rejected_quantity"):
            warnings.append("WARN_LIQUIDITY_REJECTIONS")
        return self._base_export(
            "execution",
            generated_from,
            f"Execution simulation filled {len(executed)} trades and left {len(unfilled)} unfilled.",
            metrics,
            ["execution simulation completed"],
            warnings,
            ["review unfilled trades", "inspect execution costs", "compare execution modes"],
            [f"executed {trade.get('side')} {trade.get('symbol')}" for trade in executed[:5]],
            [],
        )

    def _export_backtest(self, report: dict[str, Any], generated_from: str) -> AgentExport:
        metrics = report.get("metrics") or {}
        warnings = self._clean_warnings(report.get("warnings"))
        warnings.extend(
            self._performance_warnings(
                total_return=metrics.get("total_return") or metrics.get("total_return_pct"),
                sharpe=metrics.get("sharpe_ratio"),
                drawdown=metrics.get("max_drawdown") or metrics.get("max_drawdown_pct"),
            )
        )
        key_metrics = {
            "strategy": report.get("strategy", report.get("mode")),
            "start": report.get("start"),
            "end": report.get("end"),
            "final_value": metrics.get("final_value"),
            "total_return": metrics.get("total_return", metrics.get("total_return_pct")),
            "sharpe": metrics.get("sharpe_ratio"),
            "max_drawdown": metrics.get("max_drawdown", metrics.get("max_drawdown_pct")),
            "total_cost": metrics.get("total_cost"),
            "trade_count": metrics.get("trade_count", metrics.get("number_of_trades")),
        }
        return self._base_export(
            "backtest",
            generated_from,
            "Backtest report summarized for agent review.",
            key_metrics,
            ["backtest completed"],
            warnings,
            ["run strategy evaluation", "review drawdown", "compare benchmark"],
            [],
            [],
        )

    def _export_walk_forward(self, report: dict[str, Any], generated_from: str) -> AgentExport:
        summary = report.get("summary") or {}
        warnings = self._clean_warnings(report.get("warnings"))
        stability = (report.get("stability_analysis") or {}).get("factor_stability_ranking") or []
        top_stable = stability[0] if stability else {}
        metrics = {
            "strategy": report.get("strategy"),
            "fold_count": summary.get("fold_count"),
            "average_train_return": summary.get("average_train_return"),
            "average_test_return": summary.get("average_test_return"),
            "average_train_sharpe": summary.get("average_train_sharpe"),
            "average_test_sharpe": summary.get("average_test_sharpe"),
            "average_ic": summary.get("average_ic"),
            "average_rank_ic": summary.get("average_rank_ic"),
            "top_stable_factor": top_stable.get("factor"),
            "top_stable_factor_classification": top_stable.get("classification"),
        }
        findings = []
        if top_stable:
            findings.append(f"{top_stable.get('factor')} classified as {top_stable.get('classification')}")
        if any("WARN_OVERFIT" in warning for warning in warnings):
            findings.append("overfitting detected")
        if any("WARN_FACTOR_DECAY" in warning for warning in warnings):
            findings.append("factor decay detected")
        assessment = "walk-forward validation completed"
        return self._base_export(
            "walk_forward",
            generated_from,
            assessment,
            metrics,
            findings or [assessment],
            warnings,
            ["compare folds", "review factor stability", "inspect out-of-sample drawdowns"],
            [],
            [],
        )

    def _export_trade_sim(self, report: dict[str, Any], generated_from: str) -> AgentExport:
        warnings = self._clean_warnings(report.get("warnings"))
        warnings.extend(
            self._performance_warnings(
                total_return=report.get("total_return"),
                sharpe=report.get("sharpe"),
                drawdown=report.get("max_drawdown"),
            )
        )
        final_equity = self._num(report.get("final_equity"))
        total_cost = self._num(report.get("total_cost"))
        if final_equity is not None and total_cost is not None and total_cost / max(abs(final_equity), 1.0) > 0.02:
            warnings.append("WARN_COST_DRAG_HIGH")
        realism = report.get("market_realism") or {}
        if realism.get("total_rejected_quantity"):
            warnings.append("WARN_LIQUIDITY_CAP")
        if realism.get("total_slippage") and final_equity is not None and float(realism["total_slippage"]) / max(abs(final_equity), 1.0) > 0.01:
            warnings.append("WARN_HIGH_SLIPPAGE")
        metrics = {
            "strategy": report.get("strategy"),
            "portfolio_method": report.get("portfolio_method"),
            "initial_cash": report.get("initial_cash"),
            "final_equity": report.get("final_equity"),
            "total_return": report.get("total_return"),
            "annual_return": report.get("annual_return"),
            "sharpe": report.get("sharpe"),
            "max_drawdown": report.get("max_drawdown"),
            "total_cost": report.get("total_cost"),
            "slippage": realism.get("total_slippage"),
            "market_impact": realism.get("total_market_impact"),
            "liquidity_cost": realism.get("total_liquidity_cost"),
            "rejected_trade_count": len(report.get("rejected_trades") or []),
            "largest_constrained_trades": realism.get("largest_constrained_trades"),
            "turnover": report.get("turnover"),
            "trade_count": report.get("trade_count"),
            "rebalance_events": len(report.get("rebalance_events") or []),
            "no_lookahead": report.get("no_lookahead"),
        }
        assessment = "positive historical simulation" if self._num(report.get("total_return")) and self._num(report.get("total_return")) > 0 else "weak or negative historical simulation"
        return self._base_export(
            "trade_sim",
            generated_from,
            f"Historical trading simulation completed with {assessment}.",
            metrics,
            [assessment, "account-style cash and positions were tracked through time"],
            warnings,
            ["run walk-forward validation", "compare portfolio methods", "inspect cost drag", "review liquidity constraints"],
            ["run strategy evaluation", "export trade simulation report"],
            [],
        )

    def _export_fundamental_import(self, report: dict[str, Any], generated_from: str) -> AgentExport:
        summary = report.get("summary") or {}
        warnings = self._clean_warnings(report.get("warnings"))
        metrics = {
            "inserted": summary.get("inserted"),
            "updated": summary.get("updated"),
            "skipped": summary.get("skipped"),
            "errors": summary.get("errors"),
            "file": (report.get("parameters") or {}).get("file"),
            "statement": (report.get("parameters") or {}).get("statement"),
        }
        return self._base_export(
            "fundamental_import",
            generated_from,
            "Fundamental CSV import completed.",
            metrics,
            ["fundamental data imported into SQLite"],
            warnings,
            ["run fundamental coverage", "run fundamental quality", "review report_date alignment"],
            [],
            report.get("no_lookahead_notes") or [],
        )

    def _export_fundamental_coverage(self, report: dict[str, Any], generated_from: str) -> AgentExport:
        coverage = report.get("coverage") or {}
        warnings = self._clean_warnings(report.get("warnings"))
        if coverage.get("symbols_missing_fundamental_data", 0):
            warnings.append("WARN_FUNDAMENTAL_COVERAGE_GAP")
        metrics = {
            "readiness_score": coverage.get("readiness_score"),
            "total_symbols": coverage.get("total_symbols"),
            "symbols_covered": coverage.get("symbols_with_any_fundamental_data"),
            "symbols_missing": coverage.get("symbols_missing_fundamental_data"),
            "missing_symbols": (coverage.get("missing_symbols") or [])[:10],
            "statement_coverage": coverage.get("statement_coverage"),
            "latest_report_date": coverage.get("latest_report_date"),
        }
        return self._base_export(
            "fundamental_coverage",
            generated_from,
            f"Fundamental coverage readiness score is {coverage.get('readiness_score')}.",
            metrics,
            ["fundamental coverage report generated"],
            warnings,
            ["import missing symbols", "run fundamental quality", "validate report_date freshness"],
            [],
            report.get("no_lookahead_notes") or [],
        )

    def _export_fundamental_quality(self, report: dict[str, Any], generated_from: str) -> AgentExport:
        summary = report.get("summary") or {}
        warnings = self._clean_warnings(report.get("warnings"))
        metrics = {
            "status": summary.get("status"),
            "symbols_checked": summary.get("symbols_checked"),
            "warnings": summary.get("warnings"),
            "checks": summary.get("checks"),
            "top_warnings": warnings[:10],
        }
        return self._base_export(
            "fundamental_quality",
            generated_from,
            f"Fundamental quality status is {summary.get('status')}.",
            metrics,
            ["fundamental quality checks completed"],
            warnings,
            ["fix stale reports", "review missing fields", "check currency consistency"],
            [],
            report.get("no_lookahead_notes") or [],
        )

    def _export_factor_store_summary(self, report: dict[str, Any], generated_from: str) -> AgentExport:
        counts = report.get("counts") or {}
        metrics = {
            "factor_definitions": counts.get("factor_definitions"),
            "factor_values": counts.get("factor_values"),
            "factor_evaluation_history": counts.get("factor_evaluation_history"),
            "factor_backtest_history": counts.get("factor_backtest_history"),
            "factor_walk_forward_history": counts.get("factor_walk_forward_history"),
            "factor_stability_history": counts.get("factor_stability_history"),
            "factor_count": len(report.get("factors") or []),
        }
        warnings = []
        if not counts.get("factor_values"):
            warnings.append("WARN_FACTOR_STORE_EMPTY_VALUES")
        return self._base_export(
            "factor_store_summary",
            generated_from,
            "Factor store summary generated for persisted research history.",
            metrics,
            ["factor store is available for reproducible research"],
            warnings,
            ["save factor-eval with --save-factor-history", "review factor-rank", "compare factor history over time"],
            [],
            [],
        )

    def _export_factor_history(self, report: dict[str, Any], generated_from: str) -> AgentExport:
        evaluations = report.get("evaluation_history") or []
        backtests = report.get("backtest_history") or []
        stability = report.get("stability_history") or []
        latest_eval = evaluations[0] if evaluations else {}
        latest_backtest = backtests[0] if backtests else {}
        latest_stability = stability[0] if stability else {}
        metrics = {
            "factor": report.get("factor"),
            "evaluation_rows": len(evaluations),
            "backtest_rows": len(backtests),
            "walk_forward_rows": len(report.get("walk_forward_history") or []),
            "stability_rows": len(stability),
            "latest_ic": latest_eval.get("ic"),
            "latest_rank_ic": latest_eval.get("rank_ic"),
            "latest_icir": latest_eval.get("icir"),
            "latest_coverage": latest_eval.get("coverage"),
            "latest_long_short_return": latest_backtest.get("long_short_return"),
            "latest_sharpe": latest_backtest.get("sharpe"),
            "latest_stability": latest_stability.get("stability_score"),
        }
        warnings = []
        if not evaluations and not backtests:
            warnings.append("WARN_FACTOR_HISTORY_EMPTY")
        if self._num(latest_eval.get("coverage")) is not None and self._num(latest_eval.get("coverage")) < 0.5:
            warnings.append("WARN_FACTOR_COVERAGE_LOW")
        return self._base_export(
            "factor_history",
            generated_from,
            f"Persisted history for factor {report.get('factor') or 'all factors'} summarized.",
            metrics,
            ["historical factor diagnostics are persisted"],
            warnings,
            ["compare IC history", "review coverage trend", "run factor-rank"],
            [],
            [],
        )

    def _export_factor_rank(self, report: dict[str, Any], generated_from: str) -> AgentExport:
        top = report.get("top_factors") or []
        worst = report.get("worst_factors") or []
        stable = report.get("most_stable_factors") or []
        top_factor = top[0] if top else {}
        metrics = {
            "top_factor": top_factor.get("factor_name"),
            "top_factor_health": top_factor.get("health_score"),
            "top_factor_ic": top_factor.get("ic"),
            "top_factor_coverage": top_factor.get("coverage"),
            "top_factors": [row.get("factor_name") for row in top[:5]],
            "worst_factors": [row.get("factor_name") for row in worst[:5]],
            "most_stable_factors": [row.get("factor_name") for row in stable[:5]],
        }
        warnings = []
        if top_factor and self._num(top_factor.get("coverage")) is not None and self._num(top_factor.get("coverage")) < 0.5:
            warnings.append("WARN_TOP_FACTOR_LOW_COVERAGE")
        return self._base_export(
            "factor_rank",
            generated_from,
            "Factor ranking report summarized persisted factor quality diagnostics.",
            metrics,
            [f"top factor: {top_factor.get('factor_name')}" if top_factor else "no ranked factors available"],
            warnings,
            ["increase coverage before production use", "inspect worst factors", "run walk-forward validation"],
            [],
            [],
        )

    def _export_regime_detection(self, report: dict[str, Any], generated_from: str) -> AgentExport:
        current = report.get("current_regime") or {}
        metrics = {
            "benchmark": report.get("benchmark"),
            "current_regime": current.get("regime"),
            "date": current.get("date"),
            "volatility": current.get("volatility"),
            "trend_strength": current.get("trend_strength"),
            "drawdown": current.get("drawdown"),
            "confidence": current.get("confidence"),
            "regime_counts": report.get("regime_counts"),
        }
        warnings = self._clean_warnings(report.get("warnings"))
        return self._base_export(
            "regime_detection",
            generated_from,
            f"Current market regime is {current.get('regime', 'UNKNOWN')} based on deterministic historical diagnostics.",
            metrics,
            [f"current regime: {current.get('regime', 'UNKNOWN')}"],
            warnings,
            ["review factor performance by regime", "run regime-rank", "compare current exposures with regime diagnostics"],
            [],
            ["regime detection is observational research evidence, not a forecast or trading recommendation"],
        )

    def _export_regime_history(self, report: dict[str, Any], generated_from: str) -> AgentExport:
        current = report.get("current_regime") or {}
        metrics = {
            "current_regime": current.get("regime"),
            "history_rows": len(report.get("history") or []),
            "regime_counts": report.get("regime_counts"),
        }
        return self._base_export(
            "regime_history",
            generated_from,
            "Persisted market regime history summarized.",
            metrics,
            [f"current regime: {current.get('regime', 'UNKNOWN')}"],
            self._clean_warnings(report.get("warnings")),
            ["run regime-report", "review regime transitions"],
            [],
            ["regime history is not a timing signal or trading recommendation"],
        )

    def _export_regime_report(self, report: dict[str, Any], generated_from: str) -> AgentExport:
        current = report.get("current_regime") or {}
        performance = report.get("factor_performance_by_regime") or {}
        metrics = {
            "current_regime": current.get("regime"),
            "regime_counts": report.get("regime_counts"),
            "regimes_with_factor_history": sorted(performance),
        }
        return self._base_export(
            "regime_report",
            generated_from,
            f"Regime diagnostics report for current regime {current.get('regime', 'UNKNOWN')}.",
            metrics,
            ["factor performance by regime available" if performance else "no factor regime history available"],
            self._clean_warnings(report.get("warnings")),
            ["save factor-eval with --save-regime-history", "run regime-rank"],
            [],
            ["factor-by-regime diagnostics are observational research summaries, not predictions"],
        )

    def _export_regime_rank(self, report: dict[str, Any], generated_from: str) -> AgentExport:
        current = report.get("current_regime") or {}
        best = report.get("best_by_regime") or {}
        current_rows = best.get(current.get("regime")) or []
        top = current_rows[0] if current_rows else {}
        metrics = {
            "current_regime": current.get("regime"),
            "top_factor_current_regime": top.get("factor_name"),
            "top_factor_health": top.get("health_score"),
            "regimes_ranked": sorted(best),
            "most_stable_factors": [
                row.get("factor_name")
                for row in (report.get("most_stable_across_regimes") or [])[:5]
            ],
        }
        warnings = self._clean_warnings(report.get("warnings"))
        return self._base_export(
            "regime_rank",
            generated_from,
            "Regime-aware factor ranking summarized as observational research evidence.",
            metrics,
            [f"top current-regime factor: {top.get('factor_name')}" if top else "no current-regime factor ranking available"],
            warnings,
            ["review momentum exposure", "compare factor stability across regimes", "increase factor regime history"],
            [],
            ["regime rankings are diagnostics only, not forecasts, timing signals, or investment advice"],
        )

    def _export_research_run(self, report: dict[str, Any], generated_from: str) -> AgentExport:
        summary = report.get("daily_research_summary") or {}
        trade = summary.get("trade_sim_summary") or {}
        metrics = {
            "run_id": report.get("run_id"),
            "status": report.get("status"),
            "current_regime": summary.get("current_regime"),
            "best_factors": summary.get("best_factors"),
            "weak_factors": summary.get("weak_factors"),
            "trade_sim_return": trade.get("total_return"),
            "trade_sim_final_equity": trade.get("final_equity"),
            "trade_sim_max_drawdown": trade.get("max_drawdown"),
            "generated_reports": len(report.get("generated_reports") or []),
            "generated_visualizations": len(report.get("generated_visualizations") or []),
        }
        findings = []
        if summary.get("current_regime"):
            findings.append(f"current regime: {summary['current_regime']}")
        if summary.get("best_factors"):
            findings.append(f"top factor: {summary['best_factors'][0]}")
        if trade.get("total_return") is not None:
            findings.append(f"trade simulation return: {trade['total_return']}")
        warnings = self._clean_warnings(report.get("warnings"))
        return self._base_export(
            "research_run",
            generated_from,
            "Daily research pipeline completed as an offline diagnostics workflow.",
            metrics,
            findings,
            warnings,
            report.get("recommended_next_checks") or ["review generated artifacts", "inspect warnings"],
            [],
            ["scheduler output is research automation, not investment advice or live trading"],
        )

    def _export_research_status(self, report: dict[str, Any], generated_from: str) -> AgentExport:
        latest = report.get("latest_run") or {}
        return self._base_export(
            "research_status",
            generated_from,
            f"Latest research scheduler status is {report.get('status', 'NO_RUNS')}.",
            {"status": report.get("status"), "latest_run_id": latest.get("run_id"), "latest_regime": latest.get("regime")},
            [],
            self._clean_warnings(latest.get("warnings")),
            ["run research-run", "review research-history"],
            [],
            ["research status is operational metadata only"],
        )

    def _export_research_history(self, report: dict[str, Any], generated_from: str) -> AgentExport:
        runs = report.get("runs") or []
        return self._base_export(
            "research_history",
            generated_from,
            "Research scheduler history summarized.",
            {"run_count": len(runs), "status_counts": (report.get("summary") or {}).get("status_counts")},
            [f"latest run: {runs[0].get('run_id')}" if runs else "no scheduler runs found"],
            [],
            ["review repeated failures", "compare daily regime and factor summaries"],
            [],
            ["research history is offline workflow telemetry"],
        )

    def _export_strategy_list(self, report: dict[str, Any], generated_from: str) -> AgentExport:
        strategies = report.get("strategies") or []
        return self._base_export(
            "strategy_list",
            generated_from,
            f"Strategy registry contains {len(strategies)} offline research definitions.",
            {
                "strategy_count": len(strategies),
                "strategies": [row.get("name") for row in strategies[:10]],
            },
            ["strategy definitions are versioned research objects"],
            self._clean_warnings(report.get("warnings")),
            ["validate a strategy before running", "run strategy-run for offline simulation"],
            [],
            ["Strategy DSL does not enable broker execution or live trading."],
        )

    def _export_strategy_definition(self, report: dict[str, Any], generated_from: str) -> AgentExport:
        strategy = report.get("strategy") or {}
        validation = report.get("validation") or {}
        return self._base_export(
            "strategy_definition",
            generated_from,
            f"Strategy {strategy.get('name')} version {strategy.get('version')} summarized.",
            {
                "name": strategy.get("name"),
                "version": strategy.get("version"),
                "factor_count": len(strategy.get("factors") or []),
                "portfolio_method": (strategy.get("portfolio") or {}).get("method"),
                "valid": validation.get("valid"),
            },
            ["strategy DSL definition loaded"],
            self._clean_warnings(validation.get("warnings")),
            ["run strategy-validate", "run strategy-run offline"],
            [],
            ["Strategy definitions are reproducibility metadata, not investment advice."],
        )

    def _export_strategy_validation(self, report: dict[str, Any], generated_from: str) -> AgentExport:
        return self._base_export(
            "strategy_validation",
            generated_from,
            f"Strategy validation {'passed' if report.get('valid') else 'failed'} for {report.get('strategy_name')}.",
            {
                "strategy_name": report.get("strategy_name"),
                "strategy_version": report.get("strategy_version"),
                "valid": report.get("valid"),
                "errors": report.get("errors"),
                "gates": report.get("gates"),
            },
            ["validation gates checked"],
            self._clean_warnings(report.get("warnings")) + [f"ERROR: {error}" for error in report.get("errors", [])],
            ["fix validation errors before research runs", "run walk-forward if required"],
            [],
            ["Validation gates are deterministic checks, not return guarantees."],
        )

    def _export_strategy_run(self, report: dict[str, Any], generated_from: str) -> AgentExport:
        summary = report.get("trade_sim_summary") or {}
        return self._base_export(
            "strategy_run",
            generated_from,
            f"Strategy {report.get('strategy_name')} ran through offline historical simulation.",
            {
                "strategy_name": report.get("strategy_name"),
                "strategy_version": report.get("strategy_version"),
                "status": report.get("status"),
                "final_equity": summary.get("final_equity"),
                "total_return": summary.get("total_return"),
                "max_drawdown": summary.get("max_drawdown"),
                "trade_count": summary.get("trade_count"),
                "trade_sim_report_path": (report.get("artifacts") or {}).get("trade_sim_report_path"),
            },
            ["strategy DSL orchestrated existing engines"],
            self._clean_warnings(report.get("warnings")),
            ["review trade simulation report", "run walk-forward validation", "inspect strategy validation gates"],
            [],
            ["Strategy runs are offline research simulation only, not live trading."],
        )

    def _export_strategy_gate(self, report: dict[str, Any], generated_from: str) -> AgentExport:
        gates = report.get("gate_results") or []
        by_status = (report.get("evidence_summary") or {}).get("by_status") or {}
        failed = [gate.get("gate_name") for gate in gates if gate.get("status") in {"FAIL", "REJECTED"}]
        warning_gates = [gate.get("gate_name") for gate in gates if gate.get("status") == "WARNING"]
        return self._base_export(
            "strategy_gate",
            generated_from,
            f"Strategy gates completed with overall status {report.get('overall_status')}.",
            {
                "strategy_name": report.get("strategy_name"),
                "strategy_version": report.get("strategy_version"),
                "overall_status": report.get("overall_status"),
                "gate_count": len(gates),
                "by_status": by_status,
                "warning_gates": warning_gates,
                "rejection_reasons": report.get("rejection_reasons") or [],
            },
            [
                "strategy gate report is quality control for offline research readiness",
                f"{len(failed)} gates failed or rejected" if failed else "no failed or rejected gates",
            ],
            self._clean_warnings(report.get("warnings")) + [f"REJECTION: {reason}" for reason in report.get("rejection_reasons", [])],
            report.get("recommended_next_checks") or ["review weak gates before relying on the strategy research"],
            [],
            [
                "Gates are deterministic diagnostics, not investment advice.",
                "Gate reports do not submit orders or mutate live accounts.",
            ],
        )

    def _base_export(
        self,
        report_type: str,
        generated_from: str,
        summary: str,
        key_metrics: dict[str, Any] | None = None,
        key_findings: list[str] | None = None,
        warnings: list[str] | None = None,
        recommended_next_steps: list[str] | None = None,
        action_candidates: list[str] | None = None,
        data_quality_notes: list[str] | None = None,
    ) -> AgentExport:
        return AgentExport(
            report_type=report_type,
            generated_from=generated_from,
            summary=summary,
            key_metrics=key_metrics or {},
            key_findings=self._dedupe(key_findings or []),
            warnings=self._dedupe(warnings or []),
            recommended_next_steps=self._dedupe(recommended_next_steps or []),
            action_candidates=self._dedupe(action_candidates or []),
            data_quality_notes=self._dedupe(data_quality_notes or []),
            visualization_paths=self._visualization_paths(generated_from),
        )

    def _performance_warnings(self, total_return: Any, sharpe: Any, drawdown: Any) -> list[str]:
        warnings = []
        total = self._num(total_return)
        sharpe_value = self._num(sharpe)
        drawdown_value = self._num(drawdown)
        if drawdown_value is not None and drawdown_value <= -0.30:
            warnings.append("WARN_EXTREME_DRAWDOWN")
        if total is not None and sharpe_value is not None and total < 0 and sharpe_value > 0:
            warnings.append("WARN_SHARPE_RETURN_MISMATCH")
        return warnings

    def _exclusion_notes(self, report: dict[str, Any]) -> list[str]:
        excluded = report.get("excluded_symbols") or []
        reasons = report.get("exclusion_reasons") or {}
        if not excluded:
            return []
        notes = [f"excluded_symbols: {len(excluded)}"]
        for symbol in list(excluded)[:5]:
            reason = reasons.get(symbol) if isinstance(reasons, dict) else None
            notes.append(f"{symbol}: {reason or 'excluded'}")
        return notes

    def _best_decay_horizon(self, decay: dict[str, Any]) -> str | None:
        best = None
        best_value = None
        for horizon, values in decay.items():
            value = values.get("ic") if isinstance(values, dict) else None
            number = self._num(value)
            if number is None:
                continue
            if best_value is None or number > best_value:
                best = horizon
                best_value = number
        return best

    def _trim_export(self, export: dict[str, Any], max_tokens: int) -> dict[str, Any]:
        trimmed = json.loads(json.dumps(export, default=str))
        priority_order = ["data_quality_notes", "visualization_paths", "action_candidates", "key_findings", "recommended_next_steps", "warnings", "key_metrics"]
        for key in priority_order:
            if self._estimate_tokens(trimmed) <= max_tokens:
                break
            value = trimmed.get(key)
            if isinstance(value, list) and len(value) > 3:
                trimmed[key] = value[:3]
            elif isinstance(value, dict) and len(value) > 6:
                trimmed[key] = {item_key: value[item_key] for item_key in list(value)[:6]}
        if self._estimate_tokens(trimmed) > max_tokens:
            trimmed["summary"] = str(trimmed.get("summary", ""))[: max(80, max_tokens * 3)]
        return trimmed

    @staticmethod
    def _render_text(export: dict[str, Any]) -> str:
        lines = [
            f"report_type: {export['report_type']}",
            f"generated_from: {export['generated_from']}",
            f"summary: {export['summary']}",
            "key_metrics:",
        ]
        lines.extend(f"- {key}: {AgentExporter._stringify(value)}" for key, value in export["key_metrics"].items())
        for section in ("key_findings", "warnings", "recommended_next_steps", "action_candidates", "data_quality_notes", "visualization_paths"):
            lines.append(f"{section}:")
            lines.extend(f"- {item}" for item in export.get(section, []))
        return "\n".join(lines) + "\n"

    @staticmethod
    def _render_markdown(export: dict[str, Any]) -> str:
        lines = [
            f"# Agent Export: {export['report_type']}",
            "",
            f"**Generated from:** `{export['generated_from']}`",
            "",
            f"## Summary\n{export['summary']}",
            "",
            "## Key Metrics",
        ]
        lines.extend(f"- `{key}`: {AgentExporter._stringify(value)}" for key, value in export["key_metrics"].items())
        for title, key in (
            ("Key Findings", "key_findings"),
            ("Warnings", "warnings"),
            ("Recommended Next Steps", "recommended_next_steps"),
            ("Action Candidates", "action_candidates"),
            ("Data Quality Notes", "data_quality_notes"),
            ("Visualization Paths", "visualization_paths"),
        ):
            lines.extend(["", f"## {title}"])
            values = export.get(key, [])
            lines.extend(f"- {value}" for value in values)
            if not values:
                lines.append("- None")
        return "\n".join(lines) + "\n"

    @staticmethod
    def _stringify(value: Any) -> str:
        if isinstance(value, float):
            return f"{value:.6g}"
        if isinstance(value, (dict, list)):
            return json.dumps(value, sort_keys=True)
        return str(value)

    @staticmethod
    def _estimate_tokens(value: Any) -> int:
        text = json.dumps(value, default=str, sort_keys=True)
        return max(1, int(len(text.split()) * 1.3))

    @staticmethod
    def _format_pct(value: Any) -> str:
        number = AgentExporter._num(value)
        return "N/A" if number is None else f"{number * 100:.2f}%"

    @staticmethod
    def _round_mapping(values: dict[str, Any]) -> dict[str, Any]:
        output = {}
        for key in sorted(values):
            number = AgentExporter._num(values[key])
            output[key] = round(number, 6) if number is not None else values[key]
        return output

    @staticmethod
    def _clean_warnings(warnings: Any) -> list[str]:
        if not warnings:
            return []
        cleaned = []
        if isinstance(warnings, list):
            for warning in warnings:
                if isinstance(warning, dict):
                    cleaned.append(str(warning.get("code") or warning.get("reason") or warning))
                else:
                    text = str(warning)
                    cleaned.append(text if text.startswith("WARN_") else f"SOURCE_WARNING: {text}")
        else:
            text = str(warnings)
            cleaned.append(text if text.startswith("WARN_") else f"SOURCE_WARNING: {text}")
        return cleaned

    @staticmethod
    def _visualization_paths(generated_from: str) -> list[str]:
        if generated_from == "<memory>":
            return []
        report_path = Path(generated_from)
        charts_dir = report_path.parent / "charts"
        if not charts_dir.exists():
            return []
        paths = []
        for extension in ("png", "svg", "html"):
            paths.extend(charts_dir.glob(f"{report_path.stem}_*.{extension}"))
        return sorted(str(path) for path in paths if not path.name.endswith("_dashboard.png"))

    @staticmethod
    def _dedupe(values: list[str]) -> list[str]:
        output = []
        seen = set()
        for value in values:
            text = str(value)
            if text and text not in seen:
                output.append(text)
                seen.add(text)
        return output

    @staticmethod
    def _num(value: Any) -> float | None:
        try:
            if value is None:
                return None
            return float(value)
        except (TypeError, ValueError):
            return None
