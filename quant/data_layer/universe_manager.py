"""Universe selection and normalization."""

from __future__ import annotations

from dataclasses import dataclass

from quant.config import DEFAULT_SYMBOLS
from quant.data_layer.symbol_metadata import SymbolMetadata, SymbolMetadataStore
from quant.data_providers import DataProvider


ETF_UNIVERSE = ("SPY", "QQQ", "DIA", "IWM", "TLT", "GLD", "XLK", "XLF", "XLV", "XLE")
LARGE_CAP_UNIVERSE = (
    "AAPL",
    "MSFT",
    "NVDA",
    "AMZN",
    "GOOGL",
    "META",
    "TSLA",
    "JPM",
    "V",
    "MA",
    "UNH",
    "JNJ",
    "LLY",
    "XOM",
    "CVX",
    "PG",
    "COST",
    "HD",
    "WMT",
    "AMD",
)
DEFAULT_RESEARCH_UNIVERSE = tuple(dict.fromkeys((*DEFAULT_SYMBOLS, "AMZN", "JPM", "V", "UNH", "XOM", "XLK", "XLF", "XLV")))


@dataclass(frozen=True)
class UniverseResult:
    universe_type: str
    selected_symbols: list[str]
    excluded_symbols: list[str]
    exclusion_reasons: dict[str, str]


class UniverseManager:
    """Build deterministic research universes from static metadata."""

    def __init__(self, metadata_store: SymbolMetadataStore, data_provider: DataProvider | None = None) -> None:
        self.metadata_store = metadata_store
        self.data_provider = data_provider

    def list_universes(self) -> dict[str, list[str]]:
        return {
            "default_universe": list(DEFAULT_RESEARCH_UNIVERSE),
            "etf_universe": list(ETF_UNIVERSE),
            "large_cap_universe": list(LARGE_CAP_UNIVERSE),
            "custom_universe": [],
            "sector_universe": sorted({row["sector"] for row in self.metadata_store.list_all()}),
        }

    def build_universe(
        self,
        symbols: str | list[str] | None = None,
        sector: str | None = None,
        universe: str | None = None,
        max_symbols: int | None = None,
    ) -> UniverseResult:
        universe_key = (universe or "default_universe").strip().lower()
        requested = self._requested_symbols(symbols=symbols, sector=sector, universe_key=universe_key)
        selected: list[str] = []
        excluded: list[str] = []
        reasons: dict[str, str] = {}
        seen = set()

        for symbol in requested:
            ticker = symbol.upper().strip()
            if not ticker or ticker in seen:
                continue
            seen.add(ticker)
            metadata = self._metadata_for(ticker)
            if not metadata:
                excluded.append(ticker)
                reasons[ticker] = "missing metadata"
                continue
            if max_symbols is not None and len(selected) >= max_symbols:
                excluded.append(ticker)
                reasons[ticker] = "max_symbols limit"
                continue
            selected.append(ticker)

        return UniverseResult(
            universe_type="sector_universe" if sector else universe_key,
            selected_symbols=selected,
            excluded_symbols=excluded,
            exclusion_reasons=reasons,
        )

    def _requested_symbols(
        self,
        symbols: str | list[str] | None,
        sector: str | None,
        universe_key: str,
    ) -> list[str]:
        if symbols:
            if isinstance(symbols, str):
                return [symbol.strip() for symbol in symbols.replace(",", " ").split()]
            return [symbol.strip() for symbol in symbols]
        if sector:
            return [row["symbol"] for row in self.metadata_store.list_by_sector(sector)]
        if universe_key in {"etf", "etf_universe"}:
            return list(ETF_UNIVERSE)
        if universe_key in {"large_cap", "large_cap_universe"}:
            return list(LARGE_CAP_UNIVERSE)
        if universe_key in {"default", "default_universe"}:
            return list(DEFAULT_RESEARCH_UNIVERSE)
        if universe_key in {"all", "metadata"}:
            return [row["symbol"] for row in self.metadata_store.list_all()]
        return list(DEFAULT_RESEARCH_UNIVERSE)

    def _metadata_for(self, symbol: str) -> dict | None:
        metadata = self.metadata_store.get(symbol)
        if metadata or not self.data_provider:
            return metadata
        provider_metadata = self.data_provider.get_symbol_metadata(symbol)
        if not provider_metadata:
            return None
        ticker = provider_metadata.get("symbol", symbol).upper().strip()
        row = SymbolMetadata(
            symbol=ticker,
            name=provider_metadata.get("name", ticker),
            asset_type=provider_metadata.get("asset_type", "Equity"),
            sector=provider_metadata.get("sector", "Unknown"),
            industry=provider_metadata.get("industry", "Unknown"),
            currency=provider_metadata.get("currency", "USD"),
            exchange=provider_metadata.get("exchange", "UNKNOWN"),
        )
        self.metadata_store.upsert_many([row])
        return self.metadata_store.get(symbol)
