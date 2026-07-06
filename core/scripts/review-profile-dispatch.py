#!/usr/bin/env python3
"""Discover skills loaded by an agent from agent-crew skill metadata.

Generalized from reviewer-only (#137) to any opted-in agent (#186).
The `--agent` flag selects which agent's `loaded_by` declaration to
match. Defaults to `reviewer` for backward compatibility with existing
callers. By default, discovery scans canonical agent-crew skill layers:
system defaults plus user extensions/overrides. Host mirrors are loading
surfaces, not policy sources.

Inputs:
  --agent NAME         Requesting agent name (default: reviewer).
                       Matched against skill frontmatter `loaded_by` lists.
  --skills-dir DIR     Skill directory to scan. Repeatable.
  --project-root DIR   Repository root used as detection context.
  --task TEXT          Normalized task or review request text.
  --changed-file PATH  Changed path to include as detection context. Repeatable.

Output:
  JSON by default, or text with --format text.

Exit codes:
  0 - discovery completed, with or without matches
  2 - malformed arguments

Examples:
  # Reviewer (backward-compatible default) using default system/user layers
  python3 review-profile-dispatch.py \
    --project-root "$PROJECT_ROOT" \
    --task "$TASK"

  # Backend / frontend dispatch using default system/user layers
  python3 review-profile-dispatch.py --agent backend \
    --project-root "$PROJECT_ROOT" \
    --task "$TASK"
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Iterable, NamedTuple


PROFILE_TYPES = {
    "review-policy",
    "review-profile",
    "review_policy",
    "review_profile",
}

STOP_WORDS = {
    "and",
    "agent",
    "agents",
    "behavior",
    "changes",
    "code",
    "for",
    "like",
    "load",
    "loaded",
    "loads",
    "policy",
    "profile",
    "repository",
    "request",
    "requests",
    "review",
    "reviewer",
    "reviews",
    "sensitive",
    "skill",
    "skills",
    "task",
    "the",
    "touch",
    "touches",
    "use",
    "user",
    "when",
    "with",
    "work",
    "works",
}

REQUIRED_DISPATCH_FIELDS = ("loaded_by", "axis", "detection")
LAYER_PRIORITY = {
    "user": 0,
    "system": 1,
    "merged": 2,
    "host_mirror": 3,
    "unknown": 4,
}
RESERVED_USER_SKILL_DOCS = {
    "changelog",
    "license",
    "readme",
    "skill-template",
}
AGENT_NAME_PREFIXES = {
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
}
PROJECT_CONTEXT_FILES = (
    "pom.xml",
    "build.gradle.kts",
    "build.gradle",
    "package.json",
    "pyproject.toml",
    "setup.py",
    "Cargo.toml",
    "go.mod",
    "build.sbt",
    "Package.swift",
)
PROJECT_CONTEXT_FILE_LIMIT = 50_000


class ContextFragment(NamedTuple):
    text: str
    tokens: set[str]
    project_context_file: str = ""


def strip_scalar(value: str) -> str:
    value = value.strip()
    if value in {">", "|"}:
        return ""
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1].strip()
    return value


def parse_frontmatter(text: str) -> dict[str, str]:
    if not text.startswith("---"):
        return {}

    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}

    frontmatter: list[str] = []
    for line in lines[1:]:
        if line.strip() == "---":
            break
        frontmatter.append(line)
    else:
        return {}

    data: dict[str, str] = {}
    current_key = ""
    for line in frontmatter:
        if not line.strip():
            continue

        if line.startswith((" ", "\t")) and current_key:
            continuation = line.strip()
            if continuation.startswith("- "):
                continuation = continuation[2:].strip()
                separator = "," if data.get(current_key) else ""
                data[current_key] = f"{data.get(current_key, '')}{separator}{continuation}"
            else:
                separator = " " if data.get(current_key) else ""
                data[current_key] = f"{data.get(current_key, '')}{separator}{continuation}"
            continue

        match = re.match(r"^([A-Za-z_][A-Za-z0-9_-]*):\s*(.*)$", line)
        if not match:
            current_key = ""
            continue

        current_key = match.group(1).strip().replace("-", "_")
        data[current_key] = strip_scalar(match.group(2))

    return data


def split_list(value: str) -> list[str]:
    cleaned = value.strip().strip("[]")
    parts = re.split(r"[,;|\s]+", cleaned)
    return [part.strip().strip("'\"") for part in parts if part.strip().strip("'\"")]


def metadata_value(metadata: dict[str, str], *keys: str) -> str:
    for key in keys:
        normalized = key.replace("-", "_")
        if metadata.get(normalized):
            return metadata[normalized]
    return ""


def metadata_has_key(metadata: dict[str, str], *keys: str) -> bool:
    return any(key.replace("-", "_") in metadata for key in keys)


def loaded_by(metadata: dict[str, str], agent_name: str) -> tuple[bool, list[str]]:
    """Return (is_loaded_by_agent, raw loaded_by list) for the given agent."""
    loaded = split_list(metadata_value(metadata, "loaded_by", "loaded-by"))
    lowered = [entry.lower() for entry in loaded]

    return agent_name.lower() in lowered, loaded


# Backward-compatible alias retained for external callers that imported the
# reviewer-specific helper before #186 generalized the dispatcher.
def loaded_by_reviewer(metadata: dict[str, str]) -> tuple[bool, list[str]]:
    return loaded_by(metadata, "reviewer")


def _qualifies_for_agent(metadata: dict[str, str], agent_name: str) -> bool:
    """Apply the per-agent qualification rule AFTER `loaded_by` has been
    checked by the caller.

    For `reviewer`, the legacy review-profile contract is preserved
    (`profile_type` or detection + "review" keyword). For every other
    agent, qualifying solely on the `loaded_by` declaration is
    sufficient — the `detection` clause is then applied separately to
    filter by context. Splitting this from `is_loaded_by()` lets the
    discovery loop call `loaded_by()` exactly once per skill
    (finding [11]).
    """
    if agent_name.lower() != "reviewer":
        return True

    profile_type = metadata_value(
        metadata,
        "profile_type",
        "profile-type",
        "contract",
        "kind",
        "type",
    ).lower()
    if profile_type in PROFILE_TYPES:
        return True

    legacy_contract = " ".join(
        metadata_value(metadata, key)
        for key in ("name", "description", "axis", "detection")
    ).lower()

    if metadata_value(metadata, "detection"):
        return "review" in legacy_contract
    # Reviewer empty-detection path (finding [2]): accept the skill on
    # the `loaded_by: reviewer` declaration alone. The match is then
    # attributed via the legacy `global-review-profile` matched_by
    # token in `_matched_by_for()`.
    return True


def is_loaded_by(metadata: dict[str, str], agent_name: str) -> bool:
    """Return True when the skill metadata qualifies for the given agent.

    Backward-compatible wrapper retained for callers that imported the
    helper before #186 refactored `discover_skills_for_agent()` to
    parse `loaded_by` exactly once per skill (finding [11]).
    """
    agent_loaded, _loaded = loaded_by(metadata, agent_name)
    if not agent_loaded:
        return False
    return _qualifies_for_agent(metadata, agent_name)


def is_review_profile(metadata: dict[str, str]) -> bool:
    """Backward-compatible alias for callers pre-#186."""
    return is_loaded_by(metadata, "reviewer")


