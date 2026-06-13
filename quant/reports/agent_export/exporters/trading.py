"""Trading and portfolio agent exporters."""

from __future__ import annotations

from typing import Any

from quant.reports.agent_export.helpers import AgentExportContext, clean_warnings, format_pct, num, round_mapping
from quant.reports.agent_export.models import AgentExport
from quant.reports.agent_export.specs import export_spec


def export_alpha(ctx: AgentExportContext, report: dict[str, Any], generated_from: str) -> AgentExport:
    selected = report.get("selected_symbols") or []
    weights = report.get("target_weights") or {}
    universe_size = len((report.get("config") or {}).get("universe") or selected)
    warnings = clean_warnings(report.get("warnings"))
    if universe_size < 10:
        warnings.append("WARN_UNIVERSE_SMALL")
    metrics = {
        "as_of_date": report.get("as_of_date"),
        "selected_symbols": selected,
        "target_weights": round_mapping(weights),
        "cash_weight": weights.get("cash"),
        "weighting_mode": (report.get("config") or {}).get("weighting_mode"),
        "multi_factor_confidence": ((report.get("multi_factor_summary") or {}).get("confidence") or {}).get("overall_confidence"),
        "multi_factor_report_path": report.get("multi_factor_report_path"),
    }
    return ctx.base_export(
        "alpha",
        generated_from,
        f"Alpha selected {len(selected)} symbols from a {universe_size} symbol universe.",
        metrics,
        [f"selected_symbols: {', '.join(selected)}", "momentum-based portfolio selected"],
        warnings,
        ["run factor evaluation", "run rebalance with costs", "expand universe"],
        [f"target {symbol} {format_pct(weight)}" for symbol, weight in weights.items()],
        ctx.exclusion_notes(report),
    )


def export_portfolio_construction(ctx: AgentExportContext, report: dict[str, Any], generated_from: str) -> AgentExport:
    weights = report.get("target_weights") or {}
    cash = report.get("cash_weight", weights.get("cash"))
    warnings = clean_warnings(report.get("warnings"))
    if num(cash) is not None and num(cash) >= 0.30:
        warnings.append("WARN_CASH_ALLOCATION_HIGH")
    if any("capped" in warning for warning in warnings):
        warnings.append("WARN_MAX_WEIGHT_CONSTRAINT_BINDING")
    metrics = {
        "method": report.get("method"),
        "target_weights": round_mapping(weights),
        "cash_weight": cash,
        "portfolio_volatility": report.get("portfolio_volatility", report.get("expected_portfolio_volatility")),
        "risk_contribution_pct": round_mapping(report.get("risk_contribution_pct") or report.get("risk_contribution_pct_by_symbol") or {}),
        "selected_symbols": report.get("selected_symbols") or report.get("symbols_used"),
    }
    assessment = "constraints produced large cash allocation" if num(cash) and num(cash) >= 0.30 else "portfolio construction produced constrained target weights"
    return ctx.base_export(
        "portfolio_construction",
        generated_from,
        f"Portfolio construction method {report.get('method')} generated target weights.",
        metrics,
        [assessment],
        warnings,
        ["evaluate risk parity allocation", "run rebalance with costs", "expand universe"],
        [f"target {symbol} {format_pct(weight)}" for symbol, weight in weights.items()],
        ctx.exclusion_notes(report),
    )


