#!/usr/bin/env python3
"""Record before/after update preservation state for user-owned assets."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path


CODEX_SYSTEM_AGENT_MARKER = "This is a Codex adapter bootstrap for the agent-crew system agent."
LEGACY_SYSTEM_CODEX_AGENT_NAMES = {
    "analyst.toml",
    "backend.toml",
    "designer.toml",
    "devops.toml",
    "documenter.toml",
    "frontend.toml",
    "historian.toml",
    "issuer.toml",
    "korean-normalizer.toml",
    "learning-mentor.toml",
    "mcp-manager.toml",
    "planner.toml",
    "requirements.toml",
    "resolver.toml",
    "reviewer.toml",
    "scribe.toml",
    "supervisor.toml",
    "test-writer.toml",
}


def utc_now_z() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def file_snapshot(root: Path) -> dict:
    return filtered_file_snapshot(root)


def filtered_file_snapshot(root: Path, predicate=None) -> dict:
    files = {}
    if root.is_dir():
        for path in sorted(p for p in root.rglob("*") if p.is_file()):
            if predicate and not predicate(path):
                continue
            rel = str(path.relative_to(root))
            files[rel] = {
                "sha256": sha256_file(path),
                "bytes": path.stat().st_size,
            }
    return {
        "root": str(root),
        "count": len(files),
        "files": files,
    }


def protected_project_codex_agent(path: Path) -> bool:
    text = path.read_text(encoding="utf-8", errors="replace")
    if CODEX_SYSTEM_AGENT_MARKER in text:
        return False
    if path.name in LEGACY_SYSTEM_CODEX_AGENT_NAMES and "Agent-crew system agent:" in text:
        return False
    return True


def settings_snapshot(paths: list[Path]) -> dict:
    data = {}
    for path in paths:
        if path.is_file():
            data[str(path)] = {
                "exists": True,
                "sha256": sha256_file(path),
                "bytes": path.stat().st_size,
            }
        else:
            data[str(path)] = {"exists": False}
    return data


def snapshot(agent_crew_home: Path, project_root: Path) -> dict:
    home = Path.home()
    codex_home = Path(os.environ.get("CODEX_HOME", home / ".codex")).expanduser()
    claude_dir = Path(os.environ.get("CLAUDE_DIR", home / ".claude")).expanduser()
    return {
        "user_agents": file_snapshot(agent_crew_home / "user" / "agents"),
        "user_skills": file_snapshot(agent_crew_home / "user" / "skills"),
        "project_codex_agents": filtered_file_snapshot(
            project_root / ".codex" / "agents",
            protected_project_codex_agent,
        ),
        "settings": settings_snapshot([
            claude_dir / "settings.json",
            codex_home / "config.toml",
            project_root / ".codex" / "config.toml",
            project_root / ".codex" / "hooks.json",
            agent_crew_home / "AGENTS.md",
        ]),
    }


def deleted_files(before: dict, after: dict, key: str) -> list[str]:
    before_files = set(before.get(key, {}).get("files", {}))
    after_files = set(after.get(key, {}).get("files", {}))
    return sorted(before_files - after_files)


def changed_settings(before: dict, after: dict) -> list[str]:
    changed = []
    before_settings = before.get("settings", {})
    after_settings = after.get("settings", {})
    for path, before_info in before_settings.items():
        after_info = after_settings.get(path, {"exists": False})
        if before_info.get("exists") != after_info.get("exists"):
            changed.append(path)
        elif before_info.get("sha256") and before_info.get("sha256") != after_info.get("sha256"):
            changed.append(path)
    return sorted(changed)


def begin(args: argparse.Namespace) -> int:
    project_root = Path(args.project_root).expanduser().resolve()
    agent_crew_home = Path(args.agent_crew_home).expanduser().resolve()
    project_name = project_root.name
    manifest_dir = agent_crew_home / "state" / project_name / "update-preservation"
    manifest_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = manifest_dir / f"{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}.json"
    manifest = {
        "schema_version": 1,
        "project_root": str(project_root),
        "agent_crew_home": str(agent_crew_home),
        "started_at": utc_now_z(),
        "before": snapshot(agent_crew_home, project_root),
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(manifest_path)
    return 0


def finish(args: argparse.Namespace) -> int:
    manifest_path = Path(args.manifest).expanduser().resolve()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    project_root = Path(manifest["project_root"])
    agent_crew_home = Path(manifest["agent_crew_home"])
    before = manifest.get("before", {})
    after = snapshot(agent_crew_home, project_root)
    deleted = {
        "user_agents": deleted_files(before, after, "user_agents"),
        "user_skills": deleted_files(before, after, "user_skills"),
        "project_codex_agents": deleted_files(before, after, "project_codex_agents"),
    }
    changed = changed_settings(before, after)
    manifest.update({
        "finished_at": utc_now_z(),
        "after": after,
        "deleted_custom_files": deleted,
        "changed_settings": changed,
        "passed": not any(deleted.values()),
    })
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.format == "json":
        print(json.dumps(manifest, ensure_ascii=False, indent=2))
    else:
        print(f"update-preservation-manifest: {manifest_path}")
        print(f"user_agents: {after['user_agents']['count']} file(s)")
        print(f"user_skills: {after['user_skills']['count']} file(s)")
        print(f"project_codex_agents: {after['project_codex_agents']['count']} protected file(s)")
        if not manifest["passed"]:
            print("deleted_custom_files: " + json.dumps(deleted, ensure_ascii=False))
        if changed:
            print("changed_settings: " + json.dumps(changed, ensure_ascii=False))
    return 0 if manifest["passed"] else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    begin_parser = sub.add_parser("begin")
    begin_parser.add_argument("--agent-crew-home", required=True)
    begin_parser.add_argument("--project-root", required=True)

    finish_parser = sub.add_parser("finish")
    finish_parser.add_argument("--manifest", required=True)
    finish_parser.add_argument("--format", choices=["text", "json"], default="text")

    args = parser.parse_args()
    if args.command == "begin":
        return begin(args)
    if args.command == "finish":
        return finish(args)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
