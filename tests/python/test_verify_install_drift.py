"""Tests for install drift verification helpers."""
from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPT = REPO_ROOT / "core" / "scripts" / "verify-install-drift.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("verify_install_drift", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


module = _load_module()


def test_compare_tree_handles_missing_roots_and_prunes_extra_files(tmp_path: Path):
    missing = module.compare_tree(tmp_path / "missing-src", tmp_path / "missing-dest", prune_extra=False)
    assert missing["passed"] is True
    assert missing["missing"] == []

    src = tmp_path / "src"
    dest = tmp_path / "dest"
    src.mkdir()
    dest.mkdir()
    (dest / "extra.txt").write_text("extra", encoding="utf-8")

    result = module.compare_tree(src, dest, prune_extra=True)

    assert result["passed"] is True
    assert result["extra"] == ["extra.txt"]
    assert not (dest / "extra.txt").exists()


def test_compare_tree_ignores_python_runtime_cache(tmp_path: Path):
    src = tmp_path / "src"
    dest = tmp_path / "dest"
    source_cache = src / "__pycache__"
    dest_cache = dest / "__pycache__"
    source_cache.mkdir(parents=True)
    dest_cache.mkdir(parents=True)
    (src / "module.py").write_text("value = 1\n", encoding="utf-8")
    (dest / "module.py").write_text("value = 1\n", encoding="utf-8")
    (source_cache / "module.cpython-312.pyc").write_bytes(b"source-path")
    (dest_cache / "module.cpython-312.pyc").write_bytes(b"installed-path")

    result = module.compare_tree(src, dest, prune_extra=False)

    assert result["passed"] is True
    assert result["mismatched"] == []
    assert result["extra"] == []


def test_compare_file_reports_source_missing_dest_missing_and_mismatch(tmp_path: Path):
    assert module.compare_file(tmp_path / "missing-src", tmp_path / "dest")["missing"] == [
        str(tmp_path / "missing-src")
    ]

    src = tmp_path / "src.txt"
    src.write_text("source", encoding="utf-8")
    assert module.compare_file(src, tmp_path / "missing-dest")["missing"] == [
        str(tmp_path / "missing-dest")
    ]

    dest = tmp_path / "dest.txt"
    dest.write_text("different", encoding="utf-8")
    result = module.compare_file(src, dest)
    assert result["passed"] is False
    assert result["mismatched"] == [str(dest)]


