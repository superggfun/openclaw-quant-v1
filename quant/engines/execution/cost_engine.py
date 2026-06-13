"""Transaction cost estimation engine."""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Iterable

from quant.engines.execution.slippage_model import SlippageModel
from quant.reports.report_io import generate_report_path, write_json_report


DEFAULT_COST_CONFIG = {
    "model": "combined",
    "fixed_fee": 1.0,
    "commission_rate": 0.001,
    "min_commission": 1.0,
    "slippage_bps": 5.0,
    "slippage_model": None,
    "market_impact_bps": 0.0,
    "liquidity_impact_rate": 0.0,
    "currency": "USD",
    "min_trade_notional": 50.0,
    "min_cost_efficiency_ratio": None,
}


@dataclass(frozen=True)
class TradeInput:
    symbol: str
    side: str
    shares: int
    price: float
    average_daily_volume: float | None = None
    volatility: float | None = None


@dataclass(frozen=True)
class TradeCostEstimate:
    symbol: str
    side: str
    shares: int
    price: float
    notional: float
    fixed_fee: float
    commission: float
    slippage_cost: float
    market_impact_cost: float
    liquidity_cost: float
    total_cost: float
    cost_ratio: float
    slippage_model: str
    adv_participation: float | None


@dataclass(frozen=True)
class CostReport:
    model: str
    currency: str
    config: dict
    trades: list[TradeCostEstimate]
    gross_trade_value: float
    total_commission: float
    total_slippage: float
    total_market_impact: float
    total_liquidity_cost: float
    total_cost: float
    total_cost_ratio: float
    warnings: list[str]
    report_path: str

    def to_report(self) -> dict:
        return {
            "model": self.model,
            "currency": self.currency,
            "config": self.config,
            "trades": [asdict(trade) for trade in self.trades],
            "gross_trade_value": self.gross_trade_value,
            "total_commission": self.total_commission,
            "total_slippage": self.total_slippage,
            "total_market_impact": self.total_market_impact,
            "total_liquidity_cost": self.total_liquidity_cost,
            "total_cost": self.total_cost,
            "total_cost_ratio": self.total_cost_ratio,
            "warnings": self.warnings,
        }


