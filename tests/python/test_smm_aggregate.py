# Spec: prd.md § "Input / Output Contract" — SMM single-view (issue #129 Finding #2)
"""Tests for core/scripts/smm-aggregate.py.

Derived purely from the PRD contract (TDD parallel partner — these tests do
NOT read the implementation). Targets:
  - read_handoff(task_dir) -> dict          (present vs absent)
  - build_smm(state_dir, task_dir) -> dict  (all-sources vs missing-file)
  - render_text(smm_list) -> str            (N>1 multi-task, absent handoff, empty)
  - main() / CLI                            (--format json/text, exit codes, read-only)

Exit code contract (matches telemetry-aggregate.py):
  0 — success (including zero tasks)
  3 — invalid args / unreadable state dir
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SMM = REPO_ROOT / "core" / "scripts" / "smm-aggregate.py"


def _load_module(path: Path, name: str):
    script_dir = str(path.parent)
    if script_dir in sys.path:
        sys.path.remove(script_dir)
    sys.path.insert(0, script_dir)
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


smm = _load_module(SMM, "smm_aggregate")


# --------------------------------------------------------------------------- #
# Fixture builders                                                            #
# --------------------------------------------------------------------------- #

def _make_task(state_dir: Path, task_id: str, *,
               with_pipeline: bool = True,
               with_register: bool = True,
               with_handoff: bool = True,
               with_buffer: bool = True,
               with_log: bool = True,
               current_phase: str = "phase_2",
               completed_stages: int = 1,
               branch: str = "feat/example") -> Path:
    """Create a task directory with the requested subset of the five sources."""
    task_dir = state_dir / "tasks" / task_id
    (task_dir / "context").mkdir(parents=True, exist_ok=True)

    if with_pipeline:
        (task_dir / "pipeline.json").write_text(json.dumps({
            "task": "example task description",
            "stages": [
                {"agents": ["backend"], "tdd_parallel": True},
                ["reviewer"],
            ],
            "completed_stages": completed_stages,
        }), encoding="utf-8")

    if with_register:
        session_id = task_id.rsplit("-", 1)[0]
        (task_dir / "register.json").write_text(json.dumps({
            "schema_version": 1,
            "task_id": task_id,
            "session_id": session_id,
            "task": "example task description",
            "branch": branch,
            "project_root": "/tmp/proj",
            "task_dir": str(task_dir),
            "execution_mode": "single",
            "current_phase": current_phase,
            "approval_status": "approved",
            "verification_status": "running",
            "modified_files": ["core/scripts/smm-aggregate.py"],
            "blocked_by": [],
        }), encoding="utf-8")

    if with_handoff:
        (task_dir / "handoff.md").write_text(
            "# Handoff — example\n\n"
            "## Summarized requirements\n\n"
            "Build the thing.\n\n"
            "## Key technical decisions\n\n"
            "- decision one\n",
            encoding="utf-8",
        )

    if with_buffer:
        rows = [
            {"ts": "2026-05-29T09:38:58Z", "trace_id": "t.0", "task_id": task_id,
             "session_id": task_id.rsplit("-", 1)[0], "event": "STARTED",
             "stage": 0, "agent": "", "attempt": 0, "status": "started",
             "detail": "example task description", "files": []},
            {"ts": "2026-05-29T09:39:00Z", "trace_id": "t.1", "task_id": task_id,
             "session_id": task_id.rsplit("-", 1)[0], "event": "STAGE",
             "stage": 1, "agent": "backend", "attempt": 1, "status": "in_progress",
             "detail": "1/2 — backend", "files": []},
        ]
        with (task_dir / "progress.buffer.jsonl").open("w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r) + "\n")

    if with_log:
        (task_dir / "progress.log").write_text(
            "2026-05-29T09:38:58Z | STARTED | example task description\n"
            "2026-05-29T09:39:00Z | STAGE | 1/2 — backend\n",
            encoding="utf-8",
        )

    return task_dir


def _snapshot_tree(root: Path) -> dict:
    """Map every file under root to (size, sha256) for byte-identity checks."""
    snap = {}
    for p in sorted(root.rglob("*")):
        if p.is_file():
            data = p.read_bytes()
            snap[str(p.relative_to(root))] = (len(data), hashlib.sha256(data).hexdigest())
    return snap


# --------------------------------------------------------------------------- #
# read_handoff                                                                #
# --------------------------------------------------------------------------- #

def test_read_handoff_present(tmp_path: Path):
    task_dir = _make_task(tmp_path / "state", "20260529-100000-0")
    sut = smm.read_handoff(task_dir)

    assert sut["present"] is True
    assert sut["lines"] > 0
    # Heading text only — no leading '#'
    assert "Handoff — example" in sut["headings"]
    assert "Summarized requirements" in sut["headings"]
    assert "Key technical decisions" in sut["headings"]
    assert all(not h.startswith("#") for h in sut["headings"])
    assert "Build the thing." in sut["excerpt"]


def test_read_handoff_absent(tmp_path: Path):
    task_dir = _make_task(tmp_path / "state", "20260529-100001-0",
                          with_handoff=False)
    sut = smm.read_handoff(task_dir)

    assert sut == {"present": False, "lines": 0, "headings": [], "excerpt": ""}


def test_read_handoff_excerpt_is_bounded(tmp_path: Path):
    task_dir = (tmp_path / "state" / "tasks" / "20260529-100002-0")
    task_dir.mkdir(parents=True)
    body = "\n".join(f"line {i}" for i in range(200))
    (task_dir / "handoff.md").write_text(body, encoding="utf-8")

    sut = smm.read_handoff(task_dir)

    assert sut["present"] is True
    assert sut["lines"] == 200
    # Excerpt bounded to first 40 lines
    assert sut["excerpt"].count("\n") <= 40
    assert "line 0" in sut["excerpt"]
    assert "line 199" not in sut["excerpt"]


# --------------------------------------------------------------------------- #
# build_smm — all sources present                                            #
# --------------------------------------------------------------------------- #

def test_build_smm_all_sources(tmp_path: Path):
    state_dir = tmp_path / "state"
    task_dir = _make_task(state_dir, "20260529-100100-0",
                          branch="feat/smm", current_phase="phase_2",
                          completed_stages=1)
    sut = smm.build_smm(state_dir, task_dir)

    assert sut["task_id"] == "20260529-100100-0"
    assert sut["task"] == "example task description"
    assert sut["branch"] == "feat/smm"
    assert sut["status"] in ("completed", "blocked", "cancelled", "running", "unknown")
    assert sut["current_phase"] == "phase_2"
    assert sut["approval_status"] == "approved"
    assert sut["verification_status"] == "running"
    assert sut["stages_total"] == 2
    assert sut["stages_completed"] == 1
    assert sut["modified_files"] == ["core/scripts/smm-aggregate.py"]
    assert sut["blocked_by"] == []

    # stage_list: one per stage with index + agents + marker
    assert len(sut["stage_list"]) == 2
    first, second = sut["stage_list"]
    assert first["index"] == 1
    assert first["agents"] == ["backend"]
    assert first["marker"] == "done"          # completed_stages == 1
    assert second["index"] == 2
    assert second["agents"] == ["reviewer"]
    assert second["marker"] == "current"      # next stage to run

    # recent_events: up to 5 from the buffer
    assert isinstance(sut["recent_events"], list)
    assert len(sut["recent_events"]) <= 5
    assert all({"ts", "event", "detail"} <= set(e.keys()) for e in sut["recent_events"])

    # handoff dict embedded
    assert sut["handoff"]["present"] is True

    # sources_present: all five True
    assert sut["sources_present"] == {
        "pipeline": True, "progress_log": True, "progress_buffer": True,
        "register": True, "handoff": True,
    }


def test_build_smm_includes_orchestration_summary(tmp_path: Path):
    state_dir = tmp_path / "state"
    task_dir = _make_task(state_dir, "20260529-100102-0", completed_stages=0)
    context_dir = task_dir / "context"

    (task_dir / "pipeline.json").write_text(json.dumps({
        "task": "example task description",
        "stages": [
            {
                "agents": ["backend"],
                "tdd_parallel": True,
                "parallelizable_units": [
                    {"id": "orders", "files": ["src/orders/**"], "brief": "orders"},
                    {"id": "carts", "files": ["src/carts/**"], "brief": "carts"},
                ],
            },
            ["reviewer"],
        ],
        "completed_stages": 0,
    }), encoding="utf-8")
    (context_dir / "memory-retrieval.json").write_text(json.dumps({
        "status": "ok",
        "results": [
            {"memory_id": "mem-1", "layer": "project"},
            {"memory_id": "mem-2", "layer": "session"},
        ],
    }), encoding="utf-8")
    (context_dir / "memory-usage.json").write_text(json.dumps({
        "schema_version": "agent-crew.memory-usage.v2",
        "decisions": [
            {
                "memory_id": "mem-1",
                "disposition": "applied",
                "applications": [
                    {
                        "artifact": "pipeline.json",
                        "locator_type": "json_pointer",
                        "locator": "/stages/0/tdd_parallel",
                        "effect": "set_true",
                    }
                ],
            },
            {"memory_id": "mem-2", "disposition": "ignored", "applications": []},
        ],
    }), encoding="utf-8")
    (context_dir / "memory-feedback.json").write_text(json.dumps({
        "sent_events": [{"event": "applied", "memory_id": "mem-1"}],
        "failed_events": [],
    }), encoding="utf-8")
    (context_dir / "evolution-report.json").write_text(json.dumps({
        "observed_patterns": [{"kind": "retry"}],
        "asset_candidates": [],
    }), encoding="utf-8")
    proposals = state_dir / "learning-candidates" / "proposals.json"
    proposals.parent.mkdir(parents=True)
    proposals.write_text(json.dumps({
        "schema_version": 1,
        "proposals": [{
            "candidate_id": "review-fix-verifier-2x",
            "proposal_type": "create_agent",
            "status": "approval_required",
            "asset_name": "review-fix-verifier",
            "occurrence_count": 2,
        }],
    }), encoding="utf-8")
    (context_dir / "evolution-proposals-summary.txt").write_text(
        "SELF_EVOLUTION_PROPOSALS: 1 pending\n",
        encoding="utf-8",
    )
    (task_dir / "delegation.jsonl").write_text(
        json.dumps({"agent_role": "backend", "unit_id": "orders"}) + "\n",
        encoding="utf-8",
    )
    with (task_dir / "progress.buffer.jsonl").open("a", encoding="utf-8") as f:
        for event in ("STAGE_FANOUT_STARTED", "STAGE_FANOUT_UNIT_DONE",
                      "STAGE_FANOUT_DONE"):
            f.write(json.dumps({
                "ts": "2026-05-29T09:40:00Z",
                "trace_id": f"t.{event}",
                "task_id": "20260529-100102-0",
                "session_id": "20260529-100102",
                "event": event,
                "stage": 1,
                "agent": "backend",
                "attempt": 1,
                "status": "completed",
                "detail": event,
                "files": [],
            }) + "\n")

    sut = smm.build_smm(state_dir, task_dir)
    orchestration = sut["orchestration"]

    assert orchestration["memory"] == {
        "retrieval_status": "ok",
        "retrieved": 2,
        "applied": 1,
        "ignored": 1,
        "feedback_sent": 1,
        "feedback_failed": 0,
        "artifacts": [
            "context/memory-retrieval.json",
            "context/memory-usage.json",
            "context/memory-feedback.json",
        ],
        "next_action": "memory_context_available",
    }
    assert orchestration["dag"]["parallel_units"] == 2
    assert orchestration["dag"]["current_stage_agents"] == ["backend"]
    assert orchestration["dag"]["tdd_parallel_stages"] == 1
    assert orchestration["dag"]["artifacts"] == ["pipeline.json"]
    assert orchestration["dag"]["next_action"] == "continue_current_stage"
    assert orchestration["inbox"]["delegations"] == 1
    assert orchestration["inbox"]["fanout_events"] == 3
    assert orchestration["inbox"]["artifacts"] == [
        "progress.buffer.jsonl",
        "delegation.jsonl",
    ]
    assert orchestration["inbox"]["next_action"] == "review_delegations"
    assert orchestration["evolution"] == {
        "report_present": True,
        "observed_patterns": 1,
        "proposal": "approval_required",
        "artifacts": [
            "context/evolution-report.json",
            "context/evolution-proposals-summary.txt",
            "learning-candidates/proposals.json",
        ],
        "next_action": "review_evolution_proposal",
    }


def test_build_smm_orchestration_distinguishes_memory_next_actions(tmp_path: Path):
    state_dir = tmp_path / "state"

    no_results = _make_task(state_dir, "20260529-100103-0")
    (no_results / "context" / "memory-retrieval.json").write_text(
        json.dumps({"status": "ok", "results": []}),
        encoding="utf-8",
    )

    unavailable = _make_task(state_dir, "20260529-100103-1")
    (unavailable / "context" / "memory-retrieval.json").write_text(
        json.dumps({"status": "unavailable", "results": []}),
        encoding="utf-8",
    )

    disabled = _make_task(state_dir, "20260529-100103-2")
    (disabled / "context" / "memory-retrieval.json").write_text(
        json.dumps({"status": "disabled", "results": []}),
        encoding="utf-8",
    )

    invalid = _make_task(state_dir, "20260529-100103-3")
    (invalid / "context" / "memory-retrieval.json").write_text(
        "{broken",
        encoding="utf-8",
    )

    invalid_usage = _make_task(state_dir, "20260529-100103-4")
    (invalid_usage / "context" / "memory-retrieval.json").write_text(
        json.dumps({
            "status": "ok",
            "results": [{"memory_id": "mem-1"}],
        }),
        encoding="utf-8",
    )
    (invalid_usage / "context" / "memory-usage.json").write_text(
        "{broken",
        encoding="utf-8",
    )

    assert smm.build_smm(state_dir, no_results)["orchestration"]["memory"][
        "next_action"
    ] == "no_memory_results"
    assert smm.build_smm(state_dir, unavailable)["orchestration"]["memory"][
        "next_action"
    ] == "continue_without_memory"
    assert smm.build_smm(state_dir, disabled)["orchestration"]["memory"][
        "next_action"
    ] == "memory_disabled"
    assert smm.build_smm(state_dir, invalid)["orchestration"]["memory"][
        "next_action"
    ] == "inspect_memory_retrieval"
    assert smm.build_smm(state_dir, invalid_usage)["orchestration"]["memory"][
        "next_action"
    ] == "inspect_memory_usage"


def test_build_smm_orchestration_distinguishes_dag_next_actions(tmp_path: Path):
    state_dir = tmp_path / "state"
    missing = _make_task(
        state_dir,
        "20260529-100104-0",
        with_pipeline=False,
    )
    complete = _make_task(
        state_dir,
        "20260529-100104-1",
        completed_stages=2,
    )

    assert smm.build_smm(state_dir, missing)["orchestration"]["dag"][
        "next_action"
    ] == "inspect_pipeline"
    assert smm.build_smm(state_dir, complete)["orchestration"]["dag"][
        "next_action"
    ] == "pipeline_complete"


def test_build_smm_stage_markers_pending(tmp_path: Path):
    state_dir = tmp_path / "state"
    task_dir = _make_task(state_dir, "20260529-100101-0", completed_stages=0)
    sut = smm.build_smm(state_dir, task_dir)

    markers = [s["marker"] for s in sut["stage_list"]]
    assert markers == ["current", "pending"]


# --------------------------------------------------------------------------- #
# build_smm — missing-file degradation                                       #
# --------------------------------------------------------------------------- #

def test_build_smm_missing_all_optional_sources(tmp_path: Path):
    state_dir = tmp_path / "state"
    # Only the task dir exists — NO pipeline.json / handoff.md / register.json /
    # buffer / log.
    task_dir = _make_task(state_dir, "20260529-100200-0",
                          with_pipeline=False, with_register=False,
                          with_handoff=False, with_buffer=False,
                          with_log=False)

    sut = smm.build_smm(state_dir, task_dir)  # MUST NOT raise

    assert sut["task_id"] == "20260529-100200-0"
    assert sut["branch"] == ""
    assert sut["current_phase"] == ""
    assert sut["approval_status"] == "not_required"
    assert sut["verification_status"] == "not_started"
    assert sut["stages_total"] == 0
    assert sut["stages_completed"] == 0
    assert sut["stage_list"] == []
    assert sut["modified_files"] == []
    assert sut["blocked_by"] == []
    assert sut["recent_events"] == []
    assert sut["handoff"] == {"present": False, "lines": 0,
                              "headings": [], "excerpt": ""}
    assert sut["sources_present"] == {
        "pipeline": False, "progress_log": False, "progress_buffer": False,
        "register": False, "handoff": False,
    }


def test_build_smm_malformed_sources_do_not_raise(tmp_path: Path):
    state_dir = tmp_path / "state"
    task_dir = state_dir / "tasks" / "20260529-100201-0"
    (task_dir / "context").mkdir(parents=True)
    (task_dir / "pipeline.json").write_text("{ not valid json", encoding="utf-8")
    (task_dir / "register.json").write_text("also broken", encoding="utf-8")
    (task_dir / "progress.buffer.jsonl").write_text(
        "not json\n{\"ts\":\"x\",\"event\":\"STARTED\",\"detail\":\"ok\"}\n",
        encoding="utf-8")

    sut = smm.build_smm(state_dir, task_dir)  # MUST NOT raise

    assert sut["task_id"] == "20260529-100201-0"
    assert sut["stages_total"] == 0
    assert sut["stages_completed"] == 0


# --------------------------------------------------------------------------- #
# render_text                                                                 #
# --------------------------------------------------------------------------- #

def test_render_text_multi_task_session_header_and_blocks(tmp_path: Path):
    state_dir = tmp_path / "state"
    td1 = _make_task(state_dir, "20260529-100300-0", branch="feat/a")
    td2 = _make_task(state_dir, "20260529-100300-1", branch="feat/b")
    smm_list = [smm.build_smm(state_dir, td1), smm.build_smm(state_dir, td2)]

    out = smm.render_text(smm_list)

    # Session header with the literal substring "tasks" and the count
    assert "tasks" in out
    assert "2" in out
    # Each task_id present, in its own block
    assert "20260529-100300-0" in out
    assert "20260529-100300-1" in out
    # Each block has Status / Phase / Handoff lines and marker-style stage list
    assert "Status" in out
    assert "Phase" in out
    assert "Handoff" in out
    assert ("[x]" in out or "[>]" in out or "[ ]" in out)


def test_render_text_includes_orchestration_summary(tmp_path: Path):
    state_dir = tmp_path / "state"
    td = _make_task(state_dir, "20260529-100302-0")
    (td / "context" / "memory-retrieval.json").write_text(
        json.dumps({"status": "no_results", "results": []}),
        encoding="utf-8",
    )
    (td / "context" / "evolution-report.json").write_text(
        json.dumps({"observed_patterns": [{"kind": "retry"}]}),
        encoding="utf-8",
    )
    out = smm.render_text([smm.build_smm(state_dir, td)])

    assert "Orchestration:" in out
    assert "Memory:" in out
    assert "DAG:" in out
    assert "Inbox:" in out
    assert "Evolution:" in out
    assert "artifacts=" in out
    assert "next=" in out


def test_render_text_includes_actionable_evolution_next_action(tmp_path: Path):
    state_dir = tmp_path / "state"
    td = _make_task(state_dir, "20260529-100303-0")
    (td / "context" / "evolution-report.json").write_text(
        json.dumps({
            "observed_patterns": [{"kind": "retry"}],
            "asset_candidates": [],
        }),
        encoding="utf-8",
    )
    proposals = state_dir / "learning-candidates" / "proposals.json"
    proposals.parent.mkdir(parents=True)
    proposals.write_text(
        json.dumps({
            "schema_version": 1,
            "proposals": [{
                "candidate_id": "review-fix-verifier-2x",
                "proposal_type": "create_agent",
                "status": "approval_required",
                "asset_name": "review-fix-verifier",
                "occurrence_count": 2,
            }],
        }),
        encoding="utf-8",
    )
    (td / "context" / "evolution-proposals-summary.txt").write_text(
        "SELF_EVOLUTION_PROPOSALS: 1 pending\n",
        encoding="utf-8",
    )
    out = smm.render_text([smm.build_smm(state_dir, td)])

    assert "next=review_evolution_proposal" in out
    assert "context/evolution-proposals-summary.txt" in out
    assert "learning-candidates/proposals.json" in out


def test_render_text_absent_handoff_token(tmp_path: Path):
    state_dir = tmp_path / "state"
    td = _make_task(state_dir, "20260529-100301-0", with_handoff=False)
    out = smm.render_text([smm.build_smm(state_dir, td)])

    assert "(handoff not produced yet)" in out


def test_render_text_empty_input(tmp_path: Path):
    out = smm.render_text([])
    assert "(no tasks matched)" in out


# --------------------------------------------------------------------------- #
# CLI                                                                         #
# --------------------------------------------------------------------------- #

def _run_cli(*args):
    return subprocess.run(
        [sys.executable, str(SMM), *args],
        capture_output=True, text=True,
    )


def test_cli_format_json_shape(tmp_path: Path):
    state_dir = tmp_path / "state"
    _make_task(state_dir, "20260529-100400-0")

    proc = _run_cli("--state-dir", str(state_dir),
                    "--task-id", "20260529-100400-0", "--format", "json")
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["state_dir"] == str(state_dir)
    assert isinstance(payload["tasks"], list)
    assert len(payload["tasks"]) == 1
    assert payload["tasks"][0]["task_id"] == "20260529-100400-0"
    # full SMM dict keys are present
    assert "sources_present" in payload["tasks"][0]
    assert "handoff" in payload["tasks"][0]


def test_cli_format_text(tmp_path: Path):
    state_dir = tmp_path / "state"
    _make_task(state_dir, "20260529-100401-0")

    proc = _run_cli("--state-dir", str(state_dir),
                    "--task-id", "20260529-100401-0", "--format", "text")
    assert proc.returncode == 0, proc.stderr
    assert "20260529-100401-0" in proc.stdout


def test_cli_exit_0_on_zero_tasks(tmp_path: Path):
    state_dir = tmp_path / "state"
    (state_dir / "tasks").mkdir(parents=True)

    proc = _run_cli("--state-dir", str(state_dir), "--format", "text")
    assert proc.returncode == 0, proc.stderr
    assert "(no tasks matched)" in proc.stdout


def test_cli_exit_3_on_unreadable_state_dir(tmp_path: Path):
    missing = tmp_path / "does-not-exist"
    proc = _run_cli("--state-dir", str(missing), "--format", "text")
    assert proc.returncode == 3


def test_cli_json_zero_tasks(tmp_path: Path):
    state_dir = tmp_path / "state"
    (state_dir / "tasks").mkdir(parents=True)
    proc = _run_cli("--state-dir", str(state_dir), "--format", "json")
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["tasks"] == []


# --------------------------------------------------------------------------- #
# Read-only invariant                                                         #
# --------------------------------------------------------------------------- #

def test_cli_is_read_only(tmp_path: Path):
    state_dir = tmp_path / "state"
    _make_task(state_dir, "20260529-100500-0")
    _make_task(state_dir, "20260529-100500-1", with_handoff=False)

    before = _snapshot_tree(state_dir)

    proc = _run_cli("--state-dir", str(state_dir), "--recent", "10",
                    "--format", "json")
    assert proc.returncode == 0, proc.stderr

    after = _snapshot_tree(state_dir)
    assert before == after, "CLI mutated state files — read-only invariant broken"


def test_build_smm_is_read_only(tmp_path: Path):
    state_dir = tmp_path / "state"
    task_dir = _make_task(state_dir, "20260529-100501-0")

    before = _snapshot_tree(state_dir)
    smm.build_smm(state_dir, task_dir)
    after = _snapshot_tree(state_dir)

    assert before == after
