"""Deterministic slippage models for historical simulation."""

from __future__ import annotations

import math


DEFAULT_SLIPPAGE_CONFIG = {
    "model": "bps",
    "fixed_amount": 0.0,
    "bps": 5.0,
    "volume_scaled_bps": 20.0,
    "volatility_multiplier": 0.25,
}


class SlippageModel:
    """Estimate per-trade slippage cost without changing execution price."""

    def __init__(self, config: dict | str | None = None) -> None:
        if isinstance(config, str):
            config = {"model": config}
        merged = dict(DEFAULT_SLIPPAGE_CONFIG)
        merged.update(config or {})
        merged["model"] = str(merged["model"]).lower().strip()
        if merged["model"] not in {"fixed", "bps", "volume_scaled", "volatility_scaled"}:
            raise ValueError("slippage model must be one of: fixed, bps, volume_scaled, volatility_scaled")
        for key in ("fixed_amount", "bps", "volume_scaled_bps", "volatility_multiplier"):
            merged[key] = float(merged[key])
            if merged[key] < 0:
                raise ValueError(f"{key} must be non-negative")
        self.config = merged

    def estimate(
        self,
        notional: float,
        shares: int,
        price: float,
        average_daily_volume: float | None = None,
        volatility: float | None = None,
    ) -> float:
        if notional <= 0 or shares <= 0 or price <= 0 or not all(math.isfinite(v) for v in (notional, shares, price)):
            return 0.0
        model = self.config["model"]
        if model == "fixed":
            return self.config["fixed_amount"]
        if model == "bps":
            return notional * self.config["bps"] / 10000.0
        if model == "volume_scaled":
            usage = self._volume_usage(shares, average_daily_volume)
            return notional * (self.config["volume_scaled_bps"] * usage) / 10000.0
        if model == "volatility_scaled":
            vol = max(float(volatility or 0.0), 0.0)
            return notional * vol * self.config["volatility_multiplier"]
        return 0.0

    @staticmethod
    def _volume_usage(shares: int, average_daily_volume: float | None) -> float:
        if average_daily_volume is None or average_daily_volume <= 0 or not math.isfinite(float(average_daily_volume)):
            return 0.0
        return max(float(shares) / float(average_daily_volume), 0.0)