def normalize_text(text: str) -> str:
    return " ".join(re.findall(r"[A-Za-z0-9]+", text.lower()))


PROJECT_CONTEXT_FILE_TOKENS = {normalize_text(path) for path in PROJECT_CONTEXT_FILES}
PROJECT_CONTEXT_FILE_TOKENS_BY_LENGTH = sorted(
    PROJECT_CONTEXT_FILE_TOKENS,
    key=len,
    reverse=True,
)


def token_set(text: str) -> set[str]:
    return set(normalize_text(text).split())


def significant_tokens(text: str) -> list[str]:
    tokens = token_set(text)
    return sorted(
        token
        for token in tokens
        if len(token) >= 4 and token not in STOP_WORDS
    )


def context_fragment(text: str, *, project_context_file: str = "") -> ContextFragment:
    normalized = normalize_text(text)
    return ContextFragment(
        text=normalized,
        tokens=set(normalized.split()),
        project_context_file=normalize_text(project_context_file),
    )


def project_context_file_for_path(path_text: str) -> str:
    normalized = normalize_text(path_text)
    for file_token in PROJECT_CONTEXT_FILE_TOKENS_BY_LENGTH:
        if normalized == file_token or normalized.endswith(f" {file_token}"):
            return file_token

    return ""


def project_context_file_clause_parts(clause: str) -> tuple[str, str]:
    normalized = normalize_text(clause)
    for file_token in PROJECT_CONTEXT_FILE_TOKENS_BY_LENGTH:
        if normalized == file_token:
            return file_token, ""
        if normalized.startswith(f"{file_token} "):
            remainder = normalized.removeprefix(file_token).strip()
            for prefix in ("containing ", "contains ", "with "):
                if remainder.startswith(prefix):
                    remainder = remainder.removeprefix(prefix).strip()
                    break

            return file_token, remainder

    return "", ""


