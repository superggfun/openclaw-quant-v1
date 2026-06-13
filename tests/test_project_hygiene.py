from __future__ import annotations

from pathlib import Path

from quant.cli import COMMAND_HANDLERS, build_parser
from tools.project_audit import (
    empty_package_dirs,
    ignored_generated_paths,
    missing_documented_commands,
    missing_module_docs,
    missing_packaging_files,
    stale_version_references,
)


def test_all_cli_commands_are_registered() -> None:
    parser = build_parser()
    subparsers_action = next(action for action in parser._actions if action.dest == "command")

    assert set(subparsers_action.choices) == set(COMMAND_HANDLERS)


def test_critical_docs_mention_registered_cli_commands() -> None:
    assert missing_documented_commands() == []


def test_generated_paths_are_ignored() -> None:
    ignored = ignored_generated_paths(
        [
            "data/quant.db",
            "reports/example.json",
            "reports/agent_summary.md",
            "reports/charts/example.png",
            "examples/portfolio_constructed_targets.json",
        ]
    )

    assert all(ignored.values())


def test_no_stale_v1_version_references_in_docs() -> None:
    assert stale_version_references() == {}


def test_stale_version_audit_catches_current_version_drift(tmp_path: Path) -> None:
    readme = tmp_path / "README.md"
    ai_development = tmp_path / "AI_DEVELOPMENT.md"
    readme.write_text("# Project\n\n## Current Version\n\n`v0.42.0-factor-eval-cache`\n", encoding="utf-8")
    ai_development.write_text("# AI\n\n## Current Version\n\n`v0.35.0-mcp-server-foundation`\n", encoding="utf-8")

    stale = stale_version_references([readme, ai_development])

    assert str(ai_development) in stale
    assert "does not start with `v0.42.0`" in stale[str(ai_development)][0]


def test_no_unintentional_empty_package_dirs() -> None:
    assert empty_package_dirs() == []


def test_required_module_docs_exist() -> None:
    assert missing_module_docs() == []


def test_required_packaging_files_exist() -> None:
    assert missing_packaging_files() == []


def test_tracked_generated_dirs_only_keep_placeholders() -> None:
    assert (Path("data") / ".gitkeep").exists()
    assert (Path("reports") / ".gitkeep").exists()
