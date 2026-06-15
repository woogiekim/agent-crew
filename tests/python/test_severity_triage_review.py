"""Red TDD tests for severity-triaged code-review acceptance (backlog #2).

Spec: context/prd.md - PRD: Severity-triaged code review acceptance
      (superpowers-benchmark backlog #2).

These tests pin the new contract that lives across one Python script and
four markdown rule files:

1. ``core/scripts/quality_loop_lib.py``
   - ``FINDING_TERMINAL_STATUSES`` must include ``"deferred-minor"``.
   - ``FINDING_OWNER_STATUSES`` must NOT include ``"deferred-minor"``
     (auto-promoted minors are exempt from owner/follow-up enforcement).
   - The runtime gate (``core/scripts/quality-loop-check.py``) must PASS a
     synthetic ``finding-register.json`` whose only entry has
     status=``deferred-minor`` (with normal fields the reviewer auto-upsert
     ships: severity ``P3``, focused ``verification.test_targets``).
   - Regression: existing terminal statuses still pass; unknown statuses
     still fail with ``invalid_finding_register``.

2. Reviewer auto-upsert helper for MINOR findings
   (PRD acceptance criterion: AC #1).

   The reviewer must auto-upsert each MINOR finding into
   ``finding-register.json`` with status=``deferred-minor`` and
   severity=``P3``. We exercise this through whichever surface the
   implementer chooses (per handoff.md Step 2):

   - a new helper script at ``core/scripts/auto-record-minor-findings.py``, OR
   - a new function in ``core/scripts/quality_loop_lib.py``
     (e.g. ``upsert_deferred_minor_findings``).

   The helper must:
   - Create ``finding-register.json`` if missing (schema_version=1,
     ``findings=[]`` shell).
   - Update (not duplicate) an existing finding with the same id.
   - Append a new finding when id is unknown.
   - Default status=``deferred-minor`` and severity=``P3`` on each
     upserted entry, plus carry the supervisor-supplied
     owner/timestamp/source defaults.

3. Markdown contract tests (PRD acceptance criteria: AC #2, #3, #4):
   - ``core/agents/supervisor-retry.md`` loop-back rule names
     CRITICAL+IMPORTANT as the only re-loop triggers; MINOR is
     documented as auto-promoting to ``deferred-minor``.
   - ``core/agents/skills/code-review.md`` documents the new severity
     vocabulary CRITICAL / IMPORTANT / MINOR and the
     BLOCKER<->CRITICAL / WARNING<->IMPORTANT / NOTE<->MINOR remap
     (or the legacy tokens are removed in favor of the new tokens).
   - ``core/agents/reviewer.md`` Step 4 return-block documents the new
     ``MINOR_DEFERRED:`` annotation that pairs with ``REVIEW: APPROVED``.
   - ``core/rules/quality-loop.md`` lists ``deferred-minor`` in its valid
     terminal statuses.

These tests are RED on purpose: they fail until the implementer extends
the Python set, adds the auto-upsert helper, and edits the four
markdown files documented in handoff.md.
"""

from __future__ import annotations

import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPTS_DIR = REPO_ROOT / "core" / "scripts"
QUALITY_LIB_PATH = SCRIPTS_DIR / "quality_loop_lib.py"
QUALITY_CHECK = SCRIPTS_DIR / "quality-loop-check.py"
AUTO_RECORD_MINOR_SCRIPT = SCRIPTS_DIR / "auto-record-minor-findings.py"

CODE_REVIEW_SKILL = REPO_ROOT / "core" / "agents" / "skills" / "code-review.md"
REVIEWER_AGENT = REPO_ROOT / "core" / "agents" / "reviewer.md"
SUPERVISOR_RETRY = REPO_ROOT / "core" / "agents" / "supervisor-retry.md"
QUALITY_LOOP_RULE = REPO_ROOT / "core" / "rules" / "quality-loop.md"

if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader, f"could not load module from {path}"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


quality_loop_lib = _load_module(QUALITY_LIB_PATH, "quality_loop_lib")


