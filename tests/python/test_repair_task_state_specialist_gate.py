"""Tests for specialist-dispatch evidence on manual Codex fallback repair."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPT = REPO_ROOT / "core" / "scripts" / "repair-task-state.py"
RUN_COMMAND = REPO_ROOT / "core" / "commands" / "run.md"
SCRIPTS_DIR = REPO_ROOT / "core" / "scripts"

if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


repair_state = _load_module(SCRIPT, "repair_task_state_specialist_gate")


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


def test_repair_reports_missing_specialist_dispatch_as_advisory_gap(tmp_path: Path):
    state_dir = tmp_path / "state"
    task_id = "20260604-000000-0"
    task_dir = _write_task(state_dir, task_id)

    result = _repair(
        state_dir,
        task_id,
        "--skill-load-bypass-reason",
        "isolate specialist dispatch advisory coverage",
    )

    assert result.returncode == 0, result.stdout + result.stderr
    repair = json.loads((task_dir / "context" / "manual-fallback-repair.json").read_text(encoding="utf-8"))
    gate = repair["specialist_dispatch_gate"]
    assert gate["passed"] is False
    assert gate["advisory"] is True
    assert gate["missing_fields"] == ["selected_agent", "selection_reason", "execution_mode"]
    assert "SPECIALIST_DISPATCH: advisory" in (task_dir / "result.md").read_text(encoding="utf-8")


def test_repair_reports_incomplete_specialist_dispatch_as_advisory_gap(tmp_path: Path):
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

    assert result.returncode == 0, result.stdout + result.stderr
    repair = json.loads((task_dir / "context" / "manual-fallback-repair.json").read_text(encoding="utf-8"))
    gate = repair["specialist_dispatch_gate"]
    assert gate["passed"] is False
    assert gate["advisory"] is True
    assert gate["incomplete_paths"] == {
        "context/specialist-dispatch.md": ["execution_mode", "selected_agent", "selection_reason"]
    }


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


def test_commit_current_session_repair_reports_missing_git_handler_as_advisory_gap(tmp_path: Path):
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

    assert result.returncode == 0, result.stdout + result.stderr
    repair = json.loads((task_dir / "context" / "manual-fallback-repair.json").read_text(encoding="utf-8"))
    gate = repair["required_capability_gate"]
    assert gate["passed"] is False
    assert gate["advisory"] is True
    assert "vcs.commit.message.compose" in gate["missing_capabilities"]
    assert "vcs.history.local_mutation" in gate["missing_capabilities"]


def test_required_capability_inference_ignores_negative_remote_constraints():
    capabilities = repair_state.required_capabilities_for_task(
        "Implement the quality coverage change. Do not push, merge, deploy, or perform remote operations."
    )

    assert capabilities == []


def test_required_capability_inference_ignores_high_risk_gate_references():
    capabilities = repair_state.required_capabilities_for_task(
        "Improve the quality-loop checker and preserve hard gates for high-risk actions such as push, merge, deploy, destructive operations, and auto-completion."
    )

    assert capabilities == []


def test_required_capability_inference_preserves_commit_without_push_or_deploy():
    capabilities = repair_state.required_capabilities_for_task(
        "Commit local changes without pushing or deploying."
    )

    assert "vcs.commit.message.compose" in capabilities
    assert "vcs.history.local_mutation" in capabilities
    assert "vcs.remote_mutation" not in capabilities
    assert "deployment.mutate" not in capabilities


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


def test_required_capability_gate_reports_selected_handlers_without_completion_as_advisory(tmp_path: Path):
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

    assert result.returncode == 0, result.stdout + result.stderr
    repair = json.loads((task_dir / "context" / "manual-fallback-repair.json").read_text(encoding="utf-8"))
    gate = repair["required_capability_gate"]
    assert gate["passed"] is False
    assert gate["advisory"] is True
    assert gate["missing_completion_capabilities"] == [
        "vcs.commit.message.compose",
        "vcs.history.local_mutation",
    ]


def test_required_capability_gate_reports_non_completed_handler_results_as_advisory(tmp_path: Path):
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

    assert result.returncode == 0, result.stdout + result.stderr
    repair = json.loads((task_dir / "context" / "manual-fallback-repair.json").read_text(encoding="utf-8"))
    gate = repair["required_capability_gate"]
    assert gate["passed"] is False
    assert gate["advisory"] is True
    assert gate["missing_completion_capabilities"] == ["vcs.commit.message.compose"]


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


def test_normalization_current_session_repair_reports_unsatisfied_required_capabilities_as_advisory(tmp_path: Path):
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

    assert result.returncode == 0, result.stdout + result.stderr
    repair = json.loads((task_dir / "context" / "manual-fallback-repair.json").read_text(encoding="utf-8"))
    gate = repair["required_capability_gate"]
    assert gate["passed"] is False
    assert gate["advisory"] is True
    assert "vcs.commit.message.compose" in gate["missing_capabilities"]


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
