"""Portfolio construction and risk-aware target weight generation."""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Mapping

import pandas as pd
import numpy as np

from quant.core.symbols import normalize_symbols
from quant.engines.risk.risk_engine import DEFAULT_INDUSTRY_MAP
from quant.reports.report_io import generate_report_path, write_json_report
from quant.storage.sqlite_store import SQLitePriceStore


SUPPORTED_METHODS = {"equal_weight", "inverse_volatility", "risk_parity", "min_variance"}

DEFAULT_CONSTRAINTS = {
    "min_cash_weight": 0.10,
    "max_position_weight": 0.20,
    "max_sector_weight": 0.50,
    "only_long": True,
}


@dataclass(frozen=True)
class PortfolioConstructionResult:
    method: str
    symbols_requested: list[str]
    symbols_used: list[str]
    excluded_symbols: list[str]
    exclusion_reasons: dict[str, str]
    start_date: str | None
    end_date: str | None
    lookback: int
    no_lookahead: bool
    target_weights: dict[str, float]
    cash_weight: float
    constraints: dict
    volatility: dict[str, float]
    covariance_matrix: dict[str, dict[str, float]]
    correlation_matrix: dict[str, dict[str, float]]
    portfolio_volatility: float | None
    marginal_risk_contributions: dict[str, float]
    risk_contributions: dict[str, float]
    risk_contribution_pct: dict[str, float]
    warnings: list[str]
    output_targets_path: str | None
    report_path: str

    def to_report(self) -> dict:
        return {
            "method": self.method,
            "input_symbols": self.symbols_requested,
            "selected_symbols": self.symbols_used,
            "symbols_requested": self.symbols_requested,
            "symbols_used": self.symbols_used,
            "excluded_symbols": self.excluded_symbols,
            "exclusion_reasons": self.exclusion_reasons,
            "start_date": self.start_date,
            "end_date": self.end_date,
            "lookback": self.lookback,
            "covariance_window": {
                "start_date": self.start_date,
                "end_date": self.end_date,
                "lookback": self.lookback,
            },
            "no_lookahead": self.no_lookahead,
            "target_weights": self.target_weights,
            "cash_weight": self.cash_weight,
            "constraints": self.constraints,
            "volatility_by_symbol": self.volatility,
            "volatility": self.volatility,
            "covariance_matrix_metadata": {
                "symbols": self.symbols_used,
                "frequency": "daily_return",
                "source": "stored_close_prices",
            },
            "covariance_matrix": self.covariance_matrix,
            "correlation_matrix": self.correlation_matrix,
            "expected_portfolio_volatility": self.portfolio_volatility,
            "portfolio_volatility": self.portfolio_volatility,
            "marginal_risk_contributions": self.marginal_risk_contributions,
            "risk_contribution_by_symbol": self.risk_contributions,
            "risk_contributions": self.risk_contributions,
            "risk_contribution_pct_by_symbol": self.risk_contribution_pct,
            "risk_contribution_pct": self.risk_contribution_pct,
            "warnings": self.warnings,
            "interpretation_notes": [
                "Portfolio construction is offline research only and does not execute trades.",
                "Cash is residual unallocated capital after long-only constraints are applied.",
                "Risk parity is an approximate iterative balancing of asset risk contribution percentages.",
                "Minimum variance is long-only and may leave high cash when max-weight constraints bind.",
            ],
            "output_targets_path": self.output_targets_path,
        }


