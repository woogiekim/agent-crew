import json
import importlib.util
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPT = REPO_ROOT / "core" / "scripts" / "update-project-registry.py"


def run_registry(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        text=True,
        capture_output=True,
        check=False,
    )


def load_registry_module():
    spec = importlib.util.spec_from_file_location("update_project_registry", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_registry_marks_global_and_project_and_lists_project(tmp_path: Path):
    home = tmp_path / "home"
    source = tmp_path / "source"
    project = tmp_path / "project"
    source.mkdir()
    project.mkdir()

    result = run_registry(
        "--agent-crew-home",
        str(home),
        "mark-global",
        "--source-root",
        str(source),
    )
    assert result.returncode == 0
    assert f"update_scope: global={home.resolve()}" in result.stdout

    result = run_registry(
        "--agent-crew-home",
        str(home),
        "mark-project",
        "--source-root",
        str(source),
        "--project-root",
        str(project),
    )
    assert result.returncode == 0
    assert f"update_scope: project={project.resolve()}" in result.stdout

    registry = json.loads((home / "state" / "update-registry.json").read_text())
    assert str(project.resolve()) in registry["projects"]
    assert (home / "state" / project.name / "project-update.json").is_file()

    result = run_registry(
        "--agent-crew-home",
        str(home),
        "list-projects",
    )
    assert result.returncode == 0
    assert str(project.resolve()) in result.stdout.splitlines()


def test_check_stale_reports_warning_when_global_is_newer(tmp_path: Path):
    home = tmp_path / "home"
    project = tmp_path / "project"
    project.mkdir()
    (project / ".codex").mkdir()
    registry = {
        "schema_version": 1,
        "global": {
            "updated_at_epoch": 20,
            "updated_at": "1970-01-01T00:00:20Z",
        },
        "projects": {
            str(project.resolve()): {
                "project_root": str(project.resolve()),
                "project_name": project.name,
                "updated_at_epoch": 10,
                "updated_at": "1970-01-01T00:00:10Z",
            }
        },
    }
    registry_path = home / "state" / "update-registry.json"
    registry_path.parent.mkdir(parents=True)
    registry_path.write_text(json.dumps(registry), encoding="utf-8")

    result = run_registry(
        "--agent-crew-home",
        str(home),
        "check-stale",
        "--project-root",
        str(project),
    )
    assert result.returncode == 0
    assert "WARNING: project-local agent-crew files may be stale" in result.stdout
    assert "crew update --all-projects" in result.stdout

    result = run_registry(
        "--agent-crew-home",
        str(home),
        "check-stale",
        "--project-root",
        str(project),
        "--format",
        "json",
    )
    payload = json.loads(result.stdout)
    assert payload["status"] == "stale"
    assert payload["reason"] == "global_newer_than_project"


def test_list_projects_includes_task_state_project_roots(tmp_path: Path):
    home = tmp_path / "home"
    project = tmp_path / "project"
    task_dir = home / "state" / "legacy" / "tasks" / "task-1"
    project.mkdir()
    task_dir.mkdir(parents=True)
    (task_dir / "project-root.txt").write_text(str(project), encoding="utf-8")

    result = run_registry(
        "--agent-crew-home",
        str(home),
        "list-projects",
        "--format",
        "json",
    )
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    roots = [item["project_root"] for item in payload["projects"]]
    assert str(project.resolve()) in roots


def test_helpers_tolerate_malformed_registry_and_task_state(tmp_path: Path):
    module = load_registry_module()
    home = tmp_path / "home"
    registry_path = home / "state" / "update-registry.json"
    registry_path.parent.mkdir(parents=True)
    registry_path.write_text("{", encoding="utf-8")

    assert module.read_json(registry_path)["schema_version"] == 1
    assert module.as_dict("not a dict") == {}
    assert module.int_value({"updated_at_epoch": "bad"}, "updated_at_epoch") == 0

    registry_path.write_text("{}", encoding="utf-8")
    registry = module.read_json(registry_path)
    assert registry["schema_version"] == 1
    assert registry["global"] == {}
    assert registry["projects"] == {}

    assert module.roots_from_task_state(tmp_path / "missing-home") == {}

    project = tmp_path / "project"
    project.mkdir()
    task_dir = home / "state" / "legacy" / "tasks" / "task-1"
    task_dir.mkdir(parents=True)
    (task_dir / "register.json").write_text("{", encoding="utf-8")
    assert module.roots_from_task_state(home) == {}

    (task_dir / "register.json").write_text(
        json.dumps({"project_root": str(project)}),
        encoding="utf-8",
    )
    roots = module.roots_from_task_state(home)
    assert str(project.resolve()) in roots


def test_local_output_detection_covers_project_instruction_files(tmp_path: Path):
    module = load_registry_module()
    project = tmp_path / "project"
    project.mkdir()

    assert module.project_has_local_outputs(project) is False

    (project / "AGENTS.md").write_text("rules", encoding="utf-8")
    assert module.project_has_local_outputs(project) is True

    (project / "AGENTS.md").unlink()
    (project / "CLAUDE.md").write_text("rules", encoding="utf-8")
    assert module.project_has_local_outputs(project) is True


def test_check_stale_reports_missing_project_marker_when_local_outputs_exist(tmp_path: Path):
    home = tmp_path / "home"
    project = tmp_path / "project"
    project.mkdir()
    (project / ".agent-crew").mkdir()
    registry_path = home / "state" / "update-registry.json"
    registry_path.parent.mkdir(parents=True)
    registry_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "global": {
                    "updated_at_epoch": 20,
                    "updated_at": "1970-01-01T00:00:20Z",
                },
                "projects": {},
            }
        ),
        encoding="utf-8",
    )

    result = run_registry(
        "--agent-crew-home",
        str(home),
        "check-stale",
        "--project-root",
        str(project),
        "--format",
        "json",
    )
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["status"] == "stale"
    assert payload["reason"] == "project_update_marker_missing"
