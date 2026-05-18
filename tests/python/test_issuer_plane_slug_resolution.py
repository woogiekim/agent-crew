"""Smoke tests for the Plane adapter workspace-slug resolution rule.

Issue #36: workspace slug must be resolved from input parameter or
environment variable only — never from the mcp__plane__list_projects
API response, which returns a UUID-style ``id`` field rather than the
human-readable slug.

These tests verify:
1. The UUID-rejection guard (no UUID-shaped value is a valid slug).
2. The resolution priority: input param wins over env var.
3. The rule text in the installed skill file explicitly forbids API derivation.
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Optional

import pytest


# ---------------------------------------------------------------------------
# UUID detection helper — mirrors the guard an adapter should apply
# ---------------------------------------------------------------------------

UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


def is_uuid(value: str) -> bool:
    """Return True if *value* looks like a UUID (8-4-4-4-12 hex groups)."""
    return bool(UUID_RE.match(value))


def resolve_workspace_slug(
    input_param: Optional[str] = None,
    env_var: Optional[str] = None,
) -> str:
    """Resolve PLANE_WORKSPACE_SLUG using the priority order defined in
    the issuer-plane adapter spec (issue #36 fix):

      1. ``PLANE_WORKSPACE_SLUG`` / ``WORKSPACE_SLUG`` input parameter
      2. ``PLANE_WORKSPACE_SLUG`` environment variable
      3. Raise ValueError if still absent

    A UUID-shaped value is always rejected regardless of source, because
    the Plane API returns internal UUIDs in its workspace.id field, NOT
    the human-readable slug.
    """
    slug: Optional[str] = None

    # Priority 1: explicit input parameter
    if input_param:
        slug = input_param

    # Priority 2: environment variable fallback
    if slug is None and env_var:
        slug = env_var

    if slug is None:
        raise ValueError(
            "PLANE_WORKSPACE_SLUG is required. "
            "Provide it as input or set the environment variable."
        )

    # Guard: reject UUID-shaped values regardless of source.
    # The list_projects response includes workspace.id (UUID) — passing
    # that as workspace_slug would break every subsequent API call.
    if is_uuid(slug):
        raise ValueError(
            f"PLANE_WORKSPACE_SLUG must be a human-readable slug, "
            f"not a UUID. Got: {slug!r}. "
            f"Tip: use the PLANE_WORKSPACE_SLUG env var or pass the slug "
            f"explicitly as an input parameter."
        )

    return slug


# ---------------------------------------------------------------------------
# Tests: UUID detection
# ---------------------------------------------------------------------------

class TestUUIDDetection:
    """Verify the UUID guard catches API-response IDs."""

    def test_standard_uuid_is_detected(self):
        assert is_uuid("550e8400-e29b-41d4-a716-446655440000") is True

    def test_uppercase_uuid_is_detected(self):
        assert is_uuid("550E8400-E29B-41D4-A716-446655440000") is True

    def test_mixed_case_uuid_is_detected(self):
        assert is_uuid("550e8400-E29B-41d4-A716-446655440000") is True

    def test_human_readable_slug_is_not_uuid(self):
        assert is_uuid("my-org") is False

    def test_slug_with_digits_is_not_uuid(self):
        assert is_uuid("acme-2024") is False

    def test_empty_string_is_not_uuid(self):
        assert is_uuid("") is False

    def test_partial_uuid_is_not_uuid(self):
        # Missing groups — not a full UUID
        assert is_uuid("550e8400-e29b-41d4") is False

    def test_slug_resembling_uuid_prefix_is_not_uuid(self):
        # Has hyphens but wrong structure
        assert is_uuid("abc-def-ghi-jkl") is False


# ---------------------------------------------------------------------------
# Tests: resolution priority — input param wins over env var
# ---------------------------------------------------------------------------

class TestSlugResolutionPriority:
    """Verify input parameter takes precedence over env var."""

    def test_input_param_wins_over_env_var(self):
        slug = resolve_workspace_slug(
            input_param="my-org",
            env_var="other-org",
        )
        assert slug == "my-org"

    def test_env_var_used_when_no_input(self):
        slug = resolve_workspace_slug(
            input_param=None,
            env_var="my-org",
        )
        assert slug == "my-org"

    def test_raises_when_both_absent(self):
        with pytest.raises(ValueError, match="PLANE_WORKSPACE_SLUG is required"):
            resolve_workspace_slug(input_param=None, env_var=None)

    def test_empty_input_falls_through_to_env_var(self):
        # Falsy input (empty string) is treated as absent → use env var.
        slug = resolve_workspace_slug(input_param="", env_var="my-org")
        assert slug == "my-org"


# ---------------------------------------------------------------------------
# Tests: UUID rejection — no UUID-shaped value ever becomes workspace_slug
# ---------------------------------------------------------------------------

class TestUUIDRejection:
    """Assert that UUID-shaped values are always rejected as workspace slugs.

    These are the values the Plane API returns in the workspace.id field of
    the list_projects response. If an adapter naively uses that field as the
    workspace_slug, the UUID guard must catch it.
    """

    def test_uuid_from_input_param_is_rejected(self):
        uuid_val = "550e8400-e29b-41d4-a716-446655440000"
        with pytest.raises(ValueError, match="human-readable slug"):
            resolve_workspace_slug(input_param=uuid_val)

    def test_uuid_from_env_var_is_rejected(self):
        uuid_val = "550e8400-e29b-41d4-a716-446655440000"
        with pytest.raises(ValueError, match="human-readable slug"):
            resolve_workspace_slug(input_param=None, env_var=uuid_val)

    def test_uuid_never_appears_in_workspace_slug_field(self):
        """Regression guard: simulate what happens if an adapter incorrectly
        uses the API response's workspace.id as the slug.

        The API response shape (from mcp__plane__list_projects):
          {"results": [{"id": "<uuid>", "name": "...", ...}]}

        An adapter must NOT do: workspace_slug = response["results"][0]["id"]
        """
        # Simulate the API response
        api_response_workspace_id = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
        assert is_uuid(api_response_workspace_id), \
            "Precondition: API response contains a UUID id field"

        # Attempting to use it as workspace_slug must fail
        with pytest.raises(ValueError, match="human-readable slug"):
            resolve_workspace_slug(input_param=api_response_workspace_id)

    def test_valid_slugs_are_accepted(self):
        """Positive cases: common human-readable slug formats."""
        valid_slugs = [
            "my-org",
            "acme",
            "acme-2024",
            "team-alpha",
            "org123",
        ]
        for slug in valid_slugs:
            result = resolve_workspace_slug(input_param=slug)
            assert result == slug, f"Expected {slug!r} to be accepted"


# ---------------------------------------------------------------------------
# Tests: skill file contains the "Do NOT" rule (installed path check)
# ---------------------------------------------------------------------------

class TestSkillFileContainsRule:
    """Verify the installed issuer-plane.md skill file explicitly forbids
    deriving the slug from the API response.

    This test is skipped when the skill file is not installed (e.g. in CI
    environments that only have the repo checkout, not a full agent-crew
    install). The hermetic unit tests above cover the logic; this is an
    integration smoke check against the live installed file.
    """

    SKILL_PATH = Path.home() / ".agent-crew" / "user" / "skills" / "issuer-plane.md"

    @pytest.mark.skipif(
        not (Path.home() / ".agent-crew" / "user" / "skills" / "issuer-plane.md").exists(),
        reason="issuer-plane.md not installed at ~/.agent-crew/user/skills/",
    )
    def test_skill_forbids_api_derivation(self):
        """The slug-resolution rule in the installed skill must contain an
        explicit prohibition against deriving the slug from the API response.
        """
        text = self.SKILL_PATH.read_text(encoding="utf-8")
        assert "Do NOT attempt to derive the slug from any API response" in text, (
            f"Expected issuer-plane.md to contain the 'Do NOT derive from API' rule. "
            f"File: {self.SKILL_PATH}"
        )

    @pytest.mark.skipif(
        not (Path.home() / ".agent-crew" / "user" / "skills" / "issuer-plane.md").exists(),
        reason="issuer-plane.md not installed at ~/.agent-crew/user/skills/",
    )
    def test_skill_specifies_input_then_env_priority(self):
        """The 'Input resolution priority' section in the skill file must list
        the input parameter BEFORE the environment variable.
        """
        text = self.SKILL_PATH.read_text(encoding="utf-8")

        # Isolate the "Input resolution priority" block — search within it
        # rather than the whole document to avoid false matches from the
        # free-text description section which mentions env var first.
        priority_marker = "Input resolution priority"
        marker_pos = text.find(priority_marker)
        assert marker_pos != -1, (
            f"Expected issuer-plane.md to contain an '{priority_marker}' "
            f"section. File: {self.SKILL_PATH}"
        )

        # Extract up to 400 chars after the marker — enough for the list
        priority_block = text[marker_pos : marker_pos + 400]

        input_pos = priority_block.find("input parameter")
        env_pos = priority_block.find("environment variable")

        assert input_pos != -1, (
            "Priority block must mention 'input parameter'"
        )
        assert env_pos != -1, (
            "Priority block must mention 'environment variable'"
        )
        assert input_pos < env_pos, (
            "Input parameter must appear BEFORE env variable in the "
            f"'{priority_marker}' block.\n"
            f"Block text:\n{priority_block}"
        )
