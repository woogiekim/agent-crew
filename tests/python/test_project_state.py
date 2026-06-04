import json
import importlib.util
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPT = REPO_ROOT / "core" / "scripts" / "project_state.py"


def load_module():
    spec = importlib.util.spec_from_file_location("project_state", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_project_state_key_disambiguates_duplicate_basenames(tmp_path: Path):
    module = load_module()
    first = tmp_path / "a" / "service"
    second = tmp_path / "b" / "service"
    first.mkdir(parents=True)
    second.mkdir(parents=True)

    first_key = module.project_state_key(first)
    second_key = module.project_state_key(second)

    assert first_key.startswith("service-")
    assert second_key.startswith("service-")
    assert first_key != second_key


def test_resolve_migrates_matching_legacy_state_to_keyed_state(tmp_path: Path):
    module = load_module()
    home = tmp_path / "home"
    project = tmp_path / "workspace" / "app"
    project.mkdir(parents=True)
    legacy = home / "state" / project.name
    task = legacy / "tasks" / "20260101-120000-0"
    task.mkdir(parents=True)
    (task / "register.json").write_text(
        json.dumps({"project_root": str(project.resolve())}),
        encoding="utf-8",
    )

    info = module.resolve_project_state(
        home=home,
        project_root=project,
        ensure=True,
        migrate_legacy=True,
    )

    state_dir = Path(info["state_dir"])
    assert state_dir.name == module.project_state_key(project)
    assert state_dir.exists()
    assert not legacy.exists()
    assert (state_dir / "tasks" / "20260101-120000-0" / "register.json").is_file()
    metadata = json.loads((state_dir / "project.json").read_text())
    assert metadata["project_name"] == "app"
    assert metadata["project_root"] == str(project.resolve())


def test_setup_existing_preserves_project_context_and_resets_runtime(tmp_path: Path):
    module = load_module()
    home = tmp_path / "home"
    project = tmp_path / "project"
    project.mkdir()
    info = module.resolve_project_state(home=home, project_root=project, ensure=True)
    state_dir = Path(info["state_dir"])
    (state_dir / "project-context").mkdir()
    (state_dir / "project-context" / "project-map.md").write_text("map", encoding="utf-8")
    (state_dir / "tasks" / "task-1").mkdir(parents=True)
    (state_dir / "session.json").write_text("{}", encoding="utf-8")

    result = module.setup_existing_state(
        home=home,
        project_root=project,
        action="preserve-context",
    )

    assert result["cancelled"] is False
    assert (state_dir / "project-context" / "project-map.md").is_file()
    assert not (state_dir / "tasks" / "task-1").exists()
    assert not (state_dir / "session.json").exists()
    assert (state_dir / "tasks").is_dir()


def test_setup_existing_archives_project_context(tmp_path: Path):
    module = load_module()
    home = tmp_path / "home"
    project = tmp_path / "project"
    project.mkdir()
    info = module.resolve_project_state(home=home, project_root=project, ensure=True)
    state_dir = Path(info["state_dir"])
    (state_dir / "project-context").mkdir()
    (state_dir / "project-context" / "decisions.md").write_text("decision", encoding="utf-8")

    result = module.setup_existing_state(
        home=home,
        project_root=project,
        action="archive-context",
    )

    archived = Path(result["archived_to"])
    assert archived.is_dir()
    assert (archived / "decisions.md").is_file()
    assert not (state_dir / "project-context").exists()
