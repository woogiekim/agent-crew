"""Tests for specialist-dispatch evidence on manual Codex fallback repair."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPT = REPO_ROOT / "core" / "scripts" / "repair-task-state.py"
RUN_COMMAND = REPO_ROOT / "core" / "commands" / "run.md"


def _write_task(
    state_dir: Path,
    task_id: str = "20260604-000000-0",
    task: str = "Implement a small change",
    project_root: Path | None = None,
) -> Path:
    task_dir = state_dir / "tasks" / task_id
    task_dir.mkdir(parents=True)
    (task_dir / "context").mkdir()
    root = project_root or state_dir.parent / "project"
    (task_dir / "register.json").write_text(
        json.dumps(
            {
                "task": task,
                "project_root": str(root),
                "current_phase": "handoff_ready",
                "host_bridge_status": "current_session_required",
                "blocked_by": [],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (task_dir / "pipeline.json").write_text(
        json.dumps({"stages": ["supervisor"], "completed_stages": 0}) + "\n",
        encoding="utf-8",
    )
    (task_dir / "result.md").write_text("STATUS: handoff_ready\n", encoding="utf-8")
    return task_dir


def _install_git_committer(project_root: Path) -> None:
    agent_dir = project_root / ".agent-crew" / "agents"
    agent_dir.mkdir(parents=True)
    (agent_dir / "git-committer.md").write_text(
        "# git-committer\n",
        encoding="utf-8",
    )


def _write_capability_result(task_dir: Path, capability: str, handler: str) -> Path:
    path = task_dir / "context" / "capabilities" / f"{capability}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "capability": capability,
                "handler": handler,
                "state": "completed",
                "artifact": f"context/capabilities/{capability}.json",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def _repair(state_dir: Path, task_id: str, *extra: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "python3",
            str(SCRIPT),
            "--state-dir",
            str(state_dir),
            "--status",
            "completed",
            "--quality-bypass-reason",
            "unit test bypasses quality-loop evidence to isolate specialist dispatch gate",
            *extra,
            task_id,
        ],
        text=True,
        capture_output=True,
    )


def test_repair_blocks_mutating_current_session_without_specialist_evidence(tmp_path: Path):
    state_dir = tmp_path / "state"
    task_id = "20260604-000000-0"
    _write_task(state_dir, task_id)

    result = _repair(state_dir, task_id)

    assert result.returncode != 0
    assert "BLOCKER: missing_specialist_dispatch_evidence" in result.stderr
    assert "specialist agent and agent-skill selection" in result.stderr


def test_repair_blocks_incomplete_specialist_dispatch_evidence(tmp_path: Path):
    state_dir = tmp_path / "state"
    task_id = "20260604-000000-0"
    task_dir = _write_task(state_dir, task_id)
    (task_dir / "context" / "specialist-dispatch.md").write_text(
        "selected_skill: frontend-typescript-react\n",
        encoding="utf-8",
    )

    result = _repair(
        state_dir,
        task_id,
        "--skill-load-bypass-reason",
        "isolate specialist dispatch shape",
    )

    assert result.returncode != 0
    assert "BLOCKER: incomplete_specialist_dispatch_evidence" in result.stderr
    assert "selected_agent" in result.stderr
    assert "selection_reason" in result.stderr
    assert "execution_mode" in result.stderr


def test_repair_accepts_specialist_dispatch_evidence(tmp_path: Path):
    state_dir = tmp_path / "state"
    task_id = "20260604-000000-0"
    task_dir = _write_task(state_dir, task_id)
    (task_dir / "context" / "specialist-dispatch.md").write_text(
        "\n".join(
            [
                "selected_agent: frontend",
                "selected_skill: frontend-typescript-react",
                "selection_reason: UI implementation task",
                "execution_mode: current_session_required fallback",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (task_dir / "context" / "skill-load.md").write_text(
        "SKILL_LOAD: passed\n"
        "Loaded before implementation:\n"
        "- ~/.agent-crew/user/skills/frontend-typescript-react.md\n",
        encoding="utf-8",
    )
    (task_dir / "context" / "skill-plan.json").write_text(
        json.dumps(
            {
                "skills": [
                    {
                        "skill_path": "~/.agent-crew/user/skills/frontend-typescript-react.md",
                        "rules": [
                            {
                                "rule_id": "component-contract",
                                "task_interpretation": "Preserve the UI specialist contract in repair evidence.",
                                "planned_application": "Record frontend skill understanding for the pass fixture.",
                            }
                        ],
                    }
                ]
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (task_dir / "context" / "skill-use.json").write_text(
        json.dumps(
            {
                "skills": [
                    {
                        "skill_path": "~/.agent-crew/user/skills/frontend-typescript-react.md",
                        "applied_rules": ["component contract applied"],
                        "evidence_refs": ["tests/python/test_repair_task_state_specialist_gate.py"],
                        "output_files": ["tests/python/test_repair_task_state_specialist_gate.py"],
                        "verification": ["python3 -m pytest tests/python/test_repair_task_state_specialist_gate.py -q"],
                        "rule_evidence": [
                            {
                                "rule_id": "component-contract",
                                "artifact_refs": ["tests/python/test_repair_task_state_specialist_gate.py"],
                                "diff_refs": ["tests/python/test_repair_task_state_specialist_gate.py"],
                                "verification": [
                                    "python3 -m pytest tests/python/test_repair_task_state_specialist_gate.py -q"
                                ],
                                "adversarial_checks": ["confirmed dispatch evidence still drives specialist gate"],
                                "reviewer_status": "approved",
                            }
                        ],
                    }
                ]
            }
        )
        + "\n",
        encoding="utf-8",
    )
    result = _repair(state_dir, task_id)

    assert result.returncode == 0
    repair = json.loads((task_dir / "context" / "manual-fallback-repair.json").read_text(encoding="utf-8"))
    assert repair["specialist_dispatch_gate"]["passed"] is True
    assert repair["specialist_dispatch_gate"]["matched_paths"] == ["context/specialist-dispatch.md"]
    assert repair["skill_load_gate"]["passed"] is True


def test_repair_preserves_user_agent_and_subagent_dispatch_axes(tmp_path: Path):
    state_dir = tmp_path / "state"
    task_id = "20260604-000000-0"
    task_dir = _write_task(state_dir, task_id)
    (task_dir / "context" / "specialist-dispatch.md").write_text(
        "\n".join(
            [
                "selected_agent: backend",
                "selected_user_agent: kotlin-domain-specialist",
                "selected_subagents: test-writer, reviewer",
                "selected_skill: backend-kotlin-spring",
                "selection_reason: backend Kotlin implementation with custom domain reviewer",
                "execution_mode: current_session_required fallback",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    result = _repair(
        state_dir,
        task_id,
        "--quality-bypass-reason",
        "isolate specialist dispatch axis serialization",
        "--skill-load-bypass-reason",
        "isolate specialist dispatch axis serialization",
    )

    assert result.returncode == 0, result.stdout + result.stderr
    repair = json.loads((task_dir / "context" / "manual-fallback-repair.json").read_text(encoding="utf-8"))
    gate = repair["specialist_dispatch_gate"]
    assert gate["selected_agents"] == ["backend"]
    assert gate["selected_user_agents"] == ["kotlin-domain-specialist"]
    assert gate["selected_subagents"] == ["reviewer", "test-writer"]
    assert gate["selected_skills"] == ["backend-kotlin-spring"]
    result_text = (task_dir / "result.md").read_text(encoding="utf-8")
    assert "SPECIALIST_AGENT: backend" in result_text
    assert "SPECIALIST_USER_AGENT: kotlin-domain-specialist" in result_text
    assert "SPECIALIST_SUBAGENT: reviewer" in result_text
    assert "SPECIALIST_SUBAGENT: test-writer" in result_text
    assert "SPECIALIST_SKILL: backend-kotlin-spring" in result_text


def test_repair_accepts_json_specialist_dispatch_axes(tmp_path: Path):
    state_dir = tmp_path / "state"
    task_id = "20260604-000000-0"
    task_dir = _write_task(state_dir, task_id)
    (task_dir / "context" / "specialist-dispatch.md").unlink(missing_ok=True)
    (task_dir / "context" / "specialist-dispatch.json").write_text(
        json.dumps(
            {
                "selected_agent": "backend",
                "selected_user_agent": ["domain-reviewer"],
                "selected_subagents": ["test-writer", "reviewer"],
                "selected_skills": ["backend-kotlin-spring"],
                "selection_reason": "backend change with custom review specialist",
                "execution_mode": "current_session_required fallback",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    result = _repair(
        state_dir,
        task_id,
        "--quality-bypass-reason",
        "isolate JSON specialist dispatch parsing",
        "--skill-load-bypass-reason",
        "isolate JSON specialist dispatch parsing",
    )

    assert result.returncode == 0, result.stdout + result.stderr
    repair = json.loads((task_dir / "context" / "manual-fallback-repair.json").read_text(encoding="utf-8"))
    gate = repair["specialist_dispatch_gate"]
    assert gate["matched_paths"] == ["context/specialist-dispatch.json"]
    assert gate["selected_user_agents"] == ["domain-reviewer"]
    assert gate["selected_subagents"] == ["reviewer", "test-writer"]


def test_commit_current_session_repair_blocks_without_git_committer_user_agent(tmp_path: Path):
    state_dir = tmp_path / "state"
    project_root = tmp_path / "project"
    _install_git_committer(project_root)
    task_id = "20260604-000000-0"
    task_dir = _write_task(
        state_dir,
        task_id,
        task="Commit local changes",
        project_root=project_root,
    )
    (task_dir / "context" / "specialist-dispatch.md").write_text(
        "\n".join(
            [
                "selected_agent: backend",
                "selected_skill: tdd",
                "selection_reason: implementation finished and user requested commit",
                "execution_mode: current_session_required fallback",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    result = _repair(
        state_dir,
        task_id,
        "--skill-load-bypass-reason",
        "isolate commit capability dispatch gate",
    )

    assert result.returncode != 0
    assert "BLOCKER: missing_required_capability_evidence" in result.stderr
    assert "vcs.commit.message.compose" in result.stderr


def test_commit_current_session_repair_translates_legacy_user_agent_to_capability_handlers(tmp_path: Path):
    state_dir = tmp_path / "state"
    project_root = tmp_path / "project"
    _install_git_committer(project_root)
    task_id = "20260604-000000-0"
    task_dir = _write_task(
        state_dir,
        task_id,
        task="Commit local changes",
        project_root=project_root,
    )
    (task_dir / "context" / "specialist-dispatch.md").write_text(
        "\n".join(
            [
                "selected_agent: backend",
                "selected_user_agent: git-committer",
                "selected_skill: tdd",
                "selection_reason: legacy commit request evidence must translate before mutating git history",
                "execution_mode: current_session_required fallback",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (task_dir / "context" / "skill-load.md").write_text(
        "SKILL_LOAD: passed\n"
        "Loaded before implementation:\n"
        "- ~/.agent-crew/system/agents/skills/tdd.md\n",
        encoding="utf-8",
    )
    _write_capability_result(task_dir, "vcs.commit.message.compose", "git-committer")
    _write_capability_result(task_dir, "vcs.history.local_mutation", "git-committer")

    result = _repair(state_dir, task_id)

    assert result.returncode == 0, result.stdout + result.stderr
    repair = json.loads((task_dir / "context" / "manual-fallback-repair.json").read_text(encoding="utf-8"))
    gate = repair["required_capability_gate"]
    assert gate["required"] is True
    assert gate["passed"] is True
    assert gate["selected_handlers"]["vcs.commit.message.compose"] == ["git-committer"]
    assert gate["selected_handlers"]["vcs.history.local_mutation"] == ["git-committer"]
    assert gate["completed_handlers"]["vcs.commit.message.compose"] == ["git-committer"]
    assert gate["completed_handlers"]["vcs.history.local_mutation"] == ["git-committer"]


def test_required_capability_gate_blocks_selected_handlers_without_completion(tmp_path: Path):
    state_dir = tmp_path / "state"
    project_root = tmp_path / "project"
    _install_git_committer(project_root)
    task_id = "20260604-000000-0"
    task_dir = _write_task(
        state_dir,
        task_id,
        task="Normalize raw user input into a canonical English agent-crew workflow instruction",
        project_root=project_root,
    )
    (task_dir / "context" / "input-normalization.json").write_text(
        json.dumps(
            {
                "required_capabilities": [
                    "vcs.commit.message.compose",
                    "vcs.history.local_mutation",
                ],
                "raw_input_ref": "handoff.md#RAW_TASK",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (task_dir / "context" / "specialist-dispatch.json").write_text(
        json.dumps(
            {
                "selected_agent": "supervisor",
                "selected_handlers": [
                    {
                        "capability": "vcs.commit.message.compose",
                        "handler": "commit-message-specialist",
                    },
                    {
                        "capability": "vcs.history.local_mutation",
                        "handler": "local-git",
                    },
                ],
                "selection_reason": "capability handlers satisfy the required abstractions",
                "execution_mode": "current_session_required fallback",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    result = _repair(state_dir, task_id)

    assert result.returncode != 0
    assert "BLOCKER: missing_required_capability_completion_evidence" in result.stderr
    assert "vcs.commit.message.compose" in result.stderr
    assert "vcs.history.local_mutation" in result.stderr


def test_required_capability_gate_rejects_non_completed_handler_results(tmp_path: Path):
    state_dir = tmp_path / "state"
    project_root = tmp_path / "project"
    _install_git_committer(project_root)
    task_id = "20260604-000000-0"
    task_dir = _write_task(
        state_dir,
        task_id,
        task="Normalize raw user input into a canonical English agent-crew workflow instruction",
        project_root=project_root,
    )
    (task_dir / "context" / "input-normalization.json").write_text(
        json.dumps(
            {
                "required_capabilities": [
                    "vcs.commit.message.compose",
                ],
                "raw_input_ref": "handoff.md#RAW_TASK",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (task_dir / "context" / "specialist-dispatch.json").write_text(
        json.dumps(
            {
                "selected_agent": "supervisor",
                "selected_handlers": [
                    {
                        "capability": "vcs.commit.message.compose",
                        "handler": "commit-message-specialist",
                    },
                ],
                "selection_reason": "capability handler selected",
                "execution_mode": "current_session_required fallback",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (task_dir / "context" / "handler-results.json").write_text(
        json.dumps(
            {
                "handler_results": [
                    {
                        "capability": "vcs.commit.message.compose",
                        "handler": "commit-message-specialist",
                        "state": "failed",
                    }
                ]
            }
        )
        + "\n",
        encoding="utf-8",
    )

    result = _repair(state_dir, task_id)

    assert result.returncode != 0
    assert "BLOCKER: missing_required_capability_completion_evidence" in result.stderr
    assert "vcs.commit.message.compose" in result.stderr


def test_required_capability_gate_accepts_completed_abstract_handler_names(tmp_path: Path):
    state_dir = tmp_path / "state"
    project_root = tmp_path / "project"
    _install_git_committer(project_root)
    task_id = "20260604-000000-0"
    task_dir = _write_task(
        state_dir,
        task_id,
        task="Normalize raw user input into a canonical English agent-crew workflow instruction",
        project_root=project_root,
    )
    (task_dir / "context" / "input-normalization.json").write_text(
        json.dumps(
            {
                "required_capabilities": [
                    "vcs.commit.message.compose",
                    "vcs.history.local_mutation",
                ],
                "raw_input_ref": "handoff.md#RAW_TASK",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (task_dir / "context" / "specialist-dispatch.json").write_text(
        json.dumps(
            {
                "selected_agent": "supervisor",
                "selected_handlers": [
                    {
                        "capability": "vcs.commit.message.compose",
                        "handler": "commit-message-specialist",
                    },
                    {
                        "capability": "vcs.history.local_mutation",
                        "handler": "local-git",
                    },
                ],
                "selection_reason": "capability handlers satisfy the required abstractions",
                "execution_mode": "current_session_required fallback",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    _write_capability_result(task_dir, "vcs.commit.message.compose", "commit-message-specialist")
    _write_capability_result(task_dir, "vcs.history.local_mutation", "local-git")

    result = _repair(state_dir, task_id)

    assert result.returncode == 0, result.stdout + result.stderr
    repair = json.loads((task_dir / "context" / "manual-fallback-repair.json").read_text(encoding="utf-8"))
    gate = repair["required_capability_gate"]
    assert gate["passed"] is True
    assert gate["selected_handlers"]["vcs.commit.message.compose"] == ["commit-message-specialist"]
    assert gate["selected_handlers"]["vcs.history.local_mutation"] == ["local-git"]
    assert gate["completed_handlers"]["vcs.commit.message.compose"] == ["commit-message-specialist"]
    assert gate["completed_handlers"]["vcs.history.local_mutation"] == ["local-git"]


def test_required_capability_policy_has_no_concrete_git_committer_branch():
    source = SCRIPT.read_text(encoding="utf-8")
    policy_body = source.split("def capability_satisfied", 1)[1].split("\ndef ", 1)[0]

    assert "git-committer" not in policy_body
    assert "selected_user_agents" not in policy_body


def test_normalization_current_session_repair_blocks_unsatisfied_required_capabilities(tmp_path: Path):
    state_dir = tmp_path / "state"
    project_root = tmp_path / "project"
    _install_git_committer(project_root)
    task_id = "20260604-000000-0"
    task_dir = _write_task(
        state_dir,
        task_id,
        task="Normalize raw user input into a canonical English agent-crew workflow instruction",
        project_root=project_root,
    )
    (task_dir / "context" / "input-normalization.json").write_text(
        json.dumps(
            {
                "required_capabilities": [
                    "vcs.commit.message.compose",
                    "vcs.history.local_mutation",
                ],
                "raw_input_ref": "handoff.md#RAW_TASK",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (task_dir / "context" / "specialist-dispatch.json").write_text(
        json.dumps(
            {
                "selected_agent": "supervisor",
                "selection_reason": "normalization handoff still carries downstream mutation capabilities",
                "execution_mode": "current_session_required fallback",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    result = _repair(state_dir, task_id)

    assert result.returncode != 0
    assert "BLOCKER: missing_required_capability_evidence" in result.stderr
    assert "vcs.commit.message.compose" in result.stderr


def test_normalization_current_session_repair_accepts_selected_capability_handlers(tmp_path: Path):
    state_dir = tmp_path / "state"
    project_root = tmp_path / "project"
    _install_git_committer(project_root)
    task_id = "20260604-000000-0"
    task_dir = _write_task(
        state_dir,
        task_id,
        task="Normalize raw user input into a canonical English agent-crew workflow instruction",
        project_root=project_root,
    )
    (task_dir / "context" / "input-normalization.json").write_text(
        json.dumps(
            {
                "required_capabilities": [
                    "vcs.commit.message.compose",
                    "vcs.history.local_mutation",
                ],
                "raw_input_ref": "handoff.md#RAW_TASK",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (task_dir / "context" / "specialist-dispatch.json").write_text(
        json.dumps(
            {
                "selected_agent": "supervisor",
                "selected_handlers": [
                    {
                        "capability": "vcs.commit.message.compose",
                        "handler": "git-committer",
                    },
                    {
                        "capability": "vcs.history.local_mutation",
                        "handler": "git",
                    },
                ],
                "selection_reason": "normalization handoff carries downstream mutation capabilities",
                "execution_mode": "current_session_required fallback",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    _write_capability_result(task_dir, "vcs.commit.message.compose", "git-committer")
    _write_capability_result(task_dir, "vcs.history.local_mutation", "git")

    result = _repair(state_dir, task_id)

    assert result.returncode == 0, result.stdout + result.stderr
    repair = json.loads((task_dir / "context" / "manual-fallback-repair.json").read_text(encoding="utf-8"))
    gate = repair["required_capability_gate"]
    assert gate["passed"] is True
    assert gate["selected_handlers"]["vcs.commit.message.compose"] == ["git-committer"]
    assert gate["selected_handlers"]["vcs.history.local_mutation"] == ["git"]
    assert gate["completed_handlers"]["vcs.commit.message.compose"] == ["git-committer"]
    assert gate["completed_handlers"]["vcs.history.local_mutation"] == ["git"]


def test_normalization_current_session_repair_accepts_markdown_selected_handlers(tmp_path: Path):
    state_dir = tmp_path / "state"
    project_root = tmp_path / "project"
    _install_git_committer(project_root)
    task_id = "20260604-000000-0"
    task_dir = _write_task(
        state_dir,
        task_id,
        task="Normalize raw user input into a canonical English agent-crew workflow instruction",
        project_root=project_root,
    )
    (task_dir / "context" / "input-normalization.json").write_text(
        json.dumps(
            {
                "required_capabilities": [
                    "vcs.commit.message.compose",
                    "vcs.history.local_mutation",
                ],
                "raw_input_ref": "handoff.md#RAW_TASK",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (task_dir / "context" / "specialist-dispatch.md").write_text(
        "\n".join(
            [
                "selected_agent: supervisor",
                "selected_handler: vcs.commit.message.compose=git-committer",
                "selected_handler: vcs.history.local_mutation=git",
                "selection_reason: normalization handoff carries downstream mutation capabilities",
                "execution_mode: current_session_required fallback",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    _write_capability_result(task_dir, "vcs.commit.message.compose", "git-committer")
    _write_capability_result(task_dir, "vcs.history.local_mutation", "git")

    result = _repair(state_dir, task_id)

    assert result.returncode == 0, result.stdout + result.stderr
    repair = json.loads((task_dir / "context" / "manual-fallback-repair.json").read_text(encoding="utf-8"))
    gate = repair["required_capability_gate"]
    assert gate["passed"] is True
    assert gate["selected_handlers"]["vcs.commit.message.compose"] == ["git-committer"]
    assert gate["selected_handlers"]["vcs.history.local_mutation"] == ["git"]
    assert gate["completed_handlers"]["vcs.commit.message.compose"] == ["git-committer"]
    assert gate["completed_handlers"]["vcs.history.local_mutation"] == ["git"]


def test_run_commit_fast_path_delegates_to_git_committer_not_direct_shell_commit():
    command_doc = RUN_COMMAND.read_text(encoding="utf-8")
    commit_section = command_doc.split("##### `commit_only`", 1)[1].split("##### Destructive intents", 1)[0]

    assert 'git commit -m "${COMMIT_MSG}"' not in commit_section
    assert "git-committer" in commit_section
    assert "selected_handler: vcs.commit.message.compose=git-committer" in commit_section
    assert "selected_user_agent: git-committer" not in commit_section
