"""Generate visual chart reports from existing JSON reports."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from quant.agent_export.agent_exporter import AgentExporter
from quant.visualization.chart_builder import ChartArtifact, ChartBuilder


SUPPORTED_REPORT_TYPES = {
    "trade_sim",
    "backtest",
    "strategy_eval",
    "factor_eval",
    "factor_backtest",
    "portfolio_construction",
    "walk_forward",
    "risk",
    "fundamental_coverage",
    "fundamental_quality",
    "multi_factor",
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
}

EXPECTED_CHARTS_BY_REPORT_TYPE = {
    "trade_sim": {"equity_curve", "cash_curve", "drawdown_curve", "monthly_returns", "cost_accumulation", "slippage", "cost_breakdown", "rejected_trades", "liquidity_usage"},
    "backtest": {"equity_curve", "drawdown_curve", "monthly_returns"},
    "strategy_eval": {"return_attribution", "top_contributors", "top_detractors", "risk_metrics_summary"},
    "factor_eval": {"ic_history", "rank_ic_history", "ic_distribution", "quintile_returns", "factor_decay"},
    "factor_backtest": {"long_leg_return", "short_leg_return", "long_short_return", "drawdown", "turnover"},
    "portfolio_construction": {"target_weights", "risk_contribution", "volatility_contribution", "correlation_matrix"},
    "walk_forward": {"fold_returns", "train_vs_test_return", "train_vs_test_sharpe", "factor_stability_ranking", "overfit_diagnostics"},
    "risk": {"risk_summary", "top_holdings"},
    "fundamental_coverage": {"statement_coverage"},
    "fundamental_quality": {"warnings_by_reason"},
    "multi_factor": {"family_contribution", "factor_contribution", "confidence", "stability_ranking"},
    "factor_store_summary": {"factor_store_counts"},
    "factor_history": {"ic_history", "rank_ic_history", "stability_history", "coverage_history"},
    "factor_rank": {"factor_ranking", "stability_ranking", "coverage_ranking"},
    "regime_detection": {"regime_timeline", "regime_frequency", "regime_confidence"},
    "regime_history": {"regime_timeline", "regime_frequency", "regime_confidence"},
    "regime_report": {"regime_frequency", "factor_performance_by_regime"},
    "regime_rank": {"factor_performance_by_regime", "regime_stability"},
    "research_run": {"pipeline_status", "trade_simulation", "factor_summary", "artifact_counts"},
    "research_status": {"latest_run"},
    "research_history": {"run_status"},
}


@dataclass(frozen=True)
class VisualizationResult:
    report_type: str
    source_report: str
    output_dir: str
    charts: list[dict[str, str]]
    dashboard_path: str
    warnings: list[str]

    def to_report(self) -> dict:
        return {
            "report_type": self.report_type,
            "source_report": self.source_report,
            "output_dir": self.output_dir,
            "charts": self.charts,
            "dashboard_path": self.dashboard_path,
            "warnings": self.warnings,
        }


class ReportVisualizer:
    """Build deterministic SVG, PNG, and HTML dashboards from report JSON."""

    def __init__(self, output_dir: str | Path = "reports/charts") -> None:
        self.output_dir = Path(output_dir)
        self.exporter = AgentExporter()

    def visualize_file(self, report_path: str | Path, output_dir: str | Path | None = None) -> VisualizationResult:
        path = Path(report_path)
        try:
            report = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise ValueError(f"report file not found: {path}") from exc
        except json.JSONDecodeError as exc:
            raise ValueError(f"report file is not valid JSON: {path}") from exc
        if not isinstance(report, dict):
            raise ValueError("report must contain a JSON object")

        report_type = self.exporter.detect_report_type(report)
        if report_type not in SUPPORTED_REPORT_TYPES:
            raise ValueError(f"unsupported report type for visualization: {report_type}")

        builder = ChartBuilder(output_dir or self.output_dir)
        prefix = self._prefix(path)
        charts = getattr(self, f"_charts_{report_type}")(builder, prefix, report)
        metrics = self._metrics_for_dashboard(report_type, report)
        warnings = self._warnings(report) + self._chart_warnings(report_type, charts)
        notes = self._notes(report)
        dashboard = builder.dashboard(
            prefix=prefix,
            title=f"{report_type} visualization",
            report_type=report_type,
            metrics=metrics,
            charts=charts,
            warnings=warnings,
            notes=notes,
        )
        return VisualizationResult(
            report_type=report_type,
            source_report=str(path),
            output_dir=str(builder.output_dir),
            charts=[chart.to_dict() for chart in charts],
            dashboard_path=str(dashboard),
            warnings=warnings,
        )

    def _charts_trade_sim(self, builder: ChartBuilder, prefix: str, report: dict[str, Any]) -> list[ChartArtifact]:
        charts = []
        equity = self._series(report.get("equity_curve"), "date", "equity")
        cash = self._series(report.get("cash_curve"), "date", "cash")
        trade_records = self._trade_sim_trade_records(report)
        costs = self._cumulative_costs(trade_records)
        monthly = self._monthly_returns(equity)
        realism = report.get("market_realism") or {}
        charts.extend(
            self._keep(
                builder.line_chart(prefix, "equity_curve", "Equity Curve", equity),
                builder.line_chart(prefix, "cash_curve", "Cash Curve", cash),
                builder.line_chart(prefix, "drawdown_curve", "Drawdown Curve", self._drawdown(equity)),
                builder.bar_chart(prefix, "monthly_returns", "Monthly Returns", monthly),
                builder.line_chart(prefix, "cost_accumulation", "Cost Accumulation", costs),
                builder.bar_chart(prefix, "slippage", "Slippage", self._cost_component_by_date(trade_records, "slippage_cost")),
                builder.bar_chart(prefix, "cost_breakdown", "Cost Breakdown", self._cost_breakdown(report)),
                builder.bar_chart(prefix, "rejected_trades", "Rejected Trades", self._rejected_by_symbol(report.get("rejected_trades") or [])),
                builder.bar_chart(prefix, "liquidity_usage", "Liquidity Usage", self._liquidity_usage(trade_records, realism)),
            )
        )
        return charts

    def _charts_backtest(self, builder: ChartBuilder, prefix: str, report: dict[str, Any]) -> list[ChartArtifact]:
        equity = self._series(report.get("equity_curve"), "date", "equity")
        if not equity:
            equity = self._series(report.get("equity_curve"), "date", "value")
        return self._keep(
            builder.line_chart(prefix, "equity_curve", "Equity Curve", equity),
            builder.line_chart(prefix, "drawdown_curve", "Drawdown Curve", self._drawdown(equity)),
            builder.bar_chart(prefix, "monthly_returns", "Monthly Returns", self._monthly_returns(equity)),
        )

    def _charts_strategy_eval(self, builder: ChartBuilder, prefix: str, report: dict[str, Any]) -> list[ChartArtifact]:
        attribution = report.get("attribution") or {}
        return_attr = attribution.get("return_attribution") or {}
        by_symbol = return_attr.get("by_symbol") or {}
        top_pos = self._items_to_mapping(attribution.get("top_positive_contributors"), "symbol", "contribution")
        top_neg = self._items_to_mapping(attribution.get("top_negative_contributors"), "symbol", "contribution")
        summary = report.get("summary_metrics") or {}
        risk_metrics = {
            "volatility": summary.get("annual_volatility"),
            "max_drawdown": summary.get("max_drawdown"),
            "turnover": summary.get("turnover"),
            "total_cost": summary.get("total_cost"),
            "gross_exposure": summary.get("gross_exposure"),
            "net_exposure": summary.get("net_exposure"),
        }
        return self._keep(
            builder.bar_chart(prefix, "return_attribution", "Return Attribution", by_symbol),
            builder.bar_chart(prefix, "top_contributors", "Top Contributors", top_pos),
            builder.bar_chart(prefix, "top_detractors", "Top Detractors", top_neg),
            builder.bar_chart(prefix, "risk_metrics_summary", "Risk Metrics Summary", risk_metrics),
        )

    def _charts_factor_eval(self, builder: ChartBuilder, prefix: str, report: dict[str, Any]) -> list[ChartArtifact]:
        ic_history, rank_history = self._factor_eval_history(report.get("observations") or [])
        ic_values = {str(index + 1): value for index, (_, value) in enumerate(ic_history)}
        quintiles = report.get("quintiles") or {}
        decay = {
            horizon: values.get("ic")
            for horizon, values in (report.get("decay") or {}).items()
            if isinstance(values, dict)
        }
        return self._keep(
            builder.line_chart(prefix, "ic_history", "IC History", ic_history),
            builder.line_chart(prefix, "rank_ic_history", "Rank IC History", rank_history),
            builder.bar_chart(prefix, "ic_distribution", "IC Distribution", ic_values),
            builder.bar_chart(prefix, "quintile_returns", "Quintile Returns", quintiles),
            builder.line_chart(prefix, "factor_decay", "Factor Decay", list(decay.items())),
        )

    def _charts_factor_backtest(self, builder: ChartBuilder, prefix: str, report: dict[str, Any]) -> list[ChartArtifact]:
        periods = report.get("periods") or []
        long_leg = self._series(periods, "signal_date", "long_leg_return")
        short_leg = self._series(periods, "signal_date", "short_leg_return")
        spread = self._series(periods, "signal_date", "long_short_return")
        turnover = self._series(periods, "signal_date", "turnover")
        return self._keep(
            builder.line_chart(prefix, "long_leg_return", "Long Leg Return", long_leg),
            builder.line_chart(prefix, "short_leg_return", "Short Leg Return", short_leg),
            builder.line_chart(prefix, "long_short_return", "Long Short Return", spread),
            builder.line_chart(prefix, "drawdown", "Long Short Drawdown", self._drawdown_from_returns(spread)),
            builder.line_chart(prefix, "turnover", "Turnover", turnover),
        )

    def _charts_portfolio_construction(self, builder: ChartBuilder, prefix: str, report: dict[str, Any]) -> list[ChartArtifact]:
        weights = report.get("target_weights") or {}
        risk = report.get("risk_contribution_pct") or report.get("risk_contribution_pct_by_symbol") or {}
        volatility = report.get("volatility") or report.get("volatility_by_symbol") or {}
        correlation = report.get("correlation_matrix") or report.get("covariance_matrix") or {}
        return self._keep(
            builder.pie_chart(prefix, "target_weights", "Target Weights", weights),
            builder.bar_chart(prefix, "risk_contribution", "Risk Contribution", risk),
            builder.bar_chart(prefix, "volatility_contribution", "Volatility Contribution", volatility),
            builder.heatmap(prefix, "correlation_matrix", "Correlation Matrix", correlation),
        )

    def _charts_walk_forward(self, builder: ChartBuilder, prefix: str, report: dict[str, Any]) -> list[ChartArtifact]:
        folds = report.get("folds") or []
        train_returns = {str(fold.get("fold_id", index + 1)): self._fold_value(fold, "train_return", "total_return") for index, fold in enumerate(folds)}
        test_returns = {str(fold.get("fold_id", index + 1)): self._fold_value(fold, "test_return", "total_return") for index, fold in enumerate(folds)}
        train_sharpe = {str(fold.get("fold_id", index + 1)): self._fold_value(fold, "train_sharpe", "sharpe") for index, fold in enumerate(folds)}
        test_sharpe = {str(fold.get("fold_id", index + 1)): self._fold_value(fold, "test_sharpe", "sharpe") for index, fold in enumerate(folds)}
        stability = {
            item.get("factor", f"factor_{index + 1}"): item.get("stability_score", item.get("score", index + 1))
            for index, item in enumerate(((report.get("stability_analysis") or {}).get("factor_stability_ranking") or []))
            if isinstance(item, dict)
        }
        warning_counts = self._warning_counts(report.get("warnings") or [])
        return self._keep(
            builder.bar_chart(prefix, "fold_returns", "Fold Test Returns", test_returns),
            builder.bar_chart(prefix, "train_vs_test_return", "Train vs Test Return", self._paired_average(train_returns, test_returns)),
            builder.bar_chart(prefix, "train_vs_test_sharpe", "Train vs Test Sharpe", self._paired_average(train_sharpe, test_sharpe)),
            builder.bar_chart(prefix, "factor_stability_ranking", "Factor Stability Ranking", stability),
            builder.bar_chart(prefix, "overfit_diagnostics", "Overfit Diagnostics", warning_counts),
        )

    def _charts_risk(self, builder: ChartBuilder, prefix: str, report: dict[str, Any]) -> list[ChartArtifact]:
        metrics = {
            "risk_score": report.get("risk_score"),
            "single_stock": report.get("single_stock_concentration_pct"),
            "industry": report.get("industry_concentration_pct"),
            "cash": report.get("cash_weight_pct"),
            "top_5": report.get("top_5_holdings_pct"),
        }
        holdings = self._items_to_mapping(report.get("holdings"), "symbol", "market_value")
        return self._keep(
            builder.bar_chart(prefix, "risk_summary", "Risk Summary", metrics),
            builder.bar_chart(prefix, "top_holdings", "Top Holdings", holdings),
        )

    def _charts_fundamental_coverage(self, builder: ChartBuilder, prefix: str, report: dict[str, Any]) -> list[ChartArtifact]:
        coverage = report.get("coverage") or {}
        return self._keep(
            builder.bar_chart(prefix, "statement_coverage", "Statement Coverage", coverage.get("statement_coverage") or {}),
        )

    def _charts_fundamental_quality(self, builder: ChartBuilder, prefix: str, report: dict[str, Any]) -> list[ChartArtifact]:
        return self._keep(
            builder.bar_chart(prefix, "warnings_by_reason", "Warnings By Reason", self._warning_counts(report.get("warnings") or [])),
        )

    def _charts_multi_factor(self, builder: ChartBuilder, prefix: str, report: dict[str, Any]) -> list[ChartArtifact]:
        scores = [item for item in (report.get("scores") or []) if isinstance(item, dict)]
        top = sorted(
            scores,
            key=lambda item: (float(item.get("final_alpha_score") or -999), str(item.get("symbol"))),
            reverse=True,
        )[:5]
        family_contribution = self._average_nested(top, "family_contributions")
        factor_contribution = self._average_nested(top, "factor_contributions")
        confidence = {
            item.get("symbol", f"symbol_{index + 1}"): item.get("overall_confidence")
            for index, item in enumerate(top)
        }
        stability = {
            factor: values.get("score")
            for factor, values in (report.get("stability") or {}).items()
            if isinstance(values, dict)
        }
        return self._keep(
            builder.bar_chart(prefix, "family_contribution", "Family Contribution", family_contribution),
            builder.bar_chart(prefix, "factor_contribution", "Factor Contribution", factor_contribution),
            builder.bar_chart(prefix, "confidence", "Confidence", confidence),
            builder.bar_chart(prefix, "stability_ranking", "Stability Ranking", stability),
        )

    def _charts_factor_store_summary(self, builder: ChartBuilder, prefix: str, report: dict[str, Any]) -> list[ChartArtifact]:
        return self._keep(
            builder.bar_chart(prefix, "factor_store_counts", "Factor Store Counts", report.get("counts") or {}),
        )

    def _charts_factor_history(self, builder: ChartBuilder, prefix: str, report: dict[str, Any]) -> list[ChartArtifact]:
        evaluations = report.get("evaluation_history") or []
        stability = report.get("stability_history") or []
        return self._keep(
            builder.line_chart(prefix, "ic_history", "IC History", self._series(evaluations, "evaluation_date", "ic")),
            builder.line_chart(prefix, "rank_ic_history", "RankIC History", self._series(evaluations, "evaluation_date", "rank_ic")),
            builder.line_chart(prefix, "stability_history", "Stability History", self._series(stability, "timestamp", "stability_score")),
            builder.line_chart(prefix, "coverage_history", "Coverage History", self._series(evaluations, "evaluation_date", "coverage")),
        )

    def _charts_factor_rank(self, builder: ChartBuilder, prefix: str, report: dict[str, Any]) -> list[ChartArtifact]:
        top = self._items_to_mapping(report.get("top_factors"), "factor_name", "health_score")
        stable = self._items_to_mapping(report.get("most_stable_factors"), "factor_name", "stability_score")
        coverage = self._items_to_mapping(report.get("top_factors"), "factor_name", "coverage")
        return self._keep(
            builder.bar_chart(prefix, "factor_ranking", "Factor Ranking", top),
            builder.bar_chart(prefix, "stability_ranking", "Stability Ranking", stable),
            builder.bar_chart(prefix, "coverage_ranking", "Coverage Ranking", coverage),
        )

    def _charts_regime_detection(self, builder: ChartBuilder, prefix: str, report: dict[str, Any]) -> list[ChartArtifact]:
        observations = report.get("observations") or []
        return self._keep(
            builder.line_chart(prefix, "regime_timeline", "Regime Timeline", self._regime_timeline(observations)),
            builder.bar_chart(prefix, "regime_frequency", "Regime Frequency", report.get("regime_counts") or {}),
            builder.line_chart(prefix, "regime_confidence", "Regime Confidence", self._series(observations, "date", "confidence")),
        )

    def _charts_regime_history(self, builder: ChartBuilder, prefix: str, report: dict[str, Any]) -> list[ChartArtifact]:
        history = list(reversed(report.get("history") or []))
        return self._keep(
            builder.line_chart(prefix, "regime_timeline", "Regime Timeline", self._regime_timeline(history)),
            builder.bar_chart(prefix, "regime_frequency", "Regime Frequency", report.get("regime_counts") or {}),
            builder.line_chart(prefix, "regime_confidence", "Regime Confidence", self._series(history, "date", "confidence")),
        )

    def _charts_regime_report(self, builder: ChartBuilder, prefix: str, report: dict[str, Any]) -> list[ChartArtifact]:
        return self._keep(
            builder.bar_chart(prefix, "regime_frequency", "Regime Frequency", report.get("regime_counts") or {}),
            builder.bar_chart(prefix, "factor_performance_by_regime", "Factor Performance By Regime", self._factor_regime_mapping(report)),
        )

    def _charts_regime_rank(self, builder: ChartBuilder, prefix: str, report: dict[str, Any]) -> list[ChartArtifact]:
        return self._keep(
            builder.bar_chart(prefix, "factor_performance_by_regime", "Best Factor By Regime", self._best_by_regime_mapping(report)),
            builder.bar_chart(prefix, "regime_stability", "Regime Stability", self._items_to_mapping(report.get("most_stable_across_regimes"), "factor_name", "stability")),
        )

    def _charts_research_run(self, builder: ChartBuilder, prefix: str, report: dict[str, Any]) -> list[ChartArtifact]:
        summary = report.get("daily_research_summary") or {}
        trade = summary.get("trade_sim_summary") or {}
        factor_stability = summary.get("factor_stability_summary") or {}
        factor_scores = {
            factor: values.get("icir")
            for factor, values in factor_stability.items()
            if isinstance(values, dict)
        }
        artifact_counts = {
            "reports": len(report.get("generated_reports") or []),
            "visualizations": len(report.get("generated_visualizations") or []),
            "agent_exports": len(report.get("agent_exports") or []),
        }
        statuses = {}
        for step in report.get("pipeline_steps") or []:
            status = str(step.get("status") or "UNKNOWN")
            statuses[status] = statuses.get(status, 0) + 1
        return self._keep(
            builder.bar_chart(prefix, "pipeline_status", "Pipeline Step Status", statuses),
            builder.bar_chart(
                prefix,
                "trade_simulation",
                "Trade Simulation Metrics",
                {
                    "return": trade.get("total_return"),
                    "drawdown": trade.get("max_drawdown"),
                    "cost": trade.get("total_cost"),
                },
            ),
            builder.bar_chart(prefix, "factor_summary", "Factor ICIR Summary", factor_scores),
            builder.bar_chart(prefix, "artifact_counts", "Generated Artifact Counts", artifact_counts),
        )

    def _charts_research_status(self, builder: ChartBuilder, prefix: str, report: dict[str, Any]) -> list[ChartArtifact]:
        latest = report.get("latest_run") or {}
        return self._keep(
            builder.bar_chart(prefix, "latest_run", "Latest Run", {"duration": latest.get("duration"), "trade_return": latest.get("trade_sim_return")}),
        )

    def _charts_research_history(self, builder: ChartBuilder, prefix: str, report: dict[str, Any]) -> list[ChartArtifact]:
        counts = (report.get("summary") or {}).get("status_counts") or {}
        return self._keep(builder.bar_chart(prefix, "run_status", "Run Status Counts", counts))

    @staticmethod
    def _series(items: Any, label_key: str, value_key: str) -> list[tuple[str, float]]:
        output = []
        if not isinstance(items, list):
            return output
        for item in items:
            if not isinstance(item, dict):
                continue
            value = item.get(value_key)
            if ReportVisualizer._finite(value):
                output.append((str(item.get(label_key, len(output) + 1)), float(value)))
        return output

    @staticmethod
    def _average_nested(items: list[dict[str, Any]], key: str) -> dict[str, float]:
        totals: dict[str, float] = {}
        counts: dict[str, int] = {}
        for item in items:
            values = item.get(key) or {}
            if not isinstance(values, dict):
                continue
            for label, value in values.items():
                if ReportVisualizer._finite(value):
                    totals[str(label)] = totals.get(str(label), 0.0) + float(value)
                    counts[str(label)] = counts.get(str(label), 0) + 1
        return {
            label: totals[label] / counts[label]
            for label in sorted(totals)
            if counts.get(label)
        }

    @staticmethod
    def _drawdown(points: list[tuple[str, float]]) -> list[tuple[str, float]]:
        output = []
        peak = None
        for label, value in points:
            peak = value if peak is None else max(peak, value)
            output.append((label, (value / peak - 1.0) if peak else 0.0))
        return output

    @staticmethod
    def _drawdown_from_returns(returns: list[tuple[str, float]]) -> list[tuple[str, float]]:
        equity = 1.0
        points = []
        for label, value in returns:
            equity *= 1.0 + value
            points.append((label, equity))
        return ReportVisualizer._drawdown(points)

    @staticmethod
    def _monthly_returns(points: list[tuple[str, float]]) -> dict[str, float]:
        by_month: dict[str, list[float]] = {}
        for label, value in points:
            by_month.setdefault(label[:7], []).append(value)
        output = {}
        for month, values in by_month.items():
            if len(values) >= 2 and values[0] != 0:
                output[month] = values[-1] / values[0] - 1.0
        return output

    @staticmethod
    def _cumulative_costs(trades: list[dict]) -> list[tuple[str, float]]:
        total = 0.0
        output = []
        for trade in trades:
            if not isinstance(trade, dict):
                continue
            cost = trade.get("cost", trade.get("total_cost"))
            if ReportVisualizer._finite(cost):
                total += float(cost)
                output.append((str(trade.get("date") or trade.get("execution_date") or len(output) + 1), total))
        return output

    @staticmethod
    def _trade_sim_trade_records(report: dict[str, Any]) -> list[dict]:
        records: list[dict] = []
        for trade in report.get("trades") or []:
            if isinstance(trade, dict):
                records.append(trade)
        for event in report.get("rebalance_events") or []:
            if not isinstance(event, dict):
                continue
            for trade in event.get("executed_trades") or []:
                if isinstance(trade, dict):
                    records.append(trade)
        return records

    @staticmethod
    def _cost_component_by_date(trades: list[dict], key: str) -> dict[str, float]:
        output: dict[str, float] = {}
        for trade in trades:
            if not isinstance(trade, dict):
                continue
            date = str(trade.get("date") or trade.get("execution_date") or "unknown")
            if ReportVisualizer._finite(trade.get(key)):
                output[date] = output.get(date, 0.0) + float(trade[key])
        return output

    @staticmethod
    def _cost_breakdown(report: dict[str, Any]) -> dict[str, float]:
        realism = report.get("market_realism") or {}
        return {
            "commission_and_fees": float(report.get("total_cost") or 0.0)
            - float(realism.get("total_slippage") or 0.0)
            - float(realism.get("total_market_impact") or 0.0)
            - float(realism.get("total_liquidity_cost") or 0.0),
            "slippage": float(realism.get("total_slippage") or 0.0),
            "market_impact": float(realism.get("total_market_impact") or 0.0),
            "liquidity": float(realism.get("total_liquidity_cost") or 0.0),
        }

    @staticmethod
    def _rejected_by_symbol(rejected: list[dict]) -> dict[str, float]:
        output: dict[str, float] = {}
        for trade in rejected:
            if not isinstance(trade, dict):
                continue
            symbol = str(trade.get("symbol") or "UNKNOWN")
            output[symbol] = output.get(symbol, 0.0) + float(trade.get("rejected_quantity") or 0.0)
        return output

    @staticmethod
    def _liquidity_usage(trades: list[dict], realism: dict[str, Any]) -> dict[str, float]:
        output: dict[str, float] = {}
        for trade in trades:
            if isinstance(trade, dict) and ReportVisualizer._finite(trade.get("adv_participation")):
                output[str(trade.get("symbol") or len(output) + 1)] = max(
                    output.get(str(trade.get("symbol") or len(output) + 1), 0.0),
                    float(trade["adv_participation"]),
                )
        if not output and realism.get("largest_constrained_trades"):
            for trade in realism["largest_constrained_trades"]:
                if isinstance(trade, dict) and ReportVisualizer._finite(trade.get("adv_participation")):
                    output[str(trade.get("symbol") or len(output) + 1)] = float(trade["adv_participation"])
        return output

    @staticmethod
    def _factor_eval_history(observations: list[dict]) -> tuple[list[tuple[str, float]], list[tuple[str, float]]]:
        by_date: dict[str, list[tuple[float, float]]] = {}
        for row in observations:
            if not isinstance(row, dict):
                continue
            factor = row.get("factor_value")
            future = row.get("future_return")
            if ReportVisualizer._finite(factor) and ReportVisualizer._finite(future):
                by_date.setdefault(str(row.get("signal_date")), []).append((float(factor), float(future)))
        ic_history = []
        rank_history = []
        for date in sorted(by_date):
            pairs = by_date[date]
            if len(pairs) < 2:
                continue
            xs = [pair[0] for pair in pairs]
            ys = [pair[1] for pair in pairs]
            ic_history.append((date, ReportVisualizer._corr(xs, ys)))
            rank_history.append((date, ReportVisualizer._corr(ReportVisualizer._ranks(xs), ReportVisualizer._ranks(ys))))
        return ic_history, rank_history

    @staticmethod
    def _corr(xs: list[float], ys: list[float]) -> float:
        x_mean = sum(xs) / len(xs)
        y_mean = sum(ys) / len(ys)
        numerator = sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, ys, strict=False))
        x_var = sum((x - x_mean) ** 2 for x in xs)
        y_var = sum((y - y_mean) ** 2 for y in ys)
        denominator = math.sqrt(x_var * y_var)
        return numerator / denominator if denominator else 0.0

    @staticmethod
    def _ranks(values: list[float]) -> list[float]:
        ordered = sorted((value, index) for index, value in enumerate(values))
        ranks = [0.0] * len(values)
        for rank, (_, index) in enumerate(ordered, start=1):
            ranks[index] = float(rank)
        return ranks

    @staticmethod
    def _items_to_mapping(items: Any, label_key: str, value_key: str) -> dict[str, float]:
        if isinstance(items, dict):
            return {str(key): float(value) for key, value in items.items() if ReportVisualizer._finite(value)}
        if not isinstance(items, list):
            return {}
        output = {}
        for item in items:
            if isinstance(item, dict) and ReportVisualizer._finite(item.get(value_key)):
                output[str(item.get(label_key, len(output) + 1))] = float(item[value_key])
        return output

    @staticmethod
    def _warning_counts(warnings: list[Any]) -> dict[str, float]:
        counts: dict[str, float] = {}
        for warning in warnings:
            text = str(warning.get("code") if isinstance(warning, dict) else warning)
            key = text.split(":")[0].split()[0]
            counts[key] = counts.get(key, 0.0) + 1.0
        return counts

    @staticmethod
    def _paired_average(first: dict[str, Any], second: dict[str, Any]) -> dict[str, float]:
        first_values = [float(value) for value in first.values() if ReportVisualizer._finite(value)]
        second_values = [float(value) for value in second.values() if ReportVisualizer._finite(value)]
        return {
            "train_average": sum(first_values) / len(first_values) if first_values else 0.0,
            "test_average": sum(second_values) / len(second_values) if second_values else 0.0,
        }

    @staticmethod
    def _fold_value(fold: dict[str, Any], direct_key: str, nested_key: str) -> Any:
        if direct_key in fold:
            return fold.get(direct_key)
        container = "train_metrics" if direct_key.startswith("train_") else "test_metrics"
        return (fold.get(container) or {}).get(nested_key)

    @staticmethod
    def _metrics_for_dashboard(report_type: str, report: dict[str, Any]) -> dict[str, Any]:
        if report_type == "strategy_eval":
            return report.get("summary_metrics") or {}
        if report_type == "walk_forward":
            return report.get("summary") or {}
        if report_type == "backtest":
            return report.get("metrics") or {}
        keys = ("strategy", "portfolio_method", "final_equity", "total_return", "max_drawdown", "total_cost", "trade_count", "risk_score", "factor", "ic_mean", "rank_ic_mean", "icir", "method")
        if report_type in {"fundamental_coverage", "fundamental_quality"}:
            return report.get("summary") or {}
        if report_type == "multi_factor":
            confidence = report.get("confidence") or {}
            return {
                "as_of_date": report.get("as_of_date"),
                "weighting_mode": report.get("weighting_mode"),
                "overall_confidence": confidence.get("overall_confidence"),
                "factor_count": len(report.get("factors") or []),
            }
        if report_type == "factor_store_summary":
            return report.get("counts") or {}
        if report_type == "factor_history":
            return {
                "factor": report.get("factor"),
                "evaluation_rows": len(report.get("evaluation_history") or []),
                "backtest_rows": len(report.get("backtest_history") or []),
                "stability_rows": len(report.get("stability_history") or []),
            }
        if report_type == "factor_rank":
            top = (report.get("top_factors") or [{}])[0]
            return {
                "top_factor": top.get("factor_name"),
                "top_factor_health": top.get("health_score"),
                "ranked_count": len(report.get("top_factors") or []),
            }
        if report_type in {"regime_detection", "regime_history", "regime_report", "regime_rank"}:
            current = report.get("current_regime") or {}
            return {
                "current_regime": current.get("regime"),
                "date": current.get("date"),
                "confidence": current.get("confidence"),
                "regime_count": len(report.get("regime_counts") or {}),
            }
        if report_type == "research_run":
            summary = report.get("daily_research_summary") or {}
            trade = summary.get("trade_sim_summary") or {}
            return {
                "status": report.get("status"),
                "current_regime": summary.get("current_regime"),
                "trade_sim_return": trade.get("total_return"),
                "generated_reports": len(report.get("generated_reports") or []),
            }
        if report_type == "research_status":
            latest = report.get("latest_run") or {}
            return {"status": report.get("status"), "latest_run": latest.get("run_id")}
        if report_type == "research_history":
            return (report.get("summary") or {}).get("status_counts") or {}
        return {key: report.get(key) for key in keys if key in report}

    @staticmethod
    def _warnings(report: dict[str, Any]) -> list[str]:
        warnings = report.get("warnings") or []
        if isinstance(warnings, list):
            return [str(warning.get("code") if isinstance(warning, dict) else warning) for warning in warnings]
        return [str(warnings)]

    @staticmethod
    def _chart_warnings(report_type: str, charts: list[ChartArtifact]) -> list[str]:
        expected = EXPECTED_CHARTS_BY_REPORT_TYPE.get(report_type, set())
        generated = {chart.chart_id for chart in charts}
        return [
            f"VISUALIZATION_SKIPPED_CHART: {chart_id} missing required report fields"
            for chart_id in sorted(expected - generated)
        ]

    @staticmethod
    def _notes(report: dict[str, Any]) -> list[str]:
        notes = report.get("interpretation_notes") or []
        return [str(note) for note in notes] if isinstance(notes, list) else [str(notes)]

    @staticmethod
    def _keep(*charts: ChartArtifact | None) -> list[ChartArtifact]:
        return [chart for chart in charts if chart is not None]

    @staticmethod
    def _finite(value: Any) -> bool:
        try:
            number = float(value)
            return math.isfinite(number)
        except (TypeError, ValueError):
            return False

    @staticmethod
    def _prefix(path: Path) -> str:
        return "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in path.stem)

    @staticmethod
    def _regime_timeline(items: list[dict[str, Any]]) -> list[tuple[str, float]]:
        order = {
            "UNKNOWN": 0,
            "LOW_VOL": 1,
            "RANGE_BOUND": 2,
            "BULL": 3,
            "TRENDING": 4,
            "RECOVERY": 5,
            "HIGH_VOL": 6,
            "BEAR": 7,
            "CRISIS": 8,
        }
        return [
            (str(item.get("date")), float(order.get(str(item.get("regime") or "UNKNOWN"), 0)))
            for item in items
            if item.get("date")
        ]

    @staticmethod
    def _factor_regime_mapping(report: dict[str, Any]) -> dict[str, float]:
        output = {}
        for regime, rows in (report.get("factor_performance_by_regime") or {}).items():
            if isinstance(rows, list) and rows:
                best = max(rows, key=lambda row: ReportVisualizer._safe_float(row.get("icir")))
                output[str(regime)] = ReportVisualizer._safe_float(best.get("icir"))
        return output

    @staticmethod
    def _best_by_regime_mapping(report: dict[str, Any]) -> dict[str, float]:
        output = {}
        for regime, rows in (report.get("best_by_regime") or {}).items():
            if isinstance(rows, list) and rows:
                output[str(regime)] = ReportVisualizer._safe_float(rows[0].get("health_score"))
        return output

    @staticmethod
    def _safe_float(value: Any) -> float:
        try:
            number = float(value)
            return number if math.isfinite(number) else 0.0
        except (TypeError, ValueError):
            return 0.0
