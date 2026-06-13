from __future__ import annotations

from pathlib import Path

from quant.data.layer.symbol_metadata import SymbolMetadata, SymbolMetadataStore
from quant.config import DEFAULT_SYMBOLS


def test_metadata_bootstrap_and_lookup(tmp_path: Path) -> None:
    store = SymbolMetadataStore(tmp_path / "quant.db")

    spy = store.get("SPY")

    assert spy is not None
    assert spy["symbol"] == "SPY"
    assert spy["asset_type"] == "ETF"
    assert spy["sector"] == "ETF"


def test_metadata_upsert_custom_symbol(tmp_path: Path) -> None:
    store = SymbolMetadataStore(tmp_path / "quant.db")
    store.upsert_many(
        [
            SymbolMetadata(
                symbol="TEST",
                name="Test Corp",
                asset_type="Equity",
                sector="Technology",
                industry="Software",
                exchange="NYSE",
            )
        ]
    )

    row = store.get("test")

    assert row is not None
    assert row["symbol"] == "TEST"
    assert row["name"] == "Test Corp"
    assert row["currency"] == "USD"


def test_metadata_sector_filter(tmp_path: Path) -> None:
    store = SymbolMetadataStore(tmp_path / "quant.db")

    rows = store.list_by_sector("Technology")

    assert "AAPL" in {row["symbol"] for row in rows}
    assert all(row["sector"] == "Technology" for row in rows)


def test_default_symbols_have_sector_and_industry_metadata(tmp_path: Path) -> None:
    store = SymbolMetadataStore(tmp_path / "quant.db")

    for symbol in DEFAULT_SYMBOLS:
        row = store.get(symbol)
        assert row is not None
        assert row["sector"]
        assert row["industry"]
