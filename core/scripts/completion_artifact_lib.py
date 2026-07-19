"""Shared validation for task-local semantic completion artifacts."""

from __future__ import annotations

import re
from pathlib import Path


REQUIRED_FIELDS = {
    "analyst": ("HANDOFF", "PRD"),
    "planner": ("HANDOFF", "PRD"),
    "reviewer": ("REPORT",),
}
CONTENT_SCAN_CHUNK_SIZE = 4096


def extract_values(text: str, field: str) -> list[str]:
    pattern = re.compile(rf"^{re.escape(field)}\s*:\s*(.+?)\s*$", re.MULTILINE)
    return [match.group(1).strip() for match in pattern.finditer(text)]


def is_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False

    return True


def reject(reason: str, *, field: str = "", path: str = "") -> dict[str, str]:
    return {
        "action": "retry_validation",
        "reason": reason,
        "field": field,
        "path": path,
    }


def has_non_whitespace_content(path: Path) -> bool:
    with path.open("r", encoding="utf-8") as artifact:
        while chunk := artifact.read(CONTENT_SCAN_CHUNK_SIZE):
            if any(not character.isspace() for character in chunk):
                return True

    return False


def validate(agent: str, task_dir: Path, text: str) -> dict[str, str]:
    required = REQUIRED_FIELDS.get(agent)
    if required is None:
        return {
            "action": "not_applicable",
            "reason": "",
            "field": "",
            "path": "",
        }

    try:
        task_root = task_dir.resolve()
    except (OSError, RuntimeError, ValueError):
        return reject("completion_artifact_unreadable", path=str(task_dir))

    for field in required:
        values = extract_values(text, field)
        if not values:
            return reject("completion_artifact_missing", field=field)
        if len(values) != 1:
            return reject("completion_artifact_ambiguous", field=field)

        raw_path = values[0]
        try:
            candidate = Path(raw_path).expanduser()
            if not candidate.is_absolute():
                candidate = task_root / candidate
            resolved = candidate.resolve()
            if not is_within(resolved, task_root):
                return reject(
                    "completion_artifact_outside_task", field=field, path=raw_path
                )
            if not resolved.exists():
                return reject(
                    "completion_artifact_missing", field=field, path=raw_path
                )
            if not resolved.is_file():
                return reject(
                    "completion_artifact_not_file", field=field, path=raw_path
                )
            has_content = has_non_whitespace_content(resolved)
        except (OSError, RuntimeError, UnicodeError, ValueError):
            return reject(
                "completion_artifact_unreadable", field=field, path=raw_path
            )
        if not has_content:
            return reject("completion_artifact_empty", field=field, path=raw_path)

    return {"action": "accept", "reason": "", "field": "", "path": ""}
