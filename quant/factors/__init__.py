"""Reusable no-lookahead factor library."""


def __getattr__(name):
    if name == "FactorDefinition":
        from quant.factors.specs import FactorDefinition
        return FactorDefinition
    if name == "FactorRegistry":
        from quant.factors.price.factor_registry import FactorRegistry
        return FactorRegistry
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = ["FactorDefinition", "FactorRegistry"]
