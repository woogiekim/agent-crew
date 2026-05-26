"""Tests for core objective capability ceiling helpers."""

from __future__ import annotations

import importlib.util
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPT = REPO_ROOT / "core" / "scripts" / "core_objective_lib.py"


def load_core_objective_module():
    spec = importlib.util.spec_from_file_location("core_objective_lib", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_capability_ceiling_reports_native_ready_when_all_capabilities_are_true():
    module = load_core_objective_module()
    capabilities = {"host": "claude"}
    capabilities.update({name: True for name in module.CORE_RUNTIME_CAPABILITIES})

    ceiling = module.capability_ceiling(capabilities)

    assert ceiling["status"] == "native_runtime_ready"
    assert ceiling["native_capability_count"] == ceiling["total_capabilities"]
    assert module.summary_for_status("native_runtime_ready") == (
        "Host advertises all core runtime capabilities natively."
    )
