from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / 'core/scripts/ensure-project-initialized.sh'
PROJECT_STATE = REPO_ROOT / 'core/scripts/project_state.py'
CREW = REPO_ROOT / 'core/bin/crew'


def make_home(tmp_path: Path) -> tuple[Path, Path, dict[str, str]]:
    home = tmp_path / 'agent-crew-home'
    project = tmp_path / 'project'
    (home / 'scripts').mkdir(parents=True)
    (home / 'setup').mkdir()
    project.mkdir()
    (home / 'scripts/project_state.py').write_bytes(PROJECT_STATE.read_bytes())
    (home / 'scripts/ensure-project-initialized.sh').write_bytes(SCRIPT.read_bytes())
    (home / 'setup/setup-host.sh').write_text(
        '#!/bin/bash\nprintf called > "${AGENT_CREW_HOME}/setup-called"\nexit 91\n'
    )
    env = os.environ.copy()
    for name in tuple(env):
        if name.startswith(('AGENT_CREW_', 'CODEX_', 'CLAUDE_')) or name in {'STATE_DIR', 'PROJECT_STATE_KEY'}:
            env.pop(name)
    env.update(
        AGENT_CREW_HOME=str(home), PROJECT_ROOT=str(project),
        HOME=str(tmp_path / 'user-home'), CODEX_HOME=str(tmp_path / 'user-home/.codex'),
        CLAUDE_DIR=str(tmp_path / 'user-home/.claude'),
        AGENT_CREW_AUTO_SYNC_RUNTIME_ON_RUN='0', AGENT_CREW_AUTO_SYNC_HOOKS_ON_RUN='0',
        AGENT_CREW_HOST_BRIDGE_DISABLE_DEFAULT='1',
    )
    return home, project, env


def state_dir(home: Path, project: Path) -> Path:
    root = project.resolve()
    slug = re.sub(r'[^A-Za-z0-9._-]+', '-', root.name.strip()).strip('.-').lower()
    digest = hashlib.sha256(str(root).encode()).hexdigest()[:10]
    return home / 'state' / f'{slug}-{digest}'


