#!/usr/bin/env python3
"""Resolve collision-safe per-project agent-crew state paths."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shlex
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


STATE_KEY_HASH_LEN = 10
RUNTIME_STATE_NAMES = (
    "tasks",
    "agent-requests",
    "cost",
    "session.json",
    "normalized-tasks",
    "integrity",
    "routing-misses.log",
)


def canonical_project_root(project_root: str | Path | None = None) -> Path:
    root = Path(project_root or os.environ.get("PROJECT_ROOT") or os.getcwd())
    return root.expanduser().resolve()


def agent_crew_home(path: str | Path | None = None) -> Path:
    return Path(path or os.environ.get("AGENT_CREW_HOME") or Path.home() / ".agent-crew").expanduser().resolve()


def slug_name(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip()).strip(".-").lower()
    return slug or "project"


def project_state_key(project_root: str | Path) -> str:
    root = canonical_project_root(project_root)
    digest = hashlib.sha256(str(root).encode("utf-8")).hexdigest()[:STATE_KEY_HASH_LEN]
    return f"{slug_name(root.name)}-{digest}"


def legacy_state_dir(home: str | Path, project_root: str | Path) -> Path:
    return agent_crew_home(home) / "state" / canonical_project_root(project_root).name


def keyed_state_dir(home: str | Path, project_root: str | Path) -> Path:
    return agent_crew_home(home) / "state" / project_state_key(project_root)


def read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def metadata_payload(home: str | Path, project_root: str | Path, state_dir: Path) -> dict[str, Any]:
    root = canonical_project_root(project_root)
    key = project_state_key(root)
    return {
        "schema_version": 1,
        "project_name": root.name,
        "project_root": str(root),
        "project_state_key": key,
        "state_dir": str(state_dir),
        "legacy_state_dir": str(legacy_state_dir(home, root)),
        "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def root_matches(value: Any, project_root: Path) -> bool:
    if not value:
        return False
    try:
        return Path(str(value)).expanduser().resolve() == project_root
    except Exception:
        return False


def legacy_match_status(state_dir: Path, project_root: str | Path) -> str:
    """Return match, conflict, unknown, or absent for a legacy state directory."""
    root = canonical_project_root(project_root)
    if not state_dir.exists():
        return "absent"

    evidence_paths = [
        state_dir / "project.json",
        state_dir / "project-update.json",
    ]
    evidence_paths.extend(sorted((state_dir / "tasks").glob("*/register.json"))[:25])

    saw_evidence = False
    for path in evidence_paths:
        if not path.is_file():
            continue
        payload = read_json(path)
        value = payload.get("project_root")
        if value:
            saw_evidence = True
            if root_matches(value, root):
                return "match"
            return "conflict"

    for path in sorted((state_dir / "tasks").glob("*/project-root.txt"))[:25]:
        text = path.read_text(encoding="utf-8", errors="replace").strip()
        if text:
            saw_evidence = True
            if root_matches(text, root):
                return "match"
            return "conflict"

    return "unknown" if not saw_evidence else "conflict"


def write_project_metadata(home: str | Path, project_root: str | Path, state_dir: Path) -> None:
    write_json(state_dir / "project.json", metadata_payload(home, project_root, state_dir))


def resolve_project_state(
    *,
    home: str | Path | None = None,
    project_root: str | Path | None = None,
    ensure: bool = False,
    migrate_legacy: bool = False,
    prefer_existing_legacy: bool = False,
) -> dict[str, Any]:
    resolved_home = agent_crew_home(home)
    root = canonical_project_root(project_root)
    key = project_state_key(root)
    target = keyed_state_dir(resolved_home, root)
    legacy = legacy_state_dir(resolved_home, root)
    migrated = False
    legacy_status = legacy_match_status(legacy, root)

    if migrate_legacy and legacy != target and legacy.exists() and not target.exists():
        if legacy_status in {"match", "unknown"}:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(legacy), str(target))
            migrated = True

    if prefer_existing_legacy and not target.exists() and legacy.exists() and legacy_status in {"match", "unknown"}:
        state_dir = legacy
    else:
        state_dir = target

    if ensure:
        state_dir.mkdir(parents=True, exist_ok=True)

    if state_dir.exists():
        write_project_metadata(resolved_home, root, state_dir)

    return {
        "project_root": str(root),
        "project_name": root.name,
        "project_state_key": key,
        "state_dir": str(state_dir),
        "legacy_state_dir": str(legacy),
        "legacy_match_status": legacy_status,
        "migrated_legacy_state": migrated,
    }


def archive_project_context(state_dir: Path) -> str:
    context = state_dir / "project-context"
    if not context.exists():
        return ""

    archive_root = state_dir / "archive" / "project-context"
    archive_root.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    target = archive_root / timestamp
    suffix = 1
    while target.exists():
        target = archive_root / f"{timestamp}-{suffix}"
        suffix += 1
    shutil.move(str(context), str(target))
    return str(target)


def reset_runtime_state(state_dir: Path) -> list[str]:
    removed: list[str] = []
    for name in RUNTIME_STATE_NAMES:
        path = state_dir / name
        if path.is_dir():
            shutil.rmtree(path)
            removed.append(name)
        elif path.exists():
            path.unlink()
            removed.append(name)
    (state_dir / "tasks").mkdir(parents=True, exist_ok=True)
    return removed


def setup_existing_state(
    *,
    home: str | Path | None,
    project_root: str | Path | None,
    action: str,
) -> dict[str, Any]:
    info = resolve_project_state(
        home=home,
        project_root=project_root,
        ensure=True,
        migrate_legacy=True,
    )
    state_dir = Path(info["state_dir"])
    action = action.strip().lower().replace("_", "-")
    if action in {"preserve", "preserve-context", "reset-preserve-context"}:
        removed = reset_runtime_state(state_dir)
        archived_to = ""
    elif action in {"archive-context", "archive-regenerate-context"}:
        archived_to = archive_project_context(state_dir)
        removed = reset_runtime_state(state_dir)
    elif action in {"full-reset", "reset-all"}:
        if state_dir.exists():
            shutil.rmtree(state_dir)
        state_dir.mkdir(parents=True, exist_ok=True)
        removed = ["state_dir"]
        archived_to = ""
    elif action == "cancel":
        return {**info, "action": action, "cancelled": True, "removed": [], "archived_to": ""}
    else:
        raise ValueError(f"unknown setup existing-state action: {action}")

    write_project_metadata(home, project_root, state_dir)
    return {**info, "action": action, "cancelled": False, "removed": removed, "archived_to": archived_to}


def shell_exports(info: dict[str, Any]) -> str:
    mapping = {
        "PROJECT_ROOT": info["project_root"],
        "PROJECT_NAME": info["project_name"],
        "PROJECT_STATE_KEY": info["project_state_key"],
        "STATE_DIR": info["state_dir"],
        "LEGACY_STATE_DIR": info["legacy_state_dir"],
        "PROJECT_STATE_LEGACY_MATCH": info["legacy_match_status"],
        "PROJECT_STATE_MIGRATED": "1" if info["migrated_legacy_state"] else "0",
    }
    return "\n".join(f"export {key}={shlex.quote(str(value))}" for key, value in mapping.items())


def cmd_resolve(args: argparse.Namespace) -> int:
    info = resolve_project_state(
        home=args.agent_crew_home,
        project_root=args.project_root,
        ensure=args.ensure,
        migrate_legacy=args.migrate_legacy,
        prefer_existing_legacy=args.prefer_existing_legacy,
    )
    if args.format == "shell":
        print(shell_exports(info))
    else:
        print(json.dumps(info, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def cmd_setup_existing(args: argparse.Namespace) -> int:
    payload = setup_existing_state(
        home=args.agent_crew_home,
        project_root=args.project_root,
        action=args.action,
    )
    if args.format == "shell":
        print(shell_exports(payload))
        print(f"export AGENT_CREW_SETUP_CANCELLED={shlex.quote('1' if payload['cancelled'] else '0')}")
    else:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 10 if payload["cancelled"] else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    resolve = sub.add_parser("resolve")
    resolve.add_argument("--agent-crew-home", default=os.environ.get("AGENT_CREW_HOME", str(Path.home() / ".agent-crew")))
    resolve.add_argument("--project-root", default=os.environ.get("PROJECT_ROOT", os.getcwd()))
    resolve.add_argument("--ensure", action="store_true")
    resolve.add_argument("--migrate-legacy", action="store_true")
    resolve.add_argument("--prefer-existing-legacy", action="store_true")
    resolve.add_argument("--format", choices=["json", "shell"], default="json")
    resolve.set_defaults(func=cmd_resolve)

    setup = sub.add_parser("setup-existing-state")
    setup.add_argument("--agent-crew-home", default=os.environ.get("AGENT_CREW_HOME", str(Path.home() / ".agent-crew")))
    setup.add_argument("--project-root", default=os.environ.get("PROJECT_ROOT", os.getcwd()))
    setup.add_argument("--action", required=True)
    setup.add_argument("--format", choices=["json", "shell"], default="json")
    setup.set_defaults(func=cmd_setup_existing)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        return args.func(args)
    except ValueError as error:
        print(f"project-state: {error}", file=os.sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
