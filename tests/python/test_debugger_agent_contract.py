"""Contract tests for the provider-neutral debugger system agent."""

from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
ROUTING_PATH = REPO_ROOT / "core" / "rules" / "agent-routing.md"
DEBUGGER_PATH = REPO_ROOT / "core" / "agents" / "debugger.md"
SYSTEMATIC_SKILL_PATH = REPO_ROOT / "core" / "agents" / "skills" / "systematic-debugging.md"
MANIFEST_PATH = REPO_ROOT / "core" / "policies" / "agent-capabilities.json"
RUNTIME_PATH = REPO_ROOT / "core" / "scripts" / "crew-runtime.py"
SCRIPTS_DIR = REPO_ROOT / "core" / "scripts"

if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


crew_runtime = _load_module(RUNTIME_PATH, "crew_runtime_debugger_contract")


def _table_rows(text: str, header_fragment: str) -> list[str]:
    rows: list[str] = []
    in_section = False
    section_level = 0
    for line in text.splitlines():
        heading_match = re.match(r"^(#{2,})\s+", line)
        if heading_match and re.search(re.escape(header_fragment), line, re.IGNORECASE):
            in_section = True
            section_level = len(heading_match.group(1))
            continue
        if in_section and heading_match and len(heading_match.group(1)) <= section_level:
            break
        if in_section and line.startswith("|"):
            rows.append(line)
    return rows


def test_debugger_agent_file_declares_read_only_diagnostic_contract() -> None:
    text = DEBUGGER_PATH.read_text(encoding="utf-8")
    lowered = text.lower()

    assert "name: debugger" in text
    assert "read-only" in lowered
    assert "must not edit" in lowered
    assert "temporary debugging code" in lowered
    assert "deploy" in lowered
    assert "TASK_DIR" in text
    assert "context/debug" in text
    assert "git diff" in text
    assert "git log" in text
    assert "static analysis" in lowered


def test_debugger_agent_records_structured_debug_evidence_and_memory_capture_status() -> None:
    text = DEBUGGER_PATH.read_text(encoding="utf-8")

    for path in (
        "context/debug/reproduction.md",
        "context/debug/evidence.json",
        "context/debug/hypotheses.md",
        "context/debug/root-cause.md",
        "context/debug/memory-capture.json",
        "context/debug/report.md",
    ):
        assert path in text

    assert "AGENT_CREW_HOME" in text
    assert "/bin/memory" in text
    assert "--layer project" in text
    assert "capture_id" in text
    assert "backend_unavailable" in text
    assert "timeout" in text
    assert "must not claim" in text.lower()


def test_systematic_debugging_skill_covers_agent_crew_debugger_constraints() -> None:
    text = SYSTEMATIC_SKILL_PATH.read_text(encoding="utf-8")
    lowered = text.lower()

    assert "debugger" in lowered
    assert "context/debug" in text
    assert "read-only" in lowered
    assert "verified root cause" in lowered
    assert "memory" in lowered
    assert "raw logs" in lowered
    assert "hypotheses" in lowered
    assert "backend" in lowered
    assert "timeout" in lowered


def test_debugger_is_registered_as_safe_direct_readonly_agent() -> None:
    routing = ROUTING_PATH.read_text(encoding="utf-8")
    rows = _table_rows(routing, "Agent Registry")
    debugger_rows = [row for row in rows if row.lstrip("| ").lower().startswith("debugger")]

    assert debugger_rows, "debugger registry row not found"
    cells = [cell.strip() for cell in debugger_rows[0].strip().strip("|").split("|")]
    assert cells[0] == "debugger"
    assert cells[3] == "yes"
    assert "read-only" in cells[1].lower()


