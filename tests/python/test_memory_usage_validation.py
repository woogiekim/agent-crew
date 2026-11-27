"""Tests for memory-usage SSOT validation."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path

import jsonschema
import pytest


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


def test_applied_json_pointer_validates_without_compatibility_projection(tmp_path: Path):
    usage = _usage([
        _decision(
            "mem-project",
            "applied",
            [{"artifact": "pipeline.json", "locator_type": "json_pointer", "locator": "/stages/0/tdd_parallel", "effect": "set_true"}],
        )
    ])
    task_dir = _write_task(tmp_path, usage)

    result = _run_validator(task_dir)

    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["passed"] is True
    assert not (task_dir / "context" / "memory-evidence.json").exists()


def test_live_eligibility_is_batched_and_each_memory_is_checked(tmp_path: Path, monkeypatch):
    module = _load_module()
    names = ("active", "retired", "missing")
    app = {"artifact": "context/analysis.md", "locator_type": "markdown_heading", "locator": "Risks"}
    task = _write_task(tmp_path, _usage([_decision(name, "applied", [app]) for name in names]),
                       [_selected_memory(memory_id=name) for name in names])
    seen = []
    statuses = {"active": True, "retired": False, "missing": None}

    def run(argv, **kwargs):
        seen.append(argv)
        if "--eligibility-only" in argv:
            payload = {"schema_version": "mnemos.read-eligibility.response.v1",
                       "items": [{"id": name, "eligible_for_use": statuses[name]} for name in names if name != "missing"]}
        else:
            name = argv[-1]
            payload = {"id": name, "eligible_for_use": statuses[name]}
        return subprocess.CompletedProcess(argv, 0, stdout=json.dumps(payload))

    monkeypatch.setattr(module.subprocess, "run", run)

    result = module.validate_usage(task, strict=True, memory_bin="memory")

    assert len(seen) == 1
    assert set(seen[0][-3:]) == set(names)
    assert result["memory_feedback_allowed_ids"] == ["active"]
    assert {row["memory_id"]: row["code"] for row in result["findings"]} == {
        "retired": "memory_no_longer_eligible", "missing": "memory_current_state_unavailable",
    }


def test_validator_rejects_legacy_write_compat_option(tmp_path: Path):
    usage = _usage([_decision("mem-project", "accepted_not_applied")])
    task_dir = _write_task(tmp_path, usage)

    result = _run_validator(task_dir, "--write-compat")

    assert result.returncode == 2
    assert "unrecognized arguments" in result.stderr


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


def test_applied_project_context_requires_readable_source_inside_recalled_root(tmp_path: Path):
    project = tmp_path / "repo"
    project.mkdir()
    (project / "present.md").write_text("## Evidence\n", encoding="utf-8")
    outside = tmp_path / "outside.md"
    outside.write_text("## Evidence\n", encoding="utf-8")
    (project / "escaped.md").symlink_to(outside)
    selected = [
        _selected_memory(memory_id=path, record_type="project_context_section",
                         source_path=path, source_section="Evidence")
        for path in ("present.md", "missing.md", "escaped.md")
    ]
    application = {"artifact": "context/analysis.md", "locator_type": "markdown_heading",
                   "locator": "Risks", "effect": "updated_risk_check"}
    usage = _usage([_decision(row["memory_id"], "applied", [application], reason_code="source_verified")
                    for row in selected])
    task_dir = _write_task(tmp_path, usage, selected)
    retrieval_file = task_dir / "context/memory-retrieval.json"
    retrieval = json.loads(retrieval_file.read_text())
    retrieval["project_root"] = str(project)
    retrieval_file.write_text(json.dumps(retrieval), encoding="utf-8")

    standard = _run_validator(task_dir)
    strict = _run_validator(task_dir, "--strict")

    assert standard.returncode == 1
    assert strict.returncode == 2
    result = json.loads(strict.stdout)
    assert result["memory_feedback_allowed_ids"] == ["present.md"]
    assert {(item["memory_id"], item["code"]) for item in result["findings"]} == {
        ("missing.md", "project_source_unavailable"), ("escaped.md", "project_source_unavailable"),
    }


def test_project_source_section_must_exist_and_match_the_captured_content(tmp_path: Path):
    project = tmp_path / "repo"
    project.mkdir()
    section = "# Evidence\n\nKeep the current decision."
    content_hash = hashlib.sha256(section.encode("utf-8")).hexdigest()
    notes = {
        "present": (section + "\n\n# Unrelated\nUpdated elsewhere.", "Evidence", content_hash),
        "renamed": ("# Old evidence\nSame prose.", "Evidence", None),
        "edited": ("# Evidence\nReverse the decision.", "Evidence", content_hash),
        "duplicate": (section + "\n\n# Evidence\nA newer decision.", "Evidence", content_hash),
        "plain": ("Text without headings.", "(document)", None),
        "preamble": ("Intro\n\n# Next\nBody.", "(preamble)", None),
        "named-preamble": ("Intro\n\n# (preamble)\nBody.", "(preamble)",
                           hashlib.sha256(b"# (preamble)\nBody.").hexdigest()),
    }
    rows = []
    for name, (text, heading, digest) in notes.items():
        filename = name + ".md"
        (project / filename).write_text(text, encoding="utf-8")
        rows.append(_selected_memory(memory_id=name, record_type="project_context_section",
                                     source_path=filename, source_section=heading, source_content_hash=digest,
                                     content="# (preamble)\nBody." if name == "named-preamble" else section))
    application = {"artifact": "context/analysis.md", "locator_type": "markdown_heading",
                   "locator": "Risks", "effect": "updated_risk_check"}
    usage = _usage([_decision(name, "applied", [application], reason_code="source_verified") for name in notes])
    task = _write_task(tmp_path, usage, rows)
    retrieval_file = task / "context/memory-retrieval.json"
    retrieval = json.loads(retrieval_file.read_text())
    retrieval["project_root"] = str(project)
    retrieval_file.write_text(json.dumps(retrieval), encoding="utf-8")

    result = _run_validator(task, "--strict")

    assert result.returncode == 2
    report = json.loads(result.stdout)
    assert report["memory_feedback_allowed_ids"] == ["named-preamble", "plain", "preamble", "present"]
    assert {f["memory_id"]: f["code"] for f in report["findings"]} == {
        "renamed": "project_source_section_missing",
        "edited": "project_source_changed",
        "duplicate": "project_source_changed",
    }


@pytest.mark.skipif(not shutil.which("swiftc"), reason="Swift parser is required for this integration test")
def test_applied_swift_project_context_requires_an_unambiguous_declaration(tmp_path: Path, monkeypatch):
    project = tmp_path / "repo"
    project.mkdir()
    cases = {
        "present": ("final class PaletteFocusRequest {}", "PaletteFocusRequest"),
        "function": ("func keepKey(_ event: Int) {}", "keepKey(_:)"),
        "renamed": ("final class NewFocusRequest {}", "PaletteFocusRequest"),
        "comment-only": ("/*\nfunc keepKey() {}\n*/", "keepKey"),
        "duplicate": ("struct One { func keepKey() {} }\nstruct Two { func keepKey() {} }", "keepKey"),
        "syntax-error": ("func keepKey(", "keepKey"),
        "whole-file": ("let marker = 1", "(document)"),
    }
    rows = []
    for name, (text, symbol) in cases.items():
        path = f"{name}.swift"
        (project / path).write_text(text + "\n", encoding="utf-8")
        rows.append(_selected_memory(memory_id=name, record_type="project_context_section",
                                     source_path=path, source_section=symbol))
    application = {"artifact": "context/analysis.md", "locator_type": "markdown_heading",
                   "locator": "Risks", "effect": "updated_risk_check"}
    usage = _usage([_decision(name, "applied", [application], reason_code="source_verified") for name in cases])
    task_dir = _write_task(tmp_path, usage, rows)
    retrieval_path = task_dir / "context/memory-retrieval.json"
    retrieval = json.loads(retrieval_path.read_text())
    retrieval["project_root"] = str(project)
    retrieval_path.write_text(json.dumps(retrieval), encoding="utf-8")

    result = _run_validator(task_dir, "--strict")

    assert result.returncode == 2
    report = json.loads(result.stdout)
    assert report["memory_feedback_allowed_ids"] == ["function", "present", "whole-file"]
    assert {item["memory_id"]: item["code"] for item in report["findings"]} == {
        "renamed": "project_source_section_missing",
        "comment-only": "project_source_section_missing",
        "duplicate": "project_source_section_ambiguous",
        "syntax-error": "project_source_section_unverified",
    }

    monkeypatch.setenv("PATH", str(tmp_path))
    result = _run_validator(task_dir, "--strict")

    assert result.returncode == 2
    report = json.loads(result.stdout)
    assert report["memory_feedback_allowed_ids"] == ["whole-file"]
    assert {item["code"] for item in report["findings"]} == {"project_source_section_unverified"}


def test_candidate_application_requires_an_exact_scoped_current_source_excerpt(tmp_path: Path):
    project = tmp_path / "repo"
    project.mkdir()
    excerpt = "Keep the original test log for reuse."
    section = f"# Reuse\n\n{excerpt}"
    source = project / "checks.md"
    source.write_text(section, encoding="utf-8")
    common = dict(record_type="project_context_section", source_path="checks.md", source_section="Reuse", content=section,
                  source_content_hash=hashlib.sha256(section.encode("utf-8")).hexdigest())
    rows = [_selected_memory(memory_id="reviewed", **common),
            _selected_memory(memory_id="wrong-root", project_root_hash="other", **common),
            _selected_memory(memory_id="no-root", project_root_hash=None, **common),
            {**_selected_memory(memory_id="different-body", **common), "content": "Delete the original test log."}]
    application = {"artifact": "context/analysis.md", "locator_type": "markdown_heading",
                   "locator": "Risks", "effect": "Check original log before reuse"}
    decisions = [_decision(row["memory_id"], "applied", [application], reason_code="source_reviewed_candidate")
                 for row in rows]
    for decision in decisions:
        decision["source_review"] = {"excerpt": excerpt, "relevance": "Same test-log reuse decision"}
    task_dir = _write_task(tmp_path, _usage(decisions), [])
    retrieval_path = task_dir / "context/memory-retrieval.json"
    retrieval = json.loads(retrieval_path.read_text())
    retrieval.update(project_root=str(project), provider_response={"results": rows})
    retrieval_path.write_text(json.dumps(retrieval), encoding="utf-8")
    usage_path = task_dir / "context/memory-usage.json"

    result = _run_validator(task_dir, "--strict")

    assert result.returncode == 2
    report = json.loads(result.stdout)
    assert report["memory_feedback_allowed_ids"] == ["reviewed"]
    assert {item["memory_id"]: item["code"] for item in report["findings"]} == {
        "no-root": "memory_not_selected", "wrong-root": "memory_not_selected",
        "different-body": "project_recalled_body_mismatch",
    }
    jsonschema.validate(_usage([decisions[0]]), json.loads(SCHEMA.read_text()))

    usage_path.write_text(json.dumps(_usage([decisions[0]])), encoding="utf-8")
    assert _run_validator(task_dir, "--strict").returncode == 0

    decisions[0]["source_review"]["excerpt"] = "original test log"
    usage_path.write_text(json.dumps(_usage([decisions[0]])), encoding="utf-8")
    excerpt_error = json.loads(_run_validator(task_dir, "--strict").stdout)
    assert [item["code"] for item in excerpt_error["findings"]] == ["project_source_excerpt_missing"]

    decisions[0]["source_review"]["excerpt"] = excerpt
    usage_path.write_text(json.dumps(_usage([decisions[0]])), encoding="utf-8")
    source.write_text(section.replace("original", "dashboard"), encoding="utf-8")
    stale = json.loads(_run_validator(task_dir, "--strict").stdout)
    assert [item["code"] for item in stale["findings"]] == ["project_source_changed"]


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
