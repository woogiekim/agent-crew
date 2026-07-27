#!/usr/bin/env python3
"""Detect no-op update state from source, user, and generated output hashes."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def managed_path_crew(path: Path) -> bool:
    if not path.is_file():
        return False
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return False
    return (
        "experimental Codex launcher for agent-crew" in text
        or "deterministic shell entrypoint for agent-crew" in text
    )


def add_tree(entries: dict[str, str], label: str, root: Path) -> None:
    if not root.is_dir():
        entries[f"{label}/"] = "<missing>"
        return
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(root)
        entries[f"{label}/{rel}"] = sha256_file(path)


def add_file(entries: dict[str, str], label: str, path: Path) -> None:
    entries[label] = sha256_file(path) if path.is_file() else "<missing>"


def build_payload(args: argparse.Namespace) -> dict:
    source = Path(args.source_root).expanduser().resolve()
    project = Path(args.project_root).expanduser().resolve()
    home = Path(args.agent_crew_home).expanduser().resolve()
    codex_home = Path(args.codex_home).expanduser().resolve()
    claude_dir = Path(args.claude_dir).expanduser().resolve()
    path_bin = Path(args.path_bin).expanduser().resolve()
    entries: dict[str, str] = {}

    for rel in (
        "core/commands",
        "core/user",
        "core/rules",
        "core/hooks",
        "core/scripts",
        "core/evaluations",
        "core/schemas",
        "core/policies",
        "core/setup",
        "core/agents",
        "core/bin",
        "adapters",
    ):
        add_tree(entries, f"source/{rel}", source / rel)

    add_tree(entries, "user/agents", home / "user" / "agents")
    add_tree(entries, "user/skills", home / "user" / "skills")
    add_tree(entries, "user/commands", home / "user" / "commands")
    add_tree(entries, "output/project-codex", project / ".codex")
    add_tree(entries, "output/global-codex-skill", codex_home / "skills" / "agent-crew")
    add_tree(entries, "output/global-codex-crew-skills", codex_home / "agent-crew" / "skills")
    add_tree(entries, "output/global-codex-agents", codex_home / "agents")
    add_tree(entries, "output/claude-agent-crew", claude_dir / "agent-crew")
    add_tree(entries, "output/agent-crew-system", home / "system")
    add_tree(entries, "output/agent-crew-commands", home / "commands")
    add_tree(entries, "output/agent-crew-hooks", home / "hooks")
    add_tree(entries, "output/agent-crew-scripts", home / "scripts")
    add_tree(entries, "output/agent-crew-evaluations", home / "evaluations")
    add_tree(entries, "output/agent-crew-policies", home / "policies")
    add_tree(entries, "output/agent-crew-bin", home / "bin")

    path_crew = path_bin / "crew"
    if managed_path_crew(path_crew):
        add_file(entries, "output/path-bin/crew", path_crew)

    encoded = json.dumps(entries, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return {
        "schema_version": 1,
        "source_root": str(source),
        "project_root": str(project),
        "entry_count": len(entries),
        "sha256": hashlib.sha256(encoded).hexdigest(),
        "entries": entries,
    }


def category_for(entry: str) -> str:
    parts = entry.split("/")
    if len(parts) >= 2 and parts[0] in {"source", "output", "user"}:
        return "/".join(parts[:2])
    return parts[0] if parts else "unknown"


def diff_payload(previous: dict, payload: dict) -> dict:
    previous_entries = previous.get("entries", {}) if isinstance(previous, dict) else {}
    current_entries = payload.get("entries", {})
    if not previous_entries:
        return {
            "reason": "missing_previous_fingerprint",
            "changed_categories": [],
            "added": 0,
            "removed": 0,
            "changed": 0,
        }

    previous_keys = set(previous_entries)
    current_keys = set(current_entries)
    added_keys = current_keys - previous_keys
    removed_keys = previous_keys - current_keys
    changed_keys = {
        key
        for key in current_keys & previous_keys
        if previous_entries.get(key) != current_entries.get(key)
    }
    category_counts: dict[str, int] = {}
    for key in added_keys | removed_keys | changed_keys:
        category = category_for(key)
        category_counts[category] = category_counts.get(category, 0) + 1

    return {
        "reason": "entry_hash_changed" if category_counts else "sha_changed",
        "changed_categories": [
            {"category": category, "count": category_counts[category]}
            for category in sorted(category_counts)
        ],
        "added": len(added_keys),
        "removed": len(removed_keys),
        "changed": len(changed_keys),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", required=True)
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--agent-crew-home", default=os.environ.get("AGENT_CREW_HOME", str(Path.home() / ".agent-crew")))
    parser.add_argument("--codex-home", default=os.environ.get("CODEX_HOME", str(Path.home() / ".codex")))
    parser.add_argument("--claude-dir", default=os.environ.get("CLAUDE_DIR", str(Path.home() / ".claude")))
    parser.add_argument("--path-bin", default=os.environ.get("AGENT_CREW_PATH_BIN", str(Path.home() / ".local" / "bin")))
    parser.add_argument("--fingerprint", required=True)
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--format", choices=["json", "text"], default="text")
    args = parser.parse_args()

    fingerprint_path = Path(args.fingerprint).expanduser().resolve()
    payload = build_payload(args)
    previous = {}
    if fingerprint_path.is_file():
        try:
            previous = json.loads(fingerprint_path.read_text(encoding="utf-8"))
        except Exception:
            previous = {}
    matched = bool(previous) and previous.get("sha256") == payload["sha256"]
    diff = diff_payload(previous, payload) if not matched else {
        "reason": "matched",
        "changed_categories": [],
        "added": 0,
        "removed": 0,
        "changed": 0,
    }

    if args.write:
        fingerprint_path.parent.mkdir(parents=True, exist_ok=True)
        fingerprint_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        matched = True
        diff = {
            "reason": "written",
            "changed_categories": [],
            "added": 0,
            "removed": 0,
            "changed": 0,
        }

    result = {
        "schema_version": 1,
        "matched": matched,
        "fingerprint": str(fingerprint_path),
        "sha256": payload["sha256"],
        "previous_sha256": previous.get("sha256"),
        "entry_count": payload["entry_count"],
        "reason": diff["reason"],
        "diff": diff,
    }
    if args.format == "json":
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        if matched:
            print("MATCH: update fingerprint")
        elif diff["reason"] == "missing_previous_fingerprint":
            print("MISS: update fingerprint (no previous fingerprint; full refresh required)")
        else:
            categories = ", ".join(
                f"{item['category']}={item['count']}"
                for item in diff["changed_categories"][:8]
            ) or "unknown"
            print(
                "MISS: update fingerprint "
                f"(changed={diff['changed']}, added={diff['added']}, "
                f"removed={diff['removed']}; categories: {categories})"
            )

    if args.check:
        return 0 if matched else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
