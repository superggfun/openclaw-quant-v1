"""Fundamental data schemas and aliases."""

from __future__ import annotations

from dataclasses import dataclass


COMMON_FIELDS = [
    "symbol",
    "fiscal_period_end",
    "report_date",
    "fiscal_year",
    "fiscal_quarter",
    "currency",
]

STATEMENT_FIELDS = {
    "income_statement": [
        *COMMON_FIELDS,
        "revenue",
        "gross_profit",
        "operating_income",
        "net_income",
        "eps_basic",
        "eps_diluted",
        "shares_outstanding_basic",
        "shares_outstanding_diluted",
    ],
    "balance_sheet": [
        *COMMON_FIELDS,
        "total_assets",
        "total_liabilities",
        "total_equity",
        "total_debt",
        "cash_and_equivalents",
        "current_assets",
        "current_liabilities",
        "inventory",
    ],
    "cash_flow": [
        *COMMON_FIELDS,
        "operating_cash_flow",
        "capital_expenditure",
        "free_cash_flow",
        "dividends_paid",
    ],
    "fundamental_metrics": [
        *COMMON_FIELDS,
        "market_cap",
        "enterprise_value",
        "book_value_per_share",
        "pe_ratio",
        "pb_ratio",
        "ps_ratio",
        "ev_to_ebitda",
        "roe",
        "roa",
        "gross_margin",
        "net_margin",
        "debt_to_equity",
        "current_ratio",
        "quick_ratio",
        "revenue_growth",
        "eps_growth",
        "free_cash_flow_yield",
    ],
}

NUMERIC_FIELDS = {
    field
    for fields in STATEMENT_FIELDS.values()
    for field in fields
    if field not in {"symbol", "fiscal_period_end", "report_date", "fiscal_quarter", "currency"}
}

DATE_FIELDS = {"fiscal_period_end", "report_date"}

STATEMENT_ALIASES = {
    "income": "income_statement",
    "income_statement": "income_statement",
    "balance": "balance_sheet",
    "balance_sheet": "balance_sheet",
    "cash": "cash_flow",
    "cash-flow": "cash_flow",
    "cash_flow": "cash_flow",
    "metrics": "fundamental_metrics",
    "fundamental_metrics": "fundamental_metrics",
}


@dataclass(frozen=True)
class FundamentalImportResult:
    inserted: int
    updated: int
    skipped: int
    errors: int
    warnings: list[str]
    report_path: str

    def to_dict(self) -> dict:
        return {
            "inserted": self.inserted,
            "updated": self.updated,
            "skipped": self.skipped,
            "errors": self.errors,
            "warnings": self.warnings,
            "report_path": self.report_path,
        }


def normalize_statement(statement: str | None) -> str | None:
    if statement is None:
        return None
    key = statement.strip().lower().replace(" ", "_")
    return STATEMENT_ALIASES.get(key)
