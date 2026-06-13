"""Trading, portfolio, risk, and walk-forward visualization extractors."""

from __future__ import annotations

from typing import Any

from quant.reports.visualization.chart_builder import ChartArtifact, ChartBuilder
from quant.reports.visualization.extractors.common import (
    drawdown,
    drawdown_from_returns,
    finite,
    fold_value,
    items_to_mapping,
    keep,
    monthly_returns,
    paired_average,
    series,
    warning_counts,
)
from quant.reports.visualization.specs import report_spec


def trade_sim_charts(builder: ChartBuilder, prefix: str, report: dict[str, Any]) -> list[ChartArtifact]:
    equity = series(report.get("equity_curve"), "date", "equity")
    cash = series(report.get("cash_curve"), "date", "cash")
    trade_records = _trade_sim_trade_records(report)
    realism = report.get("market_realism") or {}
    return keep(
        builder.line_chart(prefix, "equity_curve", "Equity Curve", equity),
        builder.line_chart(prefix, "cash_curve", "Cash Curve", cash),
        builder.line_chart(prefix, "drawdown_curve", "Drawdown Curve", drawdown(equity)),
        builder.bar_chart(prefix, "monthly_returns", "Monthly Returns", monthly_returns(equity)),
        builder.line_chart(prefix, "cost_accumulation", "Cost Accumulation", _cumulative_costs(trade_records)),
        builder.bar_chart(prefix, "slippage", "Slippage", _cost_component_by_date(trade_records, "slippage_cost")),
        builder.bar_chart(prefix, "cost_breakdown", "Cost Breakdown", _cost_breakdown(report)),
        builder.bar_chart(prefix, "rejected_trades", "Rejected Trades", _rejected_by_symbol(report.get("rejected_trades") or [])),
        builder.bar_chart(prefix, "liquidity_usage", "Liquidity Usage", _liquidity_usage(trade_records, realism)),
    )


def backtest_charts(builder: ChartBuilder, prefix: str, report: dict[str, Any]) -> list[ChartArtifact]:
    equity = series(report.get("equity_curve"), "date", "equity")
    if not equity:
        equity = series(report.get("equity_curve"), "date", "value")
    return keep(
        builder.line_chart(prefix, "equity_curve", "Equity Curve", equity),
        builder.line_chart(prefix, "drawdown_curve", "Drawdown Curve", drawdown(equity)),
        builder.bar_chart(prefix, "monthly_returns", "Monthly Returns", monthly_returns(equity)),
    )


def strategy_eval_charts(builder: ChartBuilder, prefix: str, report: dict[str, Any]) -> list[ChartArtifact]:
    attribution = report.get("attribution") or {}
    return_attr = attribution.get("return_attribution") or {}
    summary = report.get("summary_metrics") or {}
    risk_metrics = {
        "volatility": summary.get("annual_volatility"),
        "max_drawdown": summary.get("max_drawdown"),
        "turnover": summary.get("turnover"),
        "total_cost": summary.get("total_cost"),
        "gross_exposure": summary.get("gross_exposure"),
        "net_exposure": summary.get("net_exposure"),
    }
    return keep(
        builder.bar_chart(prefix, "return_attribution", "Return Attribution", return_attr.get("by_symbol") or {}),
        builder.bar_chart(prefix, "top_contributors", "Top Contributors", items_to_mapping(attribution.get("top_positive_contributors"), "symbol", "contribution")),
        builder.bar_chart(prefix, "top_detractors", "Top Detractors", items_to_mapping(attribution.get("top_negative_contributors"), "symbol", "contribution")),
        builder.bar_chart(prefix, "risk_metrics_summary", "Risk Metrics Summary", risk_metrics),
    )


def factor_backtest_charts(builder: ChartBuilder, prefix: str, report: dict[str, Any]) -> list[ChartArtifact]:
    periods = report.get("periods") or []
    long_leg = series(periods, "signal_date", "long_leg_return")
    short_leg = series(periods, "signal_date", "short_leg_return")
    spread = series(periods, "signal_date", "long_short_return")
    turnover = series(periods, "signal_date", "turnover")
    return keep(
        builder.line_chart(prefix, "long_leg_return", "Long Leg Return", long_leg),
        builder.line_chart(prefix, "short_leg_return", "Short Leg Return", short_leg),
        builder.line_chart(prefix, "long_short_return", "Long Short Return", spread),
        builder.line_chart(prefix, "drawdown", "Long Short Drawdown", drawdown_from_returns(spread)),
        builder.line_chart(prefix, "turnover", "Turnover", turnover),
    )


def portfolio_construction_charts(builder: ChartBuilder, prefix: str, report: dict[str, Any]) -> list[ChartArtifact]:
    return keep(
        builder.pie_chart(prefix, "target_weights", "Target Weights", report.get("target_weights") or {}),
        builder.bar_chart(prefix, "risk_contribution", "Risk Contribution", report.get("risk_contribution_pct") or report.get("risk_contribution_pct_by_symbol") or {}),
        builder.bar_chart(prefix, "volatility_contribution", "Volatility Contribution", report.get("volatility") or report.get("volatility_by_symbol") or {}),
        builder.heatmap(prefix, "correlation_matrix", "Correlation Matrix", report.get("correlation_matrix") or report.get("covariance_matrix") or {}),
    )


