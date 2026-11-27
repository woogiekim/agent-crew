"""Tests for applied and validated memory feedback dispatch."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPT = REPO_ROOT / "core" / "scripts" / "memory-feedback.py"


def _selected_memory(memory_id: str = "mem-applied") -> dict:
    return {
        "memory_id": memory_id,
        "content": "project lesson",
        "layer": "project",
        "semantic_status": "active",
        "project_id": "agent-crew-abc123",
        "project_root_hash": "abc123",
        "superseded_by": [],
    }


def _application(locator: str = "/stages/0/tdd_parallel") -> dict:
    return {
        "artifact": "pipeline.json",
        "locator_type": "json_pointer",
        "locator": locator,
        "effect": "set_true",
    }


def _decision(memory_id: str, disposition: str, applications=None) -> dict:
    return {
        "memory_id": memory_id,
        "disposition": disposition,
        "reason_code": "matched_prior_aar",
        "applications": applications or [],
    }


def _write_task(tmp_path: Path, decisions: list[dict], *, selected=None, review: str | None = None) -> Path:
    task_dir = tmp_path / "task"
    context = task_dir / "context"
    context.mkdir(parents=True)
    (task_dir / "pipeline.json").write_text(
        json.dumps({"stages": [{"agents": ["backend"], "tdd_parallel": True}]}),
        encoding="utf-8",
    )
    (context / "review.md").write_text("review passed\n", encoding="utf-8")
    (context / "quality-metrics.json").write_text('{"schema_version":1}\n', encoding="utf-8")
    (context / "memory-retrieval.json").write_text(
        json.dumps({
            "status": "ok",
            "request": {"scope": {"project_id": "agent-crew-abc123", "project_root_hash": "abc123"}},
            "results": selected if selected is not None else [_selected_memory()],
        }),
        encoding="utf-8",
    )
    (context / "memory-usage.json").write_text(
        json.dumps({
            "schema_version": "agent-crew.memory-usage.v2",
            "retrieval_id": "task-1-recall",
            "task_id": "task-1",
            "decisions": decisions,
            "conflicts": [],
            "generated_by": "analyst",
            "generated_at_phase": "phase-1b-analysis",
        }),
        encoding="utf-8",
    )
    if review is not None:
        (context / "reviewer-response.txt").write_text(review, encoding="utf-8")
    return task_dir


def _memory_bin(tmp_path: Path, *, status: str = "ok", rc: int = 0) -> tuple[Path, Path]:
    calls = tmp_path / "feedback-calls.jsonl"
    memory = tmp_path / "memory"
    memory.write_text(
        f"""#!/usr/bin/env bash
printf '%s\\n' "$*" >> "{calls}"
if [ "{status}" = "ok" ]; then
  echo '{{"status":"ok","feedback_id":"fb-test"}}'
else
  echo '{{"status":"{status}","reason":"test_failure"}}'