def run_initializer(env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(['bash', str(SCRIPT)], env=env, text=True, capture_output=True, check=False)


def run_cli(env: dict[str, str], *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(['bash', str(CREW), *args], env=env, cwd=env['PROJECT_ROOT'],
                          text=True, capture_output=True, check=False)


def test_success_case_new_project_initializes_runtime_only_and_is_idempotent(tmp_path: Path):
    home, project, env = make_home(tmp_path)

    for _ in range(2):
        result = run_initializer(env)
        assert result.returncode == 0, result.stderr

    state = state_dir(home, project)
    assert json.loads((state / 'project.json').read_text())['project_root'] == str(project)
    assert (state / 'tasks').is_dir()
    assert not (state / 'capabilities.json').exists()
    assert not (home / 'setup-called').exists()
    assert not list(project.iterdir())


@pytest.mark.parametrize('existing_capabilities', [None, '{"host":"claude"}'])
def test_boundary_case_existing_runtime_state_is_preserved(tmp_path: Path, existing_capabilities):
    home, project, env = make_home(tmp_path)
    state = state_dir(home, project)
    task = state / 'tasks/task-1'
    task.mkdir(parents=True)
    preserved = {state / 'session.json': '{"status":"running"}',
                 task / 'approval.json': '{"approved":true}',
                 state / 'user-note.md': '사용자 메모'}
    if existing_capabilities is not None:
        preserved[state / 'capabilities.json'] = existing_capabilities
    for path, body in preserved.items():
        path.write_text(body)

    result = run_initializer(env)

    assert result.returncode == 0, result.stderr
    assert {path: path.read_text() for path in preserved} == preserved
    assert not (home / 'setup-called').exists()


@pytest.mark.parametrize('list_sessions_first', [False, True])
def test_success_case_cli_run_without_setup_preserves_raw_input(tmp_path: Path, list_sessions_first: bool):
    home, project, env = make_home(tmp_path)
    if list_sessions_first:
        listed = run_cli(env, 'sessions')
        assert listed.returncode == 0, listed.stderr

        initialized = run_initializer(env)
        assert initialized.returncode == 0, initialized.stderr
    prompt = '로컬 분석\n`literal` $HOME "인용" $(literal)'
    run = run_cli(env, 'run', prompt)

    assert run.returncode == 0, run.stderr
    assert 'STATUS: handoff_ready' in run.stdout
    state = state_dir(home, project)
    registers = list((state / 'tasks').glob('*/register.json'))
    assert len(registers) == 1
    assert json.loads(registers[0].read_text())['task'] == prompt
    assert not (home / 'setup-called').exists()
    assert not (state / 'capabilities.json').exists()
    assert not list(project.iterdir())


@pytest.mark.parametrize('damage', ['state-file', 'invalid-metadata', 'foreign-owner'])
@pytest.mark.parametrize('entry', ['helper', 'cli'])
def test_failure_case_damaged_state_stops_before_overwriting(tmp_path: Path, damage: str, entry: str):
    home, project, env = make_home(tmp_path)
    state = state_dir(home, project)
    state.parent.mkdir(parents=True)
    if damage == 'state-file':
        state.write_text('보존할 파일')
        preserved = state
    else:
        state.mkdir()
        preserved = state / 'project.json'
        preserved.write_text('{invalid' if damage == 'invalid-metadata' else
                             json.dumps({'project_root': str(tmp_path / 'other')}))
    original = preserved.read_bytes()

    result = run_initializer(env) if entry == 'helper' else run_cli(env, 'run', 'read docs')

    assert result.returncode != 0
    assert 'project-state:' in result.stderr
    assert str(state) in result.stderr
    assert preserved.read_bytes() == original
    assert not (state / 'tasks').exists()
    assert not (home / 'setup-called').exists()


def test_success_case_concurrent_initialization_and_same_basename_isolation(tmp_path: Path):
    home, first, env = make_home(tmp_path)
    second = tmp_path / 'other/project'
    second.mkdir(parents=True)
    envs = [dict(env, PROJECT_ROOT=str(project)) for project in [first, second] for _ in range(4)]

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(run_initializer, envs))

    assert all(result.returncode == 0 for result in results), [r.stderr for r in results]
    assert state_dir(home, first) != state_dir(home, second)
    for project in (first, second):
        state = state_dir(home, project)
        assert json.loads((state / 'project.json').read_text())['project_root'] == str(project)
        assert (state / 'tasks').is_dir()
    assert not (home / 'setup-called').exists()


@pytest.mark.parametrize('phase', ['pre-injection', 'state-paths'])
def test_success_case_run_documented_initialization_accepts_lazy_state(tmp_path: Path, phase: str):
    home, project, env = make_home(tmp_path)
    state = state_dir(home, project)
    state.mkdir(parents=True)
    document = (REPO_ROOT / 'core/commands/run.md').read_text()
    if phase == 'pre-injection':
        section = document.split('#### Live session detection\n', 1)[1].split('A session is injectable only', 1)[0]
    else:
        section = document.split('### 2. Initialize State Paths\n', 1)[1].split('### 3.', 1)[0]
    blocks = re.findall(r'```bash\n(.*?)```', section, re.S)

    result = subprocess.run(['bash', '-euc', '\n'.join(blocks)], cwd=project, env=env,
                            text=True, capture_output=True)

    assert result.returncode == 0, result.stderr
    assert not (home / 'setup-called').exists()
    assert 'Run crew:setup' not in section
    assert 'setup/setup-host.sh' not in section


@pytest.mark.parametrize('phase', ['pre-injection', 'supervisor'])
@pytest.mark.parametrize('host_env', [{'AGENT_CREW_HOST': 'codex'}, {'CODEX_THREAD_ID': 'test-thread'}])
@pytest.mark.parametrize('stored_host, expected', [('claude', '0 0'), ('codex', '1 1')])
def test_boundary_case_capability_consumers_ignore_other_hosts_without_setup(
    tmp_path: Path, phase: str, host_env: dict[str, str], stored_host: str, expected: str,
):
    home, project, env = make_home(tmp_path)
    env.update(host_env)
    state = state_dir(home, project)
    state.mkdir(parents=True)
    caps = state / 'capabilities.json'
    original = json.dumps({'host': stored_host, 'task_tools': True, 'agent_background': True})
    caps.write_text(original)
    if phase == 'pre-injection':
        document = (REPO_ROOT / 'core/commands/run.md').read_text()
        marker = 'read -r HAS_AGENT_BACKGROUND HAS_TASK_TOOLS'
    else:
        document = (REPO_ROOT / 'core/agents/supervisor-bootstrap.md').read_text()
        marker = 'read -r HAS_TASK_TOOLS HAS_AGENT_BACKGROUND'
    blocks = re.findall(r'```bash\n(.*?)```', document, re.S)
    block = next(block for block in blocks if marker in block)
    env.update(STATE_DIR=str(state), CAPABILITIES_PATH=str(caps))

    result = subprocess.run(['bash', '-euc', block + '\nprintf "%s %s" "$HAS_TASK_TOOLS" "$HAS_AGENT_BACKGROUND"'],
                            env=env, cwd=project, text=True, capture_output=True)

    assert result.returncode == 0, result.stderr
    assert result.stdout == expected
    assert caps.read_text() == original
    assert not (home / 'setup-called').exists()
