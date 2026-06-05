#!/usr/bin/env python3
"""Discover reviewer review-profile skills from user-owned metadata.

Inputs:
  --skills-dir DIR     Skill directory to scan. Repeatable.
  --project-root DIR   Repository root used as detection context.
  --task TEXT          Normalized task or review request text.
  --changed-file PATH  Changed path to include as detection context. Repeatable.

Output:
  JSON by default, or text with --format text.

Exit codes:
  0 - discovery completed, with or without matches
  2 - malformed arguments

Example:
  python3 review-profile-dispatch.py \
    --skills-dir ~/.agent-crew/user/skills \
    --project-root "$PROJECT_ROOT" \
    --task "$TASK"
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Iterable


PROFILE_TYPES = {
    "review-policy",
    "review-profile",
    "review_policy",
    "review_profile",
}

STOP_WORDS = {
    "and",
    "behavior",
    "changes",
    "code",
    "for",
    "like",
    "policy",
    "profile",
    "repository",
    "request",
    "requests",
    "review",
    "reviewer",
    "reviews",
    "sensitive",
    "task",
    "the",
    "touch",
    "touches",
    "user",
    "with",
}


def strip_scalar(value: str) -> str:
    value = value.strip()
    if value in {">", "|"}:
        return ""
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1].strip()
    return value


def parse_frontmatter(text: str) -> dict[str, str]:
    if not text.startswith("---"):
        return {}

    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}

    frontmatter: list[str] = []
    for line in lines[1:]:
        if line.strip() == "---":
            break
        frontmatter.append(line)
    else:
        return {}

    data: dict[str, str] = {}
    current_key = ""
    for line in frontmatter:
        if not line.strip():
            continue

        if line.startswith((" ", "\t")) and current_key:
            continuation = line.strip()
            if continuation.startswith("- "):
                continuation = continuation[2:].strip()
                separator = "," if data.get(current_key) else ""
                data[current_key] = f"{data.get(current_key, '')}{separator}{continuation}"
            else:
                separator = " " if data.get(current_key) else ""
                data[current_key] = f"{data.get(current_key, '')}{separator}{continuation}"
            continue

        match = re.match(r"^([A-Za-z_][A-Za-z0-9_-]*):\s*(.*)$", line)
        if not match:
            current_key = ""
            continue

        current_key = match.group(1).strip().replace("-", "_")
        data[current_key] = strip_scalar(match.group(2))

    return data


def split_list(value: str) -> list[str]:
    cleaned = value.strip().strip("[]")
    parts = re.split(r"[,;|\s]+", cleaned)
    return [part.strip().strip("'\"") for part in parts if part.strip().strip("'\"")]


def metadata_value(metadata: dict[str, str], *keys: str) -> str:
    for key in keys:
        normalized = key.replace("-", "_")
        if metadata.get(normalized):
            return metadata[normalized]
    return ""


def loaded_by_reviewer(metadata: dict[str, str]) -> tuple[bool, list[str]]:
    loaded = split_list(metadata_value(metadata, "loaded_by", "loaded-by"))
    lowered = [entry.lower() for entry in loaded]

    return "reviewer" in lowered, loaded


def is_review_profile(metadata: dict[str, str]) -> bool:
    reviewer_loaded, _loaded = loaded_by_reviewer(metadata)
    if not reviewer_loaded:
        return False

    profile_type = metadata_value(
        metadata,
        "profile_type",
        "profile-type",
        "contract",
        "kind",
        "type",
    ).lower()
    if profile_type in PROFILE_TYPES:
        return True

    legacy_contract = " ".join(
        metadata_value(metadata, key)
        for key in ("name", "description", "axis", "detection")
    ).lower()

    return bool(metadata_value(metadata, "detection")) and "review" in legacy_contract


def normalize_text(text: str) -> str:
    return " ".join(re.findall(r"[A-Za-z0-9]+", text.lower()))


def token_set(text: str) -> set[str]:
    return set(normalize_text(text).split())


def significant_tokens(text: str) -> list[str]:
    tokens = token_set(text)
    return sorted(
        token
        for token in tokens
        if len(token) >= 4 and token not in STOP_WORDS
    )


def clause_matches(clause: str, context_text: str, context_tokens: set[str]) -> bool:
    tokens = significant_tokens(clause)
    if not tokens:
        return False

    def token_present(token: str) -> bool:
        return token in context_tokens or token in context_text

    if "/" in clause:
        return any(token_present(token) for token in tokens)

    if len(tokens) <= 2:
        return all(token_present(token) for token in tokens)

    return any(token_present(token) for token in tokens)


def detection_matches(detection: str, context_text: str, context_tokens: set[str]) -> bool:
    detection = detection.strip()
    if not detection:
        return True

    clauses = re.split(r"\bOR\b|\|\|", detection, flags=re.IGNORECASE)

    return any(clause_matches(clause, context_text, context_tokens) for clause in clauses)


def default_skill_dirs() -> list[Path]:
    home = Path(os.environ.get("AGENT_CREW_HOME", Path.home() / ".agent-crew"))

    return [home / "user" / "skills", home / "skills"]


def build_context(project_root: Path, task: str, changed_files: Iterable[str]) -> tuple[str, set[str]]:
    parts = [str(project_root), project_root.name, task, *changed_files]
    context_text = normalize_text(" ".join(parts))

    return context_text, set(context_text.split())


def iter_skill_files(skills_dirs: Iterable[Path]) -> Iterable[Path]:
    seen: set[Path] = set()
    for skills_dir in skills_dirs:
        if not skills_dir.is_dir():
            continue
        for path in sorted(skills_dir.glob("*.md")):
            resolved = path.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            yield path


def discover_review_profiles(
    skills_dirs: Iterable[Path],
    *,
    project_root: Path,
    task: str,
    changed_files: Iterable[str],
) -> list[dict]:
    context_text, context_tokens = build_context(project_root, task, changed_files)
    matches: list[dict] = []

    for path in iter_skill_files(skills_dirs):
        text = path.read_text(encoding="utf-8", errors="replace")
        metadata = parse_frontmatter(text)
        if not is_review_profile(metadata):
            continue

        detection = metadata_value(metadata, "detection")
        if not detection_matches(detection, context_text, context_tokens):
            continue

        _reviewer_loaded, loaded_by = loaded_by_reviewer(metadata)
        matches.append(
            {
                "name": metadata_value(metadata, "name") or path.stem,
                "path": str(path),
                "axis": metadata_value(metadata, "axis"),
                "loaded_by": loaded_by,
                "detection": detection,
                "matched_by": "detection" if detection else "global-review-profile",
            }
        )

    return sorted(matches, key=lambda item: (item["name"], item["path"]))


def build_payload(args: argparse.Namespace) -> dict:
    skills_dirs = [Path(path).expanduser() for path in args.skills_dir] or default_skill_dirs()
    matches = discover_review_profiles(
        skills_dirs,
        project_root=Path(args.project_root).expanduser(),
        task=args.task,
        changed_files=args.changed_file,
    )

    return {
        "agent": "reviewer",
        "matched": matches,
        "fallback": not bool(matches),
        "fallback_policy": "generic-review-skills",
    }


def print_text(payload: dict) -> None:
    if payload["matched"]:
        for match in payload["matched"]:
            print(f"review_profile: {match['name']} path={match['path']}")
        return

    print("[crew] DEGRADED | review-profile=none fallback=generic-review-skills")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Discover reviewer review-profile skills.")
    parser.add_argument("--skills-dir", action="append", default=[])
    parser.add_argument("--project-root", default=".")
    parser.add_argument("--task", default="")
    parser.add_argument("--changed-file", action="append", default=[])
    parser.add_argument("--format", choices=("json", "text"), default="json")

    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    payload = build_payload(args)

    if args.format == "json":
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print_text(payload)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
