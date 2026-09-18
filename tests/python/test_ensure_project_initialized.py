from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "core" / "scripts" / "ensure-project-initialized.sh"
PROJECT_STATE = REPO_ROOT / "core" / "scripts" / "project_state.py"


def make_home(tmp_path: Path) -> tuple[Path, Path, Path]:
    home = tmp_path / "agent-crew-home"
    project = tmp_path / "project"
    calls = tmp_path / "setup-calls"
    (home / "scripts").mkdir(parents=True)
    (home / "setup").mkdir()
    project.mkdir()
    (home / "scripts" / "project_state.py").write_bytes(PROJECT_STATE.read_bytes())
    setup = home / "setup" / "setup-host.sh"
    setup.write_text(
        """#!/usr/bin/env bash
set -euo pipefail
printf '%s\n' "$1" >> "${SETUP_CALLS}"
eval "$(python3 \"${AGENT_CREW_HOME}/scripts/project_state.py\" resolve --agent-crew-home \"${AGENT_CREW_HOME}\" --project-root \"$1\" --ensure --format shell)"
printf '{\"host\":\"test\"}\n' > "${STATE_DIR}/capabilities.json"
""",
        encoding="utf-8",
    )
    setup.chmod(0o755)
    return home, project, calls


def run_initializer(home: Path, project: Path, calls: Path) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.update({"AGENT_CREW_HOME": str(home), "PROJECT_ROOT": str(project), "SETUP_CALLS": str(calls)})
    return subprocess.run(["bash", str(SCRIPT)], env=env, text=True, capture_output=True, check=False)


def state_dir(home: Path, project: Path) -> Path:
    result = subprocess.run(
        [
            "python3",
            str(home / "scripts" / "project_state.py"),
            "resolve",
            "--agent-crew-home",
            str(home),
            "--project-root",
            str(project),
            "--format",
            "json",
        ],
        text=True,
        capture_output=True,
        check=True,
    )
    return Path(json.loads(result.stdout)["state_dir"])


def test_absent_project_state_is_initialized_once(tmp_path: Path):
    home, project, calls = make_home(tmp_path)

    first = run_initializer(home, project, calls)
    second = run_initializer(home, project, calls)

    assert first.returncode == 0, first.stderr
    assert second.returncode == 0, second.stderr
    assert calls.read_text(encoding="utf-8").splitlines() == [str(project)]
    assert (state_dir(home, project) / "tasks").is_dir()


def test_existing_partial_state_is_not_repaired_implicitly(tmp_path: Path):
    home, project, calls = make_home(tmp_path)
    partial_state = state_dir(home, project)
    partial_state.mkdir(parents=True)

    result = run_initializer(home, project, calls)

    assert result.returncode != 0
    assert "Run crew:setup" in result.stderr
    assert not calls.exists()
