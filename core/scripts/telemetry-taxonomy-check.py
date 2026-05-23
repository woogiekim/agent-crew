#!/usr/bin/env python3
"""Correlate live telemetry retry/blocker labels with retry-chaos taxonomy.

The retry-chaos fixture defines the governed failure vocabulary for retries,
blocked handoffs, and terminal recovery outcomes. This checker reads real
`progress.buffer.jsonl` files and verifies that explicit retry/blocker labels
match the same taxonomy, so production telemetry can be compared against the
golden failure cases.

Read-only by design: no state files are modified.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any


TASK_ID_RE = re.compile(r"^\d{8}-\d{6}(?:-\d+)?$")
EXPLICIT_TOKEN_RE = re.compile(r"\b(?:taxonomy_label|retry_reason|reason|blocker|blocked_by)=([A-Za-z0-9_.:-]+)")
EXPLICIT_FIELDS = ("taxonomy_label", "retry_reason", "reason", "blocker", "blocked_by")
CLASSIFIABLE_EVENTS = {
    "RETRY",
    "BLOCKED",
    "COST_BLOCKED",
    "STAGE_TIMEOUT",
    "STAGE_FANOUT_BLOCKED",
    "STATUS",
}
COVERAGE_CATEGORIES = ("tool", "delegation", "token")


def load_json(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return None, str(exc)
    if not isinstance(payload, dict):
        return None, "fixture root must be an object"
    return payload, None


def invalid_fixture(fixture_path: Path, detail: str) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "fixture": str(fixture_path),
        "taxonomy": [],
        "passed": False,
        "error_type": "invalid_fixture",
        "summary": {
            "tasks": 0,
            "events": 0,
            "classified_events": 0,
            "unknown_labels": 0,
            "required_labels_present": 0,
        },
        "tasks": [],
        "failures": [detail],
    }


def load_taxonomy(fixture_path: Path) -> tuple[set[str] | None, dict[str, Any] | None]:
    fixture, error = load_json(fixture_path)
    if fixture is None:
        return None, invalid_fixture(fixture_path, error or "fixture_parse_failed")

    cases = fixture.get("cases")
    if fixture.get("schema_version") != 1 or not isinstance(cases, list) or not cases:
        return None, invalid_fixture(fixture_path, "fixture must have schema_version=1 and non-empty cases array")

    labels: set[str] = set()
    for case in cases:
        if not isinstance(case, dict):
            return None, invalid_fixture(fixture_path, "fixture cases must be objects")
        expected = case.get("expected")
        if not isinstance(expected, dict):
            continue
        labels.update(_string_list(expected.get("retry_reasons")))
        labels.update(_string_list(expected.get("blocked_by")))

    if not labels:
        return None, invalid_fixture(fixture_path, "fixture did not define retry/blocker labels")

    return labels, None


def _string_list(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [item for item in value if isinstance(item, str) and item]
    return []


def resolve_state_dir(override: str | None) -> Path:
    if override:
        return Path(override).expanduser()
    env = os.environ.get("AGENT_CREW_STATE_DIR")
    if env:
        return Path(env).expanduser()
    home = os.environ.get("AGENT_CREW_HOME", str(Path.home() / ".agent-crew"))
    project = os.environ.get("AGENT_CREW_PROJECT", "default")
    return Path(home).expanduser() / "state" / project


def is_task_dir(path: Path) -> bool:
    if TASK_ID_RE.match(path.name):
        return True
    return any((path / marker).exists() for marker in ("register.json", "pipeline.json", "progress.buffer.jsonl"))


def discover_task_dirs(state_dir: Path, explicit_task_dirs: list[str]) -> list[Path]:
    if explicit_task_dirs:
        return [Path(item).expanduser() for item in explicit_task_dirs]
    tasks_root = state_dir / "tasks"
    if not tasks_root.is_dir():
        return []
    return sorted(path for path in tasks_root.iterdir() if path.is_dir() and is_task_dir(path))


def read_progress_buffer(task_dir: Path) -> list[dict[str, Any]]:
    path = task_dir / "progress.buffer.jsonl"
    if not path.is_file():
        return []

    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(event, dict):
            rows.append(event)
    return rows


def extract_labels(event: dict[str, Any], taxonomy: set[str]) -> tuple[set[str], set[str]]:
    labels: set[str] = set()
    unknown: set[str] = set()

    for field in EXPLICIT_FIELDS:
        for value in _string_list(event.get(field)):
            if value in taxonomy:
                labels.add(value)
            else:
                unknown.add(value)

    text_parts = [
        str(event.get("event") or ""),
        str(event.get("detail") or ""),
        str(event.get("message") or ""),
    ]
    text = "\n".join(text_parts)
    for label in taxonomy:
        if label in text:
            labels.add(label)

    for match in EXPLICIT_TOKEN_RE.finditer(text):
        value = match.group(1)
        if value in taxonomy:
            labels.add(value)
        else:
            unknown.add(value)

    return labels, unknown


def evaluate_task(task_dir: Path, taxonomy: set[str]) -> dict[str, Any]:
    events = read_progress_buffer(task_dir)
    classified = []
    labels: set[str] = set()
    unknown_labels: set[str] = set()

    for event in events:
        event_name = str(event.get("event") or "")
        event_labels, event_unknown = extract_labels(event, taxonomy)
        if event_name not in CLASSIFIABLE_EVENTS and not event_labels and not event_unknown:
            continue

        labels.update(event_labels)
        unknown_labels.update(event_unknown)
        if event_labels or event_unknown:
            classified.append({
                "event": event_name,
                "stage": event.get("stage"),
                "agent": event.get("agent"),
                "labels": sorted(event_labels),
                "unknown_labels": sorted(event_unknown),
            })

    coverage = telemetry_coverage(task_dir, events)

    return {
        "task_id": task_dir.name,
        "task_dir": str(task_dir),
        "events": len(events),
        "classified_events": len(classified),
        "coverage": coverage,
        "labels": sorted(labels),
        "unknown_labels": sorted(unknown_labels),
        "classified": classified,
    }


def _jsonl_count(path: Path) -> int:
    if not path.is_file():
        return 0
    count = 0
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            json.loads(line)
        except json.JSONDecodeError:
            continue
        count += 1
    return count


def telemetry_coverage(task_dir: Path, events: list[dict[str, Any]]) -> dict[str, Any]:
    tool_events = _jsonl_count(task_dir / "tool-events.jsonl")
    delegation_events = _jsonl_count(task_dir / "delegation.jsonl")
    token_events = _jsonl_count(task_dir.parent.parent / "cost" / f"{task_dir.name}.jsonl")
    weak = []
    if tool_events == 0:
        weak.append("tool")
    if delegation_events == 0:
        weak.append("delegation")
    if token_events == 0:
        weak.append("token")
    return {
        "events_present": len(events) > 0,
        "tool_events": tool_events,
        "delegation_events": delegation_events,
        "token_events": token_events,
        "weak_categories": weak,
    }


def evaluate(
    state_dir: Path,
    fixture_path: Path,
    task_dirs: list[str],
    required_labels: list[str],
) -> dict[str, Any]:
    taxonomy, invalid = load_taxonomy(fixture_path)
    if invalid:
        return invalid
    assert taxonomy is not None

    tasks = [evaluate_task(task_dir, taxonomy) for task_dir in discover_task_dirs(state_dir, task_dirs)]
    observed_labels = {
        label
        for task in tasks
        for label in task["labels"]
    }
    unknown_labels = sorted({
        label
        for task in tasks
        for label in task["unknown_labels"]
    })
    missing_required = sorted(label for label in required_labels if label not in observed_labels)
    invalid_required = sorted(label for label in required_labels if label not in taxonomy)

    failures: list[dict[str, Any] | str] = []
    if not tasks:
        failures.append({
            "code": "insufficient_telemetry_coverage",
            "detail": "no task telemetry streams were found",
        })
    for task in tasks:
        coverage = task["coverage"]
        if not coverage["events_present"]:
            failures.append({
                "task_id": task["task_id"],
                "code": "insufficient_telemetry_coverage",
                "detail": "progress.buffer.jsonl has zero usable telemetry events",
            })
        elif coverage["weak_categories"]:
            failures.append({
                "task_id": task["task_id"],
                "code": "weak_telemetry_coverage",
                "weak_categories": coverage["weak_categories"],
            })
    for task in tasks:
        if task["unknown_labels"]:
            failures.append({
                "task_id": task["task_id"],
                "unknown_labels": task["unknown_labels"],
            })
    if invalid_required:
        failures.append({"invalid_required_labels": invalid_required})
    if missing_required:
        failures.append({"missing_required_labels": missing_required})

    return {
        "schema_version": 1,
        "fixture": str(fixture_path),
        "state_dir": str(state_dir),
        "taxonomy": sorted(taxonomy),
        "passed": not failures,
        "summary": {
            "tasks": len(tasks),
            "events": sum(task["events"] for task in tasks),
            "classified_events": sum(task["classified_events"] for task in tasks),
            "unknown_labels": len(unknown_labels),
            "required_labels_present": len(required_labels) - len(missing_required),
            "tasks_with_events": sum(1 for task in tasks if task["coverage"]["events_present"]),
            "weak_tool_coverage": sum(1 for task in tasks if "tool" in task["coverage"]["weak_categories"]),
            "weak_delegation_coverage": sum(1 for task in tasks if "delegation" in task["coverage"]["weak_categories"]),
            "weak_token_coverage": sum(1 for task in tasks if "token" in task["coverage"]["weak_categories"]),
        },
        "tasks": tasks,
        "failures": failures,
    }


def print_text(result: dict[str, Any]) -> None:
    print(("PASS" if result["passed"] else "FAIL") + ": telemetry taxonomy check")
    summary = result["summary"]
    print(
        "tasks={tasks} events={events} classified_events={classified_events} "
        "unknown_labels={unknown_labels}".format(**summary)
    )
    for task in result["tasks"]:
        if task["labels"] or task["unknown_labels"]:
            print(
                f"- {task['task_id']}: labels={','.join(task['labels']) or '-'} "
                f"unknown={','.join(task['unknown_labels']) or '-'}"
            )
    for failure in result["failures"]:
        print(f"- {failure}")


def main() -> int:
    repo_root = Path(__file__).resolve().parent.parent.parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-dir", default=None)
    parser.add_argument("--task-dir", action="append", default=[])
    parser.add_argument("--fixture", default=str(repo_root / "core" / "evaluations" / "retry-chaos.json"))
    parser.add_argument("--require-label", action="append", default=[])
    parser.add_argument("--format", choices=["json", "text"], default="text")
    args = parser.parse_args()

    result = evaluate(
        resolve_state_dir(args.state_dir).resolve(),
        Path(args.fixture).expanduser().resolve(),
        args.task_dir,
        args.require_label,
    )

    if args.format == "json":
        json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
        print()
    else:
        print_text(result)

    if result.get("error_type") == "invalid_fixture":
        return 2
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
