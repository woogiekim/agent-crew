#!/usr/bin/env python3
"""Validate task memory-usage.json.

Inputs: `--task-dir DIR` containing `context/memory-retrieval.json`,
`context/memory-usage.json`, and referenced artifacts.
Outputs: JSON or text findings.
Exit codes: 0 valid, 1 non-strict invariant warnings, 2 strict/schema failure,
3 invalid local arguments or unreadable required files.
Example:
  validate-memory-usage.py --task-dir "$TASK_DIR"
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from project_memory_source import can_review_candidate, project_source_issue
except ModuleNotFoundError:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from project_memory_source import can_review_candidate, project_source_issue


DISPOSITIONS = {
    "applied",
    "accepted_not_applied",
    "ignored",
    "superseded",
    "conflict_with_current_requirements",
    "conflict_with_managed_rule",
}
ADVISORY_ONLY_LAYERS = {"session", "global_candidate"}
INACTIVE_STATUSES = {"deprecated", "invalidated"}


def utc_now_z() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def read_json(path: Path) -> tuple[Any, str | None]:
    try:
        return json.loads(path.read_text(encoding="utf-8")), None
    except Exception as exc:
        return None, str(exc)


def pointer_exists(document: Any, pointer: str) -> bool:
    if pointer == "":
        return True
    if not pointer.startswith("/"):
        return False
    current = document
    for raw_part in pointer.split("/")[1:]:
        part = raw_part.replace("~1", "/").replace("~0", "~")
        if isinstance(current, list):
            if not part.isdigit():
                return False
            index = int(part)
            if index >= len(current):
                return False
            current = current[index]
        elif isinstance(current, dict):
            if part not in current:
                return False
            current = current[part]
        else:
            return False
    return True


def markdown_heading_exists(text: str, heading: str) -> bool:
    wanted = heading.strip().lstrip("#").strip().lower()
    for line in text.splitlines():
        match = re.match(r"^\s{0,3}#{1,6}\s+(.+?)\s*#*\s*$", line)
        if match and match.group(1).strip().lower() == wanted:
            return True
    return False


def retrieval_results(retrieval: dict[str, Any]) -> list[dict[str, Any]]:
    rows = retrieval.get("results")
    if isinstance(rows, list):
        return [row for row in rows if isinstance(row, dict)]
    return provider_results(retrieval)


def provider_results(retrieval: dict[str, Any]) -> list[dict[str, Any]]:
    provider = retrieval.get("provider_response")
    if isinstance(provider, dict):
        rows = provider.get("results")
        if isinstance(rows, list):
            return [row for row in rows if isinstance(row, dict)]
    return []


def memory_id(row: dict[str, Any]) -> str:
    return str(row.get("memory_id") or row.get("id") or "")


def matched_project_id(row: dict[str, Any], scope: dict[str, Any]) -> str | None:
    project_id = str(scope.get("project_id") or "")
    root_hash = scope.get("project_root_hash")
    row_hash = row.get("project_root_hash")
    if project_id and row.get("project_id") == project_id and (not root_hash or not row_hash or row_hash == root_hash):
        return project_id

    source_scope = scope.get("project_context")
    if (
        isinstance(source_scope, dict)
        and source_scope.get("project_id")
        and source_scope.get("project_root_hash")
        and row.get("record_type") == "project_context_section"
        and row.get("source_path")
        and row.get("source_section")
        and row.get("project_id") == source_scope["project_id"]
        and row_hash == source_scope["project_root_hash"]
    ):
        return str(source_scope["project_id"])
    return None


def finding(code: str, message: str, severity: str = "warning", **extra: Any) -> dict[str, Any]:
    payload = {"code": code, "severity": severity, "message": message}
    payload.update(extra)
    return payload


def load_artifact(task_dir: Path, artifact: str) -> tuple[Path, Any, str | None]:
    path = (task_dir / artifact).resolve() if not Path(artifact).is_absolute() else Path(artifact)
    if not path.is_file():
        return path, None, "artifact_missing"
    if path.suffix == ".json":
        data, error = read_json(path)
        if error:
            return path, None, "artifact_invalid_json"
        return path, data, None
    return path, path.read_text(encoding="utf-8", errors="replace"), None


def project_retrieval_root_issue(recorded: Any, current: str | None, scope: dict[str, Any]) -> str | None:
    context = scope.get("project_context")
    expected_hash = context.get("project_root_hash") if isinstance(context, dict) else None
    if not current and not expected_hash:
        return None
    if not isinstance(recorded, str) or not Path(recorded).is_absolute():
        return "project_retrieval_root_unavailable"
    try:
        recalled_root = Path(recorded).resolve(strict=True)
        current_root = Path(current).expanduser().resolve(strict=True) if current else recalled_root
    except (OSError, RuntimeError, ValueError):
        return "project_retrieval_root_unavailable"
    if not recalled_root.is_dir() or not current_root.is_dir():
        return "project_retrieval_root_unavailable"
    if recalled_root != current_root:
        return "project_retrieval_root_mismatch"
    if expected_hash and hashlib.sha256(str(recalled_root).encode("utf-8")).hexdigest()[:16] != expected_hash:
        return "project_retrieval_root_mismatch"
    return None


def live_use_issues(memory_bin: str, memory_ids: list[str]) -> dict[str, str]:
    if not memory_ids:
        return {}

    unavailable = "memory_current_state_unavailable"
    command = [str(Path(memory_bin).expanduser()), "read", "--read-only", "--json"]
    if len(memory_ids) > 1:
        command.append("--eligibility-only")
    try:
        result = subprocess.run([*command, "--", *memory_ids], check=False, capture_output=True, text=True, timeout=10)
        current = json.loads(result.stdout)
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return dict.fromkeys(memory_ids, unavailable)

    if result.returncode or not isinstance(current, dict):
        return dict.fromkeys(memory_ids, unavailable)
    if len(memory_ids) == 1:
        rows = [current]
    elif current.get("schema_version") == "mnemos.read-eligibility.response.v1" and isinstance(current.get("items"), list):
        rows = current["items"]
    else:
        return dict.fromkeys(memory_ids, unavailable)

    states = {}
    for row in rows:
        if isinstance(row, dict) and isinstance(row.get("id"), str):
            mid = row["id"]
            states[mid] = None if mid in states else row.get("eligible_for_use")

    issues = {}
    for mid in memory_ids:
        state = states.get(mid)
        if state is not True:
            issues[mid] = "memory_no_longer_eligible" if state is False else unavailable
    return issues


def validate_usage(task_dir: Path, *, strict: bool = False, project_root: str | None = None,
                   memory_bin: str | None = None) -> dict[str, Any]:
    context_dir = task_dir / "context"
    usage_path = context_dir / "memory-usage.json"
    retrieval_path = context_dir / "memory-retrieval.json"
    usage, usage_error = read_json(usage_path)
    retrieval, retrieval_error = read_json(retrieval_path)
    findings: list[dict[str, Any]] = []
    if usage_error:
        findings.append(finding("usage_unreadable", usage_error, "error"))
        return result_payload(task_dir, findings, usage={}, retrieval={})
    if retrieval_error:
        findings.append(finding("retrieval_unreadable", retrieval_error, "error"))
        retrieval = {}
    if not isinstance(usage, dict):
        findings.append(finding("usage_not_object", "memory-usage.json must be an object", "error"))
        usage = {}
    if not isinstance(retrieval, dict):
        retrieval = {}

    if usage.get("schema_version") != "agent-crew.memory-usage.v2":
        findings.append(finding("schema_version_invalid", "schema_version must be agent-crew.memory-usage.v2", "error"))
    decisions = usage.get("decisions")
    if not isinstance(decisions, list):
        findings.append(finding("decisions_not_array", "decisions must be an array", "error"))
        decisions = []

    selected_rows = retrieval_results(retrieval)
    selected_by_id = {memory_id(row): row for row in selected_rows if memory_id(row)}
    candidates_by_id = {memory_id(row): row for row in provider_results(retrieval) if memory_id(row)}
    retrieval_scope = retrieval.get("request", {}).get("scope", {}) if isinstance(retrieval.get("request"), dict) else {}
    has_project_scope = bool(retrieval_scope.get("project_id") or retrieval_scope.get("project_context"))
    root_issue = project_retrieval_root_issue(retrieval.get("project_root"), project_root, retrieval_scope)
    seen: set[str] = set()

    for index, decision in enumerate(decisions):
        if not isinstance(decision, dict):
            findings.append(finding("decision_not_object", "decision must be an object", "error", index=index))
            continue
        mid = str(decision.get("memory_id") or "")
        disposition = decision.get("disposition")
        applications = decision.get("applications")
        if disposition not in DISPOSITIONS:
            findings.append(finding("disposition_invalid", f"invalid disposition: {disposition}", "error", memory_id=mid))
        if not isinstance(applications, list):
            findings.append(finding("applications_not_array", "applications must be an array", "error", memory_id=mid))
            applications = []
        if mid in seen:
            findings.append(finding("duplicate_decision", f"duplicate decision for {mid}", "warning", memory_id=mid))
        seen.add(mid)
        selected = selected_by_id.get(mid)
        excerpt = None
        review = decision.get("source_review")
        candidate = candidates_by_id.get(mid)
        if (
            selected is None and candidate is not None and disposition == "applied"
            and decision.get("reason_code") == "source_reviewed_candidate"
            and isinstance(review, dict)
            and isinstance(retrieval.get("project_root"), str)
            and all(isinstance(review.get(key), str) and review[key].strip() for key in ("excerpt", "relevance"))
            and can_review_candidate(candidate, retrieval_scope)
        ):
            selected = candidate
            excerpt = review["excerpt"].strip("\r\n")
        if selected is None:
            findings.append(finding("memory_not_selected", f"{mid} is not present in selected recall results", "warning", memory_id=mid))
        if disposition == "applied" and not applications:
            findings.append(finding("applied_without_applications", "applied decisions require applications", "warning", memory_id=mid))
        if disposition == "ignored" and applications:
            findings.append(finding("ignored_has_applications", "ignored decisions cannot include applications", "warning", memory_id=mid))
        if disposition == "conflict_with_managed_rule" and applications:
            findings.append(finding("managed_rule_conflict_applied", "managed-rule conflicts cannot be applied", "warning", memory_id=mid))
        if selected is not None:
            layer = str(selected.get("layer") or "")
            status = str(selected.get("semantic_status") or "")
            if disposition == "applied":
                if status in INACTIVE_STATUSES or status != "active":
                    findings.append(finding("inactive_memory_applied", f"inactive memory cannot be applied: {status}", "warning", memory_id=mid))
                if selected.get("superseded_by"):
                    findings.append(finding("superseded_applied", "superseded memory cannot be applied", "warning", memory_id=mid))
                if layer == "project" and has_project_scope and matched_project_id(selected, retrieval_scope) is None:
                    findings.append(finding("wrong_project_applied", "different project memory cannot be applied", "warning", memory_id=mid))
                if layer == "project" and root_issue:
                    findings.append(finding(root_issue, "cannot verify that the recalled root matches the current checkout", memory_id=mid))
                elif (
                    layer == "project"
                    and selected.get("record_type") == "project_context_section"
                    and "project_root" in retrieval
                ):
                    issue = project_source_issue(retrieval["project_root"], selected, excerpt=excerpt)
                    if issue:
                        findings.append(finding(
                            issue, "cannot verify the recalled project source at its recorded location",
                            memory_id=mid,
                        ))
        else:
            layer = ""
        for app_index, app in enumerate(applications):
            if not isinstance(app, dict):
                findings.append(finding("application_not_object", "application must be an object", "error", memory_id=mid))
                continue
            artifact = str(app.get("artifact") or "")
            locator_type = str(app.get("locator_type") or "")
            locator = str(app.get("locator") or "")
            artifact_path, artifact_data, artifact_error = load_artifact(task_dir, artifact)
            if artifact_error:
                findings.append(finding(artifact_error, f"{artifact} is not readable", "warning", memory_id=mid, artifact=artifact))
                continue
            if locator_type == "json_pointer":
                if not pointer_exists(artifact_data, locator):
                    findings.append(finding("json_pointer_missing", f"{locator} not found in {artifact}", "warning", memory_id=mid, artifact=artifact))
            elif locator_type == "markdown_heading":
                if not isinstance(artifact_data, str) or not markdown_heading_exists(artifact_data, locator):
                    findings.append(finding("markdown_heading_missing", f"{locator} heading not found in {artifact}", "warning", memory_id=mid, artifact=artifact))
            else:
                findings.append(finding("locator_type_invalid", f"unknown locator_type {locator_type}", "error", memory_id=mid))
            if disposition == "applied" and layer in ADVISORY_ONLY_LAYERS and Path(artifact).name == "pipeline.json":
                findings.append(
                    finding(
                        "advisory_layer_pipeline_change",
                        f"{layer} memory cannot deterministically change pipeline.json",
                        "warning",
                        memory_id=mid,
                        artifact=artifact,
                    )
                )

    for mid in selected_by_id:
        if mid not in seen:
            findings.append(
                finding(
                    "selected_memory_missing_decision",
                    f"selected memory {mid} has no memory-usage decision",
                    "warning",
                    memory_id=mid,
                )
            )

    if memory_bin:
        allowed = set(feedback_allowed_ids(usage, findings))
        applied = {memory_id(row) for row in decisions if isinstance(row, dict) and row.get("disposition") == "applied"}
        for mid, issue in live_use_issues(memory_bin, sorted(allowed & applied)).items():
            findings.append(finding(issue, "cannot confirm the current eligibility of the recalled memory", memory_id=mid))

    payload = result_payload(task_dir, findings, usage=usage, retrieval=retrieval)
    if strict:
        payload["strict"] = True
        for item in payload["findings"]:
            if item["severity"] == "warning":
                item["strict_blocker"] = True
    return payload


def result_payload(task_dir: Path, findings: list[dict[str, Any]], *, usage: dict[str, Any], retrieval: dict[str, Any]) -> dict[str, Any]:
    error_count = sum(1 for item in findings if item["severity"] == "error")
    warning_count = sum(1 for item in findings if item["severity"] == "warning")
    return {
        "schema_version": 1,
        "task_dir": str(task_dir),
        "passed": not findings,
        "findings": findings,
        "error_count": error_count,
        "warning_count": warning_count,
        "memory_feedback_allowed_ids": feedback_allowed_ids(usage, findings),
    }


def feedback_allowed_ids(usage: dict[str, Any], findings: list[dict[str, Any]]) -> list[str]:
    blocked = {str(item.get("memory_id")) for item in findings if item.get("memory_id")}
    allowed: list[str] = []
    for decision in usage.get("decisions", []) if isinstance(usage.get("decisions"), list) else []:
        if not isinstance(decision, dict):
            continue
        mid = str(decision.get("memory_id") or "")
        if mid and mid not in blocked:
            allowed.append(mid)
    return sorted(set(allowed))


def text_output(payload: dict[str, Any]) -> str:
    lines = [
        f"passed={str(payload['passed']).lower()} errors={payload['error_count']} warnings={payload['warning_count']}",
    ]
    for item in payload["findings"]:
        lines.append(f"{item['severity']}: {item['code']}: {item['message']}")
    return "\n".join(lines) + "\n"


def exit_code(payload: dict[str, Any], *, strict: bool) -> int:
    if payload["error_count"]:
        return 2
    if payload["warning_count"]:
        return 2 if strict else 1
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task-dir", required=True)
    parser.add_argument("--project-root", default=os.environ.get("PROJECT_ROOT"))
    parser.add_argument("--memory-bin", help="Check current use eligibility through this memory wrapper.")
    parser.add_argument("--strict", action="store_true", default=os.environ.get("AGENT_CREW_MEMORY_STRICT") == "1")
    parser.add_argument("--format", choices=("json", "text"), default="text")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    task_dir = Path(args.task_dir).expanduser().resolve()
    payload = validate_usage(task_dir, strict=args.strict, project_root=args.project_root, memory_bin=args.memory_bin)
    if args.format == "json":
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(text_output(payload), end="")
    return exit_code(payload, strict=args.strict)


if __name__ == "__main__":
    raise SystemExit(main())
