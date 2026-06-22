"""Regression coverage for capability-skill on-disk layout.

These tests lock in the structural invariants documented in PRD
acceptance criteria for finding [1] (dead-code-elimination skill
location) and finding [8] (shared `capability-dispatch.sh` helper):

* `core/agents/skills/dead-code-elimination.md` MUST NOT exist at the
  top of the discovery dir. It auto-loads on every backend/frontend
  refactor task when present there, which is the HIGH-severity bug
  finding [1] addresses.
* `core/agents/skills/templates/dead-code-elimination.md` MUST exist
  as the copy-if-absent seed (per the PRD's "Contract: dead-code-
  elimination not auto-loaded" section).
* `core/scripts/capability-dispatch.sh` MUST exist, MUST be
  executable, and each of the 13 dispatch-enabled agent `.md` files
  MUST invoke it (per the PRD's "Contract: shared script" section,
  finding [8]).
* Each of the 13 dispatch-enabled agent `.md` files MUST also carry
  the rule-mandated post-dispatch citation form referencing
  `context/skill-use.json` (per the PRD's "Contract: post-dispatch
  citation" section, finding [4]).
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
# Finding [1] — dead-code-elimination must live under templates/
# ---------------------------------------------------------------------------


def test_failure_case_dead_code_skill_not_in_discovery_dir() -> None:
    """failure-case: dead-code-elimination MUST NOT live at the top of
    `core/agents/skills/` — that path is `crew:update`'s discovery dir
    and would auto-load the skill on every backend/frontend refactor
    task (finding [1] HIGH).
    """
    assert not DEAD_CODE_DISCOVERY_PATH.exists(), (
        f"{DEAD_CODE_DISCOVERY_PATH} must NOT exist — it would auto-load "
        "framework-wide. The skill lives under templates/ as a "
        "copy-if-absent seed (finding [1])."
    )


def test_success_case_dead_code_skill_lives_under_templates() -> None:
    """success-case: the templates copy of dead-code-elimination must
    exist so adopters can opt in via crew:update's seed flow."""
    assert DEAD_CODE_TEMPLATE_PATH.is_file(), (
        f"{DEAD_CODE_TEMPLATE_PATH} must exist as the copy-if-absent "
        "seed for the dead-code-elimination capability skill (finding [1])."
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
# Finding [4] — unified post-dispatch citation form
# ---------------------------------------------------------------------------


def test_success_case_dispatch_agents_cite_skill_use_json() -> None:
    """success-case: each of the 13 dispatch-enabled agents must carry
    the rule-mandated post-dispatch citation form referencing
    `context/skill-use.json` (per `core/rules/agent-tool-dispatch.md`
    state 3) — see finding [4]. Drift across the agent .md files was
    the original defect."""
    missing: list[str] = []
    for agent in DISPATCH_ENABLED_AGENTS:
        agent_file = REPO_ROOT / "core" / "agents" / f"{agent}.md"
        text = agent_file.read_text(encoding="utf-8")
        if "context/skill-use.json" not in text:
            missing.append(
                f"{agent_file} must cite `context/skill-use.json` in its "
                "post-dispatch instruction block (finding [4])"
            )
    assert not missing, "\n".join(missing)