class CostEngine:
    """Estimate fixed, linear, or combined transaction costs."""

    def __init__(
        self,
        config: dict | None = None,
        report_dir: str | Path = "reports",
    ) -> None:
        self.config = self._normalize_config(config or {})
        self.report_dir = Path(report_dir)

    def estimate(self, trades: Iterable[TradeInput], write_report: bool = True) -> CostReport:
        trade_estimates = []
        warnings = []

        for trade in trades:
            if trade.shares <= 0:
                continue
            if trade.price <= 0:
                raise ValueError("trade price must be positive")

            notional = trade.shares * trade.price
            fixed_fee = self._fixed_fee()
            commission = self._commission(notional)
            adv_participation = self._adv_participation(trade)
            slippage_model = SlippageModel(self.config["slippage_model"])
            slippage_cost = slippage_model.estimate(
                notional=notional,
                shares=trade.shares,
                price=trade.price,
                average_daily_volume=trade.average_daily_volume,
                volatility=trade.volatility,
            )
            market_impact_cost = self._market_impact(notional, adv_participation)
            liquidity_cost = self._liquidity_cost(notional, adv_participation)
            total_cost = fixed_fee + commission + slippage_cost + market_impact_cost + liquidity_cost
            cost_ratio = total_cost / notional if notional else 0.0

            if notional < self.config["min_trade_notional"]:
                warnings.append(
                    f"{trade.symbol} {trade.side} notional {notional:.2f} "
                    f"is below min_trade_notional {self.config['min_trade_notional']:.2f}"
                )

            efficiency_ratio = self.config.get("min_cost_efficiency_ratio")
            if efficiency_ratio is not None and cost_ratio > efficiency_ratio:
                warnings.append(
                    f"{trade.symbol} {trade.side} cost_ratio {cost_ratio:.6f} "
                    f"exceeds min_cost_efficiency_ratio {efficiency_ratio:.6f}"
                )

            trade_estimates.append(
                TradeCostEstimate(
                    symbol=trade.symbol.upper(),
                    side=trade.side.upper(),
                    shares=int(trade.shares),
                    price=float(trade.price),
                    notional=notional,
                    fixed_fee=fixed_fee,
                    commission=commission,
                    slippage_cost=slippage_cost,
                    market_impact_cost=market_impact_cost,
                    liquidity_cost=liquidity_cost,
                    total_cost=total_cost,
                    cost_ratio=cost_ratio,
                    slippage_model=str(self.config["slippage_model"]["model"]),
                    adv_participation=adv_participation,
                )
            )

        gross_trade_value = sum(trade.notional for trade in trade_estimates)
        total_commission = sum(trade.fixed_fee + trade.commission for trade in trade_estimates)
        total_slippage = sum(trade.slippage_cost for trade in trade_estimates)
        total_market_impact = sum(trade.market_impact_cost for trade in trade_estimates)
        total_liquidity_cost = sum(trade.liquidity_cost for trade in trade_estimates)
        total_cost = sum(trade.total_cost for trade in trade_estimates)
        total_cost_ratio = total_cost / gross_trade_value if gross_trade_value else 0.0

        report = CostReport(
            model=self.config["model"],
            currency=self.config["currency"],
            config=self.config,
            trades=trade_estimates,
            gross_trade_value=gross_trade_value,
            total_commission=total_commission,
            total_slippage=total_slippage,
            total_market_impact=total_market_impact,
            total_liquidity_cost=total_liquidity_cost,
            total_cost=total_cost,
            total_cost_ratio=total_cost_ratio,
            warnings=warnings,
            report_path="",
        )
        report_path = self._write_report(report) if write_report else Path("")
        return replace(report, report_path=str(report_path))

    def _fixed_fee(self) -> float:
        if self.config["model"] in {"fixed", "combined"}:
            return self.config["fixed_fee"]
        return 0.0

    def _commission(self, notional: float) -> float:
        if self.config["model"] not in {"linear", "combined"}:
            return 0.0
        return max(notional * self.config["commission_rate"], self.config["min_commission"])

    def _market_impact(self, notional: float, adv_participation: float | None) -> float:
        if notional <= 0:
            return 0.0
        base = notional * self.config["market_impact_bps"] / 10000.0
        if adv_participation is None:
            return base
        return base * max(1.0, adv_participation)

    def _liquidity_cost(self, notional: float, adv_participation: float | None) -> float:
        if notional <= 0 or adv_participation is None:
            return 0.0
        return notional * self.config["liquidity_impact_rate"] * max(0.0, adv_participation)

    @staticmethod
    def _adv_participation(trade: TradeInput) -> float | None:
        if trade.average_daily_volume is None or trade.average_daily_volume <= 0:
            return None
        return max(float(trade.shares) / float(trade.average_daily_volume), 0.0)

    @staticmethod
    def _normalize_config(config: dict) -> dict:
        merged = dict(DEFAULT_COST_CONFIG)
        merged.update(config)
        merged["model"] = str(merged["model"]).lower()
        if merged["model"] not in {"fixed", "linear", "combined"}:
            raise ValueError("cost model must be one of: fixed, linear, combined")

        merged["fixed_fee"] = float(merged["fixed_fee"])
        merged["commission_rate"] = float(merged["commission_rate"])
        merged["min_commission"] = float(merged["min_commission"])
        merged["slippage_bps"] = float(merged["slippage_bps"])
        if merged.get("slippage_model") is None:
            merged["slippage_model"] = {"model": "bps", "bps": merged["slippage_bps"]}
        elif isinstance(merged["slippage_model"], str):
            merged["slippage_model"] = {"model": merged["slippage_model"], "bps": merged["slippage_bps"]}
        elif isinstance(merged["slippage_model"], dict):
            merged["slippage_model"] = dict(merged["slippage_model"])
            merged["slippage_model"].setdefault("bps", merged["slippage_bps"])
        else:
            raise ValueError("slippage_model must be a string or JSON object")
        SlippageModel(merged["slippage_model"])
        merged["market_impact_bps"] = float(merged["market_impact_bps"])
        merged["liquidity_impact_rate"] = float(merged["liquidity_impact_rate"])
        merged["currency"] = str(merged["currency"]).upper()
        merged["min_trade_notional"] = float(merged["min_trade_notional"])
        if merged.get("min_cost_efficiency_ratio") is not None:
            merged["min_cost_efficiency_ratio"] = float(merged["min_cost_efficiency_ratio"])

        for key in (
            "fixed_fee",
            "commission_rate",
            "min_commission",
            "slippage_bps",
            "market_impact_bps",
            "liquidity_impact_rate",
            "min_trade_notional",
        ):
            if merged[key] < 0:
                raise ValueError(f"{key} must be non-negative")
        return merged

    def _write_report(self, report: CostReport) -> Path:
        return write_json_report(
            generate_report_path(self.report_dir, "cost"),
            report.to_report(),
        )
