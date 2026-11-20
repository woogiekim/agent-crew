"""Regression coverage for user-facing crew repair help text."""

from __future__ import annotations

import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CREW_BIN = REPO_ROOT / "core" / "bin" / "crew"


def test_crew_repair_help_describes_skill_notes_as_advisory() -> None:
    result = subprocess.run(
        ["bash", str(CREW_BIN), "repair", "--help"],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    compact = " ".join(result.stdout.split())
    assert "Specialist dispatch, skill-load, capability handler, skill-use, and skill-understanding files are diagnostic coverage sources" in compact
    assert "advisory gaps rather than completion blockers" in compact
    assert "--evidence may attach optional extra references" in compact
    assert "skill-use plus skill-understanding evidence for loaded non-TDD skills" not in compact
    assert "skill-load evidence proving which agent-crew skills were loaded" not in compact


def repair_install(tmp_path, *, installation_name="crew"):
    import os
    import shutil
    crew_home = tmp_path / installation_name
    for name in ['system/scripts', 'scripts', 'bin', 'commands']:
        (crew_home / name).mkdir(parents=True)
    for src in (REPO_ROOT / 'core/scripts').glob('*.py'):
        shutil.copy2(src, crew_home / 'system/scripts' / src.name)
    shutil.copy2(REPO_ROOT / 'core/scripts/repair-task-state.py', crew_home / 'scripts/repair-task-state.py')
    shutil.copy2(CREW_BIN, crew_home / 'bin/crew')
    (crew_home / 'scripts/quality_loop_lib.py').write_text('def check_quality_loop(*args, **kwargs): return {}\n')
    env = dict(os.environ, AGENT_CREW_HOME=str(crew_home), HOME=str(tmp_path), PYTHONDONTWRITEBYTECODE='1')
    return crew_home, env


def test_success_case_discovery_repair_uses_canonical_system_bundle(tmp_path):
    """success-case(regression) - stale discovery에도 실제 Python help가 canonical bundle로 실행된다."""
    import sys
    crew_home, env = repair_install(tmp_path)

    result = subprocess.run([sys.executable, str(crew_home / 'scripts/repair-task-state.py'), '--help'],
                            cwd=tmp_path, env=env, capture_output=True, text=True)

    assert result.returncode == 0, 'canonical Python help 진입 실패'
    assert '--state-dir' in result.stdout


import pytest


@pytest.mark.parametrize('entry', ['discovery', 'cli'])
@pytest.mark.parametrize('damage', ['none', 'missing', 'api', 'import'])
def test_boundary_case_canonical_repair_entry_fails_closed(tmp_path, entry, damage):
    """boundary-case(contract) - 임의 CWD 진입과 파손된 canonical 실패를 구분한다."""
    import sys
    crew_home, env = repair_install(tmp_path)
    canonical = crew_home / 'system/scripts'
    if damage == 'missing':
        (canonical / 'repair-task-state.py').unlink()
    if damage == 'api':
        (canonical / 'quality_loop_lib.py').write_text('def check_quality_loop(*args, **kwargs): return {}\n')
    if damage == 'import':
        (canonical / 'quality_loop_lib.py').write_text('raise RuntimeError("canonical broken")\n')
    argv = [sys.executable, str(crew_home / 'scripts/repair-task-state.py'), '--help']
    if entry == 'cli':
        argv = ['bash', str(crew_home / 'bin/crew'), 'repair', '--status', 'completed', '--help']

    result = subprocess.run(argv, cwd=tmp_path, env=env, capture_output=True, text=True)

    assert (result.returncode == 0) is (damage == 'none')
    if damage == 'none':
        assert '--state-dir' in result.stdout
        invalid = subprocess.run(argv[:-1] + ['--no-such-argument'], cwd=tmp_path, env=env, capture_output=True, text=True)
        assert invalid.returncode == 2


def test_success_case_repair_preserves_dirty_source_and_installed_assets(tmp_path):
    """success-case(side-effect) - repair Python 진입은 dirty source를 설치에 복사하지 않는다."""
    crew_home, env = repair_install(tmp_path)
    dirty = tmp_path / 'dirty'
    (dirty / 'core/scripts').mkdir(parents=True)
    (dirty / 'adapters').mkdir()
    marker = tmp_path / 'autosync-called'
    (dirty / 'core/scripts/crew-runtime.py').write_text('# dirty runtime\n')
    (dirty / 'core/scripts/sync-local-install.sh').write_text('touch ' + str(marker) + '\n')
    (crew_home / 'source.path').write_text(str(dirty))
    paths = list(crew_home.rglob('*')) + list(dirty.rglob('*'))
    before = {str(path): path.read_bytes() for path in paths if path.is_file()}

    result = subprocess.run(['bash', str(crew_home / 'bin/crew'), 'repair', '--status', 'completed', '--help'],
                            cwd=tmp_path, env=env, capture_output=True, text=True)

    assert result.returncode == 0, result.stderr
    assert not marker.exists()
    assert all(Path(name).read_bytes() == content for name, content in before.items())


@pytest.mark.parametrize('installation_name', ['crew', 'core', 'system'])
@pytest.mark.parametrize('entry', ['discovery', 'cli'])
@pytest.mark.parametrize('damage', ['none', 'missing'])
def test_boundary_case_repair_root_names_use_canonical_bundle(tmp_path, installation_name, entry, damage):
    """boundary-case(regression) - 설치 root 이름과 무관하게 canonical bundle만 실행한다."""
    import shutil
    import sys
    crew_home, env = repair_install(tmp_path, installation_name=installation_name)
    if damage == 'missing':
        for source in (crew_home / 'system/scripts').glob('*.py'):
            shutil.copy2(source, crew_home / 'scripts' / source.name)
        (crew_home / 'system/scripts/repair-task-state.py').unlink()
    argv = [sys.executable, str(crew_home / 'scripts/repair-task-state.py'), '--help']
    if entry == 'cli':
        argv = ['bash', str(crew_home / 'bin/crew'), 'repair', '--status', 'completed', '--help']

    result = subprocess.run(argv, cwd=tmp_path, env=env, capture_output=True, text=True)

    assert (result.returncode == 0) is (damage == 'none')
    if damage == 'none':
        assert '--state-dir' in result.stdout
