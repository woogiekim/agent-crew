"""Regression coverage for the Claude PreToolUse[Bash] guard-dangerous-commands
hook registration and the corresponding hook-system.md capability-contract fix.

Derived purely from the task spec (handoff.md / prd.md / analysis.md) for
task 20260723-123704-0 — this file intentionally never reads or executes
adapters/claude/setup.sh's logic; it only performs static regex/text
assertions against its source, mirroring the existing
tests/python/test_codex_hook_timeout_contract.py convention.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
CLAUDE_SETUP = REPO_ROOT / "adapters" / "claude" / "setup.sh"
HOOK_SYSTEM_DOC = REPO_ROOT / "core" / "rules" / "capabilities" / "hook-system.md"

# Mirrors the four-positional-argument python3-heredoc idiom already used for
# every individual PreToolUse hook registration in adapters/claude/setup.sh
# (e.g. the direct-edit-guard.sh block, adapters/claude/setup.sh:519-546):
#   python3 - "${CLAUDE_DIR}/settings.json" \
#     "${CLAUDE_DIR}/agent-crew/hooks/direct-edit-guard.sh" "Edit\|Write" "PreToolUse" <<'PYEOF'
#   ...
#   dest, hook_path, matcher, hook_type = sys.argv[1:5]
#   hook_entry = {"type": "command", "command": f"bash {hook_path}", "timeout": N}
#   ...
#   PYEOF
_HOOK_INVOCATION_RE = re.compile(
    r'python3\s+-\s+'
    r'"(?P<dest>[^"]+)"\s+'
    r'"(?P<hook_path>[^"]+)"\s+'
    r'"(?P<matcher>[^"]+)"\s+'
    r'"(?P<hook_type>[^"]+)"\s+'
    r"<<\s*'PYEOF'\n"
    r"(?P<body>.*?)"
    r"\nPYEOF",
    flags=re.DOTALL,
)


def _claude_setup_text() -> str:
    return CLAUDE_SETUP.read_text(encoding="utf-8")


def _hook_system_doc_text() -> str:
    return HOOK_SYSTEM_DOC.read_text(encoding="utf-8")


def _bash_pretooluse_blocks_for(hook_basename: str) -> list[re.Match[str]]:
    """Return every PreToolUse[Bash] invocation block registering hook_basename."""
    text = _claude_setup_text()
    return [
        match
        for match in _HOOK_INVOCATION_RE.finditer(text)
        if match.group("hook_path").endswith(hook_basename)
        and match.group("matcher") == "Bash"
        and match.group("hook_type") == "PreToolUse"
    ]


def _claude_adapter_rows() -> list[str]:
    """Return every markdown table line in hook-system.md that mentions claude.

    Adapter Examples table rows are single markdown-table lines (GFM
    convention), so a line-based scan is a sufficient, format-agnostic way to
    locate "the claude row" without assuming exact column layout.
    """
    text = _hook_system_doc_text()
    return [
        line
        for line in text.splitlines()
        if line.strip().startswith("|") and "claude" in line.lower()
    ]


# Spec: prd.md § "Acceptance Criteria" AC-001 — adapters/claude/setup.sh
# registers guard-dangerous-commands.sh as a PreToolUse hook with matcher "Bash".
def test_success_case_registers_guard_dangerous_commands_as_pretooluse_bash_hook() -> None:
    """success-case - adapters/claude/setup.sh registers guard-dangerous-commands.sh
    as a PreToolUse[Bash] hook."""
    # given: adapters/claude/setup.sh's full source text
    # when: scanned for a PreToolUse invocation whose hook_path ends in
    #       guard-dangerous-commands.sh and whose matcher is "Bash"
    sut = _bash_pretooluse_blocks_for("guard-dangerous-commands.sh")

    # then: at least one such registration block exists
    assert sut, (
        "expected adapters/claude/setup.sh to register a PreToolUse[Bash] "
        "hook invocation for guard-dangerous-commands.sh"
    )


# Spec: prd.md § "Acceptance Criteria" AC-001 — the hook entry declares
# "timeout": 5, mirroring adapters/codex/setup.sh's existing contract.
def test_success_case_guard_dangerous_commands_hook_has_explicit_timeout_five() -> None:
    """success-case - the guard-dangerous-commands.sh PreToolUse[Bash] hook
    entry declares "timeout": 5."""
    # given: the PreToolUse[Bash] block registering guard-dangerous-commands.sh
    blocks = _bash_pretooluse_blocks_for("guard-dangerous-commands.sh")
    assert blocks, "missing guard-dangerous-commands.sh PreToolUse[Bash] block"
    sut = blocks[0]

    # when: the heredoc body of that block is inspected
    body = sut.group("body")

    # then: it contains the explicit timeout=5 hook_entry field
    assert '"timeout": 5' in body


# Spec: prd.md § "Core Features" — "The registration is idempotent ... must
# not create a duplicate hook entry"; static proxy per test-checklist.md TC-003
# (also covers TC-013's idempotency intent, per the checklist's own accepted
# static-proxy note — see context/test-checklist.md).
def test_boundary_case_guard_dangerous_commands_registered_exactly_once() -> None:
    """boundary-case - guard-dangerous-commands.sh is registered exactly once
    under PreToolUse[Bash] in the static source (not zero, not duplicated)."""
    # given: adapters/claude/setup.sh's full source text
    # when: every PreToolUse[Bash] block for guard-dangerous-commands.sh is collected
    sut = _bash_pretooluse_blocks_for("guard-dangerous-commands.sh")

    # then: exactly one registration block exists
    assert len(sut) == 1, (
        "expected exactly one PreToolUse[Bash] registration block for "
        f"guard-dangerous-commands.sh, found {len(sut)}"
    )


# Spec: prd.md § "Will Do" — "Run `bash -n adapters/claude/setup.sh` as a
# syntax-validity check before and after the edit."
def test_boundary_case_claude_setup_script_remains_syntactically_valid() -> None:
    """boundary-case - adapters/claude/setup.sh remains syntactically valid
    bash after the new hook block is added."""
    # given: the current adapters/claude/setup.sh file on disk
    # when: bash -n is run against it (syntax check only, never executed)
    sut = subprocess.run(
        ["bash", "-n", str(CLAUDE_SETUP)],
        capture_output=True,
        text=True,
        check=False,
    )

    # then: it exits 0 (no syntax errors)
    assert sut.returncode == 0, sut.stderr


# Spec: handoff.md § "Constraints and cautions" — "Do not refactor, reorder,
# or change the timeout of any other existing hook-registration block."
def test_success_case_regression_pre_existing_hook_registrations_untouched() -> None:
    """success-case(regression) - pre-existing hook registrations named in the
    handoff's scope constraints remain present after the new block is added."""
    # given: adapters/claude/setup.sh's full source text
    sut = _claude_setup_text()

    # when/then: each pre-existing hook basename named in the PRD's Out-of-Scope
    # list is still present (no removal/refactor of unrelated blocks)
    for existing_hook in (
        "direct-edit-guard.sh",
        "tracker-mutation-guard.sh",
        "forbid-plaintext-approval.sh",
    ):
        assert existing_hook in sut, f"expected {existing_hook} to remain registered"


