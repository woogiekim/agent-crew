"""Tests for the agent capability manifest validator."""

from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPT = REPO_ROOT / "core" / "scripts" / "agent-capability-check.py"
SCHEMA = REPO_ROOT / "core" / "schemas" / "agent-capabilities.schema.json"
MANIFEST = REPO_ROOT / "core" / "policies" / "agent-capabilities.json"


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


capability_check = _load_module(SCRIPT, "agent_capability_check")


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


def test_agent_capability_check_requires_safe_default_custom_profile(tmp_path: Path):
    project = _make_project(tmp_path)
    manifest_path = project / "core" / "policies" / "agent-capabilities.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["default_custom_profile"] = "custom-devops-approved"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    result = _run(project)

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    failed_names = {failure["name"] for failure in payload["failures"]}
    assert "custom_profiles.default_safe_worker" in failed_names


def test_agent_capability_check_blocks_recursive_custom_profile(tmp_path: Path):
    project = _make_project(tmp_path)
    manifest_path = project / "core" / "policies" / "agent-capabilities.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    profile = dict(manifest["custom_profiles"]["custom-worker"])
    profile["role"] = "planner"
    profile["may_delegate"] = True
    manifest["custom_profiles"]["custom-planner"] = profile
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    result = _run(project)

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    failed_names = {failure["name"] for failure in payload["failures"]}
    assert "profile.custom-planner.no_recursive_orchestrator_role" in failed_names


def test_agent_capability_helpers_handle_invalid_shapes(tmp_path: Path):
    invalid = tmp_path / "invalid.json"
    invalid.write_text("not json", encoding="utf-8")
    payload, error = capability_check.read_json(invalid)
    assert payload is None
    assert error

    assert capability_check.agent_markdown_files(tmp_path) == set()
    assert capability_check.frontmatter_reasoning_tier(tmp_path / "missing.md") is None
    shape = capability_check.validate_agent_shape("broken", [])
    assert shape == [
        {
            "name": "broken.shape",
            "passed": False,
            "detail": "Agent entry must be an object.",
        }
    ]
    custom = capability_check.validate_custom_profiles({"custom_profiles": []})
    assert custom[0]["name"] == "custom_profiles.object"
    assert custom[0]["passed"] is False


def test_agent_capability_check_reports_manifest_parse_error(tmp_path: Path):
    project = _make_project(tmp_path)
    manifest_path = project / "core" / "policies" / "agent-capabilities.json"
    manifest_path.write_text("not json", encoding="utf-8")

    result = _run(project)

    assert result.returncode == 2
    payload = json.loads(result.stdout)
    failed_names = {failure["name"] for failure in payload["failures"]}
    assert "manifest.parse" in failed_names


def test_agent_capability_check_handles_non_object_collections(tmp_path: Path):
    project = _make_project(tmp_path)
    manifest_path = project / "core" / "policies" / "agent-capabilities.json"
    manifest_path.write_text(
        json.dumps({
            "schema_version": 1,
            "agents": [],
            "custom_profiles": {},
            "default_custom_profile": "custom-worker",
        }),
        encoding="utf-8",
    )

    result = _run(project)

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    failed_names = {failure["name"] for failure in payload["failures"]}
    assert "manifest.agents_object" in failed_names


def test_agent_capability_check_skips_non_object_profiles_and_agents(tmp_path: Path):
    project = _make_project(tmp_path)
    manifest_path = project / "core" / "policies" / "agent-capabilities.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["custom_profiles"]["custom-broken"] = []
    manifest["agents"]["broken-agent"] = []
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    result = _run(project)

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    failed_names = {failure["name"] for failure in payload["failures"]}
    assert "profile.custom-broken.shape" in failed_names
    assert "broken-agent.shape" in failed_names


def test_agent_capability_check_text_output_lists_failures(tmp_path: Path):
    project = _make_project(tmp_path)
    manifest_path = project / "core" / "policies" / "agent-capabilities.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["agents"]["reviewer"]["may_implement"] = True
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    result = subprocess.run(
        ["python3", str(SCRIPT), "--project-root", str(project)],
        text=True,
        capture_output=True,
    )

    assert result.returncode == 1
    assert "FAIL: agent capability check" in result.stdout
    assert "reviewer.reviewer_read_only_boundary" in result.stdout