def export_risk(ctx: AgentExportContext, report: dict[str, Any], generated_from: str) -> AgentExport:
    score = report.get("risk_score")
    warnings = clean_warnings(report.get("warnings"))
    concentration = report.get("single_stock_concentration_pct")
    if num(concentration) is not None and num(concentration) > 50:
        warnings.append("WARN_POSITION_CONCENTRATION_HIGH")
    metrics = {
        "risk_score": score,
        "single_stock_concentration_pct": concentration,
        "industry_concentration_pct": report.get("industry_concentration_pct"),
        "top_5_holdings_pct": report.get("top_5_holdings_pct"),
        "cash_weight_pct": report.get("cash_weight_pct"),
        "top_holdings": (report.get("holdings") or [])[:5] if isinstance(report.get("holdings"), list) else report.get("holdings"),
    }
    assessment = "high risk" if num(score) is not None and num(score) >= 70 else "moderate or low risk"
    return ctx.base_export(
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


def export_rebalance(ctx: AgentExportContext, report: dict[str, Any], generated_from: str) -> AgentExport:
    items = report.get("items") or []
    trades = [item for item in items if item.get("action") in {"BUY", "SELL"}]
    metrics = {
        "total_assets": report.get("total_assets"),
        "cash_before": report.get("cash_before"),
        "cash_after_rebalance": report.get("cash_after_rebalance"),
        "estimated_total_commission": report.get("estimated_total_commission"),
        "trade_count": len(trades),
        "largest_changes": sorted(trades, key=lambda item: abs(item.get("difference", 0) or 0), reverse=True)[:5],
    }
    actions = [f"{item.get('action')} {item.get('symbol')} {item.get('qty')} shares" for item in trades]
    return ctx.base_export(
        "rebalance",
        generated_from,
        f"Rebalance plan has {len(trades)} trade candidates.",
        metrics,
        [f"{len(trades)} buy/sell suggestions"],
        clean_warnings(report.get("warnings")),
        ["inspect cost drag", "simulate execution", "review cash target"],
        actions,
        [],
    )


def export_execution(ctx: AgentExportContext, report: dict[str, Any], generated_from: str) -> AgentExport:
    executed = report.get("executed_trades") or []
    unfilled = report.get("unfilled_trades") or []
    costs = report.get("execution_costs") or {}
    warnings = clean_warnings(report.get("warnings"))
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
    return ctx.base_export(
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


def export_backtest(ctx: AgentExportContext, report: dict[str, Any], generated_from: str) -> AgentExport:
    metrics = report.get("metrics") or {}
    warnings = clean_warnings(report.get("warnings"))
    warnings.extend(
        ctx.performance_warnings(
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
    return ctx.base_export(
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


def export_trade_sim(ctx: AgentExportContext, report: dict[str, Any], generated_from: str) -> AgentExport:
    warnings = clean_warnings(report.get("warnings"))
    warnings.extend(
        ctx.performance_warnings(
            total_return=report.get("total_return"),
            sharpe=report.get("sharpe"),
            drawdown=report.get("max_drawdown"),
        )
    )
    final_equity = num(report.get("final_equity"))
    total_cost = num(report.get("total_cost"))
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
    assessment = "positive historical simulation" if num(report.get("total_return")) and num(report.get("total_return")) > 0 else "weak or negative historical simulation"
    return ctx.base_export(
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


def is_trade_sim(report: dict[str, Any]) -> bool:
    return report.get("metadata", {}).get("report_type") == "trade_sim" or {"strategy", "portfolio_method", "equity_curve", "rebalance_events", "final_equity"}.issubset(report)


EXPORT_SPECS = (
    export_spec("trade_sim", 10, is_trade_sim, export_trade_sim),
    export_spec("portfolio_construction", 80, lambda report: "method" in report and "risk_contribution_pct" in report and "covariance_matrix" in report, export_portfolio_construction),
    export_spec("alpha", 90, lambda report: "selected_symbols" in report and "target_weights" in report, export_alpha),
    export_spec("risk", 100, lambda report: "risk_score" in report and ("single_stock_concentration_pct" in report or "holdings" in report), export_risk),
    export_spec("rebalance", 110, lambda report: "items" in report and "cash_after_rebalance" in report, export_rebalance),
    export_spec("execution", 120, lambda report: "executed_trades" in report and "unfilled_trades" in report and "execution_costs" in report, export_execution),
    export_spec("backtest", 130, lambda report: "metrics" in report and ("equity_curve" in report or "trades" in report), export_backtest),
)
