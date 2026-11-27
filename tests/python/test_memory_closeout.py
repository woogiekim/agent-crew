"""Explicit closeout only indexes a verified, source-backed project lesson."""

import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest


MEMORY = Path(__file__).resolve().parents[2] / "core/bin/memory"


@pytest.fixture
def project(tmp_path):
    root = tmp_path / "local-project"
    root.mkdir()
    (root / "src.py").write_text("def save():\n    pass\n", encoding="utf-8")
    lesson = root / "lesson.md"
    lesson.write_text(
        "## One verified lesson\n\n"
        "- Condition: A saved operation is retried.\n"
        "- Decision: Keep the original record.\n"
        "- Evidence: src.py:1\n",
        encoding="utf-8",
    )
    spy = tmp_path / "spy.json"
    provider = tmp_path / "provider"
    provider.write_text(
        "#!/usr/bin/env python3\n"
        "import json, os, sys\n"
        "from pathlib import Path\n"
        "Path(os.environ['CLOSEOUT_SPY']).write_text(json.dumps(sys.argv[1:]))\n"
        "print(os.environ.get('CLOSEOUT_TEST_RESPONSE', json.dumps("
        "{'status':'ok','section_count':1,'created':['lesson-id']})))\n",
        encoding="utf-8",
    )
    provider.chmod(0o755)
    env = {**os.environ, "MNEMOS_BIN": str(provider), "CLOSEOUT_SPY": str(spy)}
    return root, lesson, spy, env


def invoke(project, *flags):
    root, lesson, _, env = project
    return subprocess.run(
        [str(MEMORY), "closeout", str(lesson), "--project-root", str(root), *flags],
        env=env, capture_output=True, text=True, timeout=15,
    )


def test_explicit_closeout_uses_real_project_scope_and_source(project):
    root, lesson, spy, _ = project
    result = invoke(project, "--verified")

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["created"] == ["lesson-id"]
    fingerprint = hashlib.sha256(b"src.py:1\0" + (root / "src.py").read_bytes()).hexdigest()
    assert json.loads(spy.read_text()) == [
        "project-context", "capture", str(lesson), "--project-id", root.name,
        "--project-root", str(root), "--tag", f"evidence-sha256:{fingerprint}", "--json",
    ]


def test_unverified_lesson_is_rejected_before_provider_call(project):
    _, _, spy, _ = project
    result = invoke(project)

    assert result.returncode != 0
    assert not spy.exists()


@pytest.mark.parametrize("reference", ["../outside.py:1", "src.py:99", "missing.py:1"])
def test_invalid_evidence_is_rejected_before_provider_call(project, reference):
    _, lesson, spy, _ = project
    lesson.write_text(lesson.read_text().replace("src.py:1", reference), encoding="utf-8")
    result = invoke(project, "--verified")

    assert result.returncode != 0
    assert not spy.exists()


def test_multiple_lesson_sections_are_rejected(project):
    _, lesson, spy, _ = project
    lesson.write_text(lesson.read_text() + "\n## Unrelated section\n\nExtra text.\n")
    result = invoke(project, "--verified")

    assert result.returncode != 0
    assert not spy.exists()


def test_evidence_symlink_cannot_cross_checkout_boundary(project):
    root, lesson, spy, _ = project
    outside = root.parent / "elsewhere.py"
    outside.write_text("verified value\n", encoding="utf-8")
    (root / "linked.py").symlink_to(outside)
    lesson.write_text(lesson.read_text().replace("src.py:1", "linked.py:1"), encoding="utf-8")

    result = invoke(project, "--verified")

    assert result.returncode != 0
    assert not spy.exists()


def test_installed_memory_resolves_closeout_helper_under_system(project, tmp_path):
    root, lesson, spy, env = project
    install = tmp_path / "installed"
    scripts = install / "system/scripts"
    scripts.mkdir(parents=True)
    entry = install / "bin/memory"
    entry.parent.mkdir()
    shutil.copy2(MEMORY, entry)
    shutil.copy2(MEMORY.parents[1] / "scripts/memory-closeout.py", scripts)
    shutil.copy2(MEMORY.parents[1] / "scripts/project_memory_source.py", scripts)

    result = subprocess.run(
        [str(entry), "closeout", str(lesson), "--project-root", str(root), "--verified"],
        env={**env, "AGENT_CREW_HOME": str(install)}, capture_output=True, text=True, timeout=15,
    )

    assert result.returncode == 0, result.stderr
    assert json.loads(spy.read_text())[:2] == ["project-context", "capture"]


def test_empty_provider_success_is_not_reported_as_saved(project):
    _, _, _, env = project
    env["CLOSEOUT_TEST_RESPONSE"] = ""
    result = invoke(project, "--verified")

    assert result.returncode != 0
    assert "provider" in result.stderr
