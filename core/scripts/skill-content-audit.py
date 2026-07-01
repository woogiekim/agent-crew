#!/usr/bin/env python3
"""Audit agent skill inventory and high-value content-depth contracts."""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


IMPLEMENTATION_AGENTS = ("backend", "frontend", "test-writer", "reviewer")

EFFECTIVE_JAVA_REQUIRED_TERMS = [
    "Item 17",
    "Item 50",
    "Item 54",
    "Collections.emptyMap()",
    "Collections.emptyList()",
    "Collections.emptySet()",
    "List.of()",
    "Map.of()",
    "Set.of()",
    "read-only fallback collection",
    "new HashMap<Long, String>()",
]

FOLLOWUP_CATEGORIES = {
    "empty-or-default-values": ("empty", "default", "fallback"),
    "immutability-shareability": ("immutable", "immutability", "read-only", "readonly"),
    "defensive-copy-or-aliasing": ("defensive cop", "copy", "alias"),
    "review-triggers": ("review", "checklist", "trigger"),
}

REQUIRED_SECTIONS = (
    "Source",
    "When to Apply",
    "Core Rules",
    "Anti-Patterns",
    "References",
)


@dataclass(frozen=True)
class MatrixEntry:
    consumers: list[str]
    mandatory: list[str]


@dataclass(frozen=True)
class SkillLayout:
    root: Path
    skills_dir: Path
    agents_dir: Path
    agent_skill_loading: Path


def _candidate_layouts(script_path: Path) -> list[SkillLayout]:
    candidates: list[SkillLayout] = []

    # Source checkout: {repo}/core/scripts/skill-content-audit.py
    if len(script_path.parents) >= 3:
        root = script_path.parents[2]
        candidates.append(
            SkillLayout(
                root=root,
                skills_dir=root / "core" / "agents" / "skills",
                agents_dir=root / "core" / "agents",
                agent_skill_loading=root / "core" / "rules" / "agent-skill-loading.md",
            )
        )

    # Installed system copy: ~/.agent-crew/system/scripts/skill-content-audit.py
    if len(script_path.parents) >= 2:
        root = script_path.parents[1]
        candidates.append(
            SkillLayout(
                root=root,
                skills_dir=root / "agents" / "skills",
                agents_dir=root / "agents",
                agent_skill_loading=root / "rules" / "agent-skill-loading.md",
            )
        )

    # Installed compatibility copy: ~/.agent-crew/scripts/skill-content-audit.py
    if len(script_path.parents) >= 2:
        root = script_path.parents[1]
        candidates.append(
            SkillLayout(
                root=root,
                skills_dir=root / "system" / "agents" / "skills",
                agents_dir=root / "system" / "agents",
                agent_skill_loading=root / "system" / "rules" / "agent-skill-loading.md",
            )
        )

    return candidates


def _resolve_layout(script_path: Path | None = None) -> SkillLayout:
    path = script_path or Path(__file__).resolve()
    for layout in _candidate_layouts(path):
        if layout.skills_dir.is_dir():
            return layout

    fallback = _candidate_layouts(path)[0]
    return fallback


LAYOUT = _resolve_layout()
REPO_ROOT = LAYOUT.root
SKILLS_DIR = LAYOUT.skills_dir
AGENTS_DIR = LAYOUT.agents_dir
AGENT_SKILL_LOADING = LAYOUT.agent_skill_loading


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _extract_section(text: str, heading: str) -> str:
    marker = f"## {heading}"
    start = text.find(marker)
    if start < 0:
        return ""

    rest = text[start + len(marker) :]
    match = re.search(r"\n##\s+", rest)
    if not match:
        return rest.strip()

    return rest[: match.start()].strip()


def _source_lines(text: str) -> list[str]:
    section = _extract_section(text, "Source")
    return [
        line[2:].strip()
        for line in section.splitlines()
        if line.strip().startswith("- ")
    ]


def _rule_count(text: str) -> int:
    return len(re.findall(r"^### Rule\s+[0-9]+", text, flags=re.MULTILINE))


def _checklist_markers(text: str) -> int:
    lowered = text.lower()
    checklist_items = len(
        re.findall(r"^\s*-\s+\[[ xX]\]", text, re.MULTILINE)
    )

    return lowered.count("checklist") + checklist_items


def _missing_required_sections(text: str) -> list[str]:
    missing: list[str] = []
    for section in REQUIRED_SECTIONS:
        if f"## {section}" not in text:
            missing.append(section)

    return missing


def _parse_matrix() -> dict[str, MatrixEntry]:
    if not AGENT_SKILL_LOADING.is_file():
        return {}

    entries: dict[str, MatrixEntry] = {}
    for line in _read(AGENT_SKILL_LOADING).splitlines():
        if not line.startswith("| `"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) < 5:
            continue

        skill = cells[0].strip("`")
        if not skill.endswith(".md"):
            continue

        consumers: list[str] = []
        mandatory: list[str] = []
        for agent, value in zip(IMPLEMENTATION_AGENTS, cells[1:5]):
            normalized = value.lower()
            if value == "MANDATORY":
                consumers.append(agent)
                mandatory.append(agent)
            elif normalized == "yes":
                consumers.append(agent)

        entries[skill] = MatrixEntry(consumers=consumers, mandatory=mandatory)

    return entries


def _declared_agent_refs() -> dict[str, list[str]]:
    refs: dict[str, set[str]] = {}
    pattern = re.compile(r"`(?:~/.agent-crew/system/agents/skills/|core/agents/skills/)([^`/]+\.md)`")
    for agent in IMPLEMENTATION_AGENTS:
        path = AGENTS_DIR / f"{agent}.md"
        if not path.is_file():
            continue
        for skill in pattern.findall(_read(path)):
            refs.setdefault(skill, set()).add(agent)

    return {skill: sorted(agents) for skill, agents in refs.items()}