# Spec: prd.md § "Acceptance Criteria" AC-002 — the claude row no longer
# states that adapters/claude/setup.sh "wires every script under core/hooks/".
def test_success_case_regression_hook_system_doc_no_longer_overstates_claude_wiring() -> None:
    """success-case(regression) - hook-system.md's claude row no longer claims
    Claude wires every script under core/hooks/."""
    # given: the Adapter Examples table rows mentioning claude
    sut = _claude_adapter_rows()
    assert sut, "expected at least one Adapter Examples table row mentioning claude"

    # when/then: none of those rows still contain the stale overstatement
    assert not any("wires every script under" in row.lower() for row in sut), (
        "hook-system.md still claims the claude adapter wires every script "
        "under core/hooks/; AC-002 requires this stale claim to be corrected"
    )


# Spec: prd.md § "Acceptance Criteria" AC-002 — the claude row instead names
# guard-dangerous-commands.sh as a PreToolUse[Bash] hook now registered there.
def test_success_case_hook_system_doc_names_new_guard_registration() -> None:
    """success-case - hook-system.md's claude row names
    guard-dangerous-commands.sh as a registered PreToolUse[Bash] hook."""
    # given: the Adapter Examples table rows mentioning claude
    sut = _claude_adapter_rows()
    assert sut, "expected at least one Adapter Examples table row mentioning claude"

    # when/then: at least one such row names the new hook and its registration shape
    assert any(
        "guard-dangerous-commands.sh" in row
        and "pretooluse" in row.lower()
        and "bash" in row.lower()
        for row in sut
    ), (
        "expected the claude row in hook-system.md's Adapter Examples table to "
        "name guard-dangerous-commands.sh as a PreToolUse[Bash] hook"
    )


# Spec: prd.md § "Scope / Out" — "No broader rewrite of hook-system.md beyond
# the named stale claim"; lightweight regression smoke-check (see
# context/test-case-mapping.md for why this is a weak proxy, not a
# byte-identical diff, consistent with the test-writer's spec-only
# constraint against reading the file's pre-edit content).
def test_success_case_regression_other_adapter_rows_still_documented() -> None:
    """success-case(regression) - other adapter rows (e.g. codex) remain
    documented in hook-system.md after the claude row correction."""
    # given: hook-system.md's full text after the edit
    sut = _hook_system_doc_text()

    # then: the codex adapter is still documented (the table was not emptied
    # or wholesale rewritten as part of this surgical, claude-only fix)
    assert "codex" in sut.lower(), (
        "expected hook-system.md's Adapter Examples table to still document "
        "the codex adapter row after the claude row correction"
    )
