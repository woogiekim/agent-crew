"""Tests for issue #127 — read-only requests use crew:agent without the full pipeline.

Acceptance criteria from issue #127, all must hold:
  1. crew:agent remains the default path for read-only Q&A.
  2. The pipeline is NOT started for simple lookup / explanation requests.
  3. Mutating requests still route through crew:run with existing approval
     and review gates.
  4. Routing docs AND hook behavior match this split consistently.

These tests pin both directions of the routing split by invoking
`core/hooks/auto-route.sh` as a subprocess (the same harness pattern as
`test_auto_route_question_pat.py`) and asserting the emitted directive
type is ROUTE for read-only inputs and STOP for mutating inputs.

They also pin every example listed in the "Read-only vs mutating: hook
decision table" section of `core/rules/agent-routing.md` — so the docs
and the hook cannot drift independently.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
HOOK_PATH = REPO_ROOT / "core" / "hooks" / "auto-route.sh"
ROUTING_RULES_PATH = REPO_ROOT / "core" / "rules" / "agent-routing.md"


def _run_hook(prompt: str, *, bridge_configured: bool | str = True) -> dict:
    env = os.environ.copy()
    if bridge_configured:
        if isinstance(bridge_configured, str):
            env["AGENT_CREW_HOST_BRIDGE_COMMAND"] = bridge_configured
        else:
            env["AGENT_CREW_HOST_BRIDGE_COMMAND"] = "true"
    else:
        env.pop("AGENT_CREW_HOST_BRIDGE_COMMAND", None)
        env["AGENT_CREW_HOST_BRIDGE_DISABLE_DEFAULT"] = "1"

    result = subprocess.run(
        [str(HOOK_PATH)],
        input=json.dumps({"prompt": prompt}),
        text=True,
        capture_output=True,
        check=True,
        env=env,
    )
    output = result.stdout.strip()
    if not output:
        return {}
    return json.loads(output)


def _directive_type(prompt: str) -> str:
    """Return 'ROUTE', 'STOP', 'COMMAND', or 'EMPTY' for the prompt."""
    out = _run_hook(prompt)
    if not out:
        return "EMPTY"
    ctx = out["hookSpecificOutput"]["additionalContext"]
    if "[agent-crew] ROUTE" in ctx:
        return "ROUTE"
    if "[agent-crew] STOP" in ctx:
        return "STOP"
    if "[agent-crew] COMMAND" in ctx:
        return "COMMAND"
    return "OTHER"


# ---------------------------------------------------------------------------
# Acceptance criteria #1, #2: read-only Q&A routes to crew:agent (ROUTE).
# The pipeline is NOT started.
# ---------------------------------------------------------------------------

class TestReadOnlyRoutesToCrewAgent:
    """Read-only requests must emit ROUTE -> crew:agent (no pipeline spawn)."""

    def test_codebase_explanation_routes_to_agent(self):
        assert _directive_type("explain how the supervisor works") == "ROUTE"

    def test_session_history_question_routes_to_agent(self):
        assert _directive_type("what just ran in this session") == "ROUTE"

    def test_git_history_question_routes_to_agent(self):
        assert _directive_type("show me the most recent commit") == "ROUTE"

    def test_status_lookup_routes_to_agent(self):
        assert _directive_type("what are the open issues") == "ROUTE"

    def test_korean_question_routes_to_agent(self):
        assert _directive_type("어떻게 동작하나요?") == "ROUTE"

    def test_comparison_question_routes_to_agent(self):
        assert _directive_type(
            "how does crew:run differ from crew:agent?"
        ) == "ROUTE"

    def test_describe_question_routes_to_agent(self):
        assert _directive_type("describe the routing flow") == "ROUTE"

    def test_list_question_routes_to_agent(self):
        assert _directive_type("list the available agents") == "ROUTE"

    def test_bare_status_routes_to_agent(self):
        # "status" alone matches the fast-path status intent which routes
        # to historian (read-only) — still ROUTE, not STOP.
        assert _directive_type("status") == "ROUTE"

    def test_korean_diagnostic_question_routes_to_agent(self):
        assert _directive_type("왜 자꾸 안 쓰이는 거죠?") == "ROUTE"

    def test_route_directive_names_crew_agent_for_question(self):
        out = _run_hook("explain how the routing works")
        ctx = out["hookSpecificOutput"]["additionalContext"]
        assert "ROUTE_LOCK: crew-agent" in ctx
        assert 'Invoke Skill("crew-agent")' in ctx
        assert "INLINE_ANSWER: FORBIDDEN" in ctx


# ---------------------------------------------------------------------------
# Acceptance criterion #3: mutating requests route through crew:run (STOP)
# with the existing approval + review gates preserved.
# ---------------------------------------------------------------------------

class TestMutatingRoutesToCrewRun:
    """Mutating verbs must emit STOP -> crew:run.

    Regression for the issue #127 root cause: the previous fallback
    `emit_question_route("analyst", "general user request")` fired even when
    ACTION_PAT matched but no domain pattern matched. The fix tightens that
    fallback so a mutating verb without a read-only signal always lands on
    the STOP path.
    """

    def test_fix_routes_to_crew_run(self):
        assert _directive_type("fix the bug in auto-route") == "STOP"

    def test_add_routes_to_crew_run(self):
        assert _directive_type("add a new test for routing") == "STOP"

    def test_update_doc_routes_to_crew_run(self):
        assert _directive_type("update README.md to mention X") == "STOP"

    def test_commit_routes_to_crew_run(self):
        assert _directive_type("commit the staged changes") == "STOP"

    def test_rename_routes_to_crew_run(self):
        assert _directive_type("rename a variable") == "STOP"

    def test_refactor_routes_to_crew_run(self):
        assert _directive_type("refactor this function") == "STOP"

    def test_remove_routes_to_crew_run(self):
        assert _directive_type("remove the legacy alias") == "STOP"

    def test_change_routes_to_crew_run(self):
        assert _directive_type("change the default value") == "STOP"

    def test_issue_creation_routes_to_crew_run(self):
        assert _directive_type("create issue for routing gap") == "STOP"

    def test_git_push_routes_to_crew_run(self):
        assert _directive_type("push") == "STOP"

    def test_git_merge_routes_to_crew_run(self):
        assert _directive_type("merge to main") == "STOP"

    def test_korean_deploy_routes_to_crew_run(self):
        assert _directive_type("배포해주세요") == "STOP"

    def test_korean_fix_routes_to_crew_run(self):
        assert _directive_type("버그를 수정해주세요") == "STOP"

    def test_stop_directive_names_crew_run_for_mutation(self):
        out = _run_hook("fix the typo in auto-route")
        ctx = out["hookSpecificOutput"]["additionalContext"]
        assert "ROUTE_LOCK: crew-run" in ctx
        assert 'Invoke Skill("crew-run")' in ctx
        assert "INLINE_IMPLEMENTATION_OR_ANSWER: FORBIDDEN" in ctx


# ---------------------------------------------------------------------------
# Edge cases — mutating verbs paired with explicit read-only signals must
# still route to crew:agent (read-only takes precedence over verb-only
# classification). This preserves the existing behavior for diagnostic
# reviews that mention "fix" or "improve" in conditional context.
# ---------------------------------------------------------------------------

class TestReadOnlySignalOverridesMutatingVerb:
    """When a prompt mixes a mutating verb with an explicit read-only signal,
    the read-only signal wins."""

    def test_explicit_no_edit_with_mutating_verb_routes_to_agent(self):
        prompt = (
            "Inspect the routing classifier and identify gaps. "
            "Do not edit files."
        )
        assert _directive_type(prompt) == "ROUTE"

    def test_korean_read_only_marker_with_mutating_verb_routes_to_agent(self):
        prompt = (
            "라우팅 분기를 검토하고 부족한 점만 알려주세요. 수정하지 마세요."
        )
        assert _directive_type(prompt) == "ROUTE"

    def test_conditional_review_without_followup_routes_to_agent(self):
        # "review" alone (read-only audit, no follow-up execution verb)
        # still routes to crew:agent.
        prompt = "Review the routing classifier for gaps; do not edit files."
        assert _directive_type(prompt) == "ROUTE"


# ---------------------------------------------------------------------------
# Acceptance criterion #4: docs and hook behavior match.
# The "Read-only vs mutating: hook decision table" in
# core/rules/agent-routing.md is the single source of truth. Every example
# listed there must classify to the documented direction when run through
# the hook.
# ---------------------------------------------------------------------------

_DECISION_TABLE_SECTION_HEADER = "## Read-only vs mutating: hook decision table"


def _parse_decision_table_examples() -> list[tuple[str, str]]:
    """Return (prompt, expected_directive) pairs from the rule file.

    Lines under the decision-table section that look like:
        | `"prompt text"` | ROUTE | reason |
        | `"prompt text"` | STOP  | reason |
    are parsed. The prompt cell may be wrapped in backticks, double quotes,
    or both (markdown style: `"..."`). Only ROUTE and STOP rows are
    returned; header / divider rows and free-form prose are ignored.
    """
    src = ROUTING_RULES_PATH.read_text(encoding="utf-8")
    if _DECISION_TABLE_SECTION_HEADER not in src:
        return []
    section = src.split(_DECISION_TABLE_SECTION_HEADER, 1)[1]
    # Cut at the next top-level heading so we only scan this section's rows.
    section = re.split(r"\n## ", section, maxsplit=1)[0]

    rows: list[tuple[str, str]] = []
    # Accept the markdown shape `"prompt"` (backtick + double-quote pair),
    # bare `prompt`, or "prompt". The prompt body itself must not contain a
    # backtick or unescaped double quote at the boundary.
    row_pat = re.compile(
        r'^\|\s*`?"?([^`"|]+?)"?`?\s*\|\s*(ROUTE|STOP)\b',
        re.MULTILINE,
    )
    for m in row_pat.finditer(section):
        prompt = m.group(1).strip()
        expected = m.group(2)
        # Skip the table header row "Example prompt | Directive | Reason"
        if prompt.lower() in ("example prompt", "prompt"):
            continue
        rows.append((prompt, expected))
    return rows


class TestDocsAndHookMatch:
    """Every example in core/rules/agent-routing.md's decision table must
    classify to the documented direction. If a new row is added to the
    table, this test will exercise it without code changes here."""

    def test_decision_table_section_exists(self):
        src = ROUTING_RULES_PATH.read_text(encoding="utf-8")
        assert _DECISION_TABLE_SECTION_HEADER in src, (
            "core/rules/agent-routing.md must contain a "
            f"'{_DECISION_TABLE_SECTION_HEADER}' section so docs and hook "
            "stay in sync (acceptance criterion #4)."
        )

    def test_decision_table_has_at_least_one_route_and_one_stop_row(self):
        rows = _parse_decision_table_examples()
        assert any(d == "ROUTE" for _, d in rows), (
            "Decision table must include at least one ROUTE example."
        )
        assert any(d == "STOP" for _, d in rows), (
            "Decision table must include at least one STOP example."
        )

    def test_decision_table_examples_classify_correctly(self):
        rows = _parse_decision_table_examples()
        assert rows, "No decision-table rows parsed — see preceding test."
        failures: list[str] = []
        for prompt, expected in rows:
            actual = _directive_type(prompt)
            if actual != expected:
                failures.append(
                    f"prompt={prompt!r}: docs say {expected}, hook emits {actual}"
                )
        assert not failures, (
            "core/rules/agent-routing.md decision table and hook behavior "
            "are out of sync (acceptance criterion #4):\n  "
            + "\n  ".join(failures)
        )


# ---------------------------------------------------------------------------
# Regression — the existing read-only fallback for pure conversational
# prompts (no action verb, no specific domain match) must still ROUTE to
# analyst. This preserves acceptance criterion #1 (crew:agent default).
# ---------------------------------------------------------------------------

class TestNonActionConversationalStillRoutes:
    """Pure non-action conversational prompts (no mutating verb) must
    continue routing to crew:agent so crew:agent remains the default."""

    def test_bare_statement_routes_to_agent(self):
        assert _directive_type(
            "업데이트했음에도 에이전트크루를 안쓰네요"
        ) == "ROUTE"

    def test_short_korean_question_routes_to_agent(self):
        assert _directive_type("되나요?") == "ROUTE"

    def test_general_remark_routes_to_agent(self):
        # No action verb, no specific match — still ROUTE so crew:agent is
        # the default path (acceptance criterion #1).
        assert _directive_type("the docs feel inconsistent") == "ROUTE"