# ---------------------------------------------------------------------------
# Section 1: Python set membership for FINDING_TERMINAL_STATUSES / OWNER set
# ---------------------------------------------------------------------------

def test_finding_terminal_statuses_includes_deferred_minor() -> None:
    """deferred-minor must be a terminal status (PRD Must-have, AC #3)."""
    assert "deferred-minor" in quality_loop_lib.FINDING_TERMINAL_STATUSES, (
        "FINDING_TERMINAL_STATUSES must include 'deferred-minor' so the "
        "auto-promoted MINOR findings pass the completion gate."
    )


def test_finding_owner_statuses_excludes_deferred_minor() -> None:
    """deferred-minor is exempt from owner/follow-up enforcement (PRD)."""
    assert "deferred-minor" not in quality_loop_lib.FINDING_OWNER_STATUSES, (
        "FINDING_OWNER_STATUSES must NOT include 'deferred-minor' - "
        "auto-deferred minors are exempt from owner/follow-up enforcement."
    )


def test_existing_terminal_statuses_preserved() -> None:
    """Regression: existing closed-set members must remain (PRD AC #3 regression)."""
    expected_legacy = {
        "fixed",
        "accepted-risk",
        "moved-to-issue",
        "out-of-scope",
        "false-positive",
    }
    missing = expected_legacy - set(quality_loop_lib.FINDING_TERMINAL_STATUSES)
    assert not missing, (
        f"existing terminal statuses must remain in the set; missing: {missing}"
    )


# ---------------------------------------------------------------------------
# Section 2: Runtime gate (quality-loop-check.py) must accept deferred-minor
# ---------------------------------------------------------------------------

def _write_minimal_task(tmp_path: Path) -> Path:
    """Create a task_dir that already satisfies the surrounding quality-loop gate.

    The point of this helper is to isolate the finding-register validation
    branch: every other gate must already pass so that any failure points
    cleanly at the deferred-minor / unknown-status behavior.
    """
    task_id = "20260601-000000-0"
    session_id = "20260601-000000"
    state_dir = tmp_path / "state" / "project"
    task_dir = state_dir / "tasks" / task_id
    (task_dir / "context").mkdir(parents=True)

    (task_dir / "register.json").write_text(
        json.dumps(
            {
                "task_id": task_id,
                "session_id": session_id,
                "task": "Implement a new severity-triage gate",
                "current_phase": "completed",
                "blocked_by": [],
            }
        ),
        encoding="utf-8",
    )
    (task_dir / "pipeline.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "task": "Implement a new severity-triage gate",
                "stages": [
                    {"agents": ["backend"], "tdd_parallel": True},
                    "reviewer",
                ],
                "completed_stages": 2,
            }
        ),
        encoding="utf-8",
    )
    (task_dir / "result.md").write_text("STATUS: completed\n", encoding="utf-8")

    rows = [
        {
            "ts": "2026-06-01T00:00:00Z",
            "trace_id": f"{session_id}.{task_id}.1.1",
            "task_id": task_id,
            "session_id": session_id,
            "event": "STAGE_DONE",
            "stage": 1,
            "agent": "test-writer",
            "attempt": 1,
            "status": "completed",
            "detail": "TDD RED GREEN REFACTOR, 1 test passed",
            "files": ["tests/python/test_severity_triage_review.py"],
        },
        {
            "ts": "2026-06-01T00:00:01Z",
            "trace_id": f"{session_id}.{task_id}.1.1",
            "task_id": task_id,
            "session_id": session_id,
            "event": "STAGE_DONE",
            "stage": 1,
            "agent": "backend",
            "attempt": 1,
            "status": "completed",
            "detail": "backend - implemented severity-triage gate",
            "files": [],
        },
        {
            "ts": "2026-06-01T00:00:02Z",
            "trace_id": f"{session_id}.{task_id}.2.1",
            "task_id": task_id,
            "session_id": session_id,
            "event": "STAGE_DONE",
            "stage": 2,
            "agent": "reviewer",
            "attempt": 1,
            "status": "completed",
            "detail": "reviewer - REVIEW: APPROVED QUALITY_METRICS: context/quality-metrics.json",
            "files": [],
        },
    ]
    with (task_dir / "progress.buffer.jsonl").open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row) + "\n")

    (task_dir / "context" / "quality-metrics.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "hallucination_detected": False,
                "rollback_performed": False,
                "human_intervention_required": False,
                "factuality_review": "passed",
                "evidence_paths": ["context/review.md"],
            }
        ),
        encoding="utf-8",
    )
    (task_dir / "context" / "tdd_log.md").write_text(
        "TDD: RED -> GREEN -> REFACTOR. tests passed 4.\n", encoding="utf-8"
    )
    (task_dir / "context" / "tdd-red.md").write_text(
        "TDD-RED: focused pytest failed as expected before implementation.\n",
        encoding="utf-8",
    )
    (task_dir / "context" / "tdd-refactor.md").write_text(
        "TDD-REFACTOR: no-op refactor review complete; post-refactor pytest passed.\n",
        encoding="utf-8",
    )
    (task_dir / "context" / "review.md").write_text(
        "REVIEW: APPROVED QUALITY_METRICS: context/quality-metrics.json after refactor.\n",
        encoding="utf-8",
    )
    return task_dir


