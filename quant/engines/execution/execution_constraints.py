"""Execution constraints for marketability, liquidity, and position sizing."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


DEFAULT_MARKET_REALISM_CONFIG = {
    "enabled": True,
    "adv_lookback_days": 20,
    "max_adv_participation": None,
    "max_position_notional": None,
    "max_position_weight": None,
    "min_trade_notional": 50.0,
    "enforce_min_trade_notional": False,
    "minimum_shares": 1,
}


@dataclass(frozen=True)
class ExecutionConstraintResult:
    allowed: bool
    reason: str
    adjusted_quantity: int
    warnings: list[str]
    requested_quantity: int
    rejected_quantity: int
    average_daily_volume: float | None
    adv_participation: float | None
    max_adv_quantity: int | None
    min_trade_notional: float
    minimum_shares: int

    def to_dict(self) -> dict:
        return {
            "allowed": self.allowed,
            "reason": self.reason,
            "adjusted_quantity": self.adjusted_quantity,
            "warnings": self.warnings,
            "requested_quantity": self.requested_quantity,
            "rejected_quantity": self.rejected_quantity,
            "average_daily_volume": self.average_daily_volume,
            "adv_participation": self.adv_participation,
            "max_adv_quantity": self.max_adv_quantity,
            "min_trade_notional": self.min_trade_notional,
            "minimum_shares": self.minimum_shares,
        }


class ExecutionConstraints:
    """Apply deterministic trade caps before simulated execution."""

    def __init__(self, config: Mapping | None = None) -> None:
        merged = dict(DEFAULT_MARKET_REALISM_CONFIG)
        merged.update(dict(config or {}))
        merged["enabled"] = bool(merged["enabled"])
        merged["adv_lookback_days"] = int(merged["adv_lookback_days"])
        if merged.get("max_adv_participation") is not None:
            merged["max_adv_participation"] = float(merged["max_adv_participation"])
        merged["min_trade_notional"] = float(merged["min_trade_notional"])
        merged["enforce_min_trade_notional"] = bool(merged["enforce_min_trade_notional"])
        merged["minimum_shares"] = int(merged["minimum_shares"])
        if merged["adv_lookback_days"] <= 0:
            raise ValueError("adv_lookback_days must be positive")
        if merged["max_adv_participation"] is not None and merged["max_adv_participation"] < 0:
            raise ValueError("max_adv_participation must be non-negative")
        if merged["min_trade_notional"] < 0:
            raise ValueError("min_trade_notional must be non-negative")
        if merged["minimum_shares"] < 1:
            raise ValueError("minimum_shares must be >= 1")
        if merged.get("max_position_notional") is not None:
            merged["max_position_notional"] = float(merged["max_position_notional"])
        if merged.get("max_position_weight") is not None:
            merged["max_position_weight"] = float(merged["max_position_weight"])
        self.config = merged

    def apply(
        self,
        symbol: str,
        side: str,
        requested_quantity: int,
        price: float | None,
        average_daily_volume: float | None = None,
        current_shares: int = 0,
        current_equity: float = 0.0,
    ) -> ExecutionConstraintResult:
        requested = max(int(requested_quantity), 0)
        warnings: list[str] = []
        if price is None or float(price) <= 0:
            return self._result(False, "SKIPPED_NO_PRICE", requested, 0, warnings + [f"WARN_NO_PRICE: {symbol}"], None, None)

        trade_price = float(price)
        if not self.config["enabled"]:
            return self._result(True, "OK", requested, requested, warnings, average_daily_volume, None)

        adjusted = requested
        max_adv_quantity = None
        adv_participation = None
        max_adv_participation = self.config.get("max_adv_participation")
        if average_daily_volume is not None and average_daily_volume > 0 and max_adv_participation is not None and max_adv_participation > 0:
            max_adv_quantity = int(float(average_daily_volume) * max_adv_participation)
            if adjusted > max_adv_quantity:
                adjusted = max(0, max_adv_quantity)
                warnings.append(
                    f"WARN_LIQUIDITY_CAP: {symbol} requested {requested} shares capped to {adjusted} "
                    f"by {max_adv_participation:.2%} ADV"
                )
            adv_participation = adjusted / float(average_daily_volume) if average_daily_volume else None
        elif max_adv_participation is not None and max_adv_participation > 0:
            warnings.append(f"WARN_LIQUIDITY_UNKNOWN: {symbol} ADV unavailable")

        if side.upper() == "BUY":
            adjusted = self._cap_buy_by_position_limits(symbol, adjusted, trade_price, current_shares, current_equity, warnings)

        minimum_shares = self.config["minimum_shares"]
        if adjusted < minimum_shares:
            return self._result(
                False,
                "SKIPPED_MINIMUM_SHARES",
                requested,
                0,
                warnings + [f"WARN_MINIMUM_SHARES: {symbol} adjusted quantity {adjusted} below {minimum_shares}"],
                average_daily_volume,
                adv_participation,
                max_adv_quantity,
            )

        notional = adjusted * trade_price
        if notional < self.config["min_trade_notional"]:
            warning = (
                f"WARN_MIN_TRADE_NOTIONAL: {symbol} notional {notional:.2f} below "
                f"{self.config['min_trade_notional']:.2f}"
            )
            warnings.append(warning)
            if self.config["enforce_min_trade_notional"]:
                return self._result(False, "SKIPPED_MIN_NOTIONAL", requested, 0, warnings, average_daily_volume, adv_participation, max_adv_quantity)

        reason = "OK" if adjusted == requested else "ADJUSTED_BY_CONSTRAINTS"
        return self._result(True, reason, requested, adjusted, warnings, average_daily_volume, adv_participation, max_adv_quantity)

    def _cap_buy_by_position_limits(
        self,
        symbol: str,
        adjusted: int,
        price: float,
        current_shares: int,
        current_equity: float,
        warnings: list[str],
    ) -> int:
        caps = []
        if self.config.get("max_position_notional") is not None:
            caps.append(float(self.config["max_position_notional"]))
        if self.config.get("max_position_weight") is not None and current_equity > 0:
            caps.append(float(self.config["max_position_weight"]) * float(current_equity))
        if not caps:
            return adjusted
        max_position_value = min(caps)
        current_value = max(current_shares, 0) * price
        available_notional = max(0.0, max_position_value - current_value)
        capped = min(adjusted, int(available_notional // price))
        if capped < adjusted:
            warnings.append(f"WARN_POSITION_LIMIT: {symbol} buy capped from {adjusted} to {capped}")
        return capped

    def _result(
        self,
        allowed: bool,
        reason: str,
        requested: int,
        adjusted: int,
        warnings: list[str],
        average_daily_volume: float | None,
        adv_participation: float | None,
        max_adv_quantity: int | None = None,
    ) -> ExecutionConstraintResult:
        return ExecutionConstraintResult(
            allowed=allowed,
            reason=reason,
            adjusted_quantity=int(adjusted),
            warnings=warnings,
            requested_quantity=int(requested),
            rejected_quantity=max(0, int(requested) - int(adjusted)),
            average_daily_volume=average_daily_volume,
            adv_participation=adv_participation,
            max_adv_quantity=max_adv_quantity,
            min_trade_notional=float(self.config["min_trade_notional"]),
            minimum_shares=int(self.config["minimum_shares"]),
        )
