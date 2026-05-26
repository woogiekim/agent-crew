"""Shared pytest fixtures for the agent-crew test suite.

All tests must be hermetic — never touch the real ${HOME}/.agent-crew/.
Use the `agent_crew_home`, `state_dir`, and `task_dir` fixtures which
provide tmp_path-based isolation.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = REPO_ROOT / "core" / "scripts"
SCHEMAS_DIR = REPO_ROOT / "core" / "schemas"
COVERAGE_STARTUP_DIR = REPO_ROOT / "tests" / "coverage-startup"


def _prepend_env_path(env: dict[str, str], key: str, values: list[Path]) -> None:
    existing = [item for item in env.get(key, "").split(os.pathsep) if item]
    additions = [str(value) for value in values if str(value) not in existing]
    env[key] = os.pathsep.join([*additions, *existing])


def configure_subprocess_coverage(env: dict[str, str]) -> dict[str, str]:
    """Attach coverage startup settings to child Python processes when enabled."""
    if os.environ.get("AGENT_CREW_SUBPROCESS_COVERAGE") != "1":
        return env

    try:
        import coverage  # type: ignore
    except ModuleNotFoundError:
        return env

    coverage_site = Path(coverage.__file__).resolve().parent.parent
    env["COVERAGE_PROCESS_START"] = str(REPO_ROOT / ".coveragerc")
    _prepend_env_path(env, "PYTHONPATH", [COVERAGE_STARTUP_DIR, coverage_site])
    return env


configure_subprocess_coverage(os.environ)


@pytest.fixture
def repo_root() -> Path:
    """Absolute path to the agent-crew repo root."""
    return REPO_ROOT


@pytest.fixture
def scripts_dir() -> Path:
    """Absolute path to core/scripts/."""
    return SCRIPTS_DIR


@pytest.fixture
def schemas_dir() -> Path:
    """Absolute path to core/schemas/ (used by validate-state-schema.py)."""
    return SCHEMAS_DIR


@pytest.fixture
def agent_crew_home(tmp_path: Path) -> Path:
    """Hermetic AGENT_CREW_HOME with schemas linked from the repo.

    Layout matches what `validate-state-schema.py` expects:
      {home}/schemas/*.schema.json
      {home}/state/{project}/...
    """
    home = tmp_path / "agent-crew-home"
    home.mkdir()
    # Copy schemas so the validator can find them without env contamination
    schemas_dst = home / "schemas"
    schemas_dst.mkdir()
    if SCHEMAS_DIR.is_dir():
        for f in SCHEMAS_DIR.iterdir():
            if f.suffix == ".json":
                shutil.copy(f, schemas_dst / f.name)
    return home


@pytest.fixture
def state_dir(agent_crew_home: Path) -> Path:
    """Hermetic STATE_DIR with tasks/ subdir and valid project-level files.

    Seeds minimum-viable session.json and capabilities.json so the schema
    validator's project-level checks pass cleanly. Individual tests that
    need to corrupt either file may overwrite them.
    """
    project = "testproj"
    sd = agent_crew_home / "state" / project
    (sd / "tasks").mkdir(parents=True)
    (sd / "cost").mkdir(parents=True)

    # Valid minimal session.json (schema requires session_id, status, tasks)
    (sd / "session.json").write_text(json.dumps({
        "schema_version": 1,
        "session_id": "20260101-120000",
        "status": "completed",
        "tasks": [],
    }))
    # Valid minimal capabilities.json (schema requires host)
    (sd / "capabilities.json").write_text(json.dumps({
        "schema_version": 1,
        "host": "test",
        "task_tools": False,
        "agent_background": False,
        "monitor_tool": False,
        "cost_tracking": False,
    }))
    return sd


@pytest.fixture
def task_dir(state_dir: Path) -> Path:
    """A fresh task dir under state_dir/tasks/."""
    td = state_dir / "tasks" / "20260101-120000-0"
    (td / "context").mkdir(parents=True)
    return td


@pytest.fixture
def env_with_home(agent_crew_home: Path, state_dir: Path) -> dict:
    """Environment dict pointing all path env vars at the hermetic dirs."""
    env = os.environ.copy()
    env["AGENT_CREW_HOME"] = str(agent_crew_home)
    env["AGENT_CREW_STATE_DIR"] = str(state_dir)
    env["AGENT_CREW_PROJECT"] = state_dir.name
    # Make sure nothing inherits a stale budget setting
    for k in list(env.keys()):
        if k.startswith("AGENT_CREW_BUDGET_"):
            del env[k]
    env["AGENT_CREW_STALE_HOST_BRIDGE_SECONDS"] = "0"
    return env


def run_script(script_name: str, *args: str, env: dict | None = None,
               input_text: str | None = None,
               cwd: Path | None = None) -> subprocess.CompletedProcess:
    """Run a script under core/scripts/ and capture its output.

    Returns the CompletedProcess (do NOT check=True so tests can assert
    on non-zero exit codes themselves).
    """
    path = SCRIPTS_DIR / script_name
    if script_name.endswith(".py"):
        cmd = [sys.executable, str(path), *args]
    else:
        cmd = ["bash", str(path), *args]
    child_env = env if env is not None else os.environ.copy()
    configure_subprocess_coverage(child_env)
    return subprocess.run(
        cmd,
        env=child_env,
        input=input_text,
        capture_output=True,
        text=True,
        cwd=str(cwd) if cwd else None,
    )


@pytest.fixture
def script_runner():
    """Callable to invoke any script under core/scripts/."""
    return run_script
