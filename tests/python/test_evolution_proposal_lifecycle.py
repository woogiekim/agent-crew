"""Lifecycle command coverage for explicit self-evolution proposal handling."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
CREW = REPO_ROOT / "core" / "bin" / "crew"


def _write_proposals(state_dir: Path, proposals: list[dict]) -> Path:
    path = state_dir / "learning-candidates" / "proposals.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"schema_version": 1, "proposals": proposals}, indent=2) + "\n",
        encoding="utf-8",
    )
    return path


def test_lifecycle_status_reads_only_existing_proposals(script_runner, env_with_home, state_dir):
    _write_proposals(state_dir, [{
        "candidate_id": "review-fix-verifier-2x",
        "proposal_type": "create_agent",
        "status": "approval_required",
        "asset_name": "review-fix-verifier",
        "promotion_reason": "2 independent learning events recorded the same pattern.",
        "occurrence_count": 2,
    }])

    result = script_runner(
        "evolution-proposal-lifecycle.py",
        "--state-dir", str(state_dir),
        "status",
        env=env_with_home,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "SELF_EVOLUTION_PROPOSALS: 1 pending" in result.stdout
    assert "review-fix-verifier-2x" in result.stdout
    assert "type: create_agent" in result.stdout
    assert "target: review-fix-verifier" in result.stdout
    assert "evolution-proposal-aggregate" not in result.stdout + result.stderr
    assert not (state_dir / "learning-candidates" / "agent-maker-requests").exists()


def test_lifecycle_status_missing_file_is_fast_zero(script_runner, env_with_home, state_dir):
    result = script_runner(
        "evolution-proposal-lifecycle.py",
        "--state-dir", str(state_dir),
        "status",
        env=env_with_home,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "SELF_EVOLUTION_PROPOSALS: 0 pending" in result.stdout


def test_lifecycle_approve_updates_one_candidate_idempotently(script_runner, env_with_home, state_dir):
    proposals_path = _write_proposals(state_dir, [
        {
            "candidate_id": "target-2x",
            "proposal_type": "create_skill",
            "status": "approval_required",
            "asset_name": "target-skill",
        },
        {
            "candidate_id": "other-2x",
            "proposal_type": "create_skill",
            "status": "approval_required",
            "asset_name": "other-skill",
        },
    ])

    first = script_runner(
        "evolution-proposal-lifecycle.py",
        "--state-dir", str(state_dir),
        "approve", "target-2x",
        "--approved-by", "tester",
        "--reason", "operator approved",
        env=env_with_home,
    )
    second = script_runner(
        "evolution-proposal-lifecycle.py",
        "--state-dir", str(state_dir),
        "approve", "target-2x",
        "--approved-by", "tester",
        env=env_with_home,
    )

    assert first.returncode == 0, first.stdout + first.stderr
    assert second.returncode == 0, second.stdout + second.stderr
    payload = json.loads(proposals_path.read_text(encoding="utf-8"))
    target = payload["proposals"][0]
    other = payload["proposals"][1]
    assert target["status"] == "approved"
    assert target["approved_by"] == "tester"
    assert target["decision_reason"] == "operator approved"
    assert "approved_at" in target
    assert other["status"] == "approval_required"
    assert "already approved" in second.stdout


def test_lifecycle_approve_rejects_terminal_state(script_runner, env_with_home, state_dir):
    _write_proposals(state_dir, [{
        "candidate_id": "rejected-2x",
        "proposal_type": "create_skill",
        "status": "rejected",
    }])

    result = script_runner(
        "evolution-proposal-lifecycle.py",
        "--state-dir", str(state_dir),
        "approve", "rejected-2x",
        env=env_with_home,
    )

    assert result.returncode == 2
    assert "cannot approve proposal in status rejected" in result.stderr


def test_lifecycle_apply_requires_approval_and_creates_agent_maker_request(
    script_runner,
    env_with_home,
    state_dir,
    tmp_path: Path,
):
    skill_dir = tmp_path / "skills"
    skill_dir.mkdir()
    _write_proposals(state_dir, [
        {
            "candidate_id": "new-agent-2x",
            "proposal_type": "create_agent",
            "status": "approved",
            "asset_name": "review-fix-verifier",
            "asset_purpose": "Verify repeated review-fix evidence.",
            "evidence_refs": ["tasks/one/context/evolution-report.json"],
        },
        {
            "candidate_id": "not-approved-2x",
            "proposal_type": "create_agent",
            "status": "approval_required",
            "asset_name": "must-not-apply",
        },
    ])

    rejected = script_runner(
        "evolution-proposal-lifecycle.py",
        "--state-dir", str(state_dir),
        "--skill-dir", str(skill_dir),
        "apply", "not-approved-2x",
        env=env_with_home,
    )
    applied = script_runner(
        "evolution-proposal-lifecycle.py",
        "--state-dir", str(state_dir),
        "--skill-dir", str(skill_dir),
        "apply", "new-agent-2x",
        env=env_with_home,
    )

    assert rejected.returncode == 2
    assert "proposal must be approved before apply" in rejected.stderr
    assert applied.returncode == 0, applied.stdout + applied.stderr
    request = state_dir / "learning-candidates" / "agent-maker-requests" / "new-agent-2x.md"
    assert request.is_file()
    assert "crew:agent-maker" in request.read_text(encoding="utf-8")
    assert "NEXT: crew:agent-maker" in applied.stdout
    audit = json.loads((state_dir / "learning-candidates" / "apply-audit.json").read_text(encoding="utf-8"))
    assert audit["applied"][0]["status"] == "agent_maker_request_created"


def test_native_crew_evolve_dispatches_lifecycle_script(tmp_path: Path):
    home = tmp_path / "home"
    state_dir = home / "state" / "repo"
    (state_dir / "learning-candidates").mkdir(parents=True)
    (state_dir / "session.json").write_text(
        json.dumps({"schema_version": 1, "session_id": "s", "status": "completed", "tasks": []}),
        encoding="utf-8",
    )
    (state_dir / "capabilities.json").write_text(
        json.dumps({"schema_version": 1, "host": "test"}),
        encoding="utf-8",
    )
    env = os.environ.copy()
    env["AGENT_CREW_HOME"] = str(home)
    env["AGENT_CREW_STATE_DIR"] = str(state_dir)
    env["AGENT_CREW_AUTO_SYNC_RUNTIME_ON_RUN"] = "0"
    env["AGENT_CREW_AUTO_SYNC_HOOKS_ON_RUN"] = "0"
    env["AGENT_CREW_PROJECT"] = "repo"

    result = subprocess.run(
        [str(CREW), "evolve", "status"],
        text=True,
        capture_output=True,
        cwd=str(REPO_ROOT),
        env=env,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "SELF_EVOLUTION_PROPOSALS: 0 pending" in result.stdout
