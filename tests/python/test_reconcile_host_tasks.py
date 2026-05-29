"""Tests for ``core/scripts/reconcile-host-tasks.py``.

Issue #128 — when a P4 background fan-out task reaches a terminal state,
the helper script plans which host TaskList rows must transition to a
terminal status. The script itself is a pure planner: it never calls into
the host. Three call sites (supervisor Phase 3 sweep,
``crew:status --collect``, plain ``crew:status``) consume the JSON plan
and issue TaskGet/TaskUpdate at the call site, gated on the ``task_tools``
capability flag.

These tests cover:

- terminal-status detection for completed / blocked / CANCELLED
- legacy ``**Status:**`` markdown form (issue #31 compat)
- malformed / missing inputs (helper must never crash)
- capability-gate no-op semantics by inspecting the plan size, not via runtime
- custom-agent names in host_task_ids
- exit-code contract (0 valid plan, 1 unparseable, 2 unknown status)
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPT = REPO_ROOT / "core" / "scripts" / "reconcile-host-tasks.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("reconcile_host_tasks", SCRIPT)
    assert spec and spec.loader, f"could not load {SCRIPT}"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def reconcile():
    """Import the helper as a module so we can test pure functions directly."""
    return _load_module()


def _seed_task_dir(
    base: Path,
    *,
    status: str | None = "completed",
    legacy_status_form: bool = False,
    pipeline_host_task_ids=None,
    pipeline_corrupt: bool = False,
    pipeline_missing: bool = False,
    parent_host_task_id: str | None = "host-parent-1",
) -> Path:
    """Build a hermetic task-dir fixture mirroring real state layout."""
    base.mkdir(parents=True, exist_ok=True)
    (base / "context").mkdir(exist_ok=True)

    # result.md
    if status is not None:
        body = "# task\n\n"
        if legacy_status_form:
            body += f"**Status:** {status}\n"
        else:
            body += f"STATUS: {status}\n"
        (base / "result.md").write_text(body, encoding="utf-8")

    # pipeline.json
    if pipeline_missing:
        pass
    elif pipeline_corrupt:
        (base / "pipeline.json").write_text("{this is :: not json", encoding="utf-8")
    else:
        p = {"task": "demo", "stages": [], "completed_stages": 0}
        if pipeline_host_task_ids is not None:
            p["host_task_ids"] = pipeline_host_task_ids
        (base / "pipeline.json").write_text(json.dumps(p), encoding="utf-8")

    # host-task-id.txt
    if parent_host_task_id is not None:
        (base / "host-task-id.txt").write_text(parent_host_task_id + "\n", encoding="utf-8")

    return base


# ---------- terminal-status detection ----------

def test_helper_emits_completed_plan_for_terminal_result_md(reconcile, tmp_path: Path):
    """Given STATUS: completed + host_task_ids, every entry targets completed."""
    td = _seed_task_dir(
        tmp_path / "t",
        status="completed",
        pipeline_host_task_ids=[
            {"backend": "stage-1-backend"},
            {"reviewer": "stage-2-reviewer"},
        ],
    )
    plan = reconcile.build_plan(td)
    assert plan["terminal_status"] == "completed"
    assert plan["host_status"] == "completed"
    assert plan["parent_task_id"] == "host-parent-1"
    actions = plan["reconcile_plan"]
    # one parent + two stage entries
    assert len(actions) == 3
    parent = [a for a in actions if a["scope"] == "parent"]
    stages = [a for a in actions if a["scope"] == "stage"]
    assert len(parent) == 1 and parent[0]["target_status"] == "completed"
    assert {s["host_task_id"] for s in stages} == {"stage-1-backend", "stage-2-reviewer"}
    assert all(s["target_status"] == "completed" for s in stages)


def test_helper_emits_blocked_plan_for_blocked_result_md(reconcile, tmp_path: Path):
    """STATUS: blocked → every action target is blocked."""
    td = _seed_task_dir(
        tmp_path / "t",
        status="blocked",
        pipeline_host_task_ids=[{"backend": "s1"}, {"reviewer": "s2"}],
    )
    plan = reconcile.build_plan(td)
    assert plan["terminal_status"] == "blocked"
    assert plan["host_status"] == "blocked"
    assert all(a["target_status"] == "blocked" for a in plan["reconcile_plan"])


def test_helper_treats_cancelled_as_completed(reconcile, tmp_path: Path):
    """STATUS: CANCELLED → host_status=completed (matches supervisor Step 2b)."""
    td = _seed_task_dir(tmp_path / "t", status="CANCELLED",
                        pipeline_host_task_ids=[{"backend": "s1"}])
    plan = reconcile.build_plan(td)
    assert plan["terminal_status"] == "cancelled"
    assert plan["host_status"] == "completed"
    for a in plan["reconcile_plan"]:
        assert a["target_status"] == "completed"


# ---------- error contracts ----------

def test_helper_returns_rc1_when_result_md_missing(tmp_path: Path):
    """No result.md → exit 1, no plan written."""
    td = tmp_path / "t"
    td.mkdir()
    (td / "context").mkdir()
    cp = subprocess.run(
        [sys.executable, str(SCRIPT), "--task-dir", str(td), "--format", "json"],
        capture_output=True, text=True,
    )
    assert cp.returncode == 1, cp.stderr
    # Some descriptive stderr message
    assert "result.md" in (cp.stderr + cp.stdout).lower()


def test_helper_returns_rc1_when_status_unparseable(tmp_path: Path):
    """result.md exists but no STATUS line → exit 1."""
    td = tmp_path / "t"
    td.mkdir()
    (td / "result.md").write_text("# task\nNo status line here.\n", encoding="utf-8")
    cp = subprocess.run(
        [sys.executable, str(SCRIPT), "--task-dir", str(td), "--format", "json"],
        capture_output=True, text=True,
    )
    assert cp.returncode == 1, cp.stderr


def test_helper_returns_rc2_when_status_unknown(tmp_path: Path):
    """STATUS: weird (not completed/blocked/cancelled) → exit 2."""
    td = _seed_task_dir(tmp_path / "t", status="something-else")
    cp = subprocess.run(
        [sys.executable, str(SCRIPT), "--task-dir", str(td), "--format", "json"],
        capture_output=True, text=True,
    )
    assert cp.returncode == 2, cp.stderr


# ---------- partial inputs ----------

def test_helper_empty_plan_when_no_host_task_ids_and_no_parent(reconcile, tmp_path: Path):
    """No pipeline host_task_ids AND no host-task-id.txt → empty plan."""
    td = _seed_task_dir(
        tmp_path / "t", status="completed",
        pipeline_host_task_ids=None,
        parent_host_task_id=None,
    )
    plan = reconcile.build_plan(td)
    assert plan["parent_task_id"] is None
    assert plan["stage_task_ids"] == []
    assert plan["reconcile_plan"] == []


def test_helper_parent_only_plan_when_no_pipeline_host_task_ids(reconcile, tmp_path: Path):
    """Only host-task-id.txt present → plan has 1 entry (parent)."""
    td = _seed_task_dir(
        tmp_path / "t", status="completed",
        pipeline_host_task_ids=None,
        parent_host_task_id="parent-only",
    )
    plan = reconcile.build_plan(td)
    actions = plan["reconcile_plan"]
    assert len(actions) == 1
    assert actions[0]["scope"] == "parent"
    assert actions[0]["host_task_id"] == "parent-only"


def test_helper_stage_only_plan_when_no_parent_task_id(reconcile, tmp_path: Path):
    """Only pipeline.json host_task_ids → plan has N stage entries, no parent."""
    td = _seed_task_dir(
        tmp_path / "t", status="completed",
        pipeline_host_task_ids=[{"backend": "s1"}, {"reviewer": "s2"}],
        parent_host_task_id=None,
    )
    plan = reconcile.build_plan(td)
    assert plan["parent_task_id"] is None
    actions = plan["reconcile_plan"]
    assert {a["scope"] for a in actions} == {"stage"}
    assert {a["host_task_id"] for a in actions} == {"s1", "s2"}


def test_helper_handles_custom_agent_names(reconcile, tmp_path: Path):
    """Custom-agent keys in host_task_ids round-trip through the plan."""
    td = _seed_task_dir(
        tmp_path / "t", status="completed",
        pipeline_host_task_ids=[{"my-custom-agent": "custom-id-1"}],
    )
    plan = reconcile.build_plan(td)
    custom = [a for a in plan["reconcile_plan"] if a.get("agent_name") == "my-custom-agent"]
    assert len(custom) == 1
    assert custom[0]["host_task_id"] == "custom-id-1"


def test_helper_tolerates_malformed_pipeline_json(reconcile, tmp_path: Path):
    """Corrupt pipeline.json → empty stage_task_ids, parent still planned, no crash."""
    td = _seed_task_dir(
        tmp_path / "t", status="completed",
        pipeline_corrupt=True,
        parent_host_task_id="parent-x",
    )
    plan = reconcile.build_plan(td)
    assert plan["stage_task_ids"] == []
    actions = plan["reconcile_plan"]
    # Parent still appears in the plan
    assert any(a["scope"] == "parent" and a["host_task_id"] == "parent-x" for a in actions)


def test_helper_legacy_markdown_status_marker(reconcile, tmp_path: Path):
    """Legacy `**Status:** completed` form parses identically to canonical form."""
    td = _seed_task_dir(
        tmp_path / "t", status="completed", legacy_status_form=True,
        pipeline_host_task_ids=[{"backend": "s1"}],
    )
    plan = reconcile.build_plan(td)
    assert plan["terminal_status"] == "completed"
    assert plan["host_status"] == "completed"
    assert any(a["host_task_id"] == "s1" for a in plan["reconcile_plan"])


# ---------- CLI smoke + side-effect freedom ----------

def test_helper_cli_smoke_emits_valid_json(tmp_path: Path):
    """`--format json` returns a parseable JSON object on a healthy fixture."""
    td = _seed_task_dir(
        tmp_path / "t", status="completed",
        pipeline_host_task_ids=[{"backend": "s1"}, {"reviewer": "s2"}],
    )
    cp = subprocess.run(
        [sys.executable, str(SCRIPT), "--task-dir", str(td), "--format", "json"],
        capture_output=True, text=True,
    )
    assert cp.returncode == 0, cp.stderr
    payload = json.loads(cp.stdout)
    assert payload["terminal_status"] == "completed"
    assert isinstance(payload["reconcile_plan"], list) and len(payload["reconcile_plan"]) == 3


def test_helper_text_format_renders_human_readable(tmp_path: Path):
    """`--format text` returns a non-empty human readable summary."""
    td = _seed_task_dir(
        tmp_path / "t", status="completed",
        pipeline_host_task_ids=[{"backend": "s1"}],
    )
    cp = subprocess.run(
        [sys.executable, str(SCRIPT), "--task-dir", str(td), "--format", "text"],
        capture_output=True, text=True,
    )
    assert cp.returncode == 0
    out = cp.stdout
    assert "reconcile" in out.lower()
    assert "s1" in out


def test_helper_no_filesystem_side_effects(tmp_path: Path):
    """Helper must not write anywhere — verify the fixture dir is unchanged."""
    td = _seed_task_dir(
        tmp_path / "t", status="completed",
        pipeline_host_task_ids=[{"backend": "s1"}],
    )
    before = sorted(p.relative_to(td).as_posix() for p in td.rglob("*") if p.is_file())
    subprocess.run(
        [sys.executable, str(SCRIPT), "--task-dir", str(td), "--format", "json"],
        capture_output=True, text=True, check=True,
    )
    after = sorted(p.relative_to(td).as_posix() for p in td.rglob("*") if p.is_file())
    assert before == after, f"helper created/removed files: {set(after) ^ set(before)}"


# ---------- Capability gate semantics (documented in plan output) ----------

def test_helper_plan_is_consumable_by_capability_gated_caller(reconcile, tmp_path: Path):
    """The plan output carries every field a capability-gated caller needs.

    The reconcile is meant to be executed by a wrapper that gates each
    TaskUpdate on ``HAS_TASK_TOOLS == 1``. The helper itself is host-agnostic,
    so we verify the plan structure carries exactly the fields a wrapper needs.
    """
    td = _seed_task_dir(
        tmp_path / "t", status="completed",
        pipeline_host_task_ids=[{"backend": "s1"}],
    )
    plan = reconcile.build_plan(td)
    for action in plan["reconcile_plan"]:
        # Required fields for any TaskGet/TaskUpdate wrapper
        assert "host_task_id" in action
        assert "target_status" in action
        assert action["target_status"] in {"completed", "blocked"}
        assert action["scope"] in {"parent", "stage"}
        if action["scope"] == "stage":
            assert "stage_index" in action and "agent_name" in action
