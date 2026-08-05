"""Regression tests for issuer.md's Step 1.5 tracker mutation safety evidence
producer.

Issue: core/hooks/tracker-mutation-guard.sh blocks every Plane-mutating MCP
call unless {TASK_DIR}/context/specialist-dispatch.md and
{TASK_DIR}/context/tracker-fallback-validation.json already exist with
specific fields and a user-owned approval record matches the exact tool and
payload. issuer.md must describe both validation evidence and the approval
evidence needed for a legitimate Plane mutation retry.

Spec sources: handoff.md ("Key Technical Decision" / positioning),
context/prd.md (AC-001..AC-005), context/analysis.md ("Evidence-Grounded
Reasoning" table -- exact heading/field facts). Content-assertion style,
following the existing tests/python/test_issuer_lifecycle_contract.py and
tests/python/test_agent_routing_issuer.py conventions for this same target
file: there is no runtime application code to exercise, so the "behavior"
under test is the exact instruction text and its position, matching what
core/hooks/tracker-mutation-guard.sh parses at runtime.

Checklist cross-reference notes (see context/test-checklist.md):
- TC-012 (AC-005 diff confinement to core/agents/issuer.md only) is
  enforced by the reviewer stage's git-diff read, per the accepted
  checklist-review footnote -- not a unit test here.
- TC-013 (regression: existing issuer.md content-assertion markers stay
  intact) is covered by the pre-existing
  tests/python/test_issuer_lifecycle_contract.py suite, not duplicated
  here.
"""
from __future__ import annotations

import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
ISSUER_PATH = REPO_ROOT / "core" / "agents" / "issuer.md"

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")


def _load_issuer_text() -> str:
    return ISSUER_PATH.read_text(encoding="utf-8")


def _section_text(text: str, contains: str) -> str:
    """Return the text of the first section whose heading line contains
    `contains` (case-sensitive substring), from that heading line up to
    (but excluding) the next heading of equal or higher level."""
    lines = text.splitlines()
    start_idx = None
    level = None
    for i, line in enumerate(lines):
        m = _HEADING_RE.match(line)
        if m and contains in line:
            start_idx = i
            level = len(m.group(1))
            break
    if start_idx is None:
        return ""
    end_idx = len(lines)
    for j in range(start_idx + 1, len(lines)):
        m = _HEADING_RE.match(lines[j])
        if m and len(m.group(1)) <= level:
            end_idx = j
            break
    return "\n".join(lines[start_idx:end_idx])


def _step_1_5_section(text: str) -> str:
    """Locate the new Step 1.5 section by heading, tolerant of the dash
    style between "Step 1.5" and the rest of the heading title (the spec
    documents use both "--" (handoff.md) and an em dash (prd.md) across
    their own headings, so the exact connector character is not part of
    the parsing contract)."""
    match = re.search(r"(?m)^#{2,4}\s.*Step 1\.5.*$", text)
    assert match, "no heading containing 'Step 1.5' found in core/agents/issuer.md"
    assert "Tracker Mutation Safety Evidence" in match.group(0), (
        "Step 1.5 heading does not contain 'Tracker Mutation Safety Evidence': "
        f"{match.group(0)!r}"
    )
    return _section_text(text, "Step 1.5")


def _redirect_operator(section: str, filename: str) -> str | None:
    """Return the redirection operator ('>' or '>>') that writes
    ${TASK_DIR}/context/<filename>, anchored on the full path rather than
    the bare filename so a plain prose mention of the filename (e.g. an
    introductory sentence naming both evidence files) is never mistaken
    for the write site."""
    pattern = re.compile(
        r'(>{1,2})\s*"?\$\{TASK_DIR\}/context/' + re.escape(filename)
    )
    match = pattern.search(section)
    return match.group(1) if match else None


def _write_start(section: str, filename: str) -> int:
    pattern = re.compile(
        r'>{1,2}\s*"?\$\{TASK_DIR\}/context/' + re.escape(filename)
    )
    match = pattern.search(section)
    assert match, (
        f"no redirection writing ${{TASK_DIR}}/context/{filename} found in Step 1.5"
    )
    return match.start()


def _split_write_blocks(section: str) -> tuple[str, str]:
    """Split the Step 1.5 section into the (specialist-dispatch.md write,
    tracker-fallback-validation.json write) blocks, anchored on each
    file's actual redirection site (see `_write_start`) so the split is
    agnostic to the exact heredoc delimiter the implementer chooses."""
    dispatch_idx = _write_start(section, "specialist-dispatch.md")
    validation_idx = _write_start(section, "tracker-fallback-validation.json")
    if dispatch_idx < validation_idx:
        return section[dispatch_idx:validation_idx], section[validation_idx:]
    return section[dispatch_idx:], section[validation_idx:dispatch_idx]


