#!/usr/bin/env python3
"""Track update scope and project-local freshness for agent-crew installs."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
from pathlib import Path
from typing import Any

try:
    from project_state import resolve_project_state
except ModuleNotFoundError:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from project_state import resolve_project_state


def now_epoch() -> int:
    return int(dt.datetime.now(dt.timezone.utc).timestamp())


def iso_from_epoch(value: int) -> str:
    if value <= 0:
        return "unknown"
    return dt.datetime.fromtimestamp(value, dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def base_registry() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "global": {},
        "projects": {},
    }


def dict_value(mapping: Any, key: str, default: Any) -> Any:
    if isinstance(mapping, dict) and key in mapping:
        return mapping[key]
    return default


def as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


def int_value(mapping: Any, key: str) -> int:
    value = dict_value(mapping, key, 0)
    try:
        return int(value)
    except Exception:
        return 0


def registry_path(agent_crew_home: Path) -> Path:
    return agent_crew_home / "state" / "update-registry.json"


def read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return base_registry()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return base_registry()
    registry = as_dict(data)
    if "schema_version" not in registry:
        registry["schema_version"] = 1
    if "global" not in registry:
        registry["global"] = {}
    if "projects" not in registry:
        registry["projects"] = {}
    return registry


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def project_key(project_root: Path) -> str:
    return str(project_root.expanduser().resolve())


def mark_global(args: argparse.Namespace) -> int:
    home = Path(args.agent_crew_home).expanduser().resolve()
    source_root = str(Path(args.source_root).expanduser().resolve())
    registry_file = registry_path(home)
    registry = read_json(registry_file)
    timestamp = now_epoch()
    registry["global"] = {
        "updated_at_epoch": timestamp,
        "updated_at": iso_from_epoch(timestamp),
        "source_root": source_root,
        "mode": args.mode,
    }
    write_json(registry_file, registry)
    print(f"update_scope: global={home} source={source_root}")
    return 0


def project_entry(agent_crew_home: Path, project_root: Path, source_root: Path, timestamp: int) -> dict[str, Any]:
    root = project_root.expanduser().resolve()
    state_info = resolve_project_state(
        home=agent_crew_home,
        project_root=root,
        ensure=True,
        migrate_legacy=True,
    )
    return {
        "project_name": root.name,
        "project_root": str(root),
        "project_state_key": state_info["project_state_key"],
        "state_dir": state_info["state_dir"],
        "updated_at_epoch": timestamp,
        "updated_at": iso_from_epoch(timestamp),
        "source_root": str(source_root.expanduser().resolve()),
    }


def mark_project(args: argparse.Namespace) -> int:
    home = Path(args.agent_crew_home).expanduser().resolve()
    project_root = Path(args.project_root).expanduser().resolve()
    source_root = Path(args.source_root).expanduser().resolve()
    registry_file = registry_path(home)
    registry = read_json(registry_file)
    projects = as_dict(dict_value(registry, "projects", {}))
    timestamp = now_epoch()
    entry = project_entry(home, project_root, source_root, timestamp)
    projects[project_key(project_root)] = entry
    registry["projects"] = projects
    write_json(registry_file, registry)

    state_marker = Path(entry["state_dir"]) / "project-update.json"
    write_json(state_marker, entry)
    print(f"update_scope: project={project_root}")
    return 0


def roots_from_registry(registry: dict[str, Any]) -> dict[str, str]:
    projects = as_dict(dict_value(registry, "projects", {}))
    roots: dict[str, str] = {}
    for key, value in projects.items():
        entry = as_dict(value)
        root = str(dict_value(entry, "project_root", key)).strip()
        if root:
            roots[project_key(Path(root))] = "registry"
    return roots


def roots_from_task_state(agent_crew_home: Path) -> dict[str, str]:
    roots: dict[str, str] = {}
    state_root = agent_crew_home / "state"
    if not state_root.is_dir():
        return roots
    for marker in sorted(state_root.glob("*/tasks/*/project-root.txt")):
        root = marker.read_text(encoding="utf-8", errors="replace").strip()
        if root:
            roots[project_key(Path(root))] = "task-state"
    for register in sorted(state_root.glob("*/tasks/*/register.json")):
        try:
            data = json.loads(register.read_text(encoding="utf-8"))
        except Exception:
            continue
        root = str(dict_value(data, "project_root", "")).strip()
        if root:
            roots[project_key(Path(root))] = "task-state"
    return roots


def list_projects(args: argparse.Namespace) -> int:
    home = Path(args.agent_crew_home).expanduser().resolve()
    registry = read_json(registry_path(home))
    roots = roots_from_registry(registry)
    roots.update(roots_from_task_state(home))
    ordered = sorted(roots)
    if args.format == "json":
        payload = {
            "schema_version": 1,
            "agent_crew_home": str(home),
            "projects": [
                {"project_root": root, "source": roots[root]}
                for root in ordered
            ],
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0
    for root in ordered:
        print(root)
    return 0


def project_has_local_outputs(project_root: Path) -> bool:
    for rel in (".codex", ".agent-crew", ".claude"):
        if (project_root / rel).exists():
            return True
    if (project_root / "AGENTS.md").is_file():
        return True
    if (project_root / "CLAUDE.md").is_file():
        return True
    return False


def stale_payload(agent_crew_home: Path, project_root: Path) -> dict[str, Any]:
    registry = read_json(registry_path(agent_crew_home))
    global_info = as_dict(dict_value(registry, "global", {}))
    projects = as_dict(dict_value(registry, "projects", {}))
    entry = as_dict(dict_value(projects, project_key(project_root), {}))
    global_epoch = int_value(global_info, "updated_at_epoch")
    project_epoch = int_value(entry, "updated_at_epoch")
    status = "current"
    reason = "project_local_update_current"
    if global_epoch <= 0:
        status = "unknown"
        reason = "global_update_marker_missing"
    if global_epoch > 0 and project_epoch <= 0 and project_has_local_outputs(project_root):
        status = "stale"
        reason = "project_update_marker_missing"
    if global_epoch > project_epoch and project_epoch > 0:
        status = "stale"
        reason = "global_newer_than_project"
    return {
        "schema_version": 1,
        "status": status,
        "reason": reason,
        "project_root": str(project_root),
        "global_updated_at": iso_from_epoch(global_epoch),
        "project_updated_at": iso_from_epoch(project_epoch),
    }


def check_stale(args: argparse.Namespace) -> int:
    home = Path(args.agent_crew_home).expanduser().resolve()
    project_root = Path(args.project_root).expanduser().resolve()
    payload = stale_payload(home, project_root)
    if args.format == "json":
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0
    if payload["status"] == "stale":
        print(
            "WARNING: project-local agent-crew files may be stale; "
            f"global update {payload['global_updated_at']} is newer than "
            f"project update {payload['project_updated_at']} for {project_root}. "
            "Run `crew update` in this project or `crew update --all-projects`."
        )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--agent-crew-home", default=os.environ.get("AGENT_CREW_HOME", str(Path.home() / ".agent-crew")))
    sub = parser.add_subparsers(dest="command", required=True)

    global_parser = sub.add_parser("mark-global")
    global_parser.add_argument("--source-root", required=True)
    global_parser.add_argument("--mode", default="update")

    project_parser = sub.add_parser("mark-project")
    project_parser.add_argument("--project-root", required=True)
    project_parser.add_argument("--source-root", required=True)

    list_parser = sub.add_parser("list-projects")
    list_parser.add_argument("--format", choices=["text", "json"], default="text")

    stale_parser = sub.add_parser("check-stale")
    stale_parser.add_argument("--project-root", required=True)
    stale_parser.add_argument("--format", choices=["text", "json"], default="text")

    args = parser.parse_args()
    if args.command == "mark-global":
        return mark_global(args)
    if args.command == "mark-project":
        return mark_project(args)
    if args.command == "list-projects":
        return list_projects(args)
    if args.command == "check-stale":
        return check_stale(args)
    return 2  # pragma: no cover - argparse subcommands exhaust valid paths.


if __name__ == "__main__":
    raise SystemExit(main())
