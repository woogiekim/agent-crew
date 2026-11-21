"""Contract tests for installation-based runtime drift and explicit source comparisons."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
VERIFIER = ROOT / "core/scripts/verify-install-drift.py"


def copy_source(dest):
    for directory in ("core", "adapters"):
        shutil.copytree(ROOT / directory, dest / directory, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    shutil.copy2(ROOT / "install.sh", dest / "install.sh")


def invoke(argv, env, cwd):
    return subprocess.run(argv, env=env, cwd=cwd, capture_output=True, text=True, timeout=90)


def output(result):
    return result.stdout + result.stderr


def payload(result):
    line = next(line for line in output(result).splitlines() if line.startswith("DRIFT_DIAGNOSTICS: "))
    return json.loads(line.split(": ", 1)[1])


def installation_env(tmp_path, host="codex"):
    user_home = tmp_path / "user-home"
    user_home.mkdir(exist_ok=True)
    return dict(
        (key, value) for key, value in os.environ.items()
        if not key.startswith(("AGENT_CREW_", "CODEX", "CLAUDE", "MNEMOS"))
    ) | {
        "HOME": str(user_home),
        "AGENT_CREW_HOME": str(tmp_path / "crew"),
        "CODEX_HOME": str(tmp_path / "codex"),
        "CLAUDE_DIR": str(tmp_path / "claude"),
        "AGENT_CREW_HOST": host,
        "AGENT_CREW_PATH_BIN": str(tmp_path / "bin"),
        "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
        "AGENT_CREW_SKIP_PATH_CLI": "1",
        "AGENT_CREW_WRITE_INSTALL_MANIFEST": "0",
        "AGENT_CREW_HOST_BRIDGE_COMMAND": "false",
        "MNEMOS_BIN": str(tmp_path / "unavailable-mnemos"),
    }


def install_update_fixture(tmp_path, *, install_path_cli=False):
    release, project = tmp_path / "release", tmp_path / "project"
    copy_source(release)
    project.mkdir()
    env = installation_env(tmp_path)
    if install_path_cli:
        env.pop("AGENT_CREW_SKIP_PATH_CLI")
    home = Path(env["AGENT_CREW_HOME"])
    result = invoke(["bash", str(release / "core/scripts/sync-local-install.sh"), str(release), str(project)], env, project)
    assert result.returncode == 0, output(result)
    return release, project, home, env


@pytest.fixture
def installation(tmp_path):
    return install_update_fixture(tmp_path)


def installed_run(installation, **overrides):
    _, project, home, env = installation
    return invoke(["bash", str(home / "bin/crew"), "run", "로컬 drift 계약 조사"], env | overrides, project)


def test_codex_agent_backups_do_not_change_managed_projection(tmp_path):
    spec = importlib.util.spec_from_file_location("drift", VERIFIER)
    verifier = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(verifier)
    agents = tmp_path / "agents"
    home = tmp_path / "crew"
    generated = invoke([
        "python3", str(ROOT / "core/scripts/generate-codex-system-agents.py"),
        str(ROOT / "core/agents"), str(agents), "--source-ref-root", str(home / "system/agents"),
        "--model-policy", str(ROOT / "adapters/codex/model-policy.json"),
    ], os.environ, tmp_path)
    assert generated.returncode == 0, output(generated)
    before = verifier.compare_codex_generated_agents(ROOT, home, agents)
    assert before["passed"]
    original = (agents / "reviewer.toml").read_bytes()
    backup = agents / "reviewer.toml.bak-keep"
    backup.write_bytes(original)
    (agents / "archive").mkdir()
    (agents / "archive/reviewer.toml").write_bytes(original)
    (agents / "personal.toml").write_text('description = "user agent"\n')

    after = verifier.compare_codex_generated_agents(ROOT, home, agents)
    assert after["passed"] and after["projection"] == before["projection"], after
    assert backup.read_bytes() == original

    (agents / "stale.toml").write_bytes(original)
    (agents / "reviewer.toml").write_text('description = "changed"\n')
    (agents / "backend.toml").unlink()
    changed = verifier.compare_codex_generated_agents(ROOT, home, agents)
    assert changed["extra"] == ["stale.toml"]
    assert "reviewer.toml" in changed["mismatched"] and "backend.toml" in changed["missing"]
    assert not changed["passed"]


def test_installed_run_keeps_project_state_without_comparing_dirty_checkout(installation):
    release, project, home, env = installation
    project = project.with_name("runtime-install-baseline")
    project.mkdir()
    installation = (release, project, home, env)
    expected_key = "runtime-install-baseline-" + hashlib.sha256(str(project.resolve()).encode()).hexdigest()[:10]
    clean = installed_run(installation)
    assert "TASK_DIR:" in clean.stdout, output(clean)

    copy_source(project)
    (project / "core/commands/run.md").write_text("local project edit\n")
    (project / "core/commands/local-only.md").write_text("untracked command\n")
    backup = Path(env["CODEX_HOME"]) / "agents/reviewer.toml.bak"
    backup.write_bytes(backup.with_name("reviewer.toml").read_bytes())
    saved = backup.read_bytes()
    shutil.rmtree(release)

    result = installed_run(installation)

    assert "runtime_drift_selection_required" not in output(result), output(result)
    register_path = Path(re.search(r"^TASK_DIR: (.+)$", result.stdout, re.MULTILINE)[1]) / "register.json"
    register = json.loads(register_path.read_text())
    assert Path(register["project_root"]).resolve() == project.resolve()
    assert register_path.parents[2].name == expected_key
    assert not (home / "state/runtime-install-baseline").exists()
    assert backup.read_bytes() == saved and (project / "core/commands/run.md").read_text() == "local project edit\n"


def test_installed_run_detects_real_drift_without_source_checkout(installation):
    release, project, home, env = installation
    shutil.rmtree(release)
    (home / "system/commands/run.md").unlink()
    with (home / "scripts/tdd_execution.py").open("a") as changed_runtime:
        changed_runtime.write("\n# changed runtime\n")
    (home / "system/hooks/obsolete.sh").write_text("stale hook\n")
    (Path(env["CODEX_HOME"]) / "agents/reviewer.toml").write_text('description = "changed"\n')

    result = installed_run(installation)

    assert result.returncode == 3, output(result)
    diagnostics = payload(result)
    checks = [row for row in diagnostics["checks"] if not row["passed"]]
    assert any("run.md" in row["missing"] for row in checks)
    assert any("tdd_execution.py" in row["mismatched"] for row in checks)
    assert any("obsolete.sh" in row["extra"] for row in checks)
    assert any("reviewer.toml" in row["mismatched"] for row in checks)
    assert not (home / "system/commands/run.md").exists()


def test_installed_run_without_baseline_requires_explicit_migration(installation):
    release, project, home, _ = installation
    shutil.rmtree(home / "runtime-install-baseline", ignore_errors=True)
    copy_source(project)

    result = installed_run(installation)

    assert result.returncode == 2, output(result)
    assert "crew update" in output(result)
    assert payload(result)["status"] == "UNKNOWN"
    assert "TASK_DIR:" not in output(result)
    assert not (home / "runtime-install-baseline").exists()


def test_explicit_development_source_still_detects_a_changed_checkout(installation):
    release, project, _, env = installation
    copy_source(project)
    (project / "core/commands/run.md").write_text("development source edit\n")

    result = installed_run(installation, AGENT_CREW_SOURCE_DIR=str(project))
    direct = invoke(["bash", str(project / "core/bin/crew"), "run", "직접 소스 비교"], env, release)

    for attempt in (result, direct):
        assert attempt.returncode == 3, output(attempt)
        assert Path(payload(attempt)["source_root"]).resolve() == project.resolve()
    absent = installed_run(installation, AGENT_CREW_SOURCE_DIR=str(project / "absent"))
    assert absent.returncode == 2 and "TASK_DIR:" not in output(absent), output(absent)


def test_update_reuses_baseline_and_failed_update_preserves_active_generation(installation):
    release, project, home, env = installation
    baseline = home / "runtime-install-baseline"
    pointer = baseline / "active"
    original = pointer.read_bytes()
    generations = list((baseline / "generations").iterdir())

    update = ["bash", str(release / "core/bin/crew"), "update", "--local", str(release)]
    result = invoke(update, env | {"PROJECT_ROOT": str(project)}, project)
    assert result.returncode == 0, output(result)
    assert "skipped adapter refresh" in output(result)
    assert pointer.read_bytes() == original and list((baseline / "generations").iterdir()) == generations
    command = Path("commands/parity-implement-example.md")
    (release / "core" / command).write_text("new input")
    result = invoke(update, env | {"PROJECT_ROOT": str(project)}, project)
    assert result.returncode == 0, output(result)
    assert pointer.read_bytes() != original
    assert (home / "system" / command).read_text() == "new input"
    original = pointer.read_bytes()
    generations = list((baseline / "generations").iterdir())

    (release / "core/scripts/sync-local-install.sh").write_text("# sync-local-install.sh\nexit 9\n")

    result = invoke(update, env | {"PROJECT_ROOT": str(project)}, project)

    assert result.returncode == 9, output(result)
    assert pointer.read_bytes() == original and list((baseline / "generations").iterdir()) == generations


def test_installed_run_rejects_corrupt_or_escaping_baseline(installation):
    _, _, home, _ = installation
    baseline = home / "runtime-install-baseline"
    active = baseline / "active"
    generation = baseline / "generations" / active.read_text().splitlines()[0]
    (generation / "core/commands/run.md").write_text("modified official source\n")

    result = installed_run(installation)
    assert result.returncode == 2 and "crew update" in output(result), output(result)
    assert payload(result)["status"] == "UNKNOWN"

    active.write_text("../../outside\n")
    result = installed_run(installation)
    assert result.returncode == 2 and "TASK_DIR:" not in output(result), output(result)
    assert payload(result)["status"] == "UNKNOWN"


def test_first_core_install_records_a_baseline_without_activating_optional_hosts(tmp_path):
    release, project = tmp_path / "release", tmp_path / "project"
    copy_source(release)
    project.mkdir()
    env = installation_env(tmp_path, host="none") | {
        "AGENT_CREW_INSTALL_CLAUDE_COMPAT": "0",
    }
    result = invoke(["bash", str(release / "install.sh")], env, project)
    assert result.returncode == 0, output(result)
    home = Path(env["AGENT_CREW_HOME"])
    shutil.rmtree(release)

    result = installed_run((release, project, home, env))

    assert "TASK_DIR:" in result.stdout, output(result)
    assert not (Path(env["CLAUDE_DIR"]) / "agent-crew").exists()
    assert not (Path(env["CODEX_HOME"]) / "agents").exists()


def test_installed_run_detects_missing_or_replaced_managed_path_cli_and_syncs_from_release(tmp_path):
    installation = install_update_fixture(tmp_path, install_path_cli=True)
    release, project, _, env = installation
    path_cli = Path(env["AGENT_CREW_PATH_BIN"]) / "crew"
    original = path_cli.read_bytes()
    copy_source(project)
    command = project / "core/commands/run.md"
    command.write_text("local edit\n")
    shutil.rmtree(release)
    path_cli.write_text("#!/bin/bash\necho user replacement\n")

    replaced = installed_run(installation)

    assert "runtime_drift_selection_required" in output(replaced), output(replaced)
    assert any(row["destination"] == str(path_cli) and not row["passed"] for row in payload(replaced)["checks"])
    assert path_cli.read_text().endswith("echo user replacement\n")
    path_cli.unlink()
    missing = installed_run(installation)
    assert "runtime_drift_selection_required" in output(missing), output(missing)
    assert any(row["destination"] == str(path_cli) and row["missing"] for row in payload(missing)["checks"])
    fields = dict(line.split(": ", 1) for line in output(missing).splitlines() if ": " in line)
    source = Path(payload(missing)["source_root"])
    decision = invoke([
        "python3", str(source / "core/scripts/interactive-question-state.py"), "record",
        "--state-dir", fields["QUESTION_STATE_DIR"], "--question-id", fields["QUESTION_ID"],
        "--prompt", fields["QUESTION_PROMPT"], "--options-json", fields["OPTIONS_JSON"],
        "--chosen-label", "Sync source then run", "--chosen-value", "sync",
    ], env, project)
    assert decision.returncode == 0, output(decision)

    recovered = installed_run(installation)

    assert "runtime assets synchronized and verified" in output(recovered), output(recovered)
    assert "TASK_DIR:" in recovered.stdout and path_cli.read_bytes() == original
    assert command.read_text() == "local edit\n"


def test_update_cannot_publish_source_changed_after_verification(installation):
    release, project, home, env = installation
    pointer = home / "runtime-install-baseline/active"
    previous = pointer.read_bytes()
    verifier = release / "core/scripts/verify-install-drift.py"
    verifier.write_text(verifier.read_text().replace(
        "    raise SystemExit(main())",
        """    import sys

    result = main()
    if result == 0 and "--prune-extra" in sys.argv:
        source = Path(sys.argv[sys.argv.index("--source-root") + 1])
        command = source / "core/commands/run.md"
        if command.read_text() != "late source edit":
            command.write_text("late source edit")
    raise SystemExit(result)""",
    ))

    result = invoke([
        "bash", str(release / "core/scripts/sync-local-install.sh"), str(release), str(project),
    ], env | {"AGENT_CREW_DISABLE_FAST_NOOP_UPDATE": "1"}, project)

    assert (release / "core/commands/run.md").read_text() == "late source edit", output(result)
    assert result.returncode != 0, output(result)
    assert pointer.read_bytes() == previous
    assert "refreshed installed assets" not in output(result)

    retry = invoke([
        "bash", str(release / "core/bin/crew"), "update", "--local", str(release),
    ], env | {"PROJECT_ROOT": str(project)}, project)
    assert retry.returncode == 0, output(retry)
    assert pointer.read_bytes() != previous
    assert (home / "system/commands/run.md").read_text() == "late source edit"


def test_incomplete_release_is_rejected_before_changing_the_install(installation):
    release, project, home, env = installation
    pointer = home / "runtime-install-baseline/active"
    previous = pointer.read_bytes()
    installed_command = home / "system/commands/run.md"
    original = installed_command.read_bytes()
    (release / "core/scripts/runtime-install-baseline.py").unlink()
    (release / "core/commands/run.md").write_text("unverified release")

    result = invoke([
        "bash", str(release / "core/scripts/sync-local-install.sh"), str(release), str(project),
    ], env, project)

    assert result.returncode == 2 and "missing runtime baseline helper" in output(result), output(result)
    assert pointer.read_bytes() == previous and installed_command.read_bytes() == original


def test_same_name_user_command_is_preserved_across_update_and_reinstall(installation):
    release, project, home, env = installation
    user_command = home / "user/commands/run.md"
    user_command.write_text("custom user command")
    local_update = ["bash", str(release / "core/scripts/sync-local-install.sh"), str(release), str(project)]
    reinstall = ["bash", str(release / "install.sh")]
    env |= {
        "AGENT_CREW_MODE": "update",
        "AGENT_CREW_INSTALL_CLAUDE_COMPAT": "0",
    }

    for installer in (local_update, reinstall):
        updated = invoke(installer, env, project)
        assert updated.returncode == 0, output(updated)
        assert user_command.read_text() == "custom user command"
        assert (home / "commands/run.md").read_text() == "custom user command"
        result = installed_run(installation)
        assert "TASK_DIR:" in result.stdout, output(result)

    (home / "system/commands/run.md").unlink()
    result = installed_run(installation)
    assert "runtime_drift_selection_required" in output(result), output(result)
    assert any("run.md" in row["missing"] for row in payload(result)["checks"])


def test_first_install_with_default_claude_adapter_has_no_runtime_drift(tmp_path):
    release, project = tmp_path / "release", tmp_path / "project"
    copy_source(release)
    project.mkdir()
    env = installation_env(tmp_path, host="claude")
    result = invoke(["bash", str(release / "install.sh")], env, project)
    assert result.returncode == 0, output(result)
    home = Path(env["AGENT_CREW_HOME"])
    shutil.rmtree(release)

    result = installed_run((release, project, home, env))

    assert "TASK_DIR:" in result.stdout, output(result)
    assert "runtime_drift_selection_required" not in output(result)