def project_context_file_family(file_token: str) -> str:
    if file_token in {"build gradle", "build gradle kts"}:
        return "gradle"

    return file_token


def expand_manifest_family_qualifiers(clauses: list[str]) -> list[str]:
    """Apply old shorthand qualifiers across sibling manifest OR clauses."""
    qualifiers_by_family: dict[str, set[str]] = {}
    for clause in clauses:
        file_token, remainder = project_context_file_clause_parts(clause)
        if not file_token or not remainder:
            continue
        family = project_context_file_family(file_token)
        qualifiers_by_family.setdefault(family, set()).add(remainder)

    inherited_qualifier = {
        family: next(iter(qualifiers))
        for family, qualifiers in qualifiers_by_family.items()
        if len(qualifiers) == 1
    }

    expanded: list[str] = []
    for clause in clauses:
        file_token, remainder = project_context_file_clause_parts(clause)
        if file_token and not remainder:
            qualifier = inherited_qualifier.get(project_context_file_family(file_token))
            if qualifier:
                expanded.append(f"{file_token} with {qualifier}")
                continue

        expanded.append(clause)

    return expanded


def is_project_context_file_clause(clause: str) -> bool:
    file_token, _ = project_context_file_clause_parts(clause)
    return bool(file_token)


def negated_clause(clause: str) -> str:
    normalized = normalize_text(clause)
    if not normalized.startswith("not "):
        return ""

    return normalized.removeprefix("not ").strip()


def strict_fragment_clause_matches(clause: str, fragment: ContextFragment) -> bool:
    """Match manifest-file qualifiers without loose "any token" fallback."""
    and_parts = [
        part.strip()
        for part in re.split(r"\s+AND\s+", clause, flags=re.IGNORECASE)
        if part.strip()
    ]
    if len(and_parts) > 1:
        return all(strict_fragment_clause_matches(part, fragment) for part in and_parts)

    if negative_clause := negated_clause(clause):
        return not strict_fragment_clause_matches(negative_clause, fragment)

    normalized_clause = normalize_text(clause)
    if normalized_clause and normalized_clause in fragment.text:
        return True

    tokens = significant_tokens(clause)
    if not tokens:
        return False

    return all(token in fragment.tokens or token in fragment.text for token in tokens)


def project_context_file_clause_matches(
    normalized_clause: str,
    *,
    context_text: str,
    context_fragments: list[ContextFragment] | None,
    current_fragment: ContextFragment | None,
) -> bool:
    file_token, remainder = project_context_file_clause_parts(normalized_clause)

    if current_fragment:
        if not file_token:
            if current_fragment.project_context_file:
                return normalized_clause == current_fragment.project_context_file

            return normalized_clause == current_fragment.text
        if current_fragment.project_context_file != file_token:
            return False
        if not remainder:
            return True

        return strict_fragment_clause_matches(remainder, current_fragment)

    if context_fragments:
        return any(
            project_context_file_clause_matches(
                normalized_clause,
                context_text=fragment.text,
                context_fragments=None,
                current_fragment=fragment,
            )
            for fragment in context_fragments
        )

    if file_token:
        return normalized_clause == context_text

    return normalized_clause == context_text


