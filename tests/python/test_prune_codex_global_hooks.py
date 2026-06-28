"""Tests for pruning legacy global Codex agent-crew hook registrations."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPT = REPO_ROOT / "core" / "scripts" / "prune-codex-global-hooks.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("prune_codex_global_hooks", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


module = _load_module()


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def test_prune_managed_global_hooks_when_project_hooks_exist(tmp_path: Path):
    home = tmp_path / "agent-crew"
    global_hooks = tmp_path / "codex" / "hooks.json"
    project_hooks = tmp_path / "project" / ".codex" / "hooks.json"

    _write_json(project_hooks, {"hooks": {"UserPromptSubmit": [{"hooks": []}]}})
    _write_json(
        global_hooks,
        {
            "hooks": {
                "UserPromptSubmit": [
                    {
                        "hooks": [
                            {"type": "command", "command": f"bash '{home}/hooks/auto-route.sh'"},
                            {"type": "command", "command": "/usr/local/bin/user-prompt-hook"},
                        ]
                    }
                ],
                "PreToolUse": [
                    {
                        "matcher": "Bash",
                        "hooks": [
                            {"type": "command", "command": f"bash '{home}/hooks/guard-dangerous-commands.sh'"},
                            {"type": "command", "command": "/usr/local/bin/user-pre-hook"},
                        ],
                    }
                ],
            },
            "other": "preserved",
        },
    )

    result = module.prune(global_hooks, project_hooks, home)

    assert result["changed"] is True
    data = json.loads(global_hooks.read_text(encoding="utf-8"))
    assert data["other"] == "preserved"
    assert data["hooks"]["UserPromptSubmit"][0]["hooks"] == [
        {"type": "command", "command": "/usr/local/bin/user-prompt-hook"}
    ]
    assert data["hooks"]["PreToolUse"][0]["hooks"] == [
        {"type": "command", "command": "/usr/local/bin/user-pre-hook"}
    ]


def test_prune_leaves_global_hooks_when_project_hooks_are_absent(tmp_path: Path):
    home = tmp_path / "agent-crew"
    global_hooks = tmp_path / "codex" / "hooks.json"
    project_hooks = tmp_path / "project" / ".codex" / "hooks.json"

    payload = {
        "hooks": {
            "UserPromptSubmit": [
                {"hooks": [{"type": "command", "command": f"bash '{home}/hooks/auto-route.sh'"}]}
            ]
        }
    }
    _write_json(global_hooks, payload)

    result = module.prune(global_hooks, project_hooks, home)

    assert result["changed"] is False
    assert json.loads(global_hooks.read_text(encoding="utf-8")) == payload


def test_prune_removes_empty_managed_only_hook_sections(tmp_path: Path):
    home = tmp_path / "agent-crew"
    global_hooks = tmp_path / "codex" / "hooks.json"
    project_hooks = tmp_path / "project" / ".codex" / "hooks.json"

    _write_json(project_hooks, {"hooks": {"UserPromptSubmit": [{"hooks": []}]}})
    _write_json(
        global_hooks,
        {
            "hooks": {
                "UserPromptSubmit": [
                    {
                        "hooks": [
                            {"type": "command", "command": f"bash '{home}/hooks/auto-issue-report.sh'"},
                            {"type": "command", "command": f"bash '{home}/hooks/auto-route.sh'"},
                        ]
                    }
                ]
            }
        },
    )

    result = module.prune(global_hooks, project_hooks, home)

    assert result["changed"] is True
    assert json.loads(global_hooks.read_text(encoding="utf-8")) == {}
