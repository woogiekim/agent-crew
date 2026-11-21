#!/usr/bin/env python3
"""Verify installed source-owned assets match the source checkout."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shlex
import subprocess
import tempfile
from pathlib import Path


LEGACY_CODEX_DASH_SKILLS = (
    "crew-agent-maker",
    "crew-agent",
    "crew-cost",
    "crew-interact",
    "crew-run",
    "crew-sessions",
    "crew-setup",
    "crew-smm",
    "crew-sync-instructions",
    "crew-status",
    "crew-task",
    "crew-telemetry",
    "crew-update",
    "crew-workflow",
)

SOURCE_IDENTITY_FILES = (
    "install.sh",
    "core/bin/crew",
    "core/commands/run.md",
    "core/rules/task-injection.md",
    "core/scripts/sync-local-install.sh",
    "adapters/codex/skill/crew:run/SKILL.md",
    "adapters/codex/invocation.md",
)
SOURCE_IDENTITY_DIRS = (
    "core/commands",
    "core/rules",
    "adapters/codex/skill",
)
SOURCE_MANAGED_SENTINELS = (
    "core/hooks/route-directive-guard.sh",
    "core/evaluations/phase-2-validation.json",
    "core/policies/agent-capabilities.json",
    "core/schemas/session.schema.json",
    "core/setup/setup-host.sh",
    "core/agents/resolver.md",
    "core/agents/skills/tdd.md",
    "core/bin/memory",
    "adapters/codex/setup.sh",
    "adapters/codex/template/config.toml",
    "adapters/codex/model-policy.json",
    "core/scripts/generate-codex-system-agents.py",
    "core/schemas/runtime-managed-source-inventory.json",
)
SOURCE_INVENTORY = "core/schemas/runtime-managed-source-inventory.json"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def is_python_runtime_cache(path: Path, root: Path) -> bool:
    relative = path.relative_to(root)
    return "__pycache__" in relative.parts or path.suffix in {".pyc", ".pyo"}


def source_files(root: Path) -> dict[str, Path]:
    if not root.is_dir():
        return {}
    return {
        str(path.relative_to(root)): path
        for path in sorted(root.rglob("*"))
        if path.is_file() and not is_python_runtime_cache(path, root)
    }


def dest_files(root: Path) -> dict[str, Path]:
    if not root.is_dir():
        return {}
    return {
        str(path.relative_to(root)): path
        for path in sorted(root.rglob("*"))
        if path.is_file() and not is_python_runtime_cache(path, root)
    }


def compare_tree(src: Path, dest: Path, *, prune_extra: bool) -> dict:
    return compare_trees([src], dest, prune_extra=prune_extra)


def compare_trees(
    src_roots: list[Path], dest: Path, *, prune_extra: bool, overrides: Path | None = None
) -> dict:
    src_map: dict[str, Path] = {}
    for src in src_roots:
        src_map.update(source_files(src))
    applied_overrides = {}
    if overrides is not None:
        for path in overrides.glob("*.md"):
            if path.name in src_map and path.is_file():
                src_map[path.name] = path
                applied_overrides[path.name] = sha256_file(path)

    dest_map = dest_files(dest)
    missing = []
    mismatched = []
    extra = []

    for rel, src_path in src_map.items():
        dest_path = dest / rel
        if not dest_path.is_file():
            missing.append(rel)
            continue
        if sha256_file(src_path) != sha256_file(dest_path):
            mismatched.append(rel)

    for rel, dest_path in dest_map.items():
        if rel in src_map:
            continue
        extra.append(rel)
        if prune_extra:
            dest_path.unlink()

    check = {
        "source": ", ".join(str(src) for src in src_roots),
        "destination": str(dest),
        "missing": missing,
        "mismatched": mismatched,
        "extra": extra,
        "passed": not missing and not mismatched and (not extra or prune_extra),
    }
    if applied_overrides:
        material = json.dumps(applied_overrides, sort_keys=True).encode()
        check["source_projection"] = hashlib.sha256(material).hexdigest()
    return check


def compare_expected_trees(src_roots: list[Path], dest: Path, *, overrides: Path | None = None) -> dict:
    """Compare source-owned files without treating shared-destination extras as drift."""
    result = compare_trees(src_roots, dest, prune_extra=False, overrides=overrides)
    result["extra"] = []
    result["passed"] = not result["missing"] and not result["mismatched"]
    return result


def compare_expected_flat_files(src: Path, dest: Path, pattern: str = "*.md") -> dict:
    missing = []
    mismatched = []
    for source_path in sorted(src.glob(pattern)) if src.is_dir() else []:
        destination = dest / source_path.name
        if not destination.is_file():
            missing.append(source_path.name)
        elif sha256_file(source_path) != sha256_file(destination):
            mismatched.append(source_path.name)
    return {
        "source": str(src),
        "destination": str(dest),
        "missing": missing,
        "mismatched": mismatched,
        "extra": [],
        "passed": not missing and not mismatched,
    }


def compare_merged_expected_flat_files(system_src: Path, user_src: Path, dest: Path) -> dict:
    expected = {path.name: path for path in system_src.glob("*.md")} if system_src.is_dir() else {}
    if user_src.is_dir():
        expected.update({path.name: path for path in user_src.glob("*.md")})
    missing, mismatched = [], []
    for name, source in sorted(expected.items()):
        installed = dest / name
        if not installed.is_file():
            missing.append(name)
        elif sha256_file(source) != sha256_file(installed):
            mismatched.append(name)
    return {
        "source": f"{system_src}, {user_src}", "destination": str(dest),
        "missing": missing, "mismatched": mismatched, "extra": [],
        "passed": not missing and not mismatched,
    }


def compare_merged_expected_trees(system_src: Path, user_src: Path, dest: Path) -> dict:
    """Expected contents of a user-wins discovery tree (system layer + user layer)."""
    expected: dict[str, Path] = dict(source_files(system_src))
    for rel, path in source_files(user_src).items():
        # merge_rules_to_discovery projects *.md only, and treats a user-layer
        # README.md as documentation rather than a rule.
        if path.suffix != ".md" or Path(rel).name == "README.md":
            continue
        expected[rel] = path

    missing, mismatched = [], []
    for rel, source in sorted(expected.items()):
        installed = dest / rel
        if not installed.is_file():
            missing.append(rel)
        elif sha256_file(source) != sha256_file(installed):
            mismatched.append(rel)

    return {
        "source": f"{system_src}, {user_src}",
        "destination": str(dest),
        "missing": missing,
        "mismatched": mismatched,
        "extra": [],
        "passed": not missing and not mismatched,
    }


def compare_codex_managed_hooks(dest: Path, home: Path) -> dict:
    tracker = "mcp__plane__create_work_item|mcp__plane__update_work_item|mcp__plane__delete_work_item|mcp__plane__create_intake_work_item|mcp__plane__create_label|mcp__plane__create_work_item_comment|mcp__plane.create_work_item|mcp__plane.update_work_item|mcp__plane.delete_work_item|mcp__plane.create_intake_work_item|mcp__plane.create_label|mcp__plane.create_work_item_comment"
    required = {
        ("PreToolUse", "Bash", "guard-dangerous-commands.sh", 10),
        ("PreToolUse", tracker, "tracker-mutation-guard.sh", 10),
        ("PreToolUse", "Agent", "context-guard.sh", 10),
        ("PreToolUse", "Edit|Write|MultiEdit|apply_patch", "direct-edit-guard.sh", 10),
        ("PostToolUse", "*", "post-tool-use-dispatcher.sh", 15),
        ("UserPromptSubmit", "", "general-memory-context.sh", 10),
        ("UserPromptSubmit", "", "auto-issue-report.sh", 10),
        ("UserPromptSubmit", "", "auto-route.sh", 15),
    }


    found, observed, occurrences, invalid_managed = set(), [], {}, False
    error = None
    try:
        data = json.loads(dest.read_text(encoding="utf-8"))
        hooks = data.get("hooks", {}) if isinstance(data, dict) else None
        if not isinstance(hooks, dict):
            raise ValueError("hooks must be an object")
        for event, blocks in hooks.items():
            if not isinstance(blocks, list):
                continue
            for block in blocks:
                if not isinstance(block, dict) or not isinstance(block.get("hooks"), list):
                    continue
                matcher = str(block.get("matcher", ""))
                for hook in block["hooks"]:
                    if not isinstance(hook, dict) or hook.get("type") != "command":
                        continue
                    try:
                        tokens = shlex.split(str(hook.get("command", "")))
                    except ValueError:
                        continue
                    for name in {item[2] for item in required}:
                        expected_path = (home / "hooks" / name).resolve()
                        path_is_present = any(
                            Path(token).expanduser().resolve() == expected_path for token in tokens if token
                        )
                        if path_is_present:
                            occurrence_key = (event, matcher, name)
                            occurrences[occurrence_key] = occurrences.get(occurrence_key, 0) + 1
                            observed.append((
                                event, matcher, name,
                                f"{type(hook.get('timeout')).__name__}:{hook.get('timeout')!r}",
                                tuple(tokens),
                            ))
                        valid_command = len(tokens) == 2 and tokens[0] == "bash" \
                            and Path(tokens[1]).expanduser().resolve() == expected_path
                        if path_is_present and (not valid_command or not isinstance(hook.get("timeout"), int)):
                            invalid_managed = True
                        if valid_command and isinstance(hook.get("timeout"), int):
                            found.add((event, matcher, name, hook.get("timeout")))
    except Exception as exc:
        error = type(exc).__name__
    projection = hashlib.sha256(json.dumps({
        "found": sorted(found), "observed_managed_commands": sorted(observed),
        "duplicate_managed_commands": sorted(key for key, count in occurrences.items() if count > 1),
        "invalid_managed_command": invalid_managed, "parse_error": error,
    }, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
    passed = error is None and required.issubset(found) and not invalid_managed \
        and all(count == 1 for count in occurrences.values())
    return {
        "source": "generated:codex-managed-hooks", "destination": str(dest),
        "missing": [str(dest)] if not dest.is_file() else [],
        "mismatched": [] if passed or not dest.is_file() else [str(dest)],
        "extra": [], "passed": passed, "projection": projection,
    }


def _toml_section_assignments(path: Path, section: str) -> dict[str, str]:
    assignments, active = {}, False
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line.startswith("[") and line.endswith("]"):
            active = line == f"[{section}]"
            continue
        if active and line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            assignments[key.strip()] = value.split("#", 1)[0].strip()
    return assignments


def compare_codex_managed_config(template: Path, dest: Path) -> dict:
    missing, mismatched = [], []
    try:
        expected = _toml_section_assignments(template, "agents")
        installed = _toml_section_assignments(dest, "agents")
        if any(installed.get(key) != value for key, value in expected.items()):
            mismatched.append(str(dest))
        projection_value = {key: installed.get(key) for key in expected}
    except FileNotFoundError:
        missing.append(str(dest))
        projection_value = {"error": "FileNotFoundError"}
    except (OSError, ValueError) as exc:
        mismatched.append(str(dest))
        projection_value = {"error": type(exc).__name__}
    return {
        "source": str(template), "destination": str(dest), "missing": missing,
        "mismatched": mismatched, "extra": [], "passed": not missing and not mismatched,
        "projection": hashlib.sha256(json.dumps(projection_value, sort_keys=True).encode()).hexdigest(),
    }


def compare_codex_generated_agents(source_root: Path, home: Path, dest: Path) -> dict:
    generator = source_root / "core" / "scripts" / "generate-codex-system-agents.py"
    missing, mismatched, extra = [], [], []
    with tempfile.TemporaryDirectory(prefix="agent-crew-verify-agents-") as temp:
        expected_root = Path(temp)
        completed = subprocess.run([
            "python3", str(generator), str(source_root / "core" / "agents"), str(expected_root),
            "--source-ref-root", str(home / "system" / "agents"),
            "--model-policy", str(source_root / "adapters" / "codex" / "model-policy.json"),
        ], text=True, capture_output=True)
        if completed.returncode != 0:
            raise ValueError("Codex managed agent projection could not be generated")
        user_generator = source_root / "core" / "scripts" / "generate-codex-user-agents.py"
        if user_generator.is_file() and (home / "user" / "agents").is_dir():
            completed = subprocess.run([
                "python3", str(user_generator), str(home / "user" / "agents"), str(expected_root),
                "--system-agents-dir", str(home / "system" / "agents"),
            ], text=True, capture_output=True)
            if completed.returncode != 0:
                raise ValueError("Codex user agent projection could not be generated")
        expected = source_files(expected_root)
        expected_projection = [(rel, sha256_file(path)) for rel, path in sorted(expected.items())]
        for rel, source in expected.items():
            installed = dest / rel
            if not installed.is_file():
                missing.append(rel)
            elif source.read_text(encoding="utf-8").replace("/private/var/", "/var/") != \
                    installed.read_text(encoding="utf-8").replace("/private/var/", "/var/"):
                mismatched.append(rel)
        installed_projection = {
            rel: sha256_file(dest / rel) if (dest / rel).is_file() else None for rel in sorted(expected)
        }
        markers = (
            "This is a Codex adapter bootstrap for the agent-crew system agent.",
            "Agent-crew system agent:",
            "# This is a Codex adapter bootstrap for an agent-crew user agent.",
        )
        for installed in sorted(dest.glob("*.toml")):
            if not installed.is_file() or installed.name in expected:
                continue
            text = installed.read_text(encoding="utf-8", errors="replace")
            if any(marker in text for marker in markers):
                extra.append(installed.name)
                installed_projection[f"extra:{installed.name}"] = sha256_file(installed)
    return {
        "source": ", ".join(str(path) for path in (
            source_root / "core" / "agents",
            home / "user" / "agents",
            source_root / "core" / "scripts" / "generate-codex-system-agents.py",
            source_root / "core" / "scripts" / "generate-codex-user-agents.py",
            source_root / "adapters" / "codex" / "model-policy.json",
        )), "destination": str(dest),
        "missing": missing, "mismatched": mismatched, "extra": extra,
        "passed": not missing and not mismatched and not extra,
        "source_projection": hashlib.sha256(
            json.dumps(expected_projection, sort_keys=True).encode()
        ).hexdigest(),
        "projection": hashlib.sha256(json.dumps(installed_projection, sort_keys=True).encode()).hexdigest(),
    }


def compare_claude_managed_hooks(dest: Path, claude_dir: Path) -> dict:
    tracker = "mcp__plane__create_work_item|mcp__plane__update_work_item|mcp__plane__delete_work_item|mcp__plane__create_intake_work_item|mcp__plane__create_label|mcp__plane__create_work_item_comment|mcp__plane.create_work_item|mcp__plane.update_work_item|mcp__plane.delete_work_item|mcp__plane.create_intake_work_item|mcp__plane.create_label|mcp__plane.create_work_item_comment"
    required = {
        ("UserPromptSubmit", "", "auto-route.sh", 5),
        ("UserPromptSubmit", "*", "general-memory-context.sh", 10),
        ("PreToolUse", "Agent|Task|Delegate", "context-guard.sh", 5),
        ("PreToolUse", "Agent|Task", "normalize-task-guard.sh", 5),
        ("PreToolUse", "Agent", "agent-diff-pre.sh", 5),
        ("PostToolUse", "Agent", "agent-diff-post.sh", 10),
        ("PostToolUse", "*", "supervisor-progress-guard.sh", 5),
        ("PostToolUse", "*", "cost-tracker.sh", 5),
        ("PostToolUse", "Bash", "tool-event-recorder.sh", 5),
        ("PostToolUse", "*", "mnemos-capture-guard.sh", 10),
        ("UserPromptSubmit", "*", "auto-issue-report.sh", 10),
        ("PostToolUse", "Bash", "auto-issue-report.sh", 10),
        ("PreToolUse", "Edit|Write", "direct-edit-guard.sh", 10),
        ("PreToolUse", "Bash", "guard-dangerous-commands.sh", 5),
        ("PreToolUse", tracker, "tracker-mutation-guard.sh", 10),
        ("PostToolUse", "Agent", "forbid-plaintext-approval.sh", 5),
        ("PostToolUse", "Agent", "route-directive-guard.sh", 5),
    }


    found, observed, occurrences, stale_managed, error = set(), [], {}, [], None
    expected_occurrences = {}
    for _, _, name, _ in required:
        expected_occurrences[name] = expected_occurrences.get(name, 0) + 1
    try:
        data = json.loads(dest.read_text(encoding="utf-8"))
        hooks = data.get("hooks", {}) if isinstance(data, dict) else None
        if not isinstance(hooks, dict):
            raise ValueError("hooks must be an object")
        for event, blocks in hooks.items():
            if not isinstance(blocks, list):
                continue
            for block in blocks:
                if not isinstance(block, dict) or not isinstance(block.get("hooks"), list):
                    continue
                matcher = str(block.get("matcher", ""))
                for hook in block["hooks"]:
                    if not isinstance(hook, dict):
                        continue
                    command = str(hook.get("command", ""))
                    try:
                        command_tokens = shlex.split(command)
                    except ValueError:
                        command_tokens = []
                    managed_root = (claude_dir / "agent-crew" / "hooks").resolve()
                    current_paths = {
                        (managed_root / managed_name).resolve() for managed_name in expected_occurrences
                    }
                    for token in command_tokens:
                        token_path = Path(token).expanduser().resolve()
                        try:
                            token_path.relative_to(managed_root)
                        except ValueError:
                            continue
                        if token_path not in current_paths:
                            stale_managed.append((event, matcher, str(token_path), command))
                    for managed_name in expected_occurrences:
                        managed_path = (claude_dir / "agent-crew" / "hooks" / managed_name).resolve()
                        if any(Path(token).expanduser().resolve() == managed_path for token in command_tokens if token):
                            occurrences[managed_name] = occurrences.get(managed_name, 0) + 1
                    for required_event, required_matcher, name, timeout in required:
                        expected_path = (claude_dir / "agent-crew" / "hooks" / name).resolve()
                        try:
                            tokens = shlex.split(command)
                        except ValueError:
                            tokens = []
                        exact_command = len(tokens) == 2 and tokens[0] == "bash" \
                            and Path(tokens[1]).expanduser().resolve() == expected_path
                        if name in command:
                            observed.append((event, matcher, name, repr(hook.get("timeout")), command))
                        if (event, matcher, exact_command, hook.get("type"), hook.get("timeout")) == \
                                (required_event, required_matcher, True, "command", timeout):
                            found.add((required_event, required_matcher, name, timeout))
    except Exception as exc:
        error = type(exc).__name__
    projection = hashlib.sha256(json.dumps(
        {"found": sorted(found), "observed": sorted(observed),
         "occurrences": sorted(occurrences.items()), "stale_managed": sorted(stale_managed),
         "error": error}, sort_keys=True
    ).encode()).hexdigest()
    passed = error is None and required.issubset(found) \
        and occurrences == expected_occurrences and not stale_managed
    return {
        "source": "generated:claude-managed-hooks", "destination": str(dest),
        "missing": [str(dest)] if not dest.is_file() else [],
        "mismatched": [] if passed or not dest.is_file() else [str(dest)],
        "extra": [], "passed": passed, "projection": projection,
    }


def compare_claude_generated_agents(home: Path, dest: Path) -> dict:
    system = home / "system" / "agents"
    user = home / "user" / "agents"
    expected = {path.name: path.read_text(encoding="utf-8") for path in system.glob("*.md")}
    if user.is_dir():
        expected.update({path.name: path.read_text(encoding="utf-8") for path in user.glob("*.md")
                         if path.name != "README.md" and path.name not in expected})
    tier_models = {"xhigh": "claude-fable-5", "deep": "claude-opus-4-8",
                   "balanced": "claude-sonnet-5", "light": "claude-haiku-4-5"}
    for name in {path.name for path in system.glob("*.md")} & expected.keys():
        text = expected[name]
        frontmatter = re.match(r"\A---\n(.*?)\n---\n", text, re.DOTALL)
        if not frontmatter:
            continue
        block = frontmatter.group(1)
        tier_match = re.search(r"^reasoning_tier:\s*(\S+)\s*$", block, re.MULTILINE)
        model = tier_models.get(tier_match.group(1) if tier_match else "balanced", tier_models["balanced"])
        if re.search(r"^model:\s*\S+\s*$", block, re.MULTILINE):
            block = re.sub(r"^model:\s*\S+\s*$", f"model: {model}", block, count=1, flags=re.MULTILINE)
        else:
            block = block.rstrip() + f"\nmodel: {model}"
        expected[name] = text[:frontmatter.start()] + "---\n" + block + "\n---\n" + text[frontmatter.end():]
    missing, mismatched, projection = [], [], {}
    for name, content in sorted(expected.items()):
        installed = dest / name
        if not installed.is_file():
            missing.append(name)
            projection[name] = None
        else:
            installed_content = installed.read_text(encoding="utf-8")
            projection[name] = hashlib.sha256(installed_content.encode()).hexdigest()
            if installed_content != content:
                mismatched.append(name)
    return {"source": f"{system}, {user}", "destination": str(dest), "missing": missing,
            "mismatched": mismatched, "extra": [], "passed": not missing and not mismatched,
            "projection": hashlib.sha256(json.dumps(projection, sort_keys=True).encode()).hexdigest()}


def source_identity(source_root: Path) -> dict:
    required_files = (*SOURCE_IDENTITY_FILES, *SOURCE_MANAGED_SENTINELS)
    missing = [rel for rel in required_files if not (source_root / rel).is_file()]
    missing.extend(rel for rel in SOURCE_IDENTITY_DIRS if not (source_root / rel).is_dir())
    inventory_error = None
    inventory_files = []
    try:
        inventory = json.loads((source_root / SOURCE_INVENTORY).read_text(encoding="utf-8"))
        inventory_files = inventory.get("files", []) if isinstance(inventory, dict) else []
        if not inventory_files or not all(isinstance(rel, str) and rel for rel in inventory_files):
            raise ValueError("runtime source inventory must contain files")
        missing.extend(rel for rel in inventory_files if not (source_root / rel).is_file())
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        inventory_error = type(exc).__name__
    markers = {}
    for rel, marker in (
        ("core/bin/crew", "deterministic shell entrypoint for agent-crew"),
        ("core/scripts/sync-local-install.sh", "sync-local-install.sh"),
    ):
        path = source_root / rel
        markers[rel] = path.is_file() and marker in path.read_text(encoding="utf-8", errors="replace")
    return {
        "valid": not missing and inventory_error is None and all(markers.values()),
        "required_files": list(required_files),
        "required_directories": list(SOURCE_IDENTITY_DIRS),
        "missing": missing,
        "markers": markers,
        "inventory_file": SOURCE_INVENTORY,
        "inventory_count": len(inventory_files),
        "inventory_error": inventory_error,
    }


def paths_fingerprint(paths: list[Path]) -> str:
    material = []
    for root in sorted({path.resolve() for path in paths}, key=str):
        if root.is_file():
            material.append((str(root), sha256_file(root)))
            continue
        for rel, path in source_files(root).items():
            material.append((f"{root}:{rel}", sha256_file(path)))
    return hashlib.sha256(json.dumps(material, sort_keys=True).encode("utf-8")).hexdigest()


def source_projection_fingerprint(checks: list[dict]) -> str:
    paths_hash = paths_fingerprint([
        Path(raw)
        for check in checks
        for raw in check["source"].split(", ")
    ])
    semantic = [check["source_projection"] for check in checks if "source_projection" in check]
    return hashlib.sha256(json.dumps({"paths": paths_hash, "semantic": semantic}, sort_keys=True).encode()).hexdigest()


def install_projection_fingerprint(checks: list[dict]) -> str:
    material = []
    for check in checks:
        if "projection" in check:
            material.append((str(check["destination"]), "semantic-projection", check["projection"]))
        source_map: dict[str, Path] = {}
        for raw in check["source"].split(", "):
            source = Path(raw)
            if source.is_file():
                source_map[source.name] = source
            else:
                source_map.update(source_files(source))
        destination = Path(check["destination"])
        for rel in sorted(source_map):
            installed = destination if destination.is_file() else destination / rel
            material.append((str(destination), rel, sha256_file(installed) if installed.is_file() else None))
        for rel in sorted(check["extra"]):
            extra = destination / rel
            material.append((str(destination), f"extra:{rel}", sha256_file(extra) if extra.is_file() else "present"))
    return hashlib.sha256(json.dumps(material, sort_keys=True).encode("utf-8")).hexdigest()


def compare_file(src: Path, dest: Path) -> dict:
    missing = []
    mismatched = []
    if not src.is_file():
        missing.append(str(src))
    elif not dest.is_file():
        missing.append(str(dest))
    elif sha256_file(src) != sha256_file(dest):
        mismatched.append(str(dest))
    return {
        "source": str(src),
        "destination": str(dest),
        "missing": missing,
        "mismatched": mismatched,
        "extra": [],
        "passed": not missing and not mismatched,
    }


def compare_required_text(dest: Path, required: str, source_label: str) -> dict:
    missing = []
    mismatched = []
    if not dest.is_file():
        missing.append(str(dest))
    elif required not in dest.read_text(encoding="utf-8", errors="replace"):
        mismatched.append(str(dest))
    return {
        "source": source_label,
        "destination": str(dest),
        "missing": missing,
        "mismatched": mismatched,
        "extra": [],
        "passed": not missing and not mismatched,
    }


def contains_symlink(root: Path) -> bool:
    return root.is_symlink() or any(path.is_symlink() for path in root.rglob("*"))


def compare_codex_command_skills(src: Path, dest: Path, *, prune_extra: bool) -> dict:
    missing = []
    mismatched = []
    extra = []

    if not src.is_dir():
        return {
            "source": str(src),
            "destination": str(dest),
            "missing": missing,
            "mismatched": mismatched,
            "extra": extra,
            "passed": True,
        }

    if dest.is_symlink():
        return {
            "source": str(src), "destination": str(dest), "missing": [],
            "mismatched": ["symlink at Codex skill root"], "extra": [], "passed": False,
        }

    for src_skill in sorted(path for path in src.iterdir() if (path / "SKILL.md").is_file()):
        rel_root = src_skill.name
        dest_skill = dest / rel_root
        if contains_symlink(dest_skill):
            mismatched.append(f"{rel_root} (symlink in managed skill)")
            continue
        src_files = source_files(src_skill)

        for rel, src_path in src_files.items():
            dest_path = dest_skill / rel
            display = f"{rel_root}/{rel}"
            if not dest_path.is_file():
                missing.append(display)
                continue
            if sha256_file(src_path) != sha256_file(dest_path):
                mismatched.append(display)
        for rel in sorted(set(dest_files(dest_skill)) - set(src_files)):
            extra.append(f"{rel_root}/{rel}")
            if prune_extra:
                (dest_skill / rel).unlink()

    for legacy_name in (*LEGACY_CODEX_DASH_SKILLS, "agent-crew"):
        legacy_path = dest / legacy_name
        if contains_symlink(legacy_path):
            mismatched.append(f"{legacy_name} (symlink in legacy skill)")
            continue
        if not legacy_path.exists():
            continue
        extra.append(legacy_name)
        if prune_extra:
            for child in sorted(legacy_path.rglob("*"), reverse=True):
                if child.is_file() or child.is_symlink():
                    child.unlink()
                elif child.is_dir():
                    child.rmdir()
            legacy_path.rmdir()

    return {
        "source": str(src),
        "destination": str(dest),
        "missing": missing,
        "mismatched": mismatched,
        "extra": extra,
        "passed": not missing and not mismatched and (not extra or prune_extra),
    }


COMMAND_REFERENCE = re.compile(r"~/.agent-crew/commands/([A-Za-z0-9._-]+\.md)")
LEGACY_COMMAND_NAME = re.compile(r"[a-z][a-z0-9-]*")


def regular_file_under(root: Path, path: Path) -> bool:
    """Recognize only real files inside a configured installation root."""
    return safe_install_path(root, path) and path.is_file()


def safe_install_path(root: Path, path: Path) -> bool:
    if not path.is_relative_to(root):
        return False
    return all(not part.is_symlink() for part in (path, *path.parents) if part == root or root in part.parents)


def command_names(root: Path, directory: Path) -> set[str]:
    if not safe_install_path(root, directory):
        return set()
    return {path.name for path in directory.glob("*.md") if regular_file_under(root, path)}


def wrapper_references(path: Path) -> set[str]:
    return set(COMMAND_REFERENCE.findall(path.read_text(encoding="utf-8", errors="replace")))


def legacy_crew_wrappers(home: Path):
    plugin = home / "plugins" / "crew"
    for host, directory, prefix in (("claude", "skills", "/"), ("codex", "skills-codex", "$")):
        manifest = plugin / f".{host}-plugin" / "plugin.json"
        if not regular_file_under(home, manifest):
            continue
        try:
            metadata = json.loads(manifest.read_text(encoding="utf-8"))
        except (ValueError, UnicodeError):
            continue
        if (
            not isinstance(metadata, dict)
            or metadata.get("name") != "crew"
            or metadata.get("author") != {"name": "agent-crew"}
            or (host == "codex" and metadata.get("skills") != "./skills-codex/")
        ):
            continue

        skill_root = plugin / directory
        if not safe_install_path(home, skill_root):
            continue
        for path in sorted(skill_root.glob("*/SKILL.md")):
            name = path.parent.name
            if not LEGACY_COMMAND_NAME.fullmatch(name) or not regular_file_under(home, path):
                continue
            target = f"{name}.md"
            invocation = f"{prefix}crew:{name}"
            flags = "disable-model-invocation: true\nuser-invocable: true\n" if host == "claude" else ""
            # The retired package has no receipt. Only its original generated page
            # is owned; filenames and a shared command reference are insufficient.
            generated = (
                f"---\nname: {name}\ndescription: Use only when the user explicitly invokes {invocation}. "
                f"Loads the provider-neutral crew:{name} command.\n{flags}---\n\n"
                f"# crew:{name}\n\nOrdinary natural language does not activate agent-crew.\n\n"
                f"1. Preserve all text after `{invocation}` as immutable raw input.\n"
                f"2. Read `~/.agent-crew/commands/{target}` in full.\n"
                "3. Execute that provider-neutral definition without selecting another command.\n"
                "4. Do not load unrelated host/plugin skills without explicit user approval.\n"
            )
            if path.read_bytes() == generated.encode("utf-8"):
                yield path, target


def check_command_wrappers(source_root: Path, home: Path, codex_home: Path, *, reconcile: bool) -> dict:
    source_skills = source_root / "adapters/codex/skill"
    active = (
        command_names(source_root, source_root / "core/commands")
        | command_names(home, home / "user/commands")
    )
    shipped = {path.parent.name: path for path in source_skills.glob("*/SKILL.md") if regular_file_under(source_root, path)}
    missing = [
        f"{path} -> {target}"
        for path in sorted(shipped.values())
        for target in sorted(wrapper_references(path) - active)
    ]
    legacy = [(path, target) for path, target in legacy_crew_wrappers(home) if target not in active]

    previous = home / "system/adapters/codex/skill"
    retired_native = []
    previous_skills = previous.glob("*/SKILL.md") if safe_install_path(home, previous) else ()
    for old in sorted(previous_skills):
        name = old.parent.name
        installed = codex_home / "skills" / name / "SKILL.md"
        if (
            name not in shipped
            and regular_file_under(home, old)
            and regular_file_under(codex_home, installed)
            and old.read_bytes() == installed.read_bytes()
        ):
            retired_native.extend((installed, target) for target in sorted(wrapper_references(old) - active))

    retired = [*legacy, *retired_native]
    if reconcile and not missing:
        for path in sorted({path for path, _target in retired}):
            path.unlink()

        previous_commands = home / "system/commands"
        for name in sorted(command_names(home, previous_commands) - active):
            installed = home / "commands" / name
            if regular_file_under(home, installed) and installed.read_bytes() == (previous_commands / name).read_bytes():
                installed.unlink()
    else:
        missing.extend(f"{path} -> {target}" for path, target in retired)

    return {
        "source": str(source_skills),
        "destination": "managed command wrapper targets",
        "missing": missing,
        "mismatched": [],
        "extra": [],
        "passed": not missing,
    }


def compare_claude_command_projection(source_root: Path, claude_dir: Path) -> dict:
    source = source_root / "core/commands"
    dest = claude_dir / "commands/crew"
    if not safe_install_path(claude_dir, dest) or contains_symlink(dest):
        return {
            "source": str(source), "destination": str(dest), "missing": [],
            "mismatched": ["symlink in managed Claude command path"], "extra": [], "passed": False,
        }
    return compare_tree(source, dest, prune_extra=False)


def runtime_checks(
    source_root: Path,
    home: Path,
    codex_home: Path,
    claude_dir: Path,
    path_bin: Path,
    *,
    skip_path_bin: bool,
    active_host: str,
    managed_path_clis: list[Path],
) -> list[dict]:
    checks = []
    mirrored_trees = (
        ("commands", "commands"),
        ("rules", "rules"),
        ("hooks", "hooks"),
        ("scripts", "scripts"),
        ("evaluations", "evaluations"),
        ("policies", "policies"),
        ("schemas", "schemas"),
        ("setup", "setup"),
        ("agents", "agents"),
        ("bin", "bin"),
    )
    for source_name, destination_name in mirrored_trees:
        source = source_root / "core" / source_name
        if source_name == "bin":
            checks.append(compare_trees([source], home / destination_name, prune_extra=False))
            continue
        if source_name == "commands":
            checks.append(compare_trees([source], home / "system" / destination_name, prune_extra=False))
            checks.append(compare_expected_trees(
                [source], home / destination_name, overrides=home / "user/commands"
            ))
            continue

        checks.append(compare_trees([source], home / "system" / destination_name, prune_extra=False))
        if source_name == "rules":
            # Discovery rules are a user-wins merge of system/rules + user/rules,
            # so the source tree alone is not the expected content.
            checks.append(compare_merged_expected_trees(
                home / "system" / "rules", home / "user" / "rules", home / destination_name
            ))
            continue
        if source_name in {"hooks", "scripts", "evaluations", "policies", "schemas", "setup"}:
            checks.append(compare_expected_trees([source], home / destination_name))

    checks.append(
        compare_trees(
            [source_root / "core" / "agents" / "skills"],
            home / "system" / "skills",
            prune_extra=False,
        )
    )
    checks.append(compare_merged_expected_flat_files(
        source_root / "core" / "agents" / "skills", home / "user" / "skills", home / "skills"
    ))
    if active_host and active_host != "none":
        adapter_source = source_root / "adapters" / active_host
        checks.append(compare_trees([adapter_source], home / "system" / "adapters" / active_host, prune_extra=False))
        checks.append(compare_trees([adapter_source], home / "adapters" / active_host, prune_extra=False))
    if active_host == "codex":
        checks.append(compare_codex_command_skills(
            source_root / "adapters" / "codex" / "skill", codex_home / "skills", prune_extra=False
        ))
        checks.append(compare_file(
            source_root / "adapters" / "codex" / "invocation.md",
            codex_home / "agent-crew" / "invocation.md",
        ))
        checks.append(compare_codex_managed_hooks(codex_home / "hooks.json", home))
        checks.append(compare_codex_managed_config(
            source_root / "adapters" / "codex" / "template" / "config.toml", codex_home / "config.toml"
        ))
        checks.append(compare_trees([home / "skills"], codex_home / "agent-crew" / "skills", prune_extra=False))
        checks.append(compare_codex_generated_agents(source_root, home, codex_home / "agents"))
    if active_host == "claude":
        for name in ("hooks", "rules", "scripts", "setup"):
            checks.append(compare_expected_trees([home / name], claude_dir / "agent-crew" / name))
        checks.append(compare_expected_trees(
            [home / "adapters" / "claude"], claude_dir / "agent-crew" / "adapters" / "claude"
        ))
        checks.append(compare_file(home / "adapters" / "claude" / "invocation.md", claude_dir / "agent-crew" / "invocation.md"))
        checks.append(compare_trees(
            [source_root / "core" / "commands"], claude_dir / "commands" / "crew", prune_extra=False
        ))
        checks.append(compare_expected_trees([home / "system" / "agents"], claude_dir / "agent-crew" / "agents"))
        checks.append(compare_expected_trees([home / "skills"], claude_dir / "agent-crew" / "skills"))
        checks.append(compare_claude_generated_agents(home, claude_dir / "agents"))
        checks.append(compare_claude_managed_hooks(claude_dir / "settings.json", claude_dir))
    if not skip_path_bin:
        candidates = managed_path_clis or [path_bin / "crew"]
        for candidate in dict.fromkeys(candidates):
            expected = source_root / "core" / "bin" / "crew"
            if candidate.is_symlink():
                check = {
                    "source": str(expected), "destination": str(candidate), "missing": [],
                    "mismatched": [str(candidate)], "extra": [], "passed": False,
                }
            else:
                check = compare_file(expected, candidate)
                if check["passed"] and not os.access(candidate, os.X_OK):
                    check.update(mismatched=[str(candidate)], passed=False)
            checks.append(check)
    return checks


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", required=True)
    parser.add_argument("--agent-crew-home", default=os.environ.get("AGENT_CREW_HOME", str(Path.home() / ".agent-crew")))
    parser.add_argument("--codex-home", default=os.environ.get("CODEX_HOME", str(Path.home() / ".codex")))
    parser.add_argument("--claude-dir")
    parser.add_argument("--path-bin", default=os.environ.get("AGENT_CREW_PATH_BIN", str(Path.home() / ".local" / "bin")))
    parser.add_argument("--skip-path-bin", action="store_true")
    parser.add_argument("--managed-path-cli", action="append", default=[])
    parser.add_argument("--prune-extra", action="store_true")
    parser.add_argument("--reconcile-retired-command-wrappers", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--profile", choices=["install", "runtime-readonly"], default="install")
    parser.add_argument("--active-host", choices=["none", "codex", "claude", "generic"], default="none")
    parser.add_argument("--format", choices=["text", "json"], default="text")
    args = parser.parse_args()

    source_root = Path(args.source_root).expanduser().resolve()
    home = Path(args.agent_crew_home).expanduser().resolve()
    codex_home = Path(args.codex_home).expanduser().resolve()
    claude_location = args.claude_dir or os.environ.get("CLAUDE_DIR", str(Path.home() / ".claude"))
    claude_dir = Path(claude_location).expanduser().resolve()
    path_bin = Path(args.path_bin).expanduser().resolve()

    if args.reconcile_retired_command_wrappers:
        if args.profile != "install":
            parser.error("command wrapper reconciliation requires the install profile")
        check = check_command_wrappers(source_root, home, codex_home, reconcile=True)
        for reference in check["missing"]:
            print(f"Missing managed command target: {reference}")
        return 0 if check["passed"] else 1

    identity = source_identity(source_root)
    if args.profile == "runtime-readonly" and not identity["valid"]:
        payload = {
            "schema_version": 1,
            "profile": args.profile,
            "status": "NOT_APPLICABLE" if not (source_root / "core").exists() else "UNKNOWN",
            "source_root": str(source_root),
            "agent_crew_home": str(home),
            "codex_home": str(codex_home),
            "passed": False if (source_root / "core").exists() else True,
            "source_identity": identity,
            "active_host": args.active_host,
            "checks": [],
        }
        if args.format == "json":
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(f"{payload['status']}: runtime install drift check")
        return 0 if payload["status"] == "NOT_APPLICABLE" else 2

    if args.profile == "runtime-readonly":
        try:
            checks = runtime_checks(
                source_root,
                home,
                codex_home,
                claude_dir,
                path_bin,
                skip_path_bin=args.skip_path_bin,
                active_host=args.active_host,
                managed_path_clis=[Path(path).expanduser() for path in args.managed_path_cli],
            )
        except (OSError, ValueError) as error:
            payload = {
                "schema_version": 1,
                "profile": args.profile,
                "status": "UNKNOWN",
                "source_root": str(source_root),
                "agent_crew_home": str(home),
                "codex_home": str(codex_home),
                "passed": False,
                "error": str(error),
                "checks": [],
                "source_identity": identity,
                "active_host": args.active_host,
            }
            if args.format == "json":
                print(json.dumps(payload, ensure_ascii=False, indent=2))
            else:
                print(f"UNKNOWN: runtime install drift check ({error})")
            return 2
    else:
        checks = []
        for rel in ("hooks", "scripts", "evaluations", "policies"):
            src = source_root / "core" / rel
            checks.append(compare_tree(src, home / "system" / rel, prune_extra=args.prune_extra))
            checks.append(compare_expected_trees([src], home / rel))

        checks.append(
            compare_tree(
                source_root / "core" / "commands",
                home / "system" / "commands",
                prune_extra=args.prune_extra,
            )
        )
        # The user command seed layer is operator-owned once installed, so the
        # discovery view is expected to match the INSTALLED user layer, not the
        # source seeds.
        checks.append(
            compare_expected_trees(
                [source_root / "core" / "commands", home / "user" / "commands"],
                home / "commands",
            )
        )

        checks.append(compare_tree(source_root / "core" / "bin", home / "bin", prune_extra=args.prune_extra))
        checks.append(
            compare_codex_command_skills(
                source_root / "adapters" / "codex" / "skill",
                codex_home / "skills",
                prune_extra=args.prune_extra,
            )
        )
        checks.append(check_command_wrappers(source_root, home, codex_home, reconcile=False))
        claude_commands = claude_dir / "commands/crew"
        if args.claude_dir and (
            (claude_dir / "agent-crew").is_dir() or claude_commands.exists() or claude_commands.is_symlink()
        ):
            checks.append(compare_claude_command_projection(source_root, claude_dir))
        if not args.skip_path_bin:
            checks.append(compare_file(source_root / "core" / "bin" / "crew", path_bin / "crew"))

    payload = {
        "schema_version": 1,
        "profile": args.profile,
        "status": "MATCH" if all(check["passed"] for check in checks) else "MISMATCH",
        "source_identity": identity,
        "active_host": args.active_host,
        "source_fingerprint": source_projection_fingerprint(checks),
        "install_fingerprint": install_projection_fingerprint(checks),
        "source_root": str(source_root),
        "agent_crew_home": str(home),
        "codex_home": str(codex_home),
        "passed": all(check["passed"] for check in checks),
        "checks": checks,
    }

    if args.format == "json":
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(("PASS" if payload["passed"] else "FAIL") + ": install drift check")
        for check in checks:
            if check["passed"]:
                continue
            print(f"- {check['destination']}")
            if check["missing"]:
                print("  missing: " + ", ".join(check["missing"]))
            if check["mismatched"]:
                print("  mismatched: " + ", ".join(check["mismatched"]))
            if check["extra"]:
                print("  extra: " + ", ".join(check["extra"]))

    return 0 if payload["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