def clause_matches(
    clause: str,
    context_text: str,
    context_tokens: set[str],
    context_fragments: list[ContextFragment] | None = None,
    current_fragment: ContextFragment | None = None,
) -> bool:
    and_parts = [
        part.strip()
        for part in re.split(r"\s+AND\s+", clause, flags=re.IGNORECASE)
        if part.strip()
    ]
    if len(and_parts) > 1:
        if context_fragments and any(
            is_project_context_file_clause(part) for part in and_parts
        ):
            return any(
                all(
                    clause_matches(
                        part,
                        fragment.text,
                        fragment.tokens,
                        current_fragment=fragment,
                    )
                    for part in and_parts
                )
                for fragment in context_fragments
            )
        return all(
            clause_matches(part, context_text, context_tokens, context_fragments)
            for part in and_parts
        )

    normalized_clause = normalize_text(clause)
    if negative_clause := negated_clause(clause):
        return not clause_matches(
            negative_clause,
            context_text,
            context_tokens,
            context_fragments,
            current_fragment,
        )

    if normalized_clause and is_project_context_file_clause(clause):
        return project_context_file_clause_matches(
            normalized_clause,
            context_text=context_text,
            context_fragments=context_fragments,
            current_fragment=current_fragment,
        )

    if normalized_clause and normalized_clause in context_text:
        return True
    if re.search(r"[./_-]", clause.strip()) and not re.search(r"\s", clause.strip()):
        return False

    tokens = significant_tokens(clause)
    if not tokens:
        return False

    def token_present(token: str) -> bool:
        return token in context_tokens or token in context_text

    if "/" in clause:
        return any(token_present(token) for token in tokens)

    if len(tokens) <= 2:
        return all(token_present(token) for token in tokens)

    return any(token_present(token) for token in tokens)


def detection_matches(
    detection: str,
    context_text: str,
    context_tokens: set[str],
    context_fragments: list[ContextFragment] | None = None,
) -> bool:
    detection = detection.strip()
    if not detection:
        return True

    # Accept three alternation forms in detection strings:
    #   `OR` — explicit word, used by long-prose detection clauses
    #   `||` — shell-style double-pipe
    #   `|`  — regex-style single-pipe (`cleanup|refactor|dead.code|unused`)
    # All three split the detection into independent OR-clauses; a match
    # on ANY clause qualifies the skill.
    clauses = re.split(r"\bOR\b|\|\|?", detection, flags=re.IGNORECASE)
    clauses = expand_manifest_family_qualifiers(clauses)

    return any(
        clause_matches(clause, context_text, context_tokens, context_fragments)
        for clause in clauses
    )


def default_skill_dirs() -> list[Path]:
    home = Path(os.environ.get("AGENT_CREW_HOME", Path.home() / ".agent-crew"))

    return [home / "system" / "skills", home / "user" / "skills"]


def project_context_fragments(project_root: Path) -> list[ContextFragment]:
    fragments: list[ContextFragment] = []

    for relative_path in PROJECT_CONTEXT_FILES:
        path = project_root / relative_path
        if not path.is_file():
            continue

        content = ""
        try:
            content = path.read_text(encoding="utf-8", errors="replace")[
                :PROJECT_CONTEXT_FILE_LIMIT
            ]
        except OSError:
            pass

        fragments.append(
            context_fragment(
                f"{relative_path}\n{content}",
                project_context_file=relative_path,
            )
        )

    return fragments


