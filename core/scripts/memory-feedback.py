#!/usr/bin/env python3
"""Send Mnemos feedback for validated memory-usage decisions.

Inputs: `--task-dir DIR` with `context/memory-usage.json` and
`context/memory-retrieval.json`; optional `--review-response FILE` for
validated feedback.
Outputs: `context/memory-feedback.json`; failed sends are appended to
`context/memory-feedback-outbox.jsonl`.
Exit codes: always 0 for feedback disablement, validation failure, provider
timeout/error, and successful sends so the task result is never changed by
feedback transport. Exit 2 is reserved for invalid local arguments.
Example:
  AGENT_CREW_MEMORY_FEEDBACK=1 memory-feedback.py --task-dir "$TASK_DIR" --event applied
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_now_z() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def load_validator():
    script = Path(__file__).resolve().with_name("validate-memory-usage.py")
    spec = importlib.util.spec_from_file_location("validate_memory_usage", script)
    if not spec or not spec.loader:
        raise RuntimeError("cannot load validate-memory-usage.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def existing_event_ids(path: Path) -> set[str]:
    payload = read_json(path)
    ids = set()
    for key in ("sent_events", "failed_events", "skipped_events"):
        rows = payload.get(key)
        if not isinstance(rows, list):
            continue
        for row in rows:
            if isinstance(row, dict) and row.get("event_id"):
                ids.add(str(row["event_id"]))
    return ids


def event_id(*, task_id: str, memory_id: str, event: str, artifact: str, locator: str) -> str:
    raw = "\x1f".join([task_id, memory_id, event, artifact, locator])
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]
    return f"memfb-{digest}"


def review_is_final_approved(task_dir: Path, review_response: str | None) -> bool:
    if not review_response:
        return False
    response = Path(review_response)
    if not response.is_absolute():
        response = task_dir / response
    if not response.is_file():
        return False
    text = response.read_text(encoding="utf-8", errors="replace")
    last_review_index = text.upper().rfind("REVIEW:")
    if last_review_index >= 0:
        text = text[last_review_index:]
    temp_path = None
    classifier_response = response
    if text != response.read_text(encoding="utf-8", errors="replace"):
        handle = tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False)
        try:
            handle.write(text)
            temp_path = Path(handle.name)
            classifier_response = temp_path
        finally:
            handle.close()
    classifier = Path(__file__).resolve().with_name("reviewer-loop-decision.py")
    result = subprocess.run(
        [
            sys.executable,
            str(classifier),
            "--response",
            str(classifier_response),
            "--task-dir",
            str(task_dir),
            "--format",
            "json",
        ],
        check=False,
        text=True,
        capture_output=True,
    )
    if temp_path is not None:
        try:
            temp_path.unlink()
        except OSError:
            pass
    if result.returncode != 0:
        return False
    try:
        payload = json.loads(result.stdout)
    except Exception:
        return False
    return payload.get("action") == "approve"


def feedback_requests(
    *,
    task_dir: Path,
    event: str,
    usage: dict[str, Any],
    retrieval: dict[str, Any],
    agent_role: str,
) -> list[dict[str, Any]]:
    scope = retrieval.get("request", {}).get("scope", {}) if isinstance(retrieval.get("request"), dict) else {}
    project_id = str(scope.get("project_id") or "")
    task_id = str(usage.get("task_id") or task_dir.name)
    requests = []
    for decision in usage.get("decisions", []):
        if not isinstance(decision, dict):
            continue
        if decision.get("disposition") != "applied":
            continue
        memory_id = str(decision.get("memory_id") or "")
        reason_code = str(decision.get("reason_code") or "")
        applications = decision.get("applications") if isinstance(decision.get("applications"), list) else []
        for application in applications:
            if not isinstance(application, dict):
                continue
            artifact = str(application.get("artifact") or "")
            locator = str(application.get("locator") or "")
            requests.append(
                {
                    "schema_version": "mnemos.feedback.request.v1",
                    "event_id": event_id(
                        task_id=task_id,
                        memory_id=memory_id,
                        event=event,
                        artifact=artifact,
                        locator=locator,
                    ),
                    "event": event,
                    "memory_id": memory_id,
                    "task_id": task_id,
                    "project_id": project_id,
                    "agent_role": agent_role,
                    "application": application,
                    "reason_code": reason_code,
                }
            )
    return requests


def send_feedback(memory_bin: Path, request: dict[str, Any]) -> tuple[bool, dict[str, Any]]:
    result = subprocess.run(
        [str(memory_bin), "feedback", "--request-json", json.dumps(request, ensure_ascii=False, sort_keys=True)],
        check=False,
        text=True,
        capture_output=True,
        env={**os.environ, "AGENT_CREW_MEMORY_FEEDBACK": "1"},
    )
    try:
        payload = json.loads(result.stdout.strip()) if result.stdout.strip() else {}
    except Exception:
        payload = {"status": "invalid_json", "stdout": result.stdout}
    payload["exit_code"] = result.returncode
    if result.stderr:
        payload["stderr"] = result.stderr
    ok = result.returncode == 0 and payload.get("status", "ok") == "ok"
    return ok, payload


def append_outbox(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def build_report(
    *,
    status: str,
    task_dir: Path,
    validation: dict[str, Any] | None = None,
    sent_events: list[dict[str, Any]] | None = None,
    skipped_events: list[dict[str, Any]] | None = None,
    failed_events: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "created_at": utc_now_z(),
        "status": status,
        "task_dir": str(task_dir),
        "validation_passed": None if validation is None else bool(validation.get("passed")),
        "sent_events": sent_events or [],
        "skipped_events": skipped_events or [],
        "failed_events": failed_events or [],
    }


def execute(args: argparse.Namespace) -> dict[str, Any]:
    task_dir = Path(args.task_dir).expanduser().resolve()
    context_dir = task_dir / "context"
    report_path = context_dir / "memory-feedback.json"
    outbox_path = context_dir / "memory-feedback-outbox.jsonl"
    if os.environ.get("AGENT_CREW_MEMORY_FEEDBACK", "0") != "1":
        report = build_report(status="disabled", task_dir=task_dir)
        write_json(report_path, report)
        return report

    validator = load_validator()
    validation = validator.validate_usage(task_dir, strict=True)
    if not validation.get("passed"):
        report = build_report(status="validation_failed", task_dir=task_dir, validation=validation)
        write_json(report_path, report)
        return report

    if args.event == "validated" and not review_is_final_approved(task_dir, args.review_response):
        report = build_report(status="review_not_approved", task_dir=task_dir, validation=validation)
        write_json(report_path, report)
        return report

    usage = read_json(context_dir / "memory-usage.json")
    retrieval = read_json(context_dir / "memory-retrieval.json")
    requested_events = [args.event] if args.event in {"applied", "validated"} else ["applied", "validated"]
    sent_ids = existing_event_ids(report_path)
    sent_events: list[dict[str, Any]] = []
    skipped_events: list[dict[str, Any]] = []
    failed_events: list[dict[str, Any]] = []
    memory_bin = Path(args.memory_bin or Path(args.agent_crew_home).expanduser() / "bin" / "memory")

    for event_name in requested_events:
        if event_name == "validated" and not review_is_final_approved(task_dir, args.review_response):
            continue
        for request in feedback_requests(
            task_dir=task_dir,
            event=event_name,
            usage=usage,
            retrieval=retrieval,
            agent_role=args.agent_role,
        ):
            if request["event_id"] in sent_ids:
                skipped_events.append({"event_id": request["event_id"], "reason": "duplicate"})
                continue
            ok, provider_response = send_feedback(memory_bin, request)
            row = {
                "event_id": request["event_id"],
                "event": request["event"],
                "memory_id": request["memory_id"],
                "provider_response": provider_response,
            }
            if ok:
                sent_events.append(row)
                sent_ids.add(request["event_id"])
            else:
                failed_events.append(row)
                append_outbox(outbox_path, {"created_at": utc_now_z(), "request": request, "provider_response": provider_response})

    if failed_events:
        status = "feedback_failed"
    elif sent_events:
        status = "sent"
    elif skipped_events:
        status = "already_sent"
    else:
        status = "no_events"
    previous = read_json(report_path)
    previous_sent = previous.get("sent_events") if isinstance(previous.get("sent_events"), list) else []
    report = build_report(
        status=status,
        task_dir=task_dir,
        validation=validation,
        sent_events=previous_sent + sent_events,
        skipped_events=skipped_events,
        failed_events=failed_events,
    )
    write_json(report_path, report)
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task-dir", required=True)
    parser.add_argument("--event", choices=("applied", "validated", "all"), default="applied")
    parser.add_argument("--review-response")
    parser.add_argument("--agent-role", default="analyst")
    parser.add_argument("--agent-crew-home", default=os.environ.get("AGENT_CREW_HOME", str(Path.home() / ".agent-crew")))
    parser.add_argument("--memory-bin")
    parser.add_argument("--format", choices=("json", "text"), default="text")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = execute(args)
    if args.format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"STATUS: {report['status']}")
        print(f"SENT: {len(report['sent_events'])}")
        print(f"FAILED: {len(report['failed_events'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
