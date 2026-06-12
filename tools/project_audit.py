"""Lightweight project hygiene checks for maintenance releases."""

from __future__ import annotations

import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quant.cli import COMMAND_HANDLERS
DOC_PATHS = [
    ROOT / "README.md",
    ROOT / "docs" / "CLI.md",
    ROOT / "docs" / "CLI_COMMANDS.md",
]
STALE_VERSION_PATTERN = re.compile(r"\b[vV]1\.\d+")
GENERATED_PATHS = [
    "data/quant.db",
    "reports/example.json",
    "reports/agent_summary.md",
    "reports/charts/example.png",
    "examples/portfolio_constructed_targets.json",
]
ALLOWED_EMPTY_PACKAGES = {
    Path("quant/openclaw"),
    Path("quant/portfolio"),
}
REQUIRED_MODULE_DOCS = {
    "docs/AGENT_EXPORT.md",
    "docs/BACKTEST.md",
    "docs/DATA_LAYER.md",
    "docs/DATA_PROVIDERS.md",
    "docs/FACTOR_BACKTEST.md",
    "docs/FACTOR_EVALUATION.md",
    "docs/FACTOR_LIBRARY.md",
    "docs/FACTOR_PIPELINE.md",
    "docs/FUNDAMENTAL_DATA.md",
    "docs/PORTFOLIO_CONSTRUCTION.md",
    "docs/STRATEGY_EVALUATION.md",
    "docs/TRADING_SIMULATION.md",
    "docs/VISUALIZATION.md",
    "docs/WALK_FORWARD.md",
}


@dataclass(frozen=True)
class AuditResult:
    name: str
    passed: bool
    details: list[str]


def registered_commands() -> set[str]:
    return set(COMMAND_HANDLERS)


def documented_commands(paths: list[Path] | None = None) -> set[str]:
    text = "\n".join(path.read_text(encoding="utf-8") for path in (paths or DOC_PATHS))
    return {command for command in registered_commands() if command in text}


def missing_documented_commands(paths: list[Path] | None = None) -> list[str]:
    return sorted(registered_commands() - documented_commands(paths))


def stale_version_references(paths: list[Path] | None = None) -> dict[str, list[str]]:
    docs = paths or sorted((ROOT / "docs").glob("*.md")) + [ROOT / "README.md"]
    references: dict[str, list[str]] = {}
    for path in docs:
        matches = []
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if STALE_VERSION_PATTERN.search(line):
                matches.append(f"{line_number}: {line.strip()}")
        if matches:
            references[str(path.relative_to(ROOT))] = matches
    return references


def ignored_generated_paths(paths: list[str] | None = None) -> dict[str, bool]:
    result = {}
    for path in paths or GENERATED_PATHS:
        completed = subprocess.run(
            ["git", "check-ignore", "-q", path],
            cwd=ROOT,
            check=False,
        )
        result[path] = completed.returncode == 0
    return result


def empty_package_dirs(root: Path | None = None) -> list[str]:
    base = root or ROOT
    empty = []
    for package_init in (base / "quant").rglob("__init__.py"):
        package_dir = package_init.parent
        files = [path for path in package_dir.iterdir() if path.is_file()]
        dirs = [path for path in package_dir.iterdir() if path.is_dir() and path.name != "__pycache__"]
        relative = package_dir.relative_to(base)
        if len(files) == 1 and files[0].name == "__init__.py" and not dirs and relative not in ALLOWED_EMPTY_PACKAGES:
            empty.append(str(relative).replace("\\", "/"))
    return sorted(empty)


def missing_module_docs() -> list[str]:
    return sorted(path for path in REQUIRED_MODULE_DOCS if not (ROOT / path).exists())


def run_audit() -> list[AuditResult]:
    missing_commands = missing_documented_commands()
    stale_refs = stale_version_references()
    ignored = ignored_generated_paths()
    empty_packages = empty_package_dirs()
    missing_docs = missing_module_docs()
    return [
        AuditResult("cli_docs", not missing_commands, missing_commands),
        AuditResult("stale_versions", not stale_refs, [f"{path}: {items}" for path, items in stale_refs.items()]),
        AuditResult("ignored_generated_paths", all(ignored.values()), [path for path, ok in ignored.items() if not ok]),
        AuditResult("empty_package_dirs", not empty_packages, empty_packages),
        AuditResult("module_docs", not missing_docs, missing_docs),
    ]


def main() -> int:
    results = run_audit()
    for result in results:
        status = "PASS" if result.passed else "FAIL"
        print(f"{status} {result.name}")
        for detail in result.details:
            print(f"  - {detail}")
    return 0 if all(result.passed for result in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
