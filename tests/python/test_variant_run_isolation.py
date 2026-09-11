"""새 variants run은 collector 잠금과 세션별 산출물 경계를 지킨다."""
import json
import os
from pathlib import Path
import subprocess

from tests.python.test_variant_review_inputs import ROOT, v2, git


def run(base, home):
    return subprocess.run(
        ["bash", str(ROOT / "core/bin/crew"), "run", "--variants", "2", "implement"],
        cwd=base, env={**os.environ, "AGENT_CREW_HOME": str(home), "PROJECT_ROOT": str(base),
                       "AGENT_CREW_AUTO_SYNC_RUNTIME_ON_RUN": "0", "AGENT_CREW_AUTO_SYNC_HOOKS_ON_RUN": "0"},
        text=True, capture_output=True)


def test_new_run_respects_lock_and_does_not_overwrite_live_session(v2, tmp_path):
    base = v2[0]
    home = tmp_path / "home"
    first = run(base, home)
    assert first.returncode == 0, first.stderr
    path = next(home.rglob("session.json"))
    before = path.read_bytes()
    refs = git(base, "worktree", "list", "--porcelain")
    lock = path.parent / ".variants.lock"
    lock.mkdir()
    try:
        second = run(base, home)
        assert second.returncode != 0
        assert path.read_bytes() == before
        assert git(base, "worktree", "list", "--porcelain") == refs
    finally:
        lock.rmdir()
    second = run(base, home)
    assert second.returncode != 0
    assert "resume" in second.stdout + second.stderr
    assert path.read_bytes() == before


def test_new_completed_session_keeps_prior_receipts(v2, tmp_path):
    base = v2[0]
    home = tmp_path / "home"
    assert run(base, home).returncode == 0
    path = next(home.rglob("session.json"))
    previous = json.loads(path.read_text())
    artifacts = Path(previous["variants_dir"])
    evidence = artifacts / "variant-review-state.json"
    evidence.write_text('{"status":"completed","proof":"previous"}\n')
    previous["status"] = "completed"
    path.write_text(json.dumps(previous))
    second = run(base, home)
    assert second.returncode == 0, second.stderr
    current = json.loads(path.read_text())
    assert current["variants_dir"] != previous["variants_dir"]
    assert evidence.read_text() == '{"status":"completed","proof":"previous"}\n'
    assert json.loads((artifacts / "session.json").read_text()) == previous
    assert not (Path(current["variants_dir"]) / "variant-review-state.json").exists()


def test_archive_failure_preserves_previous_root_session(v2, tmp_path):
    base = v2[0]
    home = tmp_path / "home"
    assert run(base, home).returncode == 0
    path = next(home.rglob("session.json"))
    previous = json.loads(path.read_text())
    previous["status"] = "completed"
    path.write_text(json.dumps(previous))
    (Path(previous["variants_dir"]) / "session.json").mkdir()
    before = path.read_bytes()
    assert run(base, home).returncode != 0
    assert path.read_bytes() == before
