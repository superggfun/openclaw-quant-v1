"""Portfolio target allocation optimizer."""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Mapping

import numpy as np
import pandas as pd

from quant.config import DEFAULT_SYMBOLS
from quant.core.symbols import normalize_symbols
from quant.engines.portfolio.rebalance_engine import RebalanceEngine
from quant.engines.risk.risk_engine import DEFAULT_INDUSTRY_MAP, RiskEngine
from quant.reports.report_io import generate_report_path, write_json_report
from quant.storage.portfolio_store import DEFAULT_ACCOUNT_NAME, SQLitePortfolioStore
from quant.storage.sqlite_store import SQLitePriceStore


DEFAULT_CONSTRAINTS = {
    "max_position_weight": 0.20,
    "min_cash_weight": 0.10,
    "max_sector_weight": 0.50,
    "only_long": True,
}


@dataclass(frozen=True)
class OptimizerResult:
    mode: str
    current_allocation: dict[str, float]
    optimized_allocation: dict[str, float]
    constraints: dict
    warnings: list[str]
    risk_score_before: float
    estimated_risk_score_after: float
    rationale: list[str]
    report_path: str
    targets_path: str | None

    def to_report(self) -> dict:
        return {
            "mode": self.mode,
            "current_allocation": self.current_allocation,
            "optimized_allocation": self.optimized_allocation,
            "constraints": self.constraints,
            "warnings": self.warnings,
            "risk_score_before": self.risk_score_before,
            "estimated_risk_score_after": self.estimated_risk_score_after,
            "rationale": self.rationale,
            "targets_path": self.targets_path,
        }


