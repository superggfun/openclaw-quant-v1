"""Provider registry for resolving market data providers."""

from __future__ import annotations

from dataclasses import dataclass

from quant.data.providers.base import DataProvider
from quant.data.providers.provider_discovery import discover_provider_specs


@dataclass(frozen=True)
class ProviderInfo:
    name: str
    status: str
    description: str
    default: bool = False


class ProviderRegistry:
    """Resolve available and future data providers by name."""

    def __init__(self, default_provider: str = "yfinance") -> None:
        self._providers: dict[str, DataProvider] = {}
        self._default_provider = default_provider
        for spec in discover_provider_specs():
            self.register(spec.create())

    def register(self, provider: DataProvider, *, make_default: bool = False) -> None:
        key = provider.name.lower().strip()
        if not key:
            raise ValueError("provider name must not be empty")
        self._providers[key] = provider
        if make_default:
            self._default_provider = key

    def resolve(self, name: str | None = None) -> DataProvider:
        key = (name or self._default_provider).lower().strip()
        try:
            return self._providers[key]
        except KeyError as exc:
            raise ValueError(f"unknown data provider: {name}") from exc

    def default_provider(self) -> DataProvider:
        return self.resolve(self._default_provider)

    def list_providers(self) -> list[ProviderInfo]:
        rows = []
        for name in sorted(self._providers):
            provider = self._providers[name]
            rows.append(
                ProviderInfo(
                    name=provider.name,
                    status=getattr(provider, "status", "available"),
                    description=provider.description,
                    default=name == self._default_provider,
                )
            )
        return rows

    @property
    def default_name(self) -> str:
        return self._default_provider


def create_default_registry() -> ProviderRegistry:
    return ProviderRegistry()
