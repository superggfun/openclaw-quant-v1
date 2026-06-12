from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from quant.data_layer.data_quality import DataRefreshManager
from quant.data_layer.symbol_metadata import SymbolMetadataStore
from quant.data_layer.universe_manager import UniverseManager
from quant.data_providers import CSVProvider, MockProvider, ProviderRegistry
from quant.data_providers.yfinance_provider import YFinanceProvider
from quant.cli import main
from quant.services.price_service import PriceService
from quant.storage.sqlite_store import SQLitePriceStore


def test_registry_lists_default_and_placeholders() -> None:
    registry = ProviderRegistry()
    providers = {item.name: item for item in registry.list_providers()}

    assert registry.default_name == "yfinance"
    assert providers["yfinance"].default is True
    assert providers["csv"].status == "available"
    assert providers["mock"].status == "available"
    assert providers["akshare"].status == "not installed"
    assert providers["tushare"].status == "not installed"
    assert providers["alpha_vantage"].status == "not installed"
    assert providers["polygon"].status == "not installed"


def test_registry_resolves_and_rejects_unknown() -> None:
    registry = ProviderRegistry()

    assert registry.resolve("mock").name == "mock"
    assert registry.default_provider().name == "yfinance"
    with pytest.raises(ValueError, match="unknown data provider"):
        registry.resolve("missing")


def test_mock_provider_is_deterministic() -> None:
    provider = MockProvider()

    first = provider.get_price_history("SPY")
    second = provider.get_price_history("SPY")

    assert not first.empty
    assert first.equals(second)
    assert provider.get_latest_price("SPY") == float(first["close"].iloc[-1])
    assert provider.health_check().healthy is True


def test_csv_provider_reads_combined_csv(tmp_path: Path) -> None:
    csv_path = tmp_path / "prices.csv"
    pd.DataFrame(
        [
            {"symbol": "SPY", "date": "2024-01-02", "open": 100, "high": 101, "low": 99, "close": 100, "adj_close": 100, "volume": 1000},
            {"symbol": "QQQ", "date": "2024-01-02", "open": 200, "high": 201, "low": 199, "close": 200, "adj_close": 200, "volume": 2000},
        ]
    ).to_csv(csv_path, index=False)

    history = CSVProvider(csv_path=csv_path).get_price_history("SPY")

    assert list(history["symbol"]) == ["SPY"]
    assert float(history.iloc[0]["close"]) == 100.0


def test_csv_provider_rejects_malformed_csv(tmp_path: Path) -> None:
    csv_path = tmp_path / "bad.csv"
    pd.DataFrame([{"symbol": "SPY", "date": "2024-01-02", "close": 100}]).to_csv(csv_path, index=False)

    with pytest.raises(ValueError, match="price frame missing required columns"):
        CSVProvider(csv_path=csv_path).get_price_history("SPY")


def test_csv_provider_health_warns_when_path_missing(tmp_path: Path) -> None:
    health = CSVProvider(csv_dir=tmp_path / "missing").health_check()

    assert health.status == "WARNING"
    assert health.healthy is False
    assert "no CSV path found" in health.warning


def test_placeholder_health_is_not_installed() -> None:
    provider = ProviderRegistry().resolve("polygon")
    health = provider.health_check()

    assert health.healthy is False
    assert health.status == "NOT_INSTALLED"


def test_yfinance_provider_uses_same_download_arguments_and_normalizes(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []

    def fake_download(*args, **kwargs):
        calls.append((args, kwargs))
        return pd.DataFrame(
            [
                {
                    "Open": 100.0,
                    "High": 101.0,
                    "Low": 99.0,
                    "Close": 100.5,
                    "Adj Close": 100.25,
                    "Volume": 1234,
                }
            ],
            index=pd.DatetimeIndex(["2024-01-02"], name="Date"),
        )

    monkeypatch.setattr("quant.data_providers.yfinance_provider.yf.download", fake_download)

    history = YFinanceProvider().get_price_history("spy", start="2024-01-01", end="2024-01-03")

    assert calls[0][0] == ("SPY",)
    assert calls[0][1]["interval"] == "1d"
    assert calls[0][1]["auto_adjust"] is False
    assert calls[0][1]["actions"] is False
    assert calls[0][1]["progress"] is False
    assert calls[0][1]["threads"] is False
    assert history.to_dict("records")[0] == {
        "symbol": "SPY",
        "date": "2024-01-02",
        "open": 100.0,
        "high": 101.0,
        "low": 99.0,
        "close": 100.5,
        "adj_close": 100.25,
        "volume": 1234,
    }


def test_price_service_uses_data_provider(tmp_path: Path) -> None:
    store = SQLitePriceStore(tmp_path / "quant.db")
    provider = MockProvider()
    service = PriceService(store, data_source=provider, default_symbols=("SPY",))

    result = service.update_prices(start="2024-01-01", end="2024-01-10")

    assert result["SPY"] > 0
    assert len(store.get_price_history("SPY")) > 0


def test_data_refresh_manager_uses_provider_without_duplicates(tmp_path: Path) -> None:
    store = SQLitePriceStore(tmp_path / "quant.db")
    manager = DataRefreshManager(store, MockProvider(), report_dir=tmp_path / "reports")

    first = manager.refresh(["SPY"], start_date="2024-01-01", end_date="2024-01-10")
    second = manager.refresh(["SPY"], start_date="2024-01-01", end_date="2024-01-10")

    assert first.per_symbol["SPY"]["inserted"] > 0
    assert second.per_symbol["SPY"]["updated"] == first.per_symbol["SPY"]["inserted"]
    assert len(store.get_price_history("SPY")) == first.per_symbol["SPY"]["inserted"]


def test_universe_manager_can_use_provider_metadata(tmp_path: Path) -> None:
    metadata_store = SymbolMetadataStore(tmp_path / "quant.db")
    manager = UniverseManager(metadata_store, MockProvider())

    result = manager.build_universe(symbols="NEW")

    assert result.selected_symbols == ["NEW"]
    assert metadata_store.get("NEW")["sector"] == "Mock"


def test_provider_info_cli_works_for_every_registered_provider(capsys: pytest.CaptureFixture[str]) -> None:
    for provider in [item.name for item in ProviderRegistry().list_providers()]:
        assert main(["provider-info", provider]) == 0
        output = capsys.readouterr().out
        assert f"provider: {provider}" in output
