"""Finding 2 — `script_failed` branch in capability dispatch must use
`generic-<agent>-skills` (not the wrong `base-skills-only`).

Historical context: the 13 agent .md files used to carry an inline
~30-line capability-dispatch bash block with hand-written JSON
literals. Finding [8] (shared `capability-dispatch.sh` helper) and
finding [9] (`--emit-fallback` mode on `review-profile-dispatch.py`)
collapsed those literals into one canonical computation. The same
invariant — script_failed → `generic-<agent>-skills` — must still hold,
but is now verified against the shared shell helper and the Python
dispatcher rather than against the per-agent .md files.
"""

from __future__ import annotations

import importlib.util
import json
import pathlib
import subprocess

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
CAPABILITY_DISPATCH = REPO_ROOT / "core" / "scripts" / "capability-dispatch.sh"
DISPATCH_SCRIPT = REPO_ROOT / "core" / "scripts" / "review-profile-dispatch.py"

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


def _load_module(path: pathlib.Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    "agent_name,expected_policy", sorted(AGENTS_UNDER_TEST.items())
)
def test_script_failed_branch_uses_generic_agent_skills(
    agent_name: str, expected_policy: str
) -> None:
    """The shared `capability-dispatch.sh` helper now owns the script_failed
    branch. It calls `python3 review-profile-dispatch.py --agent <name>
    --emit-fallback script_failed`, which must produce a payload whose
    `fallback_policy` is exactly `generic-<agent>-skills`."""
    result = subprocess.run(
        [
            "python3",
            str(DISPATCH_SCRIPT),
            "--agent",
            agent_name,
            "--emit-fallback",
            "script_failed",
        ],
        text=True,
        capture_output=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["fallback_policy"] == expected_policy, (
        f"--emit-fallback script_failed --agent {agent_name} must produce "
        f"fallback_policy={expected_policy!r}; got "
        f"{payload['fallback_policy']!r}"
    )
    assert payload["fallback"] is True
    assert payload["reason"] == "script_failed"


def test_no_residual_base_skills_only_in_audited_agents() -> None:
    """Sanity: the legacy wrong token `base-skills-only` MUST NOT appear
    anywhere in the source repo. The replacement chain
    `capability-dispatch.sh → review-profile-dispatch.py --emit-fallback`
    has no path that emits the legacy token."""
    fallback_module = _load_module(
        DISPATCH_SCRIPT, "review_profile_dispatch_fallback"
    )
    for agent in AGENTS_UNDER_TEST:
        policy = fallback_module.fallback_policy_for(agent)
        assert "base-skills-only" not in policy
    helper_text = CAPABILITY_DISPATCH.read_text(encoding="utf-8")
    assert "base-skills-only" not in helper_text
