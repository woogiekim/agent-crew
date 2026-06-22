#!/usr/bin/env python3
"""Discover skills loaded by an agent from user-owned metadata.

Generalized from reviewer-only (#137) to any opted-in agent (#186).
The `--agent` flag selects which agent's `loaded_by` declaration to
match. Defaults to `reviewer` for backward compatibility with existing
callers.

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
  # Reviewer (backward-compatible default)
  python3 review-profile-dispatch.py \
    --skills-dir ~/.agent-crew/user/skills \
    --project-root "$PROJECT_ROOT" \
    --task "$TASK"

  # Backend / frontend dispatch
  python3 review-profile-dispatch.py --agent backend \
    --skills-dir ~/.agent-crew/user/skills \
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
from typing import Iterable


PROFILE_TYPES = {
    "review-policy",
    "review-profile",
    "review_policy",
    "review_profile",
}

STOP_WORDS = {
    "and",
    "behavior",
    "changes",
    "code",
    "for",
    "like",
    "policy",
    "profile",
    "repository",
    "request",
    "requests",
    "review",
    "reviewer",
    "reviews",
    "sensitive",
    "task",
    "the",
    "touch",
    "touches",
    "user",
    "with",
}


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


def token_set(text: str) -> set[str]:
    return set(normalize_text(text).split())


def significant_tokens(text: str) -> list[str]:
    tokens = token_set(text)
    return sorted(
        token
        for token in tokens
        if len(token) >= 4 and token not in STOP_WORDS
    )


def clause_matches(clause: str, context_text: str, context_tokens: set[str]) -> bool:
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


def detection_matches(detection: str, context_text: str, context_tokens: set[str]) -> bool:
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

    return any(clause_matches(clause, context_text, context_tokens) for clause in clauses)


def default_skill_dirs() -> list[Path]:
    home = Path(os.environ.get("AGENT_CREW_HOME", Path.home() / ".agent-crew"))

    return [home / "user" / "skills", home / "skills"]


def build_context(project_root: Path, task: str, changed_files: Iterable[str]) -> tuple[str, set[str]]:
    parts = [str(project_root), project_root.name, task, *changed_files]
    context_text = normalize_text(" ".join(parts))

    return context_text, set(context_text.split())


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


def discover_skills_for_agent(
    skills_dirs: Iterable[Path],
    *,
    agent_name: str,
    project_root: Path,
    task: str,
    changed_files: Iterable[str],
) -> list[dict]:
    context_text, context_tokens = build_context(project_root, task, changed_files)
    matches: list[dict] = []

    for path in iter_skill_files(skills_dirs):
        text = path.read_text(encoding="utf-8", errors="replace")
        metadata = parse_frontmatter(text)
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
        if not detection_matches(detection, context_text, context_tokens):
            continue

        matches.append(
            {
                "name": metadata_value(metadata, "name") or path.stem,
                "path": str(path),
                "axis": metadata_value(metadata, "axis"),
                "loaded_by": loaded_list,
                "detection": detection,
                "matched_by": _matched_by_for(agent_name, detection),
            }
        )

    return sorted(matches, key=lambda item: (item["name"], item["path"]))


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
        "fallback": True,
        "fallback_policy": fallback_policy_for(agent_name),
        "reason": reason,
    }


def build_payload(args: argparse.Namespace) -> dict:
    skills_dirs = [Path(path).expanduser() for path in args.skills_dir] or default_skill_dirs()
    matches = discover_skills_for_agent(
        skills_dirs,
        agent_name=args.agent,
        project_root=Path(args.project_root).expanduser(),
        task=args.task,
        changed_files=args.changed_file,
    )

    return {
        "agent": args.agent,
        "matched": matches,
        # Per the 3-state dispatch result spec (see
        # core/rules/agent-tool-dispatch.md § "Metadata-driven skill dispatch"),
        # zero-match is the NORMAL state when no user-owned capability skills are
        # installed for this agent — it is NOT a degraded/fallback condition.
        # `fallback=True` is reserved for the degraded paths (script missing /
        # script failed), which are emitted as a fallback JSON report by the
        # agents' dispatch blocks, not by this happy-path entry point.
        "fallback": False,
        "fallback_policy": fallback_policy_for(args.agent),
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
