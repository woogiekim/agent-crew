"""Tests for per-user coding convention cache and task snapshots."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPT = REPO_ROOT / "core" / "scripts" / "user-conventions.py"


def run_cli(*args: str) -> dict:
    result = subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        check=True,
        text=True,
        capture_output=True,
    )

    return json.loads(result.stdout)


def test_convention_snapshot_is_owner_scoped(tmp_path: Path) -> None:
    cache_dir = tmp_path / "cache"
    task_dir = tmp_path / "task"

    run_cli(
        "capture",
        "--owner",
        "alice",
        "--cache-dir",
        str(cache_dir),
        "--language",
        "python",
        "--scope",
        "global",
        "--content",
        "Prefer pathlib for new Python file work.",
    )
    run_cli(
        "capture",
        "--owner",
        "bob",
        "--cache-dir",
        str(cache_dir),
        "--language",
        "python",
        "--scope",
        "global",
        "--content",
        "Prefer os.path for legacy compatibility.",
    )

    output = run_cli(
        "snapshot",
        "--owner",
        "alice",
        "--cache-dir",
        str(cache_dir),
        "--task-dir",
        str(task_dir),
        "--stage",
        "backend",
        "--task",
        "Implement Python cache support",
        "--project-root",
        str(REPO_ROOT),
    )

    snapshot = json.loads(Path(output["snapshot_path"]).read_text(encoding="utf-8"))
    contents = [item["content"] for item in snapshot["conventions"]]

    assert snapshot["owner"] == "alice"
    assert contents == ["Prefer pathlib for new Python file work."]
    assert "Prefer os.path for legacy compatibility." not in "\n".join(contents)


def test_update_and_retire_refresh_snapshot_without_requiring_proof_artifacts(
    tmp_path: Path,
) -> None:
    cache_dir = tmp_path / "cache"
    task_dir = tmp_path / "task"

    captured = run_cli(
        "capture",
        "--owner",
        "alice",
        "--cache-dir",
        str(cache_dir),
        "--language",
        "python",
        "--scope",
        "global",
        "--content",
        "Prefer pathlib for path work.",
    )
    updated = run_cli(
        "update",
        captured["id"],
        "--owner",
        "alice",
        "--cache-dir",
        str(cache_dir),
        "--content",
        "Prefer pathlib.Path for new path work.",
    )

    assert updated["version"] > captured["version"]

    output = run_cli(
        "snapshot",
        "--owner",
        "alice",
        "--cache-dir",
        str(cache_dir),
        "--task-dir",
        str(task_dir),
        "--stage",
        "backend",
        "--task",
        "Implement path handling",
        "--project-root",
        str(REPO_ROOT),
        "--refresh",
    )
    digest = Path(output["context_path"]).read_text(encoding="utf-8")

    assert "Prefer pathlib.Path for new path work." in digest
    assert "proof artifact" not in digest.lower()
    assert "skill-use" not in digest.lower()

    run_cli(
        "update",
        captured["id"],
        "--owner",
        "alice",
        "--cache-dir",
        str(cache_dir),
        "--content",
        "Prefer pathlib.Path.resolve for normalized paths.",
    )
    frozen = run_cli(
        "snapshot",
        "--owner",
        "alice",
        "--cache-dir",
        str(cache_dir),
        "--task-dir",
        str(task_dir),
        "--stage",
        "backend",
        "--task",
        "Implement path handling",
        "--project-root",
        str(REPO_ROOT),
    )
    frozen_digest = Path(frozen["context_path"]).read_text(encoding="utf-8")

    assert frozen["cache_status"] == "frozen"
    assert "Prefer pathlib.Path for new path work." in frozen_digest
    assert "Prefer pathlib.Path.resolve for normalized paths." not in frozen_digest

    refreshed = run_cli(
        "snapshot",
        "--owner",
        "alice",
        "--cache-dir",
        str(cache_dir),
        "--task-dir",
        str(task_dir),
        "--stage",
        "backend",
        "--task",
        "Implement path handling",
        "--project-root",
        str(REPO_ROOT),
        "--refresh",
    )
    refreshed_digest = Path(refreshed["context_path"]).read_text(encoding="utf-8")

    assert refreshed["cache_status"] == "refreshed"
    assert "Prefer pathlib.Path.resolve for normalized paths." in refreshed_digest

    retired = run_cli(
        "retire",
        captured["id"],
        "--owner",
        "alice",
        "--cache-dir",
        str(cache_dir),
    )

    assert retired["status"] == "retired"

    output = run_cli(
        "snapshot",
        "--owner",
        "alice",
        "--cache-dir",
        str(cache_dir),
        "--task-dir",
        str(task_dir),
        "--stage",
        "backend",
        "--task",
        "Implement path handling",
        "--project-root",
        str(REPO_ROOT),
        "--refresh",
    )
    snapshot = json.loads(Path(output["snapshot_path"]).read_text(encoding="utf-8"))

    assert snapshot["conventions"] == []
    assert output["context_path"] == ""


def test_later_stage_digest_uses_frozen_task_snapshot_without_requerying_cache(
    tmp_path: Path,
) -> None:
    cache_dir = tmp_path / "cache"
    task_dir = tmp_path / "task"

    run_cli(
        "capture",
        "--owner",
        "alice",
        "--cache-dir",
        str(cache_dir),
        "--scope",
        "global",
        "--language",
        "typescript",
        "--applies-to",
        "frontend",
        "--content",
        "Use userEvent for frontend interaction tests.",
    )

    backend_output = run_cli(
        "snapshot",
        "--owner",
        "alice",
        "--cache-dir",
        str(cache_dir),
        "--task-dir",
        str(task_dir),
        "--stage",
        "backend",
        "--task",
        "Implement backend cache",
        "--project-root",
        str(REPO_ROOT),
    )

    assert backend_output["cache_status"] == "refreshed"
    assert backend_output["context_path"] == ""

    frontend_output = run_cli(
        "snapshot",
        "--owner",
        "alice",
        "--cache-dir",
        str(cache_dir),
        "--task-dir",
        str(task_dir),
        "--stage",
        "frontend",
        "--task",
        "Implement frontend UI",
        "--project-root",
        str(REPO_ROOT),
    )
    frontend_digest = Path(frontend_output["context_path"]).read_text(
        encoding="utf-8"
    )

    assert frontend_output["cache_status"] == "frozen"
    assert "Use userEvent for frontend interaction tests." in frontend_digest


def test_stage_prompt_docs_pass_user_conventions_by_path_only() -> None:
    supervisor = (REPO_ROOT / "core" / "agents" / "supervisor-stages.md").read_text(
        encoding="utf-8"
    )
    backend = (REPO_ROOT / "core" / "agents" / "backend.md").read_text(
        encoding="utf-8"
    )
    reviewer = (REPO_ROOT / "core" / "agents" / "reviewer.md").read_text(
        encoding="utf-8"
    )

    assert "USER_CONVENTIONS_PATH:" in supervisor
    assert "user-conventions.snapshot.json" in supervisor
    assert "read USER_CONVENTIONS_PATH" in backend
    assert "Do not require proof-only artifacts for user conventions" in reviewer
