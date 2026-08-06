#!/usr/bin/env python3
"""Derive diagnostic skill coverage from existing task state.

This module intentionally does not create or require skill-use proof files.
It only classifies signals that already exist in task context.
"""

from __future__ import annotations

import json
import re
from pathlib import Path


SKILL_USE_REQUIRED_FIELDS = ("applied_rules", "evidence_refs", "output_files", "verification")


def _evidence_name(task_dir: Path, path: Path) -> str:
    try:
        return str(path.relative_to(task_dir))
    except ValueError:
        return str(path)


def normalize_skill_name(value: str) -> str:
    raw = str(value or "").strip().strip("`'\"")
    if not raw:
        return ""
    name = Path(raw).name
    if name == "SKILL.md" and Path(raw).parent.name:
        return f"{Path(raw).parent.name}.md"
    if name.endswith(".md"):
        return name
    if "/" not in raw and "\\" not in raw:
        return f"{raw}.md"
    return f"{name}.md" if name else ""


def _split_values(value: str) -> list[str]:
    cleaned = str(value or "").strip().strip("[]")
    parts = re.split(r"[,|]", cleaned)
    values = [
        part.strip().strip("'\"`")
        for part in parts
        if part.strip().strip("'\"`")
    ]
    return [
        value for value in values
        if not value.lower().startswith(("none", "n/a", "null", "reason"))
    ]


def _paths_from_json(value: object) -> list[str]:
    paths: list[str] = []
    if isinstance(value, str):
        if value.endswith(".md"):
            paths.append(value)
        return paths
    if isinstance(value, list):
        for item in value:
            paths.extend(_paths_from_json(item))
        return paths
    if not isinstance(value, dict):
        return paths

    for key in ("loaded_skills", "skills"):
        paths.extend(_paths_from_json(value.get(key)))
    for key in ("skill_path", "path"):
        paths.extend(_paths_from_json(value.get(key)))
    return paths


def extract_loaded_skill_paths(text: str) -> list[str]:
    paths: list[str] = []
    try:
        payload = json.loads(text)
    except Exception:
        payload = None
    if payload is not None:
        paths.extend(_paths_from_json(payload))

    for line in text.splitlines():
        if not re.match(r"\s*[-*]\s+", line):
            continue
        for match in re.finditer(r"(?:~|/|\.\.?/|[A-Za-z0-9_.-]+/)[^\s`,'\")]+\.md", line):
            path = match.group(0).strip()
            if path.startswith("context/") or "/context/" in path:
                continue
            if (
                "/skills/" in path
                or "/rules/" in path
                or path.startswith(("core/rules/", "core/agents/skills/"))
            ):
                paths.append(path)
    return sorted(set(paths))


def parse_selected_skill_names_from_text(text: str) -> list[str]:
    try:
        payload = json.loads(text)
    except Exception:
        payload = None
    if isinstance(payload, dict):
        values: list[str] = []
        for key in ("selected_skill", "selected_skills"):
            value = payload.get(key)
            if isinstance(value, list):
                for item in value:
                    values.extend(_split_values(str(item)))
            elif value is not None:
                values.extend(_split_values(str(value)))
        return sorted({normalize_skill_name(value) for value in values if normalize_skill_name(value)})

    selected: list[str] = []
    collecting = False
    for line in text.splitlines():
        key_match = re.match(r"\s*[-*]?\s*selected_skills?\s*[:=]\s*(.*)$", line, re.IGNORECASE)
        if key_match:
            value = key_match.group(1).strip()
            if value:
                selected.extend(_split_values(value))
                collecting = False
            else:
                collecting = True
            continue

        if collecting:
            item_match = re.match(r"\s*[-*]\s+(.+?)\s*$", line)
            if item_match:
                selected.extend(_split_values(item_match.group(1)))
                continue
            if line.strip():
                collecting = False

    return sorted({normalize_skill_name(value) for value in selected if normalize_skill_name(value)})


def _skill_use_entries_from_json(text: str) -> list[dict]:
    try:
        payload = json.loads(text)
    except Exception:
        return []

    entries = payload.get("skills", payload) if isinstance(payload, dict) else payload
    if isinstance(entries, dict):
        entries = [entries]
    if not isinstance(entries, list):
        return []
    return [entry for entry in entries if isinstance(entry, dict)]


def _skill_use_entries_from_markdown(text: str) -> list[dict]:
    if not re.search(
        r"\b(skill[-_ ]?use|applied_rules|evidence_refs|output_files|verification)\b",
        text,
        re.IGNORECASE,
    ):
        return []

    entries: list[dict] = []
    current: dict[str, object] = {}
    for line in text.splitlines():
        match = re.match(
            r"\s*[-*]?\s*"
            r"(skill_path|applied_rules|evidence_refs|output_files|verification)"
            r"\s*:\s*(.+)",
            line,
        )
        if not match:
            continue

        field, value = match.group(1), match.group(2).strip()
        if field == "skill_path":
            if current:
                entries.append(current)
            current = {"skill_path": value}
        elif current:
            current[field] = value
    if current:
        entries.append(current)
    return entries


