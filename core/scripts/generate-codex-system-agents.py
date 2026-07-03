#!/usr/bin/env python3
"""Generate Codex TOML stubs for agent-crew system agents."""
from __future__ import annotations

import argparse
import os
import re
from pathlib import Path


SKIP = {
    "README.md",
    "supervisor-bootstrap.md",
    "supervisor-stages.md",
    "supervisor-retry.md",
}

REASONING_MAP = {
    "xhigh": "xhigh",
    "deep": "high",
    "balanced": "medium",
    "light": "low",
}

MODEL_MAP = {
    "xhigh": "claude-fable-5",
    "deep": "claude-opus-4-8",
    "balanced": "claude-sonnet-5",
    "light": "claude-haiku-4-5",
}


def parse_frontmatter(text: str) -> dict[str, str]:
    fm: dict[str, str] = {}
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n", text, re.DOTALL)
    if not match:
        return fm

    for line in match.group(1).splitlines():
        kv = re.match(r"^(\w[\w_-]*):\s*(.*)", line)
        if not kv:
            continue
        key, value = kv.group(1), kv.group(2).strip().strip("\"'")
        if value in (">", "|", ">-", "|-"):
            value = ""
        fm[key] = value

    return fm


def toml_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"""', '""\\"')


def toml_name_for(name: str, fallback: str) -> str:
    return re.sub(r"[^\w-]", "-", name.lower()).strip("-") or fallback


def render_toml(source_path: Path, source_ref: str | None = None) -> tuple[str, str]:
    text = source_path.read_text(encoding="utf-8")
    fm = parse_frontmatter(text)
    fallback = source_path.stem
    name = fm.get("name") or fallback
    toml_name = toml_name_for(name, fallback)
    description = (fm.get("description") or f"Agent-crew system agent: {name}").strip()
    description = re.sub(r"\s+", " ", description).lstrip("> ").strip()
    tier = (fm.get("reasoning_tier") or "balanced").strip()
    effort = REASONING_MAP.get(tier, REASONING_MAP["balanced"])
    model = MODEL_MAP.get(tier, MODEL_MAP["balanced"])
    canonical_ref = source_ref or str(source_path)

    instructions = f"""# {name}

This is a Codex adapter bootstrap for the agent-crew system agent.

Before doing any work:
1. Read `{canonical_ref}`.
2. Follow that file as the authoritative agent definition.
3. If that file references sibling modules or skills, read them from the paths it specifies.
4. Keep all state and artifact writes exactly where the caller's prompt says.

    Do not use the abbreviated TOML bootstrap as the behavioral source of truth.
"""

    desc_escaped = description.replace("\\", "\\\\").replace('"', '\\"')
    content = (
        f'description = "{desc_escaped}"\n'
        f'model = "{model}"\n'
        f'model_reasoning_effort = "{effort}"\n'
        f'developer_instructions = """\n{toml_escape(instructions.rstrip())}\n"""\n'
        f'name = "{toml_name}"\n'
    )
    return toml_name, content


def generate(source_dir: Path, dest_dir: Path, source_ref_root: str | None = None) -> int:
    dest_dir.mkdir(parents=True, exist_ok=True)
    converted = 0

    for source_path in sorted(source_dir.iterdir()):
        if source_path.suffix != ".md" or source_path.name in SKIP:
            continue
        ref = None
        if source_ref_root:
            ref = str(Path(source_ref_root) / source_path.name)
        toml_name, content = render_toml(source_path, ref)
        (dest_dir / f"{toml_name}.toml").write_text(content, encoding="utf-8")
        converted += 1

    return converted


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_dir")
    parser.add_argument("dest_dir")
    parser.add_argument(
        "--source-ref-root",
        help="Path root to embed in generated bootstrap instructions instead of source_dir.",
    )
    args = parser.parse_args()

    source_dir = Path(args.source_dir)
    if not source_dir.is_dir():
        raise SystemExit(f"source_dir not found: {source_dir}")

    converted = generate(source_dir, Path(args.dest_dir), args.source_ref_root)
    print(f"[generate-codex-system-agents] {converted} system agent(s) converted to TOML in {args.dest_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