def test_debugger_auto_route_is_narrower_than_analyst() -> None:
    agents = {
        "analyst": {"safe": "yes"},
        "debugger": {"safe": "yes"},
    }

    debugger_tasks = (
        "diagnose this stack trace from the failing test",
        "build failure: exception during integration test",
        "debug flaky behavior in the parser",
        "investigate performance regression in startup",
    )
    for task in debugger_tasks:
        agent_name, reason = crew_runtime.auto_route_agent(task, agents)
        assert agent_name == "debugger", f"{task!r} routed to {agent_name!r}: {reason}"

    analyst_tasks = (
        "explain how routing works",
        "investigate the architecture boundary",
        "audit the memory contract",
        "analyze the supervisor recovery flow",
    )
    for task in analyst_tasks:
        agent_name, reason = crew_runtime.auto_route_agent(task, agents)
        assert agent_name == "analyst", f"{task!r} routed to {agent_name!r}: {reason}"


def test_debugger_capability_manifest_is_read_only_with_test_and_memory_bounds() -> None:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    debugger = manifest["agents"]["debugger"]

    assert debugger["role"] == "readonly"
    assert debugger["may_implement"] is False
    assert debugger["may_modify_production_state"] is False
    assert debugger["may_mutate_workflow_state"] is False
    assert debugger["may_execute_destructive"] is False
    assert "read_file" in debugger["allowed_capabilities"]
    assert "run_tests" in debugger["allowed_capabilities"]
    assert "memory_write_project_verified_root_cause" in debugger["allowed_capabilities"]
    assert "edit_file" in debugger["denied_capabilities"]
    assert "destructive_command" in debugger["denied_capabilities"]
    assert "external_state_write" in debugger["denied_capabilities"]


def test_runtime_agent_routing_uses_declarative_table_for_debugger() -> None:
    runtime_text = RUNTIME_PATH.read_text(encoding="utf-8")
    function_body = runtime_text.split("def auto_route_agent", 1)[1].split("\ndef command_run", 1)[0]

    assert '"debugger"' not in function_body
    assert "read_agent_routing_rules" in function_body


def test_debugger_hypothesis_phase_requires_predictions_before_discriminating_evidence() -> None:
    text = DEBUGGER_PATH.read_text(encoding="utf-8")
    phase = text.split("### Phase 3 — Hypothesis", 1)[1].split("### Phase 4", 1)[0]
    phase = " ".join(phase.lower().split())

    assert "before retrieving evidence that distinguishes the hypotheses" in phase
    assert "expected observations" in phase and "observations that would rule it out" in phase
    assert "same criteria" in phase and "user's proposed cause" in phase
    assert "compare competing hypotheses against the same observations" in phase
    assert "file and line" in phase and "trace id" in phase


def test_debugger_closeout_phase_requires_sample_proof_and_one_decisive_next_check() -> None:
    text = DEBUGGER_PATH.read_text(encoding="utf-8")
    phase = text.split("### Phase 4 — Diagnostic Close-Out", 1)[1].split("## Project Memory Capture", 1)[0]
    phase = " ".join(phase.lower().split())

    assert "supported, ruled out, or undetermined" in phase
    assert "only when evidence links the cause to the failure in this sample" in phase
    assert "lookup fails" in phase and "leave it undetermined" in phase
    assert "confirm collection coverage" in phase
    assert "one next check" in phase and "lookup key" in phase and "distinguishes the hypotheses" in phase


def test_debugger_closeout_traces_what_extended_a_lock_hold() -> None:
    text = DEBUGGER_PATH.read_text(encoding="utf-8")
    phase = text.split("### Phase 4 — Diagnostic Close-Out", 1)[1].split("## Project Memory Capture", 1)[0]
    phase = " ".join(phase.lower().split())

    assert "blocker identity" in phase and "activity that extended the lock hold" in phase
    assert "acquisition through release" in phase
    assert all(interval in phase for interval in ("query", "write", "commit"))
    assert "compare their observed timestamps or durations" in phase
    assert "same key and time window" in phase
    assert "separate the competing explanations" in phase
