"""Alpha factor engine for target allocation generation."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Mapping

import pandas as pd

from quant.config import DEFAULT_SYMBOLS
from quant.storage.sqlite_store import SQLitePriceStore


DEFAULT_ALPHA_CONFIG = {
    "universe": list(DEFAULT_SYMBOLS),
    "as_of_date": None,
    "lookback_short": 20,
    "lookback_long": 60,
    "top_n": 5,
    "weighting_mode": "equal_weight",
    "min_cash_weight": 0.10,
    "max_position_weight": 0.20,
}


@dataclass(frozen=True)
class AlphaFactorRow:
    symbol: str
    as_of_date: str | None
    data_start_date: str | None
    data_end_date: str | None
    lookback_used: dict[str, int]
    momentum_20d: float | None
    momentum_60d: float | None
    volatility_20d: float | None
    risk_adjusted_momentum: float | None
    rank: int | None
    selected: bool
    excluded: bool
    exclusion_reason: str | None


@dataclass(frozen=True)
class AlphaResult:
    config: dict
    as_of_date: str | None
    data_start_date: str | None
    data_end_date: str | None
    lookback_used: dict[str, int]
    factors: list[AlphaFactorRow]
    selected_symbols: list[str]
    target_weights: dict[str, float]
    excluded_symbols: list[str]
    exclusion_reasons: dict[str, str]
    suggested_execution_date: str | None
    warnings: list[str]
    report_path: str
    targets_path: str | None

    def to_report(self) -> dict:
        return {
            "config": self.config,
            "as_of_date": self.as_of_date,
            "data_start_date": self.data_start_date,
            "data_end_date": self.data_end_date,
            "lookback_used": self.lookback_used,
            "factors": [asdict(row) for row in self.factors],
            "selected_symbols": self.selected_symbols,
            "target_weights": self.target_weights,
            "excluded_symbols": self.excluded_symbols,
            "exclusion_reasons": self.exclusion_reasons,
            "suggested_execution_date": self.suggested_execution_date,
            "warnings": self.warnings,
            "targets_path": self.targets_path,
        }


class AlphaEngine:
    """Generate alpha factors and target weights from stored price history."""

    def __init__(
        self,
        price_store: SQLitePriceStore,
        report_dir: str | Path = "reports",
    ) -> None:
        self.price_store = price_store
        self.report_dir = Path(report_dir)

    def generate(
        self,
        config: Mapping | None = None,
        output_targets: str | Path | None = None,
    ) -> AlphaResult:
        normalized_config = self._normalize_config(config or {})
        warnings: list[str] = []
        lookback_used = self._lookback_used(normalized_config)

        factor_rows = [
            self._factor_row(symbol, normalized_config, warnings)
            for symbol in normalized_config["universe"]
        ]
        ranked_rows = self._rank_rows(factor_rows)
        selected_symbols = [
            row.symbol
            for row in sorted(
                [row for row in ranked_rows if row.rank is not None and row.rank <= normalized_config["top_n"]],
                key=lambda row: row.rank or 0,
            )
        ]
        ranked_rows = self._mark_selected(ranked_rows, selected_symbols)
        selected_rows = sorted(
            [row for row in ranked_rows if row.selected],
            key=lambda row: row.rank or 0,
        )
        if not selected_rows:
            raise ValueError("no symbols have enough price history for alpha generation")

        target_weights = self._target_weights(
            selected_rows,
            normalized_config["weighting_mode"],
            normalized_config["min_cash_weight"],
            normalized_config["max_position_weight"],
            warnings,
        )
        self._validate_targets(target_weights, normalized_config)
        excluded_symbols = [row.symbol for row in ranked_rows if row.excluded]
        exclusion_reasons = {
            row.symbol: row.exclusion_reason or "excluded"
            for row in ranked_rows
            if row.excluded
        }
        as_of_date = self._result_as_of_date(selected_rows)
        data_start_date = self._min_date(row.data_start_date for row in selected_rows)
        data_end_date = self._max_date(row.data_end_date for row in selected_rows)
        suggested_execution_date = self._suggested_execution_date(selected_rows, as_of_date)
        target_output = self._write_targets(target_weights, output_targets) if output_targets else None

        result = AlphaResult(
            config=normalized_config,
            as_of_date=as_of_date,
            data_start_date=data_start_date,
            data_end_date=data_end_date,
            lookback_used=lookback_used,
            factors=ranked_rows,
            selected_symbols=selected_symbols,
            target_weights=target_weights,
            excluded_symbols=excluded_symbols,
            exclusion_reasons=exclusion_reasons,
            suggested_execution_date=suggested_execution_date,
            warnings=warnings,
            report_path="",
            targets_path=str(target_output) if target_output else None,
        )
        report_path = self._write_report(result)
        return AlphaResult(
            config=result.config,
            as_of_date=result.as_of_date,
            data_start_date=result.data_start_date,
            data_end_date=result.data_end_date,
            lookback_used=result.lookback_used,
            factors=result.factors,
            selected_symbols=result.selected_symbols,
            target_weights=result.target_weights,
            excluded_symbols=result.excluded_symbols,
            exclusion_reasons=result.exclusion_reasons,
            suggested_execution_date=result.suggested_execution_date,
            warnings=result.warnings,
            report_path=str(report_path),
            targets_path=result.targets_path,
        )

    def _factor_row(self, symbol: str, config: dict, warnings: list[str]) -> AlphaFactorRow:
        history = self.price_store.get_price_history(symbol, end=config["as_of_date"])
        if history.empty:
            return self._excluded_row(symbol, "no price data", warnings)

        history = history.sort_values("date")
        closes = pd.to_numeric(history["close"], errors="coerce").dropna()
        if len(closes) <= config["lookback_long"]:
            return self._excluded_row(
                symbol,
                f"need at least {config['lookback_long'] + 1} closes",
                warnings,
                data_end_date=str(history.iloc[-1]["date"]),
            )

        as_of_date = str(history.iloc[-1]["date"])
        data_start_date = str(history.iloc[-(config["lookback_long"] + 1)]["date"])
        momentum_short = self._momentum(closes, config["lookback_short"])
        momentum_long = self._momentum(closes, config["lookback_long"])
        volatility_short = self._volatility(closes, config["lookback_short"])
        if volatility_short is None:
            return self._excluded_row(
                symbol,
                "volatility_20d is unavailable",
                warnings,
                data_start_date=data_start_date,
                data_end_date=as_of_date,
            )
        if volatility_short <= 0:
            return self._excluded_row(
                symbol,
                "volatility_20d is zero",
                warnings,
                data_start_date=data_start_date,
                data_end_date=as_of_date,
            )

        risk_adjusted = momentum_long / volatility_short

        return AlphaFactorRow(
            symbol=symbol,
            as_of_date=as_of_date,
            data_start_date=data_start_date,
            data_end_date=as_of_date,
            lookback_used=self._lookback_used(config),
            momentum_20d=momentum_short,
            momentum_60d=momentum_long,
            volatility_20d=volatility_short,
            risk_adjusted_momentum=risk_adjusted,
            rank=None,
            selected=False,
            excluded=False,
            exclusion_reason=None,
        )

    @staticmethod
    def _rank_rows(rows: list[AlphaFactorRow]) -> list[AlphaFactorRow]:
        valid = sorted(
            [row for row in rows if row.risk_adjusted_momentum is not None],
            key=lambda row: (row.risk_adjusted_momentum, row.symbol),
            reverse=True,
        )
        rank_by_symbol = {row.symbol: rank for rank, row in enumerate(valid, start=1)}
        return [
            AlphaFactorRow(
                symbol=row.symbol,
                as_of_date=row.as_of_date,
                data_start_date=row.data_start_date,
                data_end_date=row.data_end_date,
                lookback_used=row.lookback_used,
                momentum_20d=row.momentum_20d,
                momentum_60d=row.momentum_60d,
                volatility_20d=row.volatility_20d,
                risk_adjusted_momentum=row.risk_adjusted_momentum,
                rank=rank_by_symbol.get(row.symbol),
                selected=False,
                excluded=row.excluded,
                exclusion_reason=row.exclusion_reason,
            )
            for row in rows
        ]

    @staticmethod
    def _mark_selected(rows: list[AlphaFactorRow], selected_symbols: list[str]) -> list[AlphaFactorRow]:
        selected = set(selected_symbols)
        return [
            AlphaFactorRow(
                symbol=row.symbol,
                as_of_date=row.as_of_date,
                data_start_date=row.data_start_date,
                data_end_date=row.data_end_date,
                lookback_used=row.lookback_used,
                momentum_20d=row.momentum_20d,
                momentum_60d=row.momentum_60d,
                volatility_20d=row.volatility_20d,
                risk_adjusted_momentum=row.risk_adjusted_momentum,
                rank=row.rank,
                selected=row.symbol in selected,
                excluded=row.excluded,
                exclusion_reason=row.exclusion_reason,
            )
            for row in rows
        ]

    @staticmethod
    def _target_weights(
        selected_rows: list[AlphaFactorRow],
        weighting_mode: str,
        min_cash_weight: float,
        max_position_weight: float,
        warnings: list[str],
    ) -> dict[str, float]:
        investable_weight = max(1.0 - min_cash_weight, 0.0)
        if weighting_mode == "equal_weight":
            raw_weights = {
                row.symbol: investable_weight / len(selected_rows)
                for row in selected_rows
            }
        else:
            positive_scores = {
                row.symbol: max(row.risk_adjusted_momentum or 0.0, 0.0)
                for row in selected_rows
            }
            total_score = sum(positive_scores.values())
            if total_score <= 0:
                warnings.append("score_weighted fallback to equal_weight because selected scores are not positive")
                raw_weights = {
                    row.symbol: investable_weight / len(selected_rows)
                    for row in selected_rows
                }
            else:
                raw_weights = {
                    symbol: (score / total_score) * investable_weight
                    for symbol, score in positive_scores.items()
                }

        capped_weights = {}
        for symbol, weight in raw_weights.items():
            capped = min(weight, max_position_weight)
            if capped < weight:
                warnings.append(f"capped {symbol} to max_position_weight {max_position_weight:.4f}")
            capped_weights[symbol] = capped

        targets = AlphaEngine._round_targets(capped_weights, min_cash_weight)
        return targets

    @staticmethod
    def _momentum(closes: pd.Series, lookback: int) -> float:
        return float((closes.iloc[-1] / closes.iloc[-(lookback + 1)]) - 1.0)

    @staticmethod
    def _volatility(closes: pd.Series, lookback: int) -> float | None:
        returns = closes.pct_change().dropna().tail(lookback)
        if returns.empty:
            return None
        return float(returns.std())

    def _excluded_row(
        self,
        symbol: str,
        reason: str,
        warnings: list[str],
        data_start_date: str | None = None,
        data_end_date: str | None = None,
    ) -> AlphaFactorRow:
        warnings.append(f"excluded {symbol}: {reason}")
        return AlphaFactorRow(
            symbol=symbol,
            as_of_date=data_end_date,
            data_start_date=data_start_date,
            data_end_date=data_end_date,
            lookback_used={},
            momentum_20d=None,
            momentum_60d=None,
            volatility_20d=None,
            risk_adjusted_momentum=None,
            rank=None,
            selected=False,
            excluded=True,
            exclusion_reason=reason,
        )

    @staticmethod
    def _normalize_config(config: Mapping) -> dict:
        merged = dict(DEFAULT_ALPHA_CONFIG)
        merged.update(dict(config))
        universe = merged.get("universe") or list(DEFAULT_SYMBOLS)
        merged["universe"] = AlphaEngine._normalize_symbols(list(universe))
        merged["as_of_date"] = merged.get("as_of_date") or None
        merged["lookback_short"] = int(merged["lookback_short"])
        merged["lookback_long"] = int(merged["lookback_long"])
        merged["top_n"] = int(merged["top_n"])
        merged["weighting_mode"] = str(merged["weighting_mode"]).lower()
        merged["min_cash_weight"] = float(merged["min_cash_weight"])
        merged["max_position_weight"] = float(merged["max_position_weight"])

        if not merged["universe"]:
            raise ValueError("alpha universe must not be empty")
        if merged["lookback_short"] <= 0:
            raise ValueError("lookback_short must be positive")
        if merged["lookback_long"] <= merged["lookback_short"]:
            raise ValueError("lookback_long must be greater than lookback_short")
        if merged["top_n"] <= 0:
            raise ValueError("top_n must be positive")
        if merged["weighting_mode"] not in {"equal_weight", "score_weighted"}:
            raise ValueError("weighting_mode must be one of: equal_weight, score_weighted")
        if not 0 <= merged["min_cash_weight"] <= 1:
            raise ValueError("min_cash_weight must be between 0 and 1")
        if not 0 < merged["max_position_weight"] <= 1:
            raise ValueError("max_position_weight must be between 0 and 1")
        return merged

    @staticmethod
    def _lookback_used(config: Mapping) -> dict[str, int]:
        return {
            "momentum_20d": int(config["lookback_short"]),
            "momentum_60d": int(config["lookback_long"]),
            "volatility_20d": int(config["lookback_short"]),
        }

    @staticmethod
    def _round_targets(raw_weights: dict[str, float], min_cash_weight: float) -> dict[str, float]:
        targets = {
            symbol: round(weight, 6)
            for symbol, weight in sorted(raw_weights.items())
            if weight > 0
        }
        cash_weight = max(min_cash_weight, 1.0 - sum(targets.values()))
        targets["cash"] = round(cash_weight, 6)
        total = round(sum(targets.values()), 6)
        if total != 1.0:
            targets["cash"] = round(targets["cash"] + (1.0 - total), 6)
        return targets

    @staticmethod
    def _validate_targets(targets: dict[str, float], config: dict) -> None:
        total_weight = round(sum(targets.values()), 6)
        if total_weight != 1.0:
            raise ValueError("alpha target weights must sum to 1.0")
        if targets.get("cash", 0.0) + 1e-12 < config["min_cash_weight"]:
            raise ValueError("alpha cash target is below min_cash_weight")
        for symbol, weight in targets.items():
            if symbol != "cash" and weight > config["max_position_weight"] + 1e-12:
                raise ValueError(f"alpha target for {symbol} exceeds max_position_weight")

    @staticmethod
    def _result_as_of_date(rows: list[AlphaFactorRow]) -> str | None:
        return AlphaEngine._max_date(row.data_end_date for row in rows)

    @staticmethod
    def _min_date(values) -> str | None:
        dates = [value for value in values if value is not None]
        return min(dates) if dates else None

    @staticmethod
    def _max_date(values) -> str | None:
        dates = [value for value in values if value is not None]
        return max(dates) if dates else None

    def _suggested_execution_date(
        self,
        selected_rows: list[AlphaFactorRow],
        as_of_date: str | None,
    ) -> str | None:
        if as_of_date is None:
            return None

        candidates = []
        for row in selected_rows:
            history = self.price_store.get_price_history(row.symbol, start=as_of_date)
            if history.empty:
                continue
            future = history[history["date"] > as_of_date]
            if not future.empty:
                candidates.append(str(future.iloc[0]["date"]))
        return min(candidates) if candidates else None

    @staticmethod
    def _normalize_symbols(symbols: list[str]) -> list[str]:
        normalized = []
        seen = set()
        for symbol in symbols:
            ticker = str(symbol).upper().strip()
            if ticker and ticker not in seen:
                normalized.append(ticker)
                seen.add(ticker)
        return normalized

    def _write_report(self, result: AlphaResult) -> Path:
        self.report_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = self.report_dir / f"alpha_{timestamp}.json"
        path.write_text(json.dumps(result.to_report(), indent=2), encoding="utf-8")
        return path

    @staticmethod
    def _write_targets(targets: dict[str, float], path: str | Path) -> Path:
        target_path = Path(path)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text(json.dumps(targets, indent=2) + "\n", encoding="utf-8")
        return target_path
