from __future__ import annotations

import importlib

import pytest

from quant.cli import main
from quant.data_providers import ProviderRegistry
from quant.data_providers.yfinance_provider import YFinanceProvider


def test_yfinance_provider_module_imports_without_loading_yfinance() -> None:
    module = importlib.import_module("quant.data_providers.yfinance_provider")

    assert module.YFinanceProvider.name == "yfinance"


def test_yfinance_missing_reports_not_installed(monkeypatch: pytest.MonkeyPatch) -> None:
    import quant.data_providers.yfinance_provider as yfp

    monkeypatch.setattr(yfp, "yf", None)

    def fake_import(name: str):
        if name == "yfinance":
            raise ModuleNotFoundError("No module named 'yfinance'")
        return importlib.import_module(name)

    monkeypatch.setattr(yfp.importlib, "import_module", fake_import)

    health = YFinanceProvider().health_check()

    assert health.status == "NOT_INSTALLED"
    assert health.healthy is False
    assert "yfinance" in (health.error or "")


def test_provider_registry_and_cli_start_without_yfinance(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    import quant.data_providers.yfinance_provider as yfp

    monkeypatch.setattr(yfp, "yf", None)

    def fake_import(name: str):
        if name == "yfinance":
            raise ModuleNotFoundError("No module named 'yfinance'")
        return importlib.import_module(name)

    monkeypatch.setattr(yfp.importlib, "import_module", fake_import)

    registry = ProviderRegistry()
    assert registry.default_name == "yfinance"
    assert registry.resolve("mock").health_check().healthy is True
    assert main(["provider-list"]) == 0
    assert "yfinance" in capsys.readouterr().out
    assert main(["factor-list"]) == 0
    assert "momentum_60d" in capsys.readouterr().out
