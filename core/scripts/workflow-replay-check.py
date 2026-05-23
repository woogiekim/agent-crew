#!/usr/bin/env python3
"""Replay golden workflow fixtures against deterministic local validators.

Inputs:
  --fixture PATH       replay fixture; defaults to core/evaluations/workflow-replay.json
  --project-root PATH  repository checkout; defaults to this script's repo root

Outputs:
  text or JSON report containing tool-flow, state-transition, and failure-code
  comparisons for each replay case.

Exit codes:
  0 - every replay case matched the golden fixture
  1 - one or more replay comparisons failed
  2 - fixture or arguments are invalid

Example:
  python3 core/scripts/workflow-replay-check.py --format json
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


ALLOWED_TRANSITIONS = {
    "phase_0": {"phase_1a", "phase_1bc", "phase_2", "blocked"},
    "phase_1a": {"phase_1bc", "blocked"},
    "phase_1bc": {"phase_1c_bis", "phase_1d", "phase_2", "blocked"},
    "phase_1c_bis": {"phase_1d", "phase_2", "blocked"},
    "phase_1d": {"phase_1_5", "phase_2", "blocked"},
    "phase_1_5": {"phase_2", "blocked"},
    "phase_2": {"phase_2_5", "phase_3", "blocked"},
    "phase_2_5": {"phase_3", "blocked"},
    "phase_3": {"completed", "blocked"},
    "completed": set(),
    "blocked": set(),
}


def load_json(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return None, str(exc)
    if not isinstance(data, dict):
        return None, "fixture root must be an object"
    return data, None


def run_tool(command: list[str], *, cwd: Path, env: dict[str, str], stdin: str = "") -> dict[str, Any]:
    proc = subprocess.run(command, cwd=str(cwd), env=env, input=stdin, text=True, capture_output=True)
    payload: dict[str, Any] = {}
    if proc.stdout.strip():
        try:
            payload = json.loads(proc.stdout)
        except Exception:
            payload = {}
    return {
        "tool": Path(command[1]).name if len(command) > 1 else command[0],
        "command": command,
        "returncode": proc.returncode,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
        "payload": payload,
    }


def compare_list_exact(expected: list[str], actual: list[str]) -> bool:
    return sorted(expected) == sorted(actual)


def failure_codes(result: dict[str, Any]) -> list[str]:
    payload = result.get("payload") or {}
    failures = payload.get("failures") or []
    codes: list[str] = []
    if isinstance(failures, list):
        for item in failures:
            if isinstance(item, str):
                codes.append(item)
            elif isinstance(item, dict) and item.get("code"):
                codes.append(str(item["code"]))
    return codes


def write_replay_state(root: Path, case: dict[str, Any]) -> tuple[Path, Path]:
    case_id = str(case.get("id", "case"))
    task_id = "20260101-000001-0"
    session_id = "20260101-000001"
    state_dir = root / "state"
    task_dir = state_dir / "tasks" / task_id
    task_dir.mkdir(parents=True)

    task = str(case.get("task") or case_id)
    pipeline = dict(case.get("pipeline") or {})
    pipeline.setdefault("task", task)
    pipeline.setdefault("completed_stages", 0)
    (task_dir / "pipeline.json").write_text(json.dumps(pipeline, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    final_phase = str((case.get("expected") or {}).get("final_phase") or "completed")
    register = {
        "schema_version": 1,
        "task_id": task_id,
        "session_id": session_id,
        "task": task,
        "branch": f"agent-crew/{case_id}",
        "project_root": str(root),
        "task_dir": str(task_dir),
        "execution_mode": "single",
        "current_phase": final_phase,
        "approval_status": "not_required",
        "verification_status": "passed" if final_phase == "completed" else "failed",
        "pipeline_path": str(task_dir / "pipeline.json"),
        "progress_buffer_path": str(task_dir / "progress.buffer.jsonl"),
        "result_path": str(task_dir / "result.md"),
        "modified_files": [],
        "blocked_by": [] if final_phase == "completed" else ["workflow_replay_expected_block"],
        "host_bridge_status": "fake_completed",
    }
    (task_dir / "register.json").write_text(json.dumps(register, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    (state_dir / "session.json").write_text(json.dumps({
        "schema_version": 1,
        "session_id": session_id,
        "status": final_phase,
        "tasks": [
            {
                "task_id": task_id,
                "task_dir": str(task_dir),
                "branch": register["branch"],
                "task": task,
                "status": final_phase,
            }
        ],
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (state_dir / "capabilities.json").write_text(json.dumps({
        "schema_version": 1,
        "host": "replay",
        "task_tools": False,
        "agent_background": False,
        "monitor_tool": False,
        "cost_tracking": False,
        "hook_system": False,
        "interactive_question": False,
    }, indent=2) + "\n", encoding="utf-8")

    rows = []
    for index, row in enumerate(case.get("progress_events") or [], start=1):
        item = dict(row)
        item.setdefault("ts", f"2026-01-01T00:00:{index:02d}Z")
        item.setdefault("trace_id", f"{session_id}.{task_id}.{item.get('stage', 0)}.{item.get('attempt', 0)}")
        item.setdefault("task_id", task_id)
        item.setdefault("session_id", session_id)
        rows.append(item)
    (task_dir / "progress.buffer.jsonl").write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )
    (task_dir / "result.md").write_text(f"STATUS: {final_phase}\n", encoding="utf-8")
    return state_dir, task_dir


def transition_failures(transitions: list[str]) -> list[str]:
    failures: list[str] = []
    if not transitions:
        return ["missing_state_transitions"]
    for previous, current in zip(transitions, transitions[1:]):
        allowed = ALLOWED_TRANSITIONS.get(previous)
        if allowed is None:
            failures.append(f"unknown_state:{previous}")
            continue
        if current not in allowed:
            failures.append(f"invalid_transition:{previous}->{current}")
    final = transitions[-1]
    if final not in {"completed", "blocked"}:
        failures.append(f"non_terminal_final_state:{final}")
    return failures


def replay_case(case: dict[str, Any], repo_root: Path) -> dict[str, Any]:
    case_id = str(case.get("id", "unnamed"))
    expected = case.get("expected") or {}
    expected_tools = expected.get("tool_flow") or []
    failures: list[str] = []

    with tempfile.TemporaryDirectory(prefix=f"agent-crew-replay-{case_id}-") as temp:
        replay_root = Path(temp)
        state_dir, task_dir = write_replay_state(replay_root, case)
        pipeline_path = task_dir / "pipeline.json"
        env = os.environ.copy()
        env["AGENT_CREW_HOME"] = str(repo_root / "core")
        env["AGENT_CREW_STATE_DIR"] = str(state_dir)

        commands = {
            "validate-state-schema.py": [
                sys.executable,
                str(repo_root / "core" / "scripts" / "validate-state-schema.py"),
                "--state-dir",
                str(state_dir),
                "--task-dir",
                str(task_dir),
                "--format",
                "json",
            ],
            "pipeline-quality-plan-check.py": [
                sys.executable,
                str(repo_root / "core" / "scripts" / "pipeline-quality-plan-check.py"),
                "--pipeline",
                str(pipeline_path),
                "--task",
                str(case.get("task") or ""),
                "--format",
                "json",
            ],
            "pipeline-capability-check.py": [
                sys.executable,
                str(repo_root / "core" / "scripts" / "pipeline-capability-check.py"),
                "--pipeline",
                str(pipeline_path),
                "--manifest",
                str(repo_root / "core" / "policies" / "agent-capabilities.json"),
                "--agent-dir",
                str(repo_root / "core" / "agents"),
                "--format",
                "json",
            ],
            "auto-issue-reporter.py": [
                sys.executable,
                str(repo_root / "core" / "scripts" / "auto-issue-reporter.py"),
                "auto",
                "--format",
                "json",
            ],
        }

        tool_results: list[dict[str, Any]] = []
        for expected_tool in expected_tools:
            tool_name = str(expected_tool.get("tool"))
            command = commands.get(tool_name)
            if command is None:
                failures.append(f"unknown_expected_tool:{tool_name}")
                continue
            stdin = ""
            if tool_name == "auto-issue-reporter.py":
                payload = expected_tool.get("payload")
                if payload is None:
                    payload = case.get("auto_issue_payload")
                stdin = json.dumps(payload or {}, ensure_ascii=False)
                env["AGENT_CREW_AUTO_ISSUE_STATE_DIR"] = str(state_dir / "reports")
                env["AGENT_CREW_REPORT_PUBLISH"] = "none"
                env["AGENT_CREW_TASK_ID"] = "20260101-000001-0"
            result = run_tool(command, cwd=repo_root, env=env, stdin=stdin)
            codes = failure_codes(result)
            expected_rc = expected_tool.get("returncode")
            expected_failure_codes = [str(item) for item in expected_tool.get("failures", [])]
            expected_status = expected_tool.get("status")
            if expected_rc is not None and result["returncode"] != expected_rc:
                failures.append(f"{tool_name}:returncode:{result['returncode']}!=expected:{expected_rc}")
            if not compare_list_exact(expected_failure_codes, codes):
                failures.append(
                    f"{tool_name}:failure_codes:{sorted(codes)}!=expected:{sorted(expected_failure_codes)}"
                )
            if expected_status is not None and str(result["payload"].get("status")) != str(expected_status):
                failures.append(
                    f"{tool_name}:status:{result['payload'].get('status')}!=expected:{expected_status}"
                )
            tool_results.append({
                "tool": tool_name,
                "returncode": result["returncode"],
                "expected_returncode": expected_rc,
                "failure_codes": codes,
                "expected_failures": expected_failure_codes,
                "status": result["payload"].get("status"),
                "expected_status": expected_status,
            })

    transitions = [str(item) for item in case.get("state_transitions") or []]
    state_failures = transition_failures(transitions)
    failures.extend(state_failures)
    expected_final = str(expected.get("final_phase", ""))
    if expected_final and transitions and transitions[-1] != expected_final:
        failures.append(f"final_phase:{transitions[-1]}!=expected:{expected_final}")

    expected_passed = bool(expected.get("passed"))
    observed_workflow_passed = (
        bool(transitions)
        and transitions[-1] == "completed"
        and all(item["returncode"] == 0 for item in tool_results)
    )
    if observed_workflow_passed != expected_passed:
        failures.append(f"workflow_passed:{observed_workflow_passed}!=expected:{expected_passed}")

    return {
        "id": case_id,
        "passed": not failures,
        "expected_passed": expected_passed,
        "observed_workflow_passed": observed_workflow_passed,
        "tool_flow": tool_results,
        "state_transitions": transitions,
        "failures": failures,
    }


def evaluate(repo_root: Path, fixture_path: Path) -> dict[str, Any]:
    fixture, error = load_json(fixture_path)
    if fixture is None:
        return {
            "schema_version": 1,
            "fixture": str(fixture_path),
            "passed": False,
            "error_type": "invalid_fixture",
            "summary": {"cases": 0, "passed": 0, "failed": 1},
            "cases": [],
            "failures": [error or "fixture_parse_failed"],
        }
    cases_raw = fixture.get("cases")
    if fixture.get("schema_version") != 1 or not isinstance(cases_raw, list) or not cases_raw:
        return {
            "schema_version": 1,
            "fixture": str(fixture_path),
            "passed": False,
            "error_type": "invalid_fixture",
            "summary": {"cases": 0, "passed": 0, "failed": 1},
            "cases": [],
            "failures": ["fixture must have schema_version=1 and non-empty cases array"],
        }
    if any(not isinstance(case, dict) for case in cases_raw):
        return {
            "schema_version": 1,
            "fixture": str(fixture_path),
            "passed": False,
            "error_type": "invalid_fixture",
            "summary": {"cases": 0, "passed": 0, "failed": 1},
            "cases": [],
            "failures": ["fixture cases must be objects"],
        }

    cases = [replay_case(case, repo_root) for case in cases_raw]
    failed = [case for case in cases if not case["passed"]]
    return {
        "schema_version": 1,
        "fixture": str(fixture_path),
        "passed": not failed,
        "summary": {
            "cases": len(cases),
            "passed": len(cases) - len(failed),
            "failed": len(failed),
        },
        "cases": cases,
        "failures": [
            {"id": case["id"], "failures": case["failures"]}
            for case in failed
        ],
    }


def main() -> int:
    repo_root = Path(__file__).resolve().parent.parent.parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", default=str(repo_root))
    parser.add_argument("--fixture", default=str(repo_root / "core" / "evaluations" / "workflow-replay.json"))
    parser.add_argument("--format", choices=["json", "text"], default="text")
    args = parser.parse_args()

    root = Path(args.project_root).expanduser().resolve()
    result = evaluate(root, Path(args.fixture).expanduser().resolve())
    if args.format == "json":
        json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
        print()
    else:
        print(("PASS" if result["passed"] else "FAIL") + ": workflow replay check")
        summary = result["summary"]
        print(f"cases={summary['cases']} passed={summary['passed']} failed={summary['failed']}")
        for failure in result["failures"]:
            print(f"- {failure}")
    if result["passed"]:
        return 0
    if result.get("error_type") == "invalid_fixture":
        return 2
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