def _assert_overwrite_not_append(section: str, filename: str) -> None:
    operator = _redirect_operator(section, filename)
    assert operator is not None, (
        f"no redirection writing ${{TASK_DIR}}/context/{filename} found in Step 1.5"
    )
    assert operator == ">", (
        f"{filename} write must use overwrite ('>'), found append ('{operator}')"
    )


# Spec: prd.md AC-001 / "Will Do" bullet 1 -- Step 1.5 heading present.
def test_success_case_step_1_5_heading_present():
    text = _load_issuer_text()
    section = _step_1_5_section(text)
    assert section, "Step 1.5 section body could not be extracted"


# Spec: prd.md AC-001 -- specialist-dispatch.md write satisfies
# tracker-mutation-guard.sh's has_issuer_dispatch() (issuer substring +
# one of selected_agent/specialist_agent/dispatcher).
def test_success_case_specialist_dispatch_write_satisfies_has_issuer_dispatch():
    text = _load_issuer_text()
    section = _step_1_5_section(text)
    dispatch_block, _ = _split_write_blocks(section)
    assert re.search(r"issuer", dispatch_block, re.IGNORECASE), (
        "specialist-dispatch.md write must contain 'issuer' (case-insensitive)"
    )
    assert any(
        marker in dispatch_block
        for marker in ("selected_agent", "specialist_agent", "dispatcher")
    ), (
        "specialist-dispatch.md write must contain one of selected_agent / "
        "specialist_agent / dispatcher"
    )


# Spec: prd.md AC-002 -- tracker-fallback-validation.json write satisfies
# has_tracker_fallback_contract() (status=passed, agent/validated_by=issuer,
# adapter_contract_loaded, payload_validated).
def test_success_case_tracker_fallback_validation_write_has_required_fields():
    text = _load_issuer_text()
    section = _step_1_5_section(text)
    _, validation_block = _split_write_blocks(section)
    assert re.search(r'"status"\s*:\s*"passed"', validation_block), (
        "tracker-fallback-validation.json write must set status=passed"
    )
    assert re.search(r'"(agent|validated_by)"\s*:\s*"issuer"', validation_block), (
        "tracker-fallback-validation.json write must identify agent/validated_by "
        "as issuer"
    )
    assert re.search(r'"adapter_contract_loaded"\s*:\s*true\b', validation_block), (
        "adapter_contract_loaded must be present as a literal JSON boolean"
    )
    assert re.search(r'"payload_validated"\s*:\s*true\b', validation_block), (
        "payload_validated must be present as a literal JSON boolean"
    )


def test_success_case_tracker_mutation_approval_schema_is_documented():
    text = _load_issuer_text()
    section = _step_1_5_section(text)

    assert "tracker-mutation-approval.json" in section
    assert "agent-crew.tracker-mutation-approval.v1" in section
    assert '"approved": true' in section
    assert '"tool_name": "mcp__plane__create_work_item"' in section
    assert '"tool_input_sha256"' in section
    assert '"scope": "single_tool_payload"' in section
    assert '"approved_by": "user"' in section
    assert '"expires_at"' in section


def test_boundary_case_tracker_mutation_approval_is_exact_and_user_owned():
    text = _load_issuer_text()
    section = _step_1_5_section(text)

    for phrase in (
        "broad approval",
        "different\nPlane tool",
        "changed payload",
        "expired approval",
        "agent itself",
        "do not write the approval file",
        "do not call the Plane-mutating MCP tool",
    ):
        assert phrase in section


# Spec: prd.md AC-002 -- "using literal JSON booleans (true), not the
# string "true"" -- matching bool_field() verbatim (JSON typing, not
# string equality).
def test_boundary_case_validation_booleans_are_literal_json_not_strings():
    text = _load_issuer_text()
    section = _step_1_5_section(text)
    _, validation_block = _split_write_blocks(section)
    for field in ("adapter_contract_loaded", "payload_validated"):
        quoted = re.search(rf'"{field}"\s*:\s*"true"', validation_block)
        assert quoted is None, (
            f'{field} must not be written as the quoted string "true" -- '
            "bool_field() requires a literal JSON boolean"
        )


# Spec: prd.md AC-004 / handoff.md "no-op when TASK_DIR is unset" -- do not
# fabricate evidence for a non-existent task context.
def test_boundary_case_step_1_5_gates_on_task_dir_being_set():
    text = _load_issuer_text()
    section = _step_1_5_section(text)
    assert re.search(r'-[nz]\s*"?\$\{?TASK_DIR', section), (
        "Step 1.5 must contain an explicit TASK_DIR-set guard "
        '(e.g. `[ -n "${TASK_DIR:-}" ]`) so it no-ops when TASK_DIR is unset'
    )


# Spec: prd.md "Will Do" bullet 2(a) -- creates {TASK_DIR}/context if
# missing.
def test_success_case_step_1_5_creates_context_directory_before_writes():
    text = _load_issuer_text()
    section = _step_1_5_section(text)
    assert re.search(r"mkdir\s+-p\s+\"?\$\{TASK_DIR\}/context", section), (
        "Step 1.5 must create ${TASK_DIR}/context before writing evidence files"
    )


