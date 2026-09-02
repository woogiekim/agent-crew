"""Tests for the task-bound mutation scope resolver."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPT = REPO_ROOT / "core" / "scripts" / "mutation_scope.py"


def load_module():
    spec = importlib.util.spec_from_file_location("mutation_scope", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_missing_scope_uses_legacy_workspace_write_default(tmp_path: Path):
    (tmp_path / "register.json").write_text("{}\n", encoding="utf-8")

    assert load_module().task_mutation_scope(tmp_path) == "workspace_write"


def test_blank_explicit_scope_fails_closed(tmp_path: Path):
    (tmp_path / "register.json").write_text(
        json.dumps({"mutation_scope": "  "}) + "\n",
        encoding="utf-8",
    )

    assert load_module().task_mutation_scope(tmp_path) == "read_only"


def test_malformed_register_fails_closed(tmp_path: Path):
    (tmp_path / "register.json").write_text("{not-json}\n", encoding="utf-8")

    assert load_module().task_mutation_scope(tmp_path) == "read_only"
