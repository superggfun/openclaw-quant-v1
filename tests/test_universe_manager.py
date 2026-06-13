from __future__ import annotations

from pathlib import Path

from quant.data.layer.symbol_metadata import SymbolMetadataStore
from quant.data.layer.universe_manager import UniverseManager


def manager(tmp_path: Path) -> UniverseManager:
    return UniverseManager(SymbolMetadataStore(tmp_path / "quant.db"))


def test_universe_list_contains_supported_universes(tmp_path: Path) -> None:
    universes = manager(tmp_path).list_universes()

    assert "default_universe" in universes
    assert "etf_universe" in universes
    assert "large_cap_universe" in universes
    assert "Technology" in universes["sector_universe"]


def test_custom_universe_excludes_missing_metadata(tmp_path: Path) -> None:
    result = manager(tmp_path).build_universe(symbols="SPY, QQQ, UNKNOWN")

    assert result.selected_symbols == ["SPY", "QQQ"]
    assert result.excluded_symbols == ["UNKNOWN"]
    assert result.exclusion_reasons["UNKNOWN"] == "missing metadata"


def test_sector_universe_builds_from_metadata(tmp_path: Path) -> None:
    result = manager(tmp_path).build_universe(sector="Technology", max_symbols=3)

    assert len(result.selected_symbols) == 3
    assert result.universe_type == "sector_universe"
    assert all(symbol in {"AAPL", "AMD", "MSFT", "NVDA"} for symbol in result.selected_symbols)


def test_etf_and_large_cap_universes_work(tmp_path: Path) -> None:
    universe_manager = manager(tmp_path)

    etfs = universe_manager.build_universe(universe="etf_universe", max_symbols=5)
    large_caps = universe_manager.build_universe(universe="large_cap_universe", max_symbols=5)

    assert etfs.selected_symbols == ["SPY", "QQQ", "DIA", "IWM", "TLT"]
    assert large_caps.selected_symbols == ["AAPL", "MSFT", "NVDA", "AMZN", "GOOGL"]


def test_max_symbols_exclusion(tmp_path: Path) -> None:
    result = manager(tmp_path).build_universe(universe="etf_universe", max_symbols=2)

    assert result.selected_symbols == ["SPY", "QQQ"]
    assert result.excluded_symbols
    assert all(reason == "max_symbols limit" for reason in result.exclusion_reasons.values())
