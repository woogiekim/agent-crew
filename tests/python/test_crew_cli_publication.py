"""A new invocation must see the new CLI while open readers see the old one."""
from pathlib import Path
import os
import runpy
import subprocess

import pytest

from tests.python.test_runtime_install_baseline import ROOT, install_update_fixture, invoke, output


def prepare_upgrade(tmp_path, *, install_path_cli):
    release, project, home, env = install_update_fixture(tmp_path, install_path_cli=install_path_cli)
    source_cli = release / "core/bin/crew"
    installed_cli = home / "bin/crew"
    old_cli = installed_cli.read_bytes()
    header, marker, body = old_cli.split(b"\n", 2)
    padding = b': "' + b'x' * (2 * len(old_cli)) + b'"\n'
    new_cli = b"\n".join((header, marker, padding + body))
    source_cli.write_bytes(new_cli)
    assert source_cli.read_bytes() != installed_cli.read_bytes()

    user_command = home / "user/commands/run.md"
    user_command.write_text("사용자 명령\n")
    agent = Path(env["CODEX_HOME"]) / "agents/reviewer.toml"
    backup = agent.with_suffix(".toml.bak-preserve")
    backup.write_bytes(agent.read_bytes())
    user_files = {path: path.read_bytes() for path in (user_command, backup)}
    return release, project, env, installed_cli, new_cli, user_files


@pytest.fixture
def release_upgrade(tmp_path):
    return prepare_upgrade(tmp_path, install_path_cli=True)


def verify_replaced_cli(opened, old_bytes, dest, new_bytes):
    assert opened.read() == old_bytes, f"열려 있던 CLI가 덮어써졌습니다: {dest.name}"
    assert os.fstat(opened.fileno()).st_ino != dest.stat().st_ino
    assert dest.read_bytes() == new_bytes
    assert os.access(dest, os.X_OK)


def verify_update(release_upgrade, update_args, expected_output, overrides=None):
    _, project, env, cli, new_bytes, user_files = release_upgrade
    path_cli = Path(env["AGENT_CREW_PATH_BIN"]) / "crew"
    old_bytes = cli.read_bytes()

    with cli.open("rb") as opened, path_cli.open("rb") as opened_path_cli:
        result = invoke([str(cli), "update", *update_args], env | (overrides or {}), project)

        assert result.returncode == 0 and "unexpected EOF" not in result.stderr, output(result)
        assert "PASS: install drift check" in result.stdout and expected_output in result.stdout, output(result)
        verify_replaced_cli(opened, old_bytes, cli, new_bytes)
        verify_replaced_cli(opened_path_cli, old_bytes, path_cli, new_bytes)

    new_process = invoke([str(cli), "update", "--help"], env, project)
    assert new_process.returncode == 0 and "usage: crew update" in new_process.stdout, output(new_process)
    for file, old_bytes in user_files.items():
        assert file.read_bytes() == old_bytes


def test_local_update_finishes_when_running_crew_is_replaced(release_upgrade):
    release = release_upgrade[0]
    verify_update(release_upgrade, ["--local", str(release)], "refreshed installed assets")


