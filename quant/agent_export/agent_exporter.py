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

    def detect_report_type(self, report: dict[str, Any]) -> str:
        if {"summary_metrics", "attribution", "robustness_diagnostics"}.issubset(report):
            return "strategy_eval"
        if "factor" in report and "holding_period" in report and "long_short_return" in report:
            return "factor_backtest"
        if "factor" in report and ("forward_days" in report or "ic_mean" in report) and "decay" in report:
            return "factor_eval"
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
        metrics = {
            "factor": report.get("factor"),
            "ic_mean": ic,
            "rank_ic_mean": rank_ic,
            "icir": icir,
            "ic_count": report.get("ic_count"),
            "best_horizon": best_horizon,
            "spread_return": report.get("spread_return"),
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
            "final_cash": report.get("final_cash"),
        }
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
        priority_order = ["data_quality_notes", "action_candidates", "key_findings", "recommended_next_steps", "warnings", "key_metrics"]
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
        for section in ("key_findings", "warnings", "recommended_next_steps", "action_candidates", "data_quality_notes"):
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
