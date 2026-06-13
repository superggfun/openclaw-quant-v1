from __future__ import annotations

import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_pyproject_metadata_exists() -> None:
    pyproject = ROOT / "pyproject.toml"
    data = tomllib.loads(pyproject.read_text(encoding="utf-8"))

    assert data["project"]["name"] == "openclaw-quant"
    assert data["project"]["version"] == "0.41.0"
    assert data["project"]["requires-python"] == ">=3.11"
    assert "pandas>=2.2" in data["project"]["dependencies"]
    assert "core" in data["project"]["optional-dependencies"]
    assert "dev" in data["project"]["optional-dependencies"]
    assert data["project"]["scripts"]["openclaw-quant"] == "quant.cli:main"


def test_license_and_ci_files_exist() -> None:
    assert "MIT License" in (ROOT / "LICENSE").read_text(encoding="utf-8")
    assert (ROOT / ".github" / "workflows" / "ci.yml").exists()
    assert (ROOT / ".github" / "workflows" / "project_audit.yml").exists()
    assert (ROOT / ".github" / "ISSUE_TEMPLATE" / "bug_report.md").exists()
    assert (ROOT / ".github" / "ISSUE_TEMPLATE" / "feature_request.md").exists()
    assert (ROOT / ".github" / "PULL_REQUEST_TEMPLATE.md").exists()


def test_ci_workflows_run_pytest_and_audit() -> None:
    ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    audit = (ROOT / ".github" / "workflows" / "project_audit.yml").read_text(encoding="utf-8")

    assert "3.11" in ci
    assert "3.12" in ci
    assert 'pip install -e ".[dev]"' in ci
    assert 'pip install -e ".[dev]"' in audit
    assert "pytest" in ci
    assert "python tools/project_audit.py" in ci
    assert "python tools/project_audit.py" in audit
