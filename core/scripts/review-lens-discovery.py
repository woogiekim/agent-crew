#!/usr/bin/env python3
"""Discover and classify read-only review lenses for review-synthesis."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Iterable


TRUE_VALUES = {"1", "true", "yes", "on"}
FALSE_VALUES = {"0", "false", "no", "off"}
PARITY_TERMS = (
    "parity",
    "정합성",
    "producer",
    "consumer",
    "upstream",
    "downstream",
    "source/target",
    "contract comparison",
    "migration contract",
)
PROVIDER_PRIORITY = {
    "agent-crew": 0,
    "local": 1,
    "codex": 2,
    "claude": 3,
    "gitlab": 4,
    "unknown": 9,
}
SURFACE_PRIORITY = {
    "command": 0,
    "skill": 1,
    "script": 2,
    "agent": 3,
    "host-native": 4,
}


def strip_scalar(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1].strip()
    return value


def parse_frontmatter(text: str) -> dict[str, str]:
    if not text.startswith("---\n"):
        return {}

    lines = text.splitlines()
    metadata: dict[str, str] = {}
    current_key = ""
    for line in lines[1:]:
        if line.strip() == "---":
            break
        if line.startswith((" ", "\t")) and current_key:
            continuation = line.strip()
            separator = " " if metadata.get(current_key) else ""
            metadata[current_key] = f"{metadata.get(current_key, '')}{separator}{continuation}"
            continue

        match = re.match(r"^([A-Za-z_][A-Za-z0-9_-]*):\s*(.*)$", line)
        if not match:
            current_key = ""
            continue

        current_key = match.group(1).replace("-", "_")
        metadata[current_key] = strip_scalar(match.group(2))

    return metadata


def as_bool(value: str, *, default: bool) -> bool:
    lowered = value.strip().lower()
    if lowered in TRUE_VALUES:
        return True
    if lowered in FALSE_VALUES:
        return False
    return default


def metadata_value(metadata: dict[str, str], key: str, default: str = "") -> str:
    return metadata.get(key.replace("-", "_"), default).strip()


def iter_markdown_files(roots: Iterable[Path]) -> Iterable[Path]:
    seen: set[Path] = set()
    for root in roots:
        if root.is_file() and root.suffix.lower() == ".md":
            candidates = [root]
        elif root.is_dir():
            candidates = sorted(root.rglob("*.md"))
        else:
            candidates = []

        for path in candidates:
            resolved = path.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            yield path


def is_review_lens(metadata: dict[str, str]) -> bool:
    return (
        metadata_value(metadata, "kind") == "review-lens"
        and "review-synthesis"
        in {
            part.strip()
            for part in re.split(r"[,;\s]+", metadata_value(metadata, "loaded_by"))
            if part.strip()
        }
    )


def parity_scope_missing(lens: dict[str, object], task: str, parity_scope: str) -> bool:
    lens_text = " ".join(
        str(lens.get(key, ""))
        for key in ("lens_id", "name", "duplicate_group")
    ).lower()
    if "parity" not in lens_text:
        return False
    if parity_scope.strip():
        return False
    return not any(term.lower() in task.lower() for term in PARITY_TERMS)


def classify_lens(
    lens: dict[str, object],
    *,
    task: str,
    mr_id: str,
    parity_scope: str,
) -> tuple[str, str]:
    if bool(lens["mutates"]) or not bool(lens["read_only"]):
        return "blocked", "mutation_not_allowed"
    if bool(lens["requires_supervisor_context"]):
        return "blocked", "supervisor_context_required"
    if lens["requires_mr"] == "required" and not mr_id.strip():
        return "not-run", "mr_context_unavailable"
    if not bool(lens["default_enabled"]):
        return "suggested", "default_disabled"
    if parity_scope_missing(lens, task, parity_scope):
        return "suggested", "parity_scope_missing"

    return "eligible", "eligible_read_only_lens"


def lens_sort_key(lens: dict[str, object]) -> tuple[int, int, str]:
    return (
        PROVIDER_PRIORITY.get(str(lens["provider"]), PROVIDER_PRIORITY["unknown"]),
        SURFACE_PRIORITY.get(str(lens["surface"]), SURFACE_PRIORITY["host-native"]),
        str(lens["path"]),
    )


def discover_lenses(
    roots: Iterable[Path],
    *,
    task: str,
    mr_id: str = "",
    parity_scope: str = "",
) -> list[dict[str, object]]:
    lenses: list[dict[str, object]] = []
    for path in iter_markdown_files(roots):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

        metadata = parse_frontmatter(text)
        if not is_review_lens(metadata):
            continue

        lens_id = metadata_value(metadata, "lens_id") or metadata_value(metadata, "name") or path.stem
        lens: dict[str, object] = {
            "lens_id": lens_id,
            "name": metadata_value(metadata, "name", lens_id),
            "provider": metadata_value(metadata, "provider", "unknown"),
            "surface": metadata_value(metadata, "surface", "unknown"),
            "path": str(path),
            "read_only": as_bool(metadata_value(metadata, "read_only"), default=False),
            "mutates": as_bool(metadata_value(metadata, "mutates"), default=True),
            "default_enabled": as_bool(metadata_value(metadata, "default_enabled"), default=False),
            "requires_mr": metadata_value(metadata, "requires_mr", "none"),
            "requires_remote_read": metadata_value(metadata, "requires_remote_read", "none"),
            "requires_supervisor_context": as_bool(
                metadata_value(metadata, "requires_supervisor_context"),
                default=False,
            ),
            "timeout_seconds": metadata_value(metadata, "timeout_seconds", "120"),
            "duplicate_group": metadata_value(metadata, "duplicate_group", lens_id),
        }
        status, reason = classify_lens(
            lens,
            task=task,
            mr_id=mr_id,
            parity_scope=parity_scope,
        )
        lens["status"] = status
        lens["reason"] = reason
        lenses.append(lens)

    lenses.sort(key=lens_sort_key)

    represented_groups: set[str] = set()
    for lens in lenses:
        group = str(lens.get("duplicate_group") or "")
        if not group:
            continue
        if lens["status"] == "eligible":
            if group in represented_groups:
                lens["status"] = "duplicate-suppressed"
                lens["reason"] = "duplicate_group_represented"
            else:
                represented_groups.add(group)

    return lenses


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", action="append", type=Path, required=True)
    parser.add_argument("--task", default="")
    parser.add_argument("--mr-id", default="")
    parser.add_argument("--parity-scope", default="")
    parser.add_argument("--format", choices=("json", "text"), default="json")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    lenses = discover_lenses(
        args.root,
        task=args.task,
        mr_id=args.mr_id,
        parity_scope=args.parity_scope,
    )
    payload = {
        "schema_version": "agent-crew.review-lens-discovery.v1",
        "task": args.task,
        "mr_id": args.mr_id or None,
        "parity_scope": args.parity_scope or None,
        "lenses": lenses,
    }

    if args.format == "json":
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        for lens in lenses:
            print(f"{lens['lens_id']} - {lens['status']} ({lens['reason']})")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
