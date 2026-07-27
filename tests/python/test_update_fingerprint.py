"""Tests for update fingerprint fast-path diagnostics."""
from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPT = REPO_ROOT / "core" / "scripts" / "update-fingerprint.py"


def load_update_fingerprint_module():
    spec = importlib.util.spec_from_file_location("update_fingerprint", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _make_checkout(root: Path) -> None:
    for rel in (
        "core/commands",
        "core/user",
        "core/rules",
        "core/hooks",
        "core/scripts",
        "core/evaluations",
        "core/schemas",
        "core/policies",
        "core/setup",
        "core/agents",
        "core/bin",
        "adapters",
    ):
        (root / rel).mkdir(parents=True)
    (root / "core" / "commands" / "run.md").write_text("run\n", encoding="utf-8")
    (root / "core" / "bin" / "crew").write_text(
        "# deterministic shell entrypoint for agent-crew\n",
        encoding="utf-8",
    )


def _run(tmp_path: Path, *extra: str) -> subprocess.CompletedProcess[str]:
    source = tmp_path / "source"
    project = tmp_path / "project"
    home = tmp_path / "home" / ".agent-crew"
    codex = tmp_path / "home" / ".codex"
    claude = tmp_path / "home" / ".claude"
    path_bin = tmp_path / "home" / ".local" / "bin"
    project.mkdir(exist_ok=True)
    return subprocess.run(
        [
            "python3",
            str(SCRIPT),
            "--source-root",
            str(source),
            "--project-root",
            str(project),
            "--agent-crew-home",
            str(home),
            "--codex-home",
            str(codex),
            "--claude-dir",
            str(claude),
            "--path-bin",
            str(path_bin),
            "--fingerprint",
            str(home / "state" / "project" / "update-fingerprint.json"),
            *extra,
        ],
        text=True,
        capture_output=True,
    )


def test_update_fingerprint_explains_missing_previous(tmp_path: Path):
    source = tmp_path / "source"
    _make_checkout(source)

    result = _run(tmp_path)

    assert result.returncode == 0
    assert "no previous fingerprint" in result.stdout


def test_update_fingerprint_reports_changed_categories(tmp_path: Path):
    source = tmp_path / "source"
    _make_checkout(source)
    write = _run(tmp_path, "--write")
    assert write.returncode == 0, write.stdout + write.stderr
    (source / "core" / "commands" / "run.md").write_text("changed\n", encoding="utf-8")

    result = _run(tmp_path, "--format", "json")

    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["matched"] is False
    assert payload["diff"]["changed"] == 1
    assert payload["diff"]["changed_categories"] == [
        {"category": "source/core", "count": 1}
    ]


def test_update_fingerprint_text_reports_changed_categories(tmp_path: Path):
    source = tmp_path / "source"
    _make_checkout(source)
    write = _run(tmp_path, "--write")
    assert write.returncode == 0, write.stdout + write.stderr
    (source / "core" / "commands" / "run.md").write_text("changed\n", encoding="utf-8")

    result = _run(tmp_path)

    assert result.returncode == 0
    assert "changed=1, added=0, removed=0" in result.stdout
    assert "source/core=1" in result.stdout


def test_update_fingerprint_check_exits_nonzero_on_mismatch(tmp_path: Path):
    source = tmp_path / "source"
    _make_checkout(source)

    result = _run(tmp_path, "--check")

    assert result.returncode == 1


def test_update_fingerprint_ignores_invalid_previous_json(tmp_path: Path):
    source = tmp_path / "source"
    home = tmp_path / "home" / ".agent-crew"
    fingerprint = home / "state" / "project" / "update-fingerprint.json"
    _make_checkout(source)
    fingerprint.parent.mkdir(parents=True)
    fingerprint.write_text("{", encoding="utf-8")

    result = _run(tmp_path, "--format", "json")

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["reason"] == "missing_previous_fingerprint"


def test_update_fingerprint_category_for_handles_unknown_and_empty_entries():
    module = load_update_fingerprint_module()

    assert module.category_for("misc/file.txt") == "misc"
    assert module.category_for("") == ""


def test_update_fingerprint_managed_path_crew_tolerates_read_errors():
    module = load_update_fingerprint_module()

    class BrokenPath:
        def is_file(self):
            return True

        def read_text(self, *_args, **_kwargs):
            raise OSError("cannot read")

    assert module.managed_path_crew(BrokenPath()) is False
