#!/usr/bin/env python3
"""Quarantine ownership-proven legacy project-local agent-crew assets."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from project_state import project_state_key


SCANNED_ROOTS = (
    Path(".agent-crew"),
    Path(".codex"),
    Path(".claude/agents"),
)
CODEX_SYSTEM_AGENT_MARKER = (
    "This is a Codex adapter bootstrap for the agent-crew system agent."
)
MANAGED_HOOK_NAMES = {
    "auto-issue-report.sh",
    "auto-route.sh",
    "context-guard.sh",
    "direct-edit-guard.sh",
    "guard-dangerous-commands.sh",
    "post-tool-use-dispatcher.sh",
    "tracker-mutation-guard.sh",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Move only ownership-proven legacy project-local assets to a recoverable backup."
    )
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--agent-crew-home", required=True)
    parser.add_argument("--codex-home", required=True)
    parser.add_argument("--claude-dir", required=True)
    parser.add_argument("--fingerprints", required=True)
    parser.add_argument("--mode", required=True, choices=("setup", "update"))
    return parser.parse_args()


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temp_path = Path(temp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
        os.replace(temp_path, path)
    finally:
        if temp_path.exists():
            temp_path.unlink()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git_blob_sha(path: Path) -> str:
    data = path.read_bytes()
    prefix = b"blob " + str(len(data)).encode("ascii") + b"\0"
    return hashlib.sha1(prefix + data).hexdigest()


def path_evidence(path: Path) -> dict[str, str]:
    if path.is_symlink():
        target = os.readlink(path)
        return {
            "kind": "symlink",
            "link_target": target,
            "sha256": hashlib.sha256(target.encode("utf-8")).hexdigest(),
        }
    return {"kind": "file", "sha256": sha256_file(path)}


def load_fingerprints(path: Path) -> dict[str, set[str]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return {}
    paths = payload.get("paths") if isinstance(payload, dict) else None
    if not isinstance(paths, dict):
        return {}
    return {
        str(relative): {str(value) for value in values if isinstance(value, str)}
        for relative, values in paths.items()
        if isinstance(values, list)
    }


def git_tracked_paths(project_root: Path) -> tuple[Path, set[str]] | None:
    top_result = subprocess.run(
        ["git", "-C", str(project_root), "rev-parse", "--show-toplevel"],
        check=False,
        capture_output=True,
        text=True,
    )
    if top_result.returncode != 0:
        return None
    git_root = Path(top_result.stdout.strip()).resolve()
    tracked_result = subprocess.run(
        ["git", "-C", str(git_root), "ls-files", "--cached", "-z"],
        check=False,
        capture_output=True,
    )
    if tracked_result.returncode != 0:
        return None
    tracked = {
        value.decode("utf-8", errors="surrogateescape")
        for value in tracked_result.stdout.split(b"\0")
        if value
    }
    return git_root, tracked


def iter_leaf_paths(project_root: Path) -> Iterable[Path]:
    for relative_root in SCANNED_ROOTS:
        root = project_root / relative_root
        if root.is_symlink() or root.is_file():
            yield root
            continue
        if not root.is_dir():
            continue
        for current, dir_names, file_names in os.walk(root, followlinks=False):
            current_path = Path(current)
            for name in list(dir_names):
                candidate = current_path / name
                if candidate.is_symlink():
                    yield candidate
                    dir_names.remove(name)
            for name in file_names:
                yield current_path / name


def expected_files(
    relative: Path,
    agent_crew_home: Path,
    codex_home: Path,
    claude_dir: Path,
) -> list[Path]:
    parts = relative.parts
    if len(parts) >= 4 and parts[:3] == (".agent-crew", "agents", "skills"):
        tail = Path(*parts[3:])
        return [
            agent_crew_home / "system/skills" / tail,
            agent_crew_home / "user/skills" / tail,
            agent_crew_home / "skills" / tail,
            agent_crew_home / "system/agents/skills" / tail,
        ]
    if len(parts) >= 3 and parts[:2] == (".agent-crew", "skills"):
        tail = Path(*parts[2:])
        return [
            agent_crew_home / "system/skills" / tail,
            agent_crew_home / "user/skills" / tail,
            agent_crew_home / "skills" / tail,
        ]
    if len(parts) >= 3 and parts[:2] == (".agent-crew", "agents"):
        tail = Path(*parts[2:])
        return [
            agent_crew_home / "system/agents" / tail,
            agent_crew_home / "user/agents" / tail,
        ]
    if len(parts) >= 3 and parts[:2] == (".agent-crew", "commands"):
        tail = Path(*parts[2:])
        return [
            agent_crew_home / "system/commands" / tail,
            agent_crew_home / "user/commands" / tail,
            agent_crew_home / "commands" / tail,
        ]
    if len(parts) >= 3 and parts[0] == ".agent-crew" and parts[1] in {
        "adapters",
        "hooks",
        "policies",
        "rules",
        "schemas",
        "scripts",
        "setup",
    }:
        tail = Path(*parts[1:])
        return [agent_crew_home / tail, agent_crew_home / "system" / tail]
    if relative == Path(".codex/README.md"):
        return [codex_home / "README.md", agent_crew_home / "adapters/codex/template/README.md"]
    if relative == Path(".codex/config.toml"):
        return [agent_crew_home / "adapters/codex/template/config.toml"]
    if relative == Path(".codex/hooks.json"):
        return [codex_home / "hooks.json"]
    if len(parts) >= 3 and parts[:2] == (".codex", "agents"):
        tail = Path(*parts[2:])
        return [codex_home / "agents" / tail, agent_crew_home / "adapters/codex/template/agents" / tail]
    if len(parts) >= 3 and parts[:2] == (".codex", "skills"):
        tail = Path(*parts[2:])
        return [codex_home / "skills" / tail, agent_crew_home / "adapters/codex/skill" / tail]
    if len(parts) >= 3 and parts[:2] == (".claude", "agents"):
        tail = Path(*parts[2:])
        return [
            claude_dir / "agents" / tail,
            agent_crew_home / "system/agents" / tail,
            agent_crew_home / "user/agents" / tail,
        ]
    return []


def known_link_targets(agent_crew_home: Path, codex_home: Path) -> set[Path]:
    return {
        (agent_crew_home / relative).resolve()
        for relative in (
            "commands",
            "hooks",
            "skills",
            "system/agents",
            "system/commands",
            "system/hooks",
            "system/skills",
            "user/agents",
            "user/commands",
            "user/skills",
        )
    } | {
        (codex_home / relative).resolve()
        for relative in ("agents", "skills", "agent-crew/skills")
    }


def is_strictly_managed_hooks_json(path: Path, agent_crew_home: Path) -> bool:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return False
    if not isinstance(payload, dict) or set(payload) != {"hooks"}:
        return False
    hooks = payload.get("hooks")
    if not isinstance(hooks, dict) or not hooks:
        return False

    managed_paths = {
        str(agent_crew_home / layer / name)
        for layer in ("hooks", "system/hooks")
        for name in MANAGED_HOOK_NAMES
    }
    saw_hook = False
    for blocks in hooks.values():
        if not isinstance(blocks, list):
            return False
        for block in blocks:
            if not isinstance(block, dict) or not set(block).issubset({"matcher", "hooks"}):
                return False
            hook_entries = block.get("hooks")
            if not isinstance(hook_entries, list) or not hook_entries:
                return False
            for hook in hook_entries:
                if not isinstance(hook, dict) or hook.get("type") != "command":
                    return False
                try:
                    tokens = shlex.split(str(hook.get("command") or ""))
                except ValueError:
                    return False
                if not any(token in managed_paths for token in tokens):
                    return False
                saw_hook = True
    return saw_hook


def ownership_reason(
    source: Path,
    relative: Path,
    fingerprints: dict[str, set[str]],
    agent_crew_home: Path,
    codex_home: Path,
    claude_dir: Path,
) -> str | None:
    if source.is_symlink():
        try:
            target = source.resolve(strict=False)
        except OSError:
            return None
        if target in known_link_targets(agent_crew_home, codex_home):
            return "known_global_symlink"
        return None

    if not source.is_file():
        return None
    if (
        len(relative.parts) >= 3
        and relative.parts[:2] == (".codex", "agents")
        and source.suffix == ".toml"
        and CODEX_SYSTEM_AGENT_MARKER
        in source.read_text(encoding="utf-8", errors="replace")
    ):
        return "codex_system_agent_marker"
    if relative == Path(".codex/hooks.json"):
        if is_strictly_managed_hooks_json(source, agent_crew_home):
            return "codex_managed_hook_commands"
        return None
    if relative == Path(".agent-crew/invocation.md"):
        current_generic_invocation = agent_crew_home / "adapters/generic/invocation.md"
        if (
            current_generic_invocation.is_file()
            and sha256_file(source) == sha256_file(current_generic_invocation)
        ):
            return None
    for expected in expected_files(relative, agent_crew_home, codex_home, claude_dir):
        if expected.is_file() and sha256_file(source) == sha256_file(expected):
            return f"matches_global:{expected}"
    if git_blob_sha(source) in fingerprints.get(relative.as_posix(), set()):
        return "matches_legacy_fingerprint"
    return None


def unique_backup_root(agent_crew_home: Path, project_root: Path) -> Path:
    parent = agent_crew_home / "backups/project-assets" / project_state_key(project_root)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    candidate = parent / timestamp
    suffix = 1
    while candidate.exists():
        candidate = parent / f"{timestamp}-{suffix}"
        suffix += 1
    return candidate


def remove_empty_scaffold_dirs(project_root: Path) -> list[str]:
    removed: list[str] = []
    roots = [project_root / value for value in SCANNED_ROOTS]
    for root in roots:
        if not root.is_dir() or root.is_symlink():
            continue
        directories = [Path(current) for current, _, _ in os.walk(root, topdown=False)]
        for directory in directories:
            try:
                directory.rmdir()
            except OSError:
                continue
            removed.append(directory.relative_to(project_root).as_posix())
    return removed


def migrate(args: argparse.Namespace) -> int:
    project_root = Path(args.project_root).expanduser().resolve()
    agent_crew_home = Path(args.agent_crew_home).expanduser().resolve()
    codex_home = Path(args.codex_home).expanduser().resolve()
    claude_dir = Path(args.claude_dir).expanduser().resolve()
    fingerprints = load_fingerprints(Path(args.fingerprints))

    git_state = git_tracked_paths(project_root)
    leaves = sorted(iter_leaf_paths(project_root), key=lambda value: str(value))
    if git_state is None:
        print(
            f"project_asset_migration: moved=0 preserved={len(leaves)} skipped=git_status_unavailable"
        )
        return 0

    git_root, tracked = git_state
    move_plan: list[dict[str, Any]] = []
    preserved = 0
    for source in leaves:
        relative = source.relative_to(project_root)
        try:
            git_relative = source.relative_to(git_root).as_posix()
        except ValueError:
            preserved += 1
            continue
        if git_relative in tracked:
            preserved += 1
            continue
        reason = ownership_reason(
            source,
            relative,
            fingerprints,
            agent_crew_home,
            codex_home,
            claude_dir,
        )
        if reason is None:
            preserved += 1
            continue
        move_plan.append(
            {
                "source_path": str(source),
                "relative_path": relative.as_posix(),
                "reason": reason,
                **path_evidence(source),
            }
        )

    if not move_plan:
        print(f"project_asset_migration: moved=0 preserved={preserved} backup=none")
        return 0

    backup_root = unique_backup_root(agent_crew_home, project_root)
    for entry in move_plan:
        entry["backup_path"] = str(backup_root / "files" / entry["relative_path"])
    atomic_write_json(
        backup_root / "plan.json",
        {
            "schema_version": 1,
            "status": "ready",
            "mode": args.mode,
            "project_root": str(project_root),
            "entries": move_plan,
        },
    )
    journal_entries = [
        {
            "source_path": entry["source_path"],
            "backup_path": entry["backup_path"],
            "relative_path": entry["relative_path"],
            "status": "pending",
        }
        for entry in move_plan
    ]
    atomic_write_json(
        backup_root / "journal.json",
        {
            "schema_version": 1,
            "status": "in_progress",
            "entries": journal_entries,
        },
    )

    moved: list[dict[str, Any]] = []
    try:
        for index, entry in enumerate(move_plan):
            source = Path(entry["source_path"])
            if not source.exists() and not source.is_symlink():
                raise RuntimeError(f"source disappeared before move: {source}")
            if path_evidence(source) != {
                key: entry[key]
                for key in ("kind", "sha256", "link_target")
                if key in entry
            }:
                raise RuntimeError(f"source changed before move: {source}")
            destination = Path(entry["backup_path"])
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(source), str(destination))
            moved.append(entry)
            if path_evidence(destination) != {
                key: entry[key]
                for key in ("kind", "sha256", "link_target")
                if key in entry
            }:
                raise RuntimeError(f"backup verification failed after move: {destination}")
            journal_entries[index]["status"] = "moved"
            atomic_write_json(
                backup_root / "journal.json",
                {
                    "schema_version": 1,
                    "status": "in_progress",
                    "entries": journal_entries,
                },
            )

        removed_directories = remove_empty_scaffold_dirs(project_root)
        restore_entries = [
            {
                "source_path": entry["source_path"],
                "backup_path": entry["backup_path"],
                "relative_path": entry["relative_path"],
                "kind": entry["kind"],
                "sha256": entry["sha256"],
                **(
                    {"link_target": entry["link_target"]}
                    if "link_target" in entry
                    else {}
                ),
            }
            for entry in moved
        ]
        atomic_write_json(
            backup_root / "restore-manifest.json",
            {
                "schema_version": 1,
                "status": "ready",
                "project_root": str(project_root),
                "entries": restore_entries,
                "removed_empty_directories": removed_directories,
            },
        )
        atomic_write_json(
            backup_root / "result.json",
            {
                "schema_version": 1,
                "status": "completed",
                "mode": args.mode,
                "project_root": str(project_root),
                "moved_count": len(moved),
                "preserved_count": preserved,
                "backup_root": str(backup_root),
            },
        )
        atomic_write_json(
            backup_root / "journal.json",
            {
                "schema_version": 1,
                "status": "completed",
                "entries": journal_entries,
            },
        )
    except Exception as error:
        rollback_errors: list[str] = []
        for entry in reversed(moved):
            source = Path(entry["source_path"])
            destination = Path(entry["backup_path"])
            try:
                source.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(destination), str(source))
            except Exception as rollback_error:
                rollback_errors.append(str(rollback_error))
        moved_relatives = {entry["relative_path"] for entry in moved}
        for journal_entry in journal_entries:
            if journal_entry["relative_path"] in moved_relatives:
                journal_entry["status"] = "rolled_back"
        try:
            atomic_write_json(
                backup_root / "journal.json",
                {
                    "schema_version": 1,
                    "status": "rolled_back" if not rollback_errors else "rollback_incomplete",
                    "entries": journal_entries,
                },
            )
        except OSError as journal_error:
            rollback_errors.append(f"journal: {journal_error}")
        atomic_write_json(
            backup_root / "result.json",
            {
                "schema_version": 1,
                "status": "rolled_back" if not rollback_errors else "rollback_incomplete",
                "error": str(error),
                "rollback_errors": rollback_errors,
                "moved_count": len(moved),
                "preserved_count": preserved,
            },
        )
        print(f"project_asset_migration: ERROR: {error}", file=sys.stderr)
        return 1
    print(
        f"project_asset_migration: moved={len(moved)} preserved={preserved} backup={backup_root}"
    )
    return 0


def main() -> int:
    return migrate(parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
