"""Regression guard: no dangling feature-step/feature_step references remain.

Spec: context/prd.md AC-006 (master closing gate for the whole rename) and
context/test-checklist.md TC-014 ("a repo-wide ... grep for feature-step/
feature_step ... returns zero matches in the tracked repository"), TC-015 and
TC-016 (regression: unrelated suites and the full suite keep passing once the
old command name is gone). This test is written before the `backend` agent
performs the feature-step -> stager rename (TDD red phase); it is expected to
fail until that rename lands, since `core/commands/feature-step.md`,
`adapters/codex/skill/feature-step/`, and the registration mentions in
`core/global-agents.md`, `core/scripts/seed-instruction-rules.sh`, and
`README.md` still exist at authoring time.

Per the handoff's explicit scope: the personal, out-of-repo destination paths
(`~/.agent-crew/user/commands/stager.md`, `~/.codex/skills/stager/SKILL.md`)
are outside this repo's git working tree and are intentionally not asserted on
here (non-reproducible local machine state, same rationale as AC-004). The
stale `.crew-worktrees/20260723-123704-0/` worktree is out of scope and
excluded below, same as the other generated/vendored directories.
"""

from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
THIS_FILE = Path(__file__).resolve()

EXCLUDED_DIR_NAMES = {".git", ".crew-worktrees", "dist", "node_modules", ".pytest_cache"}

TOKENS = ("feature-step", "feature_step")

OLD_COMMAND_DOC = REPO_ROOT / "core" / "commands" / "feature-step.md"
OLD_CODEX_SKILL_DIR = REPO_ROOT / "adapters" / "codex" / "skill" / "feature-step"


def _iter_repo_files():
    for path in REPO_ROOT.rglob("*"):
        if not path.is_file():
            continue
        # Exclude this test module itself: it necessarily spells out the
        # banned tokens (as string constants and in this docstring) in order
        # to check for them, so it would otherwise never be able to pass.
        if path.resolve() == THIS_FILE:
            continue
        relative_parts = path.relative_to(REPO_ROOT).parts[:-1]
        if any(part in EXCLUDED_DIR_NAMES for part in relative_parts):
            continue
        yield path


def _find_token_matches() -> list[tuple[str, str]]:
    matches: list[tuple[str, str]] = []
    for path in _iter_repo_files():
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for token in TOKENS:
            if token in text:
                matches.append((path.relative_to(REPO_ROOT).as_posix(), token))
    return matches


def test_no_feature_step_token_references_remain_in_tracked_repo() -> None:
    matches = _find_token_matches()
    assert matches == [], f"dangling feature-step/feature_step references found: {matches}"


def test_old_feature_step_command_doc_no_longer_exists() -> None:
    assert not OLD_COMMAND_DOC.exists()


def test_old_feature_step_codex_skill_directory_no_longer_exists() -> None:
    assert not OLD_CODEX_SKILL_DIR.exists()
