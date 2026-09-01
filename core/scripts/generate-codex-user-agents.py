#!/usr/bin/env python3
"""Materialize agent-crew user agents as ownership-marked Codex TOML agents."""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


MANAGED_MARKER = "# This is a Codex adapter bootstrap for an agent-crew user agent."


def parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    frontmatter: dict[str, str] = {}
    body = text
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)", text, re.DOTALL)
    if not match:
        return frontmatter, body

    body = match.group(2)
    for line in match.group(1).splitlines():
        key_value = re.match(r"^(\w[\w_-]*):\s*(.*)", line)
        if not key_value:
            continue
        key, value = key_value.group(1), key_value.group(2).strip().strip("\"'")
        if value in (">", "|", ">-", "|-"):
            value = ""
        frontmatter[key] = value

    return frontmatter, body


def codex_agent_name(name: str) -> str:
    return re.sub(r"[^\w-]", "-", name.lower()).strip("-") or "unknown"


def source_agent_name(path: Path) -> str:
    try:
        frontmatter, _body = parse_frontmatter(path.read_text(encoding="utf-8"))
    except OSError:
        return path.stem
    return frontmatter.get("name") or path.stem


def toml_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"""', '""\\"')


def render_toml(source_path: Path) -> tuple[str, str, str]:
    text = source_path.read_text(encoding="utf-8")
    frontmatter, body = parse_frontmatter(text)
    name = frontmatter.get("name") or source_path.stem
    description = (frontmatter.get("description") or f"User agent: {name}").strip()
    description = description.lstrip("> ").strip()
    model = (frontmatter.get("model") or "").strip()
    model_reasoning_effort = (frontmatter.get("model_reasoning_effort") or "").strip()
    sandbox_mode = (frontmatter.get("sandbox_mode") or "").strip()
    nickname_candidates = (frontmatter.get("nickname_candidates") or "").strip()
    if model.lower() == "inherit":
        model = ""

    toml_name = codex_agent_name(name)
    description_escaped = description.replace("\\", "\\\\").replace('"', '\\"')
    lines = [
        MANAGED_MARKER,
        f'name = "{toml_name}"',
        f'description = "{description_escaped}"',
    ]
    for key, value in (
        ("model", model),
        ("model_reasoning_effort", model_reasoning_effort),
        ("sandbox_mode", sandbox_mode),
    ):
        if value:
            escaped = value.replace("\\", "\\\\").replace('"', '\\"')
            lines.append(f'{key} = "{escaped}"')
    if nickname_candidates:
        if nickname_candidates.startswith("[") and nickname_candidates.endswith("]"):
            lines.append(f"nickname_candidates = {nickname_candidates}")
        else:
            names = [
                value.strip().strip("\"'")
                for value in nickname_candidates.split(",")
                if value.strip()
            ]
            encoded = ", ".join(
                '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'
                for value in names
            )
            lines.append(f"nickname_candidates = [{encoded}]")
    lines.append(f'developer_instructions = """\n{toml_escape(body.rstrip())}\n"""')
    managed_content = "\n".join(lines) + "\n"
    legacy_content = "\n".join(lines[1:]) + "\n"
    return toml_name, managed_content, legacy_content


def system_agent_names(system_agents_dir: Path | None) -> set[str]:
    if system_agents_dir is None or not system_agents_dir.is_dir():
        return set()

    names = set()
    for source_path in sorted(system_agents_dir.glob("*.md")):
        if source_path.name.lower() == "readme.md":
            continue
        names.add(codex_agent_name(source_agent_name(source_path)))
    return names


def generate(source_dir: Path, dest_dir: Path, system_agents_dir: Path | None = None) -> tuple[int, int, list[str]]:
    dest_dir.mkdir(parents=True, exist_ok=True)
    reserved_names = system_agent_names(system_agents_dir)
    rendered: list[tuple[Path, str, str, str]] = []
    skipped: list[str] = []

    for source_path in sorted(source_dir.glob("*.md")):
        if source_path.name.lower() == "readme.md":
            continue
        try:
            toml_name, managed_content, legacy_content = render_toml(source_path)
        except OSError as error:
            skipped.append(f"{source_path.name}: read error ({error})")
            continue
        if toml_name in reserved_names:
            skipped.append(f"{source_path.name}: name conflicts with system agent")
            continue
        rendered.append((source_path, toml_name, managed_content, legacy_content))

    allowed_names = {f"{toml_name}.toml" for _path, toml_name, _managed, _legacy in rendered}
    pruned = 0
    for dest_path in sorted(dest_dir.glob("*.toml")):
        current = dest_path.read_text(encoding="utf-8", errors="replace")
        if current.startswith(MANAGED_MARKER + "\n") and dest_path.name not in allowed_names:
            dest_path.unlink()
            pruned += 1

    converted = 0
    for source_path, toml_name, managed_content, legacy_content in rendered:
        dest_path = dest_dir / f"{toml_name}.toml"
        current = dest_path.read_text(encoding="utf-8", errors="replace") if dest_path.exists() else ""
        if current == managed_content:
            converted += 1
            continue
        if current and not (
            current.startswith(MANAGED_MARKER + "\n") or current == legacy_content
        ):
            skipped.append(
                f"{source_path.name}: {dest_path.name} exists and is not agent-crew managed"
            )
            continue
        dest_path.write_text(managed_content, encoding="utf-8")
        converted += 1

    return converted, pruned, skipped


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_dir")
    parser.add_argument("dest_dir")
    parser.add_argument("--system-agents-dir")
    args = parser.parse_args()

    source_dir = Path(args.source_dir)
    if not source_dir.is_dir():
        raise SystemExit(f"source_dir not found: {source_dir}")
    system_dir = Path(args.system_agents_dir) if args.system_agents_dir else None
    converted, pruned, skipped = generate(source_dir, Path(args.dest_dir), system_dir)
    print(
        f"[generate-codex-user-agents] converted={converted} pruned={pruned} "
        f"destination={args.dest_dir}"
    )
    for detail in skipped:
        print(f"[generate-codex-user-agents] SKIP: {detail}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
