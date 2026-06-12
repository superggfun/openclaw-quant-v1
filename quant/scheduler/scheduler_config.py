"""Configuration helpers for daily research scheduler runs."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from quant.config import DEFAULT_SYMBOLS


DEFAULT_RESEARCH_FACTORS = ("momentum_20d", "risk_adjusted_momentum")


@dataclass(frozen=True)
class SchedulerConfig:
    """Normalized scheduler settings."""

    run_data_refresh: bool = True
    run_data_coverage: bool = True
    run_fundamental_coverage: bool = True
    run_factor_eval: bool = True
    run_factor_store_update: bool = True
    run_regime_detection: bool = True
    run_trade_sim: bool = True
    run_visualization: bool = True
    run_agent_export: bool = True
    symbols: list[str] = field(default_factory=lambda: list(DEFAULT_SYMBOLS))
    factors: list[str] = field(default_factory=lambda: list(DEFAULT_RESEARCH_FACTORS))
    forward_days: int = 20
    data_start_date: str | None = None
    data_end_date: str | None = None
    trade_sim_start: str = "2024-01-01"
    trade_sim_end: str = "2025-01-01"
    trade_sim_initial_cash: float = 100000.0
    trade_sim_rebalance_frequency: str = "monthly"
    trade_sim_portfolio_method: str = "equal_weight"
    alpha_config_path: str = "examples/alpha_config.json"
    cost_config_path: str = "examples/cost_config.json"
    market_realism_config_path: str = "examples/market_realism_config.json"
    pipeline_mode: str = "custom"
    lightweight_default: bool = False

    @classmethod
    def from_mapping(cls, config: dict[str, Any] | None) -> "SchedulerConfig":
        data = dict(config or {})
        if "symbols" in data:
            data["symbols"] = _normalize_list(data["symbols"])
        if "factors" in data:
            data["factors"] = [item.lower() for item in _normalize_list(data["factors"])]
        return cls(**{key: value for key, value in data.items() if key in cls.__dataclass_fields__})

    @classmethod
    def from_file(cls, path: str | Path | None) -> "SchedulerConfig":
        if path is None:
            return cls()
        config_path = Path(path)
        if not config_path.exists():
            return cls()
        try:
            payload = json.loads(config_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"research scheduler config is not valid JSON: {config_path}") from exc
        if not isinstance(payload, dict):
            raise ValueError("research scheduler config must contain a JSON object")
        return cls.from_mapping(payload)

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_data_refresh": self.run_data_refresh,
            "run_data_coverage": self.run_data_coverage,
            "run_fundamental_coverage": self.run_fundamental_coverage,
            "run_factor_eval": self.run_factor_eval,
            "run_factor_store_update": self.run_factor_store_update,
            "run_regime_detection": self.run_regime_detection,
            "run_trade_sim": self.run_trade_sim,
            "run_visualization": self.run_visualization,
            "run_agent_export": self.run_agent_export,
            "symbols": self.symbols,
            "factors": self.factors,
            "forward_days": self.forward_days,
            "data_start_date": self.data_start_date,
            "data_end_date": self.data_end_date,
            "trade_sim_start": self.trade_sim_start,
            "trade_sim_end": self.trade_sim_end,
            "trade_sim_initial_cash": self.trade_sim_initial_cash,
            "trade_sim_rebalance_frequency": self.trade_sim_rebalance_frequency,
            "trade_sim_portfolio_method": self.trade_sim_portfolio_method,
            "alpha_config_path": self.alpha_config_path,
            "cost_config_path": self.cost_config_path,
            "market_realism_config_path": self.market_realism_config_path,
            "pipeline_mode": self.pipeline_mode,
            "lightweight_default": self.lightweight_default,
        }


def _normalize_list(value: Any) -> list[str]:
    if isinstance(value, str):
        raw = value.replace(",", " ").split()
    elif isinstance(value, list | tuple | set):
        raw = list(value)
    else:
        raw = []
    output = []
    seen = set()
    for item in raw:
        text = str(item).strip().upper()
        if text and text not in seen:
            output.append(text)
            seen.add(text)
    return output
