#!/usr/bin/env python3
"""Manage local per-user coding convention cache and task snapshots.

The cache is intentionally local to the installed user. agent-crew keeps the
mechanism in the repository, but the actual convention content lives under the
user's cache directory and is copied into a task-scoped snapshot only when a
workflow starts or when an explicit refresh is requested.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 1
DEFAULT_OWNER = (
    os.environ.get("AGENT_CREW_USER_ID")
    or os.environ.get("USER")
    or "default"
)


def utc_now() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def safe_name(value: str) -> str:
    text = re.sub(r"[^A-Za-z0-9_.-]+", "-", value.strip())
    text = text.strip(".-")
    return text or "default"


def default_cache_dir() -> Path:
    if os.environ.get("AGENT_CREW_CONVENTION_CACHE_DIR"):
        return Path(os.environ["AGENT_CREW_CONVENTION_CACHE_DIR"]).expanduser()

    home = Path(
        os.environ.get("AGENT_CREW_HOME", Path.home() / ".agent-crew")
    ).expanduser()
    return home / "cache" / "user-conventions"


def cache_path(cache_dir: Path, owner: str) -> Path:
    return cache_dir.expanduser() / f"{safe_name(owner)}.json"


def empty_cache(owner: str) -> dict[str, Any]:
    now = utc_now()

    return {
        "schema_version": SCHEMA_VERSION,
        "owner": owner,
        "version": 0,
        "created_at": now,
        "updated_at": now,
        "source": "local-user-cache",
        "conventions": [],
    }


def load_cache(cache_dir: Path, owner: str) -> dict[str, Any]:
    path = cache_path(cache_dir, owner)
    if not path.is_file():
        return empty_cache(owner)

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"user-conventions: invalid cache json: {path}: {exc}") from exc

    if not isinstance(payload, dict):
        raise SystemExit(f"user-conventions: cache must be an object: {path}")

    payload.setdefault("schema_version", SCHEMA_VERSION)
    payload.setdefault("owner", owner)
    payload.setdefault("version", 0)
    payload.setdefault("source", "local-user-cache")
    payload.setdefault("conventions", [])

    if not isinstance(payload["conventions"], list):
        raise SystemExit(f"user-conventions: conventions must be a list: {path}")

    return payload


def write_cache(cache_dir: Path, owner: str, payload: dict[str, Any]) -> Path:
    path = cache_path(cache_dir, owner)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload["schema_version"] = SCHEMA_VERSION
    payload["owner"] = owner
    payload["version"] = int(payload.get("version") or 0) + 1
    payload["updated_at"] = utc_now()
    text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"

    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)

    return path


def file_sha256(path: Path) -> str:
    if not path.is_file():
        return ""

    return hashlib.sha256(path.read_bytes()).hexdigest()


def normalize_list(values: list[str] | None) -> list[str]:
    if not values:
        return []

    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        for token in value.split(","):
            item = token.strip()
            if not item:
                continue
            key = item.lower()
            if key in seen:
                continue
            seen.add(key)
            result.append(item)

    return result


def find_convention(payload: dict[str, Any], convention_id: str) -> dict[str, Any]:
    for item in payload.get("conventions", []):
        if isinstance(item, dict) and item.get("id") == convention_id:
            return item

    raise SystemExit(f"user-conventions: convention not found: {convention_id}")


def capture(args: argparse.Namespace) -> int:
    owner = args.owner
    cache_dir = Path(args.cache_dir).expanduser()
    payload = load_cache(cache_dir, owner)
    now = utc_now()
    convention = {
        "id": str(uuid.uuid4()),
        "owner": owner,
        "status": "active",
        "scope": args.scope,
        "language": args.language,
        "project": args.project,
        "applies_to": normalize_list(args.applies_to),
        "content": args.content.strip(),
        "created_at": now,
        "updated_at": now,
    }
    payload["conventions"].append(convention)

    path = write_cache(cache_dir, owner, payload)
    print_json(
        {
            "id": convention["id"],
            "owner": owner,
            "version": payload["version"],
            "cache_path": str(path),
            "status": "active",
        }
    )

    return 0


def update(args: argparse.Namespace) -> int:
    owner = args.owner
    cache_dir = Path(args.cache_dir).expanduser()
    payload = load_cache(cache_dir, owner)
    convention = find_convention(payload, args.convention_id)

    if args.content is not None:
        convention["content"] = args.content.strip()
    if args.scope is not None:
        convention["scope"] = args.scope
    if args.language is not None:
        convention["language"] = args.language
    if args.project is not None:
        convention["project"] = args.project
    if args.applies_to:
        convention["applies_to"] = normalize_list(args.applies_to)
    convention["status"] = "active"
    convention["updated_at"] = utc_now()

    path = write_cache(cache_dir, owner, payload)
    print_json(
        {
            "id": convention["id"],
            "owner": owner,
            "version": payload["version"],
            "cache_path": str(path),
            "status": convention["status"],
        }
    )

    return 0


def retire(args: argparse.Namespace) -> int:
    owner = args.owner
    cache_dir = Path(args.cache_dir).expanduser()
    payload = load_cache(cache_dir, owner)
    convention = find_convention(payload, args.convention_id)
    convention["status"] = "retired"
    convention["retired_at"] = utc_now()
    convention["updated_at"] = convention["retired_at"]

    path = write_cache(cache_dir, owner, payload)
    print_json(
        {
            "id": convention["id"],
            "owner": owner,
            "version": payload["version"],
            "cache_path": str(path),
            "status": "retired",
        }
    )

    return 0


def snapshot_conventions(
    payload: dict[str, Any],
    args: argparse.Namespace,
) -> list[dict[str, Any]]:
    project_name = Path(args.project_root).resolve().name if args.project_root else ""
    selected: list[dict[str, Any]] = []
    for item in payload.get("conventions", []):
        if not isinstance(item, dict):
            continue
        if item.get("status", "active") != "active":
            continue
        if item.get("owner") not in (None, "", payload.get("owner")):
            continue
        project = str(item.get("project") or "").strip()
        if project and project not in {project_name, str(args.project_root or "")}:
            continue

        selected.append(
            {
                "id": item.get("id"),
                "scope": item.get("scope") or "global",
                "language": item.get("language") or "",
                "project": item.get("project") or "",
                "applies_to": item.get("applies_to") or [],
                "content": item.get("content") or "",
                "updated_at": item.get("updated_at") or "",
            }
        )

    return selected


def relevant_conventions(
    conventions: list[dict[str, Any]],
    *,
    stage: str,
    task: str,
    project_root: str,
) -> list[dict[str, Any]]:
    project_name = Path(project_root).resolve().name if project_root else ""
    haystack = " ".join(
        value.lower()
        for value in (task, stage, project_name)
        if isinstance(value, str) and value
    )

    selected: list[dict[str, Any]] = []
    for item in conventions:
        applies_to = [
            str(value).strip().lower()
            for value in item.get("applies_to", [])
        ]
        if applies_to and not any(token and token in haystack for token in applies_to):
            continue

        selected.append(item)

    return selected


def snapshot(args: argparse.Namespace) -> int:
    owner = args.owner
    cache_dir = Path(args.cache_dir).expanduser()
    task_dir = Path(args.task_dir).expanduser()
    context_dir = task_dir / "context"
    context_dir.mkdir(parents=True, exist_ok=True)
    snapshot_path = context_dir / "user-conventions.snapshot.json"
    cache_file = cache_path(cache_dir, owner)

    if snapshot_path.is_file() and not args.refresh:
        snapshot_payload = json.loads(snapshot_path.read_text(encoding="utf-8"))
        cache_status = "frozen"
    else:
        cache_payload = load_cache(cache_dir, owner)
        snapshot_payload = {
            "schema_version": SCHEMA_VERSION,
            "owner": owner,
            "source": "local-per-installed-user-cache",
            "source_cache": str(cache_file),
            "cache_version": cache_payload.get("version", 0),
            "cache_hash": file_sha256(cache_file),
            "task": args.task,
            "created_by_stage": args.stage,
            "project_root": args.project_root,
            "generated_at": utc_now(),
            "refresh_policy": "frozen_for_task_unless_explicit_refresh",
            "conventions": snapshot_conventions(cache_payload, args),
        }
        snapshot_path.write_text(
            json.dumps(
                snapshot_payload,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        cache_status = "refreshed"

    context_path = write_stage_digest(
        context_dir,
        snapshot_payload,
        stage=args.stage,
        task=args.task,
        project_root=args.project_root,
    )
    digest_count = len(
        relevant_conventions(
            snapshot_payload.get("conventions") or [],
            stage=args.stage,
            task=args.task,
            project_root=args.project_root,
        )
    )
    print_json(
        {
            "owner": owner,
            "snapshot_path": str(snapshot_path),
            "context_path": str(context_path) if context_path else "",
            "cache_status": cache_status,
            "cache_version": snapshot_payload.get("cache_version", 0),
            "convention_count": digest_count,
            "snapshot_convention_count": len(
                snapshot_payload.get("conventions") or []
            ),
        }
    )

    return 0


def write_stage_digest(
    context_dir: Path,
    snapshot_payload: dict[str, Any],
    *,
    stage: str,
    task: str,
    project_root: str,
) -> Path | None:
    conventions = relevant_conventions(
        snapshot_payload.get("conventions") or [],
        stage=stage,
        task=task,
        project_root=project_root,
    )
    digest_path = context_dir / f"user-conventions-{safe_name(stage)}.md"
    if not conventions:
        if digest_path.exists():
            digest_path.unlink()

        return None

    lines = [
        "# User Coding Conventions",
        "",
        "Source: local per-installed-user cache.",
        f"Snapshot: `{context_dir / 'user-conventions.snapshot.json'}`",
        "Refresh policy: frozen for this task unless explicitly refreshed.",
        "",
    ]
    for item in conventions:
        prefix = item.get("id") or "convention"
        language = item.get("language") or "any"
        scope = item.get("scope") or "global"
        content = item.get("content", "").strip()
        lines.append(f"- `{prefix}` ({scope}, {language}): {content}")

    digest_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")

    return digest_path


def show_cache(args: argparse.Namespace) -> int:
    cache_dir = Path(args.cache_dir).expanduser()
    payload = load_cache(cache_dir, args.owner)
    print_json(payload)

    return 0


def print_json(payload: dict[str, Any]) -> None:
    json.dump(payload, sys.stdout, ensure_ascii=False, sort_keys=True)
    sys.stdout.write("\n")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    def add_common(subparser: argparse.ArgumentParser) -> None:
        subparser.add_argument("--owner", default=DEFAULT_OWNER)
        subparser.add_argument("--cache-dir", default=str(default_cache_dir()))

    capture_parser = subparsers.add_parser("capture", help="Add a local user convention")
    add_common(capture_parser)
    capture_parser.add_argument("--content", required=True)
    capture_parser.add_argument("--scope", default="global")
    capture_parser.add_argument("--language", default="")
    capture_parser.add_argument("--project", default="")
    capture_parser.add_argument("--applies-to", action="append")
    capture_parser.set_defaults(func=capture)

    update_parser = subparsers.add_parser("update", help="Update a local user convention")
    add_common(update_parser)
    update_parser.add_argument("convention_id")
    update_parser.add_argument("--content")
    update_parser.add_argument("--scope")
    update_parser.add_argument("--language")
    update_parser.add_argument("--project")
    update_parser.add_argument("--applies-to", action="append")
    update_parser.set_defaults(func=update)

    retire_parser = subparsers.add_parser("retire", help="Retire a local user convention")
    add_common(retire_parser)
    retire_parser.add_argument("convention_id")
    retire_parser.set_defaults(func=retire)

    snapshot_parser = subparsers.add_parser("snapshot", help="Create or reuse task snapshot")
    add_common(snapshot_parser)
    snapshot_parser.add_argument("--task-dir", required=True)
    snapshot_parser.add_argument("--task", default="")
    snapshot_parser.add_argument("--stage", default="agent")
    snapshot_parser.add_argument("--project-root", default="")
    snapshot_parser.add_argument("--refresh", action="store_true")
    snapshot_parser.set_defaults(func=snapshot)

    show_parser = subparsers.add_parser("show-cache", help="Print the local user cache")
    add_common(show_parser)
    show_parser.set_defaults(func=show_cache)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
