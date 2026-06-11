"""Factor library CLI commands."""

from __future__ import annotations

from quant.factors.factor_registry import FactorRegistry


def register_parser(subparsers) -> None:
    subparsers.add_parser("factor-list", help="List available deterministic research factors.")


def handle(args, context) -> int:
    registry = FactorRegistry()
    print("factor_name category factor_type higher_is_better no_lookahead lookback_days required_inputs description")
    for definition in registry.list_factors():
        inputs = ",".join(definition.required_inputs)
        print(
            f"{definition.name:<24} "
            f"{definition.category:<15} "
            f"{definition.factor_type:<30} "
            f"{str(definition.higher_is_better).lower():<16} "
            f"{str(definition.no_lookahead).lower():<12} "
            f"{definition.lookback_days:<13} "
            f"{inputs:<15} "
            f"{definition.description}"
        )
    return 0