def test_verify_install_drift_json_output_accepts_empty_source(tmp_path: Path):
    source_root = tmp_path / "source"
    source_root.mkdir()
    home = tmp_path / "home"

    result = subprocess.run(
        [
            "python3",
            str(SCRIPT),
            "--source-root",
            str(source_root),
            "--agent-crew-home",
            str(home),
            "--skip-path-bin",
            "--format",
            "json",
        ],
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["passed"] is True


def test_verify_install_drift_text_reports_missing_mismatched_and_extra(tmp_path: Path):
    source_root = tmp_path / "source"
    commands_src = source_root / "core" / "commands"
    commands_src.mkdir(parents=True)
    (commands_src / "update.md").write_text("source", encoding="utf-8")

    home = tmp_path / "home"
    system_commands = home / "system" / "commands"
    system_commands.mkdir(parents=True)
    (system_commands / "update.md").write_text("different", encoding="utf-8")
    (system_commands / "extra.md").write_text("extra", encoding="utf-8")

    result = subprocess.run(
        [
            "python3",
            str(SCRIPT),
            "--source-root",
            str(source_root),
            "--agent-crew-home",
            str(home),
            "--skip-path-bin",
        ],
        text=True,
        capture_output=True,
    )

    assert result.returncode == 1
    assert "FAIL: install drift check" in result.stdout
    assert "missing: update.md" in result.stdout
    assert "mismatched: update.md" in result.stdout
    assert "extra: extra.md" in result.stdout


def test_verify_install_drift_prunes_legacy_codex_dash_skills_only(tmp_path: Path):
    source_root = tmp_path / "source"
    skill_src = source_root / "adapters" / "codex" / "skill" / "crew:run"
    skill_src.mkdir(parents=True)
    (skill_src / "SKILL.md").write_text("canonical\n", encoding="utf-8")

    home = tmp_path / "home"
    codex_home = tmp_path / "codex"
    legacy = codex_home / "skills" / "crew-run"
    canonical = codex_home / "skills" / "crew:run"
    unrelated = codex_home / "skills" / "custom-skill"
    legacy.mkdir(parents=True)
    canonical.mkdir(parents=True)
    unrelated.mkdir(parents=True)
    (legacy / "SKILL.md").write_text("stale\n", encoding="utf-8")
    (canonical / "SKILL.md").write_text("canonical\n", encoding="utf-8")
    (unrelated / "SKILL.md").write_text("keep\n", encoding="utf-8")

    result = subprocess.run(
        [
            "python3",
            str(SCRIPT),
            "--source-root",
            str(source_root),
            "--agent-crew-home",
            str(home),
            "--codex-home",
            str(codex_home),
            "--skip-path-bin",
            "--prune-extra",
            "--format",
            "json",
        ],
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    codex_check = next(
        check for check in payload["checks"] if check["destination"] == str(codex_home / "skills")
    )
    assert codex_check["extra"] == ["crew-run"]
    assert not legacy.exists()
    assert unrelated.is_dir()


def test_boundary_case_contract_runtime_profile_ignores_user_owned_and_unrelated_assets(
    tmp_path: Path,
):
    source_root = tmp_path / "source"
    _write_checkout_identity(source_root)
    command_source = source_root / "core" / "commands"
    command_source.mkdir(parents=True, exist_ok=True)
    (source_root / "adapters").mkdir(exist_ok=True)
    (command_source / "run.md").write_text("canonical\n", encoding="utf-8")

    home = tmp_path / "home"
    _install_core_identity_assets(source_root, home)
    for rel in ("system/scripts/sync-local-install.sh", "scripts/sync-local-install.sh"):
        target = home / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("# sync-local-install.sh\n", encoding="utf-8")
    installed_bin = home / "bin" / "crew"
    installed_bin.parent.mkdir(parents=True, exist_ok=True)
    installed_bin.write_text("# deterministic shell entrypoint for agent-crew\n", encoding="utf-8")
    system_commands = home / "system" / "commands"
    compat_commands = home / "commands"
    user_commands = home / "user" / "commands"
    for directory in (system_commands, compat_commands, user_commands):
        directory.mkdir(parents=True, exist_ok=True)
    (system_commands / "run.md").write_text("canonical\n", encoding="utf-8")
    (compat_commands / "run.md").write_text("canonical\n", encoding="utf-8")
    (compat_commands / "personal.md").write_text("keep\n", encoding="utf-8")
    (user_commands / "personal.md").write_text("changed\n", encoding="utf-8")

    codex_home = tmp_path / "codex"
    unrelated = codex_home / "skills" / "unrelated"
    unrelated.mkdir(parents=True)
    (unrelated / "SKILL.md").write_text("host-owned\n", encoding="utf-8")

    result = subprocess.run(
        [
            "python3",
            str(SCRIPT),
            "--source-root",
            str(source_root),
            "--agent-crew-home",
            str(home),
            "--codex-home",
            str(codex_home),
            "--skip-path-bin",
            "--profile",
            "runtime-readonly",
            "--format",
            "json",
        ],
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "MATCH"
    assert (compat_commands / "personal.md").read_text(encoding="utf-8") == "keep\n"


def test_failure_case_contract_runtime_profile_reports_source_owned_mismatch(
    tmp_path: Path,
):
    source_root = tmp_path / "source"
    _write_checkout_identity(source_root)
    command_source = source_root / "core" / "commands"
    command_source.mkdir(parents=True, exist_ok=True)
    (source_root / "adapters").mkdir(exist_ok=True)
    (command_source / "run.md").write_text("canonical\n", encoding="utf-8")

    home = tmp_path / "home"
    system_commands = home / "system" / "commands"
    compat_commands = home / "commands"
    system_commands.mkdir(parents=True)
    compat_commands.mkdir(parents=True)
    (system_commands / "run.md").write_text("stale\n", encoding="utf-8")
    (compat_commands / "run.md").write_text("canonical\n", encoding="utf-8")

    result = subprocess.run(
        [
            "python3",
            str(SCRIPT),
            "--source-root",
            str(source_root),
            "--agent-crew-home",
            str(home),
            "--skip-path-bin",
            "--profile",
            "runtime-readonly",
            "--format",
            "json",
        ],
        text=True,
        capture_output=True,
    )

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["status"] == "MISMATCH"
    system_check = next(
        check for check in payload["checks"] if check["destination"] == str(system_commands)
    )
    assert system_check["mismatched"] == ["run.md"]


def test_runtime_profile_reports_unknown_when_comparison_fails(
    tmp_path: Path, monkeypatch, capsys
):
    source_root = tmp_path / "source"
    _write_checkout_identity(source_root)

    def fail_comparison(*args, **kwargs):
        raise OSError("fixture read failure")

    monkeypatch.setattr(module, "runtime_checks", fail_comparison)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            str(SCRIPT),
            "--source-root",
            str(source_root),
            "--profile",
            "runtime-readonly",
            "--format",
            "json",
        ],
    )

    assert module.main() == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "UNKNOWN"
    assert payload["passed"] is False


def test_runtime_profile_maps_bin_to_installed_bin_without_system_bin(tmp_path: Path):
    source_root = tmp_path / "source"
    _write_checkout_identity(source_root)
    _install_core_identity_assets(source_root, tmp_path / "home")
    source_bin = source_root / "core" / "bin"
    source_bin.mkdir(parents=True, exist_ok=True)
    (source_root / "adapters").mkdir(exist_ok=True)
    (source_bin / "crew").write_text(
        "# deterministic shell entrypoint for agent-crew\nruntime\n", encoding="utf-8"
    )

    installed_bin = tmp_path / "home" / "bin"
    installed_bin.mkdir(parents=True, exist_ok=True)
    (installed_bin / "crew").write_text(
        "# deterministic shell entrypoint for agent-crew\nruntime\n", encoding="utf-8"
    )
    for rel in ("system/scripts/sync-local-install.sh", "scripts/sync-local-install.sh"):
        installed_script = tmp_path / "home" / rel
        installed_script.parent.mkdir(parents=True, exist_ok=True)
        installed_script.write_text("# sync-local-install.sh\n", encoding="utf-8")

    result = subprocess.run(
        [
            "python3",
            str(SCRIPT),
            "--source-root",
            str(source_root),
            "--agent-crew-home",
            str(tmp_path / "home"),
            "--codex-home",
            str(tmp_path / "codex"),
            "--skip-path-bin",
            "--profile",
            "runtime-readonly",
            "--format",
            "json",
        ],
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "MATCH"
    assert all(check["destination"] != str(tmp_path / "home" / "system" / "bin") for check in payload["checks"])


def test_boundary_case_contract_runtime_profile_reports_not_applicable_without_checkout(
    tmp_path: Path,
):
    source_root = tmp_path / "ordinary-project"
    source_root.mkdir()

    result = subprocess.run(
        [
            "python3",
            str(SCRIPT),
            "--source-root",
            str(source_root),
            "--agent-crew-home",
            str(tmp_path / "home"),
            "--skip-path-bin",
            "--profile",
            "runtime-readonly",
            "--format",
            "json",
        ],
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "NOT_APPLICABLE"
    assert payload["checks"] == []


def _write_checkout_identity(source_root: Path) -> None:
    (source_root / "core" / "bin").mkdir(parents=True, exist_ok=True)
    (source_root / "core" / "scripts").mkdir(parents=True, exist_ok=True)
    (source_root / "core" / "bin" / "crew").write_text(
        "# deterministic shell entrypoint for agent-crew\n", encoding="utf-8"
    )
    (source_root / "core" / "scripts" / "sync-local-install.sh").write_text(
        "# sync-local-install.sh\n", encoding="utf-8"
    )
    (source_root / "install.sh").write_text("# installer\n", encoding="utf-8")
    for rel, content in (
        ("core/commands/run.md", "# run\n"),
        ("core/rules/task-injection.md", "# task injection\n"),
        ("adapters/codex/skill/crew:run/SKILL.md", "# crew run\n"),
        ("adapters/codex/invocation.md", "# invocation\n"),
        ("core/hooks/route-directive-guard.sh", "# hook\n"),
        ("core/evaluations/phase-2-validation.json", "{}\n"),
        ("core/policies/agent-capabilities.json", "{}\n"),
        ("core/schemas/session.schema.json", "{}\n"),
        ("core/setup/setup-host.sh", "# setup\n"),
        ("core/agents/resolver.md", "# resolver\n"),
        ("core/agents/skills/tdd.md", "# tdd\n"),
        ("core/bin/memory", "# memory\n"),
        ("adapters/codex/setup.sh", "# setup\n"),
        ("adapters/codex/template/config.toml", "[agents]\nmax_threads = 6\nmax_depth = 1\n"),
        ("adapters/codex/model-policy.json", "{}\n"),
        ("core/scripts/generate-codex-system-agents.py", "# generator\n"),
    ):
        path = source_root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    inventory = source_root / "core" / "schemas" / "runtime-managed-source-inventory.json"
    files = [
        str(path.relative_to(source_root)) for path in source_root.rglob("*")
        if path.is_file() and path != inventory
    ]
    inventory.write_text(json.dumps({"schema_version": 1, "files": sorted(files)}), encoding="utf-8")


def _install_core_identity_assets(source_root: Path, home: Path) -> None:
    for name in ("commands", "rules", "hooks", "scripts", "evaluations", "policies", "schemas", "setup"):
        source = source_root / "core" / name
        for destination in (home / "system" / name, home / name):
            shutil.copytree(source, destination, dirs_exist_ok=True)
    for name in ("agents", "bin"):
        shutil.copytree(source_root / "core" / name, home / ("system" if name == "agents" else "") / name,
                        dirs_exist_ok=True)
    shutil.copytree(source_root / "core" / "agents" / "skills", home / "system" / "skills", dirs_exist_ok=True)
    shutil.copytree(source_root / "core" / "agents" / "skills", home / "skills", dirs_exist_ok=True)


def test_runtime_profile_rejects_partial_checkout_identity(tmp_path: Path):
    source_root = tmp_path / "partial"
    (source_root / "core").mkdir(parents=True)
    (source_root / "adapters").mkdir(exist_ok=True)

    result = subprocess.run(
        ["python3", str(SCRIPT), "--source-root", str(source_root),
         "--agent-crew-home", str(tmp_path / "home"), "--profile", "runtime-readonly",
         "--format", "json"], text=True, capture_output=True
    )

    assert result.returncode != 0
    payload = json.loads(result.stdout)
    assert payload["status"] != "MATCH"
    assert payload["source_identity"]["valid"] is False


def test_runtime_profile_reports_system_owned_stale_extra(tmp_path: Path):
    source_root = tmp_path / "source"
    _write_checkout_identity(source_root)
    (source_root / "core" / "commands").mkdir(parents=True, exist_ok=True)
    (source_root / "core" / "commands" / "run.md").write_text("run\n", encoding="utf-8")
    system_commands = tmp_path / "home" / "system" / "commands"
    system_commands.mkdir(parents=True)
    (system_commands / "run.md").write_text("run\n", encoding="utf-8")
    (system_commands / "stale.md").write_text("stale\n", encoding="utf-8")

    result = subprocess.run(
        ["python3", str(SCRIPT), "--source-root", str(source_root),
         "--agent-crew-home", str(tmp_path / "home"), "--active-host", "none",
         "--skip-path-bin", "--profile", "runtime-readonly", "--format", "json"],
        text=True, capture_output=True
    )

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    check = next(c for c in payload["checks"] if c["destination"] == str(system_commands))
    assert check["extra"] == ["stale.md"]


def test_runtime_profile_checks_only_active_codex_adapter(tmp_path: Path):
    source_root = tmp_path / "source"
    _write_checkout_identity(source_root)
    codex_skill = source_root / "adapters" / "codex" / "skill" / "crew:run"
    codex_skill.mkdir(parents=True, exist_ok=True)
    (codex_skill / "SKILL.md").write_text("codex\n", encoding="utf-8")
    claude_adapter = source_root / "adapters" / "claude"
    claude_adapter.mkdir(parents=True)
    (claude_adapter / "stale-sensitive.txt").write_text("source\n", encoding="utf-8")
    installed_skill = tmp_path / "codex" / "skills" / "crew:run"
    installed_skill.mkdir(parents=True)
    (installed_skill / "SKILL.md").write_text("codex\n", encoding="utf-8")

    result = subprocess.run(
        ["python3", str(SCRIPT), "--source-root", str(source_root),
         "--agent-crew-home", str(tmp_path / "home"), "--codex-home", str(tmp_path / "codex"),
         "--active-host", "codex", "--skip-path-bin", "--profile", "runtime-readonly",
         "--format", "json"], text=True, capture_output=True
    )

    payload = json.loads(result.stdout)
    assert result.returncode == 1
    assert payload["status"] == "MISMATCH"
    assert payload["active_host"] == "codex"
    assert all("claude" not in c["source"] for c in payload["checks"])


def test_runtime_fingerprint_ignores_shared_destination_extra_changes(tmp_path: Path):
    source_root = tmp_path / "source"
    _write_checkout_identity(source_root)
    (source_root / "core" / "commands").mkdir(parents=True, exist_ok=True)
    (source_root / "core" / "commands" / "run.md").write_text("run\n", encoding="utf-8")
    home = tmp_path / "home"
    for destination in (home / "system" / "commands", home / "commands"):
        destination.mkdir(parents=True)
        (destination / "run.md").write_text("run\n", encoding="utf-8")
    shared = home / "commands" / "personal.md"
    shared.write_text("first\n", encoding="utf-8")

    def detect():
        return subprocess.run(
            ["python3", str(SCRIPT), "--source-root", str(source_root),
             "--agent-crew-home", str(home), "--active-host", "none", "--skip-path-bin",
             "--profile", "runtime-readonly", "--format", "json"],
            text=True, capture_output=True,
        )

    first = detect()
    shared.write_text("second\n", encoding="utf-8")
    second = detect()

    assert json.loads(first.stdout)["install_fingerprint"] == json.loads(second.stdout)["install_fingerprint"]


def test_partial_checkout_unknown_is_failed_in_json_and_text(tmp_path: Path):
    partial = tmp_path / "partial"
    (partial / "core").mkdir(parents=True)
    json_result = subprocess.run(
        ["python3", str(SCRIPT), "--source-root", str(partial), "--profile", "runtime-readonly", "--format", "json"],
        text=True, capture_output=True,
    )
    text_result = subprocess.run(
        ["python3", str(SCRIPT), "--source-root", str(partial), "--profile", "runtime-readonly", "--format", "text"],
        text=True, capture_output=True,
    )

    assert json_result.returncode == 2
    assert json.loads(json_result.stdout)["passed"] is False
    assert text_result.returncode == 2
    assert text_result.stdout.startswith("UNKNOWN:")


def test_empty_required_trees_with_only_launcher_markers_are_unknown(tmp_path: Path):
    source = tmp_path / "sparse"
    (source / "core" / "bin").mkdir(parents=True)
    (source / "core" / "scripts").mkdir(parents=True)
    for rel in ("core/commands", "core/rules", "adapters/codex/skill"):
        (source / rel).mkdir(parents=True)
    (source / "install.sh").write_text("installer\n", encoding="utf-8")
    (source / "core" / "bin" / "crew").write_text(
        "deterministic shell entrypoint for agent-crew\n", encoding="utf-8"
    )
    (source / "core" / "scripts" / "sync-local-install.sh").write_text(
        "sync-local-install.sh\n", encoding="utf-8"
    )

    result = subprocess.run(
        ["python3", str(SCRIPT), "--source-root", str(source), "--profile", "runtime-readonly", "--format", "json"],
        text=True, capture_output=True,
    )

    assert result.returncode == 2
    assert json.loads(result.stdout)["status"] == "UNKNOWN"


def test_runtime_source_inventory_missing_non_sentinel_file_is_unknown(tmp_path: Path):
    source = tmp_path / "source"
    _write_checkout_identity(source)
    missing = source / "core" / "scripts" / "non-sentinel-required.py"
    inventory = source / "core" / "schemas" / "runtime-managed-source-inventory.json"
    payload = json.loads(inventory.read_text(encoding="utf-8"))
    payload["files"].append(str(missing.relative_to(source)))
    inventory.write_text(json.dumps(payload), encoding="utf-8")

    result = subprocess.run(
        ["python3", str(SCRIPT), "--source-root", str(source), "--profile", "runtime-readonly", "--format", "json"],
        text=True, capture_output=True,
    )

    assert result.returncode == 2
    assert json.loads(result.stdout)["status"] == "UNKNOWN"


def test_claude_managed_settings_hook_requires_exact_command(tmp_path: Path):
    claude = tmp_path / "claude"
    settings = claude / "settings.json"
    settings.parent.mkdir(parents=True)
    settings.write_text(json.dumps({"hooks": {"PreToolUse": [{"matcher": "Agent", "hooks": [{
        "type": "command", "command": f"echo {claude / 'agent-crew/hooks/agent-diff-pre.sh'}", "timeout": 5
    }]}]}}), encoding="utf-8")

    check = module.compare_claude_managed_hooks(settings, claude)

    assert check["passed"] is False
    assert check["projection"]


def test_codex_marker_owned_stale_generated_agent_is_reported(tmp_path: Path):
    home = tmp_path / "home"
    destination = tmp_path / "codex" / "agents"
    destination.mkdir(parents=True)
    subprocess.run([
        "python3", str(REPO_ROOT / "core/scripts/generate-codex-system-agents.py"),
        str(REPO_ROOT / "core/agents"), str(destination),
        "--source-ref-root", str(home / "system/agents"),
        "--model-policy", str(REPO_ROOT / "adapters/codex/model-policy.json"),
    ], check=True, capture_output=True, text=True)
    (destination / "stale.toml").write_text(
        'developer_instructions = "This is a Codex adapter bootstrap for the agent-crew system agent."\n',
        encoding="utf-8",
    )

    check = module.compare_codex_generated_agents(REPO_ROOT, home, destination)

    assert check["passed"] is False
    assert check["extra"] == ["stale.toml"]


def test_codex_generated_user_agent_is_expected_until_its_source_is_removed(tmp_path: Path):
    home = tmp_path / "home"
    user_agents = home / "user" / "agents"
    system_agents = home / "system" / "agents"
    destination = tmp_path / "codex" / "agents"
    user_agents.mkdir(parents=True)
    system_agents.mkdir(parents=True)
    destination.mkdir(parents=True)
    user_source = user_agents / "custom-agent.md"
    user_source.write_text("---\ndescription: custom\n---\ncustom instructions\n", encoding="utf-8")
    subprocess.run([
        "python3", str(REPO_ROOT / "core/scripts/generate-codex-system-agents.py"),
        str(REPO_ROOT / "core/agents"), str(destination),
        "--source-ref-root", str(system_agents),
        "--model-policy", str(REPO_ROOT / "adapters/codex/model-policy.json"),
    ], check=True, capture_output=True, text=True)
    subprocess.run([
        "python3", str(REPO_ROOT / "core/scripts/generate-codex-user-agents.py"),
        str(user_agents), str(destination), "--system-agents-dir", str(system_agents),
    ], check=True, capture_output=True, text=True)

    assert module.compare_codex_generated_agents(REPO_ROOT, home, destination)["passed"] is True

    user_source.unlink()
    stale = module.compare_codex_generated_agents(REPO_ROOT, home, destination)

    assert stale["passed"] is False
    assert stale["extra"] == ["custom-agent.toml"]


def test_codex_user_agent_content_change_updates_source_fingerprint(tmp_path: Path):
    home = tmp_path / "home"
    user_agents = home / "user" / "agents"
    destination = tmp_path / "codex" / "agents"
    user_agents.mkdir(parents=True)
    destination.mkdir(parents=True)
    source = user_agents / "custom-agent.md"
    source.write_text("---\ndescription: custom\n---\nfirst\n", encoding="utf-8")

    first = module.compare_codex_generated_agents(REPO_ROOT, home, destination)
    first_fingerprint = module.source_projection_fingerprint([first])
    source.write_text("---\ndescription: custom\n---\nsecond\n", encoding="utf-8")
    second = module.compare_codex_generated_agents(REPO_ROOT, home, destination)

    assert first["source_projection"] != second["source_projection"]
    assert first_fingerprint != module.source_projection_fingerprint([second])


def test_runtime_profile_checks_all_managed_path_cli_candidates(tmp_path: Path):
    source = tmp_path / "source"
    _write_checkout_identity(source)
    latest = source / "core" / "bin" / "crew"
    default_cli = tmp_path / "default" / "crew"
    path_cli = tmp_path / "path" / "crew"
    for cli in (default_cli, path_cli):
        cli.parent.mkdir(parents=True)
        cli.write_text(latest.read_text(encoding="utf-8"), encoding="utf-8")
    path_cli.write_text(path_cli.read_text(encoding="utf-8") + "stale\n", encoding="utf-8")

    result = subprocess.run(
        ["python3", str(SCRIPT), "--source-root", str(source), "--agent-crew-home", str(tmp_path / "home"),
         "--active-host", "none", "--profile", "runtime-readonly", "--format", "json",
         "--managed-path-cli", str(default_cli), "--managed-path-cli", str(path_cli)],
        text=True, capture_output=True,
    )

    payload = json.loads(result.stdout)
    assert result.returncode == 1
    assert any(check["destination"] == str(path_cli) and not check["passed"] for check in payload["checks"])


def test_codex_managed_hooks_corruption_is_detected(tmp_path: Path):
    hooks = tmp_path / "codex" / "hooks.json"
    hooks.parent.mkdir(parents=True)
    hooks.write_text('{"hooks": {}}\n', encoding="utf-8")

    check = module.compare_codex_managed_hooks(hooks, tmp_path / "home")

    assert check["passed"] is False
    assert check["mismatched"] == [str(hooks)]


def test_unrelated_user_hook_cannot_satisfy_codex_managed_hooks(tmp_path: Path):
    hooks = tmp_path / "hooks.json"
    hooks.write_text(json.dumps({"hooks": {"UserPromptSubmit": [{"hooks": [
        {"type": "command", "command": "echo auto-route.sh", "timeout": 15}
    ]}]}}), encoding="utf-8")

    check = module.compare_codex_managed_hooks(hooks, tmp_path / "home")

    assert check["passed"] is False


def test_exact_managed_hook_path_with_wrong_executable_is_rejected_and_fingerprinted(tmp_path: Path):
    hooks = tmp_path / "hooks.json"
    home = tmp_path / "home"

    tracker = "mcp__plane__create_work_item|mcp__plane__update_work_item|mcp__plane__delete_work_item|mcp__plane__create_intake_work_item|mcp__plane__create_label|mcp__plane__create_work_item_comment|mcp__plane.create_work_item|mcp__plane.update_work_item|mcp__plane.delete_work_item|mcp__plane.create_intake_work_item|mcp__plane.create_label|mcp__plane.create_work_item_comment"

    def command(name: str, timeout: int, executable: str = "bash") -> dict:
        return {"type": "command", "command": f"{executable} '{home / 'hooks' / name}'", "timeout": timeout}

    def projection(executable: str) -> dict:
        payload = {"hooks": {
            "PreToolUse": [
                {"matcher": "Bash", "hooks": [command("guard-dangerous-commands.sh", 10)]},
                {"matcher": tracker, "hooks": [command("tracker-mutation-guard.sh", 10)]},
                {"matcher": "Agent", "hooks": [command("context-guard.sh", 10)]},
                {"matcher": "Edit|Write|MultiEdit|apply_patch", "hooks": [command("direct-edit-guard.sh", 10)]},
            ],
            "PostToolUse": [{"matcher": "*", "hooks": [command("post-tool-use-dispatcher.sh", 15)]}],
            "UserPromptSubmit": [{"hooks": [
                command("general-memory-context.sh", 10),
                command("auto-issue-report.sh", 10),
                command("auto-route.sh", 15, executable),
            ]}],
        }}
        hooks.write_text(json.dumps(payload), encoding="utf-8")
        return module.compare_codex_managed_hooks(hooks, home)

    valid = projection("bash")
    echo = projection("echo")
    false = projection("false")

    assert valid["passed"] is True
    assert echo["passed"] is False
    assert false["passed"] is False
    assert echo["projection"] != false["projection"]


def test_duplicate_managed_hook_with_mixed_timeout_types_is_invalid_without_crashing(tmp_path: Path):
    hooks = tmp_path / "hooks.json"
    home = tmp_path / "home"
    command = f"bash '{home / 'hooks' / 'auto-route.sh'}'"
    hooks.write_text(json.dumps({"hooks": {"UserPromptSubmit": [{"hooks": [
        {"type": "command", "command": command, "timeout": 15},
        {"type": "command", "command": command, "timeout": None},
    ]}]}}), encoding="utf-8")

    check = module.compare_codex_managed_hooks(hooks, home)

    assert check["passed"] is False
    assert check["mismatched"] == [str(hooks)]


def test_malformed_codex_hooks_fail_and_change_semantic_fingerprint(tmp_path: Path):
    hooks = tmp_path / "hooks.json"
    hooks.write_text("{", encoding="utf-8")
    malformed = module.compare_codex_managed_hooks(hooks, tmp_path / "home")
    hooks.write_text(json.dumps({"hooks": {}}), encoding="utf-8")
    empty = module.compare_codex_managed_hooks(hooks, tmp_path / "home")

    assert malformed["passed"] is False
    assert malformed["projection"] != empty["projection"]


def test_unified_system_skill_corruption_is_detected_without_flagging_user_skill(tmp_path: Path):
    source_skills = tmp_path / "source" / "core" / "agents" / "skills"
    source_skills.mkdir(parents=True)
    (source_skills / "tdd.md").write_text("canonical\n", encoding="utf-8")
    unified = tmp_path / "home" / "skills"
    unified.mkdir(parents=True)
    (unified / "tdd.md").write_text("corrupt\n", encoding="utf-8")
    (unified / "personal.md").write_text("preserve\n", encoding="utf-8")

    check = module.compare_expected_trees([source_skills], unified)

    assert check["passed"] is False
    assert check["mismatched"] == ["tdd.md"]
    assert check["extra"] == []


def test_unified_skill_uses_user_override_precedence(tmp_path: Path):
    system = tmp_path / "system"
    user = tmp_path / "user"
    unified = tmp_path / "unified"
    for root in (system, user, unified):
        root.mkdir()
    (system / "tdd.md").write_text("system\n", encoding="utf-8")
    (user / "tdd.md").write_text("override\n", encoding="utf-8")
    (unified / "tdd.md").write_text("override\n", encoding="utf-8")
    (unified / "personal.md").write_text("preserve\n", encoding="utf-8")

    check = module.compare_merged_expected_flat_files(system, user, unified)

    assert check["passed"] is True
    assert check["extra"] == []