def build_context(
    project_root: Path,
    task: str,
    changed_files: Iterable[str],
) -> tuple[str, set[str], list[ContextFragment]]:
    searchable_fragments = [
        context_fragment(str(project_root)),
        context_fragment(project_root.name),
        context_fragment(task),
        *(
            context_fragment(
                path,
                project_context_file=project_context_file_for_path(path),
            )
            for path in changed_files
        ),
    ]
    context_fragments = [
        *searchable_fragments,
        *project_context_fragments(project_root),
    ]
    context_text = " ".join(fragment.text for fragment in searchable_fragments)

    return context_text, set(context_text.split()), context_fragments


def iter_skill_files(skills_dirs: Iterable[Path]) -> Iterable[Path]:
    seen: set[Path] = set()
    for skills_dir in skills_dirs:
        if not skills_dir.is_dir():
            continue
        for path in sorted(skills_dir.glob("*.md")):
            resolved = path.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            yield path


def classify_skill_layer(path: Path) -> str:
    parts = path.expanduser().parts
    text = str(path.expanduser())
    normalized = text.replace("\\", "/")

    if "/user/skills/" in normalized or (
        len(parts) >= 3 and parts[-3:-1] == ("user", "skills")
    ):
        return "user"
    if (
        "/system/skills/" in normalized
        or "/system/agents/skills/" in normalized
        or "/core/agents/skills/" in normalized
        or (len(parts) >= 3 and parts[-3:-1] == ("system", "skills"))
    ):
        return "system"
    if (
        "/.claude/agent-crew/skills/" in normalized
        or "/.claude/agent-crew/agents/skills/" in normalized
        or "/.codex/skills/agent-crew/" in normalized
        or "/.codex/agent-crew/skills/" in normalized
    ):
        return "host_mirror"
    if "/.agent-crew/skills/" in normalized or (
        len(parts) >= 2 and parts[-2] == "skills"
    ):
        return "merged"
    return "unknown"


def missing_dispatch_fields(metadata: dict[str, str]) -> list[str]:
    missing: list[str] = []
    if "loaded_by" in REQUIRED_DISPATCH_FIELDS and not metadata_value(
        metadata, "loaded_by", "loaded-by"
    ):
        missing.append("loaded_by")
    if "axis" in REQUIRED_DISPATCH_FIELDS and not metadata_value(metadata, "axis"):
        missing.append("axis")
    # An explicit empty detection key is valid and means "global for this agent".
    if "detection" in REQUIRED_DISPATCH_FIELDS and not metadata_has_key(
        metadata, "detection"
    ):
        missing.append("detection")
    return missing


def build_unindexed_skill(path: Path, metadata: dict[str, str], layer: str) -> dict:
    return {
        "name": metadata_value(metadata, "name") or path.stem,
        "path": str(path),
        "layer": layer,
        "missing_fields": missing_dispatch_fields(metadata),
        "reason": "missing dispatch metadata",
    }


def agent_prefix_for_stem(stem: str) -> str:
    lowered = stem.lower()
    for prefix in sorted(AGENT_NAME_PREFIXES, key=len, reverse=True):
        if lowered == prefix or lowered.startswith(f"{prefix}-"):
            return prefix
    return ""


def looks_like_explicit_invocation_skill(text: str) -> bool:
    """Detect host/user command skills that should not become agent gaps."""
    lowered = text.lower()
    if "$" not in lowered:
        return False

    return any(
        marker in lowered
        for marker in (
            "explicitly writes",
            "explicitly invokes",
            "user invokes",
            "command shapes",
            "slash command",
        )
    )


def descriptor_matches_context(
    descriptor: str,
    context_text: str,
    context_tokens: set[str],
) -> bool:
    tokens = significant_tokens(descriptor)
    if not tokens:
        return True

    return any(token in context_tokens or token in context_text for token in tokens)


def first_markdown_heading(text: str) -> str:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            return stripped.lstrip("#").strip()

    return ""


