"""Command line interface for OpenClaw Quant."""

from __future__ import annotations

import argparse
import importlib
import pkgutil
import sys
from types import ModuleType
from pathlib import Path

import quant.cli_commands as cli_commands_package
from quant.cli_commands.common import create_context
from quant.config import DB_PATH


SKIPPED_COMMAND_MODULES = {"common"}


def discover_command_modules() -> list[ModuleType]:
    modules = []
    for module_info in pkgutil.iter_modules(cli_commands_package.__path__):
        if module_info.ispkg or module_info.name in SKIPPED_COMMAND_MODULES:
            continue
        module = importlib.import_module(f"{cli_commands_package.__name__}.{module_info.name}")
        if not hasattr(module, "register_parser") or not hasattr(module, "handle"):
            raise ValueError(f"CLI command module {module.__name__} must define register_parser() and handle()")
        modules.append(module)
    return sorted(modules, key=lambda module: module.__name__)


def register_command_modules(
    subparsers: argparse._SubParsersAction,
    modules: list[ModuleType],
) -> dict[str, object]:
    handlers: dict[str, object] = {}
    for module in modules:
        before = set(subparsers.choices)
        module.register_parser(subparsers)
        registered = sorted(set(subparsers.choices) - before)
        if not registered:
            raise ValueError(f"CLI command module {module.__name__} did not register any commands")
        for command in registered:
            if command in handlers:
                raise ValueError(f"duplicate CLI command registered: {command}")
            handlers[command] = module.handle
    return handlers


COMMAND_MODULES = discover_command_modules()
_DISCOVERY_PARSER = argparse.ArgumentParser(prog="openclaw-quant-discovery", add_help=False)
COMMAND_HANDLERS = register_command_modules(_DISCOVERY_PARSER.add_subparsers(dest="command"), COMMAND_MODULES)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="openclaw-quant")
    parser.add_argument(
        "--db-path",
        default=str(DB_PATH),
        help="SQLite database path. Defaults to data/quant.db.",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)
    register_command_modules(subparsers, COMMAND_MODULES)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    context = create_context(Path(args.db_path))
    handler = COMMAND_HANDLERS.get(args.command)
    if handler is None:
        raise ValueError(f"Unknown command: {args.command}")

    try:
        return handler(args, context)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
