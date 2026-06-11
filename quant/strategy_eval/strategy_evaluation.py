"""Strategy evaluation and performance attribution from generated reports."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd


DEFAULT_ROLLING_WINDOWS = [20, 60]


@dataclass(frozen=True)
class StrategyEvaluationResult:
    metadata: dict[str, Any]
    input_report_paths: dict[str, str | None]
    strategy_type: str
    evaluation_window: dict[str, str | None]
    summary_metrics: dict[str, Any]
    benchmark_metrics: dict[str, Any]
    attribution: dict[str, Any]
    robustness_diagnostics: dict[str, Any]
    warnings: list[dict[str, str]]
    interpretation_notes: list[str]
    report_path: str

    @property
    def report_type(self) -> str:
        return self.strategy_type

    @property
    def source_report(self) -> str:
        return self.input_report_paths.get("primary_report") or ""

    @property
    def summary(self) -> dict[str, Any]:
        return {
            "total_return": self.summary_metrics.get("total_return"),
            "annual_return": self.summary_metrics.get("annual_return"),
            "volatility": self.summary_metrics.get("annual_volatility"),
            "sharpe": self.summary_metrics.get("sharpe_ratio"),
            "max_drawdown": self.summary_metrics.get("max_drawdown"),
            "calmar_ratio": self.summary_metrics.get("calmar_ratio"),
            "hit_rate": self.summary_metrics.get("hit_rate"),
            "turnover": self.summary_metrics.get("turnover"),
        }

    @property
    def return_attribution(self) -> dict[str, Any]:
        return self.attribution.get("return_attribution", {})

    @property
    def position_attribution(self) -> dict[str, Any]:
        return self.attribution.get("position_attribution", {})

    @property
    def risk_attribution(self) -> dict[str, Any]:
        return self.attribution.get("risk_attribution", {})

    @property
    def drawdown(self) -> dict[str, Any]:
        return self.attribution.get("drawdown_attribution", {})

    @property
    def rolling_metrics(self) -> dict[str, Any]:
        return self.robustness_diagnostics.get("rolling_metrics", {})

    @property
    def monthly_returns(self) -> dict[str, float]:
        return self.robustness_diagnostics.get("monthly_returns", {})

    @property
    def yearly_returns(self) -> dict[str, float]:
        return self.robustness_diagnostics.get("yearly_returns", {})

    def to_report(self) -> dict[str, Any]:
        return {
            "metadata": self.metadata,
            "input_report_paths": self.input_report_paths,
            "strategy_type": self.strategy_type,
            "evaluation_window": self.evaluation_window,
            "summary_metrics": self.summary_metrics,
            "benchmark_metrics": self.benchmark_metrics,
            "attribution": self.attribution,
            "robustness_diagnostics": self.robustness_diagnostics,
            "warnings": self.warnings,
            "interpretation_notes": self.interpretation_notes,
        }


class StrategyEvaluation:
    """Explain return and risk characteristics from offline strategy reports."""

    def __init__(self, report_dir: str | Path = "reports") -> None:
        self.report_dir = Path(report_dir)

    def evaluate(
        self,
        report_path: str | Path,
        benchmark_returns: dict[str, float] | None = None,
        benchmark_name: str | None = None,
        output_path: str | Path | None = None,
    ) -> StrategyEvaluationResult:
        source_path = Path(report_path)
        data = self._load_report(source_path)
        report_type = self._report_type(data)
        if report_type == "factor_backtest":
            prepared = self._prepare_factor_backtest(data)
        elif report_type == "backtest":
            prepared = self._prepare_backtest(data)
        else:
            raise ValueError("unsupported report type for strategy evaluation")

        result = self._build_result(
            data=data,
            source_path=source_path,
            strategy_type=report_type,
            prepared=prepared,
            benchmark_returns=benchmark_returns,
            benchmark_name=benchmark_name,
        )
        report_file = self._write_report(result, output_path)
        return StrategyEvaluationResult(
            metadata=result.metadata,
            input_report_paths=result.input_report_paths,
            strategy_type=result.strategy_type,
            evaluation_window=result.evaluation_window,
            summary_metrics=result.summary_metrics,
            benchmark_metrics=result.benchmark_metrics,
            attribution=result.attribution,
            robustness_diagnostics=result.robustness_diagnostics,
            warnings=result.warnings,
            interpretation_notes=result.interpretation_notes,
            report_path=str(report_file),
        )

    def _prepare_factor_backtest(self, data: dict[str, Any]) -> dict[str, Any]:
        periods = data.get("periods")
        if not isinstance(periods, list) or not periods:
            raise ValueError("factor_backtest report must contain non-empty periods")
        returns = self._returns_series(
            {
                str(period["signal_date"]): period.get("long_short_return")
                for period in periods
                if period.get("long_short_return") is not None
            }
        )
        symbol_contributions = self._factor_symbol_contributions(periods)
        side_attribution = self._factor_side_attribution(periods, data)
        return {
            "returns": returns,
            "periods": periods,
            "symbol_contributions": symbol_contributions,
            "cost_by_symbol": {},
            "turnover_by_symbol": self._factor_turnover_by_symbol(periods),
            "long_short_attribution": side_attribution,
            "total_cost": 0.0,
            "turnover": data.get("turnover"),
            "gross_exposure": data.get("gross_exposure"),
            "net_exposure": data.get("net_exposure"),
            "cash_drag": 0.0,
            "capital_base": 1.0,
            "source_warnings": data.get("warnings", []),
            "no_lookahead": data.get("no_lookahead"),
            "summary_overrides": {
                "total_return": data.get("long_short_return"),
                "annual_return": data.get("annual_return") or data.get("long_short_annual_return"),
                "annual_volatility": data.get("volatility") or data.get("long_short_volatility"),
                "sharpe_ratio": data.get("sharpe") or data.get("long_short_sharpe"),
                "max_drawdown": None,
                "hit_rate": data.get("hit_rate"),
            },
        }

    def _prepare_backtest(self, data: dict[str, Any]) -> dict[str, Any]:
        metrics = data.get("metrics")
        equity_curve = data.get("equity_curve")
        if not isinstance(metrics, dict):
            raise ValueError("backtest report must contain metrics")
        if not isinstance(equity_curve, list) or len(equity_curve) < 2:
            raise ValueError("backtest report must contain at least two equity_curve rows")
        returns = self._equity_returns(equity_curve)
        total_cost = float(metrics.get("total_cost") or 0.0)
        initial_cash = float(data.get("initial_cash") or 0.0)
        cash_ratios = [
            (float(row.get("cash") or 0.0) / float(row.get("equity") or 1.0))
            for row in equity_curve
            if float(row.get("equity") or 0.0) > 0
        ]
        reported_cash_ratio = metrics.get("cash_ratio")
        reported_exposure = (
            max(0.0, 1.0 - float(reported_cash_ratio))
            if reported_cash_ratio is not None
            else self._backtest_average_gross_exposure(equity_curve)
        )
        return {
            "returns": returns,
            "periods": [],
            "symbol_contributions": self._backtest_symbol_contributions(data.get("trades", []), initial_cash),
            "cost_by_symbol": self._backtest_cost_by_symbol(data.get("trades", []), initial_cash),
            "turnover_by_symbol": self._backtest_turnover_by_symbol(data.get("trades", []), initial_cash),
            "long_short_attribution": {
                "long_side": metrics.get("total_return"),
                "short_side": 0.0,
                "long_short": metrics.get("total_return"),
            },
            "total_cost": total_cost,
            "turnover": metrics.get("turnover"),
            "gross_exposure": reported_exposure,
            "net_exposure": reported_exposure,
            "cash_drag": self._mean(cash_ratios),
            "capital_base": initial_cash if initial_cash > 0 else 1.0,
            "source_warnings": [],
            "no_lookahead": data.get("no_lookahead"),
            "summary_overrides": {
                "total_return": metrics.get("total_return"),
                "annual_return": metrics.get("annual_return"),
                "annual_volatility": metrics.get("volatility"),
                "sharpe_ratio": metrics.get("sharpe_ratio"),
                "max_drawdown": metrics.get("max_drawdown"),
            },
        }

    def _build_result(
        self,
        data: dict[str, Any],
        source_path: Path,
        strategy_type: str,
        prepared: dict[str, Any],
        benchmark_returns: dict[str, float] | None,
        benchmark_name: str | None,
    ) -> StrategyEvaluationResult:
        returns: pd.Series = prepared["returns"]
        overrides = prepared["summary_overrides"]
        total_return = self._value_or(overrides.get("total_return"), self._compound_return(returns.tolist()))
        annual_return = self._value_or(overrides.get("annual_return"), self._annual_return(returns.tolist()))
        annual_volatility = self._value_or(overrides.get("annual_volatility"), self._annual_volatility(returns.tolist()))
        sharpe_ratio = self._value_or(overrides.get("sharpe_ratio"), self._sharpe(returns.tolist()))
        max_drawdown = self._normalize_drawdown(
            self._value_or(overrides.get("max_drawdown"), self._drawdown_stats(returns)["max_drawdown"])
        )
        total_cost = float(prepared.get("total_cost") or 0.0)
        cost_drag = self._cost_drag(total_cost, prepared.get("capital_base"))
        summary_metrics = {
            "total_return": total_return,
            "annual_return": annual_return,
            "annual_volatility": annual_volatility,
            "sharpe_ratio": sharpe_ratio,
            "sortino_ratio": self._sortino(returns.tolist()),
            "max_drawdown": max_drawdown,
            "calmar_ratio": self._calmar(annual_return, max_drawdown),
            "hit_rate": self._value_or(overrides.get("hit_rate"), self._hit_rate(returns.tolist())),
            "win_loss_ratio": self._win_loss_ratio(returns.tolist()),
            "average_win": self._average_win(returns.tolist()),
            "average_loss": self._average_loss(returns.tolist()),
            "best_period": self._best_period(returns),
            "worst_period": self._worst_period(returns),
            "turnover": prepared.get("turnover"),
            "total_cost": total_cost,
            "cost_to_return_ratio": self._cost_to_return_ratio(total_cost, total_return, prepared.get("capital_base")),
            "gross_exposure": prepared.get("gross_exposure"),
            "net_exposure": prepared.get("net_exposure"),
            "cash_drag": prepared.get("cash_drag"),
        }
        benchmark_metrics = self._benchmark_metrics(returns, benchmark_returns, benchmark_name, total_return)
        if benchmark_metrics:
            summary_metrics["benchmark_return"] = benchmark_metrics.get("benchmark_return")
            summary_metrics["excess_return"] = benchmark_metrics.get("excess_return")
            summary_metrics["information_ratio"] = benchmark_metrics.get("information_ratio")

        return_attribution = {
            "by_symbol": prepared["symbol_contributions"],
            "by_side": prepared["long_short_attribution"],
            "long_leg_return": prepared["long_short_attribution"].get("long_side"),
            "short_leg_return": prepared["long_short_attribution"].get("short_side"),
            "long_short_return": prepared["long_short_attribution"].get("long_short"),
            "long_side_contribution": prepared["long_short_attribution"].get("long_side_contribution"),
            "short_side_contribution": prepared["long_short_attribution"].get("short_side_contribution"),
            "cash_drag": prepared.get("cash_drag"),
            "cost_drag": cost_drag,
            "period_attribution": self._period_attribution(returns),
        }
        top_positive = self._top_contributors(prepared["symbol_contributions"])
        top_negative = self._top_detractors(prepared["symbol_contributions"])
        attribution = {
            "return_attribution": return_attribution,
            "cost_attribution_by_symbol": prepared["cost_by_symbol"],
            "turnover_attribution_by_symbol": prepared["turnover_by_symbol"],
            "top_positive_contributors": top_positive,
            "top_negative_contributors": top_negative,
            "position_attribution": {
                "top_contributors": top_positive,
                "top_detractors": top_negative,
            },
            "return_concentration": self._return_concentration(prepared["symbol_contributions"], total_return),
            "methodology": self._methodology_notes(strategy_type),
            "risk_attribution": {
                "gross_exposure": prepared.get("gross_exposure"),
                "net_exposure": prepared.get("net_exposure"),
                "average_cash": prepared.get("cash_drag"),
                "average_turnover": prepared.get("turnover"),
                "concentration": self._concentration(data, strategy_type),
            },
            "drawdown_attribution": self._drawdown(returns, prepared["symbol_contributions"], max_drawdown=max_drawdown),
        }
        rolling = self._rolling_metrics(returns)
        robustness_diagnostics = {
            "rolling_metrics": rolling,
            "monthly_returns": self._period_aggregate_returns(returns, "ME"),
            "yearly_returns": self._period_aggregate_returns(returns, "YE"),
            "diagnostics": {},
        }
        warnings = self._diagnostic_warnings(
            returns=returns,
            total_return=total_return,
            sharpe_ratio=sharpe_ratio,
            max_drawdown=max_drawdown,
            turnover=prepared.get("turnover"),
            cost_drag=cost_drag,
            benchmark_metrics=benchmark_metrics,
            symbol_contributions=prepared["symbol_contributions"],
            long_short_attribution=prepared["long_short_attribution"],
            source_warnings=prepared["source_warnings"],
        )
        if prepared.get("no_lookahead") is not True:
            warnings.append({"code": "NO_LOOKAHEAD_NOT_MARKED", "reason": "input report is not marked no_lookahead"})
        robustness_diagnostics["diagnostics"] = {
            warning["code"]: warning["reason"]
            for warning in warnings
        }
        metadata = {
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "engine": "StrategyEvaluation",
            "no_new_strategy_generated": True,
            "no_live_trading": True,
            "source_no_lookahead": prepared.get("no_lookahead"),
        }
        return StrategyEvaluationResult(
            metadata=metadata,
            input_report_paths={"primary_report": str(source_path)},
            strategy_type=strategy_type,
            evaluation_window=self._evaluation_window(returns),
            summary_metrics=summary_metrics,
            benchmark_metrics=benchmark_metrics,
            attribution=attribution,
            robustness_diagnostics=robustness_diagnostics,
            warnings=warnings,
            interpretation_notes=self._interpretation_notes(strategy_type),
            report_path="",
        )

    @staticmethod
    def _load_report(path: Path) -> dict[str, Any]:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise ValueError(f"strategy evaluation report file not found: {path}") from exc
        except json.JSONDecodeError as exc:
            raise ValueError(f"strategy evaluation report is not valid JSON: {path}") from exc
        if not isinstance(data, dict):
            raise ValueError("strategy evaluation source report must contain a JSON object")
        return data

    @staticmethod
    def _report_type(data: dict[str, Any]) -> str:
        if "periods" in data and "long_short_return" in data:
            return "factor_backtest"
        if "metrics" in data and "equity_curve" in data:
            return "backtest"
        return "unknown"

    @staticmethod
    def _returns_series(returns_by_date: dict[str, float | None]) -> pd.Series:
        values = {
            pd.to_datetime(date): float(value)
            for date, value in returns_by_date.items()
            if value is not None and pd.notna(value)
        }
        return pd.Series(values, dtype="float64").sort_index()

    @staticmethod
    def _equity_returns(equity_curve: list[dict[str, Any]]) -> pd.Series:
        frame = pd.DataFrame(equity_curve)
        frame["date"] = pd.to_datetime(frame["date"])
        frame["equity"] = pd.to_numeric(frame["equity"], errors="coerce")
        returns = frame.sort_values("date").set_index("date")["equity"].pct_change().dropna()
        return returns.astype("float64")

    @staticmethod
    def _factor_symbol_contributions(periods: list[dict[str, Any]]) -> dict[str, float]:
        contributions: dict[str, float] = {}
        for period in periods:
            long_symbols = period.get("long_symbols") or []
            short_symbols = period.get("short_symbols") or []
            long_return = period.get("long_return")
            short_return = period.get("short_return")
            if long_return is not None and long_symbols:
                per_symbol = float(long_return) / len(long_symbols)
                for symbol in long_symbols:
                    contributions[symbol] = contributions.get(symbol, 0.0) + per_symbol
            if short_return is not None and short_symbols:
                per_symbol = -float(short_return) / len(short_symbols)
                for symbol in short_symbols:
                    contributions[symbol] = contributions.get(symbol, 0.0) + per_symbol
        return {symbol: float(value) for symbol, value in sorted(contributions.items())}

    @staticmethod
    def _factor_turnover_by_symbol(periods: list[dict[str, Any]]) -> dict[str, float]:
        totals: dict[str, float] = {}
        previous: dict[str, float] | None = None
        for period in periods:
            weights = dict(period.get("long_weights") or {})
            weights.update(period.get("short_weights") or {})
            weights = {symbol: float(weight) for symbol, weight in weights.items()}
            if previous is not None:
                for symbol in set(previous) | set(weights):
                    totals[symbol] = totals.get(symbol, 0.0) + abs(weights.get(symbol, 0.0) - previous.get(symbol, 0.0))
            previous = weights
        return {symbol: float(value) for symbol, value in sorted(totals.items())}

    @staticmethod
    def _backtest_symbol_contributions(trades: list[dict[str, Any]], denominator: float) -> dict[str, float]:
        contributions: dict[str, float] = {}
        scale = denominator if denominator > 0 else 1.0
        for trade in trades or []:
            symbol = str(trade.get("symbol"))
            side = str(trade.get("side", "")).upper()
            notional = float(trade.get("notional") or 0.0)
            cost = float(trade.get("total_cost") or 0.0)
            signed = notional if side == "SELL" else -notional
            contributions[symbol] = contributions.get(symbol, 0.0) + (signed - cost) / scale
        return {symbol: float(value) for symbol, value in sorted(contributions.items())}

    @staticmethod
    def _backtest_cost_by_symbol(trades: list[dict[str, Any]], denominator: float) -> dict[str, float]:
        scale = denominator if denominator > 0 else 1.0
        costs: dict[str, float] = {}
        for trade in trades or []:
            symbol = str(trade.get("symbol"))
            costs[symbol] = costs.get(symbol, 0.0) - float(trade.get("total_cost") or 0.0) / scale
        return {symbol: float(value) for symbol, value in sorted(costs.items())}

    @staticmethod
    def _backtest_turnover_by_symbol(trades: list[dict[str, Any]], denominator: float) -> dict[str, float]:
        scale = denominator if denominator > 0 else 1.0
        turnover: dict[str, float] = {}
        for trade in trades or []:
            symbol = str(trade.get("symbol"))
            turnover[symbol] = turnover.get(symbol, 0.0) + abs(float(trade.get("notional") or 0.0)) / scale
        return {symbol: float(value) for symbol, value in sorted(turnover.items())}

    @staticmethod
    def _concentration(data: dict[str, Any], strategy_type: str) -> dict[str, float | str | None]:
        if strategy_type == "factor_backtest":
            weights_by_symbol: dict[str, list[float]] = {}
            for period in data.get("periods", []):
                weights = dict(period.get("long_weights") or {})
                weights.update(period.get("short_weights") or {})
                for symbol, weight in weights.items():
                    weights_by_symbol.setdefault(symbol, []).append(abs(float(weight)))
            average_weights = {symbol: sum(values) / len(values) for symbol, values in weights_by_symbol.items() if values}
            return StrategyEvaluation._concentration_from_weights(average_weights)
        weights_by_symbol: dict[str, list[float]] = {}
        for row in data.get("equity_curve", []):
            equity = float(row.get("equity") or 0.0)
            positions = row.get("positions") or {}
            if equity <= 0 or not isinstance(positions, dict):
                continue
            for symbol, value in positions.items():
                weights_by_symbol.setdefault(symbol, []).append(abs(float(value) / equity))
        average_weights = {symbol: sum(values) / len(values) for symbol, values in weights_by_symbol.items() if values}
        return StrategyEvaluation._concentration_from_weights(average_weights)

    @staticmethod
    def _concentration_from_weights(weights: dict[str, float]) -> dict[str, float | str | None]:
        if not weights:
            return {"largest_position": None, "largest_position_weight": None, "top_3_weight": 0.0, "top_5_weight": 0.0}
        ranked = sorted(weights.items(), key=lambda item: item[1], reverse=True)
        return {
            "largest_position": ranked[0][0],
            "largest_position_weight": float(ranked[0][1]),
            "top_3_weight": float(sum(value for _, value in ranked[:3])),
            "top_5_weight": float(sum(value for _, value in ranked[:5])),
        }

    @staticmethod
    def _backtest_average_gross_exposure(equity_curve: list[dict[str, Any]]) -> float | None:
        exposures = []
        for row in equity_curve:
            equity = float(row.get("equity") or 0.0)
            positions = row.get("positions") or {}
            if equity <= 0 or not isinstance(positions, dict):
                continue
            exposures.append(sum(abs(float(value)) for value in positions.values()) / equity)
        return StrategyEvaluation._mean(exposures)

    @staticmethod
    @staticmethod
    def _factor_side_attribution(periods: list[dict[str, Any]], data: dict[str, Any]) -> dict[str, Any]:
        long_period_returns = [
            float(period["long_return"])
            for period in periods
            if period.get("long_return") is not None and period.get("long_short_return") is not None
        ]
        short_period_returns = [
            float(period["short_return"])
            for period in periods
            if period.get("short_return") is not None and period.get("long_short_return") is not None
        ]
        long_side_contribution = sum(long_period_returns) if long_period_returns else None
        short_side_contribution = -sum(short_period_returns) if short_period_returns else None
        return {
            "long_side": data.get("long_leg_return"),
            "short_side": data.get("short_leg_return"),
            "long_short": data.get("long_short_return"),
            "long_side_contribution": long_side_contribution,
            "short_side_contribution": short_side_contribution,
            "period_contribution_sum": (
                long_side_contribution + short_side_contribution
                if long_side_contribution is not None and short_side_contribution is not None
                else None
            ),
            "raw_long_leg_return": data.get("long_leg_return"),
            "raw_short_leg_underlying_return": data.get("short_leg_return"),
            "source_long_short_return": data.get("long_short_return"),
        }

    @staticmethod
    def _drawdown(
        returns: pd.Series,
        contributions: dict[str, float],
        max_drawdown: float | None = None,
    ) -> dict[str, Any]:
        stats = StrategyEvaluation._drawdown_stats(returns)
        detractors = StrategyEvaluation._top_detractors(contributions)
        return {
            "max_drawdown": max_drawdown if max_drawdown is not None else stats["max_drawdown"],
            "drawdown_start": stats["drawdown_start"],
            "drawdown_end": stats["drawdown_end"],
            "drawdown_duration": stats["drawdown_duration"],
            "largest_contributors_to_drawdown": detractors[:5],
        }

    @staticmethod
    def _drawdown_stats(returns: pd.Series) -> dict[str, Any]:
        if returns.empty:
            return {"max_drawdown": None, "drawdown_start": None, "drawdown_end": None, "drawdown_duration": 0}
        equity = (1.0 + returns).cumprod()
        running_max = equity.cummax().clip(lower=1.0)
        drawdowns = equity / running_max - 1.0
        end = drawdowns.idxmin()
        start = equity.loc[:end].idxmax() if equity.loc[:end].max() >= 1.0 else returns.index.min()
        return {
            "max_drawdown": float(drawdowns.loc[end]),
            "drawdown_start": start.strftime("%Y-%m-%d"),
            "drawdown_end": end.strftime("%Y-%m-%d"),
            "drawdown_duration": int((end - start).days),
        }

    @staticmethod
    def _rolling_metrics(returns: pd.Series, windows: list[int] | None = None) -> dict[str, Any]:
        windows = windows or DEFAULT_ROLLING_WINDOWS
        output: dict[str, Any] = {}
        if returns.empty:
            return {str(window): {"rolling_return": {}, "rolling_sharpe": {}, "rolling_drawdown": {}} for window in windows}
        for window in windows:
            rolling_return = (1.0 + returns).rolling(window).apply(lambda values: float(values.prod() - 1.0), raw=False)
            rolling_std = returns.rolling(window).std()
            rolling_mean = returns.rolling(window).mean()
            rolling_sharpe = (rolling_mean / rolling_std) * (252.0 ** 0.5)
            equity = (1.0 + returns).cumprod()
            rolling_peak = equity.rolling(window).max()
            rolling_drawdown = equity / rolling_peak - 1.0
            output[str(window)] = {
                "rolling_return": StrategyEvaluation._series_to_dict(rolling_return.dropna()),
                "rolling_sharpe": StrategyEvaluation._series_to_dict(rolling_sharpe.dropna()),
                "rolling_drawdown": StrategyEvaluation._series_to_dict(rolling_drawdown.dropna()),
            }
        return output

    @staticmethod
    def _period_aggregate_returns(returns: pd.Series, frequency: str) -> dict[str, float]:
        if returns.empty:
            return {}
        aggregated = (1.0 + returns).resample(frequency).prod() - 1.0
        if frequency == "ME":
            return {index.strftime("%Y-%m"): float(value) for index, value in aggregated.items()}
        return {index.strftime("%Y"): float(value) for index, value in aggregated.items()}

    @staticmethod
    def _period_attribution(returns: pd.Series) -> dict[str, float]:
        return StrategyEvaluation._period_aggregate_returns(returns, "ME")

    @staticmethod
    def _benchmark_metrics(
        returns: pd.Series,
        benchmark_returns: dict[str, float] | None,
        benchmark_name: str | None,
        total_return: float | None,
    ) -> dict[str, Any]:
        if not benchmark_returns:
            return {}
        benchmark = StrategyEvaluation._returns_series(benchmark_returns)
        benchmark_return = StrategyEvaluation._compound_return(benchmark.tolist())
        excess_return = (total_return - benchmark_return) if total_return is not None and benchmark_return is not None else None
        active = pd.concat([returns, benchmark], axis=1, join="inner").dropna()
        information_ratio = None
        if len(active) > 1:
            diff = active.iloc[:, 0] - active.iloc[:, 1]
            std = float(diff.std())
            if std > 0 and pd.notna(std):
                information_ratio = float((diff.mean() / std) * (252.0 ** 0.5))
        return {
            "benchmark": benchmark_name,
            "benchmark_return": benchmark_return,
            "excess_return": excess_return,
            "information_ratio": information_ratio,
        }

    @staticmethod
    def _diagnostic_warnings(
        returns: pd.Series,
        total_return: float | None,
        sharpe_ratio: float | None,
        max_drawdown: float | None,
        turnover: float | None,
        cost_drag: float | None,
        benchmark_metrics: dict[str, Any],
        symbol_contributions: dict[str, float],
        long_short_attribution: dict[str, Any],
        source_warnings: list[str],
    ) -> list[dict[str, str]]:
        warnings = [{"code": "SOURCE_WARNING", "reason": str(warning)} for warning in source_warnings]
        if len(returns) < 30:
            warnings.append({"code": "LOW_OBSERVATION_COUNT", "reason": "fewer than 30 return observations; Sharpe may be unstable"})
        if turnover is not None and turnover > 1.0:
            warnings.append({"code": "HIGH_TURNOVER", "reason": "turnover is above 1.0"})
        if cost_drag is not None and abs(cost_drag) > 0.02:
            warnings.append({"code": "HIGH_COST_DRAG", "reason": "cost drag exceeds 2% of reported return denominator"})
        if total_return is not None and sharpe_ratio is not None and total_return < 0 < sharpe_ratio:
            warnings.append({"code": "NEGATIVE_COMPOUND_POSITIVE_SHARPE", "reason": "compounded return is negative while arithmetic Sharpe is positive"})
        if max_drawdown is not None and max_drawdown < -0.2:
            warnings.append({"code": "LARGE_DRAWDOWN", "reason": "max drawdown is worse than -20%"})
        if max_drawdown is not None and max_drawdown <= -1.0:
            warnings.append({"code": "CAPITAL_WIPEOUT_OR_MARGIN_LOSS", "reason": "drawdown reaches or exceeds -100%; long-short spread returns may imply margin-style losses"})
        if benchmark_metrics.get("excess_return") is not None and benchmark_metrics["excess_return"] < 0:
            warnings.append({"code": "BENCHMARK_UNDERPERFORMANCE", "reason": "strategy total return is below benchmark return"})
        concentration = StrategyEvaluation._return_concentration(symbol_contributions, total_return)
        if concentration.get("top_1_pct") is not None and concentration["top_1_pct"] > 0.5:
            warnings.append({"code": "SYMBOL_CONCENTRATION", "reason": "top contributor explains more than 50% of total return"})
        long_side = long_short_attribution.get("long_side")
        short_side = long_short_attribution.get("short_side")
        if long_side is not None and short_side is not None and abs(float(short_side)) > 0:
            ratio = abs(float(long_side) / float(short_side))
            if ratio > 5 or ratio < 0.2:
                warnings.append({"code": "LONG_SHORT_IMBALANCE", "reason": "long and short leg contributions are highly imbalanced"})
        return warnings

    @staticmethod
    def _top_contributors(contributions: dict[str, float]) -> list[dict[str, float | str]]:
        return [
            {"symbol": symbol, "contribution": float(value)}
            for symbol, value in sorted(contributions.items(), key=lambda item: item[1], reverse=True)
            if value > 0
        ][:5]

    @staticmethod
    def _top_detractors(contributions: dict[str, float]) -> list[dict[str, float | str]]:
        return [
            {"symbol": symbol, "contribution": float(value)}
            for symbol, value in sorted(contributions.items(), key=lambda item: item[1])
            if value < 0
        ][:5]

    @staticmethod
    def _return_concentration(contributions: dict[str, float], total_return: float | None) -> dict[str, float | None]:
        positives = sorted([value for value in contributions.values() if value > 0], reverse=True)
        denominator = abs(float(total_return)) if total_return not in {None, 0.0} else sum(abs(value) for value in positives)
        if denominator <= 0:
            return {"top_1_pct": None, "top_3_pct": None}
        return {
            "top_1_pct": float(positives[0] / denominator) if positives else 0.0,
            "top_3_pct": float(sum(positives[:3]) / denominator) if positives else 0.0,
        }

    @staticmethod
    def _interpretation_notes(strategy_type: str) -> list[str]:
        notes = ["offline evaluation only; no live trades or broker APIs are used"]
        if strategy_type == "factor_backtest":
            notes.append("factor long-short reports may use overlapping forward-return observations")
            notes.append("short_side is the raw underlying short basket return; short_side_contribution is sign-adjusted for long-short attribution")
        return notes

    @staticmethod
    def _methodology_notes(strategy_type: str) -> dict[str, str]:
        if strategy_type == "factor_backtest":
            return {
                "return_stream": "period long_short_return values from the factor backtest report",
                "max_drawdown": "computed from the period return stream with initial capital treated as the starting high-water mark",
                "by_symbol": "arithmetic period contribution using long weights and negative short weights; not compounded",
                "by_side": "raw leg returns are kept separately from sign-adjusted long-short contributions",
            }
        return {
            "return_stream": "equity_curve percentage changes from the portfolio backtest report",
            "by_symbol": "trade-notional approximation normalized by initial cash",
            "cost": "trade costs normalized by initial cash when available",
        }

    @staticmethod
    def _evaluation_window(returns: pd.Series) -> dict[str, str | None]:
        if returns.empty:
            return {"start": None, "end": None}
        return {"start": returns.index.min().strftime("%Y-%m-%d"), "end": returns.index.max().strftime("%Y-%m-%d")}

    @staticmethod
    def _series_to_dict(series: pd.Series) -> dict[str, float]:
        return {index.strftime("%Y-%m-%d"): float(value) for index, value in series.items() if pd.notna(value)}

    @staticmethod
    def _value_or(value: Any, fallback: Any) -> Any:
        return fallback if value is None else value

    @staticmethod
    def _compound_return(values: list[float]) -> float | None:
        if not values:
            return None
        total = 1.0
        for value in values:
            total *= 1.0 + value
        return total - 1.0

    @staticmethod
    def _annual_return(values: list[float]) -> float | None:
        compounded = StrategyEvaluation._compound_return(values)
        if compounded is None or not values:
            return None
        return (1.0 + compounded) ** (252.0 / len(values)) - 1.0

    @staticmethod
    def _annual_volatility(values: list[float]) -> float | None:
        if len(values) < 2:
            return None
        return float(pd.Series(values, dtype="float64").std() * (252.0 ** 0.5))

    @staticmethod
    def _sharpe(values: list[float]) -> float | None:
        if len(values) < 2:
            return None
        series = pd.Series(values, dtype="float64")
        std = float(series.std())
        if std <= 0 or pd.isna(std):
            return None
        return float((series.mean() / std) * (252.0 ** 0.5))

    @staticmethod
    def _sortino(values: list[float]) -> float | None:
        if len(values) < 2:
            return None
        series = pd.Series(values, dtype="float64")
        downside = series[series < 0]
        if len(downside) < 2:
            return None
        downside_std = float(downside.std())
        if downside_std <= 0 or pd.isna(downside_std):
            return None
        return float((series.mean() / downside_std) * (252.0 ** 0.5))

    @staticmethod
    def _calmar(annual_return: float | None, max_drawdown: float | None) -> float | None:
        if annual_return is None or max_drawdown in {None, 0.0}:
            return None
        drawdown = abs(float(max_drawdown))
        return None if drawdown <= 0 else float(annual_return) / drawdown

    @staticmethod
    def _hit_rate(values: list[float]) -> float | None:
        return None if not values else sum(1 for value in values if value > 0) / len(values)

    @staticmethod
    def _average_win(values: list[float]) -> float | None:
        wins = [value for value in values if value > 0]
        return StrategyEvaluation._mean(wins)

    @staticmethod
    def _average_loss(values: list[float]) -> float | None:
        losses = [value for value in values if value < 0]
        return StrategyEvaluation._mean(losses)

    @staticmethod
    def _win_loss_ratio(values: list[float]) -> float | None:
        average_win = StrategyEvaluation._average_win(values)
        average_loss = StrategyEvaluation._average_loss(values)
        if average_win is None or average_loss in {None, 0.0}:
            return None
        return float(average_win / abs(average_loss))

    @staticmethod
    def _best_period(returns: pd.Series) -> dict[str, Any] | None:
        if returns.empty:
            return None
        date = returns.idxmax()
        return {"date": date.strftime("%Y-%m-%d"), "return": float(returns.loc[date])}

    @staticmethod
    def _worst_period(returns: pd.Series) -> dict[str, Any] | None:
        if returns.empty:
            return None
        date = returns.idxmin()
        return {"date": date.strftime("%Y-%m-%d"), "return": float(returns.loc[date])}

    @staticmethod
    def _cost_drag(total_cost: float, capital_base: float | None) -> float | None:
        if total_cost == 0:
            return 0.0
        denominator = abs(float(capital_base)) if capital_base not in {None, 0.0} else 1.0
        return -abs(total_cost) / denominator

    @staticmethod
    def _cost_to_return_ratio(total_cost: float, total_return: float | None, capital_base: float | None = None) -> float | None:
        if total_return in {None, 0.0}:
            return None
        denominator = abs(float(total_return))
        if capital_base not in {None, 0.0}:
            denominator *= abs(float(capital_base))
        return abs(float(total_cost)) / denominator

    @staticmethod
    def _normalize_drawdown(value: float | None) -> float | None:
        if value is None:
            return None
        value = float(value)
        return -abs(value)

    @staticmethod
    def _mean(values: list[float]) -> float | None:
        clean = [float(value) for value in values if value is not None and pd.notna(value)]
        if not clean:
            return None
        return float(sum(clean) / len(clean))

    def _write_report(self, result: StrategyEvaluationResult, output_path: str | Path | None = None) -> Path:
        if output_path:
            path = Path(output_path)
            path.parent.mkdir(parents=True, exist_ok=True)
        else:
            self.report_dir.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            path = self.report_dir / f"strategy_eval_{timestamp}.json"
        path.write_text(json.dumps(result.to_report(), indent=2), encoding="utf-8")
        return path
