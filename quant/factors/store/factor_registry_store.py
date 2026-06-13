"""Persist factor registry metadata into SQLite."""

from __future__ import annotations

from quant.factors.price.factor_registry import FactorRegistry


class FactorRegistryStore:
    """Synchronize registered factor definitions with the factor store."""

    def __init__(self, factor_store) -> None:
        self.factor_store = factor_store

    def sync(self, registry: FactorRegistry | None = None) -> int:
        factor_registry = registry or FactorRegistry()
        count = 0
        for definition in factor_registry.list_factors():
            self.factor_store.upsert_factor_definition(
                factor_name=definition.name,
                category=definition.category,
                description=definition.description,
                higher_is_better=definition.higher_is_better,
                fundamental_required=definition.fundamental_data_required,
            )
            self.factor_store.upsert_factor_version(
                factor_name=definition.name,
                version="v1",
                description=definition.description,
                change_reason="registry sync",
            )
            count += 1
        return count