def walk_forward_charts(builder: ChartBuilder, prefix: str, report: dict[str, Any]) -> list[ChartArtifact]:
    folds = report.get("folds") or []
    train_returns = {str(fold.get("fold_id", index + 1)): fold_value(fold, "train_return", "total_return") for index, fold in enumerate(folds)}
    test_returns = {str(fold.get("fold_id", index + 1)): fold_value(fold, "test_return", "total_return") for index, fold in enumerate(folds)}
    train_sharpe = {str(fold.get("fold_id", index + 1)): fold_value(fold, "train_sharpe", "sharpe") for index, fold in enumerate(folds)}
    test_sharpe = {str(fold.get("fold_id", index + 1)): fold_value(fold, "test_sharpe", "sharpe") for index, fold in enumerate(folds)}
    stability = {
        item.get("factor", f"factor_{index + 1}"): item.get("stability_score", item.get("score", index + 1))
        for index, item in enumerate(((report.get("stability_analysis") or {}).get("factor_stability_ranking") or []))
        if isinstance(item, dict)
    }
    return keep(
        builder.bar_chart(prefix, "fold_returns", "Fold Test Returns", test_returns),
        builder.bar_chart(prefix, "train_vs_test_return", "Train vs Test Return", paired_average(train_returns, test_returns)),
        builder.bar_chart(prefix, "train_vs_test_sharpe", "Train vs Test Sharpe", paired_average(train_sharpe, test_sharpe)),
        builder.bar_chart(prefix, "factor_stability_ranking", "Factor Stability Ranking", stability),
        builder.bar_chart(prefix, "overfit_diagnostics", "Overfit Diagnostics", warning_counts(report.get("warnings") or [])),
    )


def risk_charts(builder: ChartBuilder, prefix: str, report: dict[str, Any]) -> list[ChartArtifact]:
    metrics = {
        "risk_score": report.get("risk_score"),
        "single_stock": report.get("single_stock_concentration_pct"),
        "industry": report.get("industry_concentration_pct"),
        "cash": report.get("cash_weight_pct"),
        "top_5": report.get("top_5_holdings_pct"),
    }
    return keep(
        builder.bar_chart(prefix, "risk_summary", "Risk Summary", metrics),
        builder.bar_chart(prefix, "top_holdings", "Top Holdings", items_to_mapping(report.get("holdings"), "symbol", "market_value")),
    )


def _cumulative_costs(trades: list[dict]) -> list[tuple[str, float]]:
    total = 0.0
    output = []
    for trade in trades:
        if not isinstance(trade, dict):
            continue
        cost = trade.get("cost", trade.get("total_cost"))
        if finite(cost):
            total += float(cost)
            output.append((str(trade.get("date") or trade.get("execution_date") or len(output) + 1), total))
    return output


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


def _cost_component_by_date(trades: list[dict], key: str) -> dict[str, float]:
    output: dict[str, float] = {}
    for trade in trades:
        if not isinstance(trade, dict):
            continue
        date = str(trade.get("date") or trade.get("execution_date") or "unknown")
        if finite(trade.get(key)):
            output[date] = output.get(date, 0.0) + float(trade[key])
    return output


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


def _rejected_by_symbol(rejected: list[dict]) -> dict[str, float]:
    output: dict[str, float] = {}
    for trade in rejected:
        if not isinstance(trade, dict):
            continue
        symbol = str(trade.get("symbol") or "UNKNOWN")
        output[symbol] = output.get(symbol, 0.0) + float(trade.get("rejected_quantity") or 0.0)
    return output


def _liquidity_usage(trades: list[dict], realism: dict[str, Any]) -> dict[str, float]:
    output: dict[str, float] = {}
    for trade in trades:
        if isinstance(trade, dict) and finite(trade.get("adv_participation")):
            key = str(trade.get("symbol") or len(output) + 1)
            output[key] = max(output.get(key, 0.0), float(trade["adv_participation"]))
    if not output and realism.get("largest_constrained_trades"):
        for trade in realism["largest_constrained_trades"]:
            if isinstance(trade, dict) and finite(trade.get("adv_participation")):
                output[str(trade.get("symbol") or len(output) + 1)] = float(trade["adv_participation"])
    return output


REPORT_SPECS = (
    report_spec("trade_sim", ("equity_curve", "cash_curve", "drawdown_curve", "monthly_returns", "cost_accumulation", "slippage", "cost_breakdown", "rejected_trades", "liquidity_usage"), trade_sim_charts),
    report_spec("backtest", ("equity_curve", "drawdown_curve", "monthly_returns"), backtest_charts),
    report_spec("strategy_eval", ("return_attribution", "top_contributors", "top_detractors", "risk_metrics_summary"), strategy_eval_charts),
    report_spec("factor_backtest", ("long_leg_return", "short_leg_return", "long_short_return", "drawdown", "turnover"), factor_backtest_charts),
    report_spec("portfolio_construction", ("target_weights", "risk_contribution", "volatility_contribution", "correlation_matrix"), portfolio_construction_charts),
    report_spec("walk_forward", ("fold_returns", "train_vs_test_return", "train_vs_test_sharpe", "factor_stability_ranking", "overfit_diagnostics"), walk_forward_charts),
    report_spec("risk", ("risk_summary", "top_holdings"), risk_charts),
)
