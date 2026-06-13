"""Portfolio risk calculation engine."""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from pathlib import Path

from quant.engines.portfolio.rebalance_engine import RebalanceEngine
from quant.engines.risk.config import DEFAULT_INDUSTRY_MAP
from quant.reports.report_io import generate_report_path, write_json_report
from quant.storage.portfolio_store import DEFAULT_ACCOUNT_NAME, SQLitePortfolioStore


@dataclass(frozen=True)
class HoldingRisk:
    symbol: str
    industry: str
    value: float
    weight_pct: float


@dataclass(frozen=True)
class IndustryRisk:
    industry: str
    value: float
    weight_pct: float


@dataclass(frozen=True)
class RiskReport:
    total_assets: float
    cash_value: float
    cash_weight_pct: float
    single_stock_concentration_pct: float
    industry_concentration_pct: float
    top_5_holdings_pct: float
    risk_score: float
    holdings: list[HoldingRisk]
    industries: list[IndustryRisk]
    warnings: list[str]
    report_path: str

    def to_report(self) -> dict:
        return {
            "total_assets": self.total_assets,
            "cash_value": self.cash_value,
            "cash_weight_pct": self.cash_weight_pct,
            "single_stock_concentration_pct": self.single_stock_concentration_pct,
            "industry_concentration_pct": self.industry_concentration_pct,
            "top_5_holdings_pct": self.top_5_holdings_pct,
            "risk_score": self.risk_score,
            "holdings": [asdict(holding) for holding in self.holdings],
            "industries": [asdict(industry) for industry in self.industries],
            "warnings": self.warnings,
        }


class RiskEngine:
    """Calculate portfolio risk from simulated portfolio state."""

    def __init__(
        self,
        store: SQLitePortfolioStore,
        account_name: str = DEFAULT_ACCOUNT_NAME,
        report_dir: str | Path = "reports",
        industry_map: dict[str, str] | None = None,
    ) -> None:
        self.store = store
        self.account_name = account_name
        self.report_dir = Path(report_dir)
        self.industry_map = industry_map or DEFAULT_INDUSTRY_MAP
        self.rebalance_engine = RebalanceEngine(store, account_name=account_name, report_dir=report_dir)

    def analyze(self) -> RiskReport:
        allocation = self.rebalance_engine.allocation()
        holdings = []
        industry_values: dict[str, float] = {}
        warnings = []

        for item in allocation.items:
            if item.symbol == "cash":
                continue
            industry = self.industry_map.get(item.symbol, "Unknown")
            if industry == "Unknown":
                warnings.append(f"industry is unknown for {item.symbol}")
            holdings.append(
                HoldingRisk(
                    symbol=item.symbol,
                    industry=industry,
                    value=item.current_value,
                    weight_pct=item.current_weight * 100.0,
                )
            )
            industry_values[industry] = industry_values.get(industry, 0.0) + item.current_value

        holdings = sorted(holdings, key=lambda holding: holding.value, reverse=True)
        industries = sorted(
            [
                IndustryRisk(
                    industry=industry,
                    value=value,
                    weight_pct=self._pct(value, allocation.total_assets),
                )
                for industry, value in industry_values.items()
            ],
            key=lambda industry: industry.value,
            reverse=True,
        )

        cash_weight_pct = self._pct(allocation.cash, allocation.total_assets)
        single_stock_concentration_pct = max((holding.weight_pct for holding in holdings), default=0.0)
        industry_concentration_pct = max((industry.weight_pct for industry in industries), default=0.0)
        top_5_holdings_pct = sum(holding.weight_pct for holding in holdings[:5])
        risk_score = self._risk_score(
            single_stock_concentration_pct=single_stock_concentration_pct,
            industry_concentration_pct=industry_concentration_pct,
            cash_weight_pct=cash_weight_pct,
            top_5_holdings_pct=top_5_holdings_pct,
        )

        report = RiskReport(
            total_assets=allocation.total_assets,
            cash_value=allocation.cash,
            cash_weight_pct=cash_weight_pct,
            single_stock_concentration_pct=single_stock_concentration_pct,
            industry_concentration_pct=industry_concentration_pct,
            top_5_holdings_pct=top_5_holdings_pct,
            risk_score=risk_score,
            holdings=holdings,
            industries=industries,
            warnings=warnings,
            report_path="",
        )
        report_path = self._write_report(report)

        return replace(report, report_path=str(report_path))

    @staticmethod
    def _pct(value: float, total: float) -> float:
        if total <= 0:
            return 0.0
        return (value / total) * 100.0

    @staticmethod
    def _risk_score(
        single_stock_concentration_pct: float,
        industry_concentration_pct: float,
        cash_weight_pct: float,
        top_5_holdings_pct: float,
    ) -> float:
        single_stock_risk = min(single_stock_concentration_pct / 50.0, 1.0) * 35.0
        industry_risk = min(industry_concentration_pct / 75.0, 1.0) * 30.0
        top_5_risk = min(top_5_holdings_pct / 100.0, 1.0) * 20.0

        if cash_weight_pct < 5.0:
            cash_risk = ((5.0 - cash_weight_pct) / 5.0) * 15.0
        elif cash_weight_pct > 50.0:
            cash_risk = min((cash_weight_pct - 50.0) / 50.0, 1.0) * 15.0
        else:
            cash_risk = 0.0

        return round(min(single_stock_risk + industry_risk + top_5_risk + cash_risk, 100.0), 2)

    def _write_report(self, report: RiskReport) -> Path:
        return write_json_report(
            generate_report_path(self.report_dir, "risk"),
            report.to_report(),
        )
