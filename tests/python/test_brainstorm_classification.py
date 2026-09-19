from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "core" / "scripts" / "brainstorm-classification.py"
spec = importlib.util.spec_from_file_location("brainstorm_classification", SCRIPT)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_incompatible_public_contract_forces_architectural() -> None:
    result = module.classify_minimum(
        "Remove the legacy response field from the public API",
        evidence={"backward_incompatible_public_contract": True},
    )

    assert result["classification"] == "Architectural"
    assert result["matched_rules"] == ["backward_incompatible_public_contract"]


def test_semantic_result_can_raise_but_not_lower_rule_minimum() -> None:
    rule = {"classification": "Architectural", "matched_rules": ["security_boundary_change"]}
    lowered = module.resolve_classification(rule, {"classification": "Bounded", "evidence": []})
    raised = module.resolve_classification(
        {"classification": "Bounded", "matched_rules": []},
        {"classification": "Architectural", "evidence": ["ownership boundary moves"]},
    )

    assert lowered["classification"] == "Architectural"
    assert lowered["resolution"] == "rule_minimum_preserved"
    assert raised["classification"] == "Architectural"
    assert raised["resolution"] == "semantic_raise"


def test_unknown_semantic_classification_degrades_to_rule_minimum() -> None:
    resolved = module.resolve_classification(
        {"classification": "Bounded", "matched_rules": []},
        {"classification": "Unknown", "evidence": []},
    )

    assert resolved == {
        "classification": "Bounded",
        "resolution": "rule_minimum_preserved",
        "semantic_status": "degraded",
    }


@pytest.mark.parametrize("semantic_classification", ([], {}))
def test_non_string_semantic_classification_degrades_to_rule_minimum(
    semantic_classification: object,
) -> None:
    resolved = module.resolve_classification(
        {"classification": "Bounded", "matched_rules": []},
        {"classification": semantic_classification, "evidence": []},
    )

    assert resolved == {
        "classification": "Bounded",
        "resolution": "rule_minimum_preserved",
        "semantic_status": "degraded",
    }


def test_file_count_and_api_keyword_do_not_force_architectural() -> None:
    result = module.classify_minimum("Add a backward-compatible API field in five files")

    assert result["classification"] == "Bounded"
    assert result["matched_rules"] == []


def test_canonical_hash_ignores_display_copy_but_changes_bound_fields() -> None:
    base = {"classification": "Bounded", "goals": ["add field"], "display_summary": "first"}

    assert module.canonical_hash(base) == module.canonical_hash({**base, "display_summary": "second"})
    assert module.canonical_hash(base) != module.canonical_hash({**base, "goals": ["remove field"]})


def test_cli_reports_preliminary_schema_with_rule_result() -> None:
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "Add a local validation", "--stage", "preliminary", "--format", "json"],
        capture_output=True,
        check=True,
        text=True,
    )

    payload = json.loads(result.stdout)
    assert payload["schema_version"] == 1
    assert payload["stage"] == "preliminary"
    assert payload["rule_result"]["classification"] == "Bounded"
    assert payload["semantic_result"] is None
    assert payload["final_classification"] == "Bounded"
    assert payload["resolution"] == "rule_minimum_preserved"
    assert payload["classifier_version"] == 1


def test_cli_returns_structured_error_for_unreadable_semantic_input(tmp_path: Path) -> None:
    missing_semantic_file = tmp_path / "missing-semantic.json"
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "Add a local validation", "--semantic-file", str(missing_semantic_file)],
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert json.loads(result.stderr)["error"] == "input_read_error"


@pytest.mark.parametrize("option", ("--semantic-file", "--evidence-file"))
def test_cli_returns_structured_error_for_non_utf8_json_input(tmp_path: Path, option: str) -> None:
    invalid_json_file = tmp_path / "invalid.json"
    invalid_json_file.write_bytes(b"\xff")
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "Add a local validation", option, str(invalid_json_file)],
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert json.loads(result.stderr)["error"] == "input_read_error"


def test_text_output_includes_rule_and_semantic_evidence(tmp_path: Path) -> None:
    evidence_file = tmp_path / "evidence.json"
    evidence_file.write_text(
        json.dumps({"backward_incompatible_public_contract": True}),
        encoding="utf-8",
    )
    semantic_file = tmp_path / "semantic.json"
    semantic_file.write_text(
        json.dumps({"classification": "Architectural", "evidence": ["ownership boundary moves"]}),
        encoding="utf-8",
    )
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "Remove a response field",
            "--evidence-file",
            str(evidence_file),
            "--semantic-file",
            str(semantic_file),
            "--format",
            "text",
        ],
        capture_output=True,
        check=True,
        text=True,
    )

    assert "matched_rules: backward_incompatible_public_contract" in result.stdout
    assert 'rule_evidence: {"backward_incompatible_public_contract":true}' in result.stdout
    assert 'semantic_evidence: ["ownership boundary moves"]' in result.stdout
