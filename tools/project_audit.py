"""Lightweight project hygiene checks for maintenance releases."""

from __future__ import annotations

import re
import subprocess
import sys
import tomllib
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
CURRENT_VERSION_DOCS = [
    ROOT / "README.md",
    ROOT / "docs" / "AI_DEVELOPMENT.md",
]
CURRENT_VERSION_PATTERN = re.compile(r"(?ms)^## Current Version\s*\n\s*`([^`]+)`")
STALE_VERSION_PATTERN = re.compile(r"\b[vV](?!0\.)\d+\.\d+")
GENERATED_PATHS = [
    "data/quant.db",
    "reports/example.json",
    "reports/research_validation_summary.md",
    "reports/performance_profile_summary.md",
    "reports/agent_summary.md",
    "reports/charts/example.png",
    "examples/portfolio_constructed_targets.json",
]
ALLOWED_EMPTY_PACKAGES = {
    Path("quant/interfaces/mcp_server"),
}
FORBIDDEN_SOURCE_PATHS = {
    "quant/adapters",
    "quant/agent_export",
    "quant/alpha",
    "quant/backtest",
    "quant/core_protocols",
    "quant/cost",
    "quant/data_layer",
    "quant/data_providers",
    "quant/execution",
    "quant/factor_backtest",
    "quant/factor_eval",
    "quant/factor_pipeline",
    "quant/factor_store",
    "quant/fundamental_data",
    "quant/fundamental_factors",
    "quant/interfaces/api",
    "quant/interfaces/cli_commands",
    "quant/market_realism",
    "quant/multi_factor",
    "quant/openclaw",
    "quant/optimizer",
    "quant/portfolio",
    "quant/portfolio_construction",
    "quant/rebalance",
    "quant/regime_detection",
    "quant/risk",
    "quant/strategy_eval",
    "quant/strategy_gates",
    "quant/trading_simulation",
    "quant/utils/module_alias.py",
    "quant/visualization",
    "quant/walk_forward",
}
FORBIDDEN_IMPORT_PATTERNS = (
    "quant.core_protocols",
    "quant.factor_store",
    "quant.fundamental_factors",
    "quant.interfaces.cli_commands",
    "quant.utils.module_alias",
)
MAX_MODULE_LINES = 800
ALLOWED_OVERSIZED_MODULES = {
    "quant/engines/alpha/alpha_engine.py",
    "quant/engines/factor_backtest/factor_backtest.py",
    "quant/engines/walk_forward/walk_forward.py",
    "quant/engines/strategy_eval/strategy_evaluation.py",
    "quant/research_validation/research_validation.py",
    "quant/factors/store/factor_store.py",
}
REQUIRED_MODULE_DOCS = {
    "docs/AGENT_EXPORT.md",
    "docs/BACKTEST.md",
    "docs/DATA_LAYER.md",
    "docs/DATA_PROVIDERS.md",
    "docs/FACTOR_BACKTEST.md",
    "docs/FACTOR_ACCELERATION.md",
    "docs/FACTOR_CACHE.md",
    "docs/FACTOR_EVALUATION.md",
    "docs/FACTOR_LIBRARY.md",
    "docs/FACTOR_STORE.md",
    "docs/FACTOR_PIPELINE.md",
    "docs/FUNDAMENTAL_DATA.md",
    "docs/FUNDAMENTAL_FACTORS.md",
    "docs/MULTI_FACTOR.md",
    "docs/MARKET_REALISM.md",
    "docs/MCP_SERVER.md",
    "docs/PACKAGING.md",
    "docs/PERFORMANCE.md",
    "docs/PORTFOLIO_CONSTRUCTION.md",
    "docs/PROTOCOLS.md",
    "docs/REGIME_DETECTION.md",
    "docs/RESEARCH_VALIDATION.md",
    "docs/SCHEDULER.md",
    "docs/STRATEGY_DSL.md",
    "docs/STRATEGY_GATES.md",
    "docs/STRATEGY_EVALUATION.md",
    "docs/TRADING_SIMULATION.md",
    "docs/VISUALIZATION.md",
    "docs/WALK_FORWARD.md",
}
REQUIRED_PACKAGING_FILES = {
    "LICENSE",
    "pyproject.toml",
    ".github/workflows/ci.yml",
    ".github/workflows/project_audit.yml",
    ".github/ISSUE_TEMPLATE/bug_report.md",
    ".github/ISSUE_TEMPLATE/feature_request.md",
    ".github/PULL_REQUEST_TEMPLATE.md",
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


def project_version() -> str:
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    return str(data["project"]["version"])


def current_version_tag(path: Path) -> str | None:
    match = CURRENT_VERSION_PATTERN.search(path.read_text(encoding="utf-8"))
    return match.group(1).strip() if match else None


def stale_version_references(paths: list[Path] | None = None) -> dict[str, list[str]]:
    docs = paths or CURRENT_VERSION_DOCS
    references: dict[str, list[str]] = {}
    expected_prefix = f"v{project_version()}"
    tags: dict[str, str] = {}
    for path in docs:
        matches: list[str] = []
        tag = current_version_tag(path)
        if tag is not None:
            tags[str(path.relative_to(ROOT) if path.is_relative_to(ROOT) else path)] = tag
            if not tag.startswith(expected_prefix):
                matches.append(f"Current Version `{tag}` does not start with `{expected_prefix}`")
        elif path.name in {"README.md", "AI_DEVELOPMENT.md"}:
            matches.append("missing ## Current Version block")
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if STALE_VERSION_PATTERN.search(line):
                matches.append(f"{line_number}: {line.strip()}")
        if matches:
            key = str(path.relative_to(ROOT) if path.is_relative_to(ROOT) else path)
            references[key] = matches
    if tags:
        expected_tag = next(iter(tags.values()))
        for path, tag in tags.items():
            if tag != expected_tag:
                references.setdefault(path, []).append(
                    f"Current Version `{tag}` does not match `{expected_tag}`"
                )
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
        init_text = package_init.read_text(encoding="utf-8")
        has_package_logic = any(token in init_text for token in ("__all__", "import ", "from "))
        if (
            len(files) == 1
            and files[0].name == "__init__.py"
            and not dirs
            and not has_package_logic
            and relative not in ALLOWED_EMPTY_PACKAGES
        ):
            empty.append(str(relative).replace("\\", "/"))
    return sorted(empty)


def missing_module_docs() -> list[str]:
    return sorted(path for path in REQUIRED_MODULE_DOCS if not (ROOT / path).exists())


def missing_packaging_files() -> list[str]:
    return sorted(path for path in REQUIRED_PACKAGING_FILES if not (ROOT / path).exists())


def forbidden_source_paths() -> list[str]:
    return sorted(path for path in FORBIDDEN_SOURCE_PATHS if (ROOT / path).exists())


def forbidden_imports() -> list[str]:
    offenders = []
    for path in (ROOT / "quant").rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        text = path.read_text(encoding="utf-8")
        matches = [pattern for pattern in FORBIDDEN_IMPORT_PATTERNS if pattern in text]
        if matches:
            offenders.append(f"{path.relative_to(ROOT).as_posix()}: {matches}")
    return sorted(offenders)


def oversized_modules(max_lines: int = MAX_MODULE_LINES) -> list[str]:
    oversized = []
    for path in (ROOT / "quant").rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        relative = path.relative_to(ROOT).as_posix()
        if relative in ALLOWED_OVERSIZED_MODULES:
            continue
        lines = len(path.read_text(encoding="utf-8").splitlines())
        if lines > max_lines:
            oversized.append(f"{relative}: {lines} lines")
    return sorted(oversized)


def run_audit() -> list[AuditResult]:
    missing_commands = missing_documented_commands()
    stale_refs = stale_version_references()
    ignored = ignored_generated_paths()
    empty_packages = empty_package_dirs()
    missing_docs = missing_module_docs()
    missing_packaging = missing_packaging_files()
    forbidden_paths = forbidden_source_paths()
    forbidden_import_matches = forbidden_imports()
    oversized = oversized_modules()
    return [
        AuditResult("cli_docs", not missing_commands, missing_commands),
        AuditResult("stale_versions", not stale_refs, [f"{path}: {items}" for path, items in stale_refs.items()]),
        AuditResult("ignored_generated_paths", all(ignored.values()), [path for path, ok in ignored.items() if not ok]),
        AuditResult("empty_package_dirs", not empty_packages, empty_packages),
        AuditResult("module_docs", not missing_docs, missing_docs),
        AuditResult("packaging_files", not missing_packaging, missing_packaging),
        AuditResult("forbidden_source_paths", not forbidden_paths, forbidden_paths),
        AuditResult("forbidden_imports", not forbidden_import_matches, forbidden_import_matches),
        AuditResult("oversized_modules", not oversized, oversized),
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