def test_default_update_finishes_when_running_crew_is_replaced(release_upgrade, tmp_path):
    release, _, env, _, _, _ = release_upgrade
    git_env = {key: value for key, value in env.items() if not key.startswith("GIT_")}

    for args in (
        ["init", "-q"],
        ["add", "--", "core", "adapters", "install.sh"],
        ["-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "-qm", "fixture release"],
    ):
        result = invoke(["git", *args], git_env, release)
        assert result.returncode == 0, output(result)

    temp = tmp_path / "clones"
    temp.mkdir()
    verify_update(release_upgrade, [], "update_phase: remote_total=", {
        "TMPDIR": str(temp),
        "GIT_ALLOW_PROTOCOL": "file",
        "GIT_CONFIG_COUNT": "1",
        "GIT_CONFIG_KEY_0": f"url.{release.resolve().as_uri()}.insteadOf",
        "GIT_CONFIG_VALUE_0": "https://github.com/woogiekim/agent-crew",
    })


def test_reinstall_preserves_open_managed_cli_handles(release_upgrade):
    release, project, env, cli, new_bytes, user_files = release_upgrade
    path_cli = Path(env["AGENT_CREW_PATH_BIN"]) / "crew"
    old_bytes = cli.read_bytes()

    with cli.open("rb") as opened, path_cli.open("rb") as opened_path_cli:
        result = invoke(["bash", str(release / "install.sh")], env | {
            "AGENT_CREW_MODE": "update",
            "AGENT_CREW_INSTALL_CLAUDE_COMPAT": "0",
        }, project)

        assert result.returncode == 0, output(result)
        verify_replaced_cli(opened, old_bytes, cli, new_bytes)
        verify_replaced_cli(opened_path_cli, old_bytes, path_cli, new_bytes)

    for file, old_bytes in user_files.items():
        assert file.read_bytes() == old_bytes


def test_legacy_runtime_sync_preserves_open_cli_handle(release_upgrade):
    release, project, env, cli, new_bytes, _ = release_upgrade
    old_bytes = cli.read_bytes()

    with cli.open("rb") as opened:
        result = invoke([str(cli), "cleanup-host-bridge"], env | {
            "AGENT_CREW_SOURCE_DIR": str(release),
        }, project)

        assert result.returncode == 0, output(result)
        assert "refreshed runtime assets from source checkout" in result.stderr
        verify_replaced_cli(opened, old_bytes, cli, new_bytes)


@pytest.mark.parametrize("kind", ["file", "symlink"])
def test_update_preserves_unmanaged_path_cli(tmp_path, kind):
    release, project, env, cli, new_bytes, _ = prepare_upgrade(tmp_path, install_path_cli=False)
    user_dir = tmp_path / "user-bin"
    user_dir.mkdir()
    user_cli = user_dir / "crew"
    personal = b"#!/bin/sh\necho personal\n"
    target = tmp_path / "personal"
    if kind == "file":
        user_cli.write_bytes(personal)
    else:
        target.write_bytes(personal)
        user_cli.symlink_to(target)

    env.pop("AGENT_CREW_SKIP_PATH_CLI")
    result = invoke([str(cli), "update", "--local", str(release)], env | {
        "AGENT_CREW_PATH_BIN": str(user_dir),
    }, project)

    assert result.returncode == 0, output(result)
    assert user_cli.read_bytes() == personal
    assert user_cli.is_symlink() == (kind == "symlink")
    assert cli.read_bytes() == new_bytes


@pytest.mark.parametrize("installed_publisher", [True, False])
def test_legacy_sync_without_source_publisher(release_upgrade, installed_publisher):
    release, project, env, cli, new_bytes, _ = release_upgrade
    (release / "core/scripts/publish-crew-cli.py").unlink()
    if not installed_publisher:
        (cli.parent.parent / "scripts/publish-crew-cli.py").unlink()
    old_bytes = cli.read_bytes()

    with cli.open("rb") as opened:
        result = invoke([str(cli), "cleanup-host-bridge"], env | {
            "AGENT_CREW_SOURCE_DIR": str(release),
        }, project)

        if installed_publisher:
            assert result.returncode == 0, output(result)
            verify_replaced_cli(opened, old_bytes, cli, new_bytes)
        else:
            assert result.returncode != 0 and "publish-crew-cli.py" in output(result), output(result)
            assert opened.read() == cli.read_bytes() == old_bytes


def test_publication_failure_keeps_old_cli_and_retry_publishes(tmp_path, monkeypatch):
    publish = runpy.run_path(str(ROOT / "core/scripts/publish-crew-cli.py"))["publish"]
    source = tmp_path / "release"
    source.write_bytes(b"new CLI\n")
    installed = tmp_path / "crew"
    installed.write_bytes(b"old CLI\n")
    installed.chmod(0o711)
    before = installed.stat()

    def fail_replace(temp, dest):
        assert Path(temp).read_bytes() == source.read_bytes()
        assert os.access(temp, os.X_OK)
        raise PermissionError("fixture publication failure")

    with monkeypatch.context() as failure:
        failure.setattr(os, "replace", fail_replace)
        with pytest.raises(PermissionError, match="fixture publication failure"):
            publish(source, installed)

    assert installed.read_bytes() == b"old CLI\n"
    assert installed.stat().st_ino == before.st_ino and installed.stat().st_mode == before.st_mode
    assert set(tmp_path.iterdir()) == {source, installed}
    publish(source, installed)
    assert installed.read_bytes() == source.read_bytes()
    assert os.access(installed, os.X_OK)


@pytest.mark.parametrize("kind", ["directory", "symlink"])
def test_publication_rejects_unexpected_destination_shape(tmp_path, kind):
    helper = ROOT / "core/scripts/publish-crew-cli.py"
    source, installed, personal = (tmp_path / name for name in ("source", "crew", "personal"))
    source.write_bytes(b"new CLI\n")
    personal.write_bytes(b"personal\n")
    if kind == "directory":
        installed.mkdir()
    else:
        installed.symlink_to(personal)

    result = subprocess.run(["python3", str(helper), str(source), str(installed)], capture_output=True, text=True, timeout=10)

    assert result.returncode != 0 and "publish" in result.stderr, output(result)
    assert personal.read_bytes() == b"personal\n"
    if kind == "directory":
        assert installed.is_dir() and not list(installed.iterdir())
    else:
        assert installed.is_symlink() and installed.readlink() == personal
    assert set(tmp_path.iterdir()) == {source, installed, personal}
