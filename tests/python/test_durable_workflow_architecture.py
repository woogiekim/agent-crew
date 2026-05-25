"""Tests for the durable workflow architecture contract."""

from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CHECK = REPO_ROOT / "core" / "scripts" / "durable-workflow-architecture-check.py"
SCHEMA = REPO_ROOT / "core" / "schemas" / "durable-workflow.schema.json"
FIXTURE = REPO_ROOT / "core" / "evaluations" / "durable-workflow-architecture.json"


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


durable_check = _load_module(CHECK, "durable_workflow_architecture_check")


def test_durable_workflow_architecture_check_passes():
    result = subprocess.run(
        ["python3", str(CHECK), "--format", "json"],
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["passed"] is True
    assert payload["summary"]["failed"] == 0


def test_durable_workflow_schema_exposes_protocol_surfaces():
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    required = set(schema["required"])
    properties = set(schema["properties"])

    assert schema["additionalProperties"] is False
    assert {
        "workflow_id",
        "task_id",
        "current_state",
        "lifecycle",
        "checkpoint",
        "resume",
        "roles",
        "approval",
        "observability",
        "extension_policy",
        "memory_refs",
    }.issubset(required)
    assert required.issubset(properties)


def test_durable_workflow_fixture_covers_open_issue_set():
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))

    assert set(fixture["issues"]) == {"107", "108", "109", "110", "111", "112", "113"}
    assert fixture["direction"] == "Persistent AI Workforce System"
    assert "workflow durability" in fixture["principles"]
    assert "operational continuity" in fixture["principles"]


def test_durable_workflow_contract_fails_without_issue_coverage(tmp_path: Path):
    (tmp_path / "docs").mkdir()
    (tmp_path / "core" / "schemas").mkdir(parents=True)
    (tmp_path / "core" / "evaluations").mkdir(parents=True)
    (tmp_path / "docs" / "durable-workflow-architecture.md").write_text(
        "Persistent AI Workforce System",
        encoding="utf-8",
    )
    (tmp_path / "core" / "schemas" / "durable-workflow.schema.json").write_text(
        json.dumps({"properties": {}, "required": []}),
        encoding="utf-8",
    )
    (tmp_path / "core" / "evaluations" / "durable-workflow-architecture.json").write_text(
        json.dumps({"issues": {"107": {}}}),
        encoding="utf-8",
    )

    payload = durable_check.evaluate(tmp_path)
    failed = {failure["name"] for failure in payload["failures"]}

    assert payload["passed"] is False
    assert "issue_coverage" in failed
