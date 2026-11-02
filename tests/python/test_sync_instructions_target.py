"""명시적인 단일 호스트 목적지의 보존·멱등성 계약."""
import os
from pathlib import Path
import subprocess

SCRIPT = Path(__file__).resolve().parents[2] / "core/scripts/sync-instructions.sh"


def test_success_case_target_preserves_tail_and_is_idempotent(tmp_path):
    stub = tmp_path / "mnemos"
    stub.write_text(r"""#!/usr/bin/env python3
import json,sys
if sys.argv[1]=='capabilities': print(json.dumps({'capabilities':{'read_json':True}}))
elif sys.argv[1]=='list': print('[global] rule:test:')
elif sys.argv[1]=='read': print(json.dumps({'tags':['instruction-rule'],'content':'---\\ntitle: Codex rule\\napplies_to: [codex]\\n---\\nCanonical rule.\\n'.replace('\\n','\n')}))
""")
    stub.chmod(0o755)
    target = tmp_path / "AGENTS.md"
    original = "intro\n<!-- agent-crew-start -->\nold\n<!-- agent-crew-end -->\nunique tail\n"
    target.write_text(original)
    env = dict(os.environ, MNEMOS_BIN=str(stub))
    args = ["bash", str(SCRIPT), "--hosts", "codex", "--target-file", str(target)]

    dry = subprocess.run(args, env=env, capture_output=True, text=True)

    assert dry.returncode == 3, dry.stdout + dry.stderr
    assert target.read_text() == original
    first = subprocess.run(args + ["--apply"], env=env, capture_output=True, text=True)
    assert first.returncode == 0, first.stdout + first.stderr
    assert "Canonical rule." in target.read_text()
    assert target.read_text().startswith("intro\n")
    assert target.read_text().endswith("unique tail\n")
    snapshot = target.read_bytes(), target.stat().st_mtime_ns
    second = subprocess.run(args + ["--apply"], env=env, capture_output=True, text=True)
    assert second.returncode == 0, second.stdout + second.stderr
    assert (target.read_bytes(), target.stat().st_mtime_ns) == snapshot


def test_failure_case_target_rejects_ambiguous_or_unsafe_destination(tmp_path):
    link = tmp_path / "link.md"
    link.symlink_to(tmp_path / "destination.md")
    cases = [
        ("codex,generic", str(tmp_path / "a")),
        ("repo", str(tmp_path / "a")),
        ("codex", "relative.md"),
        ("codex", str(link)),
        ("codex", str(tmp_path)),
        ("codex", str(tmp_path / "absent" / "a.md")),
    ]
    for hosts, target in cases:
        result = subprocess.run(["bash", str(SCRIPT), "--hosts", hosts, "--target-file", target], capture_output=True, text=True)
        assert result.returncode == 2

def test_failure_case_empty_target_is_rejected_before_provider_access(tmp_path):
    result = subprocess.run(
        ["bash", str(SCRIPT), "--target-file", "", "--apply"],
        env=dict(os.environ, MNEMOS_BIN=str(tmp_path / "missing-provider")),
        capture_output=True, text=True,
    )

    assert result.returncode == 2
