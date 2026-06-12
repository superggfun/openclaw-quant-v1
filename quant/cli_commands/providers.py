"""Data provider CLI commands."""

from __future__ import annotations


def register_parser(subparsers) -> None:
    subparsers.add_parser("provider-list", help="List registered data providers.")
    subparsers.add_parser("provider-health", help="Run health checks for registered data providers.")
    info = subparsers.add_parser("provider-info", help="Show provider details.")
    info.add_argument("provider", help="Provider name, for example yfinance, csv, or mock.")


def handle(args, context) -> int:
    if args.command == "provider-list":
        print("Data Providers")
        print("provider         status         default  description")
        for item in context.provider_registry.list_providers():
            default = "yes" if item.default else "no"
            print(f"{item.name:<16} {item.status:<14} {default:<7} {item.description}")
        return 0

    if args.command == "provider-health":
        print("Provider Health")
        for item in context.provider_registry.list_providers():
            provider = context.provider_registry.resolve(item.name)
            health = provider.health_check()
            print(f"{health.provider}: status={health.status} healthy={health.healthy}")
            if health.warning:
                print(f"  warning: {health.warning}")
            if health.error:
                print(f"  error: {health.error}")
            for message in health.messages:
                print(f"  message: {message}")
        return 0

    if args.command == "provider-info":
        provider = context.provider_registry.resolve(args.provider)
        health = provider.health_check()
        print("Provider Info")
        print(f"provider: {provider.name}")
        print(f"description: {provider.description}")
        print(f"status: {getattr(provider, 'status', 'available')}")
        print(f"default: {provider.name == context.provider_registry.default_name}")
        print(f"health_status: {health.status}")
        print(f"healthy: {health.healthy}")
        if health.warning:
            print(f"warning: {health.warning}")
        if health.error:
            print(f"error: {health.error}")
        for message in health.messages:
            print(f"message: {message}")
        return 0

    raise ValueError(f"Unknown provider command: {args.command}")