def _field_present(value: object) -> bool:
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, list):
        return any(_field_present(item) for item in value)
    if isinstance(value, dict):
        return any(_field_present(item) for item in value.values())
    return value is not None


def _complete_skill_use_names(path: Path) -> list[str]:
    if not path.is_file():
        return []

    text = path.read_text(encoding="utf-8", errors="replace")
    entries = (
        _skill_use_entries_from_json(text)
        if path.suffix.lower() == ".json"
        else _skill_use_entries_from_markdown(text)
    )
    names: list[str] = []
    for entry in entries:
        skill_name = normalize_skill_name(str(entry.get("skill_path") or ""))
        if not skill_name:
            continue
        if all(_field_present(entry.get(field)) for field in SKILL_USE_REQUIRED_FIELDS):
            names.append(skill_name)
    return sorted(set(names))


def _standard_context_paths(task_dir: Path, names: list[str]) -> list[Path]:
    return [task_dir / "context" / name for name in names]


def build_skill_coverage(task_dir: Path | str) -> dict:
    task_dir = Path(task_dir)

    selected_names: set[str] = set()
    loaded_paths: set[str] = set()
    used_sources: dict[str, str] = {}
    generated_from: list[str] = []

    selected_paths = _standard_context_paths(
        task_dir,
        ["specialist-dispatch.md", "specialist-dispatch.json"],
    )
    selected_source = "unknown"
    for path in selected_paths:
        if not path.is_file():
            continue
        generated_from.append(_evidence_name(task_dir, path))
        names = parse_selected_skill_names_from_text(
            path.read_text(encoding="utf-8", errors="replace")
        )
        if names:
            selected_source = _evidence_name(task_dir, path)
            selected_names.update(names)

    for path in _standard_context_paths(
        task_dir,
        ["skill-load.md", "skill-load.json", "codex-skill-context.md"],
    ):
        if not path.is_file():
            continue
        generated_from.append(_evidence_name(task_dir, path))
        loaded_paths.update(extract_loaded_skill_paths(path.read_text(encoding="utf-8", errors="replace")))

    loaded_names = {normalize_skill_name(path) for path in loaded_paths if normalize_skill_name(path)}

    for path in _standard_context_paths(task_dir, ["skill-use.json", "skill-use.md"]):
        if not path.is_file():
            continue
        generated_from.append(_evidence_name(task_dir, path))
        for name in _complete_skill_use_names(path):
            used_sources[name] = _evidence_name(task_dir, path)

    for name in ("tdd_log.md", "tdd-red.md", "test-case-mapping.md"):
        path = task_dir / "context" / name
        if path.is_file():
            generated_from.append(_evidence_name(task_dir, path))
            used_sources.setdefault("tdd.md", _evidence_name(task_dir, path))
            break

    selected_rows = [
        {"name": name, "source": selected_source, "confidence": "observed"}
        for name in sorted(selected_names)
    ]
    loaded_rows = [
        {
            "name": normalize_skill_name(path),
            "path": path,
            "source": "skill-load",
            "confidence": "observed",
        }
        for path in sorted(loaded_paths, key=lambda value: normalize_skill_name(value))
        if normalize_skill_name(path)
    ]
    used_rows = [
        {"name": name, "source": source, "confidence": "derived"}
        for name, source in sorted(used_sources.items())
    ]

    observed_names = set(used_sources)
    known_names = selected_names | loaded_names
    unknown_rows = [
        {
            "name": name,
            "reason": "selected_or_loaded_but_no_deterministic_usage_signal",
        }
        for name in sorted(known_names - observed_names)
    ]

    advisory_gaps: list[str] = []
    if selected_source == "unknown":
        advisory_gaps.append("selected skill set was not observed")
    if unknown_rows:
        advisory_gaps.append("some selected or loaded skills have no deterministic usage signal")
    if selected_names and loaded_names and selected_names != loaded_names:
        advisory_gaps.append("selected and loaded skill sets differ")

    return {
        "schema_version": "agent-crew.skill-coverage.v1",
        "selected": len(selected_rows),
        "loaded": len(loaded_rows),
        "used_observed": len(used_rows),
        "unknown_or_not_observed_count": len(unknown_rows),
        "advisory_gap": bool(advisory_gaps),
        "selected_source": selected_source,
        "selected_skills": selected_rows,
        "loaded_skills": loaded_rows,
        "used_skills": used_rows,
        "unknown_or_not_observed_skills": unknown_rows,
        "unknown_or_not_observed": unknown_rows,
        "advisory_gaps": advisory_gaps,
        "generated_from": sorted(set(generated_from)),
    }
