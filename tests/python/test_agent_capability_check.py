"""Tests for the agent capability manifest validator."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPT = REPO_ROOT / "core" / "scripts" / "agent-capability-check.py"
SCHEMA = REPO_ROOT / "core" / "schemas" / "agent-capabilities.schema.json"
MANIFEST = REPO_ROOT / "core" / "policies" / "agent-capabilities.json"


def _make_project(tmp_path: Path) -> Path:
    project = tmp_path / "project"
    agents_dir = project / "core" / "agents"
    policies_dir = project / "core" / "policies"
    schemas_dir = project / "core" / "schemas"
    agents_dir.mkdir(parents=True)
    policies_dir.mkdir(parents=True)
    schemas_dir.mkdir(parents=True)

    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    for name in manifest["agents"]:
        (agents_dir / f"{name}.md").write_text(f"# Agent: {name}\n", encoding="utf-8")
    (schemas_dir / "agent-capabilities.schema.json").write_text(SCHEMA.read_text(encoding="utf-8"), encoding="utf-8")
    (policies_dir / "agent-capabilities.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return project


def _run(project: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "python3",
            str(SCRIPT),
            "--project-root",
            str(project),
            "--format",
            "json",
        ],
        text=True,
        capture_output=True,
    )


def test_agent_capability_check_passes_current_repository():
    result = subprocess.run(
        ["python3", str(SCRIPT), "--format", "json"],
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["passed"] is True
    assert payload["summary"]["failed"] == 0


def test_agent_capability_check_catches_reviewer_write_authority(tmp_path: Path):
    project = _make_project(tmp_path)
    manifest_path = project / "core" / "policies" / "agent-capabilities.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["agents"]["reviewer"]["may_implement"] = True
    manifest["agents"]["reviewer"]["allowed_capabilities"].append("edit_file")
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    result = _run(project)

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    failed_names = {failure["name"] for failure in payload["failures"]}
    assert "reviewer.reviewer_read_only_boundary" in failed_names
    assert "reviewer.no_capability_overlap" in failed_names


def test_agent_capability_check_enforces_cost_tier_distribution(tmp_path: Path):
    project = _make_project(tmp_path)
    manifest_path = project / "core" / "policies" / "agent-capabilities.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for agent in manifest["agents"].values():
        agent["model_tier"] = "high"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    result = _run(project)

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    failed_names = {failure["name"] for failure in payload["failures"]}
    assert "routing.cost_aware_model_tiers" in failed_names