def _inventory() -> list[dict[str, object]]:
    matrix = _parse_matrix()
    refs = _declared_agent_refs()
    rows: list[dict[str, object]] = []

    for path in sorted(SKILLS_DIR.glob("*.md")):
        text = _read(path)
        entry = matrix.get(path.name, MatrixEntry(consumers=[], mandatory=[]))
        consumers = sorted(set(entry.consumers) | set(refs.get(path.name, [])))
        rows.append(
            {
                "file": path.name,
                "consuming_agents": consumers,
                "mandatory_agents": entry.mandatory,
                "declared_sources": _source_lines(text),
                "missing_required_sections": _missing_required_sections(text),
                "rule_count": _rule_count(text),
                "checklist_markers": _checklist_markers(text),
            }
        )

    return rows


def _effective_followups() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for path in sorted(SKILLS_DIR.glob("effective-*.md")):
        text = _read(path)
        lowered = text.lower()
        missing = [
            category
            for category, terms in FOLLOWUP_CATEGORIES.items()
            if not any(term in lowered for term in terms)
        ]
        rows.append(
            {
                "file": path.name,
                "missing_categories": missing,
                "follow_up": (
                    "No immediate gap from the generic rubric."
                    if not missing
                    else "Add concrete guidance for: " + ", ".join(missing)
                ),
            }
        )

    return rows


def _content_contracts() -> dict[str, dict[str, object]]:
    java_text = _read(SKILLS_DIR / "effective-java.md")
    missing = [term for term in EFFECTIVE_JAVA_REQUIRED_TERMS if term not in java_text]
    return {
        "effective-java.md": {
            "required_terms": EFFECTIVE_JAVA_REQUIRED_TERMS,
            "missing": missing,
            "passed": not missing,
        }
    }


def _shallow_findings(inventory: list[dict[str, object]]) -> list[dict[str, object]]:
    findings: list[dict[str, object]] = []
    for row in inventory:
        if row["file"] == "SKILL-TEMPLATE.md":
            continue

        reasons: list[str] = []
        if row["missing_required_sections"]:
            reasons.append(
                "missing required sections: "
                + ", ".join(row["missing_required_sections"])
            )
        if int(row["rule_count"]) < 5 and int(row["checklist_markers"]) < 5:
            reasons.append("low rule count and low checklist marker count")

        if reasons:
            findings.append(
                {
                    "file": row["file"],
                    "reasons": reasons,
                    "recommendation": (
                        "Review content depth before relying on this skill for "
                        "implementation or approval decisions."
                    ),
                }
            )

    return findings


def build_payload() -> dict[str, object]:
    inventory = _inventory()
    return {
        "inventory": inventory,
        "effective_followups": _effective_followups(),
        "content_contracts": _content_contracts(),
        "shallow_findings": _shallow_findings(inventory),
    }


def _markdown_table(headers: Iterable[str], rows: Iterable[Iterable[object]]) -> str:
    header_list = list(headers)
    output = [
        "| " + " | ".join(header_list) + " |",
        "| " + " | ".join("---" for _ in header_list) + " |",
    ]
    for row in rows:
        output.append("| " + " | ".join(str(value) for value in row) + " |")
    return "\n".join(output)


def to_markdown(payload: dict[str, object]) -> str:
    inventory = payload["inventory"]
    followups = payload["effective_followups"]
    contracts = payload["content_contracts"]
    shallow_findings = payload["shallow_findings"]

    inventory_rows = [
        (
            row["file"],
            ", ".join(row["consuming_agents"]) or "-",
            ", ".join(row["mandatory_agents"]) or "-",
            row["rule_count"],
            row["checklist_markers"],
        )
        for row in inventory
    ]
    followup_rows = [
        (
            row["file"],
            ", ".join(row["missing_categories"]) or "-",
            row["follow_up"],
        )
        for row in followups
    ]
    contract_rows = [
        (
            name,
            "PASS" if data["passed"] else "FAIL",
            ", ".join(data["missing"]) or "-",
        )
        for name, data in contracts.items()
    ]
    shallow_rows = [
        (
            row["file"],
            "<br>".join(row["reasons"]),
            row["recommendation"],
        )
        for row in shallow_findings
    ]

    return "\n\n".join(
        [
            "# Skill Content Depth Audit",
            "Generated by `python3 core/scripts/skill-content-audit.py --format markdown`.",
            "## Inventory",
            _markdown_table(
                ["Skill", "Consumers", "Mandatory For", "Rule Count", "Checklist Markers"],
                inventory_rows,
            ),
            "## Effective Skill Follow-Ups",
            _markdown_table(["Skill", "Generic Rubric Gaps", "Follow-Up"], followup_rows),
            "## Content Contracts",
            _markdown_table(["Skill", "Status", "Missing Terms"], contract_rows),
            "## Shallow Content Findings",
            _markdown_table(["Skill", "Reason", "Recommendation"], shallow_rows),
        ]
    ) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--format", choices=("json", "markdown"), default="json")
    parser.add_argument("--output", type=Path, help="Optional path to write the report.")
    args = parser.parse_args()

    payload = build_payload()
    if args.format == "json":
        output = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    else:
        output = to_markdown(payload)

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output, encoding="utf-8")
    else:
        print(output, end="")

    contract_failed = any(
        not data["passed"]
        for data in payload["content_contracts"].values()
    )
    return 1 if contract_failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