def _run_quality_loop_check(task_dir: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["python3", str(QUALITY_CHECK), "--task-dir", str(task_dir)],
        text=True,
        capture_output=True,
    )


def test_quality_loop_check_passes_with_deferred_minor_finding(tmp_path: Path) -> None:
    """A finding-register with only deferred-minor entries must PASS (AC #3)."""
    task_dir = _write_minimal_task(tmp_path)
    (task_dir / "context" / "finding-register.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "findings": [
                    {
                        "id": "F-100",
                        "title": "commit message lacks conventional prefix",
                        "severity": "P3",
                        "status": "deferred-minor",
                        "source": {"artifact": "context/review.md"},
                        "affected": [{"file": "core/scripts/quality_loop_lib.py"}],
                        "recommended_fix": (
                            "follow conventional commit prefix on next "
                            "touch; no behavior change required."
                        ),
                        "verification": {
                            "test_targets": [
                                "tests/python/test_severity_triage_review.py"
                                "::test_quality_loop_check_passes_with_deferred_minor_finding",
                            ],
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    result = _run_quality_loop_check(task_dir)

    assert result.returncode == 0, (
        "deferred-minor entry should PASS the quality-loop gate. "
        f"stdout={result.stdout}\nstderr={result.stderr}"
    )
    assert "invalid_finding_register" not in result.stdout
    assert "unresolved_finding_register_entries" not in result.stdout


def test_quality_loop_check_still_rejects_unknown_status(tmp_path: Path) -> None:
    """Regression (PRD AC #4): unknown status still fails the gate."""
    task_dir = _write_minimal_task(tmp_path)
    (task_dir / "context" / "finding-register.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "findings": [
                    {
                        "id": "F-200",
                        "title": "synthetic finding with bogus status",
                        "severity": "P3",
                        "status": "totally-made-up",
                        "source": {"artifact": "context/review.md"},
                        "affected": [{"file": "core/scripts/quality_loop_lib.py"}],
                        "recommended_fix": "n/a",
                        "verification": {
                            "test_targets": [
                                "tests/python/test_severity_triage_review.py"
                                "::test_quality_loop_check_still_rejects_unknown_status",
                            ],
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    result = _run_quality_loop_check(task_dir)

    assert result.returncode == 1
    assert "invalid_finding_register" in result.stdout, (
        "an unknown status must still fail with `invalid_finding_register`; "
        f"stdout={result.stdout}"
    )


# ---------------------------------------------------------------------------
# Section 3: Reviewer auto-upsert helper for MINOR findings
# ---------------------------------------------------------------------------

def _resolve_upsert_helper():
    """Return a (kind, callable_or_path) describing how to invoke the helper.

    Two surfaces are accepted, per handoff.md Step 2:
    - ("function", callable) - new function on quality_loop_lib
    - ("script", path)        - new core/scripts/auto-record-minor-findings.py
    """
    candidate_names = (
        "upsert_deferred_minor_findings",
        "upsert_minor_findings",
        "auto_record_minor_findings",
        "record_minor_findings",
    )
    for name in candidate_names:
        fn = getattr(quality_loop_lib, name, None)
        if callable(fn):
            return ("function", fn, name)

    if AUTO_RECORD_MINOR_SCRIPT.is_file():
        return ("script", AUTO_RECORD_MINOR_SCRIPT, AUTO_RECORD_MINOR_SCRIPT.name)

    return (None, None, None)


def _call_upsert(register_path: Path, findings: list[dict]) -> None:
    """Invoke whichever surface the implementer chose."""
    kind, target, _name = _resolve_upsert_helper()
    assert kind is not None, (
        "The reviewer MINOR auto-upsert helper is missing. Implementer must "
        "add either a function on quality_loop_lib.py "
        "(e.g. upsert_deferred_minor_findings(path, findings)) or "
        "a new script at core/scripts/auto-record-minor-findings.py."
    )
    if kind == "function":
        target(register_path, findings)
        return

    # Script surface: pass register path + JSON-encoded findings on stdin.
    payload = json.dumps({"register_path": str(register_path), "findings": findings})
    result = subprocess.run(
        ["python3", str(target)],
        input=payload,
        text=True,
        capture_output=True,
    )
    assert result.returncode == 0, (
        f"auto-record-minor-findings.py failed: stdout={result.stdout!r} "
        f"stderr={result.stderr!r}"
    )


def _read_register(register_path: Path) -> dict:
    return json.loads(register_path.read_text(encoding="utf-8"))


def _sample_minor_finding(
    finding_id: str = "F-301",
    title: str = "non-conforming commit message subject",
) -> dict:
    return {
        "id": finding_id,
        "title": title,
        "source": {"artifact": "context/review.md"},
        "affected": [
            {"file": "core/scripts/quality_loop_lib.py", "line": 89},
        ],
        "recommended_fix": "Use Conventional Commits subject on next touch.",
        "verification": {
            "verification_exception": "deferred-minor",
        },
    }


def test_upsert_creates_register_file_when_missing(tmp_path: Path) -> None:
    """File created with schema_version=1 + findings shell when absent."""
    register = tmp_path / "finding-register.json"
    assert not register.exists()

    _call_upsert(register, [_sample_minor_finding()])

    assert register.is_file(), "helper must create the register file when missing"
    payload = _read_register(register)
    assert payload.get("schema_version") == 1
    assert isinstance(payload.get("findings"), list)
    assert len(payload["findings"]) == 1


def test_upsert_sets_deferred_minor_status_and_p3_severity(tmp_path: Path) -> None:
    """Each upserted entry gets status=deferred-minor, severity=P3 (PRD AC #1)."""
    register = tmp_path / "finding-register.json"
    _call_upsert(register, [_sample_minor_finding("F-310")])

    payload = _read_register(register)
    entries = [f for f in payload["findings"] if f["id"] == "F-310"]
    assert entries, "upserted finding not found by id"

    finding = entries[0]
    assert finding["status"] == "deferred-minor", (
        "MINOR auto-upsert must set status='deferred-minor'"
    )
    assert finding["severity"] == "P3", (
        "MINOR maps to severity P3 (PRD: CRITICAL->P1, IMPORTANT->P2, MINOR->P3)"
    )


def test_upsert_updates_existing_finding_by_id(tmp_path: Path) -> None:
    """Re-upserting the same id updates in place; no duplicate row."""
    register = tmp_path / "finding-register.json"

    _call_upsert(register, [_sample_minor_finding("F-320", title="first title")])
    _call_upsert(register, [_sample_minor_finding("F-320", title="updated title")])

    payload = _read_register(register)
    matches = [f for f in payload["findings"] if f["id"] == "F-320"]
    assert len(matches) == 1, (
        "re-upserting an existing id must update in place, not duplicate"
    )
    assert matches[0]["title"] == "updated title"


def test_upsert_appends_new_finding_alongside_existing(tmp_path: Path) -> None:
    """A new id is appended; existing entries stay intact."""
    register = tmp_path / "finding-register.json"

    _call_upsert(register, [_sample_minor_finding("F-330", title="alpha")])
    _call_upsert(register, [_sample_minor_finding("F-340", title="beta")])

    payload = _read_register(register)
    ids = sorted(f["id"] for f in payload["findings"])
    assert ids == ["F-330", "F-340"], (
        f"both ids must be present after independent upserts; got {ids}"
    )


def test_upsert_passes_quality_loop_check(tmp_path: Path) -> None:
    """Round-trip: helper-produced register passes quality-loop-check.py."""
    task_dir = _write_minimal_task(tmp_path)
    register = task_dir / "context" / "finding-register.json"

    _call_upsert(register, [_sample_minor_finding("F-350")])

    result = _run_quality_loop_check(task_dir)
    assert result.returncode == 0, (
        "register produced by the auto-upsert helper must PASS the "
        f"runtime quality gate. stdout={result.stdout}\nstderr={result.stderr}"
    )


# ---------------------------------------------------------------------------
# Section 4: Markdown contract - supervisor-retry.md loop-back rule
# ---------------------------------------------------------------------------

def _read_markdown(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_supervisor_retry_loop_back_targets_critical_and_important_only() -> None:
    """Supervisor-retry loop-back rule names CRITICAL + IMPORTANT explicitly (PRD AC #2)."""
    text = _read_markdown(SUPERVISOR_RETRY)
    lowered = text.lower()

    # The loop-back rule must mention both CRITICAL and IMPORTANT as the
    # severity tokens that trigger re-loop.
    assert "critical" in lowered, "loop-back rule must name CRITICAL"
    assert "important" in lowered, "loop-back rule must name IMPORTANT"

    # The NEEDS_CHANGES trigger row in the table must be qualified by
    # severity: "classified as CRITICAL or IMPORTANT" (or equivalent).
    pattern = re.compile(r"critical[^\n]{0,40}important|important[^\n]{0,40}critical", re.IGNORECASE)
    assert pattern.search(text), (
        "supervisor-retry.md must describe the loop-back trigger as "
        "CRITICAL+IMPORTANT (e.g. 'classified as CRITICAL or IMPORTANT')."
    )


def test_supervisor_retry_documents_minor_auto_promotion_to_deferred_minor() -> None:
    """MINOR auto-promotes to deferred-minor; not a loop-back trigger (PRD AC #2)."""
    text = _read_markdown(SUPERVISOR_RETRY)
    lowered = text.lower()

    assert "minor" in lowered, "supervisor-retry.md must reference MINOR severity"
    assert "deferred-minor" in lowered, (
        "supervisor-retry.md must document the MINOR -> deferred-minor "
        "auto-promotion path so MINOR-only reviews do not re-loop."
    )

    # The DEFERRED_MINOR: pointer-block contract (handoff.md append step).
    assert "MINOR_DEFERRED" in text or "DEFERRED_MINOR" in text, (
        "supervisor-retry.md must mention the MINOR_DEFERRED:/DEFERRED_MINOR: "
        "annotation that the reviewer emits and the supervisor carries into "
        "handoff.md."
    )


# ---------------------------------------------------------------------------
# Section 5: Markdown contract - code-review skill new severity vocabulary
# ---------------------------------------------------------------------------

def test_code_review_skill_uses_new_severity_vocabulary() -> None:
    """code-review.md documents CRITICAL/IMPORTANT/MINOR (PRD AC #4)."""
    text = _read_markdown(CODE_REVIEW_SKILL)

    for token in ("CRITICAL", "IMPORTANT", "MINOR"):
        assert token in text, (
            f"code-review.md must document the new severity token {token!r} "
            "(BLOCKER/WARNING/NOTE -> CRITICAL/IMPORTANT/MINOR remap)."
        )


def test_code_review_skill_remaps_or_retires_legacy_severity_tokens() -> None:
    """Either the BLOCKER<->CRITICAL etc. mapping is shown, or the legacy
    tokens are removed in favor of the new tokens.

    PRD says: 'all three new tokens appear in that file and a
    BLOCKER<->CRITICAL / WARNING<->IMPORTANT / NOTE<->MINOR mapping is
    documented (or BLOCKER/WARNING/NOTE are completely removed in favor
    of the new tokens).'
    """
    text = _read_markdown(CODE_REVIEW_SKILL)
    lowered = text.lower()

    legacy_tokens = ("BLOCKER", "WARNING", "NOTE")
    legacy_present = [token for token in legacy_tokens if token in text]

    if not legacy_present:
        # Acceptable: legacy vocabulary fully retired.
        return

    # If legacy tokens linger, the mapping table or prose must explain how
    # each maps to a new token. Look for both halves of each pair appearing
    # close together (within 80 chars on the same line/block).
    pair_patterns = (
        (r"blocker", r"critical"),
        (r"warning", r"important"),
        (r"note", r"minor"),
    )
    for legacy, new in pair_patterns:
        if legacy.upper() not in legacy_present:
            continue
        pat = re.compile(
            rf"{legacy}[^\n]{{0,80}}{new}|{new}[^\n]{{0,80}}{legacy}",
            re.IGNORECASE,
        )
        assert pat.search(lowered), (
            f"code-review.md still mentions {legacy.upper()} but no "
            f"{legacy.upper()}<->{new.upper()} mapping is documented near it."
        )


# ---------------------------------------------------------------------------
# Section 6: Markdown contract - reviewer.md return block
# ---------------------------------------------------------------------------

def test_reviewer_return_block_documents_minor_deferred_annotation() -> None:
    """reviewer.md documents the MINOR_DEFERRED return line (PRD AC #1, #5)."""
    text = _read_markdown(REVIEWER_AGENT)

    assert "MINOR_DEFERRED" in text, (
        "reviewer.md Step 4 return block must document the new "
        "`MINOR_DEFERRED:` annotation (paired with REVIEW: APPROVED)."
    )
    assert "deferred-minor" in text, (
        "reviewer.md must describe the auto-promotion to status "
        "'deferred-minor' in finding-register.json."
    )

    # The MINOR_DEFERRED line must be paired with REVIEW: APPROVED (per PRD).
    pattern = re.compile(
        r"REVIEW:\s*APPROVED[\s\S]{0,800}MINOR_DEFERRED"
        r"|MINOR_DEFERRED[\s\S]{0,800}REVIEW:\s*APPROVED",
        re.IGNORECASE,
    )
    assert pattern.search(text), (
        "reviewer.md must show MINOR_DEFERRED travelling with "
        "REVIEW: APPROVED (no re-loop)."
    )


# ---------------------------------------------------------------------------
# Section 7: Markdown contract - quality-loop.md valid statuses
# ---------------------------------------------------------------------------

def test_quality_loop_rule_lists_deferred_minor_as_valid_status() -> None:
    """quality-loop.md lists deferred-minor as a valid terminal status (PRD)."""
    text = _read_markdown(QUALITY_LOOP_RULE)
    lowered = text.lower()

    assert "deferred-minor" in lowered, (
        "core/rules/quality-loop.md must list `deferred-minor` in its "
        "valid-statuses section (single-source-of-truth alignment with "
        "FINDING_TERMINAL_STATUSES)."
    )

    # The deferred-minor mention must be inside (or just after) the
    # Confirmed Finding Register section, not stray prose.
    register_header_idx = text.find("Confirmed Finding Register")
    deferred_idx = lowered.find("deferred-minor")
    assert register_header_idx != -1, (
        "Confirmed Finding Register section header missing from quality-loop.md"
    )
    assert deferred_idx > register_header_idx, (
        "deferred-minor must appear in/after the Confirmed Finding Register "
        "section, not in an unrelated location."
    )