def unindexed_user_skill_applies_to_agent(
    path: Path,
    metadata: dict[str, str],
    text: str,
    *,
    agent_name: str,
    context_text: str,
    context_tokens: set[str],
    context_fragments: list[ContextFragment],
) -> bool:
    """Return whether an incomplete user skill should be surfaced as a gap.

    The gap list is framework-computed decision context, not a required
    evidence artifact. Keep it task-scoped: directory docs, explicit command
    skills, and another agent's adapter should not dilute the current agent's
    coverage score.
    """
    stem = path.stem.lower()
    if stem in RESERVED_USER_SKILL_DOCS:
        return False

    agent_lower = agent_name.lower()
    loaded = [
        entry.lower()
        for entry in split_list(metadata_value(metadata, "loaded_by", "loaded-by"))
    ]
    if loaded and agent_lower not in loaded:
        return False

    prefix = agent_prefix_for_stem(stem)
    if prefix and prefix != agent_lower:
        return False

    if not metadata and not prefix and looks_like_explicit_invocation_skill(text):
        return False

    if metadata_has_key(metadata, "detection"):
        return detection_matches(
            metadata_value(metadata, "detection"),
            context_text,
            context_tokens,
            context_fragments,
        )

    if metadata:
        descriptor = " ".join(
            [
                path.stem,
                metadata_value(metadata, "name"),
                metadata_value(metadata, "description"),
                metadata_value(metadata, "axis"),
            ]
        )
        return descriptor_matches_context(descriptor, context_text, context_tokens)

    descriptor = " ".join([path.stem, first_markdown_heading(text)])
    descriptor_tokens = significant_tokens(descriptor)
    if not descriptor_tokens:
        return False

    return any(
        token in context_tokens or token in context_text
        for token in descriptor_tokens
    )


def _matched_by_for(agent_name: str, detection: str) -> str:
    """Return the canonical `matched_by` label for a skill match.

    - When the skill has a non-empty `detection` clause, the match is
      attributed to detection.
    - For the reviewer empty-detection case, the historical `#137`
      legacy literal `global-review-profile` is preserved (finding [2])
      so pre-#186 consumers keying on that token continue to work.
    - For every other agent's empty-detection case, the generalized
      `global-<agent>-skill` form is used.
    """
    if detection:
        return "detection"
    if agent_name.lower() == "reviewer":
        return "global-review-profile"
    return f"global-{agent_name.lower()}-skill"


