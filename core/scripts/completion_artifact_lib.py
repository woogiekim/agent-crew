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

        failure = validate_path(task_root, field, values[0])
        if failure:
            return failure

    return accept()


def accept() -> dict[str, str]:
    return {"action": "accept", "reason": "", "field": "", "path": ""}


def validate_path(
    task_root: Path, field: str, raw_path: str, *, binding: tuple[str, str] | None = None
) -> dict[str, str] | None:
    try:
        candidate = Path(raw_path).expanduser()
        if not candidate.is_absolute():
            candidate = task_root / candidate
        resolved = candidate.resolve()
        if not is_within(resolved, task_root):
            return reject("completion_artifact_outside_task", field=field, path=raw_path)
        if not resolved.exists():
            return reject("completion_artifact_missing", field=field, path=raw_path)
        if not resolved.is_file():
            return reject("completion_artifact_not_file", field=field, path=raw_path)
        if not has_non_whitespace_content(resolved):
            return reject("completion_artifact_empty", field=field, path=raw_path)
        if binding:
            label, expected = binding
            with resolved.open(encoding="utf-8") as artifact:
                values = [value for line in artifact for value in extract_values(line, label)]
            if values != [expected]:
                return reject("planning_artifact_design_hash_mismatch", field=field, path=raw_path)
    except (OSError, RuntimeError, UnicodeError, ValueError):
        return reject("completion_artifact_unreadable", field=field, path=raw_path)

    return None


def validate_planning_artifacts(task_dir: Path, design_hash: str) -> dict[str, str]:
    try:
        task_root = task_dir.resolve()
    except (OSError, RuntimeError, ValueError):
        return reject("completion_artifact_unreadable", path=str(task_dir))

    for field, path, label in (
        ("HANDOFF", "handoff.md", "BRAINSTORM_DESIGN_HASH"),
        ("PRD", "context/prd.md", "brainstorm_design_hash"),
    ):
        failure = validate_path(task_root, field, path, binding=(label, design_hash))
        if failure:
            return failure

    return accept()
