"""Tests for planning-time TDD/reviewer quality-loop enforcement."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CHECKER = REPO_ROOT / "core" / "scripts" / "pipeline-quality-plan-check.py"


def write_pipeline(tmp_path: Path, pipeline: dict) -> Path:
    path = tmp_path / "pipeline.json"
    path.write_text(json.dumps(pipeline), encoding="utf-8")
    return path


def write_prd(tmp_path: Path, content: str) -> Path:
    """Write `content` to ``<tmp_path>/context/prd.md`` (creating the dir)."""
    context_dir = tmp_path / "context"
    context_dir.mkdir(parents=True, exist_ok=True)
    path = context_dir / "prd.md"
    path.write_text(content, encoding="utf-8")
    return path


def _passing_pipeline() -> dict:
    """Minimal pipeline that passes plan-quality checks.

    Mirrors ``test_plan_checker_accepts_split_tdd_implementation_stages`` —
    a single TDD-parallel implementation stage followed by a reviewer, which
    is the smallest known shape the checker accepts.
    """

    return {
        "schema_version": 1,
        "task": "Implement a backend feature",
        "stages": [
            {"agents": ["backend"], "tdd_parallel": True},
            "reviewer",
        ],
        "completed_stages": 0,
    }


def run_checker(path: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["python3", str(CHECKER), "--pipeline", str(path), "--format", "json"],
        text=True,
        capture_output=True,
    )


def test_plan_checker_blocks_bare_implementation_stage(tmp_path: Path):
    path = write_pipeline(
        tmp_path,
        {
            "schema_version": 1,
            "task": "Implement production quality behavior",
            "stages": ["backend", "reviewer"],
            "completed_stages": 0,
        },
    )

    result = run_checker(path)

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert "implementation_stage_without_tdd_parallel" in payload["failures"]


def test_plan_checker_reports_missing_pipeline_path(tmp_path: Path):
    result = subprocess.run(
        ["python3", str(CHECKER), "--pipeline", str(tmp_path / "missing.json")],
        text=True,
        capture_output=True,
    )

    assert result.returncode == 2
    assert "pipeline not found" in result.stderr


def test_plan_checker_text_output_lists_failures(tmp_path: Path):
    path = write_pipeline(
        tmp_path,
        {
            "schema_version": 1,
            "task": "Implement production quality behavior",
            "stages": ["backend", "reviewer"],
            "completed_stages": 0,
        },
    )

    result = subprocess.run(
        ["python3", str(CHECKER), "--pipeline", str(path)],
        text=True,
        capture_output=True,
    )

    assert result.returncode == 1
    assert "FAIL: pipeline quality plan" in result.stdout
    assert "- implementation_stage_without_tdd_parallel" in result.stdout


def test_plan_checker_blocks_mixed_bare_implementation_stage(tmp_path: Path):
    path = write_pipeline(
        tmp_path,
        {
            "schema_version": 1,
            "task": "Implement a full-stack feature",
            "stages": [["designer", "backend"], ["frontend"], "reviewer"],
            "completed_stages": 0,
        },
    )

    result = run_checker(path)

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert "implementation_stage_without_tdd_parallel" in payload["failures"]


def test_plan_checker_blocks_multi_agent_tdd_stage(tmp_path: Path):
    path = write_pipeline(
        tmp_path,
        {
            "schema_version": 1,
            "task": "Implement a full-stack feature",
            "stages": [
                {"agents": ["backend", "frontend"], "tdd_parallel": True},
                "reviewer",
            ],
            "completed_stages": 0,
        },
    )

    result = run_checker(path)

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert "implementation_stage_without_tdd_parallel" in payload["failures"]
    assert "multi_agent_implementation_stage_must_split_for_tdd" in payload["failures"]
    assert payload["implementation_stages"][0]["implementers"] == ["backend", "frontend"]


def test_plan_checker_accepts_split_tdd_implementation_stages(tmp_path: Path):
    path = write_pipeline(
        tmp_path,
        {
            "schema_version": 1,
            "task": "Implement a full-stack feature",
            "stages": [
                "designer",
                {"agents": ["backend"], "tdd_parallel": True},
                "reviewer",
                {"agents": ["frontend"], "tdd_parallel": True},
                "reviewer",
            ],
            "completed_stages": 0,
        },
    )

    result = run_checker(path)

    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["required"] is True


def test_plan_checker_blocks_unmapped_prd_acceptance_criteria(tmp_path: Path):
    path = write_pipeline(
        tmp_path,
        {
            "schema_version": 1,
            "task": "Implement a backend feature",
            "stages": [
                {
                    "agents": ["backend"],
                    "tdd_parallel": True,
                    "acceptance_criteria": ["AC-001"],
                },
                "reviewer",
            ],
            "completed_stages": 0,
        },
    )
    write_prd(
        tmp_path,
        "# PRD\n\n"
        "## Acceptance Criteria\n"
        "- AC-001: first behavior is implemented.\n"
        "- AC-002: second behavior is implemented.\n",
    )

    result = run_checker(path)

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert "prd_acceptance_criteria_unmapped" in payload["failures"]
    assert payload["prd_unmapped_acceptance_criteria"] == ["AC-002"]


def test_plan_checker_does_not_require_prd_acceptance_mapping_by_default(tmp_path: Path):
    path = write_pipeline(tmp_path, _passing_pipeline())
    write_prd(
        tmp_path,
        "# PRD\n\n"
        "## Acceptance Criteria\n"
        "- AC-001: documented but not mapped by this legacy pipeline.\n",
    )

    result = run_checker(path)

    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["required"] is True
    assert payload["pipeline_acceptance_criteria"] == []
    assert payload["prd_unmapped_acceptance_criteria"] == []
    assert "prd_acceptance_criteria_unmapped" not in payload["failures"]


def test_plan_checker_does_not_map_acceptance_ids_for_design_only_pipeline(tmp_path: Path):
    path = write_pipeline(
        tmp_path,
        {
            "schema_version": 1,
            "task": "Create a UI design specification",
            "stages": [
                {
                    "agents": ["designer"],
                    "acceptance_criteria": ["AC-001"],
                },
                "reviewer",
            ],
            "completed_stages": 0,
        },
    )
    write_prd(
        tmp_path,
        "# PRD\n\n"
        "## Acceptance Criteria\n"
        "- AC-001: design covers the primary state.\n"
        "- AC-002: design covers the empty state.\n",
    )

    result = run_checker(path)

    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["required"] is False
    assert payload["prd_unmapped_acceptance_criteria"] == []
    assert "prd_acceptance_criteria_unmapped" not in payload["failures"]


def test_plan_checker_acceptance_mapping_supports_short_ac_ids(tmp_path: Path):
    path = write_pipeline(
        tmp_path,
        {
            "schema_version": 1,
            "task": "Implement a backend feature",
            "stages": [
                {
                    "agents": ["backend"],
                    "tdd_parallel": True,
                    "acceptance_criteria": ["AC-1"],
                },
                "reviewer",
            ],
            "completed_stages": 0,
        },
    )
    write_prd(
        tmp_path,
        "# PRD\n\n"
        "## Acceptance Criteria\n"
        "- AC-1: first behavior is implemented.\n"
        "- AC-2: second behavior is implemented.\n",
    )

    result = run_checker(path)

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["prd_acceptance_criteria"] == ["AC-1", "AC-2"]
    assert payload["pipeline_acceptance_criteria"] == ["AC-1"]
    assert payload["prd_unmapped_acceptance_criteria"] == ["AC-2"]
    assert "prd_acceptance_criteria_unmapped" in payload["failures"]


def test_plan_checker_accepts_qa_verify_between_implementation_and_reviewer(tmp_path: Path):
    path = write_pipeline(
        tmp_path,
        {
            "schema_version": 1,
            "task": "Implement a user-facing backend feature with QA validation",
            "stages": [
                {"agents": ["qa-owner"], "qa_mode": "plan"},
                {"agents": ["backend"], "tdd_parallel": True},
                {
                    "agents": ["qa-owner"],
                    "qa_mode": "verify",
                    "qa_loop_target": "previous_implementation",
                },
                "reviewer",
            ],
            "completed_stages": 0,
        },
    )

    result = run_checker(path)

    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["required"] is True
    assert payload["pipeline_shape"]["qa_verify_indexes"] == [2]
    assert payload["pipeline_shape"]["has_quality_gate_after_each_implementer"] is True


def test_plan_checker_blocks_qa_verify_without_following_reviewer(tmp_path: Path):
    path = write_pipeline(
        tmp_path,
        {
            "schema_version": 1,
            "task": "Implement a user-facing backend feature with QA validation",
            "stages": [
                {"agents": ["backend"], "tdd_parallel": True},
                {
                    "agents": ["qa-owner"],
                    "qa_mode": "verify",
                    "qa_loop_target": "previous_implementation",
                },
            ],
            "completed_stages": 0,
        },
    )

    result = run_checker(path)

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert "missing_pipeline_reviewer_after_qa_verify" in payload["failures"]
    assert payload["pipeline_shape"]["qa_verify_indexes_without_following_reviewer"] == [1]


def test_plan_checker_blocks_implementation_stage_without_immediate_reviewer(tmp_path: Path):
    path = write_pipeline(
        tmp_path,
        {
            "schema_version": 1,
            "task": "Implement a full-stack feature",
            "stages": [
                "designer",
                {"agents": ["backend"], "tdd_parallel": True},
                {"agents": ["frontend"], "tdd_parallel": True},
                "reviewer",
            ],
            "completed_stages": 0,
        },
    )

    result = run_checker(path)

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert "missing_pipeline_reviewer_after_each_implementer" in payload["failures"]
    assert payload["pipeline_shape"]["implementer_indexes_without_immediate_reviewer"] == [1]


def test_plan_checker_accepts_feature_deploy_after_code_review(tmp_path: Path):
    path = write_pipeline(
        tmp_path,
        {
            "schema_version": 1,
            "task": "Implement and deploy a backend feature",
            "stages": [
                {"agents": ["backend"], "tdd_parallel": True},
                "reviewer",
                "devops",
                "reviewer",
            ],
            "completed_stages": 0,
        },
    )

    result = run_checker(path)

    assert result.returncode == 0, result.stdout + result.stderr


def test_plan_checker_blocks_missing_reviewer_after_tdd_stage(tmp_path: Path):
    path = write_pipeline(
        tmp_path,
        {
            "schema_version": 1,
            "task": "Fix runtime quality loop",
            "stages": [{"agents": ["backend"], "tdd_parallel": True}],
            "completed_stages": 0,
        },
    )

    result = run_checker(path)

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert "missing_pipeline_reviewer_stage" in payload["failures"]
    assert "missing_pipeline_reviewer_after_implementer" in payload["failures"]


def test_plan_checker_blocks_code_task_without_implementation_stage(tmp_path: Path):
    path = write_pipeline(
        tmp_path,
        {
            "schema_version": 1,
            "task": "Implement runtime quality pipeline behavior",
            "stages": ["reviewer"],
            "completed_stages": 0,
        },
    )

    result = run_checker(path)

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["code_task"] is True
    assert "missing_pipeline_implementation_stage" in payload["failures"]


def test_plan_checker_ignores_design_only_pipeline(tmp_path: Path):
    path = write_pipeline(
        tmp_path,
        {
            "schema_version": 1,
            "task": "Create a UI design specification",
            "stages": ["designer", "reviewer"],
            "completed_stages": 0,
        },
    )

    result = run_checker(path)

    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["required"] is False


# ---------------------------------------------------------------------------
# Placeholder scan over prd.md (PRD §F2 / §F3)
# ---------------------------------------------------------------------------
#
# These tests exercise the placeholder scan that
# ``core/scripts/pipeline-quality-plan-check.py`` runs whenever a ``prd.md``
# exists at ``<dirname(pipeline.json)>/context/prd.md``. The scan emits
# ``prd_placeholder_<token_slug>`` failure labels (one per token type
# detected), populates ``prd_missing`` / ``prd_path`` / ``prd_placeholder_hits``
# on the JSON payload, and fails the gate (exit 1) on any hit. Blockquote
# lines and fenced code blocks are skipped so the rule itself can be
# documented; matching is case-insensitive on whole word/phrase boundaries
# so real words containing a token (e.g. ``TODOIST``) do not match.


def test_plan_checker_blocks_prd_with_todo_placeholder(tmp_path: Path):
    # Spec: prd.md § F3 — bullet 1: bare TODO placeholder fails the gate.
    pipeline = write_pipeline(tmp_path, _passing_pipeline())
    write_prd(
        tmp_path,
        "# PRD\n\n## Implementation\n\nTODO: finish later\n",
    )

    result = run_checker(pipeline)

    assert result.returncode == 1, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert "prd_placeholder_todo" in payload["failures"]


def test_plan_checker_blocks_prd_with_implement_later_phrase(tmp_path: Path):
    # Spec: prd.md § F3 — bullet 2: multi-word "implement later" phrase fails.
    pipeline = write_pipeline(tmp_path, _passing_pipeline())
    write_prd(
        tmp_path,
        "# PRD\n\n## Plan\n\nwe will implement later once design lands.\n",
    )

    result = run_checker(pipeline)

    assert result.returncode == 1, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert "prd_placeholder_implement_later" in payload["failures"]


def test_plan_checker_allows_blockquoted_forbidden_token(tmp_path: Path):
    # Spec: prd.md § F3 — bullet 3: blockquote lines (starting with `>`) are
    # skipped so the rule itself can quote the forbidden token.
    pipeline = write_pipeline(tmp_path, _passing_pipeline())
    write_prd(
        tmp_path,
        "# PRD\n\n## Notes\n\n> TODO: this rule documents the forbidden token\n",
    )

    result = run_checker(pipeline)

    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert "prd_placeholder_todo" not in payload["failures"]
    # PRD is present, so the scan must have run and emitted these fields.
    assert payload["prd_missing"] is False
    assert payload["prd_placeholder_hits"] == []


def test_plan_checker_allows_fenced_code_block_forbidden_token(tmp_path: Path):
    # Spec: prd.md § F3 — bullet 4: lines inside ``` fences are skipped so
    # test fixtures / docs can include the forbidden token verbatim.
    pipeline = write_pipeline(tmp_path, _passing_pipeline())
    write_prd(
        tmp_path,
        "# PRD\n\n## Example\n\n```\nTODO: example\n```\n",
    )

    result = run_checker(pipeline)

    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    placeholder_failures = [
        label
        for label in payload["failures"]
        if label.startswith("prd_placeholder_")
    ]
    assert placeholder_failures == []
    assert payload["prd_missing"] is False
    assert payload["prd_placeholder_hits"] == []


def test_plan_checker_ignores_substring_match_of_placeholder_token(tmp_path: Path):
    # Spec: prd.md § F3 — bullet 5: whole-word boundary. `TODOIST` contains
    # `TODO` as a substring but must not trigger the scan.
    pipeline = write_pipeline(tmp_path, _passing_pipeline())
    write_prd(
        tmp_path,
        "# PRD\n\n## Integration\n\nTODOIST integration plan goes here.\n",
    )

    result = run_checker(pipeline)

    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    placeholder_failures = [
        label
        for label in payload["failures"]
        if label.startswith("prd_placeholder_")
    ]
    assert placeholder_failures == []
    assert payload["prd_missing"] is False
    assert payload["prd_placeholder_hits"] == []


def test_plan_checker_passes_when_prd_missing(tmp_path: Path):
    # Spec: prd.md § F2 — PRD-absent case must not fail the gate. Payload
    # carries ``prd_missing: true`` and no ``prd_placeholder_*`` entries.
    pipeline = write_pipeline(tmp_path, _passing_pipeline())
    # Deliberately do NOT call write_prd — no context/prd.md on disk.

    result = run_checker(pipeline)

    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["prd_missing"] is True
    placeholder_failures = [
        label
        for label in payload["failures"]
        if label.startswith("prd_placeholder_")
    ]
    assert placeholder_failures == []


def test_plan_checker_reports_multiple_distinct_placeholder_tokens(tmp_path: Path):
    # Spec: prd.md § F3 — bullet 7: one failure label per distinct token type
    # detected. TBD and FIXME on different lines → both labels present.
    pipeline = write_pipeline(tmp_path, _passing_pipeline())
    write_prd(
        tmp_path,
        "# PRD\n\n## Open items\n\nTBD\n\nFIXME\n",
    )

    result = run_checker(pipeline)

    assert result.returncode == 1, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert "prd_placeholder_tbd" in payload["failures"]
    assert "prd_placeholder_fixme" in payload["failures"]