class OptimizerEngine:
    """Generate target allocations for the Rebalance Engine."""

    def __init__(
        self,
        price_store: SQLitePriceStore,
        portfolio_store: SQLitePortfolioStore,
        account_name: str = DEFAULT_ACCOUNT_NAME,
        report_dir: str | Path = "reports",
        industry_map: dict[str, str] | None = None,
    ) -> None:
        self.price_store = price_store
        self.portfolio_store = portfolio_store
        self.account_name = account_name
        self.report_dir = Path(report_dir)
        self.industry_map = industry_map or DEFAULT_INDUSTRY_MAP
        self.rebalance_engine = RebalanceEngine(
            portfolio_store,
            account_name=account_name,
            report_dir=report_dir,
        )
        self.risk_engine = RiskEngine(
            portfolio_store,
            account_name=account_name,
            report_dir=report_dir,
            industry_map=self.industry_map,
        )

    def optimize(
        self,
        mode: str = "equal_weight",
        symbols: list[str] | None = None,
        constraints: Mapping | None = None,
        targets_path: str | Path | None = None,
    ) -> OptimizerResult:
        normalized_mode = mode.strip().lower()
        if normalized_mode not in {"equal_weight", "risk_adjusted", "constrained", "min_variance", "risk_parity"}:
            raise ValueError("mode must be one of: equal_weight, risk_adjusted, constrained")

        merged_constraints = self._normalize_constraints(constraints or {})
        universe = self._normalize_symbols(symbols or list(DEFAULT_SYMBOLS))
        available_symbols, warnings = self._available_symbols(universe)
        if not available_symbols:
            raise ValueError("no price data found for optimizer universe")

        current_allocation = self._current_allocation()
        risk_score_before = self.risk_engine.analyze().risk_score

        if normalized_mode == "equal_weight":
            raw_weights = self._equal_weights(available_symbols, merged_constraints["min_cash_weight"])
            rationale = ["Generated equal weights across symbols with available price data."]
        elif normalized_mode == "risk_adjusted":
            raw_weights = self._risk_adjusted_weights(
                available_symbols,
                merged_constraints["min_cash_weight"],
                warnings,
            )
            rationale = ["Weighted symbols inversely to recent volatility from stored prices."]
        elif normalized_mode in ("min_variance", "risk_parity"):
            end_date = merged_constraints.get("covariance_end_date", str(pd.Timestamp.now().date()))
            lookback = int(merged_constraints.get("covariance_lookback_days", 252))
            cov, cov_symbols = self._build_covariance_matrix(
                available_symbols, end_date=end_date, lookback_days=lookback
            )
            if len(cov_symbols) < 2:
                warnings.append("COVARIANCE_FALLBACK: fewer than 2 symbols with price history; using equal weight")
                raw_weights = self._equal_weights(available_symbols, merged_constraints["min_cash_weight"])
                rationale = ["Fell back to equal weight (insufficient data for covariance)."]
            else:
                if normalized_mode == "min_variance":
                    w = self._min_variance_weights(cov)
                    rationale = [f"Minimum variance weights from {lookback}d covariance matrix ({len(cov_symbols)} symbols)."]
                else:
                    w = self._risk_parity_weights(cov)
                    rationale = [f"Risk parity weights from {lookback}d covariance matrix ({len(cov_symbols)} symbols)."]
                raw_weights = {s: float(w[i]) for i, s in enumerate(cov_symbols)}
        else:
            raw_weights = self._equal_weights(available_symbols, merged_constraints["min_cash_weight"])
            rationale = ["Generated constrained equal weights, then applied position and sector caps."]

        optimized_allocation = self._apply_constraints(raw_weights, merged_constraints, warnings)
        estimated_risk_score_after = self._estimate_risk_score(optimized_allocation)
        rationale.append("Applied max position, max sector, min cash, and long-only constraints.")
        rationale.append("Any unallocated weight is assigned to cash.")

        target_output = self._write_targets(optimized_allocation, targets_path) if targets_path else None
        result = OptimizerResult(
            mode=normalized_mode,
            current_allocation=current_allocation,
            optimized_allocation=optimized_allocation,
            constraints=merged_constraints,
            warnings=warnings,
            risk_score_before=risk_score_before,
            estimated_risk_score_after=estimated_risk_score_after,
            rationale=rationale,
            report_path="",
            targets_path=str(target_output) if target_output else None,
        )
        report_path = self._write_report(result)
        return replace(result, report_path=str(report_path))

    def _build_covariance_matrix(
        self,
        symbols: list[str],
        end_date: str,
        lookback_days: int = 252,
    ) -> tuple:
        import pandas as _pd
        end_ts = _pd.to_datetime(end_date)
        start_ts = end_ts - _pd.Timedelta(days=lookback_days * 3)

        returns_dict = {}
        valid_symbols = []
        for symbol in symbols:
            history = self.price_store.get_price_history(str(symbol), start=str(start_ts.date()), end=str(end_ts.date()))
            if history.empty:
                continue
            history = history.sort_values("date")
            history["close"] = _pd.to_numeric(history["close"], errors="coerce")
            history = history.dropna(subset=["close"])
            if len(history) < lookback_days // 3:
                continue
            rets = history["close"].pct_change().dropna().tail(lookback_days)
            if len(rets) < lookback_days // 3:
                continue
            returns_dict[symbol] = rets.values
            valid_symbols.append(symbol)

        if len(valid_symbols) < 2:
            n = max(len(valid_symbols), 1)
            return np.eye(n), valid_symbols

        aligned = _pd.DataFrame(returns_dict).dropna()
        if len(aligned) < 20:
            aligned = _pd.DataFrame(returns_dict)

        cov = aligned.cov().values
        diag = np.diag(np.diag(cov))
        cov = 0.6 * cov + 0.4 * diag
        return cov, valid_symbols

    @staticmethod
    def _min_variance_weights(cov: np.ndarray) -> np.ndarray:
        n = cov.shape[0]
        if n == 0:
            return np.array([])
        if n == 1:
            return np.array([1.0])
        try:
            inv = np.linalg.pinv(cov)
            ones = np.ones((n, 1))
            w = (inv @ ones).flatten()
            w = np.clip(w, 0, None)
            total = w.sum()
            return w / total if total > 1e-12 else np.full(n, 1.0 / n)
        except Exception:
            return np.full(n, 1.0 / n)

    @staticmethod
    def _risk_parity_weights(cov: np.ndarray, max_iter: int = 50) -> np.ndarray:
        n = cov.shape[0]
        if n == 0:
            return np.array([])
        if n == 1:
            return np.array([1.0])
        w = np.full(n, 1.0 / n)
        for _ in range(max_iter):
            rc = w * (cov @ w)
            target = rc.mean()
            if target < 1e-12:
                break
            w = w * target / np.maximum(rc, 1e-12)
            w = np.clip(w, 0, None)
            total = w.sum()
            if total < 1e-12:
                return np.full(n, 1.0 / n)
            w = w / total
        return w

    def _current_allocation(self) -> dict[str, float]:
        allocation = self.rebalance_engine.allocation()
        return {item.symbol: round(item.current_weight, 6) for item in allocation.items}

    def _available_symbols(self, symbols: list[str]) -> tuple[list[str], list[str]]:
        available = []
        warnings = []
        for symbol in symbols:
            if self.portfolio_store.latest_close(symbol) is None:
                warnings.append(f"skipped {symbol}: no latest price data")
            else:
                available.append(symbol)
        return available, warnings

    def _equal_weights(self, symbols: list[str], min_cash_weight: float) -> dict[str, float]:
        investable_weight = max(1.0 - min_cash_weight, 0.0)
        symbol_weight = investable_weight / len(symbols)
        return {symbol: symbol_weight for symbol in symbols}

    def _risk_adjusted_weights(
        self,
        symbols: list[str],
        min_cash_weight: float,
        warnings: list[str],
    ) -> dict[str, float]:
        inverse_risks = {}
        for symbol in symbols:
            history = self.price_store.get_price_history(symbol)
            if len(history) < 3:
                warnings.append(f"using neutral risk for {symbol}: insufficient history")
                inverse_risks[symbol] = 1.0
                continue

            closes = pd.to_numeric(history["close"], errors="coerce").dropna()
            returns = closes.pct_change().dropna()
            volatility = float(returns.std()) if not returns.empty else 0.0
            inverse_risks[symbol] = 1.0 / max(volatility, 0.0001)

        total_inverse_risk = sum(inverse_risks.values())
        investable_weight = max(1.0 - min_cash_weight, 0.0)
        return {
            symbol: (inverse_risk / total_inverse_risk) * investable_weight
            for symbol, inverse_risk in inverse_risks.items()
        }

    def _apply_constraints(
        self,
        raw_weights: dict[str, float],
        constraints: dict,
        warnings: list[str],
    ) -> dict[str, float]:
        if constraints["only_long"] and any(weight < 0 for weight in raw_weights.values()):
            raise ValueError("only_long requires non-negative weights")

        capped = {
            symbol: min(max(weight, 0.0), constraints["max_position_weight"])
            for symbol, weight in raw_weights.items()
        }

        sector_totals: dict[str, float] = {}
        for symbol, weight in capped.items():
            sector = self.industry_map.get(symbol, "Unknown")
            sector_totals[sector] = sector_totals.get(sector, 0.0) + weight

        adjusted = dict(capped)
        for sector, sector_weight in sector_totals.items():
            if sector_weight > constraints["max_sector_weight"]:
                scale = constraints["max_sector_weight"] / sector_weight
                warnings.append(f"scaled {sector} sector to max_sector_weight")
                for symbol in list(adjusted):
                    if self.industry_map.get(symbol, "Unknown") == sector:
                        adjusted[symbol] *= scale

        total_asset_weight = sum(adjusted.values())
        if total_asset_weight > 1.0:
            scale = 1.0 / total_asset_weight
            warnings.append("scaled asset weights because total weight exceeded 1.0")
            adjusted = {symbol: weight * scale for symbol, weight in adjusted.items()}
            total_asset_weight = 1.0

        cash_weight = max(1.0 - total_asset_weight, constraints["min_cash_weight"])
        if total_asset_weight + cash_weight > 1.0:
            scale = (1.0 - cash_weight) / total_asset_weight if total_asset_weight > 0 else 0.0
            adjusted = {symbol: weight * scale for symbol, weight in adjusted.items()}

        optimized = {
            symbol: round(weight, 6)
            for symbol, weight in sorted(adjusted.items())
            if weight > 0
        }
        optimized["cash"] = round(1.0 - sum(optimized.values()), 6)
        return optimized

    def _estimate_risk_score(self, allocation: dict[str, float]) -> float:
        stock_weights_pct = [
            weight * 100.0
            for symbol, weight in allocation.items()
            if symbol != "cash"
        ]
        industry_weights: dict[str, float] = {}
        for symbol, weight in allocation.items():
            if symbol == "cash":
                continue
            industry = self.industry_map.get(symbol, "Unknown")
            industry_weights[industry] = industry_weights.get(industry, 0.0) + (weight * 100.0)

        return RiskEngine._risk_score(
            single_stock_concentration_pct=max(stock_weights_pct, default=0.0),
            industry_concentration_pct=max(industry_weights.values(), default=0.0),
            cash_weight_pct=allocation.get("cash", 0.0) * 100.0,
            top_5_holdings_pct=sum(sorted(stock_weights_pct, reverse=True)[:5]),
        )

    @staticmethod
    def _normalize_symbols(symbols: list[str]) -> list[str]:
        return normalize_symbols(symbols)

    @staticmethod
    def _normalize_constraints(constraints: Mapping) -> dict:
        merged = dict(DEFAULT_CONSTRAINTS)
        merged.update(dict(constraints))
        merged["max_position_weight"] = float(merged["max_position_weight"])
        merged["min_cash_weight"] = float(merged["min_cash_weight"])
        merged["max_sector_weight"] = float(merged["max_sector_weight"])
        merged["only_long"] = bool(merged["only_long"])

        if merged["max_position_weight"] <= 0:
            raise ValueError("max_position_weight must be positive")
        if not 0 <= merged["min_cash_weight"] <= 1:
            raise ValueError("min_cash_weight must be between 0 and 1")
        if not 0 < merged["max_sector_weight"] <= 1:
            raise ValueError("max_sector_weight must be between 0 and 1")
        return merged

    def _write_report(self, result: OptimizerResult) -> Path:
        return write_json_report(
            generate_report_path(self.report_dir, "optimize"),
            result.to_report(),
        )

    @staticmethod
    def _write_targets(allocation: dict[str, float], path: str | Path) -> Path:
        return write_json_report(path, allocation, trailing_newline=True)
