"""Declarative data provider specifications."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from quant.data.providers.base import DataProvider


@dataclass(frozen=True)
class ProviderSpec:
    name: str
    factory: Callable[[], DataProvider]

    def create(self) -> DataProvider:
        provider = self.factory()
        if provider.name.lower().strip() != self.name.lower().strip():
            raise ValueError(f"provider spec name does not match provider instance: {self.name} != {provider.name}")
        return provider