# Spec: not a numbered AC, but required for the guard's per-invocation
# contract to stay correct across issuer retries (checklist TC-007);
# matches the existing make_task_contract() overwrite semantics in
# tests/shell/test_tracker_mutation_guard.bash.
def test_boundary_case_step_1_5_writes_use_overwrite_not_append():
    text = _load_issuer_text()
    section = _step_1_5_section(text)
    _assert_overwrite_not_append(section, "specialist-dispatch.md")
    _assert_overwrite_not_append(section, "tracker-fallback-validation.json")


# Spec: prd.md AC-003 -- positioned after Step 1's pre-mutation gate
# concludes and before "## Adapter Interface Contract".
def test_success_case_step_1_5_is_positioned_after_step_1_and_before_adapter_contract():
    text = _load_issuer_text()
    proceed_abort_idx = text.find("Proceed / Abort logic")
    issue_count_idx = text.find("Issue count resolution")
    assert proceed_abort_idx != -1 or issue_count_idx != -1, (
        "expected pre-existing Step 1 subsection anchor "
        "('Proceed / Abort logic' or 'Issue count resolution') not found"
    )
    step_1_end_idx = max(proceed_abort_idx, issue_count_idx)

    step_1_5_match = re.search(r"(?m)^#{2,4}\s.*Step 1\.5.*$", text)
    assert step_1_5_match, "Step 1.5 heading not found"
    step_1_5_idx = step_1_5_match.start()

    adapter_contract_idx = text.find("## Adapter Interface Contract")
    assert adapter_contract_idx != -1, (
        "expected pre-existing '## Adapter Interface Contract' heading not found"
    )

    assert step_1_end_idx < step_1_5_idx, (
        "Step 1.5 must appear after Step 1's Proceed/Abort logic or Issue "
        "count resolution content concludes"
    )
    assert step_1_5_idx < adapter_contract_idx, (
        "Step 1.5 must appear before '## Adapter Interface Contract'"
    )


# Spec: prd.md AC-003 cross-reference / "Will Do" bullet 3 -- Step 0.5
# point 7 ("Dispatch by operation") must note that Step 1.5 has already
# run.
def test_success_case_step_0_5_point_7_cross_references_step_1_5():
    text = _load_issuer_text()
    step_0_5_section = _section_text(text, "Step 0.5")
    assert step_0_5_section, "Step 0.5 section not found"

    lines = step_0_5_section.splitlines()
    point_7_start = None
    for i, line in enumerate(lines):
        if re.match(r"^\s*7[.)]\s", line) and "dispatch by operation" in line.lower():
            point_7_start = i
            break
    assert point_7_start is not None, (
        "Step 0.5 point 7 ('Dispatch by operation') not found"
    )
    point_7_end = len(lines)
    for j in range(point_7_start + 1, len(lines)):
        if re.match(r"^\s*8[.)]\s", lines[j]) or _HEADING_RE.match(lines[j]):
            point_7_end = j
            break
    point_7_block = "\n".join(lines[point_7_start:point_7_end])

    assert "Step 1.5" in point_7_block, (
        "Step 0.5 point 7 must cross-reference 'Step 1.5' having already run "
        "before any create/transition/update branch executes"
    )


# Spec: prd.md AC-004 -- tool-agnostic architecture: "must not branch on
# BACKEND_ADAPTER -- it applies to every adapter, not just Plane." A prose
# mention of BACKEND_ADAPTER explaining that the step does *not* branch on
# it (the documented rationale PRD "Will Do" bullet 4 asks for) is allowed;
# only an actual conditional/branch construct keyed on it is forbidden.
def test_boundary_case_step_1_5_has_no_backend_adapter_branching():
    text = _load_issuer_text()
    section = _step_1_5_section(text)
    branch_pattern = re.compile(
        r"(if|elif|case)\s*[\[\(\"]{0,2}[^\n]*BACKEND_ADAPTER", re.IGNORECASE
    )
    match = branch_pattern.search(section)
    assert match is None, (
        "Step 1.5 must not contain a conditional branch keyed on "
        f"BACKEND_ADAPTER: {match.group(0)!r}"
    )


# Spec: prd.md Non-Functional "Backward compatibility" + "Will NOT Do" --
# no renumbering of Step 0.5's existing 7 numbered items beyond the single
# added cross-reference sentence in point 7.
def test_success_case_step_0_5_retains_seven_numbered_items():
    text = _load_issuer_text()
    step_0_5_section = _section_text(text, "Step 0.5")
    assert step_0_5_section, "Step 0.5 section not found"
    top_level_items = re.findall(r"(?m)^\d+[.)]\s", step_0_5_section)
    assert len(top_level_items) == 7, (
        "Step 0.5 must retain exactly 7 top-level numbered items "
        f"(found {len(top_level_items)}): {top_level_items}"
    )
