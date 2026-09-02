#!/usr/bin/env python3
"""Resolve the mutation scope bound to the current agent-crew task."""

from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
from types import ModuleType
from typing import Iterable


DEFAULT_MUTATION_SCOPE = "workspace_write"
READ_ONLY_MUTATION_SCOPE = "read_only"
VALID_MUTATION_SCOPES = {DEFAULT_MUTATION_SCOPE, READ_ONLY_MUTATION_SCOPE}


def task_mutation_scope(task_dir: Path | str) -> str:
    register_path = Path(task_dir) / "register.json"
    if not register_path.is_file():
        return DEFAULT_MUTATION_SCOPE
    try:
        register = json.loads(register_path.read_text(encoding="utf-8"))
    except Exception:
        return READ_ONLY_MUTATION_SCOPE
    if not isinstance(register, dict):
        return READ_ONLY_MUTATION_SCOPE

    value = register.get("mutation_scope")
    if value is None:
        return DEFAULT_MUTATION_SCOPE
    scope = str(value).strip()
    if scope in VALID_MUTATION_SCOPES:
        return scope
    return READ_ONLY_MUTATION_SCOPE


def _load_project_state_module(
    agent_crew_home: Path,
    project_root: Path,
    script_roots: Iterable[Path] = (),
) -> ModuleType | None:
    candidates = [
        agent_crew_home / "scripts" / "project_state.py",
        agent_crew_home / "system" / "scripts" / "project_state.py",
        *(root / "project_state.py" for root in script_roots),
        project_root / "core" / "scripts" / "project_state.py",
    ]
    for candidate in candidates:
        if not candidate.is_file():
            continue
        try:
            spec = importlib.util.spec_from_file_location(
                "agent_crew_mutation_scope_project_state", candidate
            )
            if spec is None or spec.loader is None:
                continue
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            return module
        except Exception:
            continue
    return None


def _task_roots(
    agent_crew_home: Path,
    project_root: Path,
    script_roots: Iterable[Path] = (),
) -> list[Path]:
    roots: list[Path] = []
    module = _load_project_state_module(
        agent_crew_home,
        project_root,
        script_roots,
    )
    if module is not None:
        try:
            state = module.resolve_project_state(
                home=str(agent_crew_home),
                project_root=str(project_root),
                ensure=False,
                migrate_legacy=False,
                prefer_existing_legacy=False,
            )
            for key in ("state_dir", "legacy_state_dir"):
                value = state.get(key)
                if value:
                    roots.append(Path(value) / "tasks")
        except Exception:
            pass

    roots.append(agent_crew_home / "state" / project_root.name / "tasks")

    unique: list[Path] = []
    seen: set[str] = set()
    for root in roots:
        key = str(root)
        if key in seen:
            continue
        seen.add(key)
        unique.append(root)
    return unique


def active_task_dirs(
    agent_crew_home: Path | str,
    project_root: Path | str,
    *,
    explicit_task_dir: Path | str | None = None,
    script_roots: Iterable[Path] = (),
) -> list[Path]:
    home = Path(agent_crew_home).expanduser().resolve(strict=False)
    project = Path(project_root).expanduser().resolve(strict=False)

    if explicit_task_dir:
        return [Path(explicit_task_dir).expanduser().resolve(strict=False)]

    active: list[Path] = []

    for tasks_root in _task_roots(home, project, script_roots):
        if not tasks_root.is_dir():
            continue
        try:
            markers = sorted(tasks_root.glob("active.*"))
        except Exception:
            continue
        for marker in markers:
            if not marker.is_file():
                continue
            task_id = marker.name.removeprefix("active.")
            if task_id:
                active.append(tasks_root / task_id)

    unique: list[Path] = []
    seen: set[str] = set()
    for task_dir in active:
        key = str(task_dir)
        if key in seen:
            continue
        seen.add(key)
        unique.append(task_dir)
    return unique


def active_read_only_task_dirs(
    agent_crew_home: Path | str,
    project_root: Path | str,
    *,
    explicit_task_dir: Path | str | None = None,
    script_roots: Iterable[Path] = (),
) -> list[Path]:
    return [
        task_dir
        for task_dir in active_task_dirs(
            agent_crew_home,
            project_root,
            explicit_task_dir=explicit_task_dir,
            script_roots=script_roots,
        )
        if task_mutation_scope(task_dir) == READ_ONLY_MUTATION_SCOPE
    ]


def configured_project_root(tool_input: object = None) -> Path:
    for name in ("AGENT_CREW_PROJECT_ROOT", "PROJECT_ROOT"):
        value = os.environ.get(name, "").strip()
        if value:
            return Path(value).expanduser().resolve(strict=False)
    if isinstance(tool_input, dict):
        value = str(tool_input.get("cwd") or "").strip()
        if value:
            return Path(value).expanduser().resolve(strict=False)
    return Path.cwd().resolve(strict=False)