def resolve_skills_for_agent(
    skills_dirs: Iterable[Path],
    *,
    agent_name: str,
    project_root: Path,
    task: str,
    changed_files: Iterable[str],
) -> dict:
    context_text, context_tokens, context_fragments = build_context(
        project_root,
        task,
        changed_files,
    )
    candidates: list[dict] = []
    unindexed_user_skills: list[dict] = []

    for path in iter_skill_files(skills_dirs):
        text = path.read_text(encoding="utf-8", errors="replace")
        metadata = parse_frontmatter(text)
        layer = classify_skill_layer(path)
        missing_fields = missing_dispatch_fields(metadata)
        if layer == "user" and missing_fields:
            if unindexed_user_skill_applies_to_agent(
                path,
                metadata,
                text,
                agent_name=agent_name,
                context_text=context_text,
                context_tokens=context_tokens,
                context_fragments=context_fragments,
            ):
                unindexed_user_skills.append(build_unindexed_skill(path, metadata, layer))
            continue

        # Finding [11]: compute the parsed `loaded_by` list once at the
        # top of the loop body, then thread the qualification check
        # through it. Previously `is_loaded_by()` re-parsed the
        # frontmatter (via `loaded_by()`) and then the loop body called
        # `loaded_by()` a second time to retrieve the same list.
        agent_loaded, loaded_list = loaded_by(metadata, agent_name)
        if not agent_loaded:
            continue
        if not _qualifies_for_agent(metadata, agent_name):
            continue

        detection = metadata_value(metadata, "detection")
        if not detection_matches(
            detection,
            context_text,
            context_tokens,
            context_fragments,
        ):
            continue

        candidates.append(
            {
                "name": metadata_value(metadata, "name") or path.stem,
                "path": str(path),
                "layer": layer,
                "axis": metadata_value(metadata, "axis"),
                "loaded_by": loaded_list,
                "detection": detection,
                "matched_by": _matched_by_for(agent_name, detection),
            }
        )

    matched: list[dict] = []
    duplicate_resolved: list[dict] = []
    by_name: dict[str, list[dict]] = {}
    for candidate in candidates:
        by_name.setdefault(candidate["name"], []).append(candidate)

    for name, group in sorted(by_name.items()):
        ordered = sorted(
            group,
            key=lambda item: (
                LAYER_PRIORITY.get(item["layer"], LAYER_PRIORITY["unknown"]),
                item["path"],
            ),
        )
        selected = ordered[0]
        matched.append(selected)
        for shadowed in ordered[1:]:
            duplicate_resolved.append(
                {
                    "name": name,
                    "selected_path": selected["path"],
                    "selected_layer": selected["layer"],
                    "shadowed_path": shadowed["path"],
                    "shadowed_layer": shadowed["layer"],
                    "reason": "same skill name resolved by layer precedence",
                }
            )

    matched.sort(key=lambda item: (item["name"], item["path"]))
    duplicate_resolved.sort(key=lambda item: (item["name"], item["shadowed_path"]))
    unindexed_user_skills.sort(key=lambda item: (item["name"], item["path"]))

    indexed_count = len(candidates)
    total_discovered = indexed_count + len(unindexed_user_skills)
    discovery_coverage = (
        100 if total_discovered == 0 else round(indexed_count * 100 / total_discovered)
    )
    known_gaps = [
        {
            "id": f"unindexed_user_skill:{item['name']}",
            "type": "unindexed_user_skill",
            "severity": "medium",
            "agent": agent_name,
            "skill": item["name"],
            "layer": item["layer"],
            "path": item["path"],
            "reason": item["reason"],
            "impact": "skill may not be selected automatically",
            "recommended_action": "add loaded_by/axis/detection metadata or leave it as manual guidance",
            "deferrable": True,
        }
        for item in unindexed_user_skills
    ]

    return {
        "matched": matched,
        "duplicate_resolved": duplicate_resolved,
        "unindexed_user_skills": unindexed_user_skills,
        "decision_context": {
            "source": "framework_computed",
            "artifact_required": False,
            "coverage": {
                "skill_discovery": discovery_coverage,
                "skill_resolution": 100,
            },
            "known_gaps": known_gaps,
        },
    }


def discover_skills_for_agent(
    skills_dirs: Iterable[Path],
    *,
    agent_name: str,
    project_root: Path,
    task: str,
    changed_files: Iterable[str],
) -> list[dict]:
    return resolve_skills_for_agent(
        skills_dirs,
        agent_name=agent_name,
        project_root=project_root,
        task=task,
        changed_files=changed_files,
    )["matched"]


# Backward-compatible alias for pre-#186 callers.
def discover_review_profiles(
    skills_dirs: Iterable[Path],
    *,
    project_root: Path,
    task: str,
    changed_files: Iterable[str],
) -> list[dict]:
    return discover_skills_for_agent(
        skills_dirs,
        agent_name="reviewer",
        project_root=project_root,
        task=task,
        changed_files=changed_files,
    )


def fallback_policy_for(agent_name: str) -> str:
    """Return the canonical fallback-policy string for a given agent.

    Finding [13]: the reviewer-only `generic-review-skills` (singular)
    asymmetry is retired. Every agent — including reviewer — now follows
    the uniform `generic-<agent>-skills` rule.
    """
    return f"generic-{agent_name.lower()}-skills"


