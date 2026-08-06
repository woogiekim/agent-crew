"""Tests for derived skill coverage diagnostics.

Skill coverage is diagnostic state. These tests intentionally avoid requiring
new proof files; the summary must derive from existing task context files.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
REPAIR = REPO_ROOT / "core" / "scripts" / "repair-task-state.py"
SMM = REPO_ROOT / "core" / "scripts" / "smm-aggregate.py"
COVERAGE = REPO_ROOT / "core" / "scripts" / "skill_coverage_lib.py"


def _load_module(path: Path, name: str):
    script_dir = str(path.parent)
    if script_dir in sys.path:
        sys.path.remove(script_dir)
    sys.path.insert(0, script_dir)
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _write_task(state_dir: Path, task_id: str = "20260806-000000-0") -> Path:
    task_dir = state_dir / "tasks" / task_id
    (task_dir / "context").mkdir(parents=True)
    (task_dir / "register.json").write_text(
        json.dumps({
            "task": "Implement a current-session fallback diagnostic change",
            "current_phase": "handoff_ready",
            "host_bridge_status": "current_session_required",
            "blocked_by": [],
        }) + "\n",
        encoding="utf-8",
    )
    (task_dir / "pipeline.json").write_text(
        json.dumps({"stages": ["supervisor"], "completed_stages": 0}) + "\n",
        encoding="utf-8",
    )
    (task_dir / "context" / "specialist-dispatch.md").write_text(
        "selected_agent: backend\n"
        "selected_skills:\n"
        "- tdd\n"
        "- effective-java\n"
        "selection_reason: current-session fallback diagnostic change\n"
        "execution_mode: current_session_required fallback\n",
        encoding="utf-8",
    )
    (task_dir / "context" / "skill-load.md").write_text(
        "loaded_skills:\n"
        "- /Users/wook/.agent-crew/system/agents/skills/tdd.md\n"
        "- /Users/wook/.agent-crew/system/skills/effective-java.md\n",
        encoding="utf-8",
    )
    (task_dir / "context" / "tdd_log.md").write_text(
        "RED: focused test failed before implementation.\n"
        "GREEN: focused test passed after implementation.\n",
        encoding="utf-8",
    )
    (task_dir / "context" / "review.md").write_text(
        "REVIEW: APPROVED\n",
        encoding="utf-8",
    )
    (task_dir / "result.md").write_text("STATUS: handoff_ready\n", encoding="utf-8")
    return task_dir


def _repair(state_dir: Path, task_id: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "python3",
            str(REPAIR),
            "--state-dir",
            str(state_dir),
            "--status",
            "completed",
            "--quality-bypass-reason",
            "unit test isolates skill coverage diagnostics",
            task_id,
        ],
        text=True,
        capture_output=True,
    )


def test_skill_coverage_derives_used_only_from_observed_signals(tmp_path: Path):
    state_dir = tmp_path / "state"
    task_dir = _write_task(state_dir)
    coverage = _load_module(COVERAGE, "skill_coverage_lib")

    summary = coverage.build_skill_coverage(task_dir)

    assert [row["name"] for row in summary["selected_skills"]] == [
        "effective-java.md",
        "tdd.md",
    ]
    assert [row["name"] for row in summary["loaded_skills"]] == [
        "effective-java.md",
        "tdd.md",
    ]
    assert summary["used_skills"] == [{
        "name": "tdd.md",
        "source": "context/tdd_log.md",
        "confidence": "derived",
    }]
    assert summary["unknown_or_not_observed"] == [{
        "name": "effective-java.md",
        "reason": "selected_or_loaded_but_no_deterministic_usage_signal",
    }]
    assert summary["advisory_gap"] is True


def test_skill_coverage_uses_complete_markdown_skill_use_evidence(tmp_path: Path):
    state_dir = tmp_path / "state"
    task_dir = _write_task(state_dir)
    (task_dir / "context" / "tdd_log.md").unlink()
    (task_dir / "context" / "skill-use.md").write_text(
        "SKILL_USE: diagnostic\n\n"
        "- skill_path: /Users/wook/.agent-crew/system/skills/effective-java.md\n"
        "- applied_rules: review finding semantic parity\n"
        "- evidence_refs: core/scripts/skill_coverage_lib.py\n"
        "- output_files: core/scripts/skill_coverage_lib.py\n"
        "- verification: python3 -m pytest --no-cov tests/python/test_skill_coverage_summary.py -q\n",
        encoding="utf-8",
    )
    coverage = _load_module(COVERAGE, "skill_coverage_markdown_skill_use")

    summary = coverage.build_skill_coverage(task_dir)

    assert summary["used_skills"] == [{
        "name": "effective-java.md",
        "source": "context/skill-use.md",
        "confidence": "derived",
    }]
    assert summary["unknown_or_not_observed"] == [{
        "name": "tdd.md",
        "reason": "selected_or_loaded_but_no_deterministic_usage_signal",
    }]


def test_skill_coverage_does_not_use_incomplete_markdown_skill_use_evidence(tmp_path: Path):
    state_dir = tmp_path / "state"
    task_dir = _write_task(state_dir)
    (task_dir / "context" / "tdd_log.md").unlink()
    (task_dir / "context" / "skill-use.md").write_text(
        "SKILL_USE: diagnostic\n\n"
        "- skill_path: /Users/wook/.agent-crew/system/skills/effective-java.md\n"
        "- applied_rules: review finding semantic parity\n",
        encoding="utf-8",
    )
    coverage = _load_module(COVERAGE, "skill_coverage_incomplete_markdown_skill_use")

    summary = coverage.build_skill_coverage(task_dir)

    assert summary["used_skills"] == []
    assert [row["name"] for row in summary["unknown_or_not_observed"]] == [
        "effective-java.md",
        "tdd.md",
    ]


def test_smm_renders_markdown_skill_use_evidence_as_observed(tmp_path: Path):
    state_dir = tmp_path / "state"
    task_dir = _write_task(state_dir)
    (task_dir / "context" / "tdd_log.md").unlink()
    (task_dir / "context" / "skill-use.md").write_text(
        "SKILL_USE: diagnostic\n\n"
        "- skill_path: /Users/wook/.agent-crew/system/agents/skills/tdd.md\n"
        "- applied_rules: Red Green Refactor\n"
        "- evidence_refs: context/tdd_log.md\n"
        "- output_files: tests/python/test_skill_coverage_summary.py\n"
        "- verification: python3 -m pytest --no-cov tests/python/test_skill_coverage_summary.py -q\n",
        encoding="utf-8",
    )
    smm = _load_module(SMM, "smm_aggregate_markdown_skill_use")

    payload = smm.build_smm(state_dir, task_dir)
    skills = payload["orchestration"]["skills"]
    out = smm.render_text([payload])

    assert skills["used_observed"] == 1
    assert skills["unknown_or_not_observed"] == 1
    assert "Skills: selected=2 loaded=2 used_observed=1 unknown_or_not_observed=1" in out


def test_repair_record_preserves_markdown_selected_skills_and_adds_coverage(tmp_path: Path):
    state_dir = tmp_path / "state"
    task_id = "20260806-000000-0"
    task_dir = _write_task(state_dir, task_id)

    result = _repair(state_dir, task_id)

    assert result.returncode == 0, result.stdout + result.stderr
    repair = json.loads((task_dir / "context" / "manual-fallback-repair.json").read_text(encoding="utf-8"))
    assert repair["specialist_dispatch_gate"]["selected_skills"] == [
        "effective-java",
        "tdd",
    ]
    assert repair["skill_coverage"]["selected"] == 2
    assert repair["skill_coverage"]["loaded"] == 2
    assert repair["skill_coverage"]["used_observed"] == 1
    assert repair["skill_coverage"]["unknown_or_not_observed"] == 1
    result_text = (task_dir / "result.md").read_text(encoding="utf-8")
    assert "SKILL_COVERAGE: selected=2 loaded=2 used_observed=1 unknown_or_not_observed=1 advisory_gap=yes" in result_text


def test_smm_renders_skill_coverage_without_conflating_loaded_and_used(tmp_path: Path):
    state_dir = tmp_path / "state"
    task_dir = _write_task(state_dir)
    smm = _load_module(SMM, "smm_aggregate_for_skill_coverage")

    payload = smm.build_smm(state_dir, task_dir)
    skills = payload["orchestration"]["skills"]
    out = smm.render_text([payload])

    assert skills["selected"] == 2
    assert skills["loaded"] == 2
    assert skills["used_observed"] == 1
    assert skills["unknown_or_not_observed"] == 1
    assert skills["advisory_gap"] is True
    assert "Skills: selected=2 loaded=2 used_observed=1 unknown_or_not_observed=1 advisory_gap=yes" in out


def test_skill_coverage_reports_unknown_selected_set_without_inventing_candidates(tmp_path: Path):
    state_dir = tmp_path / "state"
    task_dir = _write_task(state_dir)
    (task_dir / "context" / "specialist-dispatch.md").unlink()
    coverage = _load_module(COVERAGE, "skill_coverage_unknown_selected")

    summary = coverage.build_skill_coverage(task_dir)

    assert summary["selected_source"] == "unknown"
    assert summary["selected_skills"] == []
    assert summary["selected"] == 0
    assert summary["loaded"] == 2
    assert summary["advisory_gap"] is True
