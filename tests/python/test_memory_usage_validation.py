"""Tests for memory-usage SSOT validation and compatibility projection."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import jsonschema


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPT = REPO_ROOT / "core" / "scripts" / "validate-memory-usage.py"
SCHEMA = REPO_ROOT / "core" / "schemas" / "memory-usage.schema.json"


def _load_module():
    spec = importlib.util.spec_from_file_location("validate_memory_usage", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _selected_memory(**overrides):
    payload = {
        "memory_id": "mem-project",
        "content": "project lesson",
        "layer": "project",
        "semantic_status": "active",
        "project_id": "agent-crew-abc123",
        "project_root_hash": "abc123",
        "superseded_by": [],
    }
    payload.update(overrides)
    return payload


def _usage(decisions):
    return {
        "schema_version": "agent-crew.memory-usage.v2",
        "retrieval_id": "task-1-recall",
        "task_id": "task-1",
        "decisions": decisions,
        "conflicts": [],
        "generated_by": "analyst",
        "generated_at_phase": "phase-1b-analysis",
    }


def _decision(memory_id: str, disposition: str, applications=None, reason_code="matched_prior_aar"):
    return {
        "memory_id": memory_id,
        "disposition": disposition,
        "reason_code": reason_code,
        "applications": applications or [],
    }


def _write_task(tmp_path: Path, usage: dict, selected: list[dict] | None = None) -> Path:
    task_dir = tmp_path / "task"
    context = task_dir / "context"
    context.mkdir(parents=True)
    (task_dir / "pipeline.json").write_text(
        json.dumps({"stages": [{"agents": ["backend"], "tdd_parallel": True}]}),
        encoding="utf-8",
    )
    (context / "analysis.md").write_text("# Risks\n\nMemory shaped risk table.\n", encoding="utf-8")
    (context / "memory-retrieval.json").write_text(
        json.dumps({
            "status": "ok",
            "request": {"scope": {"project_id": "agent-crew-abc123", "project_root_hash": "abc123"}},
            "results": selected if selected is not None else [_selected_memory()],
        }),
        encoding="utf-8",
    )
    (context / "memory-usage.json").write_text(json.dumps(usage), encoding="utf-8")
    return task_dir


def _run_validator(task_dir: Path, *extra: str):
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--task-dir", str(task_dir), "--format", "json", *extra],
        text=True,
        capture_output=True,
        check=False,
    )


def test_memory_usage_schema_accepts_all_dispositions():
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    usage = _usage([
        _decision("m1", "applied", [{"artifact": "pipeline.json", "locator_type": "json_pointer", "locator": "/stages/0/tdd_parallel", "effect": "set_true"}]),
        _decision("m2", "accepted_not_applied"),
        _decision("m3", "ignored"),
        _decision("m4", "superseded"),
        _decision("m5", "conflict_with_current_requirements"),
        _decision("m6", "conflict_with_managed_rule"),
    ])

    jsonschema.validate(instance=usage, schema=schema)


def test_applied_json_pointer_validates_and_writes_compatibility_projection(tmp_path: Path):
    usage = _usage([
        _decision(
            "mem-project",
            "applied",
            [{"artifact": "pipeline.json", "locator_type": "json_pointer", "locator": "/stages/0/tdd_parallel", "effect": "set_true"}],
        )
    ])
    task_dir = _write_task(tmp_path, usage)

    result = _run_validator(task_dir, "--write-compat")

    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["passed"] is True
    compat = json.loads((task_dir / "context" / "memory-evidence.json").read_text(encoding="utf-8"))
    assert compat["source"] == "memory-usage.json"
    assert compat["retrieved_ids"] == ["mem-project"]
    assert compat["accepted_ids"] == ["mem-project"]
    assert compat["ignored_ids"] == []


def test_validator_covers_invalid_disposition_locator_and_selected_memory_cases(tmp_path: Path):
    usage = _usage([
        _decision("missing", "applied", [{"artifact": "pipeline.json", "locator_type": "json_pointer", "locator": "/stages/99", "effect": "set"}]),
        _decision("mem-project", "ignored", [{"artifact": "pipeline.json", "locator_type": "json_pointer", "locator": "/stages/0", "effect": "bad"}]),
        _decision("mem-project", "accepted_not_applied"),
    ])
    task_dir = _write_task(tmp_path, usage)

    result = _run_validator(task_dir)

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    codes = {finding["code"] for finding in payload["findings"]}
    assert "memory_not_selected" in codes
    assert "json_pointer_missing" in codes
    assert "ignored_has_applications" in codes
    assert "duplicate_decision" in codes


def test_every_selected_memory_requires_one_decision(tmp_path: Path):
    usage = _usage([_decision("mem-project", "accepted_not_applied")])
    task_dir = _write_task(
        tmp_path,
        usage,
        [_selected_memory(memory_id="mem-project"), _selected_memory(memory_id="mem-extra")],
    )

    result = _run_validator(task_dir)

    assert result.returncode == 1
    assert "selected_memory_missing_decision" in {finding["code"] for finding in json.loads(result.stdout)["findings"]}


def test_wrong_project_superseded_and_invalidated_memories_cannot_be_applied(tmp_path: Path):
    selected = [
        _selected_memory(memory_id="wrong-project", project_id="other-project"),
        _selected_memory(memory_id="superseded", superseded_by=["newer"]),
        _selected_memory(memory_id="invalidated", semantic_status="invalidated"),
        _selected_memory(memory_id="deprecated", semantic_status="deprecated"),
    ]
    usage = _usage([
        _decision(mid, "applied", [{"artifact": "pipeline.json", "locator_type": "json_pointer", "locator": "/stages/0/tdd_parallel", "effect": "set_true"}])
        for mid in ("wrong-project", "superseded", "invalidated", "deprecated")
    ])
    task_dir = _write_task(tmp_path, usage, selected)

    result = _run_validator(task_dir)

    assert result.returncode == 1
    codes = {finding["code"] for finding in json.loads(result.stdout)["findings"]}
    assert {"wrong_project_applied", "superseded_applied", "inactive_memory_applied"} <= codes


def test_session_or_global_candidate_pipeline_change_and_managed_rule_conflict_fail(tmp_path: Path):
    selected = [
        _selected_memory(memory_id="session-mem", layer="session", project_id=""),
        _selected_memory(memory_id="candidate-mem", layer="global_candidate", project_id=""),
        _selected_memory(memory_id="managed-conflict", layer="global", project_id=""),
    ]
    pipeline_app = {"artifact": "pipeline.json", "locator_type": "json_pointer", "locator": "/stages/0/tdd_parallel", "effect": "set_true"}
    usage = _usage([
        _decision("session-mem", "applied", [pipeline_app]),
        _decision("candidate-mem", "applied", [pipeline_app]),
        _decision("managed-conflict", "conflict_with_managed_rule", [pipeline_app], reason_code="conflicts_with_managed_rule"),
    ])
    task_dir = _write_task(tmp_path, usage, selected)

    result = _run_validator(task_dir)

    assert result.returncode == 1
    codes = {finding["code"] for finding in json.loads(result.stdout)["findings"]}
    assert "advisory_layer_pipeline_change" in codes
    assert "managed_rule_conflict_applied" in codes


def test_markdown_heading_locator_must_exist(tmp_path: Path):
    usage = _usage([
        _decision(
            "mem-project",
            "applied",
            [{"artifact": "context/analysis.md", "locator_type": "markdown_heading", "locator": "Missing", "effect": "added_risk"}],
        )
    ])
    task_dir = _write_task(tmp_path, usage)

    result = _run_validator(task_dir)

    assert result.returncode == 1
    assert "markdown_heading_missing" in {finding["code"] for finding in json.loads(result.stdout)["findings"]}


def test_strict_mode_turns_validator_warning_into_failure(tmp_path: Path, monkeypatch):
    usage = _usage([_decision("mem-project", "applied")])
    task_dir = _write_task(tmp_path, usage)

    non_strict = _run_validator(task_dir)
    strict = _run_validator(task_dir, "--strict")

    assert non_strict.returncode == 1
    assert strict.returncode == 2
    assert "applied_without_applications" in {finding["code"] for finding in json.loads(strict.stdout)["findings"]}
