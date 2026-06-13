"""Read factor history from the persistent factor store."""

from __future__ import annotations


class FactorHistory:
    """Small query facade for factor history commands."""

    def __init__(self, factor_store) -> None:
        self.factor_store = factor_store

    def history(self, factor: str | None = None, limit: int = 20) -> dict:
        return self.factor_store.factor_history(factor=factor, limit=limit)

    def summary(self) -> dict:
        return self.factor_store.summary()

    def rank(self, limit: int = 10) -> dict:
        return self.factor_store.rank_factors(limit=limit)
