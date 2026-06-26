"""Agent-maker must create skills that agent-crew can actually dispatch."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
AGENT_MAKER = REPO_ROOT / "core" / "commands" / "agent-maker.md"
DEPLOY_USER_SKILL = REPO_ROOT / "core" / "setup" / "deploy-user-skill.sh"
COMMON_SH = REPO_ROOT / "core" / "setup" / "common.sh"


def test_agent_maker_skill_template_declares_dispatch_metadata() -> None:
    text = AGENT_MAKER.read_text(encoding="utf-8")

    assert "loaded_by:" in text
    assert "axis:" in text
    assert "detection:" in text
    assert "capability-skills-<agent-name>.json" in text
    assert "decision_context" in text
    assert "skill-use.json` proof" in text
    assert "~/.codex/agent-crew/skills/" in text
    assert "Copies skill to `~/.codex/skills/`" not in text


def test_deploy_user_skill_refreshes_unified_and_codex_internal_mirror(
    tmp_path: Path,
) -> None:
    home = tmp_path / "home"
    agent_crew_home = home / ".agent-crew"
    setup_dir = agent_crew_home / "setup"
    user_skills = agent_crew_home / "user" / "skills"
    system_skills = agent_crew_home / "system" / "skills"
    codex_agents = home / ".codex" / "agents"
    native_codex_skills = home / ".codex" / "skills"
    codex_crew_skills = home / ".codex" / "agent-crew" / "skills"

    setup_dir.mkdir(parents=True)
    user_skills.mkdir(parents=True)
    system_skills.mkdir(parents=True)
    codex_agents.mkdir(parents=True)
    native_codex_skills.mkdir(parents=True)
    shutil.copy(COMMON_SH, setup_dir / "common.sh")
    (system_skills / "custom-skill.md").write_text("system copy\n", encoding="utf-8")
    (user_skills / "custom-skill.md").write_text("user copy\n", encoding="utf-8")

    result = subprocess.run(
        ["bash", str(DEPLOY_USER_SKILL), "custom-skill.md"],
        cwd=tmp_path,
        env={
            **os.environ,
            "HOME": str(home),
            "AGENT_CREW_HOME": str(agent_crew_home),
        },
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert (agent_crew_home / "skills" / "custom-skill.md").read_text(
        encoding="utf-8"
    ) == "user copy\n"
    assert (codex_crew_skills / "custom-skill.md").read_text(
        encoding="utf-8"
    ) == "user copy\n"
    assert not (native_codex_skills / "custom-skill.md").exists()
