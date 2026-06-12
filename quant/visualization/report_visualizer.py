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
}

EXPECTED_CHARTS_BY_REPORT_TYPE = {
    "trade_sim": {"equity_curve", "cash_curve", "drawdown_curve", "monthly_returns", "cost_accumulation"},
    "backtest": {"equity_curve", "drawdown_curve", "monthly_returns"},
    "strategy_eval": {"return_attribution", "top_contributors", "top_detractors", "risk_metrics_summary"},
    "factor_eval": {"ic_history", "rank_ic_history", "ic_distribution", "quintile_returns", "factor_decay"},
    "factor_backtest": {"long_leg_return", "short_leg_return", "long_short_return", "drawdown", "turnover"},
    "portfolio_construction": {"target_weights", "risk_contribution", "volatility_contribution", "correlation_matrix"},
    "walk_forward": {"fold_returns", "train_vs_test_return", "train_vs_test_sharpe", "factor_stability_ranking", "overfit_diagnostics"},
    "risk": {"risk_summary", "top_holdings"},
    "fundamental_coverage": {"statement_coverage"},
    "fundamental_quality": {"warnings_by_reason"},
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
        costs = self._cumulative_costs(report.get("trades") or [])
        monthly = self._monthly_returns(equity)
        charts.extend(
            self._keep(
                builder.line_chart(prefix, "equity_curve", "Equity Curve", equity),
                builder.line_chart(prefix, "cash_curve", "Cash Curve", cash),
                builder.line_chart(prefix, "drawdown_curve", "Drawdown Curve", self._drawdown(equity)),
                builder.bar_chart(prefix, "monthly_returns", "Monthly Returns", monthly),
                builder.line_chart(prefix, "cost_accumulation", "Cost Accumulation", costs),
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