def build_fallback_payload(agent_name: str, reason: str) -> dict:
    """Build the canonical degraded-state JSON payload.

    Used by both the in-process `build_payload()` (for normal happy-path
    emissions where `fallback=False`) and the new `--emit-fallback`
    mode (finding [9]). The latter lets the shared
    `core/scripts/capability-dispatch.sh` helper reuse this single
    canonical computation instead of carrying hand-written
    `generic-<agent>-skills` JSON literals across every agent .md file.
    """
    return {
        "agent": agent_name,
        "matched": [],
        "duplicate_resolved": [],
        "unindexed_user_skills": [],
        "fallback": True,
        "fallback_policy": fallback_policy_for(agent_name),
        "reason": reason,
        "decision_context": {
            "source": "framework_computed",
            "artifact_required": False,
            "coverage": {
                "skill_discovery": 0,
                "skill_resolution": 0,
            },
            "known_gaps": [
                {
                    "id": f"capability_dispatch:{reason}",
                    "type": "capability_dispatch_degraded",
                    "severity": "medium",
                    "agent": agent_name,
                    "reason": reason,
                    "impact": "capability skills were not resolved; agent should continue with declared base skills",
                    "recommended_action": "inspect dispatcher availability only if this affects task quality",
                    "deferrable": True,
                }
            ],
        },
    }


def build_payload(args: argparse.Namespace) -> dict:
    skills_dirs = [Path(path).expanduser() for path in args.skills_dir] or default_skill_dirs()
    resolved = resolve_skills_for_agent(
        skills_dirs,
        agent_name=args.agent,
        project_root=Path(args.project_root).expanduser(),
        task=args.task,
        changed_files=args.changed_file,
    )

    return {
        "agent": args.agent,
        "matched": resolved["matched"],
        "duplicate_resolved": resolved["duplicate_resolved"],
        "unindexed_user_skills": resolved["unindexed_user_skills"],
        # Per the 3-state dispatch result spec (see
        # core/rules/agent-tool-dispatch.md § "Metadata-driven skill dispatch"),
        # zero-match is the NORMAL state when no user-owned capability skills are
        # installed for this agent — it is NOT a degraded/fallback condition.
        # `fallback=True` is reserved for the degraded paths (script missing /
        # script failed), which are emitted as a fallback JSON report by the
        # agents' dispatch blocks, not by this happy-path entry point.
        "fallback": False,
        "fallback_policy": fallback_policy_for(args.agent),
        "decision_context": resolved["decision_context"],
    }


def print_text(payload: dict) -> None:
    agent_name = payload.get("agent", "reviewer")
    if payload["matched"]:
        label = "review_profile" if agent_name == "reviewer" else f"{agent_name}_skill"
        for match in payload["matched"]:
            print(f"{label}: {match['name']} path={match['path']}")
        return

    # Finding [6]: zero-match is the NORMAL state under the 3-state
    # dispatch model (see `core/rules/agent-tool-dispatch.md` §
    # "Metadata-driven skill dispatch"). It is NOT a degraded condition
    # and MUST emit the canonical `CAPABILITY_SKILLS: none agent=<name>`
    # token — the prior `DEGRADED ...=none` token conflated zero-match
    # with the script_failed degraded state.
    print(f"[crew] CAPABILITY_SKILLS: none agent={agent_name}")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Discover skills loaded by an agent via frontmatter metadata."
    )
    parser.add_argument(
        "--agent",
        default="reviewer",
        help="Requesting agent name (default: reviewer for backward compatibility).",
    )
    parser.add_argument("--skills-dir", action="append", default=[])
    parser.add_argument("--project-root", default=".")
    parser.add_argument("--task", default="")
    parser.add_argument("--changed-file", action="append", default=[])
    parser.add_argument("--format", choices=("json", "text"), default="json")
    # Finding [9]: emit-only mode for degraded paths. When set, the
    # dispatcher skips discovery entirely and prints the canonical
    # fallback JSON payload for the (agent, reason) pair. This is what
    # `core/scripts/capability-dispatch.sh` invokes from its degraded
    # branches so the 39 hand-written fallback literals across the 13
    # agent .md files collapse into one canonical computation.
    parser.add_argument(
        "--emit-fallback",
        default=None,
        metavar="REASON",
        help=(
            "Emit the canonical fallback JSON payload for the given "
            "reason (script_missing|script_failed|mv_failed) and exit. "
            "Skips discovery entirely."
        ),
    )

    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])

    if args.emit_fallback is not None:
        payload = build_fallback_payload(args.agent, args.emit_fallback)
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0

    payload = build_payload(args)

    if args.format == "json":
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print_text(payload)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
