"""Report-date-aware fundamental factor library."""


def fundamental_factor_definitions():
    from quant.factors.fundamental.factor_registry_extension import fundamental_factor_definitions as _definitions

    return _definitions()


__all__ = ["fundamental_factor_definitions"]