class PortfolioConstructionEngine:
    """Generate long-only target weights from stored historical prices."""

    def __init__(
        self,
        price_store: SQLitePriceStore,
        report_dir: str | Path = "reports",
        sector_map: Mapping[str, str] | None = None,
    ) -> None:
        self.price_store = price_store
        self.report_dir = Path(report_dir)
        self.sector_map = dict(sector_map or DEFAULT_INDUSTRY_MAP)

    def construct(
        self,
        method: str,
        symbols: list[str],
        start: str | None = None,
        end: str | None = None,
        lookback: int = 60,
        min_cash_weight: float = DEFAULT_CONSTRAINTS["min_cash_weight"],
        max_position_weight: float = DEFAULT_CONSTRAINTS["max_position_weight"],
        max_sector_weight: float = DEFAULT_CONSTRAINTS["max_sector_weight"],
        output_targets: str | Path | None = None,
        write_report: bool = True,
    ) -> PortfolioConstructionResult:
        normalized_method = method.strip().lower()
        if normalized_method not in SUPPORTED_METHODS:
            raise ValueError("method must be one of: equal_weight, inverse_volatility, risk_parity, min_variance")
        normalized_symbols = self._normalize_symbols(symbols)
        constraints = self._normalize_constraints(
            min_cash_weight=min_cash_weight,
            max_position_weight=max_position_weight,
            max_sector_weight=max_sector_weight,
        )

        returns, excluded, warnings, data_start, data_end = self._load_returns(
            normalized_symbols,
            start=start,
            end=end,
            lookback=lookback,
        )
        if returns.empty:
            raise ValueError("no valid return history available for portfolio construction")

        used_symbols = list(returns.columns)
        covariance = returns.cov()
        correlation = returns.corr()
        volatility = {
            symbol: float(returns[symbol].std())
            for symbol in used_symbols
        }

        if normalized_method == "equal_weight":
            raw_weights = self._equal_weight(used_symbols, constraints["min_cash_weight"])
        elif normalized_method == "inverse_volatility":
            raw_weights = self._inverse_volatility(used_symbols, volatility, constraints["min_cash_weight"], warnings)
        elif normalized_method == "risk_parity":
            raw_weights = self._risk_parity(used_symbols, covariance, constraints["min_cash_weight"], warnings)
        else:
            raw_weights = self._min_variance(used_symbols, covariance, constraints["min_cash_weight"], warnings)

        target_weights = self._apply_constraints(raw_weights, constraints, warnings)
        asset_weights = {
            symbol: weight
            for symbol, weight in target_weights.items()
            if symbol != "cash"
        }
        portfolio_volatility, marginal_risk_contributions, risk_contributions, risk_contribution_pct = self._risk_contributions(
            asset_weights,
            covariance,
        )

        targets_path = self._write_targets(target_weights, output_targets) if output_targets else None
        result = PortfolioConstructionResult(
            method=normalized_method,
            symbols_requested=normalized_symbols,
            symbols_used=used_symbols,
            excluded_symbols=sorted(excluded),
            exclusion_reasons={symbol: excluded[symbol] for symbol in sorted(excluded)},
            start_date=data_start,
            end_date=data_end,
            lookback=lookback,
            no_lookahead=True,
            target_weights=target_weights,
            cash_weight=target_weights.get("cash", 0.0),
            constraints=constraints,
            volatility=self._round_dict(volatility),
            covariance_matrix=self._frame_to_nested_dict(covariance),
            correlation_matrix=self._frame_to_nested_dict(correlation),
            portfolio_volatility=round(portfolio_volatility, 10) if portfolio_volatility is not None else None,
            marginal_risk_contributions=self._round_dict(marginal_risk_contributions),
            risk_contributions=self._round_dict(risk_contributions),
            risk_contribution_pct=self._round_dict(risk_contribution_pct),
            warnings=warnings,
            output_targets_path=str(targets_path) if targets_path else None,
            report_path="",
        )
        report_path = self._write_report(result) if write_report else ""
        return replace(result, report_path=str(report_path))

    def _load_returns(
        self,
        symbols: list[str],
        start: str | None,
        end: str | None,
        lookback: int,
    ) -> tuple[pd.DataFrame, dict[str, str], list[str], str | None, str | None]:
        excluded: dict[str, str] = {}
        warnings: list[str] = []
        frames = []
        for symbol in symbols:
            history = self.price_store.get_price_history(symbol, start=start, end=end)
            if history.empty:
                excluded[symbol] = "no price data"
                warnings.append(f"excluded {symbol}: no price data")
                continue
            history = history.sort_values("date").tail(lookback + 1)
            closes = pd.to_numeric(history["close"], errors="coerce")
            if closes.notna().sum() < 3:
                excluded[symbol] = "insufficient close history"
                warnings.append(f"excluded {symbol}: insufficient close history")
                continue
            series = pd.Series(
                closes.to_numpy(dtype="float64"),
                index=pd.to_datetime(history["date"]),
                name=symbol,
            )
            returns = series.pct_change().dropna()
            if len(returns) < 2:
                excluded[symbol] = "insufficient return history"
                warnings.append(f"excluded {symbol}: insufficient return history")
                continue
            if float(returns.std()) <= 0:
                excluded[symbol] = "zero volatility"
                warnings.append(f"excluded {symbol}: zero volatility")
                continue
            frames.append(returns)

        if not frames:
            return pd.DataFrame(), excluded, warnings, None, None

        frame = pd.concat(frames, axis=1, join="inner").dropna()
        for symbol in list(frame.columns):
            if len(frame[symbol].dropna()) < 2:
                excluded[symbol] = "insufficient aligned return history"
                warnings.append(f"excluded {symbol}: insufficient aligned return history")
                frame = frame.drop(columns=[symbol])
        if frame.empty:
            return pd.DataFrame(), excluded, warnings, None, None
        return (
            frame,
            excluded,
            warnings,
            frame.index.min().strftime("%Y-%m-%d"),
            frame.index.max().strftime("%Y-%m-%d"),
        )

    @staticmethod
    def _equal_weight(symbols: list[str], min_cash_weight: float) -> dict[str, float]:
        investable = max(1.0 - min_cash_weight, 0.0)
        weight = investable / len(symbols)
        return {symbol: weight for symbol in symbols}

    @staticmethod
    def _inverse_volatility(
        symbols: list[str],
        volatility: dict[str, float],
        min_cash_weight: float,
        warnings: list[str],
    ) -> dict[str, float]:
        inverse = {}
        for symbol in symbols:
            vol = volatility.get(symbol, 0.0)
            if vol <= 0 or pd.isna(vol):
                warnings.append(f"using neutral inverse volatility for {symbol}: non-positive volatility")
                inverse[symbol] = 1.0
            else:
                inverse[symbol] = 1.0 / vol
        total = sum(inverse.values())
        investable = max(1.0 - min_cash_weight, 0.0)
        return {symbol: (inverse[symbol] / total) * investable for symbol in symbols}

    def _risk_parity(
        self,
        symbols: list[str],
        covariance: pd.DataFrame,
        min_cash_weight: float,
        warnings: list[str],
    ) -> dict[str, float]:
        investable = max(1.0 - min_cash_weight, 0.0)
        weights = pd.Series(1.0 / len(symbols), index=symbols, dtype="float64")
        covariance = covariance.loc[symbols, symbols]
        for _ in range(250):
            _, _, _, pct = self._risk_contributions(weights.to_dict(), covariance)
            if not pct:
                warnings.append("risk parity fell back to inverse volatility: invalid covariance")
                vols = {symbol: float(covariance.loc[symbol, symbol] ** 0.5) for symbol in symbols}
                return self._inverse_volatility(symbols, vols, min_cash_weight, warnings)
            target = 1.0 / len(symbols)
            adjustment = pd.Series({symbol: target / max(pct.get(symbol, 0.0), 1e-8) for symbol in symbols})
            weights = weights * adjustment.pow(0.35)
            weights = weights.clip(lower=0.0)
            total = float(weights.sum())
            if total <= 0 or pd.isna(total):
                warnings.append("risk parity fell back to equal weight: invalid iteration")
                return self._equal_weight(symbols, min_cash_weight)
            weights = weights / total
            spread = max(abs(pct.get(symbol, 0.0) - target) for symbol in symbols)
            if spread < 0.01:
                break
        return {symbol: float(weight * investable) for symbol, weight in weights.items()}

    def _min_variance(
        self,
        symbols: list[str],
        covariance: pd.DataFrame,
        min_cash_weight: float,
        warnings: list[str],
    ) -> dict[str, float]:
        try:
            cov = covariance.loc[symbols, symbols].astype(float)
            matrix = cov.to_numpy(dtype="float64")
            if not np.isfinite(matrix).all():
                raise ValueError("non-finite covariance")
            inverse = np.linalg.inv(matrix)
            ones = np.ones(len(symbols))
            denominator = float(ones.T @ inverse @ ones)
            if denominator <= 0 or not np.isfinite(denominator):
                raise ValueError("invalid minimum variance denominator")
            raw = inverse @ ones / denominator
            if (raw < 0).any():
                warnings.append("min_variance projected negative unconstrained weights to zero")
                raw = np.clip(raw, 0.0, None)
                raw_total = float(raw.sum())
                if raw_total <= 0 or not np.isfinite(raw_total):
                    raise ValueError("invalid long-only minimum variance projection")
                raw = raw / raw_total
            investable = max(1.0 - min_cash_weight, 0.0)
            return {symbol: float(raw[index] * investable) for index, symbol in enumerate(symbols)}
        except Exception:
            warnings.append("min_variance fell back to inverse_volatility because covariance was insufficient")
            vols = {}
            for symbol in symbols:
                variance = float(covariance.loc[symbol, symbol])
                vols[symbol] = float(variance ** 0.5) if variance > 0 and not pd.isna(variance) else 0.0
            return self._inverse_volatility(symbols, vols, min_cash_weight, warnings)

    def _apply_constraints(
        self,
        raw_weights: dict[str, float],
        constraints: dict,
        warnings: list[str],
    ) -> dict[str, float]:
        if constraints["only_long"] and any(weight < 0 for weight in raw_weights.values()):
            raise ValueError("only_long requires non-negative weights")

        weights = {
            symbol: min(max(float(weight), 0.0), constraints["max_position_weight"])
            for symbol, weight in raw_weights.items()
        }
        for symbol, raw_weight in raw_weights.items():
            if raw_weight > constraints["max_position_weight"]:
                warnings.append(f"capped {symbol} to max_position_weight")

        for sector in sorted({self.sector_map.get(symbol, "Unknown") for symbol in weights}):
            if sector == "Unknown":
                continue
            symbols = [symbol for symbol in weights if self.sector_map.get(symbol, "Unknown") == sector]
            sector_weight = sum(weights[symbol] for symbol in symbols)
            if sector_weight > constraints["max_sector_weight"]:
                scale = constraints["max_sector_weight"] / sector_weight
                warnings.append(f"scaled {sector} sector to max_sector_weight")
                for symbol in symbols:
                    weights[symbol] *= scale

        total_asset_weight = sum(weights.values())
        max_investable = max(1.0 - constraints["min_cash_weight"], 0.0)
        if total_asset_weight > max_investable and total_asset_weight > 0:
            scale = max_investable / total_asset_weight
            weights = {symbol: weight * scale for symbol, weight in weights.items()}
            total_asset_weight = sum(weights.values())

        rounded = {
            symbol: round(weight, 6)
            for symbol, weight in sorted(weights.items())
            if weight > 0
        }
        rounded["cash"] = round(1.0 - sum(rounded.values()), 6)
        if abs(sum(rounded.values()) - 1.0) > 1e-9:
            rounded["cash"] = round(rounded["cash"] + (1.0 - sum(rounded.values())), 6)
        return rounded

    @staticmethod
    def _risk_contributions(
        weights: dict[str, float],
        covariance: pd.DataFrame,
    ) -> tuple[float | None, dict[str, float], dict[str, float], dict[str, float]]:
        symbols = [symbol for symbol in weights if symbol in covariance.index]
        if not symbols:
            return None, {}, {}, {}
        weight_series = pd.Series({symbol: weights[symbol] for symbol in symbols}, dtype="float64")
        cov = covariance.loc[symbols, symbols]
        variance = float(weight_series.T @ cov @ weight_series)
        if variance <= 0 or pd.isna(variance):
            zeroes = {symbol: 0.0 for symbol in symbols}
            return None, zeroes, zeroes, zeroes
        volatility = variance ** 0.5
        marginal = cov @ weight_series / volatility
        total_contrib = weight_series * marginal
        total = float(total_contrib.sum())
        pct = {
            symbol: (float(total_contrib[symbol]) / total if total else 0.0)
            for symbol in symbols
        }
        return (
            volatility,
            {symbol: float(marginal[symbol]) for symbol in symbols},
            {symbol: float(total_contrib[symbol]) for symbol in symbols},
            pct,
        )

    @staticmethod
    def _normalize_symbols(symbols: list[str]) -> list[str]:
        return normalize_symbols(
            symbols,
            exclude={"CASH"},
            require_non_empty=True,
            empty_message="at least one non-cash symbol is required",
        )

    @staticmethod
    def _normalize_constraints(
        min_cash_weight: float,
        max_position_weight: float,
        max_sector_weight: float,
    ) -> dict:
        constraints = {
            "min_cash_weight": float(min_cash_weight),
            "max_position_weight": float(max_position_weight),
            "max_sector_weight": float(max_sector_weight),
            "only_long": True,
        }
        if not 0 <= constraints["min_cash_weight"] <= 1:
            raise ValueError("min_cash_weight must be between 0 and 1")
        if not 0 < constraints["max_position_weight"] <= 1:
            raise ValueError("max_position_weight must be between 0 and 1")
        if not 0 < constraints["max_sector_weight"] <= 1:
            raise ValueError("max_sector_weight must be between 0 and 1")
        return constraints

    @staticmethod
    def _frame_to_nested_dict(frame: pd.DataFrame) -> dict[str, dict[str, float]]:
        return {
            str(row): {
                str(column): round(float(value), 10)
                for column, value in values.items()
                if pd.notna(value)
            }
            for row, values in frame.to_dict(orient="index").items()
        }

    @staticmethod
    def _round_dict(values: dict[str, float]) -> dict[str, float]:
        return {
            key: round(float(value), 10)
            for key, value in sorted(values.items())
            if pd.notna(value)
        }

    def _write_targets(self, target_weights: dict[str, float], output_targets: str | Path) -> Path:
        return write_json_report(output_targets, target_weights, sort_keys=True)

    def _write_report(self, result: PortfolioConstructionResult) -> Path:
        return write_json_report(
            generate_report_path(self.report_dir, "portfolio_construction"),
            result.to_report(),
        )
