"""Regression coverage for capability-skill on-disk layout.

These tests lock in the structural invariants documented in PRD
acceptance criteria for the dead-code-elimination system-skill
reversal of finding [1] and finding [8] (shared
`capability-dispatch.sh` helper):

* `core/agents/skills/dead-code-elimination.md` MUST exist at the top
  of the discovery dir. It is the single explicit exception to the
  user-opt-in-only capability-skill rule: a low-risk pre-deletion
  safety checklist that the framework ships as a system-wide default
  and the dispatcher auto-matches for backend/frontend on
  refactor/cleanup tasks via its `loaded_by` / `detection` frontmatter.
* `core/agents/skills/templates/dead-code-elimination.md` MUST NOT
  exist — the `git mv` reversal removes the seed copy in favor of the
  framework-default discovery-path location.
* `core/scripts/capability-dispatch.sh` MUST exist, MUST be
  executable, and each of the 13 dispatch-enabled agent `.md` files
  MUST invoke it (per the PRD's "Contract: shared script" section,
  finding [8]).
* Each of the 13 dispatch-enabled agent `.md` files MUST treat the
  dispatch report as framework-computed decision context, not as a
  reason to synthesize proof artifacts such as `context/skill-use.json`.
"""

from __future__ import annotations

import os
import stat
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SKILLS_DIR = REPO_ROOT / "core" / "agents" / "skills"
TEMPLATES_DIR = SKILLS_DIR / "templates"
DEAD_CODE_DISCOVERY_PATH = SKILLS_DIR / "dead-code-elimination.md"
DEAD_CODE_TEMPLATE_PATH = TEMPLATES_DIR / "dead-code-elimination.md"
CAPABILITY_DISPATCH_SCRIPT = REPO_ROOT / "core" / "scripts" / "capability-dispatch.sh"

DISPATCH_ENABLED_AGENTS = (
    "analyst",
    "backend",
    "designer",
    "devops",
    "documenter",
    "frontend",
    "issuer",
    "planner",
    "qa-owner",
    "requirements",
    "resolver",
    "reviewer",
    "test-writer",
)


# ---------------------------------------------------------------------------
# dead-code-elimination ships as a framework-default system skill
#
# Deliberate reversal of finding [1]: the skill lives at the top of the
# discovery dir so the dispatcher auto-matches it for backend/frontend
# on refactor/cleanup tasks. The PRD documents this as the single
# explicit exception to the user-opt-in-only capability-skill rule.
# ---------------------------------------------------------------------------


def test_success_case_dead_code_skill_is_framework_default_system_skill() -> None:
    """success-case: dead-code-elimination MUST live at the top of
    `core/agents/skills/` — that path is `crew:update`'s discovery dir
    and the dispatcher auto-matches the skill from its frontmatter for
    every backend/frontend refactor/cleanup task. This is the single
    explicit exception to the user-opt-in-only capability-skill rule
    (see the "Exception" subsection in
    `core/rules/agent-tool-dispatch.md`).
    """
    assert DEAD_CODE_DISCOVERY_PATH.is_file(), (
        f"{DEAD_CODE_DISCOVERY_PATH} must exist at the top of the "
        "discovery dir — dead-code-elimination ships system-wide as a "
        "framework default so the dispatcher auto-matches it for "
        "backend/frontend on refactor/cleanup tasks."
    )


def test_failure_case_dead_code_skill_no_longer_seeded_under_templates() -> None:
    """failure-case: the templates/ seed copy of dead-code-elimination
    MUST NOT exist. The `git mv` reversal moves the file out of
    templates/ and into the discovery dir; leaving a stale copy under
    templates/ would create a duplicate-source surface that drifts from
    the framework-default file.
    """
    assert not DEAD_CODE_TEMPLATE_PATH.exists(), (
        f"{DEAD_CODE_TEMPLATE_PATH} must NOT exist — the skill now ships "
        "as a framework default at the discovery-dir location; the "
        "templates/ seed copy was removed by the `git mv` reversal."
    )


# ---------------------------------------------------------------------------
# Finding [8] — shared capability-dispatch.sh helper
# ---------------------------------------------------------------------------


def test_success_case_capability_dispatch_script_exists_and_is_executable() -> None:
    """success-case: the shared shell helper must exist and be
    executable so every agent's dispatch block can invoke it (finding [8])."""
    assert CAPABILITY_DISPATCH_SCRIPT.is_file(), (
        f"{CAPABILITY_DISPATCH_SCRIPT} must exist (finding [8] — extract "
        "the ~30-line duplicated dispatch block into a shared helper)."
    )
    mode = CAPABILITY_DISPATCH_SCRIPT.stat().st_mode
    assert mode & stat.S_IXUSR, (
        f"{CAPABILITY_DISPATCH_SCRIPT} must be executable (chmod +x); "
        f"current mode={oct(mode)}"
    )


def test_success_case_dispatch_agents_invoke_shared_helper() -> None:
    """success-case: each of the 13 dispatch-enabled agents must invoke
    the shared shell helper (finding [8]) rather than embedding a
    duplicate ~30-line bash block."""
    missing: list[str] = []
    for agent in DISPATCH_ENABLED_AGENTS:
        agent_file = REPO_ROOT / "core" / "agents" / f"{agent}.md"
        text = agent_file.read_text(encoding="utf-8")
        # Accept either bare path or `core/scripts/capability-dispatch.sh`
        # invocation; the agent must reference the shared helper script
        # by name so the dispatch block is no longer copy-pasted.
        if "capability-dispatch.sh" not in text:
            missing.append(f"{agent_file} does not invoke capability-dispatch.sh")
    assert not missing, "\n".join(missing)


# ---------------------------------------------------------------------------
# Finding [4] — computed decision context, not proof artifacts
# ---------------------------------------------------------------------------


def test_success_case_dispatch_agents_use_decision_context_not_skill_use_proof() -> None:
    """success-case: each of the 13 dispatch-enabled agents must treat
    capability dispatch as computed decision context, not a synthetic proof
    artifact contract."""
    missing: list[str] = []
    for agent in DISPATCH_ENABLED_AGENTS:
        agent_file = REPO_ROOT / "core" / "agents" / f"{agent}.md"
        text = agent_file.read_text(encoding="utf-8")
        if "decision_context" not in text:
            missing.append(
                f"{agent_file} must mention `decision_context` in its "
                "post-dispatch instruction block"
            )
        if "already appended" in text or "citation entry per matched skill" in text:
            missing.append(
                f"{agent_file} still describes dispatch as a skill-use proof "
                "artifact"
            )
    assert not missing, "\n".join(missing)
