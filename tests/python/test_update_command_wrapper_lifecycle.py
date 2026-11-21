"""Exercise command retirement through the public local-update entry point."""

import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
COMMAND = "retired-example"
TARGET = f"~/.agent-crew/commands/{COMMAND}.md"


def write(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def legacy_wrapper(host):
    prefix = "/crew:" if host == "claude" else "$crew:"
    command = f"{prefix}{COMMAND}"
    claude_fields = "disable-model-invocation: true\nuser-invocable: true\n" if host == "claude" else ""
    return (
        f"---\nname: {COMMAND}\ndescription: Use only when the user explicitly invokes {command}. "
        f"Loads the provider-neutral crew:{COMMAND} command.\n{claude_fields}---\n\n"
        f"# crew:{COMMAND}\n\nOrdinary natural language does not activate agent-crew.\n\n"
        f"1. Preserve all text after `{command}` as immutable raw input.\n"
        f"2. Read `{TARGET}` in full.\n"
        "3. Execute that provider-neutral definition without selecting another command.\n"
        "4. Do not load unrelated host/plugin skills without explicit user approval.\n"
    )


@pytest.fixture
def installation(tmp_path):
    source = tmp_path / "source"
    for directory in ("core", "adapters"):
        shutil.copytree(REPO_ROOT / directory, source / directory)
    shutil.copy2(REPO_ROOT / "install.sh", source / "install.sh")

    home = tmp_path / "crew"
    codex = tmp_path / "codex"
    claude = tmp_path / "claude"
    project = tmp_path / "project"
    project.mkdir()
    (claude / "agent-crew").mkdir(parents=True)
    env = {key: value for key, value in os.environ.items() if not key.startswith(("AGENT_CREW_", "MNEMOS_"))}
    env.update(
        AGENT_CREW_HOME=str(home),
        CODEX_HOME=str(codex),
        CLAUDE_DIR=str(claude),
        PROJECT_ROOT=str(project),
        AGENT_CREW_PATH_BIN=str(tmp_path / "bin"),
        AGENT_CREW_SKIP_PATH_CLI="1",
        AGENT_CREW_WRITE_INSTALL_MANIFEST="0",
        MNEMOS_BIN=str(tmp_path / "no-mnemos"),
    )

    def update():
        result = subprocess.run(
            ["bash", str(source / "core/bin/crew"), "update", "--local", str(source)],
            env=env, cwd=project, text=True, capture_output=True, timeout=50,
        )
        return result.returncode, result.stdout + result.stderr

    return source, home, codex, claude, update


def assert_update(update):
    rc, output = update()
    assert rc == 0, output
    return output


def old_release(source):
    command = write(source / f"core/commands/{COMMAND}.md", "previous system command\n")
    wrapper = write(source / f"adapters/codex/skill/{COMMAND}/SKILL.md", legacy_wrapper("codex"))
    return command, wrapper


def legacy_paths(home):
    root = home / "plugins/crew"
    for host, directory in (("claude", "skills"), ("codex", "skills-codex")):
        metadata = {"name": "crew", "author": {"name": "agent-crew"}}
        if host == "codex":
            metadata["skills"] = "./skills-codex/"
        write(root / f".{host}-plugin/plugin.json", json.dumps(metadata))
        yield root / f"{directory}/{COMMAND}/SKILL.md", legacy_wrapper(host)


def test_update_removes_retired_managed_wrappers_on_two_local_updates(installation, record_property):
    source, home, codex, claude, update = installation
    command, wrapper = old_release(source)
    assert_update(update)
    legacy = [write(path, body) for path, body in legacy_paths(home)]
    paths = [
        home / f"system/commands/{COMMAND}.md",
        home / f"commands/{COMMAND}.md",
        codex / f"skills/{COMMAND}/SKILL.md",
        claude / f"commands/crew/{COMMAND}.md",
        *legacy,
    ]
    assert all(path.is_file() for path in paths)
    companion = write(legacy[0].with_name("notes.md"), "user notes\n")
    protected = write(codex / "skills/personal/SKILL.md", f"Personal instructions mentioning {TARGET}\n")
    preserved = {path: path.read_bytes() for path in (companion, protected)}

    command.unlink()
    wrapper.unlink()
    observed = []
    for number in (1, 2):
        output = assert_update(update)
        observed.append([path.exists() for path in paths])
        record_property(f"update_{number}_exit", 0)
        record_property(f"update_{number}_missing_paths", observed[-1].count(False))
        record_property(f"update_{number}_fast_path", "skipped adapter refresh" in output)
        assert {path: path.read_bytes() for path in preserved} == preserved

    assert observed == [[False] * len(paths)] * 2, dict(zip(map(str, paths), observed[-1]))


def test_update_preserves_user_skills_overrides_and_companion_files(installation):
    source, home, codex, _, update = installation
    command, wrapper = old_release(source)
    assert_update(update)
    custom = write(codex / f"skills/{COMMAND}/SKILL.md", legacy_wrapper("codex") + "\nUser override.\n")
    companion = write(custom.with_name("notes.md"), "private note\n")
    user_skill = write(home / "user/skills/personal.md", f"User skill citing {TARGET}\n")
    saved = {path: path.read_bytes() for path in (custom, companion, user_skill)}

    command.unlink()
    wrapper.unlink()
    assert_update(update)

    assert {path: path.read_bytes() for path in saved} == saved


def test_update_preserves_valid_user_command_and_canonical_target_wrappers(installation):
    source, home, codex, claude, update = installation
    command, _ = old_release(source)
    assert_update(update)
    user_command = write(home / f"user/commands/{COMMAND}.md", "user command\n")

    command.unlink()
    assert_update(update)

    assert (home / f"commands/{COMMAND}.md").read_bytes() == user_command.read_bytes()
    assert (codex / f"skills/{COMMAND}/SKILL.md").is_file()
    assert (claude / f"commands/{COMMAND}.md").is_file()
    assert (codex / "skills/crew:run/SKILL.md").is_file()


def test_update_rejects_shipped_wrapper_with_missing_target(installation):
    source, home, _, _, update = installation
    command, _ = old_release(source)
    assert_update(update)
    assert (home / f"commands/{COMMAND}.md").is_file()

    command.unlink()
    rc, output = update()

    assert rc != 0, output
    assert f"skill/{COMMAND}/SKILL.md" in output and f"{COMMAND}.md" in output


def test_noop_update_validates_dangling_managed_wrappers(installation):
    _, home, _, _, update = installation
    assert_update(update)
    assert "skipped adapter refresh" in assert_update(update)
    path, body = next(legacy_paths(home))
    write(path, body)

    rc, output = update()

    assert rc != 0, output
    assert str(path) in output and f"{COMMAND}.md" in output


def test_update_does_not_follow_wrapper_symlinks_outside_install(installation, tmp_path):
    source, home, _, _, update = installation
    command, wrapper = old_release(source)
    assert_update(update)
    external = write(tmp_path / "external/SKILL.md", legacy_wrapper("claude"))
    path, _ = next(legacy_paths(home))
    path.parent.parent.mkdir(parents=True, exist_ok=True)
    path.parent.symlink_to(external.parent, target_is_directory=True)

    command.unlink()
    wrapper.unlink()
    assert_update(update)

    assert external.read_text() == legacy_wrapper("claude")
    assert path.parent.is_symlink()


def test_retained_codex_wrapper_symlink_is_never_pruned_or_copied_through(installation, tmp_path):
    source, home, codex, _, update = installation
    assert_update(update)

    managed = codex / "skills/crew:run"
    outside = tmp_path / "outside"
    managed.rename(outside)
    notes = write(outside / "notes.md", "outside user data\n")
    installed_wrapper = outside / "SKILL.md"
    original = installed_wrapper.read_bytes()
    managed.symlink_to(outside, target_is_directory=True)

    result = subprocess.run(
        ["python3", str(source / "core/scripts/verify-install-drift.py"),
         "--source-root", str(source), "--agent-crew-home", str(home),
         "--codex-home", str(codex), "--skip-path-bin", "--prune-extra"],
        text=True, capture_output=True, timeout=20,
    )
    assert result.returncode != 0, result.stdout + result.stderr
    assert "crew:run" in result.stdout
    assert notes.read_text() == "outside user data\n"
    assert installed_wrapper.read_bytes() == original

    rc, output = update()
    assert rc != 0 and "crew:run" in output, output
    assert managed.is_symlink() and managed.resolve() == outside.resolve()
    assert notes.read_text() == "outside user data\n"
    assert installed_wrapper.read_bytes() == original


def test_noop_update_does_not_accept_a_retired_claude_namespaced_command(installation):
    source, _, _, claude, update = installation
    command, wrapper = old_release(source)
    assert_update(update)
    retired = claude / f"commands/crew/{COMMAND}.md"
    old_contents = retired.read_text()
    user = write(claude / f"commands/{COMMAND}.md", "personal command\n")

    command.unlink()
    wrapper.unlink()
    assert_update(update)
    assert not retired.exists()
    write(retired, old_contents)

    rc, output = update()

    assert rc != 0, output
    assert "commands/crew" in output and f"{COMMAND}.md" in output
    assert user.read_text() == "personal command\n"