fi
exit {rc}
""",
        encoding="utf-8",
    )
    memory.chmod(0o755)
    return memory, calls


def _run(task_dir: Path, memory_bin: Path, *extra: str, feedback: str = "1"):
    env = {"AGENT_CREW_MEMORY_FEEDBACK": feedback}
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--task-dir",
            str(task_dir),
            "--memory-bin",
            str(memory_bin),
            "--format",
            "json",
            *extra,
        ],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def _requests(calls: Path) -> list[dict]:
    requests = []
    for line in calls.read_text(encoding="utf-8").splitlines():
        marker = "--request-json "
        assert marker in line
        requests.append(json.loads(line.split(marker, 1)[1]))
    return requests


def test_feedback_flag_zero_sends_nothing(tmp_path: Path):
    task_dir = _write_task(tmp_path, [_decision("mem-applied", "applied", [_application()])])
    memory, calls = _memory_bin(tmp_path)

    result = _run(task_dir, memory, "--event", "applied", feedback="0")

    assert result.returncode == 0
    assert json.loads(result.stdout)["status"] == "disabled"
    assert not calls.exists()


def test_applied_feedback_sends_only_applied_decisions(tmp_path: Path):
    task_dir = _write_task(
        tmp_path,
        [
            _decision("mem-applied", "applied", [_application()]),
            _decision("mem-accepted", "accepted_not_applied"),
            _decision("mem-ignored", "ignored"),
        ],
        selected=[_selected_memory("mem-applied"), _selected_memory("mem-accepted"), _selected_memory("mem-ignored")],
    )
    memory, calls = _memory_bin(tmp_path)

    result = _run(task_dir, memory, "--event", "applied")

    assert result.returncode == 0, result.stdout + result.stderr
    requests = _requests(calls)
    assert [request["event"] for request in requests] == ["applied"]
    assert requests[0]["memory_id"] == "mem-applied"
    assert requests[0]["application"]["locator"] == "/stages/0/tdd_parallel"
    assert requests[0]["project_id"] == "agent-crew-abc123"


def test_validator_failure_sends_nothing(tmp_path: Path):
    task_dir = _write_task(tmp_path, [_decision("mem-applied", "applied", [_application("/missing")])])
    memory, calls = _memory_bin(tmp_path)

    result = _run(task_dir, memory, "--event", "applied")

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["status"] == "validation_failed"
    assert not calls.exists()


def test_validated_feedback_requires_final_reviewer_approval(tmp_path: Path):
    approved = "REVIEW: APPROVED\nREPORT: context/review.md\nISSUES: 0\nQUALITY_METRICS: context/quality-metrics.json\n"
    task_dir = _write_task(tmp_path, [_decision("mem-applied", "applied", [_application()])], review=approved)
    memory, calls = _memory_bin(tmp_path)

    result = _run(task_dir, memory, "--event", "validated", "--review-response", str(task_dir / "context" / "reviewer-response.txt"))

    assert result.returncode == 0, result.stdout + result.stderr
    requests = _requests(calls)
    assert [request["event"] for request in requests] == ["validated"]
    assert requests[0]["memory_id"] == "mem-applied"


def test_candidate_validated_feedback_requires_its_own_current_review(tmp_path: Path):
    review = "REVIEW: APPROVED\nREPORT: context/review.md\nISSUES: 0\nQUALITY_METRICS: context/quality-metrics.json\n"
    excerpt = "Check the original log before applying this lesson."
    section = f"# Evidence\n\n{excerpt}"
    decisions = [_decision("mem-applied", "applied", [_application()])]
    candidates = []
    for mid in ("reviewed", "other"):
        decision = _decision(mid, "applied", [_application()])
        decision.update(reason_code="source_reviewed_candidate", source_review={"excerpt": excerpt, "relevance": "Same target"})
        decisions.append(decision)
        candidates.append({**_selected_memory(mid), "record_type": "project_context_section", "source_path": "review-source.md",
                           "source_section": "Evidence", "source_content_hash": hashlib.sha256(section.encode()).hexdigest(),
                           "content": section})
    task = _write_task(tmp_path, decisions, review=review)
    context = task / "context"
    root = tmp_path / "project"
    root.mkdir()
    (root / "review-source.md").write_text(section, encoding="utf-8")
    retrieval_path = context / "memory-retrieval.json"
    data = json.loads(retrieval_path.read_text())
    data.update(project_root=str(root), provider_response={"results": candidates})
    retrieval_path.write_text(json.dumps(data), encoding="utf-8")
    review_path = context / "reviewer-response.txt"
    report = context / "review.md"
    memory, calls = _memory_bin(tmp_path)

    generic = _run(task, memory, "--event", "validated", "--review-response", str(review_path))

    assert generic.returncode == 0
    assert [request["memory_id"] for request in _requests(calls)] == ["mem-applied"]
    assert {row["memory_id"] for row in json.loads(generic.stdout)["skipped_events"]} == {"reviewed", "other"}

    usage_hash, retrieval_hash = (hashlib.sha256(path.read_bytes()).hexdigest()
                                  for path in (context / "memory-usage.json", retrieval_path))
    report.write_text(f"MEMORY_USE_APPROVED: reviewed {'0' * 64} {retrieval_hash}\n", encoding="utf-8")

    stale = _run(task, memory, "--event", "validated", "--review-response", str(review_path))

    assert stale.returncode == 0
    assert [request["memory_id"] for request in _requests(calls)] == ["mem-applied"]

    report.write_text(f"MEMORY_USE_APPROVED: reviewed {usage_hash} {retrieval_hash}\n", encoding="utf-8")

    confirmed = _run(task, memory, "--event", "validated", "--review-response", str(review_path))

    assert confirmed.returncode == 0
    assert [request["memory_id"] for request in _requests(calls)] == ["mem-applied", "reviewed"]
    assert all(request["event"] == "validated" for request in _requests(calls))


def test_needs_changes_does_not_send_validated(tmp_path: Path):
    task_dir = _write_task(
        tmp_path,
        [_decision("mem-applied", "applied", [_application()])],
        review="REVIEW: NEEDS_CHANGES\nISSUES: 1\n",
    )
    memory, calls = _memory_bin(tmp_path)

    result = _run(task_dir, memory, "--event", "validated", "--review-response", str(task_dir / "context" / "reviewer-response.txt"))

    assert result.returncode == 0
    assert json.loads(result.stdout)["status"] == "review_not_approved"
    assert not calls.exists()


def test_validated_feedback_is_sent_once_after_retry_final_approval(tmp_path: Path):
    review = (
        "REVIEW: NEEDS_CHANGES\nISSUES: 1\n"
        "\n--- retry ---\n"
        "REVIEW: APPROVED\nREPORT: context/review.md\nISSUES: 0\nQUALITY_METRICS: context/quality-metrics.json\n"
    )
    task_dir = _write_task(tmp_path, [_decision("mem-applied", "applied", [_application()])], review=review)
    memory, calls = _memory_bin(tmp_path)
    review_path = task_dir / "context" / "reviewer-response.txt"

    first = _run(task_dir, memory, "--event", "validated", "--review-response", str(review_path))
    second = _run(task_dir, memory, "--event", "validated", "--review-response", str(review_path))

    assert first.returncode == 0
    assert second.returncode == 0
    requests = _requests(calls)
    assert len(requests) == 1
    assert requests[0]["event"] == "validated"


def test_event_id_is_deterministic_and_dedupes_duplicate_sends(tmp_path: Path):
    task_dir = _write_task(tmp_path, [_decision("mem-applied", "applied", [_application()])])
    memory, calls = _memory_bin(tmp_path)

    first = _run(task_dir, memory, "--event", "applied")
    disabled = _run(task_dir, memory, "--event", "applied", feedback="0")
    missing_review = _run(task_dir, memory, "--event", "validated")
    second = _run(task_dir, memory, "--event", "applied")

    assert first.returncode == 0
    assert json.loads(disabled.stdout)["status"] == "disabled"
    assert json.loads(missing_review.stdout)["status"] == "review_not_approved"
    assert second.returncode == 0
    requests = _requests(calls)
    assert len(requests) == 1
    report = json.loads((task_dir / "context" / "memory-feedback.json").read_text(encoding="utf-8"))
    assert report["sent_events"][0]["event_id"] == requests[0]["event_id"]


def test_feedback_timeout_or_error_records_outbox_and_preserves_task_result(tmp_path: Path):
    task_dir = _write_task(tmp_path, [_decision("mem-applied", "applied", [_application()])])
    (task_dir / "result.md").write_text("STATUS: completed\n", encoding="utf-8")
    memory, _calls = _memory_bin(tmp_path, status="timeout", rc=0)

    result = _run(task_dir, memory, "--event", "applied")

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["status"] == "feedback_failed"
    assert (task_dir / "context" / "memory-feedback-outbox.jsonl").is_file()
    assert (task_dir / "result.md").read_text(encoding="utf-8") == "STATUS: completed\n"


def test_feedback_provider_error_exit_records_outbox(tmp_path: Path):
    task_dir = _write_task(tmp_path, [_decision("mem-applied", "applied", [_application()])])
    memory, _calls = _memory_bin(tmp_path, status="error", rc=7)

    result = _run(task_dir, memory, "--event", "applied")

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["status"] == "feedback_failed"
    outbox = (task_dir / "context" / "memory-feedback-outbox.jsonl").read_text(encoding="utf-8")
    assert "mem-applied" in outbox


@pytest.mark.parametrize("bad_reply", [None, "", "null", '{"status":"error"}'])
def test_feedback_retries_without_acknowledgement_using_the_same_id(tmp_path: Path, bad_reply):
    task_dir = _write_task(tmp_path, [_decision("mem-applied", "applied", [_application()])])
    memory = tmp_path / "memory"
    if bad_reply is not None:
        memory.write_text(f"#!/usr/bin/env bash\ncat <<'REPLY'\n{bad_reply}\nREPLY\n", encoding="utf-8")
        memory.chmod(0o755)

    failed = _run(task_dir, memory, "--event", "applied")

    assert failed.returncode == 0, failed.stderr
    report = json.loads(failed.stdout)
    assert report["status"] == "feedback_failed"
    outbox = task_dir / "context" / "memory-feedback-outbox.jsonl"
    pending = json.loads(outbox.read_text(encoding="utf-8"))["request"]

    memory, calls = _memory_bin(tmp_path)
    retry = _run(task_dir, memory, "--event", "applied")
    again = _run(task_dir, memory, "--event", "applied")

    assert json.loads(retry.stdout)["status"] == "sent"
    assert json.loads(again.stdout)["status"] == "already_sent"
    assert _requests(calls) == [pending]


def test_feedback_timeout_is_a_failed_delivery(tmp_path: Path, monkeypatch):
    spec = importlib.util.spec_from_file_location("memory_feedback_timeout", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    def timeout(args, *, timeout, **kwargs):
        assert timeout == 30
        raise subprocess.TimeoutExpired(args, timeout)

    monkeypatch.setattr(module.subprocess, "run", timeout)

    assert module.send_feedback(tmp_path / "memory", {"event_id": "single-delivery"}) == (False, {"status": "timeout"})


def test_legacy_empty_acknowledgement_is_retried(tmp_path: Path):
    task_dir = _write_task(tmp_path, [_decision("mem-applied", "applied", [_application()])])
    memory, calls = _memory_bin(tmp_path, status="error", rc=7)
    first = _run(task_dir, memory, "--event", "applied")
    failed, = json.loads(first.stdout)["failed_events"]
    report_path = task_dir / "context" / "memory-feedback.json"
    report_path.write_text(json.dumps({"sent_events": [{**failed, "provider_response": {"exit_code": 0}}]}))

    _memory_bin(tmp_path)
    retry = _run(task_dir, memory, "--event", "applied")

    assert json.loads(retry.stdout)["status"] == "sent"
    previous, repeated = _requests(calls)
    assert previous == repeated
