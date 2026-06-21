"""Finding 2 — `script_failed` branch in capability dispatch must use
`generic-<agent>-skills` (not the wrong `base-skills-only`).

In each affected agent file, the bash capability-dispatch block has three
error branches that emit a JSON `fallback_policy` field:

  - `mv_failed`      → `generic-<agent>-skills`  (already correct)
  - `script_missing` → `generic-<agent>-skills`  (already correct)
  - `script_failed`  → `generic-<agent>-skills`  (the fix in this commit)
"""

from __future__ import annotations

import pathlib

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
AGENTS_DIR = REPO_ROOT / "core" / "agents"

AGENTS_UNDER_TEST: dict[str, str] = {
    "analyst":      "generic-analyst-skills",
    "backend":      "generic-backend-skills",
    "frontend":     "generic-frontend-skills",
    "issuer":       "generic-issuer-skills",
    "planner":      "generic-planner-skills",
    "qa-owner":     "generic-qa-owner-skills",
    "requirements": "generic-requirements-skills",
    "resolver":     "generic-resolver-skills",
    "test-writer":  "generic-test-writer-skills",
}


def _read_agent(name: str) -> str:
    return (AGENTS_DIR / f"{name}.md").read_text(encoding="utf-8")


@pytest.mark.parametrize("agent_name,expected_policy", sorted(AGENTS_UNDER_TEST.items()))
def test_script_failed_branch_uses_generic_agent_skills(
    agent_name: str, expected_policy: str
) -> None:
    text = _read_agent(agent_name)
    marker = f"capability-dispatch=script_failed agent={agent_name}"
    assert marker in text, f"{agent_name}.md missing script_failed marker"

    marker_idx = text.index(marker)
    window_start = text.rfind("printf '{", 0, marker_idx)
    assert window_start != -1, f"{agent_name}.md: no printf before marker"
    script_failed_json_line = text[window_start:marker_idx]

    assert "base-skills-only" not in script_failed_json_line, (
        f"{agent_name}.md: script_failed branch still emits base-skills-only"
    )
    expected_fragment = f'"fallback_policy":"{expected_policy}"'
    assert expected_fragment in script_failed_json_line, (
        f"{agent_name}.md: script_failed branch must emit {expected_fragment}"
    )


def test_no_residual_base_skills_only_in_audited_agents() -> None:
    offenders = [a for a in AGENTS_UNDER_TEST if "base-skills-only" in _read_agent(a)]
    assert not offenders, f"Still contain base-skills-only: {offenders}"
